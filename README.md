# 🗣️ Social Media Reader

**Social Media Reader** is a Python-based tool that scrapes and reads social media content aloud using realistic AI-generated voices from [Inworld.ai](https://inworld.ai/). It currently supports Twitter and Reddit.

---

## 📦 Features

- 🔍 Scrape Reddit or Twitter content
- 🧠 Convert text to speech with Inworld TTS
- 🎙️ Assigns unique voices to users for more immersive playback
- 📁 Reads from local Reddit JSON or BrightData datasets
- 🖥️ Works on macOS, Linux, and Windows

---

## 🛠️ Setup

### 1. Clone the Repository

```bash
git clone https://github.com/KaushikSiva/social-media-reader.git
cd social-media-reader
```

### 2. Create a Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate  # For macOS/Linux
# OR
.venv\Scripts\activate  # For Windows
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Setup the .env file
```bash
INWORLD_API_TOKEN=your_inworld_api_key
BRIGHT_DATA_API_TOKEN=your_brightdata_api_key
DATASET_ID=your_brightdata_dataset_id  # Optional
```

## 🐍 Usage

🔸 Read Reddit Comments (from JSON file)
```bash
python readers/reddit_reader.py
```
You’ll be prompted to input the path to a .reddit_comments.json file.

🔸 Scrape Tweets via Selenium
```bash
python readers/twitter_reader.py
```
Make sure chromedriver is installed and in your PATH.

## 📁 Project Structure
```bash
social-media-reader/
├── readers/
│   ├── reddit_reader.py
│   └── twitter_reader.py
├── tts_voice/
│   └── speak.py
├── .env
├── .gitignore
├── requirements.txt
└── README.md
```

## 📦 Requirements

Python 3.8+

Google Chrome + chromedriver (for Twitter scraping)

## 📦 Requirements

Python 3.8+

Google Chrome + chromedriver (for Twitter scraping)

## 🔊 Powered By
Inworld TTS API

BrightData Reddit API

Selenium

Pydub

