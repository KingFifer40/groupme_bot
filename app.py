import os, time, json, requests
from flask import Flask, request

app = Flask(__name__)

# Use BOT_ID env var to store your mebots token
MEBOTS_TOKEN = os.environ.get("BOT_ID")
DATA_FILE = "group_data.json"

def send_message(text):
    # Send messages through mebots API
    requests.post(f"https://api.mebots.io/bot/{MEBOTS_TOKEN}/send", json={
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
        send_message(group["join_message"])

    # OWNERME!!!
    if text == "!OWNERME!!!":
        if group["owner"] is None:
            group["owner"] = sender_id
            send_message("You are now the OWNER of this bot!")
            save_data(group_data)
        else:
            send_message("THERE IS ALREADY AN OWNER LOL 🫵🤣")

    # FALLENOWNER
    if text == "!FALLENOWNER":
        if sender_id == group["owner"]:
            group["owner"] = None
            send_message("The owner has abdicated. Ownership is open again.")
            save_data(group_data)
        else:
            send_message("YOU DARE TO DETHRONE THE RULER OVER THIS BOT???")

    # !admin userid
    if text.startswith("!admin"):
        if sender_id == group["owner"]:
            new_admin = text.replace("!admin", "").strip()
            if new_admin:
                group["admins"].append(new_admin)
                send_message(f"Added new admin: {new_admin}")
                save_data(group_data)
        else:
            send_message("Only the owner can add admins.")

    # !joinmessage (admins only)
    if text.startswith("!joinmessage") and sender_id in group["admins"]:
        group["join_message"] = text.replace("!joinmessage", "").strip()
        send_message(f'Join message updated: "{group["join_message"]}"')
        save_data(group_data)

    # !addtrigger <word> <response>
    if text.startswith("!addtrigger") and sender_id in group["admins"]:
        if len(group["triggers"]) >= 20:
            send_message("Trigger limit reached (20).")
        else:
            parts = text.replace("!addtrigger", "").strip().split(" ", 1)
            if len(parts) == 2:
                word, response = parts[0].strip(), parts[1].strip()
                trigger_id = len(group["triggers"]) + 1
                group["triggers"].append({"id": trigger_id, "word": word, "response": response})
                send_message(f"A new trigger with the id of {trigger_id} was created")
                save_data(group_data)
            else:
                send_message("Usage: !addtrigger <word> <response message>")

    # !listtriggers
    if text == "!listtriggers":
        if group["triggers"]:
            trigger_list = ", ".join([f"{t['id']}: {t['word']} -> {t['response']}" for t in group["triggers"]])
            send_message(f"Current triggers: {trigger_list}")
        else:
            send_message("No triggers set.")

    # !removetrigger id
    if text.startswith("!removetrigger") and sender_id in group["admins"]:
        try:
            tid = int(text.replace("!removetrigger", "").strip())
            group["triggers"] = [t for t in group["triggers"] if t["id"] != tid]
            send_message(f"Trigger {tid} removed.")
            save_data(group_data)
        except:
            send_message("Invalid trigger ID.")

    # Check triggers in normal messages
    if sender_type == "user":
        for t in group["triggers"]:
            if t["word"].lower() in text.lower():
                send_message(t["response"])

    return "ok", 200
