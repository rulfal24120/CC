import asyncio
import edge_tts
import config

async def generate_voiceover_async(text, output_file):
    communicate = edge_tts.Communicate(text, config.VOICE_NAME)
    await communicate.save(output_file)

def generate_voiceover(text, output_file="output/voiceover.mp3"):
    asyncio.run(generate_voiceover_async(text, output_file))
    return output_file