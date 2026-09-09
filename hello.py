from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
import asyncio
import json
import os
import html

BOT_TOKEN = "8550210786:AAHWjiDYi2VjppatfmqWooPCqYLolRqywIA"

# ID администраторов, которым разрешено настраивать приветствие
ADMIN_IDS = {7241565564}

# Список каналов, которые обслуживает бот
CHANNEL_IDS = {
    -1004304760994,
    -1004292771066,
    -1003990396841,
}

CONFIG_FILE = "welcome_config.json"
SENT_FILE = "sent_users.json"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ---------- Хранилище конфига приветствия ----------

def get_default_config() -> dict:
    default_text = (
        "{name}, ❗️ВНИМАНИЕ❗️\n\n"
        "Чтобы заявка была обработана, пожалуйста, "
        "<b>подтвердите что являетесь совершеннолетним</b>🔞"
    )
    default_buttons = [[{"text": "ДА, МНЕ ЕСТЬ 18 ✅", "url": "https://t.me/kruzhook_bot?start=8743547024"}]]
    return {"text": default_text, "media_type": None, "media_file_id": None, "buttons": default_buttons}


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
        # Подстраховка: если текст пустой (например, из-за старого бага), подставляем дефолтный
        if not config.get("text", "").strip():
            config["text"] = get_default_config()["text"]
        return config
    return get_default_config()

def save_config(config: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# ---------- Хранилище отправленных пользователей (антидубль) ----------

def load_sent() -> set:
    if os.path.exists(SENT_FILE):
        with open(SENT_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_sent(sent_users: set):
    with open(SENT_FILE, "w") as f:
        json.dump(list(sent_users), f)

sent_users = load_sent()


# ---------- FSM для настройки приветствия ----------

class SetWelcome(StatesGroup):
    waiting_text = State()
    waiting_media = State()
    waiting_buttons = State()


def build_keyboard(buttons: list) -> InlineKeyboardMarkup | None:
    """buttons — список списков [{text, url}, ...] (каждый вложенный список = ряд кнопок)"""
    if not buttons:
        return None
    rows = []
    for row in buttons:
        rows.append([InlineKeyboardButton(text=b["text"], url=b["url"]) for b in row])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.message(Command("setwelcome"))
async def cmd_setwelcome(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    # Запоминаем текущий текст, чтобы можно было оставить его без изменений через "-"
    current_config = load_config()
    await state.update_data(current_text=current_config.get("text", ""))
    await state.set_state(SetWelcome.waiting_text)
    await message.answer(
        "Отправьте текст приветственного сообщения.\n"
        "Можно использовать обычное форматирование Telegram (жирный, ссылки и т.д.).\n"
        "Чтобы оставить текущий текст без изменений — отправьте «-»."
    )


@dp.message(SetWelcome.waiting_text, F.text)
async def set_text(message: types.Message, state: FSMContext):
    if message.text.strip() == "-":
        data = await state.get_data()
        new_text = data.get("current_text", "")
        if not new_text.strip():
            new_text = get_default_config()["text"]
    else:
        new_text = message.html_text
    await state.update_data(text=new_text)
    await state.set_state(SetWelcome.waiting_media)
    await message.answer(
        "Теперь отправьте фото или видео для сообщения.\n"
        "Если медиа не нужно — напишите «-»."
    )


@dp.message(SetWelcome.waiting_text)
async def set_text_wrong_type(message: types.Message):
    await message.answer(
        "На этом шаге нужен именно текст сообщения (или «-», чтобы оставить текущий).\n"
        "Фото/видео будет на следующем шаге — отправьте текст сначала."
    )


@dp.message(SetWelcome.waiting_media, F.photo)
async def set_media_photo(message: types.Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await state.update_data(media_type="photo", media_file_id=file_id)
    await ask_buttons(message, state)


@dp.message(SetWelcome.waiting_media, F.video)
async def set_media_video(message: types.Message, state: FSMContext):
    file_id = message.video.file_id
    await state.update_data(media_type="video", media_file_id=file_id)
    await ask_buttons(message, state)


@dp.message(SetWelcome.waiting_media, F.text == "-")
async def set_media_skip(message: types.Message, state: FSMContext):
    await state.update_data(media_type=None, media_file_id=None)
    await ask_buttons(message, state)


async def ask_buttons(message: types.Message, state: FSMContext):
    await state.set_state(SetWelcome.waiting_buttons)
    await message.answer(
        "Теперь добавьте кнопки.\n"
        "Формат: одна кнопка на строку — «Текст кнопки - https://ссылка».\n"
        "Кнопки на одной строке через « | » окажутся в одном ряду:\n"
        "«Канал - https://t.me/channel | Сайт - https://site.com»\n\n"
        "Чтобы оставить текущие кнопки без изменений — отправьте «-».\n"
        "Чтобы убрать кнопки совсем — отправьте «убрать»."
    )


@dp.message(SetWelcome.waiting_buttons)
async def set_buttons(message: types.Message, state: FSMContext):
    raw = message.text.strip()

    if raw == "-":
        # Оставляем текущие кнопки без изменений
        current_config = load_config()
        buttons = current_config.get("buttons", [])
    elif raw == "убрать":
        buttons = []
    else:
        buttons = []
        for line in raw.split("\n"):
            row = []
            for part in line.split("|"):
                part = part.strip()
                if " - " not in part:
                    continue
                text, url = part.rsplit(" - ", 1)
                row.append({"text": text.strip(), "url": url.strip()})
            if row:
                buttons.append(row)

    data = await state.get_data()
    config = {
        "text": data.get("text", ""),
        "media_type": data.get("media_type"),
        "media_file_id": data.get("media_file_id"),
        "buttons": buttons,
    }
    save_config(config)
    await state.clear()

    await message.answer("Готово! Приветственное сообщение сохранено. Проверить — /previewwelcome")


@dp.message(Command("previewwelcome"))
async def cmd_preview(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    config = load_config()
    await send_welcome(message.chat.id, config, user_name=message.from_user.full_name)


# ---------- Отправка приветствия ----------

async def send_welcome(chat_id: int, config: dict, user_name: str = ""):
    keyboard = build_keyboard(config.get("buttons", []))
    media_type = config.get("media_type")

    # Подставляем ник заявителя вместо {name}, экранируя спецсимволы HTML
    text = config["text"].replace("{name}", html.escape(user_name))
    if not text.strip():
        text = get_default_config()["text"].replace("{name}", html.escape(user_name))

    if media_type == "photo":
        await bot.send_photo(chat_id, config["media_file_id"], caption=text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    elif media_type == "video":
        await bot.send_video(chat_id, config["media_file_id"], caption=text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    else:
        await bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


# ---------- Обработка заявок на вступление ----------

@dp.chat_join_request()
async def handle_join_request(request: types.ChatJoinRequest):
    if request.chat.id not in CHANNEL_IDS:
        return

    user_id = request.from_user.id
    if user_id in sent_users:
        return  # уже отправляли этому пользователю

    config = load_config()
    try:
        await send_welcome(user_id, config, user_name=request.from_user.full_name)
        sent_users.add(user_id)
        save_sent(sent_users)
    except Exception:
        pass  # например, пользователь заблокировал бота

    # approve/decline не вызываем — решение принимаете вручную в приложении


async def main():
    await dp.start_polling(bot)

asyncio.run(main())

# ДА, МНЕ ЕСТЬ 18 ✅ - https://t.me/kruzhook_bot?start=8743547024