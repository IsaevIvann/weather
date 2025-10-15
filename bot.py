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
HORO_SOURCE = "dzen_turbo"  # варианты: "dzen_turbo" | "mail"

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

RU_PARTS = {
    'morning': 'Утром',
    'day': 'Днём',
    'evening': 'Вечером',
}

ICONS = {
    'morning': '🌅',
    'day': '🏙️ ',
    'evening': '🌙',
}


def fetch_forecast_from_html(days_ahead: int = 1) -> str:
    url = "https://yandex.ru/pogoda/moscow/details"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ru-RU,ru;q=0.9"
    }

    response = requests.get(url, headers=headers, timeout=10)
    soup = BeautifulSoup(response.text, "html.parser")

    months_ru = [
        '', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
        'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
    ]

    target_date = datetime.now() + timedelta(days=days_ahead)
    day = target_date.day
    month = months_ru[target_date.month]
    date_pattern = re.compile(rf'\b{day}\s+{month}\b', re.IGNORECASE)

    target_article = None
    for article in soup.select("article[data-day]"):
        heading = article.find("h3")
        if heading and date_pattern.search(heading.text):
            target_article = article
            break

    if not target_article:
        raise Exception(f"Не найден блок <article> с датой '{day} {month}'")

    date_str = f"{day} {month}".capitalize()
    mapping = {'m': 'morning', 'd': 'day', 'e': 'evening'}
    result = []

    for prefix, key in mapping.items():
        part = target_article.select_one(f'[style="grid-area:{prefix}-part"]')
        temp = target_article.select_one(f'[style="grid-area:{prefix}-temp"]')
        text = target_article.select_one(f'[style="grid-area:{prefix}-text"]')
        feels = target_article.select_one(f'[style="grid-area:{prefix}-feels"]')
        if not (part and temp and text and feels):
            continue

        emoji = ICONS.get(key, '❓')
        cond = CONDITIONS.get(text.text.strip().lower(), text.text.strip().lower())
        result.append(
            f"{emoji} {RU_PARTS[key]}: {temp.text.strip()} (по ощущениям {feels.text.strip()}), {cond}"
        )

    return f"📅 Прогноз на {date_str} 🔮:\n\n" + "\n\n".join(result)


def fetch_horoscope_today(sign_slug: str = "scorpio") -> str:
    """
    Парсит основной текст гороскопа со страницы horo.mail.ru.
    Возвращает склеенный текст абзацев без служебных блоков.
    """
    url = f"https://horo.mail.ru/prediction/{sign_slug}/today/"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    containers = [
        soup.select_one('[itemprop="articleBody"]'),
        soup.select_one('.article__item_html'),
        soup.select_one('.article__text'),
        soup.select_one('[class*="article__text"]'),
    ]

    text_parts: list[str] = []
    for c in containers:
        if not c:
            continue
        for p in c.select('p'):
            t = p.get_text(" ", strip=True)
            if not t:
                continue
            if any(bad in t.lower() for bad in [
                "читайте также", "поделиться", "реклама", "mail.ru"
            ]):
                continue
            text_parts.append(t)
        if text_parts:
            break

    if not text_parts:
        og = soup.select_one('meta[property="og:description"]')
        if og and og.get("content"):
            return og["content"].strip()
        desc = soup.select_one('meta[name="description"]')
        if desc and desc.get("content"):
            return desc["content"].strip()
        return "Не удалось получить гороскоп на сегодня 😕"

    text = " ".join(text_parts)
    text = re.sub(r'\s{2,}', ' ', text).strip()
    return text


def fetch_horoscope_dzen_turbo(day: str = "today") -> str:
    """
    Парсит текст гороскопа из Turbo-страницы Дзена для Скорпиона (без JS).
    Работает с обычным requests + BeautifulSoup.
    day: "today" | "tomorrow"
    """
    suf = "na-segodnya" if day == "today" else "na-zavtra"
    url = f"https://dzen.ru/media-turbo/topic/horoscope-skorpion-{suf}"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    containers = [
        soup.select_one('[itemprop="articleBody"]'),
        soup.select_one('article'),
        soup.select_one('div[role="article"]'),
        soup.select_one('section article'),
        soup.select_one('main'),
        soup  # последний шанс — весь документ
    ]

    parts: list[str] = []
    for c in containers:
        if not c:
            continue
        ps = c.select('p')
        if not ps:
            continue
        for p in ps:
            t = p.get_text(" ", strip=True)
            if not t:
                continue
            low = t.lower()
            if any(bad in low for bad in ["читайте также", "поделиться", "реклама", "яндекс дзен"]):
                continue
            parts.append(t)
        if parts:
            break

    if not parts:
        for sel in ('meta[property="og:description"]', 'meta[name="description"]'):
            m = soup.select_one(sel)
            if m and m.get("content"):
                return m["content"].strip()
        return "Не удалось получить гороскоп на сегодня 😕"

    text = " ".join(parts)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


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
                if HORO_SOURCE == "dzen_turbo":
                    horoscope = fetch_horoscope_dzen_turbo(day="today")
                else:
                    horoscope = fetch_horoscope_today(sign_slug="scorpio")
                forecast = f"{forecast}\n\n🔮 Гороскоп на сегодня:\n{horoscope}"
            except Exception as he:
                # если гороскоп не распарсился — просто отправим погоду и мягкую пометку
                forecast = f"{forecast}\n\n🔮 Гороскоп на сегодня: не удалось получить ({he})"

        for chat_id in (chat_ids or USER_CHAT_IDS):
            await (bot_instance or bot).send_message(chat_id=chat_id, text=forecast)
    except Exception as e:
        for chat_id in (chat_ids or USER_CHAT_IDS):
            await (bot_instance or bot).send_message(chat_id=chat_id, text=f"⚠️ Ошибка прогноза на сегодня: {e}")


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🌤 Прогноз на завтра":
        await send_tomorrow_weather(chat_ids=[update.effective_chat.id])
    elif update.message.text == "🌞 Прогноз на сегодня":
        # присылаем погоду + гороскоп
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
