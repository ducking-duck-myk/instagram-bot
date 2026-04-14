import random
import os
from instagrapi import Client
from instagrapi.exceptions import (
    LoginRequired,
    ChallengeRequired,
    BadPassword,
    TwoFactorRequired
)
from src.utils import log, random_delay, ensure_data_dir
from src.actions import BotActions
from src.state_manager import StateManager
from src.validator import Validator
from src.anti_duplicate import AntiDuplicate
from src.retry_handler import BotFatalError

BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESSION_FILE = os.path.join(BASE_DIR, "data", "session.json")


class InstagramBot:
    """
    Main bot class.
    Handles login, session management,
    and orchestrates all action sessions.
    """

    def __init__(self, config: dict):
        self.config = config
        self.client = Client()
        self.state  = StateManager(config)
        self.dupes  = AntiDuplicate()
        self.actions      = None
        self.is_logged_in = False

        # Mimic Samsung Galaxy S9+
        self.client.set_device({
            "app_version":    "269.0.0.18.75",
            "android_version": 26,
            "android_release": "8.0.0",
            "dpi":             "480dpi",
            "resolution":      "1080x1920",
            "manufacturer":    "Samsung",
            "device":          "SM-G965F",
            "model":           "star2qltecs",
            "cpu":             "samsungexynos9810",
            "version_code":    "314665256"
        })
        self.client.set_user_agent(
            "Instagram 269.0.0.18.75 Android (26/8.0.0; "
            "480dpi; 1080x1920; samsung; SM-G965F; "
            "star2qltecs; samsungexynos9810; en_US; 314665256)"
        )

    # ─────────────────────────────────────────
    # LOGIN
    # ─────────────────────────────────────────

    def login(self) -> bool:
        ensure_data_dir()
        username = self.config.get("username", "")
        password = self.config.get("password", "")

        u_ok, u_err = Validator.validate_username(username)
        if not u_ok:
            log(f"❌ Bad username: {u_err}", "ERROR")
            return False

        p_ok, p_err = Validator.validate_password(password)
        if not p_ok:
            log(f"❌ Bad password: {p_err}", "ERROR")
            return False

        log(f"🔐 Logging in as @{username}...", "INFO")

        # Try session first
        if os.path.exists(SESSION_FILE):
            try:
                log("📂 Loading saved session...", "INFO")
                self.client.load_settings(SESSION_FILE)
                self.client.login(username, password)
                self.client.get_timeline_feed()
                log("✅ Session login OK!", "SUCCESS")
                self._setup_actions()
                return True
            except LoginRequired:
                log("⚠️ Session expired", "WARNING")
            except Exception as e:
                log(f"⚠️ Session failed: {str(e)[:60]}", "WARNING")

        # Fresh login
        try:
            self.client.login(username, password)
            ensure_data_dir()
            self.client.dump_settings(SESSION_FILE)
            log("✅ Login OK! Session saved.", "SUCCESS")
            self._setup_actions()
            return True

        except BadPassword:
            log("❌ Wrong password!", "ERROR")
        except TwoFactorRequired:
            log("❌ 2FA enabled - disable first", "ERROR")
        except ChallengeRequired:
            log("❌ Challenge required - login manually first", "ERROR")
        except LoginRequired:
            log("❌ Login required error", "ERROR")
        except Exception as e:
            log(f"❌ Login error: {str(e)[:80]}", "ERROR")

        return False

    def _setup_actions(self):
        """Initialize after successful login"""
        self.is_logged_in = True
        self.actions = BotActions(
            self.client,
            self.config,
            self.state
        )

    # ─────────────────────────────────────────
    # GUARDS
    # ─────────────────────────────────────────

    def _logged_in_guard(self) -> bool:
        if not self.is_logged_in:
            log("❌ Not logged in!", "ERROR")
            return False
        return True

    # ─────────────────────────────────────────
    # SESSIONS
    # ─────────────────────────────────────────

    def run_follow_session(self):
        if not self._logged_in_guard():
            return
        if not self.state.can_follow():
            log("🚫 Daily follow limit reached", "WARNING")
            return
        if not self.state.can_run_session():
            log("🚫 Max sessions today reached", "WARNING")
            return

        log("🚀 Follow Session", "ACTION")

        hashtags = self.dupes.get_next_hashtags(
            self.config["hashtags"], count=3
        )

        try:
            if self.config["features"].get("follow_by_hashtag") \
                    and hashtags:
                for tag in hashtags:
                    self.actions.follow_by_hashtag(tag)
                    random_delay(
                        self.config["delays"]["between_hashtags"]
                    )

            if self.config["features"].get("follow_by_account"):
                for acct in self.config.get("target_accounts", []):
                    self.actions.follow_by_account_followers(acct)
                    random_delay(
                        self.config["delays"]["between_hashtags"]
                    )
        except BotFatalError as e:
            log(f"🚨 Fatal in follow session: {e}", "ERROR")
            raise

    def run_like_session(self):
        if not self._logged_in_guard():
            return
        if not self.state.can_like():
            log("🚫 Daily like limit reached", "WARNING")
            return

        log("❤️ Like Session", "ACTION")

        hashtags = self.dupes.get_next_hashtags(
            self.config["hashtags"], count=4
        )

        try:
            if self.config["features"].get("like_by_hashtag") \
                    and hashtags:
                for tag in hashtags:
                    self.actions.like_by_hashtag(tag)
                    random_delay(
                        self.config["delays"]["between_hashtags"]
                    )
        except BotFatalError as e:
            log(f"🚨 Fatal in like session: {e}", "ERROR")
            raise

    def run_unfollow_session(self):
        if not self._logged_in_guard():
            return
        if not self.state.can_unfollow():
            log("🚫 Daily unfollow limit reached", "WARNING")
            return

        if self.config["features"].get("auto_unfollow"):
            log("➖ Unfollow Session", "ACTION")
            try:
                self.actions.unfollow_non_followers()
            except BotFatalError as e:
                log(f"🚨 Fatal in unfollow: {e}", "ERROR")
                raise

    def run_full_session(self) -> dict:
        if not self.state.can_run_session():
            log("🚫 Max sessions today", "WARNING")
            return self._empty_stats()

        log("🤖 Full Bot Session", "ACTION")
        self.state.start_session()

        try:
            if self.config["features"].get("auto_follow"):
                self.run_follow_session()
                random_delay(self.config["delays"]["session_break"])

            if self.config["features"].get("auto_like"):
                self.run_like_session()
                random_delay(self.config["delays"]["session_break"])

            if self.config["features"].get("auto_unfollow"):
                self.run_unfollow_session()

        except BotFatalError as e:
            log(f"🚨 Fatal - session stopped: {e}", "ERROR")

        self.state.print_daily_summary()

        return (
            self.actions.get_stats()
            if self.actions
            else self._empty_stats()
        )

    def _empty_stats(self) -> dict:
        return {
            "followed":   0,
            "liked":      0,
            "unfollowed": 0,
            "skipped":    0,
            "errors":     0
      }
