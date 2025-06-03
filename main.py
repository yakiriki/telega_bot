import logging
import os
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, Document
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
)
import xml.etree.ElementTree as ET
import asyncio
import nest_asyncio  # ✅ Додаємо

from db.database import init_db, insert_expense, get_summary, delete_item, delete_receipt, get_all_expenses
from utils.parser import parse_xml
from utils.categorizer import categorize_item

# ✅ Патчимо активний loop, щоб уникнути помилок
nest_asyncio.apply()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")

init_db()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! Надішли XML-файл, текст або URL з чеком.\n"
        "🧾 /summary_day — витрати за день\n"
        "📅 /summary_week — за тиждень\n"
        "📆 /summary_month — за місяць\n"
        "➕ /add назва,ціна,категорія — вручну додати\n"
        "🗑️ /delete_item ID — видалити товар\n"
        "🗑️ /delete_receipt ID — видалити чек\n"
        "🐞 /debug — показати всі збережені позиції"
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower().startswith("http") and text.lower().endswith(".xml"):
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                r = await client.get(text)
                r.raise_for_status()
            text = r.text
        except Exception:
            await update.message.reply_text("Помилка при завантаженні XML за URL.")
            return

    if "<CHECK" in text:
        await process_xml(update, text)
    else:
        await update.message.reply_text("Надішли XML або скористайся командою.")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file: Document = update.message.document
    if not file.file_name.lower().endswith(".xml"):
        await update.message.reply_text("Потрібен .xml файл.")
        return
    file_obj = await file.get_file()
    file_data = await file_obj.download_as_bytearray()
    text = file_data.decode("windows-1251", errors="ignore")
    await process_xml(update, text)

async def process_xml(update: Update, text: str):
    try:
        root = ET.fromstring(text)
        items, total, receipt_id = parse_xml(root)
        user_id = update.effective_user.id
        for name, price in items:
            category = categorize_item(name)
            insert_expense(user_id, name, price, category, receipt_id)
        reply = [f"✅ Збережено {len(items)} позицій на суму {total:.2f} грн"]
        for idx, (name, price) in enumerate(items, 1):
            reply.append(f"{idx}. {name} — {price:.2f} грн")
        reply.append(f"🧾 ID чеку: {receipt_id}")
        await update.message.reply_text("\n".join(reply))
    except Exception as e:
        logger.exception(e)
        await update.message.reply_text("Помилка при обробці XML.")

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE, days: int):
    user_id = update.effective_user.id
    start_date = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    rows = get_summary(user_id, start_date)
    if not rows:
        await update.message.reply_text("Немає даних.")
        return
    reply = ["📊 Витрати:"]
    total = 0
    for cat, amt in rows:
        total += amt
        reply.append(f"{cat}: {amt:.2f} грн")
    reply.append(f"Загалом: {total:.2f} грн")
    await update.message.reply_text("\n".join(reply))

async def summary_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await summary(update, context, 1)

async def summary_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await summary(update, context, 7)

async def summary_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await summary(update, context, 30)

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = update.message.text.replace("/add", "", 1).strip().split(",")
        if len(args) != 3:
            raise ValueError
        name, price, category = args
        price = float(price)
        insert_expense(update.effective_user.id, name, price, category, "manual")
        await update.message.reply_text("✅ Додано вручну.")
    except Exception:
        await update.message.reply_text("Формат: /add назва,ціна,категорія")

async def delete_item_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        item_id = int(context.args[0])
        delete_item(item_id)
        await update.message.reply_text(f"🗑️ Товар {item_id} видалено.")
    except:
        await update.message.reply_text("Формат: /delete_item ID")

async def delete_receipt_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        receipt_id = context.args[0]
        delete_receipt(receipt_id)
        await update.message.reply_text(f"🗑️ Чек {receipt_id} видалено.")
    except:
        await update.message.reply_text("Формат: /delete_receipt ID")

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rows = get_all_expenses(user_id)
    if not rows:
        await update.message.reply_text("Нічого не знайдено.")
        return
    reply = ["🐞 Всі витрати:"]
    for r in rows[-20:]:
        reply.append(f"{r[0]}: {r[2]} — {r[3]:.2f} грн ({r[4]}) чек {r[6]}")
    await update.message.reply_text("\n".join(reply))

async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    await app.bot.delete_webhook(drop_pending_updates=True)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("summary_day", summary_day))
    app.add_handler(CommandHandler("summary_week", summary_week))
    app.add_handler(CommandHandler("summary_month", summary_month))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("delete_item", delete_item_cmd))
    app.add_handler(CommandHandler("delete_receipt", delete_receipt_cmd))
    app.add_handler(CommandHandler("debug", debug))
    app.add_handler(MessageHandler(filters.Document.XML, handle_file))
    app.add_handler(MessageHandler(filters.TEXT, handle_text))

    print("✅ Бот запущено")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
