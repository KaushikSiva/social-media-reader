from selenium import webdriver
from selenium.webdriver.common.by import By
import time
import pyttsx3

# Setup Chrome driver
options = webdriver.ChromeOptions()
options.add_argument("--start-maximized")
driver = webdriver.Chrome(options=options)

# Navigate to a Twitter profile or home page
url = "https://twitter.com/elonmusk"  # Replace with your target
driver.get(url)

time.sleep(5)  # Wait for tweets to load (you can fine-tune this)

# Collect tweets and usernames
tweet_elements = driver.find_elements(By.XPATH, '//article//div[@data-testid="tweetText"]')
user_elements = driver.find_elements(By.XPATH, '//article//div[@dir="ltr"]/span[contains(text(), "@")]')

# Prepare voice engine
engine = pyttsx3.init()
voices = engine.getProperty('voices')

# Create user-voice mapping
user_voice_map = {}
voice_index = 0

def get_voice_for_user(user):
    global voice_index
    if user not in user_voice_map:
        user_voice_map[user] = voices[voice_index % len(voices)].id
        voice_index += 1
    return user_voice_map[user]

# Read tweets out loud
for user_el, tweet_el in zip(user_elements, tweet_elements):
    user = user_el.text.strip()
    tweet = tweet_el.text.strip()

    voice_id = get_voice_for_user(user)
    engine.setProperty('voice', voice_id)

    print(f"{user}: {tweet}")
    engine.say(f"{user} says: {tweet}")
    engine.runAndWait()

driver.quit()
