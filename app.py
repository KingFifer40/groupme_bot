import os, json, requests, re, time, threading
from flask import Flask, request

app = Flask(__name__)

# -------------------------
# JSONBIN CONFIG
# -------------------------

JSONBIN_API_KEY = os.getenv("JSONBIN_API_KEY", "$2a$10$nAb7Htoy3JbgFAbMoYKKw.wLVuNXKXAhRNPwY.2Mm.gT7YlJT0WDW")  # fake placeholder
JSONBIN_BIN_ID = os.getenv("JSONBIN_BIN_ID", "69c9c7c4856a682189ddf11b")

JSONBIN_URL = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"

def load_data():
    headers = {"X-Master-Key": JSONBIN_API_KEY}
    r = requests.get(JSONBIN_URL, headers=headers)
    if r.status_code == 200:
        print("[JSONBIN] Loaded data successfully")
        return r.json()["record"]
    print("[JSONBIN] Failed to load data:", r.text)
    return {"groups": {}}

def save_data(data):
    headers = {
        "Content-Type": "application/json",
        "X-Master-Key": JSONBIN_API_KEY
    }
    r = requests.put(JSONBIN_URL, json=data, headers=headers)
    print("[JSONBIN] Save status:", r.status_code, r.text)

# Load root data
data_root = load_data()
group_data = data_root.get("groups", {})

# -------------------------
# HELP REGISTRY (MODULAR)
# -------------------------

HELP_ENTRIES = {
    "owner": [],
    "admin": [],
    "general": []
}

def register_help(section, command, description):
    HELP_ENTRIES[section].append(f"{command} → {description}")

# Register base commands
register_help("owner", "!OWNERME!!!", "Claim ownership of the bot")
register_help("owner", "!FALLENOWNER", "Abdicate ownership")
register_help("owner", "!disable", "Disable the bot entirely")
register_help("owner", "!enable", "Re-enable the bot")

register_help("admin", "!joinmessage <msg>", "Set the join message")
register_help("admin", "!addtrigger \"phrase\" <response>", "Add a custom trigger")
register_help("admin", "!removetrigger <id>", "Remove a trigger")
register_help("admin", "!addbadtrigger \"word\" [msg]", "Add a bad word trigger")
register_help("admin", "!removebad <id>", "Remove a bad trigger")

register_help("general", "!userid", "Show your user ID")
register_help("general", "!help", "Show the help menu")

# -------------------------
# BOT UTILITIES
# -------------------------

def send_message(bot_id, text, mentions=None):
    signature = "\u200B"  # invisible marker
    payload = {
        "bot_id": bot_id,
        "text": text + signature
    }
    if mentions:
        payload["attachments"] = [{
            "type": "mentions",
            "loci": mentions["loci"],
            "user_ids": mentions["user_ids"]
        }]
    requests.post("https://api.groupme.com/v3/bots/post", json=payload)

def has_permission(group, sender_id):
    if not group.get("admin_enabled", True):
        return True
    return sender_id == group["owner"] or sender_id in group["admins"]

def normalize_text(s: str) -> str:
    if not s:
        return s
    return (
        s.replace("\u201C", "\"")
         .replace("\u201D", "\"")
         .replace("\u201E", "\"")
         .replace("\u201F", "\"")
         .replace("\u00AB", "\"")
         .replace("\u00BB", "\"")
         .replace("\u2033", "\"")
         .replace("\u2018", "'")
         .replace("\u2019", "'")
         .replace("\u201A", "'")
         .replace("\u2032", "'")
    )

def parse_addtrigger(text: str):
    m = re.match(r'!addtrigger\s+["\']([^"\']+)["\']\s+(.+)', text, flags=re.IGNORECASE)
    if m:
        phrase, response = m.groups()
        return phrase.strip(), response.strip()
    return None, None

def parse_addbadtrigger(text: str):
    m = re.match(r'!addbadtrigger\s+["\']([^"\']+)["\']\s*(.*)', text, flags=re.IGNORECASE)
    if m:
        word, msg = m.groups()
        return word.strip(), msg.strip() if msg else None
    return None, None

# -------------------------
# KEEPALIVE (Render Free Tier)
# -------------------------

@app.route("/ping")
def ping():
    return "pong", 200

def keepalive():
    while True:
        try:
            requests.get("https://YOUR-RENDER-URL.onrender.com/ping")
        except:
            pass
        time.sleep(240)  # ping every 4 minutes

threading.Thread(target=keepalive, daemon=True).start()

# -------------------------
# WEBHOOK START
# -------------------------

@app.route("/", methods=["POST"])
def webhook():
    global group_data
    data = request.get_json()

    # Always reload latest data from JSONBin
    data_root = load_data()
    group_data = data_root.get("groups", {})

    bot_id = data.get("bot", {}).get("id") or data.get("bot_id")
    group_id = str(data.get("group_id"))
    sender_id = data.get("sender_id")
    sender_type = data.get("sender_type")
    text = normalize_text((data.get("text") or "").strip())
    lowered = text.lower()

    # Ignore bot's own messages (signature check)
    if text.endswith("\u200B"):
        return "ok", 200

    # Ensure group entry exists
    if group_id not in group_data:
        group_data[group_id] = {
            "owner": None,
            "admins": [],
            "join_message": "Welcome to the group!",
            "triggers": [],
            "bad_triggers": [],
            "admin_enabled": True,
            "bot_enabled": True
        }
        save_data({"groups": group_data})

    group = group_data[group_id]

    # -------------------------
    # PATCH MISSING FIELDS (fixes KeyError: 'bot_enabled')
    # -------------------------

    changed = False

    if "bot_enabled" not in group:
        group["bot_enabled"] = True
        changed = True

    if "admin_enabled" not in group:
        group["admin_enabled"] = True
        changed = True

    if "triggers" not in group:
        group["triggers"] = []
        changed = True

    if "bad_triggers" not in group:
        group["bad_triggers"] = []
        changed = True

    if "admins" not in group:
        group["admins"] = []
        changed = True

    if "join_message" not in group:
        group["join_message"] = "Welcome to the group!"
        changed = True

    if changed:
        save_data({"groups": group_data})

    # If bot is disabled, only allow !enable
    if not group["bot_enabled"] and text != "!enable":
        return "ok", 200

    # System join messages
    if sender_type == "system" and "has joined the group" in text:
        send_message(bot_id, group["join_message"])

    # OWNERME!!!
    if text == "!OWNERME!!!":
        if group["owner"] is None:
            group["owner"] = sender_id
            send_message(bot_id, "You are now the OWNER of this bot!")
            save_data({"groups": group_data})
        else:
            send_message(bot_id, "THERE IS ALREADY AN OWNER LOL 🫵🤣")

    # FALLENOWNER (customized)
    if text == "!FALLENOWNER":
        if sender_id != group["owner"]:
            send_message(bot_id, "Why are you trying to overthrow my king? 😡")
        else:
            group["owner"] = None
            save_data({"groups": group_data})
            send_message(bot_id, "The throne is now empty. A new ruler may rise.")

    # !disable
    if text == "!disable" and has_permission(group, sender_id):
        group["bot_enabled"] = False
        save_data({"groups": group_data})
        send_message(bot_id, "Bot disabled. Only !enable will work now.")
        return "ok", 200

    # !enable
    if text == "!enable":
        if has_permission(group, sender_id):
            group["bot_enabled"] = True
            save_data({"groups": group_data})
            send_message(bot_id, "Bot re-enabled.")
        else:
            send_message(bot_id, "You lack the authority to awaken me.")
        return "ok", 200

    # !noadmins / !enableadmins
    if text == "!noadmins" and sender_id == group["owner"]:
        group["admin_enabled"] = False
        save_data({"groups": group_data})
        send_message(bot_id, "Admin system disabled. Everyone now has full permissions.")

    if text == "!enableadmins" and sender_id == group["owner"]:
        group["admin_enabled"] = True
        save_data({"groups": group_data})
        send_message(bot_id, "Admin system re-enabled. Only owner/admins have permissions.")

    # Mentions helper
    def mentioned_user_ids():
        ids = []
        for att in data.get("attachments", []):
            if att.get("type") == "mentions":
                ids.extend(att.get("user_ids", []))
        return ids

    # !admin
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
            save_data({"groups": group_data})
            send_message(bot_id, f"Added admin(s): {', '.join(added)}")
        else:
            send_message(bot_id, "No new admins added.")

    # !deladmin
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
            save_data({"groups": group_data})
            send_message(bot_id, f"Removed admin(s): {', '.join(removed)}")
        else:
            send_message(bot_id, "No matching admins to remove.")

    # !joinmessage
    if text.startswith("!joinmessage") and has_permission(group, sender_id):
        group["join_message"] = text.replace("!joinmessage", "").strip()
        save_data({"groups": group_data})
        send_message(bot_id, f'Join message updated: "{group["join_message"]}"')

    # -------------------------
    # ADD TRIGGER (with overlap protection)
    # -------------------------

    if text.lower().startswith("!addtrigger") and has_permission(group, sender_id):
        if len(group["triggers"]) >= 20:
            send_message(bot_id, "Trigger limit reached (20).")
        else:
            phrase, response = parse_addtrigger(text)
            if phrase and response:
                new_word = phrase.lower()

                # Check for duplicates or substring overlaps
                for t in group["triggers"]:
                    existing = t["word"].lower()
                    if existing in new_word or new_word in existing:
                        send_message(bot_id, f'Cannot add trigger "{phrase}" because it overlaps with existing trigger "{t["word"]}".')
                        return "ok", 200

                next_id = (max([t["id"] for t in group["triggers"]] or [0]) + 1)
                group["triggers"].append({"id": next_id, "word": phrase, "response": response})
                save_data({"groups": group_data})
                send_message(bot_id, f'Trigger "{phrase}" added with id {next_id}.')
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
                save_data({"groups": group_data})
                send_message(bot_id, f"Trigger {tid} removed.")
            else:
                send_message(bot_id, "Invalid trigger ID.")
        except:
            send_message(bot_id, "Invalid trigger ID.")

    # -------------------------
    # ADD BAD TRIGGER (with overlap protection)
    # -------------------------

    if text.lower().startswith("!addbadtrigger") and has_permission(group, sender_id):
        if len(group["bad_triggers"]) >= 30:
            send_message(bot_id, "Bad trigger limit reached (30).")
        else:
            word, msg = parse_addbadtrigger(text)
            if word:
                new_word = word.lower()

                for bt in group["bad_triggers"]:
                    existing = bt["word"].lower()
                    if existing in new_word or new_word in existing:
                        send_message(bot_id, f'Cannot add bad trigger "{word}" because it overlaps with existing bad trigger "{bt["word"]}".')
                        return "ok", 200

                next_id = (max([t["id"] for t in group["bad_triggers"]] or [0]) + 1)
                group["bad_triggers"].append({"id": next_id, "word": word, "message": msg})
                save_data({"groups": group_data})
                send_message(bot_id, f'Bad trigger "{word}" added with id {next_id}.')
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
                save_data({"groups": group_data})
                send_message(bot_id, f"Bad trigger {tid} removed.")
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
            "admin_enabled": True,
            "bot_enabled": True
        }
        save_data({"groups": group_data})
        send_message(bot_id, "Group data has been reset. Fresh start!")

    # !userid
    if text.startswith("!userid"):
        ids = mentioned_user_ids()
        if ids:
            send_message(bot_id, f"Mentioned user IDs: {', '.join(ids)}")
        else:
            send_message(bot_id, f"Your user ID is {sender_id}")

    # !help (modular)
    if text == "!help":
        msg = "📘 **Help Menu**\n\n"

        if group["bot_enabled"]:
            msg += "👑 **Owner Commands**\n" + "\n".join(HELP_ENTRIES["owner"]) + "\n\n"
            msg += "🛠️ **Admin Commands**\n" + "\n".join(HELP_ENTRIES["admin"]) + "\n\n"

        msg += "🙋 **General Commands**\n" + "\n".join(HELP_ENTRIES["general"])

        send_message(bot_id, msg)

    # -------------------------
    # NORMAL TRIGGERS
    # -------------------------

    if sender_type == "user":
        for t in group["triggers"]:
            if t["word"].lower() in lowered:
                if not lowered.startswith("trigger "):
                    send_message(bot_id, t["response"])

    # -------------------------
    # BAD TRIGGERS
    # -------------------------

    for bt in group["bad_triggers"]:
        if bt["word"].lower() in lowered:
            if group["admin_enabled"] and (group["admins"] or group["owner"]):
                base_msg = f'You said this banned word. {bt["message"] or ""} '
                loci = []
                user_ids = []
                pos = len(base_msg)

                ids_to_ping = []
                if group["owner"]:
                    ids_to_ping.append(group["owner"])
                ids_to_ping.extend(group["admins"])

                for idx, uid in enumerate(ids_to_ping):
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
