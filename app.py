from flask import Flask, request
import requests
import re

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
    requests.post(GROUPME_POST_URL, json={"bot_id": BOT_ID, "text": text})

def contains_any(text, keywords):
    text_lower = text.lower()
    return any(word in text_lower for word in keywords)

def is_external_link(text):
    urls = re.findall(URL_REGEX, text)
    for url in urls:
        # Allow GroupMe-hosted media
        if "i.groupme.com" in url:
            continue
        # Block everything else
        return True
    return False

def violates_rules(message):
    text = message.lower()

    # Rule 1: Harassment / slurs / hate
    if contains_any(text, SLURS) or contains_any(text, HARASSMENT):
        return "⚠️ Rule 1: Please keep things respectful."

    # Rule 2: NSFW
    if contains_any(text, NSFW):
        return "⚠️ Rule 2: Keep it PG — no NSFW content."

    # Rule 3: External links (non-GroupMe)
    if is_external_link(text):
        return "⚠️ Rule 3: No external links or group invites."

    # Rule 6: No religion or politics
    if contains_any(text, RELIGION) or contains_any(text, POLITICS):
        return "⚠️ Rule 6: No religion or politics in the chat."

    return None

# -------------------------
# Webhook Endpoint
# -------------------------

@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()

    # Ignore bot messages
    if data.get("sender_type") == "bot":
        return "OK", 200

    text = data.get("text", "")

    violation = violates_rules(text)
    if violation:
        send_message(violation)

    return "OK", 200

# -------------------------
# Run locally
# -------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
