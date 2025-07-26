import requests
import io
import json
import base64
import wave
import os
from dotenv import load_dotenv

load_dotenv() 


API_KEY = os.getenv("INWORLD_API_TOKEN")
TTS_URL = "https://api.inworld.ai/tts/v1/voice:stream"
VOICE_LIST_URL = "https://api.inworld.ai/tts/v1/voices"


# ========================================
# 🎤 Fetch All Voices Once
# ========================================
def fetch_available_voices():
    headers = {
        "Authorization": f"Basic {API_KEY}",
    }
    res = requests.get(VOICE_LIST_URL, headers=headers)
    res.raise_for_status()

    data = res.json()
    print("🔍 Voice response example:")
    print(json.dumps(data, indent=2))

    # Adjust this after inspecting
    voices = [v["voiceId"] for v in data["voices"]]
    print(f"✅ Loaded {len(voices)} voices.")
    return voices


# ========================================
# 🗣️ Speak Tweet with Inworld
# ========================================
def speak_with_inworld(text, voice_id, sample_rate=48000):
    headers = {
        "Authorization": f"Basic {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "text": text,
        "voiceId": voice_id,
        "modelId": "inworld-tts-1",
        "audio_config": {
            "audio_encoding": "LINEAR16",
            "sample_rate_hertz": sample_rate,
        }
    }

    response = requests.post(TTS_URL, json=payload, headers=headers, stream=True)
    response.raise_for_status()

    raw_audio_data = io.BytesIO()
    for line in response.iter_lines():
        if line:
            chunk = json.loads(line)
            audio_chunk = base64.b64decode(chunk["result"]["audioContent"])
            if len(audio_chunk) > 44:
                raw_audio_data.write(audio_chunk[44:])  # Strip header

    with wave.open("output.wav", "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(raw_audio_data.getvalue())

    os.system("afplay output.wav")  # macOS; use `start` (Windows), `aplay` (Linux)
