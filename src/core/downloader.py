# src/core/downloader.py
import os
from pathlib import Path
from typing import List, Optional, Callable
from src.core.parser import parse_url
from src.core.fetcher import fetch_items
from src.core.decryptor import decrypt_and_save
from src.utils import GlobalLogger

ProgressCallback = Callable[[int, int, str], None]  # cur, total, filename


class AppleMusicDownloader:
    def __init__(self, wrapper):
        self.wrapper = wrapper
        self.logger = GlobalLogger().logger

    async def download(
        self,
        url: str,
        output_dir: str,
        codec: str = "alac",
        force_overwrite: bool = False,
        metadata_language: str = "en-US",
        include_participate_songs: bool = False,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> List[str]:
        try:
            info = await parse_url(url)
            if not info:
                return []

            items = await fetch_items(info, codec, include_participate_songs)
            if not items:
                return []

            os.makedirs(output_dir, exist_ok=True)
            results = []

            for item in items:
                try:
                    file_path = await decrypt_and_save(
                        self.wrapper,
                        item,
                        output_dir,
                        force_overwrite,
                        metadata_language,
                        progress_callback,
                    )
                    if file_path and Path(file_path).exists():
                        results.append(file_path)
                except Exception as e:
                    self.logger.error(f"Item failed: {e}")

            return results
        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            return []
