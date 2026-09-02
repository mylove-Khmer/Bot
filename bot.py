import os
import sqlite3
from datetime import datetime, timedelta
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ================= ការកំណត់របស់អ្នក (Config) =================
BOT_TOKEN = "8249755354:AAHkrWuCaZN1OMTl8GkAADomLkCoxyBAuX0"[cite: 1, 2]
ADMIN_ID = 8384547912[cite: 1, 2]
ADMIN_USERNAME = "@KinHav12"[cite: 1, 2]
ADMIN_CONTACT_LINK = "https://t.me/KinHav12"
# =========================================================

# តារាងតម្លៃ កញ្ចប់សេវាកម្ម និងឈ្មោះ File រូបភាព QR ដាច់ដោយឡែកពីគ្នា
PACKAGES = {
    "plan_30": {"name": "១ ខែ", "days": 30, "price": "2$", "qr": "qr_1m.jpg"},
    "plan_150": {"name": "៥ ខែ", "days": 150, "price": "6$", "qr": "qr_5m.jpg"},
    "plan_365": {"name": "១ ឆ្នាំ", "days": 365, "price": "12$", "qr": "qr_1y.jpg"},
    "plan_730": {"name": "២ ឆ្នាំ", "days": 730, "price": "20$", "qr": "qr_2y.jpg"},
}

def init_db():
    conn = sqlite3.connect("subscribers.db")[cite: 1, 2]
    cursor = conn.cursor()[cite: 1, 2]
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            expire_date TEXT,
            has_used_trial INTEGER DEFAULT 0
        )
    """)[cite: 1, 2]
    conn.commit()[cite: 1, 2]
    conn.close()[cite: 1, 2]

# កត់ត្រាភ្ញៀវចូលប្រើប្រព័ន្ធ
def record_user(user_id: int):
    conn = sqlite3.connect("subscribers.db")[cite: 2]
    cursor = conn.cursor()[cite: 2]
    cursor.execute("""
        INSERT OR IGNORE INTO users (user_id, expire_date, has_used_trial)
        VALUES (?, NULL, 0)
    """, (user_id,))[cite: 2]
    conn.commit()[cite: 2]
    conn.close()[cite: 2]

# ពិនិត្យមើលសិទ្ធិ VIP
def is_vip(user_id: int) -> bool:
    if user_id == ADMIN_ID:[cite: 1, 2]
        return True[cite: 1, 2]
    conn = sqlite3.connect("subscribers.db")[cite: 1, 2]
    cursor = conn.cursor()[cite: 1, 2]
    cursor.execute("SELECT expire_date FROM users WHERE user_id = ?", (user_id,))[cite: 1, 2]
    row = cursor.fetchone()[cite: 1, 2]
    conn.close()[cite: 1, 2]

    if not row or not row[0]:[cite: 2]
        return False[cite: 1, 2]
    expire_date = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")[cite: 1, 2]
    return datetime.now() < expire_date[cite: 1, 2]

# បន្ថែមថ្ងៃ VIP
def add_vip(user_id: int, days: int):
    conn = sqlite3.connect("subscribers.db")[cite: 1, 2]
    cursor = conn.cursor()[cite: 1, 2]
    cursor.execute("SELECT expire_date FROM users WHERE user_id = ?", (user_id,))[cite: 1, 2]
    row = cursor.fetchone()[cite: 1, 2]

    now = datetime.now()[cite: 1, 2]
    if row and row[0]:[cite: 2]
        current_expire = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")[cite: 1, 2]
        start_from = current_expire if current_expire > now else now[cite: 1, 2]
    else:
        start_from = now[cite: 1, 2]

    new_expire = start_from + timedelta(days=days)[cite: 1, 2]
    cursor.execute("""
        INSERT INTO users (user_id, expire_date) 
        VALUES (?, ?) 
        ON CONFLICT(user_id) DO UPDATE SET expire_date=excluded.expire_date
    """, (user_id, new_expire.strftime("%Y-%m-%d %H:%M:%S")))[cite: 1, 2]
    conn.commit()[cite: 1, 2]
    conn.close()[cite: 1, 2]
    return new_expire.strftime("%Y-%m-%d %H:%M")

# មុខងារបើក Free ១ ថ្ងៃ
def claim_free_trial(user_id: int):
    conn = sqlite3.connect("subscribers.db")
    cursor = conn.cursor()
    cursor.execute("SELECT has_used_trial FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    if row and row[0] == 1:
        conn.close()
        return False, None

    expire_date = datetime.now() + timedelta(days=1)
    expire_str = expire_date.strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO users (user_id, expire_date, has_used_trial) 
        VALUES (?, ?, 1) 
        ON CONFLICT(user_id) DO UPDATE SET expire_date=excluded.expire_date, has_used_trial=1
    """, (user_id, expire_str))
    
    conn.commit()
    conn.close()
    return True, expire_date.strftime("%Y-%m-%d %H:%M")

# ស្ថិតិចំនួនអ្នកប្រើប្រាស់
def get_user_stats():
    conn = sqlite3.connect("subscribers.db")[cite: 2]
    cursor = conn.cursor()[cite: 2]
    cursor.execute("SELECT COUNT(*) FROM users")[cite: 2]
    total_users = cursor.fetchone()[0][cite: 2]
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")[cite: 2]
    cursor.execute("SELECT COUNT(*) FROM users WHERE expire_date > ?", (now_str,))[cite: 2]
    active_vip = cursor.fetchone()[0][cite: 2]
    conn.close()[cite: 2]
    return total_users, active_vip[cite: 2]

# ដំណើរការកូដតាម Piston API
def execute_code(language: str, code: str) -> str:
    url = "https://emkc.org/api/v2/piston/execute"[cite: 1, 2]
    payload = {
        "language": language,[cite: 1, 2]
        "version": "*",[cite: 1, 2]
        "files": [{"content": code}][cite: 1, 2]
    }
    try:
        res = requests.post(url, json=payload, timeout=20)[cite: 1, 2]
        data = res.json()[cite: 1, 2]
        output = data.get("run", {}).get("output", "")[cite: 1, 2]
        return output if output else "កូដដំណើរការជោគជ័យ (គ្មានលទ្ធផលបង្ហាញ)"
    except Exception as e:
        return f"កំហុសបច្ចេកទេស៖ {str(e)}"

# បង្ហាញប៊ូតុងកញ្ចប់តម្លៃ
async def send_plan_selection(update: Update, user_id: int):
    keyboard = [
        [
            InlineKeyboardButton("🎁 សាកល្បងឥតគិតថ្លៃ ១ ថ្ងៃ (Free 1 Day)", callback_data="claim_free_trial")
        ],
        [
            InlineKeyboardButton("📦 ១ ខែ (តម្លៃ ២$)", callback_data="buy_plan_30"),
            InlineKeyboardButton("🔥 ៥ ខែ (តម្លៃ ៦$)", callback_data="buy_plan_150")
        ],
        [
            InlineKeyboardButton("🔥 ១ ឆ្នាំ (តម្លៃ ១២$)", callback_data="buy_plan_365"),
            InlineKeyboardButton("🔥 ២ ឆ្នាំ (តម្លៃ ២០$)", callback_data="buy_plan_730")
        ],
        [
            InlineKeyboardButton("💬 ទំនាក់ទំនងអេដមីន (Contact Admin)", url=ADMIN_CONTACT_LINK)
        ]
    ]
    text = (
        "⚠️ **គណនីរបស់អ្នកមិនទាន់មានកញ្ចប់សេវាកម្មនៅឡើយទេ!**\n\n"
        "✨ លោកអ្នកអាចចុច **សាកល្បងឥតគិតថ្លៃ ១ ថ្ងៃ** ឬជ្រើសរើសកញ្ចប់បង់ប្រាក់ខាងក្រោម ដើម្បីដំណើរការកូដ៖"
    )
    if update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")[cite: 2]
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")[cite: 2]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id[cite: 1, 2]
    record_user(user_id)[cite: 2]
    
    if is_vip(user_id):[cite: 1, 2]
        await update.message.reply_text(
            "👋 **សូមស្វាគមន៍មកកាន់ប្រព័ន្ធដំណើរការកូដ!**\n\n"
            "លោកអ្នកជាសមាជិក VIP រួចរាល់ហើយ។ សូមផ្ញើកូដដែលអ្នកចង់ដំណើរការមកកាន់ទីនេះ (Python, JavaScript, PHP, C++, Java, C#...)",
            parse_mode="Markdown"
        )
    else:
        await send_plan_selection(update, user_id)[cite: 2]

# នៅពេលភ្ញៀវផ្ញើកូដចូលមក
async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id[cite: 1, 2]
    record_user(user_id)[cite: 2]
    if not is_vip(user_id):[cite: 1, 2]
        await send_plan_selection(update, user_id)[cite: 2]
        return[cite: 1, 2]

    context.user_data['code'] = update.message.text[cite: 1, 2]

    keyboard = [
        [
            InlineKeyboardButton("▶️ ដំណើរការកូដ", callback_data="action_run_code"),
            InlineKeyboardButton("⏹️ បញ្ឈប់ដំណើរការកូដ", callback_data="action_stop_code")
        ]
    ]
    await update.message.reply_text(
        "📥 **ទទួលបានកូដរបស់អ្នករួចរាល់ហើយ!**\n\n"
        "សូមចុចប៊ូតុងខាងក្រោមដើម្បីជ្រើសរើសដំណើរការ ឬបញ្ឈប់៖",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ទទួលរូបភាពវិក្កយបត្រ
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user[cite: 1, 2]
    record_user(user.id)[cite: 2]
    photo = update.message.photo[-1][cite: 1, 2]
    selected_plan = context.user_data.get("selected_plan", "មិនបានបញ្ជាក់")

    admin_keyboard = [
        [
            InlineKeyboardButton("✅ យល់ព្រម ១ ខែ (២$)", callback_data=f"adm_approve_{user.id}_30"),
            InlineKeyboardButton("🔥 យល់ព្រម ៥ ខែ (៦$)", callback_data=f"adm_approve_{user.id}_150")
        ],
        [
            InlineKeyboardButton("🔥 យល់ព្រម ១ ឆ្នាំ (១២$)", callback_data=f"adm_approve_{user.id}_365"),
            InlineKeyboardButton("🔥 យល់ព្រម ២ ឆ្នាំ (២០$)", callback_data=f"adm_approve_{user.id}_730")
        ],
        [
            InlineKeyboardButton("❌ បដិសេធ / បោះបង់", callback_data=f"adm_reject_{user.id}_0")
        ]
    ]

    await context.bot.send_photo(
        chat_id=ADMIN_ID,[cite: 1, 2]
        photo=photo.file_id,[cite: 1, 2]
        caption=(
            f"🔔 **មានភ្ញៀវផ្ញើវិក្កយបត្របង់ប្រាក់ថ្មី!**\n\n"
            f"👤 **ឈ្មោះភ្ញៀវ៖** {user.full_name}\n"
            f"🔗 **គណនី Telegram៖** @{user.username if user.username else 'គ្មាន'}\n"
            f"🆔 **លេខសម្គាល់ (ID)៖** `{user.id}`\n"
            f"📌 **កញ្ចប់ដែលបានជ្រើសរើស៖** {selected_plan}\n\n"
            "សូមអេដមីនពិនិត្យមើលរូបភាពវិក្កយបត្រ រួចចុចប៊ូតុងខាងក្រោមដើម្បីអនុម័ត៖"
        ),
        parse_mode="Markdown",[cite: 1, 2]
        reply_markup=InlineKeyboardMarkup(admin_keyboard)[cite: 1, 2]
    )

    await update.message.reply_text("⏳ **ទទួលបានរូបភាពវិក្កយបត្ររបស់អ្នករួចរាល់ហើយ!**\nសូមរង់ចាំអេដមីនពិនិត្យ និងបើកសិទ្ធិជូនក្នុងពេលបន្តិចទៀតនេះ...")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query[cite: 1, 2]
    data = query.data[cite: 1, 2]
    user_id = update.effective_user.id[cite: 1, 2]
    await query.answer()[cite: 1, 2]

    # ភ្ញៀវចុចយក Free Trial ១ ថ្ងៃ
    if data == "claim_free_trial":
        success, expire_time = claim_free_trial(user_id)
        if success:
            await query.edit_message_text(
                f"🎉 **អបអរសាទរ! លោកអ្នកទទួលបានសិទ្ធិប្រើប្រាស់ Free រយៈពេល ១ ថ្ងៃជោគជ័យ!**\n\n"
                f"⏰ ផុតកំណត់នៅវេលាម៉ោង៖ `{expire_time}`\n\n"
                "👉 ឥឡូវនេះ លោកអ្នកអាចផ្ញើកូដចូលមកដើម្បីដំណើរការបានភ្លាមៗ!",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                "⚠️ **លោកអ្នកធ្លាប់បានប្រើប្រាស់កញ្ចប់ Free ១ ថ្ងៃរួចរាល់ហើយ!**\n\n"
                "សូមធ្វើការជ្រើសរើសកញ្ចប់បង់ប្រាក់ ដើម្បីបន្តការដំណើរការកូដ។"
            )
            await send_plan_selection(update, user_id)[cite: 2]
        return

    # ភ្ញៀវចុចជ្រើសរើសកញ្ចប់ -> បង្ហាញរូបភាព QR តាមកញ្ចប់នោះ
    if data.startswith("buy_"):[cite: 2]
        plan_key = data.replace("buy_", "")[cite: 2]
        plan = PACKAGES.get(plan_key)[cite: 2]
        if plan:[cite: 2]
            context.user_data["selected_plan"] = f"កញ្ចប់ {plan['name']} (តម្លៃ {plan['price']})"
            caption = (
                f"🧾 **លោកអ្នកបានជ្រើសរើស៖ កញ្ចប់ {plan['name']}**\n"
                f"💰 **ចំនួនទឹកប្រាក់ត្រូវផ្ទេរ៖ {plan['price']}**\n"
                f"⏳ **រយៈពេលប្រើប្រាស់៖ {plan['days']} ថ្ងៃ**\n"
                f"🆔 **លេខសម្គាល់របស់អ្នក (ID)៖** `{user_id}`\n\n"
                "📲 សូម Scan រូបភាព QR Code ខាងលើដើម្បីទូទាត់ប្រាក់។\n"
                "📸 **ចំណាំ៖** ក្រោយផ្ទេរប្រាក់រួច សូមផ្ញើរូបភាពវិក្កយបត្រ (Slip) ចូលមកកាន់ទីនេះ ដើម្បីឱ្យអេដមីនបើកសិទ្ធិជូនភ្លាមៗ!"
            )
            keyboard = [
                [InlineKeyboardButton("💬 ទំនាក់ទំនងអេដមីនផ្ទាល់", url=ADMIN_CONTACT_LINK)]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            chat_id = query.message.chat_id[cite: 2]
            qr_file = plan["qr"]  # យករូបភាពដែលត្រូវគ្នានឹងកញ្ចប់នោះ

            if os.path.exists(qr_file):
                with open(qr_file, "rb") as photo:
                    await context.bot.send_photo(chat_id=chat_id, photo=photo, caption=caption, parse_mode="Markdown", reply_markup=reply_markup)
            else:
                await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode="Markdown", reply_markup=reply_markup)[cite: 2]
        return[cite: 2]

    # ផ្នែកគ្រប់គ្រងរបស់ Admin
    if data.startswith("adm_"):[cite: 1, 2]
        if user_id != ADMIN_ID:[cite: 1, 2]
            await query.answer("អ្នកមិនមែនជាអេដមីនទេ!", show_alert=True)[cite: 1, 2]
            return[cite: 1, 2]

        parts = data.split("_")[cite: 1, 2]
        action = parts[1][cite: 1, 2]
        target_id = int(parts[2])[cite: 1, 2]
        days = int(parts[3])[cite: 1, 2]

        if action == "approve":[cite: 1, 2]
            expire_date = add_vip(target_id, days)[cite: 1, 2]
            await query.edit_message_caption(
                caption=query.message.caption + f"\n\n🟢 **បានយល់ព្រម (Approve) រយៈពេល {days} ថ្ងៃ! ផុតកំណត់នៅថ្ងៃ៖ {expire_date}**",
                reply_markup=None[cite: 1, 2]
            )
            try:
                await context.bot.send_message(
                    chat_id=target_id,[cite: 1, 2]
                    text=f"🎉 **ការទូទាត់ប្រាក់របស់អ្នកត្រូវបានអេដមីនយល់ព្រមជោគជ័យ!**\n\n"
                         f"⏳ **កញ្ចប់សេវាកម្ម៖** {days} ថ្ងៃ\n"
                         f"📅 **ផុតកំណត់នៅថ្ងៃ៖** {expire_date}\n\n"
                         "ឥឡូវនេះ លោកអ្នកអាចផ្ញើកូដមកដំណើរការបានដោយសេរី!",
                    parse_mode="Markdown"[cite: 1, 2]
                )
            except Exception:[cite: 1, 2]
                pass[cite: 1, 2]

        elif action == "reject":[cite: 1, 2]
            await query.edit_message_caption(
                caption=query.message.caption + "\n\n🔴 **បានបដិសេធ / បោះបង់ការទូទាត់នេះ**",
                reply_markup=None[cite: 1, 2]
            )
            try:
                await context.bot.send_message(
                    chat_id=target_id,[cite: 1, 2]
                    text="❌ **ការទូទាត់ប្រាក់របស់អ្នកត្រូវបានបដិសេធ!**\n"
                         f"សូមពិនិត្យមើលវិក្កយបត្រឡើងវិញ ឬទាក់ទងមកកាន់អេដមីនផ្ទាល់៖ {ADMIN_USERNAME}"
                )
            except Exception:[cite: 1, 2]
                pass[cite: 1, 2]
        return[cite: 1, 2]

    # ភ្ញៀវចុច "⏹️ បញ្ឈប់ដំណើរការកូដ"
    if data == "action_stop_code":
        context.user_data.pop('code', None)
        await query.edit_message_text("⏹️ **កូដត្រូវបានបញ្ឈប់ និងលុបចេញពីប្រព័ន្ធដោយជោគជ័យ!**", parse_mode="Markdown")
        return

    # ភ្ញៀវចុច "▶️ ដំណើរការកូដ"
    if data == "action_run_code":
        if not is_vip(user_id):[cite: 1, 2]
            await query.edit_message_text("⚠️ **សមាជិកភាពរបស់អ្នកបានផុតកំណត់ហើយ!**\nសូមទាក់ទងអេដមីន ឬជ្រើសរើសកញ្ចប់ថ្មី។")
            return[cite: 1, 2]

        lang_keyboard = [
            [
                InlineKeyboardButton("🐍 Python", callback_data="run_python"),[cite: 1, 2]
                InlineKeyboardButton("🟨 JavaScript", callback_data="run_javascript")[cite: 1, 2]
            ],
            [
                InlineKeyboardButton("🐘 PHP", callback_data="run_php"),[cite: 1, 2]
                InlineKeyboardButton("⚡ C++", callback_data="run_cpp")[cite: 1, 2]
            ],
            [
                InlineKeyboardButton("☕ Java", callback_data="run_java"),[cite: 1, 2]
                InlineKeyboardButton("🔷 C#", callback_data="run_csharp")[cite: 1, 2]
            ],
            [
                InlineKeyboardButton("⏹️ បញ្ឈប់ / បោះបង់", callback_data="action_stop_code")
            ]
        ]
        await query.edit_message_text(
            "⚡ **សូមជ្រើសរើសភាសាកូដរបស់អ្នកដើម្បីដំណើរការ៖**",
            reply_markup=InlineKeyboardMarkup(lang_keyboard),
            parse_mode="Markdown"
        )
        return

    # ដំណើរការ Run កូដជាក់ស្ដែង
    if data.startswith("run_"):[cite: 1, 2]
        if not is_vip(user_id):[cite: 1, 2]
            await query.edit_message_text("⚠️ **សមាជិកភាពរបស់អ្នកបានផុតកំណត់ហើយ!**")
            return[cite: 1, 2]

        lang = data.replace("run_", "")[cite: 1, 2]
        code = context.user_data.get('code')[cite: 1, 2]

        if not code:[cite: 1, 2]
            await query.edit_message_text("⚠️ **មិនមានកូដក្នុងប្រព័ន្ធទេ សូមផ្ញើកូដឡើងវិញ។**")
            return[cite: 1, 2]

        await query.edit_message_text(f"⏳ កំពុងដំណើរការកូដជាភាសា `{lang}`...", parse_mode="Markdown")
        output = execute_code(lang, code)[cite: 1, 2]

        if len(output) > 3500:[cite: 1, 2]
            output = output[:3500] + "\n...[កាត់បន្ថយដោយសារលទ្ធផលវែងពេក]"

        user_name = query.from_user.full_name[cite: 1, 2]
        username = f"(@{query.from_user.username})" if query.from_user.username else ""[cite: 1, 2]

        result_text = (
            f"💻 **លទ្ធផលដំណើរការកូដ**\n"
            f"👤 **ម្ចាស់កូដ៖** {user_name} {username}\n"
            f"⚡ **ប្រភេទភាសា៖** `{lang.upper()}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"**📄 លទ្ធផល Output៖**\n"
            f"```\n{output}\n```"
        )
        await query.message.reply_text(result_text, parse_mode="Markdown")[cite: 1, 2]

# បញ្ជា /users សម្រាប់អេដមីនឆែកមើលចំនួនអ្នកប្រើ
async def admin_check_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:[cite: 2]
        return[cite: 2]
    
    total, active = get_user_stats()[cite: 2]
    expired = total - active[cite: 2]
    
    msg = (
        "📊 **ស្ថិតិអ្នកប្រើប្រាស់ Bot ទាំងអស់**\n\n"
        f"👥 ចំនួនអ្នកប្រើប្រាស់សរុប៖ **{total}** នាក់\n"
        f"🟢 សមាជិក VIP កំពុងដំណើរការ៖ **{active}** នាក់\n"
        f"⚪ សមាជិកធម្មតា / ផុតកំណត់៖ **{expired}** នាក់"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")[cite: 2]

if __name__ == "__main__":
    init_db()[cite: 1, 2]
    app = ApplicationBuilder().token(BOT_TOKEN).build()[cite: 1, 2]

    app.add_handler(CommandHandler("start", start))[cite: 1, 2]
    app.add_handler(CommandHandler("users", admin_check_users))[cite: 2]
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))[cite: 1, 2]
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code))
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("Bot កំពុងដំណើរការ...")[cite: 1, 2]
    app.run_polling()[cite: 1, 2]
