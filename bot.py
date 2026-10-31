"""Telegram bot starter for Railway: python-telegram-bot, long polling.

Without AI settings it echoes messages. Set OPENAI_API_KEY (and OPENAI_BASE_URL
for OpenRouter, Groq, DeepSeek or any other OpenAI-compatible API) and it chats
with the model instead. Add your own handlers in main().
"""
import logging
import os
import time
from collections import defaultdict, deque

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import InvalidToken
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes,
                          MessageHandler, filters)

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=os.getenv("LOG_LEVEL", "INFO"))
logging.getLogger("httpx").setLevel(logging.WARNING)  # it logs every poll, token included
log = logging.getLogger("bot")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
AI_KEY = os.getenv("OPENAI_API_KEY", "").strip()
AI_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
AI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "You are a helpful assistant in a Telegram chat. Keep answers short.")
ALLOWED = {int(x) for x in os.getenv("ALLOWED_USER_IDS", "").replace(",", " ").split()}

# Last 20 messages per chat, in memory: lost on redeploy, which suits a starter.
history: dict[int, deque] = defaultdict(lambda: deque(maxlen=20))


def allowed(update: Update) -> bool:
    return not ALLOWED or (update.effective_user and update.effective_user.id in ALLOWED)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    mode = f"I answer with {AI_MODEL}." if AI_KEY else "I echo what you send. Add OPENAI_API_KEY to make me an AI chat bot."
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("My Telegram ID", callback_data="whoami"),
                                      InlineKeyboardButton("Reset chat", callback_data="reset")]])
    await update.message.reply_text(f"Hi {update.effective_user.first_name}! {mode}", reply_markup=keyboard)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("/start - welcome\n/id - your Telegram user ID\n/reset - forget this chat\n/help - this list")


async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(f"Your Telegram user ID: {update.effective_user.id}")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    history.pop(update.effective_chat.id, None)
    await update.effective_message.reply_text("Chat history cleared.")


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    await (my_id if update.callback_query.data == "whoami" else reset)(update, context)


async def ask_ai(chat_id: int, text: str) -> str:
    history[chat_id].append({"role": "user", "content": text})
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{AI_URL}/chat/completions", headers={"Authorization": f"Bearer {AI_KEY}"},
                              json={"model": AI_MODEL, "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *history[chat_id]]})
    r.raise_for_status()
    answer = r.json()["choices"][0]["message"]["content"]
    history[chat_id].append({"role": "assistant", "content": answer})
    return answer


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        await update.message.reply_text(f"Not allowed. Ask the owner to add your ID ({update.effective_user.id}) to ALLOWED_USER_IDS.")
        return
    if not AI_KEY:
        await update.message.reply_text(update.message.text)
        return
    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    try:
        answer = await ask_ai(update.effective_chat.id, update.message.text)
    except Exception as e:  # show the provider's error instead of going silent
        log.warning("AI request failed: %s", e)
        answer = f"AI request failed: {e}"
    for i in range(0, len(answer), 4096):  # Telegram's message length limit
        await update.message.reply_text(answer[i:i + 4096])


def idle(reason: str) -> None:
    # A bot that exits on a bad token crash-loops and shows as a failed deploy.
    # Stay up with a clear log line; the fix is a variable change and a redeploy.
    log.error("%s Set TELEGRAM_BOT_TOKEN (from @BotFather) in the Variables tab; Railway redeploys.", reason)
    while True:
        time.sleep(3600)


def main() -> None:
    if not TOKEN:
        idle("TELEGRAM_BOT_TOKEN is empty.")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("id", my_id))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    log.info("Starting (%s, %s)", f"AI: {AI_MODEL}" if AI_KEY else "echo mode",
             f"{len(ALLOWED)} allowed users" if ALLOWED else "open to everyone")
    try:
        # drop_pending_updates: skip messages queued while the bot was down
        app.run_polling(drop_pending_updates=True)
    except InvalidToken:
        idle("Telegram rejected TELEGRAM_BOT_TOKEN.")


if __name__ == "__main__":
    main()
