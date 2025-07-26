import os
import json
import random
from tts_voice import speak



# ==========================================
# 📄 Load Reddit JSON File
# ==========================================
def load_reddit_json(filename):
    with open(filename, "r") as f:
        return json.load(f)


# ==========================================
# 🔀 Assign Voices to Users
# ==========================================
def assign_voices(users, voices):
    random.shuffle(voices)
    mapping = {}
    for i, user in enumerate(users):
        mapping[user] = voices[i % len(voices)]
    return mapping

# ==========================================
# 🧠 Main Logic
# ==========================================
def read_comments(filename):
    data = load_reddit_json(filename)

    comments = []
    users = set()
    for entry in data:
        user = entry.get("user_posted", "UnknownUser")
        text = entry.get("comment", "")
        if text:
            comments.append((user, text))
            users.add(user)

        replies = entry.get("replies") or []
        for reply in replies:
            ruser = reply.get("user_replying", "UnknownReply")
            rtext = reply.get("reply", "")
            if rtext:
                comments.append((ruser, rtext))
                users.add(ruser)

    voices = speak.fetch_available_voices()
    user_voice_map = assign_voices(users, voices)

    for idx, (user, text) in enumerate(comments):
        voice_id = user_voice_map.get(user, random.choice(voices))
        print(f"\n🗣️ {user} ({voice_id}): {text}")
        try:
            speak.speak_with_inworld(text, voice_id)
        except Exception as e:
            print(f"❌ Failed to speak for {user}: {e}")

# ==========================================
# 🚀 Run
# ==========================================
if __name__ == "__main__":
    input_file = "readers/reddit_comments.json"

    if not os.path.exists(input_file):
        print(f"❌ File not found: {input_file}")
    else:
        read_comments(input_file)
