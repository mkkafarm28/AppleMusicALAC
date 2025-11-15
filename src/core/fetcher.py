# src/core/fetcher.py
import requests
from typing import Dict, List, Optional

async def fetch_items(info: Dict, codec: str, include_participate_songs: bool = False) -> List[Dict]:
    country = info['country']
    type_ = info['type']
    id_ = info['id']

    items = []

    if type_ == 'song':
        url = f"https://itunes.apple.com/lookup?id={id_}&entity=song&country={country}"
        resp = requests.get(url)
        if resp.status_code != 200:
            return []
        data = resp.json()['results']
        items = data if data else []

    elif type_ == 'album':
        url = f"https://itunes.apple.com/lookup?id={id_}&entity=song&country={country}&limit=200"
        resp = requests.get(url)
        if resp.status_code != 200:
            return []
        data = resp.json()['results']
        items = [item for item in data if item['wrapperType'] == 'track']

    elif type_ == 'artist':
        # Fetch albums
        url = f"https://itunes.apple.com/lookup?id={id_}&entity=album&country={country}&limit=200"
        resp = requests.get(url)
        if resp.status_code != 200:
            return []
        albums = [item for item in resp.json()['results'] if item['wrapperType'] == 'collection']
        for album in albums:
            album_id = album['collectionId']
            album_url = f"https://itunes.apple.com/lookup?id={album_id}&entity=song&country={country}&limit=200"
            album_resp = requests.get(album_url)
            if album_resp.status_code == 200:
                items += [item for item in album_resp.json()['results'] if item['wrapperType'] == 'track']

        if include_participate_songs:
            # Approximate search for featured songs
            artist_name = albums[0]['artistName'] if albums else ''
            search_url = f"https://search.itunes.apple.com/WebObjects/MZSearch.woa/wa/search?term={artist_name}&entity=song&country={country}&limit=200"
            search_resp = requests.get(search_url)
            if search_resp.status_code == 200:
                search_data = search_resp.json().get('results', [])
                items += [item for item in search_data if item['artistId'] != int(id_)]  # featured

    elif type_ == 'playlist':
        # Note: Playlists require Apple Music API token, approximate with search or assume album-like
        url = f"https://itunes.apple.com/lookup?id={id_}&entity=song&country={country}&limit=200"
        resp = requests.get(url)
        if resp.status_code != 200:
            return []
        data = resp.json()['results']
        items = [item for item in data if item['wrapperType'] == 'track']

    for item in items:
        item['codec'] = codec

    return items
