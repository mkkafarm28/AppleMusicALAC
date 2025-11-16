# bot.py
import asyncio
import os
import logging
from pathlib import Path
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
)
from src.grpc.manager import WrapperManager
from src.core.downloader import AppleMusicDownloader
from src.utils import GlobalLogger

# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DOWNLOAD_BASE_DIR = Path("downloads")
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB
logger = GlobalLogger().logger

wrapper: WrapperManager = None
downloader: AppleMusicDownloader = None
app = Client("applemusic_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Codec options
CODECS = {
    "alac": "ALAC (Lossless)",
    "aac": "AAC (256 kbps)",
    "aac-binaural": "AAC Binaural",
    "aac-downmix": "AAC Downmix",
    "aac-legacy": "AAC Legacy",
    "ec3": "EC3 (Dolby)",
    "ac3": "AC3",
}

# User state: {user_id: {"url": str, "msg_id": int}}
USER_STATE = {}


# ----------------------------------------------------------------------
# Progress update
# ----------------------------------------------------------------------
async def update_progress(msg: Message, cur: int, total: int, name: str):
    if total == 0:
        return
    percent = cur / total
    bar = "█" * int(percent * 10) + "░" * (10 - int(percent * 10))
    text = f"`{name}`\n[{bar}] {percent:.1%}\n`{cur//1024} KB / {total//1024} KB`"
    try:
        await msg.edit_text(text, parse_mode="markdown")
    except Exception:
        pass


# ----------------------------------------------------------------------
# Handlers
# ----------------------------------------------------------------------
@app.on_message(filters.regex(r'^/start'))
async def start(client: Client, message: Message):
    logger.info("Start command received")
    try:
        await message.reply(
            "**Apple Music Downloader**\n\n"
            "Send a **song / album / artist / playlist** URL.\n"
            "Then choose codec.\n\n"
            "Example:\n"
            "https://music.apple.com/us/album/never-gonna-give-you-up/1441164362",
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Error replying to start: {e}")


@app.on_message(filters.text)
async def handle_url(client: Client, message: Message):
    if message.text.startswith('/'):
        return  # Skip command messages
    url = message.text.strip()
    user_id = message.from_user.id

    # Show codec buttons
    buttons = [[InlineKeyboardButton(text=v, callback_data=f"codec_{k}_{message.id}")] for k, v in CODECS.items()]
    keyboard = InlineKeyboardMarkup(buttons)

    status_msg = await message.reply(
        f"**URL Received!**\n\nChoose codec for:\n`{url}`",
        reply_markup=keyboard,
        parse_mode="markdown",
        disable_web_page_preview=True
    )

    # Store state
    USER_STATE[user_id] = {"url": url, "msg_id": status_msg.id}


@app.on_callback_query(filters.regex(r"^codec_(.+)_(\d+)$"))
async def handle_codec(client: Client, query: CallbackQuery):
    parts = query.data.split("_")
    codec = parts[1]
    orig_msg_id = parts[2]
    user_id = query.from_user.id

    if user_id not in USER_STATE:
        await query.answer("Session expired.", show_alert=True)
        return

    state = USER_STATE[user_id]
    url = state["url"]
    status_msg_id = state["msg_id"]

    # Edit to confirm
    try:
        status_msg = await app.get_messages(query.message.chat.id, status_msg_id)
        await status_msg.edit_text(f"Downloading with **{CODECS[codec]}**...\n\n`{url}`")
    except:
        status_msg = await query.message.reply(f"Downloading with **{CODECS[codec]}**...")

    # Cleanup state
    USER_STATE.pop(user_id, None)

    # Download
    user_dir = DOWNLOAD_BASE_DIR / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = await downloader.download(
            url=url,
            output_dir=str(user_dir),
            codec=codec,
            force_overwrite=False,
            metadata_language="en-US",
            progress_callback=lambda cur, total, name: asyncio.create_task(
                update_progress(status_msg, cur, total, name)
            ),
        )

        if not result or not any(Path(p).exists() for p in result):
            await status_msg.edit("Download failed. Try again.")
            return

        await status_msg.edit(f"Downloaded {len(result)} file(s). Sending...")

        for file_path in result:
            path = Path(file_path)
            if not path.exists():
                continue

            if path.stat().st_size > MAX_FILE_SIZE:
                await status_msg.edit(f"{path.name} too large.")
                continue

            await query.message.reply_audio(
                audio=str(path),
                caption=path.name,
                title=path.stem,
            )
            path.unlink(missing_ok=True)

        await status_msg.delete()

    except Exception as e:
        logger.error(f"Error: {e}")
        await status_msg.edit(f"Error: {str(e)}")


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
async def main():
    global wrapper, downloader
    wrapper = await WrapperManager().init(url="wm.wol.moe:443", secure=True)
    downloader = AppleMusicDownloader(wrapper)
    logger.info("Bot starting...")
    await app.start()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
