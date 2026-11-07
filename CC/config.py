import os

# ==========================================
# MEMBACA API KEYS DARI ENVIRONMENT (GITHUB SECRETS)
# ==========================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")

INSTAGRAM_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
YT_CLIENT_SECRET_JSON = os.getenv("YT_CLIENT_SECRET_JSON", "")

# ==========================================
# GAYA KONTEN & PENGATURAN VIDEO (TERKUNCI)
# ==========================================
VOICE_NAME = "en-US-ChristopherNeural"  # Suara AI Pria Natural US
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)