# bot.py
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

# ════════════════════════════════════════════════════════
# Setup Basic Logging
# ════════════════════════════════════════════════════════
logging.basicConfig(level=logging.INFO)
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
# Download Logic - Direct Implementation
# ════════════════════════════════════════════════════════
async def download_music(url: str, output_dir: str, codec: str) -> list:
    """
    Download music using subprocess to call main.py's CLI
    """
    from subprocess import Popen, PIPE
    import json
    
    logger.info(f"Starting download: {url} with codec {codec}")
    
    try:
        # Create a temporary script that runs the download
        script = f"""
import asyncio
import os
import sys
sys.path.insert(0, '/app')

from creart import add_creator, it
loop = asyncio.new_event_loop()

from src.logger import LoggerCreator
add_creator(LoggerCreator)

from src.config import ConfigCreator, Config
add_creator(ConfigCreator)

from src.api import APICreator
add_creator(APICreator)

from src.grpc.manager import WMCreator, WrapperManager
add_creator(WMCreator)

from src.cmd import InteractiveShell

async def main():
    shell = InteractiveShell(loop)
    await shell.do_download(
        raw_url='{url}',
        codec='{codec}',
        force_download=False,
        language='en-US',
        include=False
    )
    # Wait for async tasks
    await asyncio.sleep(3)

loop.run_until_complete(main())
"""
        
        # Write script to temp file
        temp_script = Path("/tmp/download_runner.py")
        temp_script.write_text(script)
        
        # Execute it
        process = Popen(
            [sys.executable, str(temp_script)],
            stdout=PIPE,
            stderr=PIPE,
            cwd="/app"
        )
        
        stdout, stderr = process.communicate(timeout=300)
        
        if process.returncode != 0:
            logger.error(f"Download failed: {stderr.decode()}")
            return []
        
        logger.info(f"Download output: {stdout.decode()}")
        
        # Find files in output directory
        output_path = Path(output_dir)
        if not output_path.exists():
            logger.warning(f"Output directory not found: {output_dir}")
            return []
        
        audio_files = []
        for ext in ['.m4a', '.mp3', '.flac', '.aac', '.alac', '.wav']:
            audio_files.extend(output_path.glob(f"*{ext}"))
        
        logger.info(f"Found {len(audio_files)} files")
        return sorted(audio_files)
        
    except Exception as e:
        logger.error(f"Download error: {e}", exc_info=True)
        return []


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
        if message.text.startswith('/'):
            return
        
        url = message.text.strip()
        user_id = message.from_user.id
        logger.info(f"🔗 URL received from {user_id}: {url}")

        try:
            if "music.apple.com" not in url:
                await message.reply(
                    "❌ Invalid URL. Please send an Apple Music link.",
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
                await message.reply(f"❌ Error: {str(e)}", parse_mode=enums.ParseMode.HTML)
            except:
                pass

    @app_instance.on_callback_query(filters.regex(r"^codec_(.+)_(\d+)$"))
    async def handle_codec(client: Client, query: CallbackQuery):
        """Handle codec selection"""
        status_msg = None
        try:
            parts = query.data.split("_")
            codec = parts[1]
            user_id = query.from_user.id
            
            logger.info(f"🎵 Codec selected: {codec} by user {user_id}")

            if user_id not in USER_STATE:
                await query.answer("❌ Session expired. Please send URL again.", show_alert=True)
                return

            state = USER_STATE[user_id]
            url = state["url"]
            status_msg_id = state["msg_id"]

            try:
                status_msg = await app_instance.get_messages(query.message.chat.id, status_msg_id)
                await status_msg.edit_text(
                    f"<b>⏳ Downloading with {CODECS[codec]}...</b>\n\n<code>{url}</code>",
                    parse_mode=enums.ParseMode.HTML
                )
            except:
                status_msg = await query.message.reply(
                    f"<b>⏳ Downloading with {CODECS[codec]}...</b>",
                    parse_mode=enums.ParseMode.HTML
                )

            USER_STATE.pop(user_id, None)

            user_dir = DOWNLOAD_BASE_DIR / str(user_id)
            user_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"📥 Starting download for {user_id} with codec: {codec}")

            # ✅ Call download function
            audio_files = await download_music(url, str(user_dir), codec)

            if not audio_files:
                await status_msg.edit_text(
                    "❌ Download failed. No audio files generated.",
                    parse_mode=enums.ParseMode.HTML
                )
                logger.error(f"❌ No files generated")
                return

            await status_msg.edit_text(
                f"<b>✅ Downloaded {len(audio_files)} file(s)</b>\n<i>Uploading to Telegram...</i>",
                parse_mode=enums.ParseMode.HTML
            )

            uploaded_count = 0
            for file_path in audio_files:
                path = Path(file_path)
                if not path.exists():
                    continue

                file_size = path.stat().st_size
                if file_size > MAX_FILE_SIZE:
                    await status_msg.edit_text(
                        f"❌ {path.name} is too large",
                        parse_mode=enums.ParseMode.HTML
                    )
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
                    logger.info(f"✓ File sent: {path.name}")
                except Exception as e:
                    logger.error(f"❌ Upload error: {e}")
                    continue

            try:
                await status_msg.delete()
            except:
                pass
            
            await query.message.reply(
                f"<b>✅ Upload Complete!</b>\n<i>{uploaded_count} file(s) sent</i>",
                parse_mode=enums.ParseMode.HTML
            )
            logger.info(f"✓ Completed for user {user_id}")

        except Exception as e:
            logger.error(f"❌ Error: {e}", exc_info=True)
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
    
    logger.info("🔐 Validating credentials...")
    if not API_ID or not API_HASH or not BOT_TOKEN:
        logger.error("❌ Missing credentials")
        sys.exit(1)
    
    logger.info("📱 Initializing Pyrogram Client...")
    try:
        app = Client(
            "applemusic_bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
        )
        logger.info("✓ Client initialized")
    except Exception as e:
        logger.error(f"❌ Client init failed: {e}")
        sys.exit(1)
    
    logger.info("📌 Setting up handlers...")
    try:
        setup_handlers(app)
        logger.info("✓ Handlers registered")
    except Exception as e:
        logger.error(f"❌ Handler setup failed: {e}")
        sys.exit(1)
    
    logger.info("🤖 Starting Bot...")
    try:
        await app.start()
        logger.info("✓✓✓ BOT STARTED ✓✓✓")
    except Exception as e:
        logger.error(f"❌ Bot start failed: {e}")
        sys.exit(1)
    
    logger.info("⏳ Bot ready for messages...")
    try:
        await idle()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await app.stop()


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("🚀 APPLE MUSIC BOT STARTING")
    logger.info("=" * 60)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted")
    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
        sys.exit(1)
