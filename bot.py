import ffmpeg
import logging
import os
import requests
import validators
import yt_dlp
from yt_dlp import YoutubeDL
from typing import Final
from telegram import Update, error
from telegram.ext import filters, MessageHandler, ApplicationBuilder, ContextTypes, CommandHandler

TOKEN: Final[str] = os.getenv("TOKEN")
USERNAME: Final[str] = os.getenv("USERNAME")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Handles the starting command from user
    """
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="I'm a bot, I can upload for you videos from youtube using url!\n"
                                        "Video must be under 50 MB and be shorter than 14 minutes")


async def picture_from_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Handles the request for uploading picture from URL
    """

    def is_valid_url(url: str):
        """ Checks if string is valid url
        :param url: string for check
        :return: true if is valid url, false otherwise
        """
        # validators.url(url) blocks cached images from Google images tab.
        # This code walks around the check
        google_tbn_templates = ["https://encrypted-tbn{}.gstatic.com/".format(i) for i in range(10)]
        for template in google_tbn_templates:
            if template in url:
                return True
        return validators.url(url)

    # some of the links to pictures don't have content-type
    def is_image_url(url: str):
        """ Checks if provided url points to a picture
        :param url: url for check
        :return: true if is picture, false otherwise
        """
        response = requests.head(url)
        content_type = response.headers.get('content-type')
        return content_type and 'image' in content_type

    if not is_valid_url(update.message.text):
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Invalid url :(")
    elif not is_image_url(update.message.text):
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Not an image :(")
    else:
        try:
            img_data = requests.get(update.message.text).content
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=img_data)
        except error.TelegramError as e:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=e.message)


async def video_from_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Handles the request for uploading video from URL
    """

    def clean_folder():
        """ If in downloads directory there are more then 14 files, clean it
        """
        directory = 'downloads'
        file_count = len(os.listdir(directory))
        if file_count > 14:
            for file_name in os.listdir(directory):
                file_path = os.path.join(directory, file_name)
                os.remove(file_path)

    def is_valid_url(url: str):
        """ Checks if string is valid url
        :param url: string for check
        :return: true if is valid url, false otherwise
        """
        return validators.url(url)

    def get_filename_duration(url):
        """ Gets the filename for future video file and duration of the video
        :param url: url with youtube video
        :return: if info was extracted correctly :
                    path to file from current directory:
                    downloads/{video_id}_cnv.mp4  and duration in minutes
                 otherwise:
                    error message and -1
        """
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4',
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            info = ydl.sanitize_info(info)
            filename = 'downloads/' + info['id'] + '_cnv.mp4'
            duration = info.get('duration', None)
            if duration:
                duration /= 60  # convert from seconds to minutes
            return filename, duration

    def is_uploadable_video(file_path):
        """ Checks that video for provided path can be uploaded through telegram Bot (size < 50MB)
        :param file_path: path to the file which contains video
        :return: true if size is less than 50, false otherwise
        """
        size_bytes = os.path.getsize(file_path)
        size_mb = size_bytes / (1024 * 1024)
        # max video size allowed to upload on telegram
        return size_mb < 50

    def download_video(url):
        """ Downloads video for provided url from youtube
        :param url: url for the video
        :return: path to the downloaded video
        """
        ydl_opts = {
            'outtmpl': 'downloads/%(id)s.%(ext)s',  # defines the format of filename
            # picks the best quality video among videos under 30 MB, video extension mp4 and audio m4a
            'format': 'best[filesize<30M]+bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4',
            'force_generic_extractor': True,
            'no_playlist': True,
        }
        with YoutubeDL(ydl_opts) as ydl:
            # downloads the video with information
            info = ydl.sanitize_info(ydl.extract_info(url))
            return "downloads/{}.{}".format(info['id'], info['ext'])

    def change_codec_to_mp4(input_filename):
        """ Changes codec to x264 which is proper codec for mp4
        :param input_filename: path to the video file
        """
        output_filename = input_filename[:-4] + "_cnv.mp4"
        (
            ffmpeg
            .input(input_filename)
            # commonly used codec for mp4 videos
            .output(output_filename, vcodec='libx264', crf=23, preset='medium', acodec='copy')
            .run()
        )
        # deletes tmp file from downloading using yt-dlp
        os.remove(input_filename)
        return output_filename

    clean_folder()
    try:
        filename, duration = get_filename_duration(update.message.text)
        # videos longer then 14 minutes are not supported
        if duration > 14:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Too long video to upload :(")
        elif os.path.exists(filename):
            # if video was recently downloaded and still in memory, just send it
            await context.bot.send_video(chat_id=update.effective_chat.id, video=open(filename, 'rb'),
                                         read_timeout=100000, write_timeout=100000)
        elif not is_valid_url(update.message.text):
            # if url is invalid send the proper message
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Invalid url :(")
        else:
            file_path = download_video(update.message.text)
            if not is_uploadable_video(file_path):
                # because yt-dlp still downloads files if None of them fit format request
                # check for size is required
                os.remove(file_path)
                await context.bot.send_message(chat_id=update.effective_chat.id,
                                               text="Downloaded unsuccessfully: file is too large")
            else:
                file_path = change_codec_to_mp4(file_path)
                if not is_uploadable_video(file_path):
                    # because changing codec can change the size
                    # check is required
                    os.remove(filename)
                    await context.bot.send_message(chat_id=update.effective_chat.id,
                                                   text="Downloaded unsuccessfully: file is too large")
                else:
                    # if everything is fine send the video
                    await context.bot.send_video(chat_id=update.effective_chat.id, video=filename,
                                                 read_timeout=1000000, write_timeout=100000)
    except yt_dlp.DownloadError as e:
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text="Problem with url or downloading the video :" + e.msg)
    except error.TelegramError as e:
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text="Problem with uploading the video or sending message: " + e.message)


async def non_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Handles every non-text message
    """
    await context.bot.send_message(chat_id=update.effective_chat.id, text="I can process only text messages!")


if __name__ == '__main__':
    application = ApplicationBuilder().token(TOKEN).build()

    start_handler = CommandHandler('start', start)
    url_video_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), video_from_url)
    non_text_handler = MessageHandler(~filters.TEXT, non_text_message)

    application.add_handler(start_handler)
    application.add_handler(url_video_handler)
    application.add_handler(non_text_handler)

    application.run_polling()
