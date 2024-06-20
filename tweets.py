from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.relative_locator import locate_with
from selenium.webdriver.common.action_chains import ActionChains
from datetime import date, datetime
from bs4 import BeautifulSoup
import time
import json
import os
import pymongo



seen_tweets_file = 'seen_tweets.json' # name of the file we will store the tweet instances
USERNAME = "cjnaskhf"
PASSWORD = "Sarpusgladius.28"
ACCOUNTS = ["onat_sf1", "fenerbahce"] # accounts to be scraped
DATECAP = 10 # stop extracting if the tweet was posted this amount of days ago

def days_difference(given_date_str):
    """
    Calculate the difference in days between a given date and today's date.
    This will be run the first time the program scrapes a given account to
    prevent scraping all the comments the account has ever posted.

    Input:
        given_date_str[str]: A string representing the given date in the format 'YYYY-MM-DD'
    Output[int]:
        The difference in days as an integer
    """
    # parse the given date string into a datetime object
    given_date = datetime.strptime(given_date_str, "%Y-%m-%d")
    
    # get today's date
    today = datetime.today()
    
    # calculate the difference in days
    difference = today - given_date
    
    return difference.days

def upload_to_mongo(tweets):
    """
    Uploads the given tweets to MongoDB.

   Inputs:
        tweets[list[dict]]: A list of tweet dictionaries to upload
    """
    # connect to mongodb
    client = pymongo.MongoClient("mongodb://localhost:27017/")
    db = client["ScrapedTweets"]
    collection = db["tweets"]
    
    # insert the tweets into the collection
    if tweets:
        collection.insert_many(tweets)
    client.close()

def save_seen_tweets(data):
    """
    Saves the given tweet data to the json file

    Inputs:
        data[list[dict]]: A list of tweet dictionaries to upload to the file


    """
    # read the tweets from the file
    file_data = read_seen_tweets("add")

    # add the new tweets
    file_data.extend(data)

    # write the everything back to the file
    with open(seen_tweets_file, "w", encoding="utf-8") as file:
        json.dump(file_data, file, ensure_ascii=False, indent=4)

def read_seen_tweets(click = None):
    """
    Either reads everything in the json file or the tweet ids only

    Inputs:
        optional argument, if you pass "add", it reads everything, otherwise ids only

    """
        
    if os.path.exists(seen_tweets_file):
        with open(seen_tweets_file, 'r', encoding="utf-8") as file:
           
            # if we are adding stuff, read everything by passing in "add" string
            if click == ("add"):
                return json.load(file)
            else:
                # if we just want to check ids, read the ids only
                return [tweet["id"] for tweet in json.load(file)]
    #if file is empty
    return []

def extract_tweets():
    """
    Uses selenium to log into a twitter account, and scrape passes the html page source to the parse_account function
    """

    # initialize chrome webdriver
    driver = webdriver.Chrome()

    # go to x login
    driver.get("https://x.com/i/flow/login")
    time.sleep(5)

    # Fill in username click on the login button
    username_input = driver.find_element(By.XPATH, '//input[@type="text"]')
    username_input.send_keys(USERNAME)
    login_button = locate_with(By.TAG_NAME, "button").below({By.TAG_NAME: "input"})
    driver.find_element(login_button).click()
    time.sleep(3)



    # Fill in password and click on the login button
    password_input = driver.find_element(By.XPATH, '//input[@type="password"]')
    password_input.send_keys(PASSWORD)
    last_login_button = driver.find_element(By.XPATH, '//button[@data-testid="LoginForm_Login_Button"]')
    last_login_button.click()
    time.sleep(3)

    # the list that will will be uploaded to mongo and the json
    to_mongo = []

    # scrape for each account
    for account in ACCOUNTS:
        driver.get(f"https://twitter.com/{account}")
        time.sleep(2)
        
         
        while True:
            html = driver.page_source

            # click is 1 if we encounter a tweet we already scraped, in which case we stop scraping
            new_tweets_batch, click = parse_account(html)
            if click == 1:
                break

            # if we encountered only new tweets this run, we add the tweets and scroll down to load more tweets
            if new_tweets_batch:
                for tweet in new_tweets_batch:
                    #we check if we already recorded these tweets because even after scrolling, we may encounter some tweets that we added in the previous run
                    if tweet not in to_mongo:
                        to_mongo.append(tweet) 
                driver.execute_script("window.scrollBy(0, 2500);")
                time.sleep(2)

            # if we scrape everything, the new_tweets_batch is an empty list so we end the loop
            else:
                break
        print(to_mongo)

    # save tweets to json
    save_seen_tweets(to_mongo)   

    # save tweets to mongodb 
    upload_to_mongo(to_mongo)

    driver.close()



def parse_account(html):
    """
    Uses beautifulsoup to extract information about the tweets of a given account

    Inputs:
        html code of a given webpage instance
    """

    new_tweets = []
    soup = BeautifulSoup(html, "html.parser")
    
    # Extract the tweets
    tweets = soup.find_all(attrs={"data-testid": "tweet"})
    
    #this is used to break out of the nested loop below
    click = 0
    
    for tweet in tweets:
        if click == 1:
            break

        links = tweet.find_all('a')
        is_pinned = tweet.find(attrs={"data-testid": "socialContext"})

        #extracts the text
        tweet_text = tweet.find(attrs={"data-testid": "tweetText"})

        #extracts the date in "Y-m-d" format
        day_year = tweet.find('time')['datetime'][:10]
        if not tweet_text or is_pinned: #if tweet doesn't have text or is pinned comment, skip
            continue
        print(days_difference(day_year))
        if days_difference(day_year) > DATECAP: #if the tweet has been posted more than DATECAP days ago, break
            break
        for link in links:
            # using the url to get the tweeet id
            url = link.get('href')
            if "/status/" in url: #extraction of tweet id from the url
                lst = url.split("/status/")
                # get the id
                twt_id = lst[1]
                if "/" not in twt_id:
                    # as soon as you encounter an old id, break
                    if int(twt_id) in read_seen_tweets():
                        click = 1
                        break
                    final_url = "https://x.com" + url 
                    new_tweets.append({"url": final_url , "tweet": tweet_text.text, "account": lst[0][1:], "date": day_year, "id": int(twt_id)})

    return (new_tweets, click) if new_tweets else (None, click)

def main():
    if not os.path.exists(seen_tweets_file):
        with open(seen_tweets_file, "w", encoding="utf-8") as file:
            json.dump([], file, ensure_ascii=False, indent=4)
    extract_tweets()

if __name__ == "__main__":
    main()
