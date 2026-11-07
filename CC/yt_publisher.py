import json
import os
import config
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

def publish_to_youtube(video_path, title, description):
    """Publish video to YouTube Shorts using Client Secrets."""
    if not config.YT_CLIENT_SECRET_JSON:
        print("[-] YouTube credentials missing, skipping YT upload.")
        return
        
    print("[+] Publishing to YouTube Shorts...")
    creds_data = json.loads(config.YT_CLIENT_SECRET_JSON)
    creds = Credentials.from_authorized_user_info(creds_data)
    
    youtube = build('youtube', 'v3', credentials=creds)
    
    body = {
        'snippet': {
            'title': f"{title[:90]} #Shorts",
            'description': description,
            'tags': ['Shorts', 'FunFacts', 'Trending'],
            'categoryId': '27' # Education / Knowledge
        },
        'status': {
            'privacyStatus': 'public',
            'selfDeclaredMadeForKids': False
        }
    }
    
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part='snippet,status', body=body, media_body=media)
    response = request.execute()
    print(f"[✓] Published to YouTube Shorts! Video ID: {response.get('id')}")