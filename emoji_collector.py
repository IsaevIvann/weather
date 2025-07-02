import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters

BOT_TOKEN = '7044099465:AAEKAmQZ5B-JFNLZgA5Ze661m6_FzQCpa4Y'

async def handle_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        entities = update.message.entities or []
        for entity in entities:
            if entity.type == "custom_emoji":
                emoji_text = update.message.text[entity.offset:entity.offset + entity.length]
                emoji_id = entity.custom_emoji_id
                await update.message.reply_text(
                    f"🆔 ID для {emoji_text} — `{emoji_id}`",
                    parse_mode="Markdown"
                )

async def run_app():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & filters.Entity("custom_emoji"), handle_emoji))
    print("🆕 Бот для сбора эмодзи запущен. Отправь премиум-эмодзи сюда.")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await app.updater.idle()
    await app.stop()
    await app.shutdown()

if __name__ == "__main__":
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop = asyncio.get_event_loop()

    loop.create_task(run_app())
    loop.run_forever()
