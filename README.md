# YT-Downloader-TGBot

**YT-Downloader-TGBot** is a Telegram bot that accepts links to either photos or YouTube videos and sends the media directly in Telegram. Videos are supported up to 50 MB in size due to Telegram Bot API limits.

---

## 📌 Features

- 📸 Send a **photo URL** to the bot — it replies with the image.
- 📹 Send a **YouTube video link** — it downloads and replies with the video (≤ 50 MB).
- ⚡ Fast and simple interface via Telegram.

---

## 🚀 Quick Start (Docker)

Run the bot entirely through Docker — no Python setup needed

---

### 📄 1. Create an `.env` file

Copy the following into a file named `.env` (have a look at `example.env`):
- `TOKEN`: Your bot token from [@BotFather](https://t.me/BotFather)
- `USERNAME`: Your bot's username (e.g. `MyCoolBot`)

---

### 🛠 2. Build the Docker image

In the project directory:

```bash
docker build -t yt-downloader-tgbot .
```
### ▶️ 3. Run the bot
Use the .env file when running the container:
```bash
docker run --env-file .env yt-downloader-tgbot
```