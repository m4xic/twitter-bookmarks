# bookmarks.py

import tweepy
import requests
from dotenv import load_dotenv
import os
from time import sleep
import re
import waybackpy
from io import BytesIO
from sys import exit
import traceback
from base64 import b64decode
from json import loads

## SETUP
print("twitter-bookmarks started")

load_dotenv()
print("Loading your config...")
raw_config = b64decode(os.environ.get("TB_B64_CONFIG"))
try:
    config = loads(raw_config)
except ValueError as e:
    print(f"Invalid base64/json config found! {e.with_traceback}")

ENABLE_OCR = os.getenv("ENABLE_OCR", 'False').lower() in ('true', '1', 't')

if ENABLE_OCR:
    import pytesseract
    from PIL import Image

class Bot:
    def resolve_dm(self, dm):
        twitter_urls = []
        for url in dm.message_create['message_data']['entities']['urls']:
            if re.match(r"https?:\/\/(www.)?twitter.com\/.*\/status\/[0-9]+", url['expanded_url']): twitter_urls.append(url['expanded_url'])
        tweets = []
        for tweet_url in twitter_urls:
            tweet_data = {}
            tweet_data['url'] = tweet_url
            tweet_data['id'] = tweet_url.split('status/')[-1]
            try:
                tweet_object = self.api.get_status(tweet_data['id'])
            except tweepy.TweepError:
                print(f"Looks like that Tweet ({tweet_data['id']}) has already been deleted.")
                continue
            tweet_data['author'] = tweet_object.author.screen_name
            tweet_data['content'] = tweet_object.text
            # This reverse split removes the t.co link included in the message by default
            tweet_data['message'] = dm.message_create['message_data']['text'].rsplit(' ', 1)[0]
            ocr = ""
            if "extended_entities" in dir(tweet_object) and ENABLE_OCR and self.mode in ["airtable"]:
                if "media" in tweet_object.extended_entities:
                    for media_item in tweet_object.extended_entities['media']:
                        if media_item['type'] == 'photo':
                            ocr += pytesseract.image_to_string(Image.open(BytesIO(requests.get(media_item['media_url']).content))) + '\n'
                        else: continue
            tweet_data['ocr'] = ocr
            tweets.append(tweet_data)
        self.api.destroy_direct_message(dm.id)
        return tweets

    def archive_url(self, url):
        try:
            return waybackpy.Url(url).save().archive_url
        except Exception as e:
            traceback.print_exc()
            return "<could not archive>"

    def check_dms(self):
        new_dms = self.api.list_direct_messages(50)
        if not new_dms:
            print(f"No new DMs found in the {self.name} inbox.")
        else:
            print(f"{len(new_dms)} found in the {self.name} inbox.")
        return new_dms
    
    def submit_airtable(self, url="", author="", content="", archive_url="", ocr="", message="", **kwargs):
        """
        Adds one record to the Airtable endpoint.

        Parameters:
        - url: URL of the Tweet to be stored
        - author: Author of the Tweet
        - content: Content of the Tweet being stored
        - archive_url: The URL from the Wayback Machine
        - ocr: (optional) Tesseract result for the image OCR
        - message: (optional) Message that was sent alongside the link
        """
        req = requests.post(
            self.endpoint,
            json={"fields": {"Tweet URL": url, "Tweet author": author, "Tweet content": content, "Archive URL": archive_url, "Message": message, "Image OCR": ocr}},
            headers={"Authorization": "Bearer " + self.airtable_key, "Content-Type": "application/json"}
        )

        print(f"Sent one Tweet to Airtable: {url}")
        if "id" not in req.json().keys() or req.status_code != 200: print(f"Airtable response error: {req.text}")

    def submit_webhook(self, url="", content="", archive_url="", message="", **kwargs):
        """
        Sends one URL to the webhook endpoint.
        
        Parameters:
        - url: URL of the Tweet to be stored
        - archive_url: The URL from the Wayback Machine
        - message: (optional) Message that was sent alongside the link
        """
        req = requests.post(
            self.endpoint,
            json={'text': '```\n' + content + '\n```\n```' + message + '\n```\n' + url + '\n> *Archived at <' + archive_url + '>*'},
            headers={'Content-Type': 'application/json'}
        )
        print(f"Sent one Tweet to Webhook: {url}")
        if req.status_code not in [200, 201]: print(f"Webhook response error: {req.status_code} {req.text}")

    def __init__(self, name, mode, endpoint, twitter_consumer_key, twitter_consumer_secret, twitter_access_token, twitter_access_token_secret, airtable_key=None):
        self.name = name
        self.mode = mode
        self.endpoint = endpoint
        try:
            auth = tweepy.OAuthHandler(twitter_consumer_key, twitter_consumer_secret)
            auth.set_access_token(twitter_access_token, twitter_access_token_secret)
            self.api = tweepy.API(auth)
        except tweepy.TweepError as e:
            print(f"Could not log in to Twitter API! {e.reason}")
            exit(1)

        if mode == "airtable" and airtable_key != None:
            self.airtable_key = airtable_key
            self.submit = self.submit_airtable
            print(f"Configured Airtable Bot object for {name}")
        elif mode == "webhook":
            self.submit = self.submit_webhook
            print(f"Configured Webhook Bot object for {name}")
        else:
            print(f"Bot object not configured correctly. {mode=} {airtable_key=} {endpoint=}")
            exit(1)

def main():
    bots = []
    for bot_config in config['bots']:
        if 'airtable_api_key' in bot_config:
            bots.append(Bot(bot_config['name'], bot_config['mode'], bot_config['airtable_endpoint'], bot_config['twitter_consumer_key'], bot_config['twitter_consumer_secret'], bot_config['twitter_access_token'], bot_config['twitter_access_token_secret'], airtable_key=bot_config['airtable_api_key']))
        else:
            bots.append(Bot(bot_config['name'], bot_config['mode'], bot_config['webhook_endpoint'], bot_config['twitter_consumer_key'], bot_config['twitter_consumer_secret'], bot_config['twitter_access_token'], bot_config['twitter_access_token_secret']))
    
    while True:
        try:
            for bot in bots:
                new_dms = bot.check_dms()
                if new_dms:
                    for dm in new_dms:
                        for result in bot.resolve_dm(dm):
                            bot.submit(url=result['url'], author=result['author'], content=result['content'], archive_url=bot.archive_url(result['url']), ocr=result['ocr'], message=result['message'])
        except tweepy.RateLimitError:
            print("Rate limited! Stopping for 15 minutes.")
            sleep(900)
            continue
        except tweepy.TweepError as te:
            print("Problem with the Twitter API!")
            print(f"{te.with_traceback}")
            exit(1)
        sleep(60)

main()
