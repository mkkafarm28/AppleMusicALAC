# bot.py name=bot.py url=https://github.com/mkkafarm28/AppleMusicALAC/blob/v2/bot.py
import asyncio
import os
import sys
from pathlib import Path
from pyrogram import Client, filters, idle, enums
from pyrogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
)
import logging
import subprocess

# ════════════════════════════════════════════════════════
# Setup Logging
# ════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════
# Config from Environment
# ════════════════════════════════════════════════════════
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DOWNLOAD_BASE_DIR = Path("downloads")
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024

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
# Download Function
# ════════════════════════════════════════════════════════
async def download_music(url: str, output_dir: str, codec: str) -> list:
    """
    Download music using subprocess with proper config handling
    """
    logger.info(f"🎵 Download started: {url} [{codec}]")
    
    try:
        # Create download script
        script = f"""
import sys
sys.path.insert(0, '/app')

# Register all creart creators
from creart import add_creator, it

from src.measurer import MeasurerCreator
add_creator(MeasurerCreator)

from src.logger import LoggerCreator
add_creator(LoggerCreator)

from src.config import ConfigCreator, Config
add_creator(ConfigCreator)

from src.api import APICreator
add_creator(APICreator)

from src.grpc.manager import WMCreator, WrapperManager
add_creator(WMCreator)

import asyncio

async def download():
    logger = it(LoggerCreator).logger
    config = it(Config)
    
    try:
        logger.info(f"Wrapper Manager Init: url={{config.instance.url}}, secure={{config.instance.secure}}")
        
        # Initialize WrapperManager with config
        await it(WrapperManager).init(config.instance.url, config.instance.secure)
        logger.info("✓ WrapperManager initialized")
        
        from src.cmd import AppleMusicURL, URLType
        from src.rip import rip_song, rip_album, rip_artist, rip_playlist
        from src.utils import GlobalLogger
        
        logger = GlobalLogger().logger
        
        raw_url = '{url}'
        codec = '{codec}'
        
        logger.info(f"Download: {{raw_url}} [{{codec}}]")
        
        # Parse URL
        url_obj = AppleMusicURL.parse_url(raw_url)
        if not url_obj:
            logger.error("URL parse failed")
            return
        
        logger.info(f"Parsed: type={{url_obj.type}}, id={{url_obj.id}}, storefront={{url_obj.storefront}}")
        
        # Download based on type
        if url_obj.type == URLType.Song:
            logger.info("Downloading song...")
            await rip_song(url_obj, codec)
        elif url_obj.type == URLType.Album:
            logger.info("Downloading album...")
            await rip_album(url_obj, codec)
        elif url_obj.type == URLType.Artist:
            logger.info("Downloading artist...")
            await rip_artist(url_obj, codec)
        elif url_obj.type == URLType.Playlist:
            logger.info("Downloading playlist...")
            await rip_playlist(url_obj, codec)
        
        logger.info("✓ Download completed")
        
    except Exception as e:
        logger.error(f"Download error: {{e}}", exc_info=True)
        raise

asyncio.run(download())
"""
        
        # Write script
        temp_script = Path("/tmp/download_runner.py")
        temp_script.write_text(script)
        
        logger.info(f"Running download script with 15min timeout...")
        
        # Execute in subprocess
        result = subprocess.run(
            [sys.executable, str(temp_script)],
            cwd="/app",
            timeout=900,  # 15 minutes
            capture_output=True,
            text=True
        )
        
        # Log output
        if result.stdout:
            logger.info(f"Download output:\n{result.stdout}")
        if result.stderr:
            logger.warning(f"Download stderr:\n{result.stderr}")
        
        if result.returncode != 0:
            logger.error(f"Download failed with code {result.returncode}")
        
        # Wait for file writing
        await asyncio.sleep(3)
        
        # Find audio files
        output_path = Path(output_dir)
        audio_files = []
        
        if output_path.exists():
            for ext in ['.m4a', '.mp3', '.flac', '.aac', '.alac', '.wav']:
                audio_files.extend(output_path.glob(f"*{ext}"))
        
        logger.info(f"✓ Found {len(audio_files)} audio file(s)")
        for f in audio_files:
            size_mb = f.stat().st_size / (1024**2)
            logger.info(f"  - {f.name} ({size_mb:.2f} MB)")
        
        return sorted(audio_files)
        
    except subprocess.TimeoutExpired:
        logger.error("❌ Download timeout (15 minutes)")
        return []
    except Exception as e:
        logger.error(f"❌ Download error: {e}", exc_info=True)
        return []


# ════════════════════════════════════════════════════════
# Bot Handlers
# ════════════════════════════════════════════════════════
def setup_handlers(app_instance):
    """Setup all bot handlers"""
    
    @app_instance.on_message(filters.command("start"))
    async def start(client: Client, message: Message):
        logger.info(f"📌 /start from user {message.from_user.id}")
        try:
            await message.reply(
                "<b>🎵 Apple Music Downloader</b>\n\n"
                "Send <b>Apple Music URL</b>\n"
                "Choose codec\n\n"
                "<code>https://music.apple.com/us/album/name/1234567890</code>",
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Error in /start: {e}")

    @app_instance.on_message(filters.text)
    async def handle_url(client: Client, message: Message):
        """Handle URL submission"""
        if message.text.startswith('/'):
            return
        
        url = message.text.strip()
        user_id = message.from_user.id
        logger.info(f"🔗 URL from {user_id}: {url}")

        try:
            # Validate URL
            if "music.apple.com" not in url:
                await message.reply(
                    "❌ Invalid Apple Music URL\n\n"
                    "Example: https://music.apple.com/us/album/name/1234567890",
                    parse_mode=enums.ParseMode.HTML
                )
                return

            # Create codec selection buttons
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
                f"<b>Select codec:</b>\n"
                f"<code>{url}</code>",
                reply_markup=keyboard,
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True
            )
            
            # Store user state
            USER_STATE[user_id] = {"url": url, "msg_id": status_msg.id}
            logger.info(f"✓ Codec menu sent to {user_id}")
            
        except Exception as e:
            logger.error(f"Error in handle_url: {e}")

    @app_instance.on_callback_query(filters.regex(r"^codec_(.+)_(\d+)$"))
    async def handle_codec(client: Client, query: CallbackQuery):
        """Handle codec selection and download"""
        status_msg = None
        try:
            parts = query.data.split("_")
            codec = parts[1]
            user_id = query.from_user.id
            
            logger.info(f"🎵 Codec selected: {codec} by {user_id}")

            # Validate session
            if user_id not in USER_STATE:
                await query.answer("❌ Session expired. Send URL again.", show_alert=True)
                logger.warning(f"Session expired for {user_id}")
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

            # Create download directory
            user_dir = DOWNLOAD_BASE_DIR / str(user_id)
            user_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"📥 Starting download for {user_id} with {codec}")

            # Download music
            audio_files = await download_music(url, str(user_dir), codec)

            if not audio_files:
                await status_msg.edit_text(
                    "❌ Download failed. No audio files generated.\n\n"
                    "Possible issues:\n"
                    "• Invalid URL\n"
                    "• Wrapper-manager connection issue\n"
                    "• Codec not available",
                    parse_mode=enums.ParseMode.HTML
                )
                logger.error(f"No files generated for {user_id}")
                return

            # Update status
            await status_msg.edit_text(
                f"<b>✅ Downloaded {len(audio_files)} file(s)</b>\n"
                f"<i>Uploading to Telegram...</i>",
                parse_mode=enums.ParseMode.HTML
            )

            # Upload files to Telegram
            uploaded_count = 0
            for file_path in audio_files:
                path = Path(file_path)
                if not path.exists():
                    logger.warning(f"File not found: {path}")
                    continue

                file_size = path.stat().st_size
                if file_size > MAX_FILE_SIZE:
                    logger.warning(f"File too large: {path.name} ({file_size/(1024**3):.2f} GB)")
                    continue

                try:
                    logger.info(f"📤 Uploading: {path.name} ({file_size/(1024**2):.2f} MB)")
                    await query.message.reply_audio(
                        audio=str(path),
                        caption=f"<code>{path.name}</code>",
                        title=path.stem,
                        parse_mode=enums.ParseMode.HTML,
                    )
                    uploaded_count += 1
                    logger.info(f"✓ Uploaded: {path.name}")
                except Exception as e:
                    logger.error(f"Upload failed for {path.name}: {e}")

            # Clean up and send final message
            try:
                await status_msg.delete()
            except:
                pass
            
            await query.message.reply(
                f"<b>✅ Upload Complete!</b>\n"
                f"<i>{uploaded_count} file(s) sent successfully</i>",
                parse_mode=enums.ParseMode.HTML
            )
            logger.info(f"✓ Download completed for {user_id}")

        except Exception as e:
            logger.error(f"Error in handle_codec: {e}", exc_info=True)
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
        logger.error(f"❌ Failed to initialize client: {e}")
        sys.exit(1)
    
    # Setup handlers
    logger.info("📌 Setting up message handlers...")
    try:
        setup_handlers(app)
        logger.info("✓ Message handlers registered")
    except Exception as e:
        logger.error(f"❌ Failed to setup handlers: {e}")
        sys.exit(1)
    
    # Start Bot
    logger.info("🤖 Starting Bot...")
    try:
        await app.start()
        logger.info("✓✓✓ BOT STARTED SUCCESSFULLY ✓✓✓")
        logger.info("📲 Bot is now listening for messages...")
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
    logger.info("🚀 APPLE MUSIC TELEGRAM BOT")
    logger.info("=" * 60)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)
