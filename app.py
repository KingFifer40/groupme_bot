import os, json, requests, re, time, threading
from flask import Flask, request

app = Flask(__name__)

# -------------------------
# JSONBIN CONFIG
# -------------------------

JSONBIN_API_KEY = os.getenv("JSONBIN_API_KEY")
JSONBIN_BIN_ID = os.getenv("JSONBIN_BIN_ID")

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
register_help("admin", "!refreshadmins", "Force-refresh admin list from GroupMe")

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

RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")

def keepalive():
    while True:
        try:
            if RENDER_URL:
                requests.get(RENDER_URL + "/ping")
        except:
            pass
        time.sleep(240)

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

    # Extract GroupMe admin roles
    user_info = data.get("user", {})
    roles = user_info.get("roles", [])

    is_group_owner = "owner" in roles
    is_group_admin = "admin" in roles or is_group_owner

    # Ignore bot's own messages (signature check)
    if text.endswith("\u200B"):
        return "ok", 200

    # Ensure group entry exists
    if group_id not in group_data:
        group_data[group_id] = {
            "bot_owner": None,
            "bot_admins": [],
            "group_owner": None,
            "group_admins": [],
            "join_message": "Welcome to the group!",
            "triggers": [],
            "bad_triggers": [],
            "admin_enabled": True,
            "bot_enabled": True
        }
        save_data({"groups": group_data})

    group = group_data[group_id]

    # -------------------------
    # AUTO-PATCH + AUTO-SYNC ADMIN SYSTEM
    # -------------------------

    changed = False

    # Ensure all required fields exist
    defaults = {
        "bot_owner": None,
        "bot_admins": [],
        "group_owner": None,
        "group_admins": [],
        "join_message": "Welcome to the group!",
        "triggers": [],
        "bad_triggers": [],
        "admin_enabled": True,
        "bot_enabled": True
    }

    for key, value in defaults.items():
        if key not in group:
            group[key] = value
            changed = True

    # Sync real group owner
    if is_group_owner and group["group_owner"] != sender_id:
        group["group_owner"] = sender_id
        changed = True

    # Sync real group admins
    if is_group_admin and sender_id not in group["group_admins"]:
        group["group_admins"].append(sender_id)
        changed = True

    if changed:
        save_data({"groups": group_data})

    # If bot is disabled, only allow !enable
    if not group["bot_enabled"] and text != "!enable":
        return "ok", 200

    # System join messages
    if sender_type == "system" and "has joined the group" in text:
        send_message(bot_id, group["join_message"])

    # -------------------------
    # PERMISSION CHECK
    # -------------------------

    def has_permission(group, sender_id):
        # Bot owner always has permission
        if sender_id == group.get("bot_owner"):
            return True

        # Real group owner always has permission
        if sender_id == group.get("group_owner"):
            return True

        # Real group admins always have permission
        if sender_id in group.get("group_admins", []):
            return True

        # Bot-specific admins have permission
        if sender_id in group.get("bot_admins", []):
            return True

        return False

    # -------------------------
    # OWNER CLAIM
    # -------------------------

    if text == "!OWNERME!!!":
        if not is_group_admin:
            send_message(bot_id, "Only real group admins can claim bot ownership.")
        else:
            if group["bot_owner"] is None:
                group["bot_owner"] = sender_id
                save_data({"groups": group_data})
                send_message(bot_id, "You are now the bot owner!")
            else:
                send_message(bot_id, "There is already a bot owner.")
        return "ok", 200

    # -------------------------
    # FALLENOWNER
    # -------------------------

    if text == "!FALLENOWNER":
        if sender_id != group.get("bot_owner"):
            send_message(bot_id, "Only the bot owner can abdicate ownership.")
        else:
            group["bot_owner"] = None
            save_data({"groups": group_data})
            send_message(bot_id, "Bot ownership has been cleared.")
        return "ok", 200

    # -------------------------
    # BOT ENABLE / DISABLE
    # -------------------------

    if text == "!disable" and has_permission(group, sender_id):
        group["bot_enabled"] = False
        save_data({"groups": group_data})
        send_message(bot_id, "Bot disabled. Only !enable will work now.")
        return "ok", 200

    if text == "!enable":
        if has_permission(group, sender_id):
            group["bot_enabled"] = True
            save_data({"groups": group_data})
            send_message(bot_id, "Bot re-enabled.")
        else:
            send_message(bot_id, "You lack permission to enable the bot.")
        return "ok", 200

    # -------------------------
    # REFRESH ADMINS COMMAND
    # -------------------------

    if text == "!refreshadmins" and has_permission(group, sender_id):
        changed = False

        # Reset real admin lists
        group["group_admins"] = []
        changed = True

        # Re-detect sender's roles
        if is_group_owner:
            group["group_owner"] = sender_id
            changed = True

        if is_group_admin and sender_id not in group["group_admins"]:
            group["group_admins"].append(sender_id)
            changed = True

        if changed:
            save_data({"groups": group_data})
            send_message(bot_id, "Admin list refreshed from GroupMe.")
        else:
            send_message(bot_id, "Admin list already up to date.")

        return "ok", 200

    # -------------------------
    # BOT-SPECIFIC ADMIN ADD
    # -------------------------

    if text.startswith("!admin") and has_permission(group, sender_id):
        uid = text.replace("!admin", "").strip()

        if not uid:
            send_message(bot_id, "Usage: !admin <user_id>")
        else:
            if uid in group["group_admins"]:
                send_message(bot_id, "That user is already a real group admin.")
            elif uid in group["bot_admins"]:
                send_message(bot_id, "That user is already a bot admin.")
            else:
                group["bot_admins"].append(uid)
                save_data({"groups": group_data})
                send_message(bot_id, f"Added bot admin: {uid}")
        return "ok", 200

    # -------------------------
    # BOT-SPECIFIC ADMIN REMOVE
    # -------------------------

    if text.startswith("!deladmin") and has_permission(group, sender_id):
        uid = text.replace("!deladmin", "").strip()

        if not uid:
            send_message(bot_id, "Usage: !deladmin <user_id>")
        else:
            if uid in group["bot_admins"]:
                group["bot_admins"].remove(uid)
                save_data({"groups": group_data})
                send_message(bot_id, f"Removed bot admin: {uid}")
            else:
                send_message(bot_id, "That user is not a bot admin.")
        return "ok", 200

    # -------------------------
    # JOIN MESSAGE
    # -------------------------

    if text.startswith("!joinmessage") and has_permission(group, sender_id):
        group["join_message"] = text.replace("!joinmessage", "").strip()
        save_data({"groups": group_data})
        send_message(bot_id, f'Join message updated: "{group["join_message"]}"')
        return "ok", 200

    # -------------------------
    # ADD TRIGGER
    # -------------------------

    if text.lower().startswith("!addtrigger") and has_permission(group, sender_id):
        if len(group["triggers"]) >= 20:
            send_message(bot_id, "Trigger limit reached (20).")
        else:
            phrase, response = parse_addtrigger(text)
            if phrase and response:
                new_word = phrase.lower()

                # Overlap protection
                for t in group["triggers"]:
                    existing = t["word"].lower()
                    if existing in new_word or new_word in existing:
                        send_message(bot_id, f'Cannot add trigger "{phrase}" because it overlaps with "{t["word"]}".')
                        return "ok", 200

                next_id = (max([t["id"] for t in group["triggers"]] or [0]) + 1)
                group["triggers"].append({"id": next_id, "word": phrase, "response": response})
                save_data({"groups": group_data})
                send_message(bot_id, f'Trigger "{phrase}" added with id {next_id}.')
            else:
                send_message(bot_id, 'Usage: !addtrigger "phrase" <response>')
        return "ok", 200

    # -------------------------
    # LIST TRIGGERS
    # -------------------------

    if text == "!listtriggers":
        if group["triggers"]:
            trigger_list = ", ".join([f"{t['id']}: \"{t['word']}\" -> {t['response']}" for t in group["triggers"]])
            send_message(bot_id, f"Current triggers: {trigger_list}")
        else:
            send_message(bot_id, "No triggers set.")
        return "ok", 200

    # -------------------------
    # REMOVE TRIGGER
    # -------------------------

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
        return "ok", 200

    # -------------------------
    # ADD BAD TRIGGER
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
                        send_message(bot_id, f'Cannot add bad trigger "{word}" because it overlaps with "{bt["word"]}".')
                        return "ok", 200

                next_id = (max([t["id"] for t in group["bad_triggers"]] or [0]) + 1)
                group["bad_triggers"].append({"id": next_id, "word": word, "message": msg})
                save_data({"groups": group_data})
                send_message(bot_id, f'Bad trigger "{word}" added with id {next_id}.')
            else:
                send_message(bot_id, 'Usage: !addbadtrigger "badword" [optional_message]')
        return "ok", 200

    # -------------------------
    # LIST BAD TRIGGERS
    # -------------------------

    if text == "!listbad":
        if group["bad_triggers"]:
            bad_list = ", ".join([f"{t['id']}: \"{t['word']}\" -> {t['message'] or '(no message)'}" for t in group["bad_triggers"]])
            send_message(bot_id, f"Current bad triggers: {bad_list}")
        else:
            send_message(bot_id, "No bad triggers set.")
        return "ok", 200

    # -------------------------
    # REMOVE BAD TRIGGER
    # -------------------------

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
        return "ok", 200

    # -------------------------
    # RESET GROUP
    # -------------------------

    if text == "!reset" and sender_id == group.get("bot_owner"):
        group_data[group_id] = {
            "bot_owner": None,
            "bot_admins": [],
            "group_owner": None,
            "group_admins": [],
            "join_message": "Welcome to the group!",
            "triggers": [],
            "bad_triggers": [],
            "admin_enabled": True,
            "bot_enabled": True
        }
        save_data({"groups": group_data})
        send_message(bot_id, "Group data has been reset.")
        return "ok", 200

    # -------------------------
    # USER ID
    # -------------------------

    if text.startswith("!userid"):
        send_message(bot_id, f"Your user ID is {sender_id}")
        return "ok", 200

    # -------------------------
    # HELP MENU
    # -------------------------

    if text == "!help":
        msg = "📘 **Help Menu**\n\n"

        msg += "👑 **Owner Commands**\n" + "\n".join(HELP_ENTRIES["owner"]) + "\n\n"
        msg += "🛠️ **Admin Commands**\n" + "\n".join(HELP_ENTRIES["admin"]) + "\n\n"
        msg += "🙋 **General Commands**\n" + "\n".join(HELP_ENTRIES["general"])

        send_message(bot_id, msg)
        return "ok", 200

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
            if group["admin_enabled"] and (group["group_admins"] or group["bot_owner"]):
                base_msg = f'You said a banned word. {bt["message"] or ""} '
                loci = []
                user_ids = []
                pos = len(base_msg)

                ids_to_ping = []
                if group["group_owner"]:
                    ids_to_ping.append(group["group_owner"])
                ids_to_ping.extend(group["group_admins"])

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
