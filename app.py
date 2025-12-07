import os
import time
import requests
from flask import Flask, request

app = Flask(__name__)

BOT_ID = os.environ.get("BOT_ID")
ADMINS = os.environ.get("ADMINS", "").split(",")  # comma-separated user IDs
join_message = "Welcome to the group!"
last_join_sent = 0

def send_message(text):
    requests.post("https://api.groupme.com/v3/bots/post", json={
        "bot_id": BOT_ID,
        "text": text
    })

@app.route("/", methods=["POST"])
def webhook():
    global join_message, last_join_sent

    data = request.get_json()

    sender_type = data.get("sender_type")
    text = data.get("text", "")
    sender_id = data.get("sender_id")

    # Handle system join messages
    if sender_type == "system" and "has joined the group" in text:
        now = time.time()
        if now - last_join_sent > 5:  # 5-second rate limit
            send_message(join_message)
            last_join_sent = now

    # Handle admin command
    if sender_type == "user" and text.startswith("!joinmessage"):
        if sender_id in ADMINS:
            join_message = text.replace("!joinmessage", "").strip()
            send_message(f'Join message updated: "{join_message}"')

    return "ok", 200