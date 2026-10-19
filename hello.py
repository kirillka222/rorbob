from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
import asyncio
import json
import os
import html

# Токен берётся из переменной окружения BOT_TOKEN (или впишите сюда новый токен)
BOT_TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬТЕ_НОВЫЙ_ТОКЕН")

# ID администраторов, которым разрешено настраивать приветствие
ADMIN_IDS = {7241565564}

# Список каналов, которые обслуживает бот
CHANNEL_IDS = {
    -1004304760994,
    -1004292771066,
    -1003990396841,
    -1001729433926,
    -1001852999100,
    -1001203335448,
}

CONFIG_FILE = "welcome_config.json"
SENT_FILE = "sent_users.json"

SLOTS = (1, 2)  # два приветственных сообщения
DELAY_BETWEEN = 0.7  # пауза между первым и вторым сообщением, сек

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ---------- Хранилище конфига приветствий ----------

def get_default_welcome() -> dict:
    default_text = (
        "{name}, ❗️ВНИМАНИЕ❗️\n\n"
        "Чтобы заявка была обработана, пожалуйста, "
        "<b>подтвердите что являетесь совершеннолетним</b>🔞"
    )
    default_buttons = [[{"text": "ДА, МНЕ ЕСТЬ 18 ✅", "url": "https://t.me/+EOn1NhliSBc3MzQ5"}]]
    return {
        "enabled": True,
        "text": default_text,
        "media_type": None,
        "media_file_id": None,
        "buttons": default_buttons,
    }


def normalize_config(raw: dict | None) -> dict:
    """Приводит конфиг к виду {"welcomes": [w1, w2]}.
    Старый формат (одно приветствие в корне) автоматически становится сообщением №1."""
    welcomes = []
    if raw:
        if "welcomes" in raw:
            welcomes = list(raw["welcomes"])
        elif "text" in raw:  # старый формат
            old = dict(raw)
            old["enabled"] = True
            welcomes = [old]

    result = []
    for i in range(len(SLOTS)):
        if i < len(welcomes) and welcomes[i]:
            w = dict(welcomes[i])
            w.setdefault("enabled", True)
            w.setdefault("media_type", None)
            w.setdefault("media_file_id", None)
            w.setdefault("buttons", [])
            if not w.get("text", "").strip():
                w["text"] = get_default_welcome()["text"]
        else:
            w = get_default_welcome()
            # второе сообщение по умолчанию выключено, пока его не настроят
            w["enabled"] = (i == 0)
        result.append(w)
    return {"welcomes": result}


def load_config() -> dict:
    raw = None
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    return normalize_config(raw)


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


def parse_slot(command: CommandObject) -> int | None:
    arg = (command.args or "").strip()
    if arg.isdigit() and int(arg) in SLOTS:
        return int(arg)
    return None


@dp.message(Command("setwelcome"))
async def cmd_setwelcome(message: types.Message, state: FSMContext, command: CommandObject):
    if message.from_user.id not in ADMIN_IDS:
        return
    slot = parse_slot(command)
    if slot is None:
        await message.answer(
            "Укажите номер приветствия:\n"
            "/setwelcome 1 — первое сообщение\n"
            "/setwelcome 2 — второе сообщение\n\n"
            "Другие команды:\n"
            "/previewwelcome — показать оба (или /previewwelcome 1, /previewwelcome 2)\n"
            "/delwelcome 2 — выключить второе сообщение"
        )
        return

    current = load_config()["welcomes"][slot - 1]
    await state.clear()
    await state.update_data(slot=slot, current_text=current.get("text", ""))
    await state.set_state(SetWelcome.waiting_text)
    await message.answer(
        f"Настройка приветствия №{slot}.\n\n"
        "Отправьте текст приветственного сообщения.\n"
        "Можно использовать обычное форматирование Telegram (жирный, ссылки и т.д.). "
        "{name} заменится на имя пользователя.\n"
        "Чтобы оставить текущий текст без изменений — отправьте «-»."
    )


@dp.message(SetWelcome.waiting_text, F.text)
async def set_text(message: types.Message, state: FSMContext):
    if message.text.strip() == "-":
        data = await state.get_data()
        new_text = data.get("current_text", "")
        if not new_text.strip():
            new_text = get_default_welcome()["text"]
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


@dp.message(SetWelcome.waiting_buttons, F.text)
async def set_buttons(message: types.Message, state: FSMContext):
    raw = message.text.strip()
    data = await state.get_data()
    slot = data.get("slot", 1)

    config = load_config()

    if raw == "-":
        buttons = config["welcomes"][slot - 1].get("buttons", [])
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

    config["welcomes"][slot - 1] = {
        "enabled": True,
        "text": data.get("text", ""),
        "media_type": data.get("media_type"),
        "media_file_id": data.get("media_file_id"),
        "buttons": buttons,
    }
    save_config(config)
    await state.clear()

    await message.answer(
        f"Готово! Приветствие №{slot} сохранено. Проверить — /previewwelcome {slot}"
    )


@dp.message(Command("delwelcome"))
async def cmd_delwelcome(message: types.Message, command: CommandObject):
    if message.from_user.id not in ADMIN_IDS:
        return
    slot = parse_slot(command)
    if slot is None:
        await message.answer("Укажите номер: /delwelcome 2")
        return
    if slot == 1:
        await message.answer("Первое сообщение выключить нельзя — измените его через /setwelcome 1.")
        return
    config = load_config()
    config["welcomes"][slot - 1]["enabled"] = False
    save_config(config)
    await message.answer(f"Приветствие №{slot} выключено. Включить снова — /setwelcome {slot}")


@dp.message(Command("previewwelcome"))
async def cmd_preview(message: types.Message, command: CommandObject):
    if message.from_user.id not in ADMIN_IDS:
        return
    config = load_config()
    slot = parse_slot(command)
    welcomes = config["welcomes"]

    if slot is not None:
        await send_one(message.chat.id, welcomes[slot - 1], message.from_user.full_name)
    else:
        await send_all(message.chat.id, config, message.from_user.full_name)


# ---------- Отправка приветствий ----------

async def send_one(chat_id: int, welcome: dict, user_name: str = ""):
    keyboard = build_keyboard(welcome.get("buttons", []))
    media_type = welcome.get("media_type")

    # Подставляем имя заявителя вместо {name}, экранируя спецсимволы HTML
    text = welcome["text"].replace("{name}", html.escape(user_name))
    if not text.strip():
        text = get_default_welcome()["text"].replace("{name}", html.escape(user_name))

    if media_type == "photo":
        await bot.send_photo(chat_id, welcome["media_file_id"], caption=text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    elif media_type == "video":
        await bot.send_video(chat_id, welcome["media_file_id"], caption=text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    else:
        await bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


async def send_all(chat_id: int, config: dict, user_name: str = ""):
    """Отправляет все включённые приветствия по порядку: №1, затем №2."""
    first = True
    for welcome in config["welcomes"]:
        if not welcome.get("enabled", True):
            continue
        if not first:
            await asyncio.sleep(DELAY_BETWEEN)
        await send_one(chat_id, welcome, user_name)
        first = False


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
        await send_all(user_id, config, user_name=request.from_user.full_name)
        sent_users.add(user_id)
        save_sent(sent_users)
    except Exception:
        pass  # например, пользователь заблокировал бота

    # approve/decline не вызываем — решение принимаете вручную в приложении


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())