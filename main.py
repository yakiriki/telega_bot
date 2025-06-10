import os
import logging
# from datetime import datetime # Закомментировано, так как не используется напрямую в этой версии

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# Все импорты, связанные с БД и парсерами, закомментированы для диагностики
# from parsers.xml_parser import parse_xml_file, parse_xml_string, parse_xml_url
# from utils.db import (
#     init_db,
#     save_items_to_db,
#     get_report,
#     get_debug_info,
#     delete_check_by_id,
#     delete_item_by_id,
# )
# from utils.categories import categorize

# ===== Настройки =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_URL    = os.getenv("DATABASE_URL") # Переменная остается, но не используется
PORT      = int(os.getenv("PORT", 8443))
HOST_URL  = os.getenv("RENDER_EXTERNAL_URL")

# Настраиваем логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Выводим настройки для проверки
logger.info(f"Настройки: PORT={PORT}, HOST_URL={HOST_URL}")

# ===== Состояния (оставлены, но не будут активно использоваться) =====
WAITING_NAME, WAITING_PRICE = range(2)
DELETE_CHECK_ID            = "DELETE_CHECK"
DELETE_ITEM_ID             = "DELETE_ITEM"
REPORT_ALL_FROM            = "REPORT_ALL_FROM"
REPORT_ALL_TO              = "REPORT_ALL_TO"

info_keyboard = ReplyKeyboardMarkup([["💡 Info"]], resize_keyboard=True)

# ===== Хендлеры =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 Привіт! Я бот для обліку витрат по чеках.\n\n"
        "📌 Команди:\n"
        "/info — довідка\n"
        "\n⚠️ Большинство функций отключены для диагностики (нет доступа к БД)."
    )
    await update.message.reply_text(msg, reply_markup=info_keyboard)

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# Функции, которые раньше работали с файлами/текстом/ручным вводом и БД, теперь просто отвечают заглушкой
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Обработка файлов временно отключена для диагностики (нет доступа к БД).")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if context.user_data.get("manual_in_progress"):
        await update.message.reply_text("❗ Завершіть /cancel або продовжіть.")
        return
    if txt == "💡 Info":
        await info(update, context)
    else:
        await update.message.reply_text("Обработка текста временно отключена для диагностики (нет доступа к БД).")

async def manual_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["manual_in_progress"] = True
    await update.message.reply_text("Ручной ввод временно отключен для диагностики (нет доступа к БД).")
    context.user_data.clear() # Сразу очищаем, чтобы не висело состояние
    return ConversationHandler.END # Завершаем ConversationHandler сразу же

async def manual_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Ручной ввод временно отключен для диагностики (нет доступа к БД).")
    context.user_data.clear()
    return ConversationHandler.END

async def manual_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Ручной ввод временно отключен для диагностики (нет доступа к БД).")
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("✅ Скасовано.")
    return ConversationHandler.END

# Все функции, связанные с отчетами и удалением, также закомментированы
# async def delete_check(...): pass
# async def delete_check_confirm(...): pass
# async def delete_item(...): pass
# async def delete_item_confirm(...): pass
# async def report_day(...): pass
# async def report_week(...): pass
# async def report_month(...): pass
# async def report_all(...): pass
# async def report_all_from(...): pass
# async def report_all_to(...): pass
# async def send_report(...): pass
# async def debug(...): pass


# Обработчик ошибок
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Логирует ошибку и отправляет сообщение пользователю (если возможно)."""
    logger.error("Произошла ошибка при обработке обновления:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Извините, произошла внутренняя ошибка. Пожалуйста, попробуйте позже. "
                "Подробнее в логах Render."
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение об ошибке пользователю: {e}")

# ===== Main с run_webhook =====

def main():
    # Инициализация БД - ЗАКОММЕНТИРОВАНО! Это наш главный подозреваемый.
    # init_db(DB_URL)

    # Построение приложения
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Регистрируем только базовые хендлеры, которые не требуют БД
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("manual", manual_start)],
        states={
            WAITING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_name)],
            WAITING_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_price)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Все остальные хендлеры, связанные с БД, также закомментированы
    # app.add_handler(CommandHandler("report_day", report_day))
    # app.add_handler(CommandHandler("report_week", report_week))
    # app.add_handler(CommandHandler("report_month", report_month))
    # app.add_handler(CommandHandler("report_all", report_all))
    # app.add_handler(CommandHandler("debug", debug))
    # app.add_handler(ConversationHandler(
    #     entry_points=[CommandHandler("delete_check", delete_check)],
    #     states={DELETE_CHECK_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_check_confirm)]},
    #     fallbacks=[CommandHandler("cancel", cancel)],
    # ))
    # app.add_handler(ConversationHandler(
    #     entry_points=[CommandHandler("delete_item", delete_item)],
    #     states={DELETE_ITEM_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_item_confirm)]},
    #     fallbacks=[CommandHandler("cancel", cancel)],
    # ))
    # app.add_handler(ConversationHandler(
    #     entry_points=[CommandHandler("report_all", report_all)],
    #     states={REPORT_ALL_FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, report_all_from)],
    #             REPORT_ALL_TO:    [MessageHandler(filters.TEXT & ~filters.COMMAND, report_all_to)]},
    #     fallbacks=[CommandHandler("cancel", cancel)],
    # ))


    # Добавляем обработчик ошибок
    app.add_error_handler(error_handler)

    # Запуск webhook
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=f"/{BOT_TOKEN}",
        webhook_url=f"{HOST_URL}/{BOT_TOKEN}"
    )

if __name__ == "__main__":
    main()
