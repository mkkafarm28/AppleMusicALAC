# bot.py
import asyncio
import os
import logging
import sys
from pathlib import Path
from pyrogram import Client, filters, idle
from pyrogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
)
from src.grpc.manager import WrapperManager
from src.core.downloader import AppleMusicDownloader
from src.utils import GlobalLogger

# ════════════════════════════════════════════════════════
# Config
# ════════════════════════════════════════════════════════
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DOWNLOAD_BASE_DIR = Path("downloads")
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024

logger = GlobalLogger().logger

wrapper: WrapperManager = None
downloader: AppleMusicDownloader = None
app = None

CODECS = {
    "alac": "ALAC (Lossless)",
    "aac": "AAC (256 kbps)",
    "aac-binaural": "AAC Binaural",
    "aac-downmix": "AAC Downmix",
    "aac-legacy": "AAC Legacy",
    "ec3": "EC3 (Dolby)",
    "ac3": "AC3",
}

USER_STATE = {}


# ════════════════════════════════════════════════════════
# Utility Functions
# ════════════════════════════════════════════════════════
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


# ════════════════════════════════════════════════════════
# Define Handlers (အဲဒီမှာ @app သုံးမယ်)
# ════════════════════════════════════════════════════════
def setup_handlers(app_instance):
    """Setup all bot handlers"""
    
    @app_instance.on_message(filters.regex(r'^/start'))
    async def start(client: Client, message: Message):
        logger.info(f"📌 /start command received from user {message.from_user.id}")
        try:
            await message.reply(
                "**Apple Music Downloader**\n\n"
                "Send a **song / album / artist / playlist** URL.\n"
                "Then choose codec.\n\n"
                "Example:\n"
                "https://music.apple.com/us/album/never-gonna-give-you-up/1441164362",
                disable_web_page_preview=True
            )
            logger.info("✓ /start response sent")
        except Exception as e:
            logger.error(f"❌ Error replying to start: {e}")

    @app_instance.on_message(filters.text)
    async def handle_url(client: Client, message: Message):
        if message.text.startswith('/'):
            return
        
        url = message.text.strip()
        user_id = message.from_user.id
        logger.info(f"🔗 URL received from {user_id}: {url}")

        try:
            buttons = [[InlineKeyboardButton(text=v, callback_data=f"codec_{k}_{message.id}")] for k, v in CODECS.items()]
            keyboard = InlineKeyboardMarkup(buttons)

            status_msg = await message.reply(
                f"**URL Received!**\n\nChoose codec for:\n`{url}`",
                reply_markup=keyboard,
                parse_mode="markdown",
                disable_web_page_preview=True
            )
            
            USER_STATE[user_id] = {"url": url, "msg_id": status_msg.id}
            logger.info(f"✓ Codec selection menu sent to {user_id}")
        except Exception as e:
            logger.error(f"❌ Error in handle_url: {e}")

    @app_instance.on_callback_query(filters.regex(r"^codec_(.+)_(\d+)$"))
    async def handle_codec(client: Client, query: CallbackQuery):
        status_msg = None
        try:
            parts = query.data.split("_")
            codec = parts[1]
            user_id = query.from_user.id
            
            logger.info(f"🎵 Codec selected: {codec} by user {user_id}")

            if user_id not in USER_STATE:
                await query.answer("Session expired.", show_alert=True)
                logger.warning(f"⚠️ Session expired for user {user_id}")
                return

            state = USER_STATE[user_id]
            url = state["url"]
            status_msg_id = state["msg_id"]

            try:
                status_msg = await app_instance.get_messages(query.message.chat.id, status_msg_id)
                await status_msg.edit_text(f"Downloading with **{CODECS[codec]}**...\n\n`{url}`")
            except:
                status_msg = await query.message.reply(f"Downloading with **{CODECS[codec]}**...")

            USER_STATE.pop(user_id, None)

            user_dir = DOWNLOAD_BASE_DIR / str(user_id)
            user_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"📥 Starting download for {user_id}")

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
                logger.error(f"❌ Download failed for {user_id}")
                return

            await status_msg.edit(f"Downloaded {len(result)} file(s). Sending...")
            logger.info(f"✓ {len(result)} file(s) downloaded, uploading to Telegram...")

            for file_path in result:
                path = Path(file_path)
                if not path.exists():
                    continue

                if path.stat().st_size > MAX_FILE_SIZE:
                    await status_msg.edit(f"{path.name} too large.")
                    logger.warning(f"⚠️ File too large: {path.name}")
                    continue

                await query.message.reply_audio(
                    audio=str(path),
                    caption=path.name,
                    title=path.stem,
                )
                path.unlink(missing_ok=True)
                logger.info(f"✓ File sent: {path.name}")

            await status_msg.delete()
            logger.info(f"✓ Download completed for user {user_id}")

        except Exception as e:
            logger.error(f"❌ Error in handle_codec: {e}", exc_info=True)
            if status_msg:
                try:
                    await status_msg.edit(f"Error: {str(e)}")
                except:
                    pass


# ════════════════════════════════════════════════════════
# Main Function
# ════════════════════════════════════════════════════════
async def main():
    global wrapper, downloader, app
    
    # Validate credentials
    logger.info("🔐 Validating credentials...")
    if not API_ID or not API_HASH or not BOT_TOKEN:
        logger.error("❌ Missing API_ID, API_HASH, or BOT_TOKEN")
        sys.exit(1)
    logger.info(f"✓ API_ID: {API_ID}")
    logger.info(f"✓ API_HASH: {API_HASH[:10]}...")
    logger.info(f"✓ BOT_TOKEN: {BOT_TOKEN[:20]}...")
    
    # Initialize Pyrogram Client
    logger.info("📱 Initializing Pyrogram Client...")
    try:
        app = Client(
            "applemusic_bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
        )
        logger.info("✓ Pyrogram Client initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Pyrogram Client: {e}")
        sys.exit(1)
    
    # Setup handlers AFTER app is initialized
    logger.info("📌 Setting up message handlers...")
    setup_handlers(app)
    logger.info("✓ Message handlers registered")
    
    # Initialize WrapperManager
    logger.info("🌐 Initializing WrapperManager...")
    try:
        wrapper = WrapperManager()
        await wrapper.init(url="wm.wol.moe:443", secure=True)
        logger.info("✓ WrapperManager initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize WrapperManager: {e}")
        sys.exit(1)
    
    # Initialize AppleMusicDownloader
    logger.info("🎵 Initializing AppleMusicDownloader...")
    try:
        downloader = AppleMusicDownloader(wrapper)
        logger.info("✓ AppleMusicDownloader initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize AppleMusicDownloader: {e}")
        sys.exit(1)
    
    # Start Bot
    logger.info("🤖 Starting Bot...")
    try:
        await app.start()
        logger.info("✓✓✓ BOT STARTED SUCCESSFULLY ✓✓✓")
        logger.info(f"📲 Bot is now listening for messages...")
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"❌ Failed to start bot: {e}")
        sys.exit(1)
    
    # Idle
    logger.info("⏳ Bot is now idle and waiting for messages...")
    try:
        await idle()
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
    finally:
        logger.info("Stopping bot...")
        await app.stop()
        logger.info("✓ Bot stopped")


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("🚀 APPLE MUSIC BOT STARTING")
    logger.info("=" * 60)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}", exc_info=True)
        sys.exit(1)
