import os
import shutil
from CC.trend_finder import get_trending_topic
from CC.script_generator import generate_script_and_metadata
from CC.audio_generator import generate_audio
from CC.visual_fetcher import fetch_background_video
from CC.video_compiler import compile_video
from CC.telegram_notifier import send_telegram_notification

def cleanup_previous_production():
    """
    Sesuai strategi: Menghapus folder temp & output lama tepat SEBELUM produksi baru dimulai.
    """
    dirs_to_clean = ["assets_temp", "output"]
    for d in dirs_to_clean:
        if os.path.exists(d):
            shutil.rmtree(d)
            print(f"[Orchestrator] Membersihkan direktori lama: {d}")
        os.makedirs(d, exist_ok=True)

def main():
    print("==================================================")
    print("      MEMULAI PRODUKSI PABRIK KONTEN REELS       ")
    print("==================================================")

    # Step 0: Pembersihan produksi sebelumnya
    cleanup_previous_production()

    # Path standar
    temp_dir = "assets_temp"
    output_dir = "output"
    
    audio_path = os.path.join(temp_dir, "voice.mp3")
    bg_video_path = os.path.join(temp_dir, "background.mp4")
    bgm_path = os.path.join("assets", "bgm.mp3")
    final_video_path = os.path.join(output_dir, "final_reels.mp4")

    # Step 1: Riset Tren USA
    topic = get_trending_topic()

    # Step 2: Generate Skrip & Metadata via Gemini API
    script_data = generate_script_and_metadata(topic)
    script_text = script_data.get("script_text", "")
    pixabay_query = script_data.get("pixabay_search_query", "cinematic nature")
    metadata = script_data.get("metadata", {})

    # Step 3: Generate Audio (Edge-TTS en-US)
    generate_audio(script_text, audio_path)

    # Step 4: Fetch Visual Video (Pixabay API)
    fetch_background_video(pixabay_query, bg_video_path)

    # Step 5: Render Video Final (FFmpeg / MoviePy)
    compile_video(bg_video_path, audio_path, bgm_path, script_text, final_video_path)

    # Step 6: Kirim Notifikasi & Video ke Telegram (Opsi A)
    send_telegram_notification(final_video_path, metadata)

    print("==================================================")
    print("     PRODUKSI SELESAI & VIDEO SIAP DIUNGGAH       ")
    print("==================================================")

if __name__ == "__main__":
    main()
