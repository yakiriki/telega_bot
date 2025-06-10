import os
import logging
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InputFile, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

from parsers.xml_parser import parse_xml_file, parse_xml_string, parse_xml_url
from utils.db import init_db, save_items_to_db, get_report, get_debug_info, delete_check_by_id, delete_item_by_id
from utils.categories import categorize

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = "/data/expenses.db"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WAITING_NAME, WAITING_PRICE = range(2)

# Стани для ConversationHandler
DELETE_CHECK_ID = "DELETE_CHECK"
DELETE_ITEM_ID = "DELETE_ITEM"
REPORT_ALL_FROM = "REPORT_ALL_FROM"
REPORT_ALL_TO = "REPORT_ALL_TO"

info_keyboard = ReplyKeyboardMarkup([["💡 Info"]], resize_keyboard=True)

# === Основні команди ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 Привіт! Я бот для обліку витрат по чеках.\n\n"
        "📌 Список команд:\n"
        "/info — довідка\n"
        "/report_day — звіт за сьогодні\n"
        "/report_week — звіт за тиждень\n"
        "/report_mounth — звіт за місяць\n"
        "/report_all — звіт за вибраний період\n"
        "/debug — технічна інформація\n"
        "/manual — додати товар вручну\n"
        "/delete_check — видалити чек\n"
        "/delete_item — видалити товар\n\n"
        "Натисніть кнопку «💡 Info», щоб побачити список команд."
    )
    await update.message.reply_text(msg, reply_markup=info_keyboard)

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# === Обробка XML ===

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.document.get_file()
    file_path = f"/tmp/{file.file_id}.xml"
    await file.download_to_drive(file_path)
    items = parse_xml_file(file_path)
    check_id = save_items_to_db(items, DB_PATH)
    await send_summary(update, items, check_id)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if context.user_data.get("manual_in_progress"):
        await update.message.reply_text("❗ Продовжіть введення назви або ціни товару, або введіть /cancel.")
        return

    if text.lower().startswith("http"):
        items = parse_xml_url(text)
    elif "<?xml" in text:
        items = parse_xml_string(text)
    elif text == "💡 Info":
        await info(update, context)
        return
    else:
        await update.message.reply_text("❌ Це не схоже на XML або URL.\nСпробуйте ще.")
        return

    check_id = save_items_to_db(items, DB_PATH)
    await send_summary(update, items, check_id)

async def send_summary(update, items, check_id):
    if not items:
        await update.message.reply_text("❌ Не вдалося знайти товари в цьому чеку.")
        return
    text = f"✅ Додано чек #{check_id}:\n"
    total = 0
    for item in items:
        text += f"• {item['name']} ({item['category']}) — {item['sum'] / 100:.2f} грн\n"
        total += item['sum']
    text += f"\n💰 Всього: {total / 100:.2f} грн"
    await update.message.reply_text(text)

# === Вручну ===

async def manual_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["manual_in_progress"] = True
    await update.message.reply_text("Введіть назву товару:")
    return WAITING_NAME

async def manual_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['manual_data'] = {'name': update.message.text}
    await update.message.reply_text("Введіть суму в грн (наприклад, 23.50):")
    return WAITING_PRICE

async def manual_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ Невірна сума. Спробуйте ще:")
        return WAITING_PRICE

    name = context.user_data['manual_data']['name']
    category = categorize(name)
    now = datetime.now()
    item = {
        "date": now.strftime("%Y-%m-%d"),
        "name": name,
        "category": category,
        "sum": int(price * 100)
    }
    check_id = save_items_to_db([item], DB_PATH)
    await update.message.reply_text(f"✅ Додано: {name} ({category}) — {price:.2f} грн")
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Скасовано.")
    return ConversationHandler.END

# === Видалення ===

async def delete_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введіть ID чеку для видалення:")
    return DELETE_CHECK_ID

async def delete_check_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    check_id = update.message.text.strip()
    success = delete_check_by_id(DB_PATH, check_id)
    msg = "✅ Чек видалено." if success else "❌ Не знайдено чек."
    await update.message.reply_text(msg)
    return ConversationHandler.END

async def delete_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введіть ID товару для видалення:")
    return DELETE_ITEM_ID

async def delete_item_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    item_id = update.message.text.strip()
    success = delete_item_by_id(DB_PATH, item_id)
    msg = "✅ Товар видалено." if success else "❌ Не знайдено товар."
    await update.message.reply_text(msg)
    return ConversationHandler.END

# === Звіти ===

async def report_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_report(update, "day")

async def report_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_report(update, "week")

async def report_mounth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_report(update, "month")

async def report_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введіть дату з (РРРР-ММ-ДД):")
    return REPORT_ALL_FROM

async def report_all_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["from_date"] = update.message.text.strip()
    await update.message.reply_text("Введіть дату по (РРРР-ММ-ДД):")
    return REPORT_ALL_TO

async def report_all_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from_date = context.user_data.get("from_date")
    to_date = update.message.text.strip()
    await send_report(update, "custom", from_date, to_date)
    return ConversationHandler.END

async def send_report(update, period, from_date=None, to_date=None):
    report = get_report(DB_PATH, period, from_date, to_date)
    if not report:
        await update.message.reply_text("Немає даних за вказаний період.")
        return
    text = "📊 Звіт:\n"
    total = 0
    for cat, s in report.items():
        text += f"• {cat}: {s / 100:.2f} грн\n"
        total += s
    text += f"\n💰 Всього: {total / 100:.2f} грн"
    await update.message.reply_text(text)

# === Debug ===

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = get_debug_info(DB_PATH)
    msg = f"📦 Чеків: {stats['checks']}\n🛒 Товарів: {stats['items']}"
    await update.message.reply_text(msg)

# === main ===

def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("report_day", report_day))
    app.add_handler(CommandHandler("report_week", report_week))
    app.add_handler(CommandHandler("report_mounth", report_mounth))
    app.add_handler(CommandHandler("debug", debug))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("manual", manual_start)],
        states={
            WAITING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_name)],
            WAITING_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_price)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("delete_check", delete_check)],
        states={DELETE_CHECK_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_check_confirm)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("delete_item", delete_item)],
        states={DELETE_ITEM_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_item_confirm)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("report_all", report_all)],
        states={
            REPORT_ALL_FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, report_all_from)],
            REPORT_ALL_TO: [MessageHandler(filters.TEXT & ~filters.COMMAND, report_all_to)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()

if __name__ == "__main__":
    main()
