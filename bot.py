import os
import sys
import time
import sqlite3
import threading
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ================= ការកំណត់របស់អ្នក (Config) =================
BOT_TOKEN = "8249755354:AAHkrWuCaZN1OMTl8GkAADomLkCoxyBAuX0"
ADMIN_ID = 8384547912
ADMIN_USERNAME = "@KinHav12"
ADMIN_CONTACT_LINK = "https://t.me/KinHav12"
# =========================================================

# ទុកសម្រាប់ផ្ទុក Process កូដដែលកំពុង Run របស់ភ្ញៀវតាម User ID
RUNNING_PROCESSES = {}

PACKAGES = {
    "plan_30": {"name": "១ ខែ", "days": 30, "price": "2$", "qr": "qr_1m.jpg"},
    "plan_150": {"name": "៥ ខែ", "days": 150, "price": "6$", "qr": "qr_5m.jpg"},
    "plan_365": {"name": "១ ឆ្នាំ", "days": 365, "price": "12$", "qr": "qr_1y.jpg"},
    "plan_730": {"name": "២ ឆ្នាំ", "days": 730, "price": "20$", "qr": "qr_2y.jpg"},
}

class SimpleHealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(b"Bot Host Manager is running 24/7!")

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
    cursor.execute("INSERT OR IGNORE INTO users (user_id, expire_date, has_used_trial) VALUES (?, NULL, 0)", (user_id,))
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
    return datetime.now() < datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")

def add_vip(user_id: int, days: int):
    conn = sqlite3.connect("subscribers.db")
    cursor = conn.cursor()
    cursor.execute("SELECT expire_date FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    now = datetime.now()
    start_from = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S") if row and row[0] and datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S") > now else now
    new_expire = start_from + timedelta(days=days)
    cursor.execute("INSERT INTO users (user_id, expire_date) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET expire_date=excluded.expire_date", (user_id, new_expire.strftime("%Y-%m-%d %H:%M:%S")))
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
    cursor.execute("INSERT INTO users (user_id, expire_date, has_used_trial) VALUES (?, ?, 1) ON CONFLICT(user_id) DO UPDATE SET expire_date=excluded.expire_date, has_used_trial=1", (user_id, expire_str))
    conn.commit()
    conn.close()
    return True, expire_date.strftime("%Y-%m-%d %H:%M")

def stop_user_process(user_id: int):
    if user_id in RUNNING_PROCESSES:
        proc = RUNNING_PROCESSES[user_id]
        try:
            proc.terminate()
            proc.kill()
        except Exception:
            pass
        del RUNNING_PROCESSES[user_id]
        return True
    return False

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
        [InlineKeyboardButton("💬 ទំនាក់ទំនងអេដមីន", url=ADMIN_CONTACT_LINK)]
    ]
    text = "⚠️ **គណនីរបស់អ្នកមិនទាន់មានកញ្ចប់សេវាកម្មនៅឡើយទេ!**\n\nសូមជ្រើសរើសកញ្ចប់ខាងក្រោម ដើម្បីបើកដំណើរការ Host Bot របស់អ្នក ២៤ ម៉ោង៖"
    if update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    record_user(user_id)
    if is_vip(user_id):
        await update.message.reply_text(
            "👋 **សូមស្វាគមន៍មកកាន់ប្រព័ន្ធ Host Bot 24 ម៉ោង!**\n\n"
            "លោកអ្នកជាសមាជិក VIP រួចរាល់ហើយ។ សូមផ្ញើ **File កូដ Bot របស់អ្នក (ឧ. bot.py, app.py)** មកកាន់ទីនេះ ដើម្បីឱ្យ Server បើកដំណើរការ Bot របស់អ្នកភ្លាមៗ!",
            parse_mode="Markdown"
        )
    else:
        await send_plan_selection(update, user_id)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    record_user(user_id)
    if not is_vip(user_id):
        await send_plan_selection(update, user_id)
        return

    doc = update.message.document
    file_name = doc.file_name or f"bot_{user_id}.py"
    
    # កំណត់ Absolute Path ត្រឹមត្រូវ កុំឱ្យជាន់ Folder
    base_dir = os.path.abspath("hosted_bots")
    user_dir = os.path.join(base_dir, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    file_path = os.path.join(user_dir, file_name)

    status_msg = await update.message.reply_text(f"⏳ កំពុងទទួល និងដំឡើងឯកសារ `{file_name}`...")
    try:
        tg_file = await context.bot.get_file(doc.file_id)
        await tg_file.download_to_drive(file_path)
        context.user_data['hosted_script'] = file_path

        keyboard = [
            [
                InlineKeyboardButton("▶️ ចាប់ផ្ដើមដំណើរការ Bot (Run)", callback_data="action_run_bot"),
                InlineKeyboardButton("⏹️ បញ្ឈប់ដំណើរការ Bot (Stop)", callback_data="action_stop_bot")
            ]
        ]
        await status_msg.edit_text(
            f"✅ **ទទួលបានឯកសារកូដ៖** `{file_name}` រួចរាល់!\n\n"
            "តើអ្នកចង់ចាប់ផ្ដើមបើកឱ្យ Bot របស់លោកអ្នកដំណើរការ ២៤ ម៉ោងដែរឬទេ?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ បរាជ័យក្នុងការទាញយកឯកសារ៖ {str(e)}")

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
        [InlineKeyboardButton("❌ បដិសេធ", callback_data=f"adm_reject_{user.id}_0")]
    ]
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo.file_id,
        caption=f"🔔 **វិក្កយបត្រថ្មី!**\n👤 ភ្ញៀវ៖ {user.full_name} (`{user.id}`)\n📌 កញ្ចប់៖ {selected_plan}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(admin_keyboard)
    )
    await update.message.reply_text("⏳ ទទួលបានវិក្កយបត្រហើយ! សូមរង់ចាំអេដមីនពិនិត្យ និងបើកសិទ្ធិជូន។")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id
    await query.answer()

    if data == "claim_free_trial":
        success, expire_time = claim_free_trial(user_id)
        if success:
            await query.edit_message_text(f"🎉 **អបអរសាទរ! ទទួលបានសិទ្ធិ Host Bot Free រយៈពេល ១ ថ្ងៃ!**\nផុតកំណត់នៅ៖ `{expire_time}`\n\nសូមផ្ញើ File កូដ Bot របស់អ្នកមកឥឡូវនេះ!", parse_mode="Markdown")
        else:
            await query.edit_message_text("⚠️ លោកអ្នកធ្លាប់បានប្រើប្រាស់កញ្ចប់ Free រួចរាល់ហើយ!")
            await send_plan_selection(update, user_id)
        return

    if data.startswith("buy_"):
        plan = PACKAGES.get(data.replace("buy_", ""))
        if plan:
            context.user_data["selected_plan"] = f"កញ្ចប់ {plan['name']} ({plan['price']})"
            caption = f"🧾 **កញ្ចប់ {plan['name']}**\n💰 តម្លៃ៖ {plan['price']}\n🆔 ID របស់អ្នក៖ `{user_id}`\n\n📲 សូម Scan QR ដើម្បីទូទាត់ រួចផ្ញើរូបភាពវិក្កយបត្រមកទីនេះ!"
            keyboard = [[InlineKeyboardButton("💬 ទំនាក់ទំនងអេដមីន", url=ADMIN_CONTACT_LINK)]]
            qr_file = plan["qr"]
            if os.path.exists(qr_file):
                with open(qr_file, "rb") as p:
                    await context.bot.send_photo(chat_id=query.message.chat_id, photo=p, caption=caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                await context.bot.send_message(chat_id=query.message.chat_id, text=caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("adm_"):
        if user_id != ADMIN_ID:
            return
        _, act, t_id, days = data.split("_")
        t_id, days = int(t_id), int(days)
        if act == "approve":
            exp = add_vip(t_id, days)
            await query.edit_message_caption(caption=query.message.caption + f"\n\n🟢 **យល់ព្រម {days} ថ្ងៃ! ផុតកំណត់៖ {exp}**")
            await context.bot.send_message(chat_id=t_id, text=f"🎉 **ការបង់ប្រាក់ត្រូវបានអនុម័ត!**\nរយៈពេល៖ {days} ថ្ងៃ\nផុតកំណត់៖ {exp}\n\nលោកអ្នកអាចផ្ញើ File Bot មកដំណើរការបានហើយ!")
        elif act == "reject":
            await query.edit_message_caption(caption=query.message.caption + "\n\n🔴 **បដិសេធការបង់ប្រាក់**")
        return

    # ចាប់ផ្ដើមដំណើរការ Bot របស់ភ្ញៀវ
    if data == "action_run_bot":
        if not is_vip(user_id):
            await query.edit_message_text("⚠️ សមាជិកភាពរបស់អ្នកបានផុតកំណត់ហើយ!")
            return

        script_path = context.user_data.get('hosted_script')
        if not script_path or not os.path.exists(script_path):
            await query.edit_message_text("⚠️ មិនមាន File កូដនៅក្នុងប្រព័ន្ធទេ សូមផ្ញើ File ឡើងវិញ។")
            return

        stop_user_process(user_id)

        try:
            work_dir = os.path.dirname(script_path)
            script_name = os.path.basename(script_path)

            proc = subprocess.Popen(
                [sys.executable, script_name],
                cwd=work_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            RUNNING_PROCESSES[user_id] = proc

            time.sleep(2)
            poll = proc.poll()

            if poll is not None:
                _, stderr = proc.communicate()
                error_msg = stderr.strip() if stderr else "កូដបានបិទបញ្ចប់ភ្លាមៗ (Process exited)"
                if len(error_msg) > 3000:
                    error_msg = error_msg[-3000:]
                
                await query.edit_message_text(
                    f"❌ **Bot របស់លោកអ្នកមិនអាចដំណើរការបានទេដោយសារជាប់ Error ដូចខាងក្រោម៖**\n\n"
                    f"```text\n{error_msg}\n```\n"
                    "👉 សូមពិនិត្យមើលបញ្ហាខ្វះ Library ឬ Token ក្នុងកូដឡើងវិញ!",
                    parse_mode="Markdown"
                )
            else:
                keyboard = [[InlineKeyboardButton("⏹️ បញ្ឈប់ដំណើរការ Bot (Stop)", callback_data="action_stop_bot")]]
                await query.edit_message_text(
                    "🚀 **Bot របស់អ្នកកំពុងដំណើរការ ២៤ ម៉ោងនៅលើ Server ហើយ!**\n\n"
                    "👉 សូមចូលទៅកាន់ Bot របស់អ្នកក្នុង Telegram រួចសាកល្បងវាយ `/start` ដើម្បីប្រើប្រាស់។",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
        except Exception as e:
            await query.edit_message_text(f"❌ កំហុសប្រព័ន្ធ៖ {str(e)}")
        return

    if data == "action_stop_bot":
        if stop_user_process(user_id):
            await query.edit_message_text("⏹️ **Bot របស់អ្នកត្រូវបានបញ្ឈប់ដំណើរការ (Offline) ដោយជោគជ័យ!**", parse_mode="Markdown")
        else:
            await query.edit_message_text("ℹ️ មិនមាន Bot ណាមួយកំពុងដំណើរការឡើយ។")
        return

# បញ្ជា /addvip សម្រាប់អេដមីន
async def admin_add_vip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        args = context.args
        target_id = int(args[0])
        days = int(args[1])
        new_exp = add_vip(target_id, days)
        await update.message.reply_text(f"✅ បានបន្ថែម VIP ជូន ID `{target_id}` ចំនួន {days} ថ្ងៃជោគជ័យ!\n📅 ផុតកំណត់៖ {new_exp}", parse_mode="Markdown")
        await context.bot.send_message(chat_id=target_id, text=f"🎉 **គណនីរបស់អ្នកត្រូវបានបន្ថែម VIP ចំនួន {days} ថ្ងៃ!**\n📅 ផុតកំណត់នៅ៖ {new_exp}")
    except Exception:
        await update.message.reply_text("❌ ទម្រង់បញ្ជាខុស! សូមប្រើ៖ `/addvip <user_id> <days>`\nឧទាហរណ៍៖ `/addvip 123456789 30`", parse_mode="Markdown")

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_web_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addvip", admin_add_vip_cmd))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("Bot Hosting Server កំពុងដំណើរការ...")
    app.run_polling()
