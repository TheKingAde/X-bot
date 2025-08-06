from telegram import Update
from telegram.ext import MessageHandler, filters
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import speech_recognition as sr
from pydub import AudioSegment
from dotenv import load_dotenv
import os
load_dotenv()

# Replace with your bot token from BotFather
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

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

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.voice.get_file()
    ogg_path = "voice.ogg"
    wav_path = "voice.wav"

    await file.download_to_drive(ogg_path)

    # Convert OGG (Opus) to WAV
    AudioSegment.from_ogg(ogg_path).export(wav_path, format="wav")

    # Transcribe
    recognizer = sr.Recognizer()
    with sr.AudioFile(wav_path) as source:
        audio = recognizer.record(source)
        try:
            text = recognizer.recognize_google(audio)
            await update.message.reply_text(f"🗣 Transcription: {text}")
        except sr.UnknownValueError:
            await update.message.reply_text("❗ Could not understand the voice message.")
        except sr.RequestError as e:
            await update.message.reply_text(f"❗ API error: {e}")

    os.remove(ogg_path)
    os.remove(wav_path)

# App setup
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("echo", echo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.run_polling()
