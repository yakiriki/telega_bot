import os
import logging
from datetime import datetime

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# Убираем ручной aiohttp, пользуясь встроенным run_webhook
# from aiohttp import web  

from parsers.xml_parser import parse_xml_file, parse_xml_string, parse_xml_url
from utils.db import (
    init_db,
    save_items_to_db,
    get_report,
    get_debug_info,
    delete_check_by_id,
    delete_item_by_id,
)
from utils.categories import categorize

# ===== Конфигурация =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_URL    = os.getenv("DATABASE_URL")      # URL Supabase
PORT      = int(os.getenv("PORT", 8443))   # Render назначит свой
# Render автоматически предоставляет переменную RENDER_EXTERNAL_URL с вашим доменом
HOST_URL  = os.getenv("RENDER_EXTERNAL_URL")  

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== Состояния для ConversationHandler =====
WAITING_NAME, WAITING_PRICE = range(2)
DELETE_CHECK_ID            = "DELETE_CHECK"
DELETE_ITEM_ID             = "DELETE_ITEM"
REPORT_ALL_FROM            = "REPORT_ALL_FROM"
REPORT_ALL_TO              = "REPORT_ALL_TO"

info_keyboard = ReplyKeyboardMarkup([["💡 Info"]], resize_keyboard=True)

# ===== Handlers (ваши функции без изменений) =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 Привіт! Я бот для обліку витрат по чеках.\n\n"
        "📌 Команди:\n"
        "/info — довідка\n"
        "/report_day — за сьогодні\n"
        "/report_week — за тиждень\n"
        "/report_month — за місяць\n"
        "/report_all — звіт за період\n"
        "/debug — техінфо\n"
        "/manual — додати вручну\n"
        "/delete_check — видалити чек\n"
        "/delete_item — видалити товар\n"
    )
    await update.message.reply_text(msg, reply_markup=info_keyboard)

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.document.get_file()
    path = f"/tmp/{file.file_id}.xml"
    await file.download_to_drive(path)
    items = parse_xml_file(path)
    check_id, item_ids = save_items_to_db(items)
    await send_summary(update, items, check_id, item_ids)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if context.user_data.get("manual_in_progress"):
        await update.message.reply_text("❗ Завершіть /cancel або продовжіть.")
        return
    if txt.lower().startswith("http"):
        items = parse_xml_url(txt)
    elif "<?xml" in txt:
        items = parse_xml_string(txt)
    elif txt == "💡 Info":
        await info(update, context)
        return
    else:
        await update.message.reply_text("❌ Це не XML/URL.")
        return
    check_id, item_ids = save_items_to_db(items)
    await send_summary(update, items, check_id, item_ids)

async def send_summary(update, items, check_id, item_ids):
    if not items:
        await update.message.reply_text("❗ Нема товарів.")
        return
    text = f"✅ Чек #{check_id}:\n"
    tot = 0
    for it, iid in zip(items, item_ids):
        text += f"• ID {iid} — {it['name']} ({it['category']}) — {it['sum']/100:.2f} грн\n"
        tot += it["sum"]
    text += f"\n💰 Всього: {tot/100:.2f} грн"
    await update.message.reply_text(text)

async def manual_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["manual_in_progress"] = True
    await update.message.reply_text("Введіть назву товару:")
    return WAITING_NAME

async def manual_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['manual_data'] = {'name': update.message.text}
    await update.message.reply_text("Введіть суму в грн (наприклад:23.50):")
    return WAITING_PRICE

async def manual_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ Невірна сума.")
        return WAITING_PRICE
    name = context.user_data['manual_data']['name']
    cat  = categorize(name)
    now  = datetime.now().strftime("%Y-%m-%d")
    item = {"date": now, "name": name, "category": cat, "sum": int(price*100)}
    check_id, item_ids = save_items_to_db([item])
    await update.message.reply_text(f"✅ Додано ID {item_ids[0]} — {name} ({cat}) — {price:.2f} грн")
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("✅ Скасовано.")
    return ConversationHandler.END

async def delete_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введіть ID чеку для видалення:")
    return DELETE_CHECK_ID

async def delete_check_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok = delete_check_by_id(update.message.text.strip())
    await update.message.reply_text("✅ Чек видалено." if ok else "❌ Не знайдено чек.")
    return ConversationHandler.END

async def delete_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введіть ID товару:")
    return DELETE_ITEM_ID

async def delete_item_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok = delete_item_by_id(update.message.text.strip())
    await update.message.reply_text("✅ Товар видалено." if ok else "❌ Не знайдено товар.")
    return ConversationHandler.END

async def report_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_report("day")
    await send_report(update, data, "за сьогодні")

async def report_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_report("week")
    await send_report(update, data, "за тиждень")

async def report_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_report("month")
    await send_report(update, data, "за місяць")

async def report_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введіть дату початку (YYYY-MM-DD):")
    return REPORT_ALL_FROM

async def report_all_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["from_date"] = update.message.text.strip()
    await update.message.reply_text("Введіть дату кінця:")
    return REPORT_ALL_TO

async def report_all_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fr   = context.user_data.get("from_date")
    to   = update.message.text.strip()
    data = get_report("custom", fr, to)
    await send_report(update, data, f"з {fr} по {to}")
    context.user_data.clear()
    return ConversationHandler.END

async def send_report(update, data, period_name):
    if not data:
        await update.message.reply_text(f"❌ Нема даних {period_name}.")
        return
    text = f"📊 Звіт {period_name}:\n"
    total = 0
    for cat, s in data.items():
        text += f"• {cat}: {s/100:.2f} грн\n"
        total += s
    text += f"\n💰 Всего: {total/100:.2f} грн"
    await update.message.reply_text(text)

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    st = get_debug_info()
    await update.message.reply_text(f"🛠️ Чеки: {st['checks']}\n🛠️ Товари: {st['items']}")

# ===== Полное исправление для webhook-сервера =====
def main():
    # 1) Инициализируем БД (DB_URL указывает на ваш DATABASE_URL)
    init_db(DB_URL)

    # 2) Создаём приложение Telegram с вашими хендлерами
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("report_day", report_day))
    app.add_handler(CommandHandler("report_week", report_week))
    app.add_handler(CommandHandler("report_month", report_month))
    app.add_handler(CommandHandler("report_all", report_all))
    app.add_handler(CommandHandler("debug", debug))
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("manual", manual_start)],
        states={WAITING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_name)],
                WAITING_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_price)]},
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
        states={REPORT_ALL_FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, report_all_from)],
                REPORT_ALL_TO:   [MessageHandler(filters.TEXT & ~filters.COMMAND, report_all_to)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    ))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # 3) Запуск webhook и HTTP-сервера вместе
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url_path=f"/{BOT_TOKEN}",
        webhook_url=f"{HOST_URL}/{BOT_TOKEN}",
    )

if __name__ == "__main__":
    main()
