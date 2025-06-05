import os
import logging
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InputFile, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

from bot.parsers.xml_parser import parse_xml_file, parse_xml_string, parse_xml_url
from bot.utils.db import init_db, save_items_to_db, get_report, get_debug_info, delete_check_by_id, delete_item_by_id
from bot.utils.categories import categorize

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = "expenses.db"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WAITING_NAME, WAITING_PRICE = range(2)
manual_data = {}

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
        "/delete_item — видалити товар"
    )
    await update.message.reply_text(msg)

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.document.get_file()
    file_path = f"/tmp/{file.file_id}.xml"
    await file.download_to_drive(file_path)
    items = parse_xml_file(file
