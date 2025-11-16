# src/core/metadata_embedder.py
import os
import subprocess
import requests
from typing import Dict
from src.grpc.manager import WrapperManager

async def embed(file_path: str, item: Dict, language: str, wrapper: WrapperManager = None) -> None:
    title = item.get('trackName', 'Unknown')
    artist = item.get('artistName', 'Unknown')
    album = item.get('collectionName', 'Unknown')
    track_number = item.get('trackNumber', '')
    disc_number = item.get('discNumber', '')
    genre = item.get('primaryGenreName', '')
    year = item.get('releaseDate', '')[:4]

    temp = file_path + '.temp.m4a'

    cmd = [
        'ffmpeg', '-i', file_path, '-c', 'copy',
        '-metadata', f'title={title}',
        '-metadata', f'artist={artist}',
        '-metadata', f'album={album}',
        '-metadata', f'genre={genre}',
        '-metadata', f'date={year}',
        '-metadata', f'track={track_number}',
        '-metadata', f'disk={disc_number}',
        temp
    ]
    subprocess.run(cmd, check=True)
    os.replace(temp, file_path)

    # Artwork
    artwork_url = item.get('artworkUrl100', '').replace('100x100', '1000x1000')
    if artwork_url:
        art_file = 'art.jpg'
        with open(art_file, 'wb') as f:
            f.write(requests.get(artwork_url).content)
        cmd = ['ffmpeg', '-i', file_path, '-i', art_file, '-map', '0', '-map', '1', '-c', 'copy', '-metadata:s:v', 'title=Album cover', '-metadata:s:v', 'comment=Cover (front)', temp]
        subprocess.run(cmd, check=True)
        os.replace(temp, file_path)
        os.remove(art_file)

    # Lyrics
    if wrapper:
        adam_id = item.get('trackId') or item.get('id')
        lyrics = await wrapper.lyrics(str(adam_id), language, item.get('country', 'us'))
        if lyrics:
            cmd = ['ffmpeg', '-i', file_path, '-c', 'copy', '-metadata', f'lyrics={lyrics}', temp]
            subprocess.run(cmd, check=True)
            os.replace(temp, file_path)
