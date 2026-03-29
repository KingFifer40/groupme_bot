from flask import Flask, request
import requests
import re
import threading
import time
import os
import json

app = Flask(__name__)

BOT_ID = "7b600877b6a2c5914f5408"
GROUPME_POST_URL = "https://api.groupme.com/v3/bots/post"

# -------------------------
# Keyword Lists
# -------------------------

SLURS = ["slur1", "slur2", "slur3"]
HARASSMENT = ["kill yourself", "kys", "stfu", "shut up", "loser"]

NSFW = ["porn", "nude", "sex", "onlyfans", "nsfw"]

RELIGION = ["jesus", "christian", "muslim", "islam", "bible", "church"]
POLITICS = ["trump", "biden", "democrat", "republican", "election", "senate"]

URL_REGEX = r"(https?://\S+|www\.\S+)"

# -------------------------
# Helper Functions
# -------------------------

def send_message(text):
    print(f"[BOT] Sending message: {text}")
    r = requests.post(GROUPME_POST_URL, json={"bot_id": BOT_ID, "text": text})
    print(f"[BOT] Status: {r.status_code}")
    return r

def contains_any(text, keywords):
    text_lower = text.lower()
    return any(word in text_lower for word in keywords)

def is_external_link(text):
    urls = re.findall(URL_REGEX, text)
    for url in urls:
        if "i.groupme.com" in url:
            print(f"[LINK] Allowed GroupMe media URL: {url}")
            continue
        print(f"[LINK] Blocked external URL: {url}")
        return True
    return False

def violates_rules(message):
    text = message.lower()

    if contains_any(text, SLURS) or contains_any(text, HARASSMENT):
        print("[RULE] Rule 1 violation detected")
        return "⚠️ Rule 1: Please keep things respectful."

    if contains_any(text, NSFW):
        print("[RULE] Rule 2 violation detected")
        return "⚠️ Rule 2: Keep it PG — no NSFW content."

    if is_external_link(text):
        print("[RULE] Rule 3 violation detected")
        return "⚠️ Rule 3: No external links or group invites."

    if contains_any(text, RELIGION) or contains_any(text, POLITICS):
        print("[RULE] Rule 6 violation detected")
        return "⚠️ Rule 6: No religion or politics in the chat."

    print("[RULE] No violations")
    return None

# -------------------------
# Webhook Endpoint
# -------------------------

@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()

    print("\n===== NEW MESSAGE RECEIVED =====")
    print(json.dumps(data, indent=2))

    text = data.get("text", "")
    sender_type = data.get("sender_type")

    # Ignore bot messages
    if sender_type == "bot":
        print("[INFO] Ignored bot message")
        return "OK", 200

    print(f"[MESSAGE] User said: {text}")

    # Test commands
    if text.lower() == "ping":
        send_message("pong!")
        return "OK", 200

    if text.lower() == "hello bot":
        send_message("Hello Jared 👋")
        return "OK", 200

    # Rule enforcement
    violation = violates_rules(text)
    if violation:
        send_message(violation)

    return "OK", 200

# -------------------------
# Keepalive Thread (Render Free Tier)
# -------------------------

RENDER_URL = os.getenv("RENDER_URL")

def keepalive():
    if not RENDER_URL:
        print("[KEEPALIVE] No RENDER_URL set, skipping keepalive")
        return
    while True:
        try:
            print("[KEEPALIVE] Pinging self...")
            requests.get(RENDER_URL)
        except Exception as e:
            print(f"[KEEPALIVE] Error: {e}")
        time.sleep(300)

threading.Thread(target=keepalive, daemon=True).start()

# -------------------------
# Run locally
# -------------------------

if __name__ == "__main__":
    print("[SYSTEM] Bot is running locally...")
    app.run(host="0.0.0.0", port=5000)
