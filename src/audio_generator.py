import asyncio
import edge_tts

async def _generate_audio_async(text: str, output_path: str, voice: str = "en-US-ChristopherNeural"):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

def generate_audio(text: str, output_path: str, voice: str = "en-US-ChristopherNeural") -> str:
    """
    Mengubah teks menjadi audio MP3 menggunakan Edge-TTS.
    """
    print(f"[AudioGenerator] Menghasilkan voiceover dengan suara {voice}...")
    asyncio.run(_generate_audio_async(text, output_path, voice))
    print(f"[AudioGenerator] File audio tersimpan di: {output_path}")
    return output_path
