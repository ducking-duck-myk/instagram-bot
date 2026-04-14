# 📸 Instagram Auto Bot v2.0

## ✨ Features
- ✅ Auto Follow by hashtag or account
- ❤️ Auto Like by hashtag
- ➖ Smart Unfollow (non-followers only)
- 📊 Daily state management & limits
- 🔄 Smart retry with exponential backoff
- 🔍 Strong validation on all inputs
- 🚫 Anti-duplication (never repeat actions)
- 🔃 Hashtag rotation (least-used first)
- 🖤 Blacklist system
- 💾 Session persistence
- 📅 GitHub Actions scheduler

## 🚀 Setup

### 1. Clone
git clone https://github.com/you/instagram-bot
cd instagram-bot

### 2. Install
pip install -r requirements.txt

### 3. Create .env
IG_USERNAME=your_username
IG_PASSWORD=your_password

### 4. Configure config.py
Edit hashtags, limits, features

## ▶️ Run

python main.py --full      # Everything
python main.py --follow    # Follow only
python main.py --like      # Like only
python main.py --unfollow  # Unfollow only
python main.py --schedule  # Auto schedule
python main.py --stats     # Today's stats

## 🔑 GitHub Secrets
Settings → Secrets → Actions:
- IG_USERNAME
- IG_PASSWORD

## ⚠️ Safe Limits
| Action    | Safe/Day |
|-----------|----------|
| Follow    | < 150    |
| Like      | < 300    |
| Unfollow  | < 150    |
