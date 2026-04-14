import os
from dotenv import load_dotenv

# FIX: Use explicit path for .env file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

CONFIG = {
    # Account Settings
    "username": os.getenv("IG_USERNAME", ""),
    "password": os.getenv("IG_PASSWORD", ""),

    # Target Hashtags
    "hashtags": [
        "photography",
        "travel",
        "lifestyle",
        "fitness",
        "nature",
        "art",
        "food",
        "fashion"
    ],

    # Target Accounts
    "target_accounts": [],

    # Daily Limits
    "limits": {
        "follow_per_day": 100,
        "follow_per_session": 20,
        "unfollow_per_day": 100,
        "unfollow_per_session": 20,
        "like_per_day": 200,
        "like_per_session": 50,
        "hashtag_posts_to_fetch": 30,
    },

    # Delays (seconds)
    "delays": {
        "between_follows": (15, 45),
        "between_likes": (8, 25),
        "between_unfollows": (15, 40),
        "between_hashtags": (60, 120),
        "session_break": (300, 600),
    },

    # Schedule
    "schedule": {
        "morning": "09:00",
        "afternoon": "14:00",
        "evening": "19:00",
    },

    # FIX: Added default value
    "unfollow_after_days": 3,

    # Features Toggle
    "features": {
        "auto_follow": True,
        "auto_like": True,
        "auto_unfollow": True,
        "follow_by_hashtag": True,
        "follow_by_account": False,
        "like_by_hashtag": True,
    }
}
