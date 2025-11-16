# src/core/segment_downloader.py
import m3u8
import requests
from typing import Tuple, List

async def download_segments(m3u8_url: str, adam_id: str) -> Tuple[bytes, List[str], int]:
    m3u8_obj = m3u8.load(m3u8_url)
    segments = [seg.absolute_uri for seg in m3u8_obj.segments]

    key_uri = m3u8_obj.keys[0].absolute_uri if m3u8_obj.keys else None
    key = requests.get(key_uri).content if key_uri else b''

    # Approximate total bytes (duration * bitrate, but for progress, use a placeholder or calculate from headers
    total_bytes = 0
    for seg in segments:
        head = requests.head(seg)
        total_bytes += int(head.headers.get('Content-Length', 0))

    return key, segments, total_bytes

async def fetch_segment(seg_url: str) -> bytes:
    return requests.get(seg_url).content
