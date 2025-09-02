# modules/filters.py
# Admin check নেই; সবাই /filter, /delfilter ব্যবহার করতে পারবে
# ফিল্টারগুলো state.GROUP_SETTINGS[gid]["filters_cfg"]["filters"] এ সেভ হয়

import re
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot.apihelper import ApiTelegramException

from state import USER_GROUPS, GROUP_SETTINGS, PENDING_INPUT  # kept import (unused now, safe)

DEFAULT_FILTERS_CFG = {"filters": {}}
_BTN_RE = re.compile(r"\[([^\]]+)\]\(buttonurl://([^)]+)\)")

# ---- small utils ----
def _ensure_filters_defaults(gid: int):
    g = GROUP_SETTINGS[gid]
    cfg = g.get("filters_cfg")
    changed = False
    if not isinstance(cfg, dict):
        cfg = DEFAULT_FILTERS_CFG.copy(); changed = True
    elif "filters" not in cfg or not isinstance(cfg["filters"], dict):
        cfg["filters"] = {}; changed = True
    if changed:
        g2 = dict(g); g2["filters_cfg"] = cfg
        GROUP_SETTINGS[gid] = g2

def _mutate_filters(gid: int, fn):
    _ensure_filters_defaults(gid)
    g = GROUP_SETTINGS[gid]
    cfg = dict(g["filters_cfg"])
    fn(cfg)
    g2 = dict(g); g2["filters_cfg"] = cfg
    GROUP_SETTINGS[gid] = g2
    return cfg

def _parse_triggers(chunk: str):
    toks = [t.strip().lower() for t in re.split(r"[,\s]+", chunk or "") if t.strip()]
    out, seen = [], set()
    for t in toks:
        if t not in seen:
            seen.add(t); out.append(t)
    return out

def parse_buttons_input(text: str):
    rows, remaining, i = [], "", 0
    while i < len(text):
        m = _BTN_RE.search(text, i)
        if not m:
            remaining += text[i:]; break
        remaining += text[i:m.start()]
        seg = text[m.start():]
        line, rest = (seg.split("\n", 1) + [""])[:2]
        parts = [p.strip() for p in line.split("&&")]
        row = []
        for part in parts:
            mm = _BTN_RE.search(part)
            if mm:
                row.append((mm.group(1).strip(), mm.group(2).strip()))
        if row:
            rows.append(row)
        last_close = line.rfind(")")
        if last_close != -1 and last_close + 1 < len(line):
            remaining += line[last_close + 1:]
        remaining += "\n"
        i = m.start() + len(line)
        if rest:
            text = text[:i] + rest
    return remaining.strip(), rows

def render_buttons_kb(rows):
    if not rows:
        return None
    kb = InlineKeyboardMarkup()
    for row in rows:
        kb.add(*[InlineKeyboardButton(t, url=u) for (t, u) in row])
    return kb

# --- PM target selection storage: PERSIST in DB using GROUP_SETTINGS[0] ---
_PM_BUCKET_GID = 0
_PM_KEY = "_pm_targets"

def _pm_store() -> dict:
    root = GROUP_SETTINGS[_PM_BUCKET_GID]
    if _PM_KEY not in root or not isinstance(root.get(_PM_KEY), dict):
        new_root = dict(root)
        new_root[_PM_KEY] = {}
        GROUP_SETTINGS[_PM_BUCKET_GID] = new_root  # persists to DB
        return new_root[_PM_KEY]
    return root[_PM_KEY]

def set_pm_target(uid: int, gid: int):
    uid = int(uid); gid = int(gid)
    root = GROUP_SETTINGS[_PM_BUCKET_GID]
    store = dict(root.get(_PM_KEY) or {})
    store[str(uid)] = int(gid)
    new_root = dict(root, **{_PM_KEY: store})
    GROUP_SETTINGS[_PM_BUCKET_GID] = new_root  # persist

def get_pm_target(uid: int):
    store = _pm_store()
    val = store.get(str(int(uid)))
    return int(val) if val is not None else None

def ensure_pm_target(uid: int):
    groups = USER_GROUPS[int(uid)]
    if groups and len(groups) == 1:
        only_gid = next(iter(groups.keys()))
        set_pm_target(uid, only_gid)
        return only_gid
    return get_pm_target(uid)

# ---- safe edit helper ----
def _safe_edit_text(bot, text, chat_id, message_id, **kw):
    try:
        return bot.edit_message_text(text, chat_id, message_id, **kw)
    except ApiTelegramException as e:
        if "message is not modified" in str(e).lower():
            return
        raise
    except Exception as e:
        if "message is not modified" in str(e).lower():
            return
        raise

# ================== PUBLIC API (register) ==================
def register(bot):

    # ---------- /filters_group (PM) ----------
    @bot.message_handler(commands=['filters_group'], func=lambda m: m.chat.type == 'private')
    def filters_group_pm(m):
        uid = m.from_user.id
        groups = USER_GROUPS[uid]
        if not groups:
            bot.reply_to(m, "⚠️ First connect your group")
            return

        if len(groups) == 1:
            only_gid = next(iter(groups.keys()))
            set_pm_target(uid, only_gid)
            bot.reply_to(m, "✅ গ্রুপ সিলেক্ট হয়েছে। এখন এখানেই /filter, /filters, /delfilter ব্যবহার করুন।")
            return

        kb = InlineKeyboardMarkup()
        for gid, info in groups.items():
            kb.add(InlineKeyboardButton(info["title"], callback_data=f"fgrp:pick:{gid}"))
        bot.reply_to(m, "🔧 কোন গ্রুপে ফিল্টার ম্যানেজ করবেন সিলেক্ট করুন:", reply_markup=kb)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("fgrp:pick:"))
    def pick_group_cb(c):
        gid = int(c.data.split(":")[2]); uid = c.from_user.id
        set_pm_target(uid, gid)
        bot.answer_callback_query(c.id, "Selected!")
        text = (
            "✅ গ্রুপ সিলেক্ট হয়েছে।\n\n"
            "এখন এখানেই সেট করুন:\n"
            "• <code>/filter trigger1, trigger2 reply_text</code>\n"
            "• অথবা কোনো মেসেজে রিপ্লাই করে: <code>/filter trigger1, trigger2</code>\n\n"
            "বাটন: <code>[Google](buttonurl://https://google.com)</code> (এক সারি: <code>&&</code>)\n"
            "ভ্যার: <code>{MENTION}</code>, <code>{GROUPNAME}</code>"
        )
        try:
            _safe_edit_text(bot, text, c.message.chat.id, c.message.message_id, parse_mode="HTML")
        except Exception:
            bot.send_message(c.message.chat.id, text, parse_mode="HTML")

    # ---------- /filter (NO ADMIN CHECK) ----------
    @bot.message_handler(commands=['filter', 'setfilter'])
    def cmd_filter(m):
        if m.chat.type in ("group", "supergroup"):
            gid = m.chat.id
            chat_title = m.chat.title or str(gid)
        else:
            gid = ensure_pm_target(m.from_user.id)
            if not gid:
                bot.reply_to(m, "⚠️ First select your group", parse_mode="HTML")
                return
            chat_title = USER_GROUPS[m.from_user.id].get(gid, {}).get("title", "This Chat")

        _ensure_filters_defaults(gid)
        raw = m.text or ""

        if m.reply_to_message:
            parts = raw.split(None, 1)
            if len(parts) < 2:
                bot.reply_to(m, "ব্যবহার:\nরিপ্লাই করে দিন: <code>/filter trigger1, trigger2</code>", parse_mode="HTML")
                return
            triggers = _parse_triggers(parts[1])
            base_text = (m.reply_to_message.text or m.reply_to_message.caption or "").strip()
            if not base_text:
                bot.reply_to(m, "❌ রিপ্লাই করা মেসেজে কোনো টেক্সট/ক্যাপশন নেই।"); 
                return
            raw_text = base_text
        else:
            parts_once = raw.split(None, 1)
            after_cmd = parts_once[1] if len(parts_once) > 1 else ""
            if not after_cmd:
                bot.reply_to(m, "ব্যবহার:\n<code>/filter trigger1, trigger2 reply_text</code>", parse_mode="HTML")
                return

            if "," in after_cmd:
                last_comma = after_cmd.rfind(",")
                left = after_cmd[:last_comma]
                right = after_cmd[last_comma + 1:].lstrip()
                sp = right.find(" ")
                if sp == -1:
                    bot.reply_to(m, "ব্যবহার:\n<code>/filter t1, t2, t3, t4 reply_text</code>", parse_mode="HTML")
                    return
                last_trigger = right[:sp].strip()
                raw_text = right[sp + 1:].strip()
                trg_chunk = f"{left}, {last_trigger}"
                triggers = _parse_triggers(trg_chunk)
            else:
                p = raw.split(None, 2)
                if len(p) < 3:
                    bot.reply_to(m, "ব্যবহার:\n<code>/filter trigger reply_text</code>", parse_mode="HTML")
                    return
                triggers = _parse_triggers(p[1])
                raw_text = p[2].strip()

        if not triggers:
            bot.reply_to(m, "❌ কমপক্ষে একটি ট্রিগার দিন।")
            return

        raw_text = raw_text.replace("{GROUPNAME}", chat_title)
        msg_text, rows = parse_buttons_input(raw_text)

        def _set(cfg):
            cur = dict(cfg["filters"])
            for trg in triggers:
                cur[trg] = {"text": msg_text, "buttons": rows, "is_html": True}
            cfg["filters"] = cur
        _mutate_filters(gid, _set)

        bot.reply_to(
            m,
            "✅ <b>{}</b> এ {}টা ফিল্টার সেভ হয়েছে:\n{}".format(
                chat_title, len(triggers), ", ".join(f"<code>{t}</code>" for t in triggers)
            ),
            parse_mode="HTML",
        )

    # ---------- /filters (list) ----------
    @bot.message_handler(commands=['filters'])
    def cmd_filters(m):
        gid = m.chat.id if m.chat.type in ("group", "supergroup") else ensure_pm_target(m.from_user.id)
        if not gid:
            bot.reply_to(m, "⚠️ First select your group", parse_mode="HTML"); 
            return
        _ensure_filters_defaults(gid)
        items = GROUP_SETTINGS[gid]["filters_cfg"]["filters"]
        if not items:
            bot.reply_to(m, "🗂 কোনো ফিল্টার নেই।")
        else:
            lines = "\n".join([f"• <code>{t}</code>" for t in sorted(items.keys())])
            bot.reply_to(m, "🗂 <b>Filters</b>\n" + lines, parse_mode="HTML")

    # ---------- /delfilter (NO ADMIN CHECK; multiple ok) ----------
    @bot.message_handler(commands=['delfilter', 'delfilters'])
    def cmd_delfilter(m):
        if m.chat.type in ("group", "supergroup"):
            gid = m.chat.id
        else:
            gid = ensure_pm_target(m.from_user.id)
            if not gid:
                bot.reply_to(m, "⚠️ First select your group", parse_mode="HTML"); 
                return

        _ensure_filters_defaults(gid)
        parts = (m.text or "").split(None, 1)
        if len(parts) < 2 or not parts[1].strip():
            bot.reply_to(
                m,
                "ব্যবহার:\n<code>/delfilter trigger</code>\n<code>/delfilters trg1, trg2 trg3</code>",
                parse_mode="HTML",
            )
            return
        targets = _parse_triggers(parts[1])

        deleted = []
        def _del(cfg):
            cur = dict(cfg["filters"])
            for t in targets:
                if t in cur:
                    cur.pop(t, None); deleted.append(t)
            cfg["filters"] = cur
        _mutate_filters(gid, _del)

        if deleted:
            bot.reply_to(m, "🗑 ডিলিট হয়েছে:\n" + "\n".join([f"• <code>{t}</code>" for t in deleted]), parse_mode="HTML")
        else:
            bot.reply_to(m, "⚠️ মিল পাওয়া যায়নি।")

    # ---------- Group listener: trigger match ----------
    @bot.message_handler(
        content_types=['text', 'photo', 'video', 'document', 'animation'],
        func=lambda m: m.chat and m.chat.type in ("group", "supergroup")
    )
    def _filter_guard(m):
        gid = m.chat.id
        _ensure_filters_defaults(gid)
        items = GROUP_SETTINGS[gid]["filters_cfg"]["filters"]
        if not items:
            return
        txt = ((m.text or "") + " " + (m.caption or "")).lower().strip()
        if not txt:
            return

        for trg, resp in items.items():
            if trg in txt:
                out = (resp.get("text") or "")
                out = out.replace("{MENTION}", f"<a href='tg://user?id={m.from_user.id}'>{m.from_user.first_name}</a>")
                out = out.replace("{GROUPNAME}", m.chat.title or str(gid))
                kb = render_buttons_kb(resp.get("buttons") or [])
                try:
                    bot.reply_to(m, out, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=False)
                except Exception:
                    bot.reply_to(m, resp.get("text",""), reply_markup=kb, disable_web_page_preview=False)
                break
