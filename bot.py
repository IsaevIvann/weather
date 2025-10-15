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

    # 1) «Сегодня» в Москве, а не по часовому поясу сервера
    mz = timezone("Europe/Moscow")
    target_dt = datetime.now(mz).date() + timedelta(days=days_ahead)
    iso = target_dt.strftime("%Y-%m-%d")

    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # 2) Сначала — точное совпадение по data-day
    target_article = soup.select_one(f'article[data-day="{iso}"]')

    # 3) Если нет — подбираем ближайшую по дате из всех карточек
    if not target_article:
        closest = None
        best_delta = None
        for art in soup.select("article[data-day]"):
            try:
                d = datetime.strptime(art.get("data-day"), "%Y-%m-%d").date()
            except Exception:
                continue
            delta = abs((d - target_dt).days)
            if best_delta is None or delta < best_delta:
                closest, best_delta = art, delta
        target_article = closest

    # 4) Если и тут пусто — берём первую карточку на странице (обычно это сегодня)
    if not target_article:
        arts = soup.select("article[data-day]")
        if arts:
            target_article = arts[0]

    if not target_article:
        raise Exception(f"Не найден блок прогноза для даты {target_dt.strftime('%-d %B')}")

    # 5) Человеческая дата в русском виде
    months_ru = [
        "", "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    ]
    date_str = f"{target_dt.day} {months_ru[target_dt.month]}".capitalize()

    # 6) Разбор утро/день/вечер
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
    Яндекс / Дзен: requests + BeautifulSoup.
    Берём верхний общий абзац + ВСЕ разделы (Женщины/Любовь/Финансы…),
    исключая "Для мужчин". Каждый раздел с новой строки.
    Работает и для обычной страницы темы, и для Turbo.
    """
    suf = "na-segodnya" if day == "today" else "na-zavtra"
    urls = [
        "https://dzen.ru/topic/horoscope-skorpion",                         # обычная тема
        f"https://dzen.ru/media-turbo/topic/horoscope-skorpion-{suf}",      # turbo-страница на сегодня/завтра
        "https://dzen.ru/media-turbo/topic/horoscope-skorpion",             # общий turbo
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": "https://dzen.ru/",
        "Connection": "keep-alive",
    }

    def _clean(s: str) -> str:
        return re.sub(r"\s{2,}", " ", (s or "").replace("\xa0", " ").strip())

    last_err = None
    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            html = r.text
            if not html or len(html) < 500:
                last_err = "пустой ответ"
                continue

            soup = BeautifulSoup(html, "html.parser")

            # 1) Верхний общий абзац
            top = ""
            span = soup.select_one(
                'div[class^="topic-channel--horoscope-widget__textBlock-"] '
                'span[class^="topic-channel--rich-text__text-"]'
            )
            if span:
                top = _clean(span.get_text(" ", strip=True))

            # fallback — первый осмысленный <p>
            if not top:
                for p in soup.select("article p, main p, body p"):
                    t = _clean(p.get_text(" ", strip=True))
                    if t and len(t) > 30:
                        top = t
                        break

            # 2) Разделы (карточки)
            sections = []
            container = soup.select_one('div[class^="topic-channel--horoscope-widget__items-"]') or soup
            items = container.select('div[class^="topic-channel--horoscope-widget__item-"]')

            for it in items:
                title_el = it.select_one('div[class^="topic-channel--horoscope-widget__itemTitle-"]')
                text_el = it.select_one('div[class^="topic-channel--horoscope-widget__itemText-"]')

                title = _clean(title_el.get_text(" ", strip=True)) if title_el else ""
                if title.lower().startswith("для мужчин"):
                    continue  # ⛔️ пропускаем блок "Для мужчин"

                if text_el:
                    body = _clean(text_el.get_text(" ", strip=True))
                else:
                    parts = [
                        _clean(e.get_text(" ", strip=True))
                        for e in it.select("p, li")
                        if _clean(e.get_text(" ", strip=True))
                    ]
                    body = _clean(" ".join(parts))

                if title or body:
                    formatted = f"**{title}**\n{body}" if title else body
                    sections.append(formatted.strip())

            # 3) fallback: заголовки → параграфы
            if not sections:
                root = soup.select_one("article") or soup.select_one("main") or soup
                if root:
                    titles = root.find_all(["h2", "h3", "strong", "span"])
                    i = 0
                    while i < len(titles):
                        t = _clean(titles[i].get_text(" ", strip=True))
                        if not t or t.lower().startswith("для мужчин"):
                            i += 1
                            continue
                        body_parts = []
                        for sib in titles[i].next_siblings:
                            if getattr(sib, "name", None) in ["h2", "h3", "strong", "span"]:
                                break
                            if getattr(sib, "name", None) in ["p", "li", "div"]:
                                txt = BeautifulSoup(str(sib), "html.parser").get_text(" ", strip=True)
                                if txt:
                                    body_parts.append(txt)
                        body = _clean(" ".join(body_parts))
                        if body:
                            formatted = f"**{t}**\n{body}"
                            sections.append(formatted)
                        i += 1

            # 4) Форматирование
            chunks = []
            if top:
                chunks.append(top)
            if sections:
                chunks.append("\n\n".join(sections))

            result = "\n\n".join(chunks).strip()
            result = re.sub(r"\s{3,}", "\n\n", result)

            if result:
                return result

        except Exception as e:
            last_err = e
            continue

    return f"Не удалось получить гороскоп на сегодня 😕 (ошибка: {last_err})"




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
