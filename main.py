# main.py
# Run: pip install pyTelegramBotAPI
# BOT_TOKEN env var set করুন, না হলে নিচের ডামি টোকেন বদলে দিন

import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from state import USER_GROUPS, GROUP_SETTINGS   # তোমার বিদ্যমান state.py
try:
    # utils.py তে থাকলে ব্যবহার করবো
    from utils import register_group_for_user
except Exception:
    register_group_for_user = None

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8218499502:AAEsLD_W_QO4WIz1yuAg-QF9fuIcmBDI-DY")
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ---------- Helpers ----------
def _link_user_group(user_id: int, gid: int, title: str):
    """
    USER_GROUPS-এ ইউজার↔গ্রুপ লিংক সেভ করে।
    utils.register_group_for_user থাকলে ওটা ইউজ করি,
    না থাকলে USER_GROUPS.connect() ট্রাই, সেটাও না থাকলে
    সরাসরি ডিকশনারিতে বসাই।
    """
    title = title or str(gid)
    if register_group_for_user:
        try:
            register_group_for_user(user_id, gid, title)
            return
        except Exception:
            pass
    try:
        USER_GROUPS.connect(user_id, gid, title)  # তোমার state.py তে থাকে
        return
    except Exception:
        pass
    # ফোলব্যাক: সরাসরি dict এ
    m = USER_GROUPS[user_id]
    m[int(gid)] = {"title": title}
    USER_GROUPS[user_id] = m

# ---------- START ----------
START_TEXT = "✫ 𝝜𝝚ⳐⳐ𝝤 ‌{mention} Ѡ𝝚Ⳑ𝗖𝝤𝝡𝝚 𝝩𝝤 𝝡Ƴ 𝝜𝝤𝝡𝝚 ✫"

@bot.message_handler(commands=['start'])
def start_cmd(m):
    u = bot.get_me().username

    # deep-link ?start=gid_... থাকলে, তবু প্রথমে স্টার্ট টেক্সটই দেখাবো
    mention = f"<a href='tg://user?id={m.from_user.id}'>{m.from_user.first_name}</a>"
    start_text = START_TEXT.replace("{mention}", mention)

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("➕ Add to Group", url=f"https://t.me/{u}?startgroup=true"))

    args = (m.text or "").split(maxsplit=1)
    if len(args) == 2 and args[1].startswith("gid_"):
        try:
            gid = int(args[1].replace("gid_", ""))
            info = USER_GROUPS[m.from_user.id].get(gid)
            # স্টার্ট টেক্সট পাঠাই
            bot.reply_to(m, start_text, parse_mode="HTML", reply_markup=kb)
            # চাইলে নিচের ব্লক অন করলে deep-link সেটিংস মেসেজও সাথে দেখাতে পারো:
            # if info:
            #     bot.send_message(
            #         m.chat.id,
            #         f"⚙️ <b>Settings</b>\nGroup: <b>{info['title']}</b>\n\n"
            #         "Filters manage in PM",
            #         parse_mode="HTML"
            #     )
            return
        except Exception:
            # কোনো কারণেই পার্স না হলে—ডিফল্ট স্টার্ট
            bot.reply_to(m, start_text, parse_mode="HTML", reply_markup=kb)
            return

    # ডিফল্ট স্টার্ট
    bot.reply_to(m, start_text, parse_mode="HTML", reply_markup=kb)

# ---------- CONNECT / SETTINGS ----------
@bot.message_handler(commands=['settings'])
def settings_cmd(m):
    """
    গ্রুপে /settings দিলে ইউজারের সাথে এই গ্রুপটা লিঙ্ক করে দিবো — admin লাগবে না।
    PM-এ দিলে লিঙ্কড গ্রুপ লিস্ট দেখাবো।
    """
    if m.chat.type in ("group", "supergroup"):
        _link_user_group(m.from_user.id, m.chat.id, m.chat.title or str(m.chat.id))
        u = bot.get_me().username
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔗 Open in PM", url=f"https://t.me/{u}?start=gid_{m.chat.id}"))
        bot.reply_to(m, "✅ Linked! নিচের বাটনে চাপ দিয়ে PM-এ ওপেন করুন।", reply_markup=kb)
        return

    # PM → গ্রুপ লিস্ট দেখাও
    groups = USER_GROUPS[m.from_user.id]
    if not groups:
        bot.reply_to(m, "কোনো গ্রুপ লিঙ্ক করা নেই।")
        return
    kb = InlineKeyboardMarkup()
    for gid, info in groups.items():
        kb.add(InlineKeyboardButton(info["title"], callback_data=f"pm_open:{gid}"))
    bot.reply_to(m, "👉 একটি গ্রুপ বেছে নিন:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("pm_open:"))
def pm_open_cb(c):
    gid = int(c.data.split(":")[1])
    info = USER_GROUPS[c.from_user.id].get(gid)
    if not info:
        bot.answer_callback_query(c.id, "এই গ্রুপটি লিঙ্ক করা নেই।")
        return
    bot.answer_callback_query(c.id, "Opened")
    bot.edit_message_text(
        f"⚙️ <b>Settings</b>\nGroup: <b>{info['title']}</b>\n\n"
        "Filters manage in PM",
        c.message.chat.id, c.message.message_id, parse_mode="HTML"
    )

@bot.message_handler(commands=['connect'])
def connect_cmd(m):
    """
    PM থেকে ম্যানুয়ালি `/connect -100xxxxxxxxxx` দিলে লিঙ্ক হবে।
    গ্রুপ/বট অ্যাডমিন হওয়া লাগবে না।
    """
    if m.chat.type not in ("private",):
        bot.reply_to(m, "এই কমান্ডটা PM-এ দিন", parse_mode="HTML")
        return
    parts = (m.text or "").split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(m, "use right format", parse_mode="HTML")
        return
    try:
        gid = int(parts[1])
    except Exception:
        bot.reply_to(m, "সঠিক group id দিন", parse_mode="HTML")
        return
    # টাইটেল জানা না থাকলেও লিঙ্ক করবো
    title = str(gid)
    try:
        ch = bot.get_chat(gid)
        title = getattr(ch, "title", None) or title
    except Exception:
        pass
    _link_user_group(m.from_user.id, gid, title)
    bot.reply_to(m, f"✅ Linked: <b>{title}</b> (ID: <code>{gid}</code>)\nNow select group", parse_mode="HTML")

# ---------- Register Filters module ----------
from modules.filters import register as register_filters
register_filters(bot)

print("Bot is running…")
bot.infinity_polling(
    allowed_updates=['message','callback_query','chat_member','my_chat_member','chat_join_request'],
    timeout=20, long_polling_timeout=20
)