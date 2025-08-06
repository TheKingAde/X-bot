import tweepy
from telegram import Update
from telegram.ext import MessageHandler, filters
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import speech_recognition as sr
from pydub import AudioSegment
from dotenv import load_dotenv
import os

load_dotenv()

# Updated with new permissions and tokens
client = tweepy.Client(
    consumer_key=os.getenv("CONSUMER"),
    consumer_secret=os.getenv("CONSUMER_SECRET"),
    access_token=os.getenv("ACCESS_TOKEN"),
    access_token_secret=os.getenv("ACCESS_TOKEN_SECRET"),
    bearer_token=os.getenv("BEARER_TOKEN")
)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# try:
#     response = client.create_tweet(text="Posting from X Bot using v2 API 🚀")
#     print(f"✅ Tweet posted! ID: {response.data['id']}")
# except Exception as e:
#     print(f"❌ Error posting tweet: {e}")
# Replace with the user's Twitter handle (without @)
# username = "Kingade_1"

# # First get the user ID
# user = client.get_user(username=username)
# user_id = user.data.id

# # Now fetch the user's recent tweets
# response = client.get_users_tweets(
#     id=user_id,
#     max_results=30,  # Up to 100
#     tweet_fields=["created_at", "text"]
# )

# # Print them
# if response.data:
#     for tweet in response.data:
#         print(f"{tweet.created_at} - {tweet.text}")
# else:
#     print("No recent tweets found.")

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
