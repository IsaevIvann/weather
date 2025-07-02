import requests
import asyncio
from telegram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

BOT_TOKEN = '7044099465:AAEKAmQZ5B-JFNLZgA5Ze661m6_FzQCpa4Y'
USER_CHAT_ID = '457829882'
YANDEX_API_KEY = '4a121b0f-8711-4b93-8ec5-9b2a051e871d'

bot = Bot(token=BOT_TOKEN)

CONDITIONS = {
    "clear": "ну, всё ясно ☀️",
    "partly-cloudy": "чучутка облачно 🌤",
    "cloudy": "облачно ☁️",
    "overcast": "пасмурно 🌥",
    "light-rain": "чуть-чуть дождь 🌦",
    "rain": "дощь 🌧",
    "heavy-rain": "того всё какой дождь 🌧",
    "snow": "снег ❄️",
    "thunderstorm": "гроза ⚡️",
}

RU_PARTS = {
    'morning': 'Утром',
    'day': 'Днём',
    'evening': 'Вечером',
}

def fetch_forecast(index: int):
    lat = 55.7558
    lon = 37.6173
    headers = {
        "User-Agent": "Mozilla/5.0",
        "X-Yandex-API-Key": YANDEX_API_KEY
    }

    response = requests.get(
        f"https://api.weather.yandex.ru/v2/forecast?lat={lat}&lon={lon}&lang=ru_RU&limit=2",
        headers=headers,
        timeout=10
    )
    data = response.json()
    return data["forecasts"][index]  # 0 = сегодня, 1 = завтра

def format_forecast(forecast, title: str):
    date = forecast["date"]
    parts = forecast["parts"]

    def format_part(part_name, emoji):
        p = parts[part_name]
        temp = p["temp_avg"]
        cond = CONDITIONS.get(p["condition"], p["condition"])
        return f"{emoji} {RU_PARTS.get(part_name, part_name)}: {temp}°C, {cond}"

    return (
        f"📅 {title} ({date}):\n\n"
        f"{format_part('morning', '🌅')}\n"
        f"{format_part('day', '🌤')}\n"
        f"{format_part('evening', '🌇')}"
    )

async def send_today_weather():
    try:
        forecast = fetch_forecast(0)
        text = format_forecast(forecast, "Прогноз на сегодня")
    except Exception as e:
        text = f"⚠️ Ошибка прогноза на сегодня: {e}"
    await bot.send_message(chat_id=USER_CHAT_ID, text=text)

async def send_tomorrow_weather():
    try:
        forecast = fetch_forecast(1)
        text = format_forecast(forecast, "Прогноз на завтра")
    except Exception as e:
        text = f"⚠️ Ошибка прогноза на завтра: {e}"
    await bot.send_message(chat_id=USER_CHAT_ID, text=text)

async def main():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_today_weather, trigger='cron', hour=8, minute=45)
    scheduler.add_job(send_tomorrow_weather, trigger='cron', hour=19, minute=15)
    scheduler.start()

    print("🤖 Бот запущен. Прогноз утром в 7:00 и вечером в 19:00.")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
