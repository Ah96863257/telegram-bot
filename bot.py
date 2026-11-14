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
from telegram.error import Conflict, InvalidToken, NetworkError
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

def parse_ids(raw: str) -> tuple[set[int], list[str]]:
    """Numeric IDs, plus whatever else was typed (an @username, a typo)."""
    ids, bad = set(), []
    for part in raw.replace(",", " ").replace(";", " ").split():
        try:
            ids.add(int(part))
        except ValueError:
            bad.append(part)
    return ids, bad


ALLOWED, BAD_IDS = parse_ids(os.getenv("ALLOWED_USER_IDS", ""))
# An allowlist that held only bad entries locks the bot instead of opening it to everyone.
LOCKED = bool(BAD_IDS) and not ALLOWED

# Last 20 messages per chat, in memory: lost on redeploy, which suits a starter.
history: dict[int, deque] = defaultdict(lambda: deque(maxlen=20))


def allowed(update: Update) -> bool:
    if LOCKED:
        return False
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


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if isinstance(context.error, Conflict):  # retried by the library; one line instead of a traceback
        log.error("Another copy of this bot is polling the same token. Stop it, or give this one its own token.")
        return
    log.error("Update failed", exc_info=context.error)


def idle(reason: str) -> None:
    # A bot that exits on a bad token crash-loops and shows as a failed deploy.
    # Stay up with a clear log line; the fix is a variable change and a redeploy.
    log.error("%s Set TELEGRAM_BOT_TOKEN (from @BotFather) in the Variables tab; Railway redeploys.", reason)
    while True:
        time.sleep(3600)


def main() -> None:
    if BAD_IDS:
        log.error("ALLOWED_USER_IDS takes numeric IDs; ignoring %s. Send /id to the bot for yours.%s",
                  ", ".join(BAD_IDS), " Nobody can chat until it holds one." if LOCKED else "")
    if not TOKEN:
        idle("TELEGRAM_BOT_TOKEN is empty.")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("id", my_id))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_error_handler(on_error)
    log.info("Starting (%s, %s)", f"AI: {AI_MODEL}" if AI_KEY else "echo mode",
             "locked" if LOCKED else f"{len(ALLOWED)} allowed users" if ALLOWED else "open to everyone")
    delay = 5
    while True:
        try:
            # drop_pending_updates: skip messages queued while the bot was down
            app.run_polling(drop_pending_updates=True, close_loop=False)
            return
        except InvalidToken:
            idle("Telegram rejected TELEGRAM_BOT_TOKEN.")
        except NetworkError as e:  # Telegram unreachable at startup: wait it out instead of crash-looping
            log.warning("Can't reach Telegram (%s); retrying in %d s.", e, delay)
            time.sleep(delay)
            delay = min(delay * 2, 300)


if __name__ == "__main__":
    main()
