import os
import logging
# from datetime import datetime # Не нужен для этой версии

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    # Мы убрали MessageHandler и ConversationHandler, чтобы минимизировать код
)

# Мы убрали все импорты, связанные с БД и парсерами, для этого теста
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
# DB_URL = os.getenv("DATABASE_URL") # Не используется в этой версии
PORT      = int(os.getenv("PORT", 8443))
HOST_URL  = os.getenv("RENDER_EXTERNAL_URL")

# Настраиваем логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Выводим настройки, чтобы убедиться, что они корректно считываются
logger.info(f"Настройки: PORT={PORT}, HOST_URL={HOST_URL}")

info_keyboard = ReplyKeyboardMarkup([["💡 Info"]], resize_keyboard=True)

# ===== Хендлеры (оставили только /start и /info) =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 Привіт! Я бот для обліку витрат по чеках.\n\n"
        "📌 Команди:\n"
        "/info — довідка\n"
        "\n⚠️ Работает только /start и /info. Остальное отключено для диагностики."
    )
    await update.message.reply_text(msg, reply_markup=info_keyboard)

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# НОВЫЙ ХЕНДЛЕР: для обработки ошибок
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Логирует ошибку и отправляет сообщение пользователю (если возможно)."""
    logger.error("Произошла ошибка при обработке обновления:", exc_info=context.error)
    # Если бот может ответить, он сообщит об ошибке
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Извините, произошла внутренняя ошибка. Попробуйте еще раз. "
                "Подробнее в логах Render."
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение об ошибке пользователю: {e}")


# ===== Main с run_webhook =====

def main():
    # Инициализация БД - ЗАКОММЕНТИРОВАНО
    # init_db(DB_URL)

    # Создаем объект приложения бота
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Регистрируем только базовые команды /start и /info
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("info", info))

    # ДОБАВЛЯЕМ ОБРАБОТЧИК ОШИБОК! Это очень важно.
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
