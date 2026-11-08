import os
import requests

def send_telegram_notification(video_path: str, metadata: dict) -> bool:
    """
    Mengirim file video .mp4 beserta metadata lengkap ke Telegram Bot (Opsi A).
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("[TelegramNotifier] TELEGRAM_BOT_TOKEN atau TELEGRAM_CHAT_ID tidak ditemukan. Notifikasi dilewati.")
        return False

    title = metadata.get("title", "")
    description = metadata.get("description", "")

    caption_text = (
        f"🎬 *PABRIK KONTEN REELS - PRODUKSI SELESAI*\n\n"
        f"📌 *Title:*\n`{title}`\n\n"
        f"📝 *Description & Hashtags:*\n`{description}`\n\n"
        f"📁 *File video .mp4 dilampirkan di bawah ini.*"
    )

    url = f"https://api.telegram.org/bot{bot_token}/sendVideo"

    print("[TelegramNotifier] Mengirim file video ke Telegram...")
    with open(video_path, "rb") as video_file:
        payload = {
            "chat_id": chat_id,
            "caption": caption_text,
            "parse_mode": "Markdown"
        }
        files = {
            "video": video_file
        }
        response = requests.post(url, data=payload, files=files)

    if response.status_code == 200:
        print("[TelegramNotifier] Berhasil mengunggah video ke Telegram!")
        return True
    else:
        print(f"[TelegramNotifier] Gagal mengunggah ke Telegram. Response: {response.text}")
        return False
