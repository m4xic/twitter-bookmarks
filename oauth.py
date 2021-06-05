import tweepy
from dotenv import load_dotenv
from os import environ

load_dotenv()

auth = tweepy.OAuthHandler(environ.get("TWITTER_CONSUMER_KEY"), environ.get("TWITTER_CONSUMER_SECRET"))
redirect_url = auth.get_authorization_url()
print(f"You need to login via Twitter: f{redirect_url}")
verifier = input("Enter your verifier code:")
auth.get_access_token(verifier)

print("You've completed authentication. Add this to the bottom of your .env file:")
print(f"\nTWITTER_ACCESS_TOKEN={auth.access_token}\nTWITTER_ACCESS_TOKEN_SECRET={auth.access_token_secret}")