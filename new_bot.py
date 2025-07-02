import re
import requests
import asyncio
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from telegram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

BOT_TOKEN = '7044099465:AAEKAmQZ5B-JFNLZgA5Ze661m6_FzQCpa4Y'
USER_CHAT_ID = '191742166'

bot = Bot(token=BOT_TOKEN)

CONDITIONS = {
    "ясно": "ну, всё ясно ",
    "малооблачно": "чучутка облачно 🌤",
    "облачно с прояснениями": "чучутка облачно 🌤",
    "облачно": "так себе, облачно ☁️",
    "пасмурно": "ну такое пасмурное 🌥",
    "небольшой дождь": "чуть-чуть дождь 🌦",
    "дождь": "дощь 🌧",
    "сильный дождь": "того всё какой дождь 🌧",
    "снег": "снег ❄️",
    "гроза": "гроза ⚡️",
}

RU_PARTS = {
    'morning': 'Утром',
    'day': 'Днём',
    'evening': 'Вечером',
}

ICONS = {
    'morning': '🌅',
    'day': '🌤',
    'evening': '🌇',
}


def fetch_forecast_from_html():
    url = "https://yandex.ru/pogoda/moscow/details"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ru-RU,ru;q=0.9"
    }

    response = requests.get(url, headers=headers, timeout=10)
    soup = BeautifulSoup(response.text, "html.parser")

    article = soup.select_one('article[data-day="2_3"]')
    if not article:
        raise Exception("Не найден блок <article> с data-day='2_3'")

    heading = article.find("h3")
    date_str = "неизвестно"
    if heading:
        match = re.search(r"\d{1,2}\s+[а-яё]+", heading.text.strip().lower())
        if match:
            date_str = match.group(0).capitalize()

    mapping = {'m': 'morning', 'd': 'day', 'e': 'evening'}
    result = []

    for prefix, key in mapping.items():
        part = article.select_one(f'[style="grid-area:{prefix}-part"]')
        temp = article.select_one(f'[style="grid-area:{prefix}-temp"]')
        text = article.select_one(f'[style="grid-area:{prefix}-text"]')
        feels = article.select_one(f'[style="grid-area:{prefix}-feels"]')
        if not (part and temp and text and feels):
            continue

        emoji = ICONS.get(key, '❓')
        cond = CONDITIONS.get(text.text.strip().lower(), text.text.strip().lower())
        result.append(
            f"{emoji} {RU_PARTS[key]}: {temp.text.strip()} (по ощущениям {feels.text.strip()}), {cond}"
        )

    return f"📅 Прогноз на томороу  ☺️({date_str}):\n\n" + "\n".join(result)


async def send_tomorrow_weather():
    try:
        forecast = fetch_forecast_from_html()
        await bot.send_message(chat_id=USER_CHAT_ID, text=forecast)
    except Exception as e:
        await bot.send_message(chat_id=USER_CHAT_ID, text=f"⚠️ Ошибка прогноза на завтра: {e}")


async def send_today_weather():
    await bot.send_message(chat_id=USER_CHAT_ID, text="🌤 Прогноз на сегодня недоступен.")


async def main():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_today_weather, trigger='cron', hour=8, minute=45)
    scheduler.add_job(send_tomorrow_weather, trigger='cron', hour=14, minute=26)
    scheduler.start()

    print("🤖 Бот запущен.")
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
