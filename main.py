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
from aiohttp import web  # встроенный HTTP-сервер

# ====== Настройка логирования ======
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ====== Команды и состояния ======
WAITING_NAME, WAITING_PRICE = range(2)
DELETE_CHECK_ID = "DELETE_CHECK"
DELETE_ITEM_ID  = "DELETE_ITEM"
REPORT_ALL_FROM = "REPORT_ALL_FROM"
REPORT_ALL_TO   = "REPORT_ALL_TO"

info_keyboard = ReplyKeyboardMarkup([["💡 Info"]], resize_keyboard=True)

# ====== Переменные окружения ======
BOT_TOKEN    = os.getenv("BOT_TOKEN")
# Хост и порт, на котором Render запустит ваше приложение
PORT         = int(os.getenv("PORT", "8000"))
# Путь, по которому Telegram шлёт обновления. Можно любой, но уникальный.
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", f"/{BOT_TOKEN}")
# Полный публичный URL вашего бота: Render даст домен вида your-app.onrender.com
# Не забудьте установить эту переменную в настройках Render!
WEBHOOK_URL  = os.getenv("WEBHOOK_URL")  # например "https://your-app.onrender.com"

# ====== Объявление команд ======

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет приветственное сообщение с меню."""
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
    """Повторно вызывает start."""
    await start(update, context)

# ====== Обработка загрузки и текста ======

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Скачиваем XML-файл и парсим
    file = await update.message.document.get_file()
    tmp_path = f"/tmp/{file.file_id}.xml"
    await file.download_to_drive(tmp_path)
    items = parse_xml_file(tmp_path)

    # Сохраняем и получаем ID чека и товаров
    check_id, item_ids = save_items_to_db(items)
    await send_summary(update, items, check_id, item_ids)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    # Если в процессе ручного ввода — не смешивать
    if context.user_data.get("manual_in_progress"):
        await update.message.reply_text(
            "❗ Продовжіть введення або введіть /cancel."
        )
        return

    if text.lower().startswith("http"):
        items = parse_xml_url(text)
    elif "<?xml" in text:
        items = parse_xml_string(text)
    elif text == "💡 Info":
        return await info(update, context)
    else:
        return await update.message.reply_text(
            "❌ Це не схоже на XML або URL."
        )

    check_id, item_ids = save_items_to_db(items)
    await send_summary(update, items, check_id, item_ids)

async def send_summary(update, items, check_id, item_ids):
    """Выводит список добавленных товаров с их ID."""
    if not items:
        return await update.message.reply_text(
            "❌ Не вдалося знайти товари в цьому чеку."
        )
    text = f"✅ Додано чек #{check_id}:\n"
    total = 0
    for item, iid in zip(items, item_ids):
        text += f"• ID {iid}: {item['name']} ({item['category']}) — {item['sum']/100:.2f} грн\n"
        total += item["sum"]
    text += f"\n💰 Всього: {total/100:.2f} грн"
    await update.message.reply_text(text)

# ====== Ручное добавление ======

async def manual_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["manual_in_progress"] = True
    await update.message.reply_text("Введіть назву товару:")
    return WAITING_NAME

async def manual_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["manual_data"] = {"name": update.message.text}
    await update.message.reply_text("Введіть суму в грн (наприклад, 23.50):")
    return WAITING_PRICE

async def manual_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.replace(",", "."))
    except ValueError:
        return await update.message.reply_text("❌ Невірна сума, спробуй ще:")
    name = context.user_data["manual_data"]["name"]
    category = categorize(name)
    now = datetime.now().strftime("%Y-%m-%d")
    item = {"date": now, "name": name, "category": category, "sum": int(price*100)}
    check_id, item_ids = save_items_to_db([item])
    await update.message.reply_text(
        f"✅ Додано: ID {item_ids[0]} — {name} ({category}) — {price:.2f} грн"
    )
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Скасовано.")
    return ConversationHandler.END

# ====== Удаление чеков и товаров ======

async def delete_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введіть ID чеку для видалення:")
    return DELETE_CHECK_ID

async def delete_check_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chk_id = update.message.text.strip()
    ok = delete_check_by_id(chk_id)
    msg = "✅ Чек видалено." if ok else "❌ Чек не знайдено."
    await update.message.reply_text(msg)
    return ConversationHandler.END

async def delete_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введіть ID товару для видалення:")
    return DELETE_ITEM_ID

async def delete_item_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    itm_id = update.message.text.strip()
    ok = delete_item_by_id(itm_id)
    msg = "✅ Товар видалено." if ok else "❌ Товар не знайдено."
    await update.message.reply_text(msg)
    return ConversationHandler.END

# ====== Отчёты ======

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
    await update.message.reply_text("Введіть дату початку YYYY-MM-DD:")
    return REPORT_ALL_FROM

async def report_all_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["from_date"] = update.message.text.strip()
    await update.message.reply_text("Введіть дату кінця YYYY-MM-DD:")
    return REPORT_ALL_TO

async def report_all_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fr = context.user_data.get("from_date")
    to = update.message.text.strip()
    data = get_report("custom", fr, to)
    await send_report(update, data, f"з {fr} по {to}")
    context.user_data.clear()
    return ConversationHandler.END

async def send_report(update, data, period_name):
    if not data:
        return await update.message.reply_text(f"❌ Дані за {period_name} не знайдені.")
    text = f"📊 Звіт {period_name}:\n"
    total = 0
    for cat, val in data.items():
        text += f"• {cat}: {val/100:.2f} грн\n"
        total += val
    text += f"\n💰 Всього: {total/100:.2f} грн"
    await update.message.reply_text(text)

# ====== Debug ======

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = get_debug_info()
    await update.message.reply_text(
        f"Чеки: {info['checks']}\nТовари: {info['items']}"
    )

# ====== HTTP-сервер для Render ======

async def health(request):
    """Простой эндпоинт для проверки статуса."""
    return web.Response(text="OK")

def main():
    # Инициализируем БД
    init_db()

    # Строим приложение Telegram
    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )

    # Регистрируем все хендлеры (команды, диалоги и т.д.)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("info", info))
    application.add_handler(CommandHandler("report_day", report_day))
    application.add_handler(CommandHandler("report_week", report_week))
    application.add_handler(CommandHandler("report_mounth", report_mounth))
    application.add_handler(CommandHandler("debug", debug))

    # ConversationHandlers
    application.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("manual", manual_start)],
            states={
                WAITING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_name)],
                WAITING_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_price)],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )
    )
    application.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("delete_check", delete_check)],
            states={DELETE_CHECK_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_check_confirm)]},
            fallbacks=[CommandHandler("cancel", cancel)],
        )
    )
    application.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("delete_item", delete_item)],
            states={DELETE_ITEM_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_item_confirm)]},
            fallbacks=[CommandHandler("cancel", cancel)],
        )
    )
    application.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("report_all", report_all)],
            states={
                REPORT_ALL_FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, report_all_from)],
                REPORT_ALL_TO:   [MessageHandler(filters.TEXT & ~filters.COMMAND, report_all_to)],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )
    )

    # XML и текст
    application.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # === Запускаем webhook-сервер ===
    # Telegram будет посылать POST запросы на /<BOT_TOKEN>
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=WEBHOOK_PATH,
        webhook_url=f"{WEBHOOK_URL}{WEBHOOK_PATH}",
        # Для HTTPS-сертификата на Render дополнительных настроек не нужно
    )

    # === HTTP-сервер для health ===
    app = web.Application()
    app.router.add_get("/health", health)
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
