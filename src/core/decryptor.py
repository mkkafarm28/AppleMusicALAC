# src/core/decryptor.py
import os
import asyncio
from pathlib import Path
from typing import Dict, Optional, Callable
from src.grpc.manager import WrapperManager
from src.core.segment_downloader import download_segments, fetch_segment
from src.core.metadata_embedder import embed
from src.utils import GlobalLogger

ProgressCallback = Callable[[int, int, str], None]


async def decrypt_and_save(
    wrapper: WrapperManager,
    item: Dict,
    output_dir: str,
    force_overwrite: bool = False,
    metadata_language: str = "en-US",
    progress_callback: Optional[ProgressCallback] = None,
) -> Optional[str]:
    logger = GlobalLogger().logger
    adam_id = item.get("trackId") or item.get("id")
    if not adam_id:
        return None

    try:
        m3u8_url = await wrapper.m3u8(str(adam_id))
    except Exception as e:
        logger.error(f"m3u8 failed for {adam_id}: {e}")
        return None

    try:
        key, segments, total_bytes = await download_segments(m3u8_url, adam_id)
    except Exception as e:
        logger.error(f"segments failed for {adam_id}: {e}")
        return None

    title = item.get("trackName", "Unknown")
    artist = item.get("artistName", "Unknown")
    safe_name = f"{artist} - {title}".replace("/", "_").replace(":", "").replace("*", "")
    ext = ".m4a" if item.get("codec") in ["alac", "aac", "aac-legacy", "aac-binaural", "aac-downmix"] else ".m4a"  # assume m4a
    out_path = Path(output_dir) / f"{safe_name}{ext}"

    if out_path.exists() and not force_overwrite:
        logger.info(f"Skipping {out_path}")
        return str(out_path)

    written = 0
    CHUNK_SIZE = 64 * 1024

    try:
        with open(out_path, "wb") as f:
            for i, seg_url in enumerate(segments):
                seg_data = await fetch_segment(seg_url)
                decrypted = await wrapper.decrypt(
                    adam_id=str(adam_id),
                    key=key.hex() if key else "",
                    sample=seg_data,
                    sample_index=i,
                )
                f.write(decrypted)
                written += len(decrypted)

                if progress_callback and total_bytes:
                    progress_callback(written, total_bytes, out_path.name)

        await embed(str(out_path), item, metadata_language, wrapper)

        logger.info(f"Saved {out_path}")
        return str(out_path)

    except Exception as e:
        logger.error(f"decrypt failed for {adam_id}: {e}")
        if out_path.exists():
            out_path.unlink()
        return None
