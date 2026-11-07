import requests
import time
import config

def publish_to_instagram(video_url, caption):
    """Publish video via Meta Graph API."""
    if not config.META_ACCESS_TOKEN or not config.INSTAGRAM_ACCOUNT_ID:
        print("[-] Meta credentials missing, skipping IG upload.")
        return
        
    print("[+] Initiating Instagram Reels upload...")
    # Step 1: Create Container
    url = f"[https://graph.facebook.com/v19.0/](https://graph.facebook.com/v19.0/){config.INSTAGRAM_ACCOUNT_ID}/media"
    payload = {
        'media_type': 'REELS',
        'video_url': video_url,
        'caption': caption,
        'access_token': config.META_ACCESS_TOKEN
    }
    res = requests.post(url, data=payload).json()
    container_id = res.get('id')
    
    if not container_id:
        print(f"[-] Failed to create container: {res}")
        return
        
    # Step 2: Wait for processing
    print("[+] Waiting for video processing on Meta servers...")
    time.sleep(30)
    
    # Step 3: Publish Container
    publish_url = f"[https://graph.facebook.com/v19.0/](https://graph.facebook.com/v19.0/){config.INSTAGRAM_ACCOUNT_ID}/media_publish"
    pub_payload = {
        'creation_id': container_id,
        'access_token': config.META_ACCESS_TOKEN
    }
    pub_res = requests.post(publish_url, data=pub_payload).json()
    print(f"[✓] Published to Instagram Reels! Media ID: {pub_res.get('id')}")