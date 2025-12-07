import os, json, requests, re
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

def has_permission(group, sender_id):
    # Equality mode: everyone has permission
    if not group.get("admin_enabled", True):
        return True
    return sender_id == group["owner"] or sender_id in group["admins"]

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
            "triggers": [],
            "admin_enabled": True
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

    # !noadmins / !enableadmins
    if text == "!noadmins" and sender_id == group["owner"]:
        group["admin_enabled"] = False
        send_message(bot_id, "Admin system disabled. Everyone now has full permissions.")
        save_data(group_data)

    if text == "!enableadmins" and sender_id == group["owner"]:
        group["admin_enabled"] = True
        send_message(bot_id, "Admin system re-enabled. Only owner/admins have permissions.")
        save_data(group_data)

    # !admin userid
    if text.startswith("!admin") and sender_id == group["owner"]:
        new_admin = text.replace("!admin", "").strip()
        if new_admin:
            group["admins"].append(new_admin)
            send_message(bot_id, f"Added new admin: {new_admin}")
            save_data(group_data)

    # !deladmin userid
    if text.startswith("!deladmin") and sender_id == group["owner"]:
        del_admin = text.replace("!deladmin", "").strip()
        if del_admin in group["admins"]:
            group["admins"].remove(del_admin)
            send_message(bot_id, f"Removed admin: {del_admin}")
            save_data(group_data)
        else:
            send_message(bot_id, "That user is not an admin.")

    # !joinmessage (owner or admins, or equality mode)
    if text.startswith("!joinmessage") and has_permission(group, sender_id):
        group["join_message"] = text.replace("!joinmessage", "").strip()
        send_message(bot_id, f'Join message updated: "{group["join_message"]}"')
        save_data(group_data)

    # !addtrigger "phrase" response (owner/admins or equality mode)
    if text.startswith("!addtrigger") and has_permission(group, sender_id):
        if len(group["triggers"]) >= 20:
            send_message(bot_id, "Trigger limit reached (20).")
        else:
            match = re.match(r'!addtrigger\s+"([^"]+)"\s+(.+)', text)
            if match:
                phrase, response = match.groups()
                trigger_id = len(group["triggers"]) + 1
                group["triggers"].append({"id": trigger_id, "word": phrase, "response": response})
                send_message(bot_id, f'Trigger "{phrase}" added with id {trigger_id}.')
                save_data(group_data)
            else:
                send_message(bot_id, 'Usage: !addtrigger "phrase" <response>')

    # !listtriggers
    if text == "!listtriggers":
        if group["triggers"]:
            trigger_list = ", ".join([f"{t['id']}: \"{t['word']}\" -> {t['response']}" for t in group["triggers"]])
            send_message(bot_id, f"Current triggers: {trigger_list}")
        else:
            send_message(bot_id, "No triggers set.")

    # !removetrigger id
    if text.startswith("!removetrigger") and has_permission(group, sender_id):
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
            "!admin <userid> → Add a new admin\n"
            "!deladmin <userid> → Remove an admin\n"
            "!noadmins → Disable admin system (everyone equal)\n"
            "!enableadmins → Re-enable admin system\n\n"
            "🛠️ Admin/Owner Commands:\n"
            "!joinmessage <message> → Set welcome message\n"
            "!addtrigger \"phrase\" <response> → Add trigger (max 20)\n"
            "!listtriggers → Show triggers\n"
            "!removetrigger <id> → Remove trigger\n\n"
            "🙋 General User Commands:\n"
            "!userid [@username] → Get your ID or mentioned user IDs\n"
            "!help → Show this help message\n"
            "Triggers → Bot replies when trigger phrases are used"
        )
        send_message(bot_id, help_message)

    # Check triggers in normal messages
    if sender_type == "user":
        for t in group["triggers"]:
            if t["word"].lower() in text.lower():
                # Prevent self-trigger loop: don't trigger if bot just announced trigger creation
                if not text.startswith("Trigger "):
                    send_message(bot_id, t["response"])

    return "ok", 200
