import re
import requests
import asyncio
from bs4 import BeautifulSoup
from pytz import timezone
from telegram import Bot, Update, ReplyKeyboardMarkup
from telegram.ext import Application, MessageHandler, ContextTypes, CommandHandler, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta


BOT_TOKEN = '7044099465:AAEKAmQZ5B-JFNLZgA5Ze661m6_FzQCpa4Y'
USER_CHAT_IDS = ['457829882','191742166']

bot = Bot(token=BOT_TOKEN)

CONDITIONS = {
    "ясно": "ну, тут ваще всё ясно, малая может сиять ☀️🤙",
    "малооблачно": "чучутка облачно 🤏🌤",
    "облачно с прояснениями": "чучутка облачно + дэшка солнца 🤏+ 🌤",
    "облачно": "так себе, облачно 😶‍🌫",
    "пасмурно": "ну такое, пасмурное 💩",
    "небольшой дождь": "чуть-чуть дощь 😓🌦",
    "дождь": "дощь 😓 🌧",
    "сильный дождь": "того всё какой дощь 🌧",
    "снег": "снег ❄️🥶",
    "гроза": "гроза грозила, я уходила ⚡️",
}

RU_PARTS = {'morning': 'Утром', 'day': 'Днём', 'evening': 'Вечером'}
ICONS = {'morning': '🌅', 'day': '🏙️ ', 'evening': '🌙'}


def fetch_forecast_from_html(days_ahead: int = 1) -> str:
    url = "https://yandex.ru/pogoda/moscow/details"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    # целевая дата
    target_dt = datetime.now() + timedelta(days=days_ahead)
    iso = target_dt.strftime("%Y-%m-%d")
    months_ru = [
        "", "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    ]
    day = target_dt.day
    month = months_ru[target_dt.month]

    # 1) пробуем найти article по data-day
    target_article = soup.select_one(f'article[data-day="{iso}"]')

    # 2) если нет — ищем по заголовку (учитываем неразрывные пробелы и год)
    if not target_article:
        # заменим NBSP на обычные пробелы и поищем регуляркой
        def norm(t: str) -> str:
            return t.replace("\xa0", " ").strip() if t else ""
        date_re = re.compile(rf"\b{day}\s+{month}\b", re.IGNORECASE)

        for article in soup.select("article[data-day]"):
            h3 = article.find("h3")
            if h3 and date_re.search(norm(h3.get_text())):
                target_article = article
                break

    # 3) если всё ещё нет — возьмём ближайшую по дате карточку по data-day
    if not target_article:
        closest = None
        closest_delta = None
        for article in soup.select("article[data-day]"):
            try:
                adate = datetime.strptime(article.get("data-day"), "%Y-%m-%d")
            except Exception:
                continue
            delta = abs((adate - target_dt).days)
            if closest is None or delta < closest_delta:
                closest, closest_delta = article, delta
        target_article = closest

    if not target_article:
        raise Exception(f"Не найден блок прогноза для даты {day} {month}")

    # красивый заголовок (без года)
    date_str = f"{day} {month}".capitalize()

    # разбор утро/день/вечер
    mapping = {"m": "morning", "d": "day", "e": "evening"}
    RU_PARTS = {'morning': 'Утром', 'day': 'Днём', 'evening': 'Вечером'}
    ICONS = {'morning': '🌅', 'day': '🏙️ ', 'evening': '🌙'}

    result = []
    for prefix, key in mapping.items():
        part = target_article.select_one(f'[style="grid-area:{prefix}-part"]')
        temp = target_article.select_one(f'[style="grid-area:{prefix}-temp"]')
        text = target_article.select_one(f'[style="grid-area:{prefix}-text"]')
        feels = target_article.select_one(f'[style="grid-area:{prefix}-feels"]')
        if not (part and temp and text and feels):
            continue

        emoji = ICONS.get(key, "❓")
        cond_text = text.get_text(" ", strip=True)
        cond = CONDITIONS.get(cond_text.lower(), cond_text)
        result.append(
            f"{emoji} {RU_PARTS[key]}: {temp.get_text(strip=True)} (по ощущениям {feels.get_text(strip=True)}), {cond}"
        )

    if not result:
        raise Exception("Не удалось разобрать блоки утро/день/вечер")

    return f"📅 Прогноз на {date_str} 🔮:\n\n" + "\n\n".join(result)


def _clean(txt: str) -> str:
    return re.sub(r"\s{2,}", " ", (txt or "").strip())

def fetch_horoscope_yandex_all(day: str = "today") -> str:
    """
    Парсит все разделы с Дзена (включая общий блок и подразделы).
    """
    url = "https://dzen.ru/media-turbo/topic/horoscope-skorpion-na-segodnya"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ru-RU,ru;q=0.9",
    }

    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # Общий верхний текст
    top_block = soup.select_one("div.topic-channel--horoscope-widget__textBlock-10 span.topic-channel--rich-text__text-24")
    top_text = top_block.get_text(" ", strip=True) if top_block else ""

    # Все разделы (для женщин, любовь, финансы, мужчины и т.п.)
    items = soup.select("div.topic-channel--horoscope-widget__item-Ut")
    sections = []
    for it in items:
        title_el = it.select_one("div.topic-channel--horoscope-widget__itemTitle-3E")
        text_el = it.select_one("div.topic-channel--horoscope-widget__itemText-3X")

        title = title_el.get_text(" ", strip=True) if title_el else ""
        text = text_el.get_text(" ", strip=True) if text_el else ""

        if title or text:
            sections.append(f"{title}\n{text}".strip())

    result_parts = []
    if top_text:
        result_parts.append(top_text)
    if sections:
        result_parts.append("\n\n".join(sections))

    final_text = "\n\n".join(result_parts).strip()
    return final_text or "Не удалось получить гороскоп на сегодня 😕"


async def send_tomorrow_weather(bot_instance: Bot = None, chat_ids: list[str] = None):
    try:
        forecast = fetch_forecast_from_html(days_ahead=1)
        for chat_id in (chat_ids or USER_CHAT_IDS):
            await (bot_instance or bot).send_message(chat_id=chat_id, text=forecast)
    except Exception as e:
        for chat_id in (chat_ids or USER_CHAT_IDS):
            await (bot_instance or bot).send_message(chat_id=chat_id, text=f"⚠️ Ошибка прогноза на завтра: {e}")

async def send_today_weather(bot_instance: Bot = None, chat_ids: list[str] = None, include_horoscope: bool = False):
    try:
        forecast = fetch_forecast_from_html(days_ahead=0)
        if include_horoscope:
            try:
                horoscope = fetch_horoscope_yandex_all(day="today")
                forecast = f"{forecast}\n\n🔮 Гороскоп на сегодня:\n{horoscope}"
            except Exception as he:
                forecast = f"{forecast}\n\n🔮 Гороскоп на сегодня: не удалось получить ({he})"

        for chat_id in (chat_ids or USER_CHAT_IDS):
            await (bot_instance or bot).send_message(chat_id=chat_id, text=forecast)
    except Exception as e:
        for chat_id in (chat_ids or USER_CHAT_IDS):
            await (bot_instance or bot).send_message(chat_id=chat_id, text=f"⚠️ Ошибка прогноза на сегодня: {e}")


# ------------------- БОТ ------------------- #

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🌤 Прогноз на завтра":
        await send_tomorrow_weather(chat_ids=[update.effective_chat.id])
    elif update.message.text == "🌞 Прогноз на сегодня":
        await send_today_weather(chat_ids=[update.effective_chat.id], include_horoscope=True)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [["🌞 Прогноз на сегодня", "🌤 Прогноз на завтра"]]
    markup = ReplyKeyboardMarkup(kb, resize_keyboard=True)
    await update.message.reply_text("👋 Привет! Я покажу тебе прогноз погоды.", reply_markup=markup)

async def start_bot():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT, handle_button))

    loop = asyncio.get_running_loop()
    scheduler = AsyncIOScheduler(timezone=timezone("Europe/Moscow"))

    scheduler.add_job(
        lambda: asyncio.run_coroutine_threadsafe(send_today_weather(app.bot, include_horoscope=True), loop),
        trigger='cron',
        hour=7,
        minute=00
    )
    scheduler.add_job(
        lambda: asyncio.run_coroutine_threadsafe(send_tomorrow_weather(app.bot), loop),
        trigger='cron',
        hour=22,
        minute=30
    )

    scheduler.start()
    print("🤖 Бот запущен.")
    await app.run_polling()


if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()

    loop = asyncio.get_event_loop()
    loop.create_task(start_bot())
    loop.run_forever()
