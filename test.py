import re
import g4f
from g4f.Provider import Yqcloud, Blackbox, PollinationsAI, OIVSCodeSer2, WeWordle
from PyPDF2 import PdfReader
from docx import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
import tweepy
from telegram import Update
from telegram.ext import MessageHandler, filters
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import speech_recognition as sr
from pydub import AudioSegment
from dotenv import load_dotenv
import tempfile
import shutil
import json
import uuid
from typing import Dict, List, Optional
import time
from datetime import datetime
import logging
import os

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
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
def send_ai_request(prompt):
    global ai_chat_to_use, failed_ai_chats

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
            # 🧠 Construct chat history with roles
            messages = prompt

            kwargs = {
                "provider": current_chat["provider"],
                "messages": messages,
            }
            if current_chat["model"]:
                kwargs["model"] = current_chat["model"]

            response = g4f.ChatCompletion.create(**kwargs)

            # if (
            #     response
            #     and isinstance(response, str)
            #     and response.strip()
            #     and re.match(r"^[\s]*[a-zA-Z]", response)
            # ):
            return response

            failed_ai_chats.add(ai_chat_to_use)
            ai_chat_to_use = (ai_chat_to_use + 1) % total_chats
            attempts += 1

        except Exception as e:
            failed_ai_chats.add(ai_chat_to_use)
            ai_chat_to_use = (ai_chat_to_use + 1) % total_chats
            attempts += 1

    failed_ai_chats.clear()
    return False

EMBEDDING_MODEL = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)
VECTOR_DB_PATH = "./vector_db"
METADATA_FILE = "./file_metadata.json"

def ensure_vector_db_directory():
    """Ensure the vector_db directory exists"""
    if not os.path.exists(VECTOR_DB_PATH):
        os.makedirs(VECTOR_DB_PATH, exist_ok=True)
        logger.info(f"Created vector_db directory: {VECTOR_DB_PATH}")

class FileMetadataManager:
    """Manages file metadata and vector associations"""
    
    def __init__(self, metadata_file: str):
        self.metadata_file = metadata_file
        self.metadata = self._load_metadata()
    
    def _load_metadata(self) -> Dict:
        """Load metadata from file"""
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading metadata: {e}")
        return {
            'files': {},
            'chunk_mappings': {},
            'next_chunk_id': 0
        }
    
    def _save_metadata(self):
        """Save metadata to file"""
        try:
            with open(self.metadata_file, 'w') as f:
                json.dump(self.metadata, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving metadata: {e}")
    
    def add_file(self, filename: str, file_size: int, upload_date: str, 
                 chunk_count: int, file_type: str) -> str:
        """Add a new file to metadata"""
        file_id = str(uuid.uuid4())
        
        self.metadata['files'][file_id] = {
            'filename': filename,
            'file_size': file_size,
            'upload_date': upload_date,
            'chunk_count': chunk_count,
            'file_type': file_type,
            'status': 'uploaded'
        }
        
        self._save_metadata()
        return file_id
    
    def add_chunk_mapping(self, file_id: str, chunk_text: str, chunk_index: int) -> int:
        """Add a chunk mapping and return chunk ID"""
        chunk_id = self.metadata['next_chunk_id']
        self.metadata['next_chunk_id'] += 1
        
        self.metadata['chunk_mappings'][chunk_id] = {
            'file_id': file_id,
            'chunk_text': chunk_text,
            'chunk_index': chunk_index
        }
        
        self._save_metadata()
        return chunk_id
    
    def get_file_metadata(self, file_id: str) -> Optional[Dict]:
        """Get metadata for a specific file"""
        return self.metadata['files'].get(file_id)
    
    def get_all_files(self) -> List[Dict]:
        """Get metadata for all files"""
        files = []
        for file_id, metadata in self.metadata['files'].items():
            file_info = metadata.copy()
            file_info['file_id'] = file_id
            files.append(file_info)
        return files
    
    def get_file_chunks(self, file_id: str) -> List[int]:
        """Get all chunk IDs for a specific file"""
        chunk_ids = []
        for chunk_id, mapping in self.metadata['chunk_mappings'].items():
            if mapping['file_id'] == file_id:
                chunk_ids.append(chunk_id)
        return chunk_ids
    
    def delete_file(self, file_id: str) -> bool:
        """Delete a file and all its chunks"""
        if file_id not in self.metadata['files']:
            return False
        
        # Remove file metadata
        del self.metadata['files'][file_id]
        
        # Remove all chunks for this file
        chunks_to_remove = []
        for chunk_id, mapping in self.metadata['chunk_mappings'].items():
            if mapping['file_id'] == file_id:
                chunks_to_remove.append(chunk_id)
        
        for chunk_id in chunks_to_remove:
            del self.metadata['chunk_mappings'][chunk_id]
        
        self._save_metadata()
        return True
    
    def clear_all(self):
        """Clear all metadata"""
        self.metadata = {
            'files': {},
            'chunk_mappings': {},
            'next_chunk_id': 0
        }
        self._save_metadata()

# Initialize metadata manager
metadata_manager = FileMetadataManager(METADATA_FILE)

def upload():
    # Handle both 'file' and 'files' field names for compatibility
    files = request.files.getlist('files') or request.files.getlist('file')
    
    if not files or not any(f.filename for f in files):
        return jsonify({'error': 'No file provided'}), 400

    processed_files = []
    
    for file in files:
        if not file.filename:
            continue
            
        filename = file.filename.lower()
        
        if not filename.endswith(('.pdf', '.txt', '.docx')):
            return f'Unsupported file type: {filename}'

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            file.save(tmp.name)
            file_path = tmp.name

        try:
            # Extract text
            if filename.endswith('.pdf'):
                reader = PdfReader(file_path)
                text = "\n".join([page.extract_text() or "" for page in reader.pages])
            elif filename.endswith('.docx'):
                doc = Document(file_path)
                text = "\n".join([p.text for p in doc.paragraphs])
            else:  # .txt
                text = open(file_path, encoding='utf-8').read()

            # Chunk text
            splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
            texts = splitter.create_documents([text])

            # Store file metadata
            file_size = os.path.getsize(file_path)
            upload_date = datetime.now().isoformat()
            file_type = os.path.splitext(filename)[1].lower()
            
            file_id = metadata_manager.add_file(
                filename=file.filename,
                file_size=file_size,
                upload_date=upload_date,
                chunk_count=len(texts),
                file_type=file_type
            )

            # Create or update vector store
            try:
                # Ensure vector_db directory exists
                ensure_vector_db_directory()
                
                if os.path.exists(VECTOR_DB_PATH) and os.listdir(VECTOR_DB_PATH):
                    # Load existing vectorstore if it has content
                    vectorstore = FAISS.load_local(VECTOR_DB_PATH, EMBEDDING_MODEL, allow_dangerous_deserialization=True)
                    new_vectorstore = FAISS.from_documents(texts, EMBEDDING_MODEL)
                    vectorstore.merge_from(new_vectorstore)
                else:
                    # Create new vectorstore
                    vectorstore = FAISS.from_documents(texts, EMBEDDING_MODEL)
                    
                vectorstore.save_local(VECTOR_DB_PATH)
            except Exception as e:
                logger.error(f"Error creating/updating vector store: {e}")
                # If vector store creation fails, try to create a fresh one
                try:
                    # Remove existing vector_db if it exists but is corrupted
                    if os.path.exists(VECTOR_DB_PATH):
                        shutil.rmtree(VECTOR_DB_PATH)
                        ensure_vector_db_directory()
                    
                    # Create fresh vector store
                    vectorstore = FAISS.from_documents(texts, EMBEDDING_MODEL)
                    vectorstore.save_local(VECTOR_DB_PATH)
                except Exception as e2:
                    logger.error(f"Error creating fresh vector store: {e2}")
                    raise Exception(f"Failed to create vector store: {str(e2)}")
            
            # Store chunk mappings
            for i, text_doc in enumerate(texts):
                metadata_manager.add_chunk_mapping(file_id, text_doc.page_content, i)
            
            processed_files.append({
                'filename': file.filename,
                'chunks': len(texts),
                'file_id': file_id,
                'file_size': file_size,
                'upload_date': upload_date
            })

        except Exception as e:
            logger.error(f"Error processing {filename}: {str(e)}")
            # Clean up temporary file
            if os.path.exists(file_path):
                os.remove(file_path)
            return f'Error processing {filename}'
        finally:
            # Ensure temporary file is cleaned up
            if os.path.exists(file_path):
                os.remove(file_path)

    return {
        'message': f'Successfully processed {len(processed_files)} file(s)',
        'files': processed_files
    }

def chat():
    try:
        data = request.json
        user_message = data.get('message', '').strip()
        if not user_message:
            return jsonify({'error': 'Message cannot be empty'}), 400
        
        if len(user_message) > 1000:
            return jsonify({'error': 'Message too long. Please keep it under 1000 characters.'}), 400
        
        # Initialize or retrieve chat history
        if 'chat_history' not in session:
            session['chat_history'] = []

        chat_history = session['chat_history']

        # Prepare full context for AI
        ai_messages = []
        for entry in chat_history:
            ai_messages.append({"role": "user", "content": entry["user"]})
            ai_messages.append({"role": "assistant", "content": entry["bot"]})
            # Inside chat()
            retrieved_docs = []
            if os.path.exists(VECTOR_DB_PATH):
                try:
                    vectorstore = FAISS.load_local(VECTOR_DB_PATH, EMBEDDING_MODEL, allow_dangerous_deserialization=True)
                    relevant = vectorstore.similarity_search(user_message, k=3)
                    retrieved_docs = [doc.page_content for doc in relevant]
                except Exception as e:
                    logger.warning(f"RAG failed: {e}")
            ai_messages.append({"role": "system", "content": "Relevant documents: " + "\n".join(retrieved_docs) if retrieved_docs else "No relevant documents found."})

        ai_messages.append({"role": "user", "content": user_message})

        # Send to AI
        response = send_ai_request(ai_messages)

        # Save latest exchange
        chat_history.append({
            "user": user_message,
            "bot": response,
            "timestamp": datetime.now().isoformat()
        })

        # Limit to last 10 exchanges
        if len(chat_history) > 10:
            chat_history = chat_history[-10:]

        session['chat_history'] = chat_history

        return {
            'response': response,
            'history_length': len(chat_history)
        }
        
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        if "rate" in str(e).lower() or "429" in str(e):
            return {
                'error': 'Service is experiencing high load. Please try again in a moment.',
                'retry_after': 60,
                'is_rate_limit': True
            }
        
        return {'error': 'Sorry, I encountered an error. Please try again.'}
    
def get_documents():
    """Get list of uploaded documents"""
    try:
        files = metadata_manager.get_all_files()
        return {'documents': files}
    except Exception as e:
        return {'error': str(e)}

def delete_document(file_id):
    """Delete a specific document and its chunks"""
    try:
        # Get file metadata
        file_metadata = metadata_manager.get_file_metadata(file_id)
        if not file_metadata:
            return {'error': 'File not found'}
        
        # Delete from metadata
        success = metadata_manager.delete_file(file_id)
        if not success:
            return {'error': 'Failed to delete file'}
        
        # Rebuild vector store without the deleted chunks
        try:
            # Get all remaining chunks from metadata
            all_chunks = []
            for chunk_id, mapping in metadata_manager.metadata['chunk_mappings'].items():
                all_chunks.append(mapping['chunk_text'])
            
            if all_chunks:
                # Create new vectorstore with remaining chunks
                ensure_vector_db_directory()
                new_vectorstore = FAISS.from_texts(all_chunks, EMBEDDING_MODEL)
                new_vectorstore.save_local(VECTOR_DB_PATH)
            else:
                # No chunks left, remove vector store
                if os.path.exists(VECTOR_DB_PATH):
                    shutil.rmtree(VECTOR_DB_PATH)
                    
        except Exception as e:
            logger.error(f"Error rebuilding vector store: {e}")
            # If rebuilding fails, clear the vector store
            if os.path.exists(VECTOR_DB_PATH):
                shutil.rmtree(VECTOR_DB_PATH)
        
        return {
            'message': f'Document {file_metadata["filename"]} deleted successfully',
            'deleted_file': file_metadata
        }
    except Exception as e:
        return {'error': str(e)}

def health_check():
    """System health check"""
    try:
        files = metadata_manager.get_all_files()
        total_chunks = len(metadata_manager.metadata['chunk_mappings'])
        
        return {
            'status': 'healthy',
            'documents_count': len(files),
            'total_chunks': total_chunks,
            'files': [f['filename'] for f in files],
            'rate_limit_status': {
                'requests_last_minute': 10,  # Simplified
                'limit': 60
            }
        }
    except Exception as e:
        return {'error': str(e)}

def clear_data():
    """Clear file content and chat history"""
    try:
        # Clear metadata
        metadata_manager.clear_all()
        
        # Clear vector database
        if os.path.exists(VECTOR_DB_PATH):
            try:
                shutil.rmtree(VECTOR_DB_PATH)
                logger.info("Vector database cleared successfully")
            except Exception as e:
                logger.error(f"Error clearing vector database: {e}")
                # Continue even if vector_db deletion fails
        
        return {
            'message': 'Chat history and file content cleared successfully.',
            'status': 'success'
        }
    except Exception as e:
        logger.error(f"Error in clear_data: {e}")
        return {
            'error': f'Failed to clear data: {str(e)}',
            'status': 'error'
        }

# App setup
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("echo", echo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.run_polling()
