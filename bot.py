import os
import sqlite3
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ================= ការកំណត់របស់អ្នក (Config) =================
BOT_TOKEN = "8249755354:AAHkrWuCaZN1OMTl8GkAADomLkCoxyBAuX0"
ADMIN_ID = 8384547912
ADMIN_USERNAME = "@KinHav12"
ADMIN_CONTACT_LINK = "https://t.me/KinHav12"
# =========================================================

# តារាងតម្លៃ កញ្ចប់សេវាកម្ម និងរូបភាព QR ទាំង ៤
PACKAGES = {
    "plan_30": {"name": "១ ខែ", "days": 30, "price": "2$", "qr": "qr_1m.jpg"},
    "plan_150": {"name": "៥ ខែ", "days": 150, "price": "6$", "qr": "qr_5m.jpg"},
    "plan_365": {"name": "១ ឆ្នាំ", "days": 365, "price": "12$", "qr": "qr_1y.jpg"},
    "plan_730": {"name": "២ ឆ្នាំ", "days": 730, "price": "20$", "qr": "qr_2y.jpg"},
}

# Web Server សម្រាប់ឆ្លើយតប Render Web Service Port
class SimpleHealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(b"Bot is alive and running!")

    def log_message(self, format, *args):
        return

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHealthCheckHandler)
    server.serve_forever()

def init_db():
    conn = sqlite3.connect("subscribers.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            expire_date TEXT,
            has_used_trial INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def record_user(user_id: int):
    conn = sqlite3.connect("subscribers.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO users (user_id, expire_date, has_used_trial)
        VALUES (?, NULL, 0)
    """, (user_id,))
    conn.commit()
    conn.close()

def is_vip(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    conn = sqlite3.connect("subscribers.db")
    cursor = conn.cursor()
    cursor.execute("SELECT expire_date FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row or not row[0]:
        return False
    expire_date = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
    return datetime.now() < expire_date

def add_vip(user_id: int, days: int):
    conn = sqlite3.connect("subscribers.db")
    cursor = conn.cursor()
    cursor.execute("SELECT expire_date FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    now = datetime.now()
    if row and row[0]:
        current_expire = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
        start_from = current_expire if current_expire > now else now
    else:
        start_from = now

    new_expire = start_from + timedelta(days=days)
    cursor.execute("""
        INSERT INTO users (user_id, expire_date) 
        VALUES (?, ?) 
        ON CONFLICT(user_id) DO UPDATE SET expire_date=excluded.expire_date
    """, (user_id, new_expire.strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    return new_expire.strftime("%Y-%m-%d %H:%M")

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

def get_user_stats():
    conn = sqlite3.connect("subscribers.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("SELECT COUNT(*) FROM users WHERE expire_date > ?", (now_str,))
    active_vip = cursor.fetchone()[0]
    conn.close()
    return total_users, active_vip

def execute_code(language: str, code: str) -> str:
    url = "https://emkc.org/api/v2/piston/execute"
    payload = {
        "language": language,
        "version": "*",
        "files": [{"content": code}]
    }
    try:
        res = requests.post(url, json=payload, timeout=20)
        data = res.json()
        output = data.get("run", {}).get("output", "")
        return output if output else "កូដដំណើរការជោគជ័យ (គ្មានលទ្ធផលបង្ហាញ)"
    except Exception as e:
        return f"កំហុសបច្ចេកទេស៖ {str(e)}"

async def send_plan_selection(update: Update, user_id: int):
    keyboard = [
        [InlineKeyboardButton("🎁 សាកល្បងឥតគិតថ្លៃ ១ ថ្ងៃ (Free 1 Day)", callback_data="claim_free_trial")],
        [
            InlineKeyboardButton("📦 ១ ខែ (តម្លៃ ២$)", callback_data="buy_plan_30"),
            InlineKeyboardButton("🔥 ៥ ខែ (តម្លៃ ៦$)", callback_data="buy_plan_150")
        ],
        [
            InlineKeyboardButton("🔥 ១ ឆ្នាំ (តម្លៃ ១២$)", callback_data="buy_plan_365"),
            InlineKeyboardButton("🔥 ២ ឆ្នាំ (តម្លៃ ២០$)", callback_data="buy_plan_730")
        ],
        [InlineKeyboardButton("💬 ទំនាក់ទំនងអេដមីន (Contact Admin)", url=ADMIN_CONTACT_LINK)]
    ]
    text = (
        "⚠️ **គណនីរបស់អ្នកមិនទាន់មានកញ្ចប់សេវាកម្មនៅឡើយទេ!**\n\n"
        "✨ លោកអ្នកអាចចុច **សាកល្បងឥតគិតថ្លៃ ១ ថ្ងៃ** ឬជ្រើសរើសកញ្ចប់បង់ប្រាក់ខាងក្រោម ដើម្បីដំណើរការកូដ៖"
    )
    if update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    record_user(user_id)
    
    if is_vip(user_id):
        await update.message.reply_text(
            "👋 **សូមស្វាគមន៍មកកាន់ប្រព័ន្ធដំណើរការកូដ!**\n\n"
            "លោកអ្នកជាសមាជិក VIP រួចរាល់ហើយ។ សូមផ្ញើអត្ថបទកូដ ឬផ្ញើជា **ឯកសារកូដ (File .py, .js, .php...)** ចូលមកទីនេះដើម្បីដំណើរការ។",
            parse_mode="Markdown"
        )
    else:
        await send_plan_selection(update, user_id)

# ទទួលកូដជាប្រភេទអត្ថបទ (Text)
async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    record_user(user_id)
    if not is_vip(user_id):
        await send_plan_selection(update, user_id)
        return

    context.user_data['code'] = update.message.text

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

# ទទួលកូដជាប្រភេទឯកសារ (Document / File)
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    record_user(user_id)
    if not is_vip(user_id):
        await send_plan_selection(update, user_id)
        return

    doc = update.message.document
    file_name = doc.file_name or "code_file"
    
    # ពិនិត្យមើលទំហំឯកសារ (កុំឱ្យលើសពី 5MB)
    if doc.file_size and doc.file_size > 5 * 1024 * 1024:
        await update.message.reply_text("⚠️ **ឯកសារនេះមានទំហំធំពេក!** សូមផ្ញើឯកសារកូដដែលមានទំហំតូចជាង 5MB។")
        return

    status_msg = await update.message.reply_text(f"⏳ កំពុងទាញយកឯកសារកូដ `{file_name}`...")
    
    try:
        tg_file = await context.bot.get_file(doc.file_id)
        downloaded_bytes = await tg_file.download_as_bytearray()
        code_content = downloaded_bytes.decode('utf-8', errors='ignore')
        
        context.user_data['code'] = code_content

        keyboard = [
            [
                InlineKeyboardButton("▶️ ដំណើរការកូដ", callback_data="action_run_code"),
                InlineKeyboardButton("⏹️ បញ្ឈប់ដំណើរការកូដ", callback_data="action_stop_code")
            ]
        ]
        await status_msg.edit_text(
            f"📄 **ទទួលបានឯកសារកូដ៖** `{file_name}` រួចរាល់ហើយ!\n\n"
            "សូមចុចប៊ូតុងខាងក្រោមដើម្បីជ្រើសរើសដំណើរការ ឬបញ្ឈប់៖",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ មិនអាចអានឯកសារនេះបានទេ៖ {str(e)}")

# ទទួលរូបភាពវិក្កយបត្របង់ប្រាក់
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    record_user(user.id)
    photo = update.message.photo[-1]
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
        [InlineKeyboardButton("❌ បដិសេធ / បោះបង់", callback_data=f"adm_reject_{user.id}_0")]
    ]

    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo.file_id,
        caption=(
            f"🔔 **មានភ្ញៀវផ្ញើវិក្កយបត្របង់ប្រាក់ថ្មី!**\n\n"
            f"👤 **ឈ្មោះភ្ញៀវ៖** {user.full_name}\n"
            f"🔗 **គណនី Telegram៖** @{user.username if user.username else 'គ្មាន'}\n"
            f"🆔 **លេខសម្គាល់ (ID)៖** `{user.id}`\n"
            f"📌 **កញ្ចប់ដែលបានជ្រើសរើស៖** {selected_plan}\n\n"
            "សូមអេដមីនពិនិត្យមើលរូបភាពវិក្កយបត្រ រួចចុចប៊ូតុងខាងក្រោមដើម្បីអនុម័ត៖"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(admin_keyboard)
    )

    await update.message.reply_text("⏳ **ទទួលបានរូបភាពវិក្កយបត្ររបស់អ្នករួចរាល់ហើយ!**\nសូមរង់ចាំអេដមីនពិនិត្យ និងបើកសិទ្ធិជូនក្នុងពេលបន្តិចទៀតនេះ...")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id
    await query.answer()

    if data == "claim_free_trial":
        success, expire_time = claim_free_trial(user_id)
        if success:
            await query.edit_message_text(
                f"🎉 **អបអរសាទរ! លោកអ្នកទទួលបានសិទ្ធិប្រើប្រាស់ Free រយៈពេល ១ ថ្ងៃជោគជ័យ!**\n\n"
                f"⏰ ផុតកំណត់នៅវេលាម៉ោង៖ `{expire_time}`\n\n"
                "👉 ឥឡូវនេះ លោកអ្នកអាចផ្ញើកូដ ឬឯកសារកូដចូលមកដើម្បីដំណើរការបានភ្លាមៗ!",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                "⚠️ **លោកអ្នកធ្លាប់បានប្រើប្រាស់កញ្ចប់ Free ១ ថ្ងៃរួចរាល់ហើយ!**\n\n"
                "សូមធ្វើការជ្រើសរើសកញ្ចប់បង់ប្រាក់ ដើម្បីបន្តការដំណើរការកូដ។"
            )
            await send_plan_selection(update, user_id)
        return

    if data.startswith("buy_"):
        plan_key = data.replace("buy_", "")
        plan = PACKAGES.get(plan_key)
        if plan:
            context.user_data["selected_plan"] = f"កញ្ចប់ {plan['name']} (តម្លៃ {plan['price']})"
            caption = (
                f"🧾 **លោកអ្នកបានជ្រើសរើស៖ កញ្ចប់ {plan['name']}**\n"
                f"💰 **ចំនួនទឹកប្រាក់ត្រូវផ្ទេរ៖ {plan['price']}**\n"
                f"⏳ **រយៈពេលប្រើប្រាស់៖ {plan['days']} ថ្ងៃ**\n"
                f"🆔 **លេខសម្គាល់របស់អ្នក (ID)៖** `{user_id}`\n\n"
                "📲 សូម Scan រូបភាព QR Code ខាងលើដើម្បីទូទាត់ប្រាក់។\n"
                "📸 **ចំណាំ៖** ក្រោយផ្ទេរប្រាក់រួច សូមផ្ញើរូបភាពវិក្កយបត្រ (Slip) ចូលមកកាន់ទីនេះ ដើម្បីឱ្យអេដមីនបើកសិទ្ធិជូនភ្លាមៗ!"
            )
            keyboard = [[InlineKeyboardButton("💬 ទំនាក់ទំនងអេដមីនផ្ទាល់", url=ADMIN_CONTACT_LINK)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            chat_id = query.message.chat_id
            qr_file = plan["qr"]

            if os.path.exists(qr_file):
                with open(qr_file, "rb") as photo:
                    await context.bot.send_photo(chat_id=chat_id, photo=photo, caption=caption, parse_mode="Markdown", reply_markup=reply_markup)
            else:
                await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode="Markdown", reply_markup=reply_markup)
        return

    if data.startswith("adm_"):
        if user_id != ADMIN_ID:
            await query.answer("អ្នកមិនមែនជាអេដមីនទេ!", show_alert=True)
            return

        parts = data.split("_")
        action = parts[1]
        target_id = int(parts[2])
        days = int(parts[3])

        if action == "approve":
            expire_date = add_vip(target_id, days)
            await query.edit_message_caption(
                caption=query.message.caption + f"\n\n🟢 **បានយល់ព្រម (Approve) រយៈពេល {days} ថ្ងៃ! ផុតកំណត់នៅថ្ងៃ៖ {expire_date}**",
                reply_markup=None
            )
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=f"🎉 **ការទូទាត់ប្រាក់របស់អ្នកត្រូវបានអេដមីនយល់ព្រមជោគជ័យ!**\n\n"
                         f"⏳ **កញ្ចប់សេវាកម្ម៖** {days} ថ្ងៃ\n"
                         f"📅 **ផុតកំណត់នៅថ្ងៃ៖** {expire_date}\n\n"
                         "ឥឡូវនេះ លោកអ្នកអាចផ្ញើកូដមកដំណើរការបានដោយសេរី!",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

        elif action == "reject":
            await query.edit_message_caption(
                caption=query.message.caption + "\n\n🔴 **បានបដិសេធ / បោះបង់ការទូទាត់នេះ**",
                reply_markup=None
            )
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text="❌ **ការទូទាត់ប្រាក់របស់អ្នកត្រូវបានបដិសេធ!**\n"
                         f"សូមពិនិត្យមើលវិក្កយបត្រឡើងវិញ ឬទាក់ទងមកកាន់អេដមីនផ្ទាល់៖ {ADMIN_USERNAME}"
                )
            except Exception:
                pass
        return

    if data == "action_stop_code":
        context.user_data.pop('code', None)
        await query.edit_message_text("⏹️ **កូដត្រូវបានបញ្ឈប់ និងលុបចេញពីប្រព័ន្ធដោយជោគជ័យ!**", parse_mode="Markdown")
        return

    if data == "action_run_code":
        if not is_vip(user_id):
            await query.edit_message_text("⚠️ **សមាជិកភាពរបស់អ្នកបានផុតកំណត់ហើយ!**\nសូមទាក់ទងអេដមីន ឬជ្រើសរើសកញ្ចប់ថ្មី។")
            return

        lang_keyboard = [
            [
                InlineKeyboardButton("🐍 Python", callback_data="run_python"),
                InlineKeyboardButton("🟨 JavaScript", callback_data="run_javascript")
            ],
            [
                InlineKeyboardButton("🐘 PHP", callback_data="run_php"),
                InlineKeyboardButton("⚡ C++", callback_data="run_cpp")
            ],
            [
                InlineKeyboardButton("☕ Java", callback_data="run_java"),
                InlineKeyboardButton("🔷 C#", callback_data="run_csharp")
            ],
            [InlineKeyboardButton("⏹️ បញ្ឈប់ / បោះបង់", callback_data="action_stop_code")]
        ]
        await query.edit_message_text(
            "⚡ **សូមជ្រើសរើសភាសាកូដរបស់អ្នកដើម្បីដំណើរការ៖**",
            reply_markup=InlineKeyboardMarkup(lang_keyboard),
            parse_mode="Markdown"
        )
        return

    if data.startswith("run_"):
        if not is_vip(user_id):
            await query.edit_message_text("⚠️ **សមាជិកភាពរបស់អ្នកបានផុតកំណត់ហើយ!**")
            return

        lang = data.replace("run_", "")
        code = context.user_data.get('code')

        if not code:
            await query.edit_message_text("⚠️ **មិនមានកូដក្នុងប្រព័ន្ធទេ សូមផ្ញើកូដឡើងវិញ។**")
            return

        await query.edit_message_text(f"⏳ កំពុងដំណើរការកូដជាភាសា `{lang}`...", parse_mode="Markdown")
        output = execute_code(lang, code)

        if len(output) > 3500:
            output = output[:3500] + "\n...[កាត់បន្ថយដោយសារលទ្ធផលវែងពេក]"

        user_name = query.from_user.full_name
        username = f"(@{query.from_user.username})" if query.from_user.username else ""

        result_text = (
            f"💻 **លទ្ធផលដំណើរការកូដ**\n"
            f"👤 **ម្ចាស់កូដ៖** {user_name} {username}\n"
            f"⚡ **ប្រភេទភាសា៖** `{lang.upper()}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"**📄 លទ្ធផល Output៖**\n"
            f"```\n{output}\n```"
        )
        await query.message.reply_text(result_text, parse_mode="Markdown")

async def admin_check_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    total, active = get_user_stats()
    expired = total - active
    
    msg = (
        "📊 **ស្ថិតិអ្នកប្រើប្រាស់ Bot ទាំងអស់**\n\n"
        f"👥 ចំនួនអ្នកប្រើប្រាស់សរុប៖ **{total}** នាក់\n"
        f"🟢 សមាជិក VIP កំពុងដំណើរការ៖ **{active}** នាក់\n"
        f"⚪ សមាជិកធម្មតា / ផុតកំណត់៖ **{expired}** នាក់"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

if __name__ == "__main__":
    init_db()
    
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("users", admin_check_users))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))  # ទទួល File ឯកសារកូដ
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code))
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("Bot កំពុងដំណើរការ...")
    app.run_polling()
