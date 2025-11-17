# bot.py
import asyncio
import os
import logging
import sys
from pathlib import Path
from pyrogram import Client, filters, idle, enums
from pyrogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
)
from creart import it

# ════════════════════════════════════════════════════════
# Import from main.py structure
# ════════════════════════════════════════════════════════
from src.logger import LoggerCreator, GlobalLogger
from src.config import ConfigCreator, Config
from src.api import APICreator
from src.grpc.manager import WMCreator, WrapperManager

# ════════════════════════════════════════════════════════
# Config
# ════════════════════════════════════════════════════════
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DOWNLOAD_BASE_DIR = Path("downloads")
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024

logger = GlobalLogger().logger

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
    """Update progress message"""
    if total == 0:
        return
    try:
        percent = cur / total
        bar = "█" * int(percent * 10) + "░" * (10 - int(percent * 10))
        text = f"<code>{name}</code>\n[{bar}] {percent:.1%}\n<code>{cur//1024} KB / {total//1024} KB</code>"
        await msg.edit_text(text, parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        logger.debug(f"Progress update error: {e}")


def get_audio_files(directory):
    """Find all audio files in directory"""
    audio_extensions = ['.m4a', '.mp3', '.flac', '.aac', '.alac', '.wav']
    files = []
    
    path = Path(directory)
    if not path.exists():
        logger.warning(f"Directory not found: {directory}")
        return files
    
    for ext in audio_extensions:
        files.extend(path.glob(f"*{ext}"))
    
    logger.info(f"Found {len(files)} audio file(s) in {directory}")
    for f in files:
        logger.info(f"  - {f.name} ({f.stat().st_size / (1024**2):.2f} MB)")
    
    return sorted(files)


# ════════════════════════════════════════════════════════
# Define Handlers
# ════════════════════════════════════════════════════════
def setup_handlers(app_instance):
    """Setup all bot handlers"""
    
    @app_instance.on_message(filters.command("start"))
    async def start(client: Client, message: Message):
        """Handle /start command"""
        logger.info(f"📌 /start command received from user {message.from_user.id}")
        try:
            await message.reply(
                "<b>🎵 Apple Music Downloader</b>\n\n"
                "Send a <b>song / album / artist / playlist</b> URL.\n"
                "Then choose codec.\n\n"
                "<b>Example:</b>\n"
                "<code>https://music.apple.com/us/album/never-gonna-give-you-up/1441164362</code>",
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True
            )
            logger.info("✓ /start response sent")
        except Exception as e:
            logger.error(f"❌ Error in /start handler: {e}", exc_info=True)

    @app_instance.on_message(filters.text)
    async def handle_url(client: Client, message: Message):
        """Handle URL messages"""
        # Skip if it's a command
        if message.text.startswith('/'):
            return
        
        url = message.text.strip()
        user_id = message.from_user.id
        logger.info(f"🔗 URL received from {user_id}: {url}")

        try:
            # Validate URL
            if "music.apple.com" not in url:
                await message.reply(
                    "❌ Invalid URL. Please send an Apple Music link.",
                    parse_mode=enums.ParseMode.HTML
                )
                return

            # Create codec buttons
            buttons = []
            for codec_key, codec_name in CODECS.items():
                buttons.append([
                    InlineKeyboardButton(
                        text=codec_name,
                        callback_data=f"codec_{codec_key}_{message.id}"
                    )
                ])
            keyboard = InlineKeyboardMarkup(buttons)

            status_msg = await message.reply(
                f"<b>✅ URL Received!</b>\n\n"
                f"<b>Choose codec for:</b>\n"
                f"<code>{url}</code>",
                reply_markup=keyboard,
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True
            )
            
            USER_STATE[user_id] = {"url": url, "msg_id": status_msg.id}
            logger.info(f"✓ Codec selection menu sent to {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Error in handle_url: {e}", exc_info=True)
            try:
                await message.reply(
                    f"❌ Error: {str(e)}",
                    parse_mode=enums.ParseMode.HTML
                )
            except:
                pass

    @app_instance.on_callback_query(filters.regex(r"^codec_(.+)_(\d+)$"))
    async def handle_codec(client: Client, query: CallbackQuery):
        """Handle codec selection - using the actual main.py architecture"""
        status_msg = None
        try:
            parts = query.data.split("_")
            codec = parts[1]
            user_id = query.from_user.id
            
            logger.info(f"🎵 Codec selected: {codec} by user {user_id}")

            # Check if session exists
            if user_id not in USER_STATE:
                await query.answer("❌ Session expired. Please send URL again.", show_alert=True)
                logger.warning(f"⚠️ Session expired for user {user_id}")
                return

            state = USER_STATE[user_id]
            url = state["url"]
            status_msg_id = state["msg_id"]

            # Update status message
            try:
                status_msg = await app_instance.get_messages(query.message.chat.id, status_msg_id)
                await status_msg.edit_text(
                    f"<b>⏳ Downloading with {CODECS[codec]}...</b>\n\n"
                    f"<code>{url}</code>",
                    parse_mode=enums.ParseMode.HTML
                )
            except:
                status_msg = await query.message.reply(
                    f"<b>⏳ Downloading with {CODECS[codec]}...</b>",
                    parse_mode=enums.ParseMode.HTML
                )

            USER_STATE.pop(user_id, None)

            # Create user directory
            user_dir = DOWNLOAD_BASE_DIR / str(user_id)
            user_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"📥 Starting download for {user_id} with codec: {codec}")
            logger.info(f"📁 Download directory: {user_dir.absolute()}")

            # ✅ Use the actual InteractiveShell's do_download logic
            try:
                # Get from creart
                from src.cmd import InteractiveShell
                shell = InteractiveShell(asyncio.get_event_loop())
                
                logger.info(f"⚙️ Calling do_download()...")
                await shell.do_download(
                    raw_url=url,
                    codec=codec,
                    force_download=False,
                    language="en-US",
                    include=False
                )
                
                # Wait a bit for files to be created
                await asyncio.sleep(2)
                logger.info(f"✓ do_download() completed")
                
            except Exception as e:
                logger.error(f"❌ Download error: {e}", exc_info=True)
                await status_msg.edit_text(
                    f"<b>❌ Download failed:</b>\n<code>{str(e)[:200]}</code>",
                    parse_mode=enums.ParseMode.HTML
                )
                return

            # Check directory for files
            logger.info(f"🔍 Checking directory for audio files...")
            audio_files = get_audio_files(str(user_dir))
            
            # Also check config download directory
            if not audio_files:
                logger.info(f"Checking config download directory...")
                config_download_dir = Path(it(Config).download.dirPathFormat.split('{')[0])
                if config_download_dir.exists():
                    logger.info(f"Scanning: {config_download_dir}")
                    audio_files = get_audio_files(str(config_download_dir))

            if not audio_files:
                logger.error(f"❌ No audio files found!")
                logger.info(f"📁 Directory contents:")
                if user_dir.exists():
                    for item in user_dir.iterdir():
                        logger.info(f"  - {item.name} (size: {item.stat().st_size / (1024**2):.2f} MB)")
                
                await status_msg.edit_text(
                    "❌ Download failed. No audio files generated.\n"
                    "This may be a wrapper-manager issue or invalid URL.",
                    parse_mode=enums.ParseMode.HTML
                )
                return

            await status_msg.edit_text(
                f"<b>✅ Downloaded {len(audio_files)} file(s)</b>\n"
                f"<i>Uploading to Telegram...</i>",
                parse_mode=enums.ParseMode.HTML
            )
            logger.info(f"✓ {len(audio_files)} file(s) ready for upload")

            # Upload files
            uploaded_count = 0
            for file_path in audio_files:
                path = Path(file_path)
                if not path.exists():
                    logger.warning(f"⚠️ File not found: {path}")
                    continue

                file_size = path.stat().st_size
                if file_size > MAX_FILE_SIZE:
                    logger.warning(f"⚠️ File too large: {path.name} ({file_size/(1024**3):.2f} GB)")
                    await status_msg.edit_text(
                        f"❌ {path.name} is too large ({file_size/(1024**3):.2f} GB)",
                        parse_mode=enums.ParseMode.HTML
                    )
                    continue

                try:
                    logger.info(f"📤 Uploading: {path.name} ({file_size / (1024**2):.2f} MB)")
                    await query.message.reply_audio(
                        audio=str(path),
                        caption=f"<code>{path.name}</code>",
                        title=path.stem,
                        parse_mode=enums.ParseMode.HTML,
                    )
                    uploaded_count += 1
                    logger.info(f"✓ File sent: {path.name}")
                except Exception as e:
                    logger.error(f"❌ Error uploading {path.name}: {e}", exc_info=True)
                    continue

            # Final message
            try:
                await status_msg.delete()
            except:
                pass
            
            await query.message.reply(
                f"<b>✅ Upload Complete!</b>\n"
                f"<i>{uploaded_count} file(s) sent successfully</i>",
                parse_mode=enums.ParseMode.HTML
            )
            logger.info(f"✓ All files completed for user {user_id}")

        except Exception as e:
            logger.error(f"❌ Error in handle_codec: {e}", exc_info=True)
            if status_msg:
                try:
                    await status_msg.edit_text(
                        f"<b>❌ Error:</b>\n<code>{str(e)[:100]}</code>",
                        parse_mode=enums.ParseMode.HTML
                    )
                except:
                    pass


# ════════════════════════════════════════════════════════
# Main Function
# ════════════════════════════════════════════════════════
async def main():
    global app
    
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
        logger.error(f"❌ Failed to initialize Pyrogram Client: {e}", exc_info=True)
        sys.exit(1)
    
    # Setup handlers AFTER app is initialized
    logger.info("📌 Setting up message handlers...")
    try:
        setup_handlers(app)
        logger.info("✓ Message handlers registered")
    except Exception as e:
        logger.error(f"❌ Failed to setup handlers: {e}", exc_info=True)
        sys.exit(1)
    
    # Start Bot
    logger.info("🤖 Starting Bot...")
    try:
        await app.start()
        logger.info("✓✓✓ BOT STARTED SUCCESSFULLY ✓✓✓")
        logger.info(f"📲 Bot is now listening for messages...")
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"❌ Failed to start bot: {e}", exc_info=True)
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
