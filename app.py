from flask import Flask, request
import requests
import re
import threading
import time
import os

app = Flask(__name__)

BOT_ID = "7b600877b6a2c5914f5408"
GROUPME_POST_URL = "https://api.groupme.com/v3/bots/post"

# -------------------------
# Keyword Lists
# -------------------------

SLURS = ["slur1", "slur2", "slur3"]  # add real ones privately
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
    response = requests.post(GROUPME_POST_URL, json={"bot_id": BOT_ID, "text": text})
    print(f"[BOT] Send status: {response.status_code}")
    return response

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
    print(f"[WEBHOOK] Received data: {data}")
    print(f"[DEBUG] Full webhook payload: {data}")

    if data.get("sender_type") == "bot":
        print("[WEBHOOK] Ignored bot message")
        return "OK", 200

    text = data.get("text", "")
    print(f"[MESSAGE] User said: {text}")

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
