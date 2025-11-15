# src/core/parser.py
import re

async def parse_url(url: str) -> Optional[Dict]:
    # Example: https://music.apple.com/us/album/album-name/1234567890
    # or https://music.apple.com/us/song/song-name/1234567890
    # or https://music.apple.com/us/artist/artist-name/1234567890
    # or https://music.apple.com/us/playlist/playlist-name/pl.u-1234567890

    match = re.match(r'https://music.apple.com/(\w+?)/(\w+?)/.*?/([a-z0-9.-]+?)(?:/i/(\d+))?$', url)
    if not match:
        return None

    country, type_, id_ = match.group(1,2,3)
    song_id = match.group(4)

    if type_ == 'song':
        id_ = song_id or id_

    return {'country': country, 'type': type_, 'id': id_}
