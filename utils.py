# utils.py
from datetime import datetime
from urllib.parse import quote_plus
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from state import USER_GROUPS, GROUP_SETTINGS

def is_user_admin(bot, chat_id: int, user_id: int) -> bool:
    try:
        st = bot.get_chat_member(chat_id, user_id).status
        return st in ("administrator", "creator")
    except Exception:
        return False

def register_group_for_user(uid: int, gid: int, title: str):
    USER_GROUPS.setdefault(uid, {})
    USER_GROUPS[uid][gid] = {"title": title}
    GROUP_SETTINGS.setdefault(gid, {
        "antispam": True, "antiflood": True, "goodbye": False, "alphabets": False,
        "captcha": False, "checks": False, "media": True, "porn": True, "warns": True,
        "night": False, "link": True, "deleting": False,
        "rules_url": "https://t.me/",
        "welcome_cfg": {"enabled": True, "mode": "always", "delete_last": False,
                        "text": "", "media": None, "buttons": []}
    })

def fmt_onoff(v: bool) -> str: return "✅" if v else "❌"

def welcome_cfg(gid: int) -> dict:
    return GROUP_SETTINGS.setdefault(gid, {}).setdefault("welcome_cfg", {
        "enabled": True, "mode": "always", "delete_last": False,
        "text": "", "media": None, "buttons": []
    })

def render_buttons_kb(button_rows):
    kb = InlineKeyboardMarkup()
    for row in button_rows:
        kb.add(*[InlineKeyboardButton(t, url=u) for (t, u) in row])
    return kb

# Url Buttons parser (supports Share:, rules)
def parse_buttons_input(s: str, rules_url: str):
    rows = []
    for line in s.strip().splitlines():
        parts = [p.strip() for p in line.split("&&")]
        row = []
        for item in parts:
            if " - " not in item: 
                continue
            t, u = [p.strip() for p in item.split(" - ", 1)]
            if u.lower() == "rules":
                u = rules_url
            elif u.lower().startswith("share:"):
                payload = u.split(":", 1)[1].strip()
                u = f"https://t.me/share/url?text={quote_plus(payload)}"
            row.append((t, u))
        if row: rows.append(row)
    return rows

def substitute_vars(text: str, user, chat_title: str, rules_url: str):
    now = datetime.now()
    mention_html = f'<a href="tg://user?id={user.id}">{(user.first_name or "User")}</a>'
    repl = {
        "{ID}": str(user.id),
        "{NAME}": user.first_name or "",
        "{SURNAME}": user.last_name or "",
        "{NAMESURNAME}": f"{user.first_name or ''} {user.last_name or ''}".strip(),
        "{MENTION}": mention_html,
        "{LANG}": user.language_code or "",
        "{DATE}": now.strftime("%Y-%m-%d"),
        "{TIME}": now.strftime("%H:%M"),
        "{WEEKDAY}": now.strftime("%A"),
        "{USERNAME}": (user.username and f"@{user.username}") or "",
        "{GROUPNAME}": chat_title,
        "{RULES}": rules_url,
    }
    for k, v in repl.items():
        text = text.replace(k, v)
    return text
