import os
import requests
import random

def fetch_background_video(query: str, output_path: str) -> str:
    """
    Mencari dan mengunduh video stok vertikal 9:16 dari Pixabay API.
    """
    api_key = os.getenv("PIXABAY_API_KEY")
    if not api_key:
        raise ValueError("PIXABAY_API_KEY tidak ditemukan di environment variable.")

    url = "https://pixabay.com/api/videos/"
    params = {
        "key": api_key,
        "q": query,
        "video_type": "film",
        "orientation": "vertical",
        "per_page": 10
    }

    print(f"[VisualFetcher] Mencari video Pixabay dengan kata kunci: '{query}'...")
    response = requests.get(url, params=params)
    data = response.json()

    hits = data.get("hits", [])
    
    if not hits:
        print(f"[VisualFetcher] Video untuk query '{query}' tidak ditemukan. Menggunakan fallback 'cinematic nature'...")
        params["q"] = "cinematic nature"
        response = requests.get(url, params=params)
        hits = response.json().get("hits", [])

    if not hits:
        raise Exception("[VisualFetcher] Gagal menemukan video dari Pixabay.")

    selected_video = random.choice(hits)
    video_files = selected_video.get("videos", {})
    download_url = video_files.get("medium", {}).get("url") or video_files.get("small", {}).get("url")

    print(f"[VisualFetcher] Mengunduh video dari Pixabay...")
    vid_data = requests.get(download_url).content
    with open(output_path, "wb") as f:
        f.write(vid_data)

    print(f"[VisualFetcher] Video berhasil diunduh ke: {output_path}")
    return output_path
