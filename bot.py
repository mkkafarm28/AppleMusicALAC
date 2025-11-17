# bot.py name=bot.py
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
import time

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
# Download Function - Using main.py approach
# ════════════════════════════════════════════════════════
async def download_music(url: str, output_dir: str, codec: str) -> list:
    """
    Download music by calling main.py's command structure
    """
    logger.info(f"🎵 Download started: {url} [{codec}]")
    
    try:
        # Create a minimal wrapper script that mimics main.py
        script = f"""
import sys
import os
sys.path.insert(0, '/app')
os.chdir('/app')

# Initialize like main.py does
import asyncio
from creart import add_creator, it

loop = asyncio.new_event_loop()

# Import and add ALL creators
from src.logger import LoggerCreator
add_creator(LoggerCreator)

from src.config import ConfigCreator
add_creator(ConfigCreator)

from src.api import APICreator
add_creator(APICreator)

from src.grpc.manager import WMCreator
add_creator(WMCreator)

from src.measurer import MeasurerCreator
add_creator(MeasurerCreator)

# Now run the download command
from src.cmd import InteractiveShell

async def run_download():
    try:
        shell = InteractiveShell(loop)
        await shell.do_download(
            raw_url='{url}',
            codec='{codec}',
            force_download=False,
            language='en-US',
            include=False
        )
        # Wait for background tasks
        await asyncio.sleep(5)
    except Exception as e:
        print(f"ERROR: {{e}}", file=sys.stderr)
        import traceback
        traceback.print_exc()

try:
    loop.run_until_complete(run_download())
except Exception as e:
    print(f"FATAL: {{e}}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
"""
        
        # Write script
        temp_script = Path("/tmp/download_runner.py")
        temp_script.write_text(script)
        
        logger.info(f"Executing download script (15min timeout)...")
        
        # Execute in subprocess
        result = subprocess.run(
            [sys.executable, str(temp_script)],
            cwd="/app",
            timeout=900,  # 15 minutes
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"}
        )
        
        # Log output
        if result.stdout:
            logger.info(f"Download output:\n{result.stdout}")
        if result.stderr:
            logger.warning(f"Download errors:\n{result.stderr}")
        
        if result.returncode != 0:
            logger.error(f"Download script failed with code {result.returncode}")
        
        # Wait for file writing
        await asyncio.sleep(3)
        
        # Check multiple possible download locations
        audio_files = []
        
        # 1. Check user's personal directory
        output_path = Path(output_dir)
        if output_path.exists():
            for ext in ['.m4a', '.mp3', '.flac', '.aac', '.alac', '.wav']:
                audio_files.extend(output_path.glob(f"*{ext}"))
        
        # 2. Check config download directory
        if not audio_files:
            try:
                from creart import add_creator, it
                from src.config import ConfigCreator, Config
                add_creator(ConfigCreator)
                
                config_dir = Path(it(Config).download.dirPathFormat)
                logger.info(f"Checking config directory: {config_dir}")
                if config_dir.exists():
                    for ext in ['.m4a', '.mp3', '.flac', '.aac', '.alac', '.wav']:
                        found = list(config_dir.glob(f"**/*{ext}"))
                        if found:
                            audio_files.extend(found)
                            logger.info(f"Found {len(found)} files in {config_dir}")
            except Exception as e:
                logger.debug(f"Could not check config dir: {e}")
        
        # 3. Check downloads folder recursively
        if not audio_files:
            logger.info("Checking downloads folder recursively...")
            for ext in ['.m4a', '.mp3', '.flac', '.aac', '.alac', '.wav']:
                audio_files.extend(Path("downloads").glob(f"**/*{ext}"))
        
        logger.info(f"✓ Total audio files found: {len(audio_files)}")
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
        logger.info(f"📌 /start from {message.from_user.id}")
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
            if "music.apple.com" not in url:
                await message.reply(
                    "❌ Invalid Apple Music URL",
                    parse_mode=enums.ParseMode.HTML
                )
                return

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
            
            USER_STATE[user_id] = {"url": url, "msg_id": status_msg.id}
            logger.info(f"✓ Codec menu sent")
            
        except Exception as e:
            logger.error(f"Error: {e}")

    @app_instance.on_callback_query(filters.regex(r"^codec_(.+)_(\d+)$"))
    async def handle_codec(client: Client, query: CallbackQuery):
        """Handle codec selection"""
        status_msg = None
        try:
            parts = query.data.split("_")
            codec = parts[1]
            user_id = query.from_user.id
            
            logger.info(f"🎵 Codec: {codec}")

            if user_id not in USER_STATE:
                await query.answer("Session expired", show_alert=True)
                return

            state = USER_STATE[user_id]
            url = state["url"]
            status_msg_id = state["msg_id"]

            try:
                status_msg = await app_instance.get_messages(query.message.chat.id, status_msg_id)
                await status_msg.edit_text(
                    f"<b>⏳ Downloading {CODECS[codec]}...</b>\n<code>{url}</code>",
                    parse_mode=enums.ParseMode.HTML
                )
            except:
                status_msg = await query.message.reply(
                    f"<b>⏳ Downloading...</b>",
                    parse_mode=enums.ParseMode.HTML
                )

            USER_STATE.pop(user_id, None)

            user_dir = DOWNLOAD_BASE_DIR / str(user_id)
            user_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"📥 Download for {user_id}")

            # Download
            audio_files = await download_music(url, str(user_dir), codec)

            if not audio_files:
                await status_msg.edit_text(
                    "❌ No files generated",
                    parse_mode=enums.ParseMode.HTML
                )
                return

            await status_msg.edit_text(
                f"<b>✅ {len(audio_files)} file(s)</b>\n<i>Uploading...</i>",
                parse_mode=enums.ParseMode.HTML
            )

            # Upload
            uploaded_count = 0
            for file_path in audio_files:
                path = Path(file_path)
                if not path.exists():
                    continue

                file_size = path.stat().st_size
                if file_size > MAX_FILE_SIZE:
                    continue

                try:
                    logger.info(f"📤 Uploading: {path.name}")
                    await query.message.reply_audio(
                        audio=str(path),
                        caption=f"<code>{path.name}</code>",
                        title=path.stem,
                        parse_mode=enums.ParseMode.HTML,
                    )
                    uploaded_count += 1
                except Exception as e:
                    logger.error(f"Upload error: {e}")

            try:
                await status_msg.delete()
            except:
                pass
            
            await query.message.reply(
                f"<b>✅ Complete!</b>\n{uploaded_count} file(s) sent",
                parse_mode=enums.ParseMode.HTML
            )

        except Exception as e:
            logger.error(f"Error: {e}")
            if status_msg:
                try:
                    await status_msg.edit_text(f"❌ Error", parse_mode=enums.ParseMode.HTML)
                except:
                    pass


# ════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════
async def main():
    global app
    
    logger.info("🔐 Validating credentials...")
    if not API_ID or not API_HASH or not BOT_TOKEN:
        logger.error("❌ Missing credentials")
        sys.exit(1)
    
    logger.info("📱 Initializing client...")
    try:
        app = Client(
            "applemusic_bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
        )
    except Exception as e:
        logger.error(f"❌ Failed: {e}")
        sys.exit(1)
    
    logger.info("📌 Setting up handlers...")
    setup_handlers(app)
    
    logger.info("🤖 Starting bot...")
    try:
        await app.start()
        logger.info("✅ BOT STARTED")
    except Exception as e:
        logger.error(f"❌ Failed: {e}")
        sys.exit(1)
    
    logger.info("⏳ Ready for messages...")
    try:
        await idle()
    except KeyboardInterrupt:
        logger.info("Stopping...")
    finally:
        await app.stop()


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("🚀 APPLE MUSIC BOT")
    logger.info("=" * 60)
    
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        sys.exit(1)
