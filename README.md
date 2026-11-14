# Deploy and Host a Telegram Bot (Python) on Railway

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/template/telegram-bot-python?referralCode=sLjDXb&utm_medium=integration&utm_source=button&utm_campaign=telegram-bot-python)

A Python Telegram bot that is running a minute after you paste its token: commands, inline buttons, a user allowlist, and optional AI chat through any OpenAI-compatible API (OpenAI, OpenRouter, Groq, DeepSeek, a self-hosted model). It's one short file built on [python-telegram-bot](https://python-telegram-bot.org), meant to be ejected and made your own.

## About Hosting a Telegram Bot

The bot uses long polling: it asks Telegram for new messages, so it needs no public domain, webhook or certificate. One small service, no database.

- Without an AI key it echoes what you send, so you can see it working first.
- With `OPENAI_API_KEY` set it chats with the model, keeping the last 20 messages of each chat as context.
- A missing or wrong token, an `@username` in the allowlist or Telegram being unreachable at start doesn't crash-loop the service: the bot waits or retries and says in its logs what to fix.

## Common Use Cases

- A personal AI assistant in Telegram, on any model you choose
- A starting point for a support, notification or community bot
- A private bot for a family or team, locked to listed user IDs
- Learning bot development with a working deploy from minute one

## Dependencies for Telegram Bot Hosting

- A bot token from [@BotFather](https://t.me/BotFather) (send `/newbot`, pick a name, copy the token).
- Optional: an API key for an OpenAI-compatible provider.

### Deployment Dependencies

- [python-telegram-bot docs](https://docs.python-telegram-bot.org)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [OpenRouter](https://openrouter.ai) for one key to many models (optional)

### Implementation Details

**First use:** paste the token as `TELEGRAM_BOT_TOKEN`, deploy, then open your bot in Telegram and send `/start`.

**Commands:** `/start`, `/help`, `/id` (shows your Telegram user ID) and `/reset` (clears the AI's memory of this chat).

**AI chat:** set `OPENAI_API_KEY`, then `OPENAI_BASE_URL` and `OPENAI_MODEL` for your provider:

| Provider | `OPENAI_BASE_URL` | `OPENAI_MODEL` example |
| --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| OpenRouter | `https://openrouter.ai/api/v1` | `anthropic/claude-sonnet-4.5` |
| Groq | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat` |

Change the bot's personality with `SYSTEM_PROMPT`.

**Lock it down:** anyone who finds your bot can use it, and your AI key pays for it. Send `/id` to the bot, then put your numeric ID (comma-separated for several people) in `ALLOWED_USER_IDS`. An entry that isn't a number is ignored, and if none are numbers the bot answers nobody until you fix it.

**Make it yours:** eject the template in the service's settings to get your own copy of the repo. Add handlers in `main()` in `bot.py`; every push redeploys.

Notes and limits:

- A bot token can be polled by one process at a time. Running the same token elsewhere (your laptop) makes both report `Conflict` errors.
- Chat memory is kept in RAM and is cleared on each redeploy.
- Messages sent while the bot is down are skipped on start, so it doesn't answer a backlog.

## Why Deploy a Telegram Bot on Railway?

Railway is a singular platform to deploy your infrastructure stack. Railway will host your infrastructure so you don't have to deal with configuration, while allowing you to vertically and horizontally scale it.

By deploying a Telegram bot on Railway, you are one step closer to supporting a complete full-stack application with minimal burden. Host your servers, databases, AI agents, and more on Railway.
