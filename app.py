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

# -------------------------
# HELP REGISTRY
# -------------------------

# Base commands can never be disabled.
# Addon commands can be toggled with !enable/!disable <commandname>.

BASE_HELP = {
    "owner": [
        ("!OWNERME!!!", "Claim ownership of the bot (if unclaimed)"),
        ("!FALLENOWNER", "Abdicate bot ownership"),
        ("!disable", "Disable the entire bot"),
        ("!enable", "Re-enable the entire bot"),
        ("!reset", "Reset all group data"),
    ],
    "admin": [
        ("!admin @Name", "Add a bot admin (saves their name)"),
        ("!deladmin <userid>", "Remove a bot admin"),
        ("!nameset <name>", "Update your own stored display name"),
    ],
    "general": [
        ("!userid", "Show your user ID"),
        ("!help", "Show this help menu"),
    ]
}

# Addon commands registry: name -> {description, section}
ADDON_COMMANDS = {}

def register_addon(name, description, section="general"):
    ADDON_COMMANDS[name] = {"description": description, "section": section}

register_addon("joinmessage", "Set the join message (!joinmessage <msg>)", section="admin")
register_addon("addtrigger", "Add a trigger (!addtrigger \"word\" <response>)", section="admin")
register_addon("removetrigger", "Remove a trigger (!removetrigger <id>)", section="admin")
register_addon("listtriggers", "List all triggers (!listtriggers)", section="general")
register_addon("addbadtrigger", "Add a bad word trigger (!addbadtrigger \"word\" [msg])", section="admin")
register_addon("removebad", "Remove a bad trigger (!removebad <id>)", section="admin")
register_addon("listbad", "List all bad triggers (!listbad)", section="general")

# Base command names — these can never be disabled
BASE_COMMAND_NAMES = {
    "ownerme", "fallenowner", "disable", "enable",
    "reset", "admin", "deladmin", "nameset", "userid", "help"
}

# -------------------------
# BOT UTILITIES
# -------------------------

def send_message(bot_id, text, mentions=None):
    if not bot_id:
        print("[ERROR] send_message called with no bot_id — ignoring.")
        return
    signature = "\u200B"
    payload = {"bot_id": bot_id, "text": text + signature}
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
        s.replace("\u201C", "\"").replace("\u201D", "\"").replace("\u201E", "\"")
         .replace("\u201F", "\"").replace("\u00AB", "\"").replace("\u00BB", "\"")
         .replace("\u2033", "\"").replace("\u2018", "'").replace("\u2019", "'")
         .replace("\u201A", "'").replace("\u2032", "'")
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

def strip_at(name: str) -> str:
    return name.lstrip("@").strip()

def is_single_word(s: str) -> bool:
    return len(s.split()) == 1

def is_command_enabled(group, command_name):
    if command_name in BASE_COMMAND_NAMES:
        return True
    return command_name not in group.get("disabled_commands", [])

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
# GROUP DEFAULTS
# -------------------------

GROUP_DEFAULTS = {
    "bot_owner": None,
    "bot_admins": [],
    "admin_names": {},
    "join_message": "Welcome to the group!",
    "triggers": [],
    "bad_triggers": [],
    "bot_enabled": True,
    "disabled_commands": []
}

def ensure_group(group_data, group_id):
    if group_id not in group_data:
        group_data[group_id] = {}
    group = group_data[group_id]
    changed = False
    for key, default in GROUP_DEFAULTS.items():
        if key not in group:
            group[key] = type(default)() if isinstance(default, (dict, list)) else default
            changed = True
    return group, changed

# -------------------------
# PERMISSION CHECK
# -------------------------

def has_permission(group, sender_id):
    if sender_id == group.get("bot_owner"):
        return True
    if sender_id in group.get("bot_admins", []):
        return True
    return False

# -------------------------
# HELP MENU BUILDER
# -------------------------

def build_help_menu(group):
    disabled = group.get("disabled_commands", [])
    lines = ["📘 Help Menu", ""]

    lines.append("━━ BASE COMMANDS ━━")
    lines.append("")
    for section, label in [("owner", "👑 Owner"), ("admin", "🛠️ Admin"), ("general", "🙋 General")]:
        entries = BASE_HELP.get(section, [])
        if entries:
            lines.append(f"{label}:")
            for cmd, desc in entries:
                lines.append(f"  {cmd} — {desc}")
            lines.append("")

    lines.append("━━ ADDON COMMANDS ━━")
    lines.append("")

    enabled_by_section  = {"owner": [], "admin": [], "general": []}
    disabled_by_section = {"owner": [], "admin": [], "general": []}

    for name, info in ADDON_COMMANDS.items():
        bucket = disabled_by_section if name in disabled else enabled_by_section
        bucket[info["section"]].append(info["description"])

    lines.append("✅ ENABLED:")
    any_enabled = False
    for section, label in [("owner", "👑 Owner"), ("admin", "🛠️ Admin"), ("general", "🙋 General")]:
        if enabled_by_section[section]:
            any_enabled = True
            lines.append(f"  {label}:")
            for desc in enabled_by_section[section]:
                lines.append(f"    {desc}")
    if not any_enabled:
        lines.append("  (none)")
    lines.append("")

    lines.append("❌ DISABLED:")
    any_disabled = False
    for section, label in [("owner", "👑 Owner"), ("admin", "🛠️ Admin"), ("general", "🙋 General")]:
        if disabled_by_section[section]:
            any_disabled = True
            lines.append(f"  {label}:")
            for desc in disabled_by_section[section]:
                lines.append(f"    {desc}")
    if not any_disabled:
        lines.append("  (none)")

    return "\n".join(lines)

# -------------------------
# WEBHOOK
# -------------------------

@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()

    # Always load fresh data from JSONBin
    data_root = load_data()
    group_data = data_root.get("groups", {})

    bot_id      = data.get("bot", {}).get("id") or data.get("bot_id")
    group_id    = str(data.get("group_id"))
    sender_id   = data.get("sender_id")
    sender_type = data.get("sender_type")
    sender_name = data.get("name", "")
    text        = normalize_text((data.get("text") or "").strip())
    lowered     = text.lower()

    # Safety: bail if no bot_id
    if not bot_id:
        print(f"[ERROR] No bot_id in payload for group {group_id} — ignoring.")
        return "ok", 200

    # Ignore bot's own messages
    if text.endswith("\u200B"):
        return "ok", 200

    # Ensure group exists with all defaults
    group, changed = ensure_group(group_data, group_id)
    if changed:
        save_data({"groups": group_data})

    # If bot is disabled, only allow !enable
    if not group["bot_enabled"] and lowered != "!enable":
        return "ok", 200

    # System join messages
    if sender_type == "system" and "has joined the group" in text:
        if is_command_enabled(group, "joinmessage"):
            send_message(bot_id, group["join_message"])
        return "ok", 200

    # -------------------------
    # OWNER CLAIM
    # -------------------------

    if text == "!OWNERME!!!":
        if group["bot_owner"] is None:
            group["bot_owner"] = sender_id
            group["admin_names"][sender_id] = sender_name
            save_data({"groups": group_data})
            send_message(bot_id, f"You are now the bot owner, {sender_name}!")
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
    # WHOLE-BOT ENABLE / DISABLE
    # -------------------------

    if lowered == "!enable":
        if has_permission(group, sender_id):
            group["bot_enabled"] = True
            save_data({"groups": group_data})
            send_message(bot_id, "Bot re-enabled.")
        else:
            send_message(bot_id, "You don't have permission to enable the bot.")
        return "ok", 200

    if lowered == "!disable":
        if has_permission(group, sender_id):
            group["bot_enabled"] = False
            save_data({"groups": group_data})
            send_message(bot_id, "Bot disabled. Only !enable will work now.")
        else:
            send_message(bot_id, "You don't have permission to disable the bot.")
        return "ok", 200

    # -------------------------
    # ENABLE / DISABLE ADDON COMMAND
    # -------------------------

    if lowered.startswith("!enable "):
        if has_permission(group, sender_id):
            cmd = lowered[8:].strip()
            if cmd in BASE_COMMAND_NAMES:
                send_message(bot_id, f"'{cmd}' is a base command and cannot be toggled.")
            elif cmd not in ADDON_COMMANDS:
                send_message(bot_id, f"Unknown addon command '{cmd}'. Check !help for names.")
            elif cmd not in group["disabled_commands"]:
                send_message(bot_id, f"'{cmd}' is already enabled.")
            else:
                group["disabled_commands"].remove(cmd)
                save_data({"groups": group_data})
                send_message(bot_id, f"Command '{cmd}' enabled.")
        else:
            send_message(bot_id, "You don't have permission to enable commands.")
        return "ok", 200

    if lowered.startswith("!disable "):
        if has_permission(group, sender_id):
            cmd = lowered[9:].strip()
            if cmd in BASE_COMMAND_NAMES:
                send_message(bot_id, f"'{cmd}' is a base command and cannot be disabled.")
            elif cmd not in ADDON_COMMANDS:
                send_message(bot_id, f"Unknown addon command '{cmd}'. Check !help for names.")
            elif cmd in group["disabled_commands"]:
                send_message(bot_id, f"'{cmd}' is already disabled.")
            else:
                group["disabled_commands"].append(cmd)
                save_data({"groups": group_data})
                send_message(bot_id, f"Command '{cmd}' disabled.")
        else:
            send_message(bot_id, "You don't have permission to disable commands.")
        return "ok", 200

    # -------------------------
    # ADD BOT ADMIN
    # -------------------------

    if lowered.startswith("!admin ") and has_permission(group, sender_id):
        raw  = text[7:].strip()
        name = strip_at(raw)
        uid  = None

        # Pull user ID from mention attachment
        for att in data.get("attachments", []):
            if att.get("type") == "mentions" and att.get("user_ids"):
                uid = str(att["user_ids"][0])
                break

        if not uid:
            send_message(bot_id, "Could not detect a user ID. Make sure you @mention them.")
        elif uid in group["bot_admins"]:
            send_message(bot_id, f"{name} is already a bot admin.")
        else:
            group["bot_admins"].append(uid)
            group["admin_names"][uid] = name
            save_data({"groups": group_data})
            send_message(bot_id, f"Added bot admin: {name} (ID: {uid})")
        return "ok", 200

    if lowered == "!admin" and has_permission(group, sender_id):
        send_message(bot_id, "Usage: !admin @Username")
        return "ok", 200

    # -------------------------
    # REMOVE BOT ADMIN
    # -------------------------

    if lowered.startswith("!deladmin") and has_permission(group, sender_id):
        uid = text[9:].strip()
        if not uid:
            send_message(bot_id, "Usage: !deladmin <user_id>")
        elif uid in group["bot_admins"]:
            group["bot_admins"].remove(uid)
            name = group["admin_names"].pop(uid, uid)
            save_data({"groups": group_data})
            send_message(bot_id, f"Removed bot admin: {name}")
        else:
            send_message(bot_id, "That user is not a bot admin.")
        return "ok", 200

    # -------------------------
    # NAMESET
    # -------------------------

    if lowered.startswith("!nameset") and has_permission(group, sender_id):
        new_name = text[8:].strip()
        if not new_name:
            send_message(bot_id, "Usage: !nameset <your display name>")
        else:
            group["admin_names"][sender_id] = new_name
            save_data({"groups": group_data})
            send_message(bot_id, f"Your display name has been set to: {new_name}")
        return "ok", 200

    # -------------------------
    # RESET GROUP
    # -------------------------

    if lowered == "!reset" and sender_id == group.get("bot_owner"):
        group_data[group_id] = {
            k: (type(v)() if isinstance(v, (dict, list)) else v)
            for k, v in GROUP_DEFAULTS.items()
        }
        save_data({"groups": group_data})
        send_message(bot_id, "Group data has been reset.")
        return "ok", 200

    # -------------------------
    # JOIN MESSAGE
    # -------------------------

    if lowered.startswith("!joinmessage") and has_permission(group, sender_id):
        if not is_command_enabled(group, "joinmessage"):
            return "ok", 200
        msg = text[12:].strip()
        if not msg:
            send_message(bot_id, "Usage: !joinmessage <message>")
        else:
            group["join_message"] = msg
            save_data({"groups": group_data})
            send_message(bot_id, f'Join message updated: "{group["join_message"]}"')
        return "ok", 200

    # -------------------------
    # ADD TRIGGER
    # -------------------------

    if lowered.startswith("!addtrigger") and has_permission(group, sender_id):
        if not is_command_enabled(group, "addtrigger"):
            return "ok", 200
        if len(group["triggers"]) >= 20:
            send_message(bot_id, "Trigger limit reached (20).")
        else:
            phrase, response = parse_addtrigger(text)
            if phrase and response:
                if not is_single_word(phrase):
                    send_message(bot_id, "Triggers must be a single word.")
                else:
                    new_word = phrase.lower()
                    conflict = next(
                        (t["word"] for t in group["triggers"]
                         if t["word"].lower() == new_word
                         or t["word"].lower() in new_word
                         or new_word in t["word"].lower()),
                        None
                    )
                    if conflict:
                        send_message(bot_id, f'Cannot add "{phrase}" — overlaps with "{conflict}".')
                    else:
                        next_id = (max((t["id"] for t in group["triggers"]), default=0) + 1)
                        group["triggers"].append({"id": next_id, "word": phrase, "response": response})
                        save_data({"groups": group_data})
                        send_message(bot_id, f'Trigger "{phrase}" added with ID {next_id}.')
            else:
                send_message(bot_id, 'Usage: !addtrigger "word" <response>')
        return "ok", 200

    # -------------------------
    # LIST TRIGGERS
    # -------------------------

    if lowered == "!listtriggers":
        if not is_command_enabled(group, "listtriggers"):
            return "ok", 200
        if group["triggers"]:
            lines = [f"  {t['id']}: \"{t['word']}\" → {t['response']}" for t in group["triggers"]]
            send_message(bot_id, "Triggers:\n" + "\n".join(lines))
        else:
            send_message(bot_id, "No triggers set.")
        return "ok", 200

    # -------------------------
    # REMOVE TRIGGER
    # -------------------------

    if lowered.startswith("!removetrigger") and has_permission(group, sender_id):
        if not is_command_enabled(group, "removetrigger"):
            return "ok", 200
        try:
            tid = int(text[14:].strip())
            before = len(group["triggers"])
            group["triggers"] = [t for t in group["triggers"] if t["id"] != tid]
            if len(group["triggers"]) < before:
                save_data({"groups": group_data})
                send_message(bot_id, f"Trigger {tid} removed.")
            else:
                send_message(bot_id, "Invalid trigger ID.")
        except:
            send_message(bot_id, "Usage: !removetrigger <id>")
        return "ok", 200

    # -------------------------
    # ADD BAD TRIGGER
    # -------------------------

    if lowered.startswith("!addbadtrigger") and has_permission(group, sender_id):
        if not is_command_enabled(group, "addbadtrigger"):
            return "ok", 200
        if len(group["bad_triggers"]) >= 30:
            send_message(bot_id, "Bad trigger limit reached (30).")
        else:
            word, msg = parse_addbadtrigger(text)
            if word:
                if not is_single_word(word):
                    send_message(bot_id, "Bad triggers must be a single word.")
                else:
                    new_word = word.lower()
                    conflict = next(
                        (bt["word"] for bt in group["bad_triggers"]
                         if bt["word"].lower() == new_word
                         or bt["word"].lower() in new_word
                         or new_word in bt["word"].lower()),
                        None
                    )
                    if conflict:
                        send_message(bot_id, f'Cannot add "{word}" — overlaps with "{conflict}".')
                    else:
                        next_id = (max((t["id"] for t in group["bad_triggers"]), default=0) + 1)
                        group["bad_triggers"].append({"id": next_id, "word": word, "message": msg})
                        save_data({"groups": group_data})
                        send_message(bot_id, f'Bad trigger "{word}" added with ID {next_id}.')
            else:
                send_message(bot_id, 'Usage: !addbadtrigger "word" [optional message]')
        return "ok", 200

    # -------------------------
    # LIST BAD TRIGGERS
    # -------------------------

    if lowered == "!listbad":
        if not is_command_enabled(group, "listbad"):
            return "ok", 200
        if group["bad_triggers"]:
            lines = [f"  {t['id']}: \"{t['word']}\" → {t['message'] or '(no message)'}" for t in group["bad_triggers"]]
            send_message(bot_id, "Bad triggers:\n" + "\n".join(lines))
        else:
            send_message(bot_id, "No bad triggers set.")
        return "ok", 200

    # -------------------------
    # REMOVE BAD TRIGGER
    # -------------------------

    if lowered.startswith("!removebad") and has_permission(group, sender_id):
        if not is_command_enabled(group, "removebad"):
            return "ok", 200
        try:
            tid = int(text[10:].strip())
            before = len(group["bad_triggers"])
            group["bad_triggers"] = [t for t in group["bad_triggers"] if t["id"] != tid]
            if len(group["bad_triggers"]) < before:
                save_data({"groups": group_data})
                send_message(bot_id, f"Bad trigger {tid} removed.")
            else:
                send_message(bot_id, "Invalid bad trigger ID.")
        except:
            send_message(bot_id, "Usage: !removebad <id>")
        return "ok", 200

    # -------------------------
    # USER ID
    # -------------------------

    if lowered == "!userid":
        send_message(bot_id, f"Your user ID is: {sender_id}")
        return "ok", 200

    # -------------------------
    # HELP MENU
    # -------------------------

    if lowered == "!help":
        send_message(bot_id, build_help_menu(group))
        return "ok", 200

    # -------------------------
    # NORMAL TRIGGERS
    # -------------------------

    if sender_type == "user" and is_command_enabled(group, "addtrigger"):
        words_in_message = lowered.split()
        for t in group["triggers"]:
            if t["word"].lower() in words_in_message:
                send_message(bot_id, t["response"])
                break  # Only fire one trigger per message

    # -------------------------
    # BAD TRIGGERS
    # -------------------------

    if is_command_enabled(group, "addbadtrigger"):
        words_in_message = lowered.split()
        for bt in group["bad_triggers"]:
            if bt["word"].lower() in words_in_message:
                # Build admin ping list
                admins_to_ping = []
                if group.get("bot_owner"):
                    admins_to_ping.append(group["bot_owner"])
                for uid in group.get("bot_admins", []):
                    if uid not in admins_to_ping:
                        admins_to_ping.append(uid)

                if admins_to_ping:
                    custom_msg = (bt["message"] or "").strip()
                    prefix = f"Banned word detected. {custom_msg} Alerting: ".strip() + " "

                    loci     = []
                    user_ids = []
                    pos      = len(prefix)
                    full_msg = prefix

                    for idx, uid in enumerate(admins_to_ping):
                        name = group["admin_names"].get(uid, f"Admin{idx+1}")
                        if idx > 0:
                            full_msg += ", "
                            pos += 2
                        loci.append([pos, len(name)])
                        user_ids.append(uid)
                        full_msg += name
                        pos += len(name)

                    send_message(bot_id, full_msg,
                                 mentions={"loci": loci, "user_ids": user_ids})
                elif bt["message"]:
                    send_message(bot_id, bt["message"])
                break  # Only fire one bad trigger per message

    return "ok", 200
