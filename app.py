import os
import requests
from flask import Flask, request

app = Flask(__name__)

# BOT_ID must be set in Render → Environment Variables
BOT_ID = os.getenv("BOT_ID")


def send_message(text: str):
    """Send a message back to GroupMe using the bot ID."""
    if not BOT_ID:
        print("ERROR: BOT_ID is not set in environment variables!")
        return

    payload = {
        "bot_id": BOT_ID,
        "text": text
    }

    try:
        r = requests.post("https://api.groupme.com/v3/bots/post", json=payload)
        print("Send message response:", r.status_code, r.text)
    except Exception as e:
        print("Error sending message:", e)


@app.route("/", methods=["GET"])
def home():
    """GET route so you can verify the bot is alive in a browser."""
    return "Bot is running!", 200


@app.route("/", methods=["POST"])
def webhook():
    """Main webhook for GroupMe/Mebots."""
    data = request.get_json()
    print("Incoming POST:", data)

    if not data:
        return "no data", 200

    text = (data.get("text") or "").strip()
    sender_type = data.get("sender_type")

    # Ignore messages from bots (including itself)
    if sender_type == "bot":
        return "ok", 200

    # Test command
    if text.lower() == "!test":
        send_message("bot is working!")

    return "ok", 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
