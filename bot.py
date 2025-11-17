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

# ════════════════════════════════════════════════════════
# Setup Logging
# ════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════
# Config
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
# Download Function - Direct CLI approach
# ════════════════════════════════════════════════════════
async def download_music(url: str, output_dir: str, codec: str) -> list:
    """
    Download music using direct Python script with simple async
    """
    logger.info(f"🎵 Download started: {url} [{codec}]")
    
    try:
        # Create simple download script without loop conflict
        script = f"""
import sys
sys.path.insert(0, '/app')

import asyncio
from pathlib import Path

async def main():
    # Import with proper initialization
    from creart import add_creator, it
    
    # Add creators sequentially
    from src.logger import LoggerCreator
    add_creator(LoggerCreator)
    
    from src.config import ConfigCreator
    add_creator(ConfigCreator)
    
    from src.api import APICreator
    add_creator(APICreator)
    
    from src.grpc.manager import WMCreator
    add_creator(WMCreaker)
    
    from src.measurer import MeasurerCreator
    add_creator(MeasurerCreator)
    
    from src.utils import GlobalLogger
    logger = GlobalLogger().logger
    
    try:
        logger.info("Starting download process...")
        
        # Import command functions
        from src.cmd import AppleMusicURL, URLType, Flags
        from src.rip import rip_song, rip_album, rip_artist, rip_playlist
        
        # Parse URL
        url_obj = AppleMusicURL.parse_url('{url}')
        if not url_obj:
            logger.error("Failed to parse URL")
            return
        
        logger.info(f"URL Type: {{url_obj.type}}, ID: {{url_obj.id}}")
        
        # Create flags
        flags = Flags(language='en-US', force_save=False)
        
        # Download based on type
        if url_obj.type == URLType.Song:
            logger.info("Downloading song...")
            await rip_song(url_obj, '{codec}', flags)
        elif url_obj.type == URLType.Album:
            logger.info("Downloading album...")
            await rip_album(url_obj, '{codec}', flags)
        elif url_obj.type == URLType.Artist:
            logger.info("Downloading artist...")
            await rip_artist(url_obj, '{codec}', flags)
        elif url_obj.type == URLType.Playlist:
            logger.info("Downloading playlist...")
            await rip_playlist(url_obj, '{codec}', flags)
        
        logger.info("✓ Download completed")
        await asyncio.sleep(2)
        
    except Exception as e:
        logger.error(f"Error: {{e}}", exc_info=True)
        raise

asyncio.run(main())
"""
        
        # Write script
        temp_script = Path("/tmp/download_runner.py")
        temp_script.write_text(script)
        
        logger.info("Running download script...")
        
        # Execute
        result = subprocess.run(
            [sys.executable, str(temp_script)],
            cwd="/app",
            timeout=900,
            capture_output=True,
            text=True
        )
        
        # Log output
        if result.stdout:
            logger.info(f"Output:\n{result.stdout}")
        if result.stderr:
            logger.warning(f"Stderr:\n{result.stderr}")
        
        if result.returncode != 0:
            logger.error(f"Download failed: code {result.returncode}")
        
        await asyncio.sleep(3)
        
        # Find files
        audio_files = []
        
        # Check config download path
        try:
            from creart import add_creator, it
            from src.config import ConfigCreator, Config
            add_creator(ConfigCreator)
            
            config_dir = Path(it(Config).download.dirPathFormat)
            logger.info(f"Checking: {config_dir}")
            
            if config_dir.exists():
                for ext in ['.m4a', '.mp3', '.flac', '.aac', '.alac', '.wav']:
                    found = list(config_dir.glob(f"**/*{ext}"))
                    if found:
                        audio_files.extend(found)
        except Exception as e:
            logger.debug(f"Config check error: {e}")
        
        # Check recursive
        if not audio_files:
            for ext in ['.m4a', '.mp3', '.flac', '.aac', '.alac', '.wav']:
                audio_files.extend(Path("downloads").glob(f"**/*{ext}"))
        
        logger.info(f"✓ Found {len(audio_files)} files")
        
        return sorted(audio_files)
        
    except subprocess.TimeoutExpired:
        logger.error("Timeout")
        return []
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return []


# ════════════════════════════════════════════════════════
# Bot Handlers
# ════════════════════════════════════════════════════════
def setup_handlers(app_instance):
    """Setup handlers"""
    
    @app_instance.on_message(filters.command("start"))
    async def start(client: Client, message: Message):
        logger.info(f"Start from {message.from_user.id}")
        try:
            await message.reply(
                "<b>🎵 Apple Music Downloader</b>\n\n"
                "Send URL, choose codec",
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True
            )
        except:
            pass

    @app_instance.on_message(filters.text)
    async def handle_url(client: Client, message: Message):
        if message.text.startswith('/'):
            return
        
        url = message.text.strip()
        user_id = message.from_user.id
        logger.info(f"URL: {url}")

        try:
            if "music.apple.com" not in url:
                await message.reply("❌ Invalid URL")
                return

            buttons = [[InlineKeyboardButton(text=v, callback_data=f"codec_{k}_{message.id}")] 
                       for k, v in CODECS.items()]
            
            status_msg = await message.reply(
                f"<b>URL Received</b>\n<code>{url}</code>",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True
            )
            
            USER_STATE[user_id] = {"url": url, "msg_id": status_msg.id}
        except:
            pass

    @app_instance.on_callback_query(filters.regex(r"^codec_(.+)_(\d+)$"))
    async def handle_codec(client: Client, query: CallbackQuery):
        status_msg = None
        try:
            parts = query.data.split("_")
            codec = parts[1]
            user_id = query.from_user.id
            
            if user_id not in USER_STATE:
                await query.answer("Session expired", show_alert=True)
                return

            state = USER_STATE[user_id]
            url = state["url"]

            try:
                status_msg = await app_instance.get_messages(query.message.chat.id, state["msg_id"])
                await status_msg.edit_text(f"<b>⏳ Downloading {CODECS[codec]}...</b>",
                                          parse_mode=enums.ParseMode.HTML)
            except:
                status_msg = await query.message.reply(f"<b>⏳ Downloading...</b>",
                                                      parse_mode=enums.ParseMode.HTML)

            USER_STATE.pop(user_id, None)
            user_dir = DOWNLOAD_BASE_DIR / str(user_id)
            user_dir.mkdir(parents=True, exist_ok=True)

            # Download
            audio_files = await download_music(url, str(user_dir), codec)

            if not audio_files:
                await status_msg.edit_text("❌ No files", parse_mode=enums.ParseMode.HTML)
                return

            await status_msg.edit_text(f"<b>✅ {len(audio_files)} file(s)</b>\n<i>Uploading...</i>",
                                      parse_mode=enums.ParseMode.HTML)

            # Upload
            uploaded = 0
            for path in audio_files:
                path = Path(path)
                if not path.exists() or path.stat().st_size > MAX_FILE_SIZE:
                    continue

                try:
                    logger.info(f"📤 {path.name}")
                    await query.message.reply_audio(
                        audio=str(path),
                        caption=f"<code>{path.name}</code>",
                        title=path.stem,
                        parse_mode=enums.ParseMode.HTML,
                    )
                    uploaded += 1
                except:
                    pass

            try:
                await status_msg.delete()
            except:
                pass
            
            await query.message.reply(f"<b>✅ {uploaded} file(s)</b>", parse_mode=enums.ParseMode.HTML)

        except Exception as e:
            logger.error(f"Error: {e}")
            if status_msg:
                try:
                    await status_msg.edit_text("❌ Error", parse_mode=enums.ParseMode.HTML)
                except:
                    pass


# ════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════
async def main():
    global app
    
    if not API_ID or not API_HASH or not BOT_TOKEN:
        logger.error("Missing credentials")
        sys.exit(1)
    
    try:
        app = Client("applemusic_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
    except Exception as e:
        logger.error(f"Client init failed: {e}")
        sys.exit(1)
    
    setup_handlers(app)
    
    try:
        await app.start()
        logger.info("✅ BOT STARTED")
    except Exception as e:
        logger.error(f"Start failed: {e}")
        sys.exit(1)
    
    logger.info("⏳ Waiting for messages...")
    try:
        await idle()
    except KeyboardInterrupt:
        pass
    finally:
        await app.stop()


if __name__ == "__main__":
    logger.info("🚀 APPLE MUSIC BOT")
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Error: {e}")စ
