import tweepy
import os
from dotenv import load_dotenv

load_dotenv()

# Updated with new permissions and tokens
client = tweepy.Client(
    consumer_key=os.getenv("CONSUMER"),
    consumer_secret=os.getenv("CONSUMER_SECRET"),
    access_token=os.getenv("ACCESS_TOKEN"),
    access_token_secret=os.getenv("ACCESS_TOKEN_SECRET"),
    bearer_token=os.getenv("BEARER_TOKEN")
)

# try:
#     response = client.create_tweet(text="Posting from X Bot using v2 API 🚀")
#     print(f"✅ Tweet posted! ID: {response.data['id']}")
# except Exception as e:
#     print(f"❌ Error posting tweet: {e}")
# Replace with the user's Twitter handle (without @)
username = "Kingade_1"

# First get the user ID
user = client.get_user(username=username)
user_id = user.data.id

# Now fetch the user's recent tweets
response = client.get_users_tweets(
    id=user_id,
    max_results=30,  # Up to 100
    tweet_fields=["created_at", "text"]
)

# Print them
if response.data:
    for tweet in response.data:
        print(f"{tweet.created_at} - {tweet.text}")
else:
    print("No recent tweets found.")
