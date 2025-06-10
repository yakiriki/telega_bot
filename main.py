import os
import logging
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from parsers.xml_parser import parse_xml_file, parse_xml_string, parse_xml_url
from utils.db import (
    init_db, save_items_to_db, get_report,
    get_debug_info, delete_check_by_id, delete_item_by_id
)
from utils.categories import categorize

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = "/data/expenses.db"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WAITING_NAME, WAITING_PRICE = range(2)
DELETE_CHECK_ID, DELETE_ITEM_ID, REPORT_ALL_FROM, REPORT_ALL_TO = range(4, 8)

info_keyboard = ReplyKeyboardMarkup([["💡 Info"]], resize_keyboard=True)

# --- Health-check HTTP server ---
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health():
    port = int(os.environ.get("PORT", "8000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

# Запускаем health-сервер в фоне
threading.Thread(target=run_health, daemon=True).start()

# === Функции бота ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 Привіт! Я бот для обліку витрат по чеках.\n\n"
        "📌 Команди:\n"
        "/info\n/report_day\n/report_week\n/report_mounth\n"
        "/report_all\n/debug\n/manual\n"
        "/delete_check\n/delete_item\n\n"
        "Натисніть «💡 Info» для довідки."
    )
    await update.message.reply_text(msg, reply_markup=info_keyboard)

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.document.get_file()
    path = f"/tmp/{file.file_id}.xml"
    await file.download_to_drive(path)
    items = parse_xml_file(path)
    cid = save_items_to_db(items, DB_PATH)
    await send_summary(update, items, cid)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if txt == "💡 Info":
        return await info(update, context)
    if context.user_data.get("manual_in_progress"):
        return await update.message.reply_text(
            "Продовжіть введення або /cancel", reply_markup=info_keyboard
        )
    if txt.lower().startswith("http"):
        items = parse_xml_url(txt)
    elif "<?xml" in txt:
        items = parse_xml_string(txt)
    else:
        return await update.message.reply_text(
            "❌ Не XML/URL.", reply_markup=info_keyboard
        )
    cid = save_items_to_db(items, DB_PATH)
    await send_summary(update, items, cid)

async def send_summary(update, items, cid):
    if not items:
        return await update.message.reply_text("❌ Порожній чек", reply_markup=info_keyboard)
    text = f"✅ Чек #{cid}:\n"
    total = 0
    for it in items:
        text += f"• {it['name']} ({it['category']}) — {it['sum']/100:.2f} грн\n"
        total += it['sum']
    text += f"\n💰 Всього: {total/100:.2f} грн"
    await update.message.reply_text(text, reply_markup=info_keyboard)

# --- Manual ---
async def manual_start(update, context):
    context.user_data["manual_in_progress"] = True
    return await update.message.reply_text("Введіть назву:", reply_markup=info_keyboard), WAITING_NAME

async def manual_name(update, context):
    context.user_data["manual_name"] = update.message.text
    return await update.message.reply_text("Введіть суму:"), WAITING_PRICE

async def manual_price(update, context):
    try:
        price = float(update.message.text.replace(",", "."))
    except:
        return await update.message.reply_text("❌ Помилка суми"), WAITING_PRICE
    name = context.user_data.pop("manual_name")
    category = categorize(name)
    now = datetime.now().strftime("%Y-%m-%d")
    save_items_to_db([{"date": now, "name": name, "category": category, "sum": int(price*100)}], DB_PATH)
    context.user_data.clear()
    return await update.message.reply_text(f"✅ Додано {name}"), ConversationHandler.END

async def cancel(update, context):
    context.user_data.clear()
    return await update.message.reply_text("Скасовано"), ConversationHandler.END

# --- Delete ---
async def delete_check_start(update, context):
    return await update.message.reply_text("ID чеку?"), DELETE_CHECK_ID

async def delete_check_confirm(update, context):
    ok = delete_check_by_id(DB_PATH, update.message.text.strip())
    return await update.message.reply_text("✅" if ok else "❌"), ConversationHandler.END

async def delete_item_start(update, context):
    return await update.message.reply_text("ID товару?"), DELETE_ITEM_ID

async def delete_item_confirm(update, context):
    ok = delete_item_by_id(DB_PATH, update.message.text.strip())
    return await update.message.reply_text("✅" if ok else "❌"), ConversationHandler.END

# --- Reports ---
async def report_day(update, context): return await send_report(update, get_report(DB_PATH, "day"))
async def report_week(update, context): return await send_report(update, get_report(DB_PATH, "week"))
async def report_mounth(update, context): return await send_report(update, get_report(DB_PATH, "month"))

async def report_all_start(update, context):
    await update.message.reply_text("Від (YYYY-MM-DD)?"), 
    return REPORT_ALL_FROM

async def report_all_from(update, context):
    context.user_data["from"] = update.message.text.strip()
    await update.message.reply_text("До (YYYY-MM-DD)?")
    return REPORT_ALL_TO

async def report_all_to(update, context):
    fr, to = context.user_data["from"], update.message.text.strip()
    return await send_report(update, get_report(DB_PATH, "custom", fr, to))

async def debug(update, context):
    s = get_debug_info(DB_PATH)
    return await update.message.reply_text(f"Чеки: {s['checks']}, Товари: {s['items']}")

# === main ===
def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Команди
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("report_day", report_day))
    app.add_handler(CommandHandler("report_week", report_week))
    app.add_handler(CommandHandler("report_mounth", report_mounth))
    app.add_handler(CommandHandler("report_all", report_all_start))
    app.add_handler(CommandHandler("debug", debug))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

    # Manual
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("manual", manual_start)],
        states={
            WAITING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_name)],
            WAITING_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_price)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    ))

    # Delete
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("delete_check", delete_check_start)],
        states={DELETE_CHECK_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_check_confirm)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("delete_item", delete_item_start)],
        states={DELETE_ITEM_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_item_confirm)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    ))

    # Report all
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("report_all", report_all_start)],
        states={
            REPORT_ALL_FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, report_all_from)],
            REPORT_ALL_TO: [MessageHandler(filters.TEXT & ~filters.COMMAND, report_all_to)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    ))

    # Fallback
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()

if __name__ == "__main__":
    main()
