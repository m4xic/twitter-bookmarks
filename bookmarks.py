# bookmarks.py

import tweepy
import requests
from dotenv import load_dotenv
import os
import logging
from time import sleep
import re
import waybackpy

## SETUP
logging.basicConfig(format='%(asctime)s %(levelname)s - %(message)s', level=logging.WARNING)
print("Logging started")

load_dotenv()
print("Loaded .env variables")

airtable_endpoint = "https://api.airtable.com/v0/" + os.environ.get("AIRTABLE_BASE")  + "/" + os.environ.get("AIRTABLE_TABLE")
print(f"Airtable endpoint set to {airtable_endpoint}")

try:
    auth = tweepy.OAuthHandler(os.environ.get("TWITTER_CONSUMER_KEY"), os.environ.get("TWITTER_CONSUMER_SECRET"))
    auth.set_access_token(os.environ.get("TWITTER_ACCESS_TOKEN"), os.environ.get("TWITTER_ACCESS_TOKEN_SECRET"))
    api = tweepy.API(auth)
except tweepy.TweepError as e:
    print(f"Could not log in to Twitter API! {e.reason}")
print("Logged in to Twitter API!")

def one_airtable(url, author, content, archive_url , message=""):
    """
    Adds one record to the Airtable endpoint.

    Parameters:
    - url: URL of the Tweet to be stored
    - author: Author of the Tweet
    - content: Content of the Tweet being stored
    - message: (optional) Message that was sent alongside the link
    - archive_url: The URL from the Wayback Machine
    """
    req = requests.post(
        airtable_endpoint,
        json={
            "fields": {
                "Tweet URL": url,
                "Tweet author": author,
                "Tweet content": content,
                "Archive URL": archive_url,
                "Message": message
            }
        },
        headers={
            "Authorization": "Bearer " + os.environ.get("AIRTABLE_API_KEY"),
            "Content-Type": "application/json"
        }
    )
    print(f"Archived one Tweet to Airtable: {url}")

    if "id" not in req.json().keys() or req.status_code != 200:
        print(f"Airtable response error: {req.text}")

def resolve_one_dm(dm):
    """
    Gets the details of all Tweets linked in one DM.

    Parameters:
    - dm_id: ID of the DM

    Returns:
    - url: URL of the embedded Tweet
    - id: status ID of the Tweet
    - author: Author of the Tweet
    - content: Content of the Tweet
    - message: (optional) Message associated with the DM
    """
    found_urls = []
    for url in dm.message_create['message_data']['entities']['urls']:
        found_urls.append(url['expanded_url'])
    twitter_urls = []
    for url in found_urls:
        if re.match(r"https?:\/\/(www.)?twitter.com\/.*\/status\/[0-9]+", url):
            twitter_urls.append(url)
    tweets = []
    for url in twitter_urls:
        url_dict = {}
        url_dict['url'] = url
        try:
            tw_id = url.split("status/")[-1]
            tweet = api.get_status(tw_id)
        except tweepy.TweepError as e:
            print(f"Tweet {tw_id} has already been deleted! Skipping...")
            print(f"{e} {e.reason}")
            continue
        url_dict['author'] = tweet.author.screen_name
        url_dict['content'] = tweet.text
        try: url_dict['message'] = dm.message_create['message_data']['text']
        except: url_dict['message'] = ''
        tweets.append(url_dict)
    api.destroy_direct_message(dm.id)
    return tweets

def check_new_twitter():
    new_dms = api.list_direct_messages(50)
    if not new_dms: print("No new DMs found in the inbox.")
    else: print(f"{len(new_dms)} found in the inbox.")
    return new_dms

def main():
    while True:
        new_dms = check_new_twitter()
        if not new_dms: sleep(90)
        else:
            for dm in new_dms:
                for result in resolve_one_dm(dm):
                    one_airtable(result['url'], result['author'], result['content'], waybackpy.Url(result['url']).save().archive_url, message=result['message'])
            sleep(30)

main()
