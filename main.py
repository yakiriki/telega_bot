import logging
import os
import pytesseract
import sqlite3
from datetime import datetime
from PIL import Image
from io import BytesIO
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes, CommandHandler

from utils.ocr import extract_text_from_image
from utils.parser import parse_receipt_text
from db.database import init_db, insert_expense, get_daily_summary

TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

init_db()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привіт! Надішли мені фото чека. /summary — витрати за сьогодні")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = await update.message.photo[-1].get_file()
    photo_bytes = await photo_file.download_as_bytearray()
    image = Image.open(BytesIO(photo_bytes))
    text = extract_text_from_image(image)
    logger.info(f"Розпізнаний текст:\n{text}")

    items = parse_receipt_text(text)
    if not items:
        await update.message.reply_text("Не вдалося розпізнати чек. Спробуй інше фото.")
        return

    total = 0
    for name, price, category in items:
        insert_expense(update.effective_user.id, name, price, category)
        total += price

    reply_lines = [f"Збережено {len(items)} позицій. Загальна сума: {total:.2f} грн"]
    for name, price, category in items:
        reply_lines.append(f"{name}: {price:.2f} грн ({category})")
    await update.message.reply_text("\n".join(reply_lines))

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_daily_summary(update.effective_user.id)
    if not data:
        await update.message.reply_text("Ще немає збережених витрат.")
        return

    lines = ["📊 Витрати за сьогодні:"]
    total = 0
    for category, amount in data:
        lines.append(f"{category}: {amount:.2f} грн")
        total += amount
    lines.append(f"Загалом: {total:.2f} грн")
    await update.message.reply_text("\n".join(lines))

# Оновлений блок запуску:
import asyncio

if __name__ == "__main__":
    async def main():
        app = ApplicationBuilder().token(TOKEN).build()
        await app.bot.delete_webhook(drop_pending_updates=True)
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("summary", summary))
        app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        logger.info("Бот запущено...")
        await app.run_polling()

    asyncio.run(main())
