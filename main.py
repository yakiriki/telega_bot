
import os
import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
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
DELETE_CHECK_ID, DELETE_ITEM_ID, REPORT_ALL_FROM, REPORT_ALL_TO = range(2, 6)

info_keyboard = ReplyKeyboardMarkup([["💡 Info"]], resize_keyboard=True)

# Health check server
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health():
    port = int(os.environ.get("PORT", "8000"))
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()

threading.Thread(target=run_health, daemon=True).start()

# Bot handlers
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
    saved_items, cid = save_items_to_db(items, DB_PATH)
    await send_summary(update, saved_items, cid)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if txt == "💡 Info":
        return await info(update, context)
    if txt.lower().startswith("http"):
        items = parse_xml_url(txt)
    elif "<?xml" in txt:
        items = parse_xml_string(txt)
    else:
        return await update.message.reply_text(
            "❌ Це не схоже на XML або URL.", reply_markup=info_keyboard
        )
    saved_items, cid = save_items_to_db(items, DB_PATH)
    await send_summary(update, saved_items, cid)

async def send_summary(update, items, cid):
    if not items:
        return await update.message.reply_text("❌ Порожній чек", reply_markup=info_keyboard)
    text = f"✅ Чек #{cid}:\n"
    total = 0
    for it in items:
        text += f"• [{it['id']}] {it['name']} ({it['category']}) — {it['sum']/100:.2f} грн\n"
        total += it['sum']
    text += f"\n💰 Всього: {total/100:.2f} грн"
    await update.message.reply_text(text, reply_markup=info_keyboard)

async def manual_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["manual_in_progress"] = True
    await update.message.reply_text("Введіть назву товару:", reply_markup=info_keyboard)
    return WAITING_NAME

async def manual_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["manual_name"] = update.message.text
    await update.message.reply_text("Введіть суму в грн:", reply_markup=info_keyboard)
    return WAITING_PRICE

async def manual_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.replace(",", "."))
    except ValueError:
        return await update.message.reply_text("❌ Невірна сума."), WAITING_PRICE
    name = context.user_data.pop("manual_name")
    category = categorize(name)
    date = datetime.now().strftime("%Y-%m-%d")
    saved_items, cid = save_items_to_db([{"date": date, "name": name, "category": category, "sum": int(price*100)}], DB_PATH)
    await send_summary(update, saved_items, cid)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Скасовано.", reply_markup=info_keyboard)
    return ConversationHandler.END

async def delete_check_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введіть ID чеку для видалення:", reply_markup=info_keyboard)
    return DELETE_CHECK_ID

async def delete_check_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok = delete_check_by_id(DB_PATH, update.message.text.strip())
    await update.message.reply_text("✅ Чек видалено." if ok else "❌ Не знайдено чек.", reply_markup=info_keyboard)
    return ConversationHandler.END

async def delete_item_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введіть ID товару для видалення:", reply_markup=info_keyboard)
    return DELETE_ITEM_ID

async def delete_item_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok = delete_item_by_id(DB_PATH, update.message.text.strip())
    await update.message.reply_text("✅ Товар видалено." if ok else "❌ Не знайдено товар.", reply_markup=info_keyboard)
    return ConversationHandler.END

async def report_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_report(update, "day")

async def report_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_report(update, "week")

async def report_mounth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_report(update, "month")

async def report_all_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введіть дату з (YYYY-MM-DD):", reply_markup=info_keyboard)
    return REPORT_ALL_FROM

async def report_all_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["from_date"] = update.message.text.strip()
    await update.message.reply_text("Введіть дату по (YYYY-MM-DD):", reply_markup=info_keyboard)
    return REPORT_ALL_TO

async def report_all_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fr = context.user_data.get("from_date")
    to = update.message.text.strip()
    await send_report(update, "custom", fr, to)
    return ConversationHandler.END

async def send_report(update, period, fr=None, to=None):
    rpt = get_report(DB_PATH, period, fr, to)
    if not rpt:
        return await update.message.reply_text("Немає даних за вказаний період.", reply_markup=info_keyboard)
    text = "📊 Звіт:\n"
    total = 0
    for c, s in rpt.items():
        text += f"• {c}: {s/100:.2f} грн\n"
        total += s
    text += f"\n💰 Всього: {total/100:.2f} грн"
    await update.message.reply_text(text, reply_markup=info_keyboard)

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = get_debug_info(DB_PATH)
    await update.message.reply_text(f"Чеки: {stats['checks']}, Товари: {stats['items']}", reply_markup=info_keyboard)

def main():
    init_db(DB_PATH)
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("report_day", report_day))
    app.add_handler(CommandHandler("report_week", report_week))
    app.add_handler(CommandHandler("report_mounth", report_mounth))
    app.add_handler(CommandHandler("report_all", report_all_start))
    app.add_handler(CommandHandler("debug", debug))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("manual", manual_start)],
        states={
            WAITING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_name)],
            WAITING_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_price)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    ))

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

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("report_all", report_all_start)],
        states={
            REPORT_ALL_FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, report_all_from)],
            REPORT_ALL_TO: [MessageHandler(filters.TEXT & ~filters.COMMAND, report_all_to)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    ))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling()

if __name__ == "__main__":
    main()
