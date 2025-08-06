import re
import g4f
from g4f.Provider import Yqcloud, Blackbox, PollinationsAI, OIVSCodeSer2, WeWordle
import tweepy
from telegram import Update
from telegram.ext import MessageHandler, filters
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import speech_recognition as sr
from pydub import AudioSegment
from dotenv import load_dotenv
import time
import logging
import os
from gtts import gTTS

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
user_id = None
user_histories = {}
MAX_HISTORY_LENGTH = 100  # Optional: limit memory size per user

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

    # Convert OGG to WAV
    AudioSegment.from_ogg(ogg_path).export(wav_path, format="wav")

    recognizer = sr.Recognizer()
    with sr.AudioFile(wav_path) as source:
        audio = recognizer.record(source)
        try:
            # Step 1: Transcribe
            transcript = recognizer.recognize_google(audio)
            await update.message.reply_text(f"🗣 Transcription: {transcript}")
            user_id = update.effective_user.id
            response = send_ai_request(user_id, transcript)
            if not response:
                await update.message.reply_text("❌ AI didn't return a response.")
                return

            # Step 3: Convert response to speech (TTS)
            tts = gTTS(text=response, lang='en', tld='ca')
            audio_path = f"response_{update.message.message_id}.mp3"
            tts.save(audio_path)

            # Step 4: Send audio back to user
            with open(audio_path, "rb") as audio_file:
                await update.message.reply_voice(voice=audio_file)

            # Cleanup
            os.remove(audio_path)

        except sr.UnknownValueError:
            await update.message.reply_text("❗ Could not understand the voice message.")
        except sr.RequestError as e:
            await update.message.reply_text(f"❗ API error: {e}")

    os.remove(ogg_path)
    os.remove(wav_path)

# Providers and models
ai_chats = [
    {"provider": Yqcloud, "model": "gpt-4", "label": "Yqcloud - GPT-4"},
    {"provider": Blackbox, "model": "gpt-4", "label": "Blackbox - GPT-4"},
    {"provider": PollinationsAI, "model": None, "label": "PollinationsAI - DEFAULT"},
    {"provider": OIVSCodeSer2, "model": "gpt-4o-mini", "label": "OIVSCodeSer2 - gpt-4o-mini"},
    {"provider": WeWordle, "model": "gpt-4", "label": "WeWordle - GPT-4"},
]

failed_ai_chats = set()
ai_chat_to_use = 0
def send_ai_request(user_id, user_message):
    global ai_chat_to_use, failed_ai_chats

    if user_id not in user_histories:
        user_histories[user_id] = []

    # Build full chat history
    history = user_histories[user_id] + [{"role": "user", "content": user_message}]
    total_chats = len(ai_chats)
    attempts = 0

    while attempts < total_chats:
        current_chat = ai_chats[ai_chat_to_use]
        if ai_chat_to_use in failed_ai_chats:
            ai_chat_to_use = (ai_chat_to_use + 1) % total_chats
            attempts += 1
            continue

        time.sleep(2)
        try:
            kwargs = {
                "provider": current_chat["provider"],
                "messages": history,
            }
            if current_chat["model"]:
                kwargs["model"] = current_chat["model"]

            response = g4f.ChatCompletion.create(**kwargs)

            if response and isinstance(response, str) and response.strip():
                # Update history
                user_histories[user_id] = history + [{"role": "assistant", "content": response}]
                user_histories[user_id] = user_histories[user_id][-MAX_HISTORY_LENGTH:]
                # if (
            #     response
            #     and isinstance(response, str)
            #     and response.strip()
            #     and re.match(r"^[\s]*[a-zA-Z]", response)
            # ):
                return response

        except Exception:
            failed_ai_chats.add(ai_chat_to_use)

        ai_chat_to_use = (ai_chat_to_use + 1) % total_chats
        attempts += 1

    failed_ai_chats.clear()
    return False

# /chat command
async def chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = " ".join(context.args)
    if not user_message:
        await update.message.reply_text("⚠️ Usage: /chat your question or prompt")
        return

    try:
        user_id = update.effective_user.id
        response = send_ai_request(user_id, user_message)

        if response:
            await update.message.reply_text(response)
        else:
            await update.message.reply_text("❌ AI didn't return a response. Please try again.")
    except Exception as e:
        logger.error(f"Chat command error: {str(e)}")
        await update.message.reply_text("⚠️ Error communicating with AI. Please try again.")

# App setup
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("echo", echo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(CommandHandler("chat", chat_command))
    app.run_polling()
