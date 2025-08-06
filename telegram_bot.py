from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Replace with your bot token from BotFather
TELEGRAM_BOT_TOKEN = "7368174407:AAFLWS9EsLKWVP_8IbXaLE5f_m4PHWzuGO0"

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hello! I'm your bot. Send /echo <text> to repeat.")

# /echo command
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = " ".join(context.args)
    if not msg:
        await update.message.reply_text("⚠️ Usage: /echo your message")
        return
    await update.message.reply_text(msg)

# App setup
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("echo", echo))
    app.run_polling()
