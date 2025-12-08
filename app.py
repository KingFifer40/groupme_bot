import os, json, requests, re, time
from flask import Flask, request

app = Flask(__name__)

DATA_FILE = "group_data.json"

def send_message(bot_id, text, mentions=None):
    payload = {
        "bot_id": bot_id,
        "text": text
    }
    if mentions:
        payload["attachments"] = [{
            "type": "mentions",
            "loci": mentions["loci"],
            "user_ids": mentions["user_ids"]
        }]
    requests.post("https://api.groupme.com/v3/bots/post", json=payload)

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
    if not group.get("admin_enabled", True):
        return True
    return sender_id == group["owner"] or sender_id in group["admins"]

# Normalize “smart” quotes and other variants to ASCII
def normalize_text(s: str) -> str:
    if not s:
        return s
    return (
        s.replace("\u201C", "\"")  # Left double quote “
         .replace("\u201D", "\"")  # Right double quote ”
         .replace("\u201E", "\"")  # Low double quote „
         .replace("\u201F", "\"")  # Double high-reversed-9 quotation mark ‟
         .replace("\u00AB", "\"")  # «
         .replace("\u00BB", "\"")  # »
         .replace("\u2033", "\"")  # Double prime ″
         .replace("\u2018", "'")   # Left single quote ‘
         .replace("\u2019", "'")   # Right single quote ’
         .replace("\u201A", "'")   # Single low-9 quote ‚
         .replace("\u2032", "'")   # Prime ′
    )

# Parse: !addtrigger "<phrase>" <response>
def parse_addtrigger(text: str):
    m = re.match(r'!addtrigger\s+["\']([^"\']+)["\']\s+(.+)', text, flags=re.IGNORECASE)
    if m:
        phrase, response = m.groups()
        return phrase.strip(), response.strip()
    return None, None

# Parse: !addbadtrigger "badword" optional_message
def parse_addbadtrigger(text: str):
    m = re.match(r'!addbadtrigger\s+["\']([^"\']+)["\']\s*(.*)', text, flags=re.IGNORECASE)
    if m:
        word, msg = m.groups()
        return word.strip(), msg.strip() if msg else None
    return None, None

@app.route("/", methods=["POST"])
def webhook():
    global group_data
    data = request.get_json()

    bot_id = data.get("bot", {}).get("id") or data.get("bot_id")
    group_id = str(data.get("group_id"))
    sender_id = data.get("sender_id")
    sender_type = data.get("sender_type")
    text = normalize_text((data.get("text") or "").strip())
    lowered = text.lower()

    # Ensure group entry exists
    if group_id not in group_data:
        group_data[group_id] = {
            "owner": None,
            "admins": [],
            "join_message": "Welcome to the group!",
            "triggers": [],
            "bad_triggers": [],   # NEW: bad word triggers
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

    # Mentions helper
    def mentioned_user_ids():
        ids = []
        for att in data.get("attachments", []):
            if att.get("type") == "mentions":
                ids.extend(att.get("user_ids", []))
        return ids

    # !admin @mention or !admin userid
    if text.startswith("!admin") and sender_id == group["owner"]:
        ids = mentioned_user_ids()
        if not ids:
            new_admin = text.replace("!admin", "").strip()
            if new_admin:
                ids = [new_admin]
        added = []
        for uid in ids:
            if uid not in group["admins"]:
                group["admins"].append(uid)
                added.append(uid)
        if added:
            send_message(bot_id, f"Added admin(s): {', '.join(added)}")
            save_data(group_data)
        else:
            send_message(bot_id, "No new admins added.")

    # !deladmin @mention or !deladmin userid
    if text.startswith("!deladmin") and sender_id == group["owner"]:
        ids = mentioned_user_ids()
        if not ids:
            del_admin = text.replace("!deladmin", "").strip()
            if del_admin:
                ids = [del_admin]
        removed = []
        for uid in ids:
            if uid in group["admins"]:
                group["admins"].remove(uid)
                removed.append(uid)
        if removed:
            send_message(bot_id, f"Removed admin(s): {', '.join(removed)}")
            save_data(group_data)
        else:
            send_message(bot_id, "No matching admins to remove.")

    # !joinmessage
    if text.startswith("!joinmessage") and has_permission(group, sender_id):
        group["join_message"] = text.replace("!joinmessage", "").strip()
        send_message(bot_id, f'Join message updated: "{group["join_message"]}"')
        save_data(group_data)

    # !addtrigger
    if text.lower().startswith("!addtrigger") and has_permission(group, sender_id):
        if len(group["triggers"]) >= 20:
            send_message(bot_id, "Trigger limit reached (20).")
        else:
            phrase, response = parse_addtrigger(text)
            if phrase and response:
                next_id = (max([t["id"] for t in group["triggers"]] or [0]) + 1)
                group["triggers"].append({"id": next_id, "word": phrase, "response": response})
                send_message(bot_id, f'Trigger "{phrase}" added with id {next_id}.')
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

    # !removetrigger
    if text.startswith("!removetrigger") and has_permission(group, sender_id):
        try:
            tid = int(text.replace("!removetrigger", "").strip())
            before = len(group["triggers"])
            group["triggers"] = [t for t in group["triggers"] if t["id"] != tid]
            after = len(group["triggers"])
            if before != after:
                send_message(bot_id, f"Trigger {tid} removed.")
                save_data(group_data)
            else:
                send_message(bot_id, "Invalid trigger ID.")
        except:
            send_message(bot_id, "Invalid trigger ID.")

    # !addbadtrigger
    if text.lower().startswith("!addbadtrigger") and has_permission(group, sender_id):
        if len(group["bad_triggers"]) >= 30:
            send_message(bot_id, "Bad trigger limit reached (30).")
        else:
            word, msg = parse_addbadtrigger(text)
            if word:
                next_id = (max([t["id"] for t in group["bad_triggers"]] or [0]) + 1)
                group["bad_triggers"].append({"id": next_id, "word": word, "message": msg})
                send_message(bot_id, f'Bad trigger "{word}" added with id {next_id}.')
                save_data(group_data)
            else:
                send_message(bot_id, 'Usage: !addbadtrigger "badword" [optional_message]')

    # !listbad
    if text == "!listbad":
        if group["bad_triggers"]:
            bad_list = ", ".join([f"{t['id']}: \"{t['word']}\" -> {t['message'] or '(no message)'}" for t in group["bad_triggers"]])
            send_message(bot_id, f"Current bad triggers: {bad_list}")
        else:
            send_message(bot_id, "No bad triggers set.")

    # !removebad
    if text.startswith("!removebad") and has_permission(group, sender_id):
        try:
            tid = int(text.replace("!removebad", "").strip())
            before = len(group["bad_triggers"])
            group["bad_triggers"] = [t for t in group["bad_triggers"] if t["id"] != tid]
            after = len(group["bad_triggers"])
            if before != after:
                send_message(bot_id, f"Bad trigger {tid} removed.")
                save_data(group_data)
            else:
                send_message(bot_id, "Invalid bad trigger ID.")
        except:
            send_message(bot_id, "Invalid bad trigger ID.")

    # !reset
    if text == "!reset" and sender_id == group["owner"]:
        group_data[group_id] = {
            "owner": None,
            "admins": [],
            "join_message": "Welcome to the group!",
            "triggers": [],
            "bad_triggers": [],
            "admin_enabled": True
        }
        save_data(group_data)
        send_message(bot_id, "Group data has been reset. Fresh start!")

    # !userid
    if text.startswith("!userid"):
        ids = mentioned_user_ids()
        if ids:
            send_message(bot_id, f"Mentioned user IDs: {', '.join(ids)}")
        else:
            send_message(bot_id, f"Your user ID is {sender_id}")

    # !help
    if text == "!help":
        help_message = (
            "👑 Owner Commands:\n"
            "!OWNERME!!! → Claim ownership\n"
            "!FALLENOWNER → Abdicate ownership\n"
            "!admin <userid>|@user → Add admin\n"
            "!deladmin <userid>|@user → Remove admin\n"
            "!noadmins → Disable admin system\n"
            "!enableadmins → Re-enable admin system\n"
            "!reset → Reset all group data\n\n"
            "🛠️ Admin/Owner Commands:\n"
            "!joinmessage <message>\n"
            "!addtrigger \"phrase\" <response>\n"
            "!listtriggers\n"
            "!removetrigger <id>\n"
            "!addbadtrigger \"badword\" [optional_message]\n"
            "!listbad\n"
            "!removebad <id>\n\n"
            "🙋 General:\n"
            "!userid [@user]\n"
            "!help"
        )
        send_message(bot_id, help_message)

    # Triggers in normal messages
    if sender_type == "user":
        lowered = text.lower()
        # Normal triggers
        for t in group["triggers"]:
            if t["word"].lower() in lowered:
                if not lowered.startswith("trigger "):
                    send_message(bot_id, t["response"])
    # Bad triggers
    for bt in group["bad_triggers"]:
        if bt["word"].lower() in lowered:
            if group["admin_enabled"] and (group["admins"] or group["owner"]):
                base_msg = f'You said this banned word. {bt["message"] or ""} '
                loci = []
                user_ids = []
                pos = len(base_msg)

                # Collect all IDs (owner + admins)
                ids_to_ping = []
                if group["owner"]:
                    ids_to_ping.append(group["owner"])
                ids_to_ping.extend(group["admins"])

                # Add each mention separately
                for idx, uid in enumerate(ids_to_ping):
                    # Give each mention its own placeholder text
                    mention_text = f"@admin{idx+1}"
                    base_msg += mention_text + " "
                    loci.append([pos, len(mention_text)])
                    user_ids.append(uid)
                    pos += len(mention_text) + 1

                send_message(bot_id, base_msg.strip(),
                             mentions={"loci": loci, "user_ids": user_ids})
            elif bt["message"]:
                send_message(bot_id, bt["message"])

    return "ok", 200
