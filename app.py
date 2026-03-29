import os
import requests
from flask import Flask, request

app = Flask(__name__)

# Your bot ID will be provided by Mebots or GroupMe
BOT_ID = os.getenv("BOT_ID")

def send_message(text):
    """Send a message back to GroupMe."""
    if not BOT_ID:
        print("BOT_ID not set!")
        return

    payload = {
        "bot_id": BOT_ID,
        "text": text
    }

    requests.post("https://api.groupme.com/v3/bots/post", json=payload)

@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()

    # Extract message text safely
    text = (data.get("text") or "").strip()

    # Ignore messages from bots (including itself)
    if data.get("sender_type") == "bot":
        return "ok", 200

    # Simple test command
    if text.lower() == "!test":
        send_message("bot is working!")

    return "ok", 200

if __name__ == "__main__":
    # Render uses PORT env variable
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
