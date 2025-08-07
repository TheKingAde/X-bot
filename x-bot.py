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
user_modes = {}
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
    await update.message.reply_text("👋 Hello! I'm x bot")

VALID_MODES = ["assisted", "fully_auto"]

async def set_mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text("⚠️ Usage: /setmode assisted OR /setmode fully_auto")
        return

    mode = context.args[0].lower()

    if mode not in VALID_MODES:
        await update.message.reply_text("❌ Invalid mode. Use `assisted` or `fully_auto`.")
        return

    user_modes[user_id] = mode
    await update.message.reply_text(f"✅ Mode set to *{mode}*", parse_mode="Markdown")

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
            user_id = update.effective_user.id

            # 🔍 Detect intent
            intent = detect_intent(transcript)
            logger.info(f"[Voice] Detected intent: {intent}")

            # 🐦 Post to Twitter if intent is make_post
            if intent == "make_post":
                try:
                    response = send_ai_request(user_id, transcript, intent, system_prompt=STYLE_SYSTEM_PROMPT)
                    if response:
                        mode = user_modes.get(user_id, "assisted")
                        if mode == "fully_auto":
                            client.create_tweet(text=response)
                        else:
                            await update.message.reply_text(response)
                    else:
                        await update.message.reply_text("❌ AI didn't return a response. Please try again.")
                except Exception as e:
                    logger.error(f"Twitter post error: {str(e)}")
                    await update.message.reply_text(f"❌ Couldn't post: {e}")
            else:
                intent = "general"
                general_system_prompt = """You are a general assistant named x bot. Respond to the user's message in a helpful and informative manner.
                    Keep responses concise and relevant. The response is to be converted to audio so avoid using punctuation, symbols, signs, emojis and the rest, spell everything out and make it sound more natural.
                """
                response = send_ai_request(user_id, transcript, intent, system_prompt=general_system_prompt)

            # 🎤 Convert response to TTS
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
# At the top of your file, add the user style prompt
STYLE_SYSTEM_PROMPT = """
You are an X (Twitter) assistant. Writing style is informal, casual, and straightforward.

FOLLOW THE USER'S STYLE RULES:
When the user wants to post something new, generate it in the same tone, length, and style.
Don't use exclaimation marks or emojis, and keep the language casual and straightforward.
Don't use any hashtags or links, numberings just the text content.
Total number of characters should be less than 150.
"""

# Modify send_ai_request to accept optional system prompt
def send_ai_request(user_id, user_message, intent, system_prompt=None):
    global ai_chat_to_use, failed_ai_chats

    if user_id not in user_histories:
        user_histories[user_id] = []

    history = []
    if system_prompt:
        history.append({"role": "system", "content": system_prompt})

    history += user_histories[user_id] + [{"role": "user", "content": user_message}]
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
            if str(response) == "Login to continue using":
                    ai_chat_to_use = (ai_chat_to_use + 1) % total_chats
                    attempts += 1
                    continue
            if intent == "general":
                user_histories[user_id] = history + [{"role": "assistant", "content": response}]
                user_histories[user_id] = user_histories[user_id][-MAX_HISTORY_LENGTH:]
                return response
                
            if (
                response
                and isinstance(response, str)
                and response.strip()
                and len(response.strip()) < 150
                and not re.search(r"[!#]|https?://|\bwww\.", response)
                and not re.search(r"[\U0001F600-\U0001F64F"
                                r"\U0001F300-\U0001F5FF"
                                r"\U0001F680-\U0001F6FF"
                                r"\U0001F1E0-\U0001F1FF]", response)
            ):
                user_histories[user_id] = history + [{"role": "assistant", "content": response}]
                user_histories[user_id] = user_histories[user_id][-MAX_HISTORY_LENGTH:]
                return response

        except Exception:
            failed_ai_chats.add(ai_chat_to_use)

        ai_chat_to_use = (ai_chat_to_use + 1) % total_chats
        attempts += 1

    failed_ai_chats.clear()
    return False

# Update /chat command
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message if update.effective_message else None
    if not message or not message.text:
        logger.warning("No message text found in update.")
        await update.effective_message.reply_text("❗ No message text found. Please send a valid message.")
        return
    user_message = message.text.strip()
    if not user_message:
        return

    try:
        user_id = update.effective_user.id
        intent = detect_intent(user_message)
        logger.info(f"[User {user_id}] Detected intent: {intent}")

        if intent == "make_post":
            response = send_ai_request(user_id, user_message, intent, system_prompt=STYLE_SYSTEM_PROMPT)
            if response:
                mode = user_modes.get(user_id, "assisted")
                if mode == "fully_auto":
                    client.create_tweet(text=response)
                else:
                    await update.effective_message.reply_text(response)
            else:
                await update.effective_message.reply_text("❌ AI didn't return a response. Please try again.")
            return
        else:
            intent = "general"
            general_system_prompt = """You are a general assistant named x bot. Respond to the user's message in a helpful and informative manner.
                Keep responses concise and relevant.
            """
            response = send_ai_request(user_id, user_message, intent, system_prompt=general_system_prompt)
            if response:
                await update.effective_message.reply_text(response)
            else:
                await update.effective_message.reply_text("❌ AI didn't return a response. Please try again.")
    except Exception as e:
        logger.error(f"Free text handler error: {str(e)}")
        await update.effective_message.reply_text("\u26a0\ufe0f Error communicating with AI. Please try again.")

INTENT_SYSTEM_PROMPT = """You are an intent classifier who uses keywords plus reasoning. Given a user message, return one of the following intents only:

- make_post
- general

Return only the intent, and nothing else.

Examples:
User: I want to post something
Intent: make_post

User: I want to post about
Intent: make_post

User: I want to make a post about
Intent: make_post

User: make a post about
Intent: make_post

User: Write a post for me
Intent: make_post

User: post
Intent: make_post

User: post this
Intent: make_post

User: post about
Intent: make_post

User: Help me post this
Intent: make_post

User: Share how I did something on X
Intent: make_post

User: I want to share how i did something on X
Intent: make_post

User: Tweet this
Intent: make_post

User: Make a tweet using this idea
Intent: make_post

User: What's the weather today?
Intent: general

User: Who won the match?
Intent: general

User: How are you?
Intent: general
"""


def detect_intent(user_message: str) -> str:
    messages = [
        {"role": "system", "content": INTENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    total_chats = len(ai_chats)
    attempts = 0
    global ai_chat_to_use, failed_ai_chats

    while attempts < total_chats:
        if ai_chat_to_use in failed_ai_chats:
            ai_chat_to_use = (ai_chat_to_use + 1) % total_chats
            attempts += 1
            continue

        try:
            kwargs = {
                "provider": ai_chats[ai_chat_to_use]["provider"],
                "messages": messages,
            }
            if ai_chats[ai_chat_to_use]["model"]:
                kwargs["model"] = ai_chats[ai_chat_to_use]["model"]

            result = g4f.ChatCompletion.create(**kwargs)
            if result:
                intent = result.strip().lower()
                if intent in ["make_post", "general"]:
                    return intent
        except Exception:
            failed_ai_chats.add(ai_chat_to_use)

        ai_chat_to_use = (ai_chat_to_use + 1) % total_chats
        attempts += 1

    return "general"  # fallback


# App setup
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setmode", set_mode_command))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT, chat))
    app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE & filters.TEXT, chat))
    app.run_polling()
