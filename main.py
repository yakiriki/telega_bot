import os
import logging
from datetime import datetime

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from aiohttp import web

from parsers.xml_parser import parse_xml_file, parse_xml_string, parse_xml_url
from utils.db import init_db, save_items_to_db, get_report, get_debug_info, delete_check_by_id, delete_item_by_id
from utils.categories import categorize

# ====== Конфиг ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_URL    = os.getenv("DATABASE_URL")
PORT      = int(os.getenv("PORT", "8443"))
HOST_URL  = os.getenv("RENDER_EXTERNAL_URL")  # https://your-app.onrender.com

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ====== Состояния ======
WAIT_NAME, WAIT_PRICE = range(2)
DEL_CHECK, DEL_ITEM = "DEL_CHECK", "DEL_ITEM"
REP_FROM, REP_TO = "REP_FROM", "REP_TO"

info_kb = ReplyKeyboardMarkup([["💡 Info"]], resize_keyboard=True)

# ====== Handlers ======

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Привіт! Я бот для обліку витрат.\n\n"
        "/info\n"
        "/report_day\n"
        "/report_week\n"
        "/report_month\n"
        "/report_all\n"
        "/debug\n"
        "/manual\n"
        "/delete_check\n"
        "/delete_item"
    )
    await update.message.reply_text(text, reply_markup=info_kb)

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = await update.message.document.get_file()
    path = f"/tmp/{doc.file_id}.xml"
    await doc.download_to_drive(path)
    items = parse_xml_file(path)
    cid, iids = save_items_to_db(items)
    await send_summary(update, items, cid, iids)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if context.user_data.get("manual"):
        await update.message.reply_text("❗ Завершіть /cancel або продовжіть.")
        return
    if txt.lower().startswith("http"):
        items = parse_xml_url(txt)
    elif "<?xml" in txt:
        items = parse_xml_string(txt)
    elif txt == "💡 Info":
        return await info(update, context)
    else:
        return await update.message.reply_text("❌ Не XML/URL.")
    cid, iids = save_items_to_db(items)
    await send_summary(update, items, cid, iids)

async def send_summary(update, items, cid, iids):
    if not items:
        return await update.message.reply_text("❌ Пустий чек.")
    text = f"✅ Чек #{cid}:\n"
    total = 0
    for it, iid in zip(items, iids):
        text += f"• ID {iid}: {it['name']} ({it['category']}) — {it['sum']/100:.2f} грн\n"
        total += it["sum"]
    text += f"\n💰 Всього: {total/100:.2f} грн"
    await update.message.reply_text(text)

async def manual_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["manual"] = True
    await update.message.reply_text("Введіть назву товару:")
    return WAIT_NAME

async def manual_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text
    await update.message.reply_text("Введіть суму, наприклад 23.50:")
    return WAIT_PRICE

async def manual_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ Невірна сума.")
        return WAIT_PRICE
    name = context.user_data.pop("name")
    category = categorize(name)
    date = datetime.now().strftime("%Y-%m-%d")
    cid, iids = save_items_to_db([{"name":name,"category":category,"sum":int(price*100),"date":date}])
    await update.message.reply_text(f"✅ ID {iids[0]} — {name} ({category}) — {price:.2f} грн")
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("✅ Скасовано.")
    return ConversationHandler.END

async def delete_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введіть ID чеку:")
    return DEL_CHECK

async def delete_check_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok = delete_check_by_id(int(update.message.text))
    await update.message.reply_text("✅ Видалено." if ok else "❌ Не знайдено.")
    return ConversationHandler.END

async def delete_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введіть ID товару:")
    return DEL_ITEM

async def delete_item_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok = delete_item_by_id(int(update.message.text))
    await update.message.reply_text("✅ Видалено." if ok else "❌ Не знайдено.")
    return ConversationHandler.END

async def report_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_report(update, get_report("day"), "сьогодні")

async def report_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_report(update, get_report("week"), "тиждень")

async def report_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_report(update, get_report("month"), "місяць")

async def report_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введіть дату початку (YYYY-MM-DD):")
    return REP_FROM

async def report_all_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["from"] = update.message.text
    await update.message.reply_text("Введіть дату кінця:")
    return REP_TO

async def report_all_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fr = context.user_data["from"]
    to = update.message.text
    await _send_report(update, get_report("custom", fr, to), f"з {fr} по {to}")
    return ConversationHandler.END

async def _send_report(update, data, period_name):
    if not data:
        return await update.message.reply_text(f"❌ Нема даних за {period_name}.")
    text = f"📊 Звіт за {period_name}:\n"
    total = 0
    for cat, s in data.items():
        text += f"• {cat}: {s/100:.2f} грн\n"
        total += s
    text += f"\n💰 {total/100:.2f} грн"
    await update.message.reply_text(text)

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = get_debug_info()
    await update.message.reply_text(f"Чеки: {stats['checks']}\nТовари: {stats['items']}")

async def health(request):
    return web.Response(text="OK")

async def webhook_handler(request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return web.Response(text="OK")

async def main():
    # 1. Инициализируем БД
    init_db(DB_URL)

    # 2. Строим бот
    global application
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # 3. Регистрируем хендлеры
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("info", info))
    application.add_handler(CommandHandler("report_day", report_day))
    application.add_handler(CommandHandler("report_week", report_week))
    application.add_handler(CommandHandler("report_month", report_month))
    application.add_handler(CommandHandler("report_all", report_all))
    application.add_handler(CommandHandler("debug", debug))
    application.add_handler(ConversationHandler(
        entry_points=[CommandHandler("manual", manual_start)],
        states={WAIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_name)],
                WAIT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_price)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    ))
    application.add_handler(ConversationHandler(
        entry_points=[CommandHandler("delete_check", delete_check)],
        states={DEL_CHECK: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_check_confirm)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    ))
    application.add_handler(ConversationHandler(
        entry_points=[CommandHandler("delete_item", delete_item)],
        states={DEL_ITEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_item_confirm)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    ))
    application.add_handler(ConversationHandler(
        entry_points=[CommandHandler("report_all", report_all)],
        states={REP_FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, report_all_from)],
                REP_TO:   [MessageHandler(filters.TEXT & ~filters.COMMAND, report_all_to)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    ))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # 4. Устанавливаем webhook
    await application.initialize()
    await application.bot.set_webhook(f"{HOST_URL}/{BOT_TOKEN}")
    await application.start()

    # 5. Запускаем HTTP-сервер
    server = web.Application()
    server.router.add_post(f"/{BOT_TOKEN}", webhook_handler)
    server.router.add_get("/health", health)
    logger.info(f"Запуск HTTP на порту {PORT}")
    web.run_app(server, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
