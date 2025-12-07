import os, json, requests
from flask import Flask, request

app = Flask(__name__)

DATA_FILE = "group_data.json"

def send_message(bot_id, text):
    # Send messages through GroupMe API using the bot_id from payload
    requests.post("https://api.groupme.com/v3/bots/post", json={
        "bot_id": bot_id,
        "text": text
    })

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

group_data = load_data()

@app.route("/", methods=["POST"])
def webhook():
    global group_data
    data = request.get_json()

    # bot_id comes from mebots payload
    bot_id = data.get("bot", {}).get("id") or data.get("bot_id")
    group_id = str(data.get("group_id"))
    sender_id = data.get("sender_id")
    sender_type = data.get("sender_type")
    text = (data.get("text") or "").strip()

    # Ensure group entry exists
    if group_id not in group_data:
        group_data[group_id] = {
            "owner": None,
            "admins": [],
            "join_message": "Welcome to the group!",
            "triggers": []
        }

    group = group_data[group_id]

    # System join messages
    if sender_type == "system" and "has joined the group" in text:
        send_message(bot_id, group["join_message"])

    # OWNERME!!!
    if text == "!OWNERME!!!":
        if group["owner"] is None:
            group["owner"] = sender_id
            send_message(bot_id, "You are now the OWNER of this bot!")
            save_data(group_data)
        else:
            send_message(bot_id, "THERE IS ALREADY AN OWNER LOL 🫵🤣")

    # FALLENOWNER
    if text == "!FALLENOWNER":
        if sender_id == group["owner"]:
            group["owner"] = None
            send_message(bot_id, "The owner has abdicated. Ownership is open again.")
            save_data(group_data)
        else:
            send_message(bot_id, "YOU DARE TO DETHRONE THE RULER OVER THIS BOT???")

    # !admin userid
    if text.startswith("!admin"):
        if sender_id == group["owner"]:
            new_admin = text.replace("!admin", "").strip()
            if new_admin:
                group["admins"].append(new_admin)
                send_message(bot_id, f"Added new admin: {new_admin}")
                save_data(group_data)
        else:
            send_message(bot_id, "Only the owner can add admins.")

    # !joinmessage (admins only)
    if text.startswith("!joinmessage") and sender_id in group["admins"]:
        group["join_message"] = text.replace("!joinmessage", "").strip()
        send_message(bot_id, f'Join message updated: "{group["join_message"]}"')
        save_data(group_data)

    # !addtrigger <word> <response>
    if text.startswith("!addtrigger") and sender_id in group["admins"]:
        if len(group["triggers"]) >= 20:
            send_message(bot_id, "Trigger limit reached (20).")
        else:
            parts = text.replace("!addtrigger", "").strip().split(" ", 1)
            if len(parts) == 2:
                word, response = parts[0].strip(), parts[1].strip()
                trigger_id = len(group["triggers"]) + 1
                group["triggers"].append({"id": trigger_id, "word": word, "response": response})
                send_message(bot_id, f"A new trigger with the id of {trigger_id} was created")
                save_data(group_data)
            else:
                send_message(bot_id, "Usage: !addtrigger <word> <response message>")

    # !listtriggers
    if text == "!listtriggers":
        if group["triggers"]:
            trigger_list = ", ".join([f"{t['id']}: {t['word']} -> {t['response']}" for t in group["triggers"]])
            send_message(bot_id, f"Current triggers: {trigger_list}")
        else:
            send_message(bot_id, "No triggers set.")

    # !removetrigger id
    if text.startswith("!removetrigger") and sender_id in group["admins"]:
        try:
            tid = int(text.replace("!removetrigger", "").strip())
            group["triggers"] = [t for t in group["triggers"] if t["id"] != tid]
            send_message(bot_id, f"Trigger {tid} removed.")
            save_data(group_data)
        except:
            send_message(bot_id, "Invalid trigger ID.")

    # !userid command
    if text.startswith("!userid"):
        mentions = data.get("attachments", [])
        mentioned_ids = []
        for att in mentions:
            if att.get("type") == "mentions":
                for m in att.get("user_ids", []):
                    mentioned_ids.append(m)

        if mentioned_ids:
            send_message(bot_id, f"Mentioned user IDs: {', '.join(mentioned_ids)}")
        else:
            send_message(bot_id, f"Your user ID is {sender_id}")

    # !help command
    if text == "!help":
        help_message = (
            "👑 Owner Commands:\n"
            "!OWNERME!!! → Claim ownership\n"
            "!FALLENOWNER → Abdicate ownership\n"
            "!admin <userid> → Add a new admin\n\n"
            "🛠️ Admin Commands:\n"
            "!joinmessage <message> → Set welcome message\n"
            "!addtrigger <word> <response> → Add trigger (max 20)\n"
            "!listtriggers → Show triggers\n"
            "!removetrigger <id> → Remove trigger\n\n"
            "🙋 General User Commands:\n"
            "!userid [@username] → Get your ID or mentioned user IDs\n"
            "!help → Show this help message\n"
            "Triggers → Bot replies when trigger words are used"
        )
        send_message(bot_id, help_message)

    # Check triggers in normal messages
    if sender_type == "user":
        for t in group["triggers"]:
            if t["word"].lower() in text.lower():
                send_message(bot_id, t["response"])

    return "ok", 200
