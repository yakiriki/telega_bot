import os
import logging

from datetime import datetime
from fastapi import FastAPI, Request, Response
from fastapi import FastAPI
from contextlib import asynccontextmanager
from telegram import Update, ReplyKeyboardMarkup
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
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WAITING_NAME, WAITING_PRICE = range(2)
DELETE_CHECK_ID = "DELETE_CHECK"
DELETE_ITEM_ID = "DELETE_ITEM"
REPORT_ALL_FROM = "REPORT_ALL_FROM"
REPORT_ALL_TO = "REPORT_ALL_TO"

info_keyboard = ReplyKeyboardMarkup([["💡 Info"]], resize_keyboard=True)

# === Команди ===

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
    check_id, item_ids = save_items_to_db(items)
    await send_summary(update, items, check_id, item_ids)

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
    check_id, item_ids = save_items_to_db(items)
    await send_summary(update, items, check_id, item_ids)

async def send_summary(update, items, check_id, item_ids):
    if not items:
        await update.message.reply_text("❌ Не вдалося знайти товари в цьому чеку.")
        return
    text = f"✅ Додано чек #{check_id}:\n"
    total = 0
    for item, item_id in zip(items, item_ids):
        text += f"• ID {item_id} — {item['name']} ({item['category']}) — {item['sum'] / 100:.2f} грн\n"
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
    check_id, item_ids = save_items_to_db([item])
    await update.message.reply_text(f"✅ Додано: ID {item_ids[0]} — {name} ({category}) — {price:.2f} грн")
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
    success = delete_check_by_id(check_id)
    msg = "✅ Чек видалено." if success else "❌ Не знайдено чек."
    await update.message.reply_text(msg)
    return ConversationHandler.END

async def delete_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введіть ID товару для видалення:")
    return DELETE_ITEM_ID

async def delete_item_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    item_id = update.message.text.strip()
    success = delete_item_by_id(item_id)
    msg = "✅ Товар видалено." if success else "❌ Не знайдено товар."
    await update.message.reply_text(msg)
    return ConversationHandler.END

# === Звіти ===

async def report_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_report("day")
    await send_report(update, data, "за сьогодні")

async def report_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_report("week")
    await send_report(update, data, "за тиждень")

async def report_mounth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_report("month")
    await send_report(update, data, "за місяць")

async def report_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введіть дату початку у форматі YYYY-MM-DD:")
    return REPORT_ALL_FROM

async def report_all_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from_date = update.message.text.strip()
    context.user_data['from_date'] = from_date
    await update.message.reply_text("Введіть дату кінця у форматі YYYY-MM-DD:")
    return REPORT_ALL_TO

async def report_all_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    to_date = update.message.text.strip()
    from_date = context.user_data.get('from_date')
    data = get_report("custom", from_date=from_date, to_date=to_date)
    await send_report(update, data, f"з {from_date} по {to_date}")
    context.user_data.clear()
    return ConversationHandler.END

async def send_report(update, data, period):
    if not data:
        await update.message.reply_text(f"❗ Немає даних за період {period}.")
        return
    text = f"📊 Звіт {period}:\n"
    total = 0
    for category, amount in data.items():
        text += f"• {category}: {amount / 100:.2f} грн\n"
        total += amount
    text += f"\n💰 Всього: {total / 100:.2f} грн"
    await update.message.reply_text(text)

# === Debug ===

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = get_debug_info()
    await update.message.reply_text(f"Debug info:\n{info}")

# === Lifespan ===

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(DATABASE_URL)
    yield

app = FastAPI(lifespan=lifespan)

application = ApplicationBuilder().token(BOT_TOKEN).build()

# === ConversationHandlers с ИСПРАВЛЕНИЯМИ ===

manual_conv = ConversationHandler(
    entry_points=[CommandHandler("manual", manual_start)],
    states={
        WAITING_NAME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, manual_name),
            CommandHandler("cancel", cancel),  # ИСПРАВЛЕНО
            CommandHandler("manual", manual_start),  # ИСПРАВЛЕНО, чтобы перезапустить manual
        ],
        WAITING_PRICE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, manual_price),
            CommandHandler("cancel", cancel),  # ИСПРАВЛЕНО
            CommandHandler("manual", manual_start),  # ИСПРАВЛЕНО
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

delete_check_conv = ConversationHandler(
    entry_points=[CommandHandler("delete_check", delete_check)],
    states={
        DELETE_CHECK_ID: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, delete_check_confirm),
            CommandHandler("cancel", cancel),  # ИСПРАВЛЕНО
            CommandHandler("delete_check", delete_check),  # ИСПРАВЛЕНО
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

delete_item_conv = ConversationHandler(
    entry_points=[CommandHandler("delete_item", delete_item)],
    states={
        DELETE_ITEM_ID: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, delete_item_confirm),
            CommandHandler("cancel", cancel),  # ИСПРАВЛЕНО
            CommandHandler("delete_item", delete_item),  # ИСПРАВЛЕНО
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

report_all_conv = ConversationHandler(
    entry_points=[CommandHandler("report_all", report_all)],
    states={
        REPORT_ALL_FROM: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, report_all_from),
            CommandHandler("cancel", cancel),  # ИСПРАВЛЕНО
            CommandHandler("report_all", report_all),  # ИСПРАВЛЕНО
        ],
        REPORT_ALL_TO: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, report_all_to),
            CommandHandler("cancel", cancel),  # ИСПРАВЛЕНО
            CommandHandler("report_all", report_all),  # ИСПРАВЛЕНО
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

# === Добавление обработчиков ===

application.add_handler(manual_conv)
application.add_handler(delete_check_conv)
application.add_handler(delete_item_conv)
application.add_handler(report_all_conv)

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("info", info))
application.add_handler(CommandHandler("report_day", report_day))
application.add_handler(CommandHandler("report_week", report_week))
application.add_handler(CommandHandler("report_mounth", report_mounth))
application.add_handler(CommandHandler("debug", debug))

application.add_handler(MessageHandler(filters.Document.FileExtension("xml"), handle_file))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

# === Webhook ===

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    update = Update.de_json(await request.json(), application.bot)
    await application.update_queue.put(update)
    return Response()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000)
