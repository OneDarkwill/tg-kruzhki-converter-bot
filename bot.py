import os
import sys
import asyncio
import logging
import tempfile
import subprocess
import json
from pathlib import Path

import imageio_ffmpeg
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8702729906:AAG-6EDd1Y1LddEgtMcducS_kznETVB2YeU")
PORT = int(os.getenv("PORT", 7860))  # Порт для Hugging Face Spaces

CHANNEL_USERNAME = "@money17ru"
SPONSOR_BOT_USERNAME = "DarkWillVPN_bot"

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 МБ — лимит Telegram Bot API

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
USERS_FILE = DATA_DIR / "users.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(message)s"
)
logger = logging.getLogger(__name__)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Получаем путь к FFmpeg (с поддержкой Docker/Linux)
try:
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_PATH = "ffmpeg"
logger.info(f"FFmpeg подключен: {FFMPEG_PATH}")

def load_users() -> set:
    if USERS_FILE.exists():
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_user(user_id: int):
    users = load_users()
    if user_id not in users:
        users.add(user_id)
        try:
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                json.dump(list(users), f)
        except Exception as e:
            logger.error(f"Ошибка сохранения пользователя: {e}")

async def is_subscribed(user_id: int) -> bool:
    """Проверяет подписку на канал. Бот должен быть администратором в @money17ru."""
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ["creator", "administrator", "member", "restricted"]
    except Exception as e:
        logger.warning(f"Ошибка проверки подписки: {e}")
        return False

def get_subscription_keyboard() -> InlineKeyboardMarkup:
    """Минималистичная клавиатура подписки"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Нажать /start",
                    url=f"https://t.me/{SPONSOR_BOT_USERNAME}?start=kruzhok"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Подписаться",
                    url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="☑️ Проверить",
                    callback_data="check_subscription"
                )
            ]
        ]
    )

def get_start_keyboard(bot_username: str) -> InlineKeyboardMarkup:
    """Кнопка для шеринга с друзьями"""
    share_url = f"https://t.me/share/url?url=https://t.me/{bot_username}&text=%D0%A1%D0%BC%D0%BE%D1%82%D1%80%D0%B8%2C%20%D1%8D%D1%82%D0%BE%D1%82%20%D0%B1%D0%BE%D1%82%20%D0%B4%D0%B5%D0%BB%D0%B0%D0%B5%D1%82%20%D0%BA%D1%80%D1%83%D0%B6%D0%BE%D1%87%D0%BA%D0%B8%20%D0%B8%D0%B7%20%D0%BB%D1%8E%D0%B1%D1%8B%D1%85%20%D0%B2%D0%B8%D0%B4%D0%B5%D0%BE%21"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🚀 Поделиться с другом", url=share_url)
            ]
        ]
    )

AUTH_TEXT = "Для доступа к боту выполните условия:"

VERIFY_SUCCESS_TEXT = (
    "✨ <b>Вы успешно выполнили задания, доступ к боту получен.</b>\n\n"
    "🚀 <b>Вам доступна конвертация Ultra HD:</b>\n"
    "• Поддержка <b>60 FPS</b> и <b>120 FPS</b> (максимальная плавность)\n"
    "• Обработка исходников <b>4K & Full HD</b> без мыла\n\n"
    "📹 <b>Отправьте ваше видео</b>, которое надо конвертировать в кружок."
)

WELCOME_TEXT = (
    "🎬 <b>Ultra HD Конвертер в кружочки</b>\n\n"
    "Сервис моментальной конвертации видео любого разрешения в кружочки Telegram:\n\n"
    "⚡️ Поддержка <b>60 FPS</b> и <b>120 FPS</b>\n"
    "💎 Обработка <b>4K & Full HD</b> видео\n"
    "🎯 Точная центровка и максимальная чёткость\n\n"
    "📹 <b>Отправьте видео</b>, чтобы сделать кругляш!"
)

@dp.message(CommandStart())
async def cmd_start(message: Message):
    save_user(message.from_user.id)

    if not await is_subscribed(message.from_user.id):
        await message.answer(AUTH_TEXT, reply_markup=get_subscription_keyboard())
        return

    bot_info = await bot.get_me()
    await message.answer(WELCOME_TEXT, reply_markup=get_start_keyboard(bot_info.username or ""))

@dp.callback_query(F.data == "check_subscription")
async def on_check_subscription(callback: CallbackQuery):
    user_id = callback.from_user.id
    if await is_subscribed(user_id):
        await callback.answer()
        bot_info = await bot.get_me()
        await callback.message.edit_text(
            VERIFY_SUCCESS_TEXT,
            reply_markup=get_start_keyboard(bot_info.username or "")
        )
    else:
        await callback.answer(
            f"❌ Подпишитесь на канал @{CHANNEL_USERNAME.lstrip('@')} и нажмите «☑️ Проверить» снова.",
            show_alert=True
        )

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    users = load_users()
    await message.answer(f"📊 Пользователей в базе: <b>{len(users)}</b>")

def convert_to_video_note(input_path: str, output_path: str) -> bool:
    """Конвертация видео в формат кружочка Telegram с поддержкой 60/120 FPS и 4K"""
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-i", input_path,
        "-t", "60",
        "-vf", r"crop=min(iw\,ih):min(iw\,ih),scale=640:640:flags=lanczos,setsar=1",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_path
    ]
    process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return process.returncode == 0

@dp.message(F.video | F.document)
async def handle_video(message: Message):
    save_user(message.from_user.id)

    if not await is_subscribed(message.from_user.id):
        await message.reply(AUTH_TEXT, reply_markup=get_subscription_keyboard())
        return

    file_id = None
    file_name = "video.mp4"
    file_size = 0
    
    if message.video:
        file_id = message.video.file_id
        file_name = message.video.file_name or "video.mp4"
        file_size = message.video.file_size or 0
    elif message.document:
        mime = message.document.mime_type or ""
        doc_name = message.document.file_name or ""
        if mime.startswith("video/") or doc_name.lower().endswith((".mp4", ".mov", ".mkv", ".avi", ".webm")):
            file_id = message.document.file_id
            file_name = doc_name or "video.mp4"
            file_size = message.document.file_size or 0
        else:
            return
            
    if file_size > MAX_FILE_SIZE:
        size_mb = file_size / (1024 * 1024)
        await message.reply(
            f"⚠️ Файл слишком большой ({size_mb:.1f} МБ). Максимум 20 МБ.\n"
            "Сожмите видео при отправке в Telegram или выберите отрезок до 60 секунд."
        )
        return

    status_msg = await message.reply("⏳ <b>Обработка видео...</b>")

    with tempfile.TemporaryDirectory() as tmp_dir:
        input_path = os.path.join(tmp_dir, f"input_{file_name}")
        output_path = os.path.join(tmp_dir, "output_round.mp4")

        try:
            file_info = await bot.get_file(file_id)
            if not file_info.file_path:
                await status_msg.edit_text("❌ Ошибка при скачивании файла.")
                return

            await bot.download_file(file_info.file_path, input_path)

            loop = asyncio.get_running_loop()
            success = await loop.run_in_executor(None, convert_to_video_note, input_path, output_path)

            if not success or not os.path.exists(output_path):
                await status_msg.edit_text("❌ Не удалось сконвертировать видео.")
                return

            video_note_file = FSInputFile(output_path)
            await message.reply_video_note(video_note=video_note_file)
            await status_msg.delete()

        except TelegramBadRequest as e:
            logger.error(f"TelegramBadRequest: {e}")
            if "file is too big" in str(e).lower():
                await status_msg.edit_text("⚠️ Видео весит больше 20 МБ. Сожмите его перед отправкой.")
            else:
                await status_msg.edit_text("❌ Ошибка обработки Telegram.")
        except Exception as e:
            logger.error(f"Ошибка при обработке видео: {e}", exc_info=True)
            await status_msg.edit_text("❌ Произошла ошибка при конвертации видео.")

async def self_ping_task():
    """Фоновый пинг раз в 10 минут, чтобы Render никогда не уходил в спящий режим"""
    await asyncio.sleep(60)
    url = os.getenv("RENDER_EXTERNAL_URL", "https://tg-kruzhki-converter-bot.onrender.com")
    while True:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    logger.info(f"24/7 Keep-Alive пинг выполнен: {resp.status}")
        except Exception as e:
            logger.warning(f"Keep-Alive предупреждение: {e}")
        await asyncio.sleep(600)

async def start_web_server():
    """Легковесный сервер на порту 7860/10000 для проверки здоровья сервиса"""
    async def ping_handler(request):
        return web.Response(text="Bot is running OK 24/7!", status=200)

    app = web.Application()
    app.router.add_get("/", ping_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"Веб-сервер проверки здоровья запущен на 0.0.0.0:{PORT}")

async def main():
    bot_info = await bot.get_me()
    logger.info(f"Бот успешно запущен: @{bot_info.username} ({bot_info.first_name})")
    
    # Запускаем фоновый веб-сервер и автопингер для работы 24/7
    await start_web_server()
    asyncio.create_task(self_ping_task())

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
