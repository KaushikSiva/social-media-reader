import time
from tts_voice import speak
import random
import os
from selenium import webdriver
from selenium.webdriver.common.by import By


TWITTER_URL = os.getenv("TWITTER_URL", "https://twitter.com/elonmusk")
SCROLL_TIMES = 3
TTS_URL = "https://api.inworld.ai/tts/v1/voice:stream"
VOICE_LIST_URL = "https://api.inworld.ai/tts/v1/voices"

# ========================================
# 🔀 Assign Voices to Users
# ========================================
def assign_voices(users, all_voices):
    voice_map = {}
    available = all_voices.copy()
    random.shuffle(available)
    for user in users:
        if not available:
            available = all_voices.copy()
            random.shuffle(available)
        voice_map[user] = available.pop()
    return voice_map


# ========================================
# 🔍 Scrape Tweets (Your Method)
# ========================================
def scrape_tweets():
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=options)

    print(f"🔗 Navigating to {TWITTER_URL}")
    driver.get(TWITTER_URL)
    time.sleep(5)

    # Scroll to load tweets
    for _ in range(SCROLL_TIMES):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

    # Extract usernames and tweets from current DOM
    tweet_elements = driver.find_elements(By.XPATH, '//article//div[@data-testid="tweetText"]')
    user_elements = driver.find_elements(By.XPATH, '//article//div[@dir="ltr"]/span[contains(text(), "@")]')

    tweets = []
    for user_el, tweet_el in zip(user_elements, tweet_elements):
        user = user_el.text.strip()
        tweet = tweet_el.text.strip()
        tweets.append((user, tweet))

    driver.quit()
    return tweets

# ========================================
# 🚀 Main Execution
# ========================================
def main():
    tweets = scrape_tweets()
    users = list({user for user, _ in tweets})

    all_voices = speak.fetch_available_voices()
    voice_map = assign_voices(users, all_voices)

    for user, tweet in tweets:
        voice = voice_map[user]
        print(f"\n🎙️ {user} ({voice}): {tweet}")
        speak.speak(f"{tweet}", voice)

if __name__ == "__main__":
    main()
