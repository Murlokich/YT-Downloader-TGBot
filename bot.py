import ffmpeg
import logging
import os
import requests
import validators
import yt_dlp
from yt_dlp import YoutubeDL
from typing import Final
from telegram import Update, error
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

TOKEN: Final[str] = os.getenv("TOKEN")
USERNAME: Final[str] = os.getenv("USERNAME")

DOWNLOADS_DIR_NAME: Final[str] = "downloads"
TELEGRAM_ERROR_MESSAGE: Final[str] = "Telegram error occured. Please try again later"
DOWNLOADER_ERROR_MESSAGE: Final[str] = "Downloading error occured. Please try again later"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger("yt_downloader")


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

    if len(context.args) != 1:
        await update.message.reply_text(
            "You must provide exactly one picture URL. Example:\n/picture https://example.com/picture.jpg"
        )
        return
    

    url = context.args[0]
    if not is_valid_url(url):
        await update.message.reply_text("Invalid url :(")
        return
    elif not is_image_url(url):
        await update.message.reply_text("Not an image :(")
        return
    else:
        try:
            img_data = requests.get(url).content
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=img_data, reply_to_message_id=update.message.id)
        except error.TelegramError as e:
            logger.error("Error while processing URL %s: %s", url, e.message)
            await update.message.reply_text(TELEGRAM_ERROR_MESSAGE)



async def video_from_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Handles the request for uploading video from URL
    """

    def clean_folder():
        """ If in downloads directory there are more then FILE_LIMIT_BEFORE_CLEANUP files, clean it
        """
        file_count = len(os.listdir(DOWNLOADS_DIR_NAME))
        FILE_LIMIT_BEFORE_CLEANUP: Final[int] = 14

        if file_count > FILE_LIMIT_BEFORE_CLEANUP:
            for file_name in os.listdir(DOWNLOADS_DIR_NAME):
                file_path = os.path.join(DOWNLOADS_DIR_NAME, file_name)
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
            filename = DOWNLOADS_DIR_NAME + '/' + info['id'] + '_cnv.mp4'
            duration = info.get('duration', None)
            if duration:
                duration /= 60  # convert from seconds to minutes
            return filename, duration

    def is_uploadable_video(file_path):
        """ Checks that video for provided path can be uploaded through telegram Bot (size < 50MB)
        :param file_path: path to the file which contains video
        :return: true if size is less than 50, false otherwise
        """
        FILE_SIZE_LIMIT_MB_TG: Final[int] = 50
        size_bytes = os.path.getsize(file_path)
        size_mb = size_bytes / (1024 * 1024)
        # max video size allowed to upload on telegram
        return size_mb < FILE_SIZE_LIMIT_MB_TG

    def download_video(url):
        """ Downloads video for provided url from youtube
        :param url: url for the video
        :return: path to the downloaded video
        """
        ydl_opts = {
            'outtmpl': '{}/%(id)s.%(ext)s'.format(DOWNLOADS_DIR_NAME),  # defines the format of filename
            # picks the best quality video among videos under 30 MB, video extension mp4 and audio m4a
            'format': 'best[filesize<30M]+bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4',
            'force_generic_extractor': True,
            'no_playlist': True,
        }
        with YoutubeDL(ydl_opts) as ydl:
            # downloads the video with information
            info = ydl.sanitize_info(ydl.extract_info(url))
            return "{}/{}.{}".format(DOWNLOADS_DIR_NAME, info['id'], info['ext'])

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
    if len(context.args) != 1:
        await update.message.reply_text(
            "You must provide exactly one video URL. Example:\n/video https://example.com/video.mp4"
        )
        return
    url = context.args[0]
    if not is_valid_url(url):
        # if url is invalid send the proper message
        await update.message.reply_text("Invalid url :(")
        return
    try:
        filename, duration = get_filename_duration(url)
        # videos longer then 14 minutes are not supported
        if duration > 14:
            await update.message.reply_text("Too long video to upload :(")
            return
        elif os.path.exists(filename):
            # if video was recently downloaded and still in memory, just send it
            await context.bot.send_video(chat_id=update.effective_chat.id, video=open(filename, 'rb'),
                                         read_timeout=100000, write_timeout=100000, reply_to_message_id=update.message.id)
        else:
            file_path = download_video(url)
            if not is_uploadable_video(file_path):
                # because yt-dlp still downloads files if None of them fit format request
                # check for size is required
                os.remove(file_path)
                await update.message.reply_text("Downloaded unsuccessfully: file is too large")
                return 
            else:
                file_path = change_codec_to_mp4(file_path)
                if not is_uploadable_video(file_path):
                    # because changing codec can change the size
                    # check is required
                    os.remove(filename)
                    await update.message.reply_text(text="Downloaded unsuccessfully: file is too large",)
                    return
                else:
                    # if everything is fine send the video
                    await context.bot.send_video(chat_id=update.effective_chat.id, video=filename,
                                                 read_timeout=1000000, write_timeout=100000)
    except yt_dlp.DownloadError as e:
        logger.error("Error while processing URL %s: %s", url, e.msg)
        await update.message.reply_text(DOWNLOADER_ERROR_MESSAGE)
        return
    except error.TelegramError as e:
        logger.error("Error while processing URL %s: %s", url, e.message)
        await update.message.reply_text(TELEGRAM_ERROR_MESSAGE)
        return

if __name__ == '__main__':
    application = ApplicationBuilder().token(TOKEN).build()

    start_handler = CommandHandler('start', start)
    picture_handler = CommandHandler('picture', picture_from_url)
    video_handler = CommandHandler('video', video_from_url)

    application.add_handler(start_handler)
    application.add_handler(picture_handler)
    application.add_handler(video_handler)

    if not os.path.exists(DOWNLOADS_DIR_NAME):
        os.makedirs(DOWNLOADS_DIR_NAME)

    application.run_polling()
