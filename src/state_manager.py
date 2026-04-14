import json
import os
from datetime import datetime, date, timedelta
from src.utils import log

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
STATE_FILE = os.path.join(DATA_DIR, "state.json")


class StateManager:
    """
    Tracks and enforces daily limits.
    Auto-resets every new day.
    Persists state across GitHub Action runs.
    """

    @staticmethod
    def _default_state() -> dict:
        """Always returns a fresh independent copy"""
        return {
            "date": str(date.today()),
            "daily_counts": {
                "followed":   0,
                "unfollowed": 0,
                "liked":      0,
                "commented":  0,
                "errors":     0
            },
            "session_counts": {
                "followed":   0,
                "unfollowed": 0,
                "liked":      0
            },
            "total_counts": {
                "followed":   0,
                "unfollowed": 0,
                "liked":      0,
                "commented":  0,
                "errors":     0
            },
            "last_action_time":  "",
            "is_rate_limited":   False,
            "rate_limit_until":  "",
            "sessions_today":    0,
            "last_session_time": ""
        }

    def __init__(self, config: dict):
        self.config = config
        self.limits = config.get("limits", {})
        self._state = None
        self._load()

    # ─────────────────────────────────────────
    # LOAD / SAVE
    # ─────────────────────────────────────────

    def _load(self):
        """Load state, merging with defaults for missing keys"""
        os.makedirs(DATA_DIR, exist_ok=True)

        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    loaded = json.loads(content)
                    if isinstance(loaded, dict):
                        # Start from defaults then overlay saved data
                        self._state = self._default_state()
                        self._state.update(loaded)

                        # Fill any missing nested keys
                        for key in ["daily_counts",
                                    "session_counts",
                                    "total_counts"]:
                            defaults = self._default_state()[key]
                            for sub_k, sub_v in defaults.items():
                                if sub_k not in self._state[key]:
                                    self._state[key][sub_k] = sub_v

                        self._check_day_reset()
                        return
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                log(f"⚠️ State corrupted, resetting: {e}", "WARNING")

        # Fresh state
        self._state = self._default_state()
        self._save()

    def _save(self):
        """Atomic save using temp file"""
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2)
            os.replace(tmp, STATE_FILE)
        except Exception as e:
            log(f"❌ State save failed: {e}", "ERROR")
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    def _check_day_reset(self):
        """Reset daily counters if new day detected"""
        today = str(date.today())
        if self._state.get("date") != today:
            log("📅 New day - resetting daily counters", "INFO")
            totals = self._state.get("total_counts", {})
            self._state = self._default_state()
            self._state["total_counts"] = totals
            self._state["date"] = today
            self._save()
            log("✅ Daily reset complete", "SUCCESS")

    # ─────────────────────────────────────────
    # LIMIT CHECKS
    # ─────────────────────────────────────────

    def can_follow(self) -> bool:
        if self._is_rate_limited():
            return False
        daily = self._state["daily_counts"].get("followed", 0)
        limit = self.limits.get("follow_per_day", 100)
        if daily >= limit:
            log(f"🚫 Follow limit reached: {daily}/{limit}", "WARNING")
            return False
        return True

    def can_like(self) -> bool:
        if self._is_rate_limited():
            return False
        daily = self._state["daily_counts"].get("liked", 0)
        limit = self.limits.get("like_per_day", 200)
        if daily >= limit:
            log(f"🚫 Like limit reached: {daily}/{limit}", "WARNING")
            return False
        return True

    def can_unfollow(self) -> bool:
        if self._is_rate_limited():
            return False
        daily = self._state["daily_counts"].get("unfollowed", 0)
        limit = self.limits.get("unfollow_per_day", 100)
        if daily >= limit:
            log(f"🚫 Unfollow limit reached: {daily}/{limit}", "WARNING")
            return False
        return True

    def can_run_session(self) -> bool:
        max_s = self.limits.get("max_sessions_per_day", 3)
        today = self._state.get("sessions_today", 0)
        if today >= max_s:
            log(f"🚫 Max sessions: {today}/{max_s}", "WARNING")
            return False
        return True

    def _is_rate_limited(self) -> bool:
        if not self._state.get("is_rate_limited", False):
            return False
        until_str = self._state.get("rate_limit_until", "")
        if not until_str:
            self._state["is_rate_limited"] = False
            self._save()
            return False
        try:
            until = datetime.fromisoformat(until_str)
            if datetime.now() < until:
                mins = int((until - datetime.now()).total_seconds() / 60)
                log(f"⏳ Rate limited {mins} min remaining", "WARNING")
                return True
            else:
                self._state["is_rate_limited"] = False
                self._state["rate_limit_until"] = ""
                self._save()
                return False
        except ValueError:
            self._state["is_rate_limited"] = False
            self._state["rate_limit_until"] = ""
            self._save()
            return False

    # ─────────────────────────────────────────
    # COUNTERS
    # ─────────────────────────────────────────

    def increment(self, action: str, count: int = 1):
        """Increment daily, session, and total counters"""
        valid = {"followed", "unfollowed", "liked", "commented", "errors"}
        if action not in valid:
            log(f"⚠️ Unknown action: '{action}'", "WARNING")
            return

        self._state["daily_counts"][action] = (
            self._state["daily_counts"].get(action, 0) + count
        )
        self._state["total_counts"][action] = (
            self._state["total_counts"].get(action, 0) + count
        )
        if action in self._state["session_counts"]:
            self._state["session_counts"][action] = (
                self._state["session_counts"].get(action, 0) + count
            )
        self._state["last_action_time"] = datetime.now().isoformat()
        self._save()

    def start_session(self):
        """Increment session counter and reset session counts"""
        self._state["sessions_today"] = (
            self._state.get("sessions_today", 0) + 1
        )
        self._state["last_session_time"] = datetime.now().isoformat()
        self._state["session_counts"] = {
            "followed": 0, "unfollowed": 0, "liked": 0
        }
        self._save()
        log(f"🟢 Session #{self._state['sessions_today']} started",
            "INFO")

    def set_rate_limited(self, minutes: int = 30):
        """Mark bot as rate limited"""
        until = datetime.now() + timedelta(minutes=minutes)
        self._state["is_rate_limited"] = True
        self._state["rate_limit_until"] = until.isoformat()
        self._save()
        log(f"⚠️ Rate limited for {minutes} min", "WARNING")

    def get_remaining(self, action: str) -> int:
        """Remaining allowed actions today"""
        key_map = {
            "followed":   "follow_per_day",
            "liked":      "like_per_day",
            "unfollowed": "unfollow_per_day"
        }
        limit_key = key_map.get(action)
        if not limit_key:
            return 0
        used  = self._state["daily_counts"].get(action, 0)
        limit = self.limits.get(limit_key, 0)
        return max(0, limit - used)

    # ─────────────────────────────────────────
    # REPORTING
    # ─────────────────────────────────────────

    def get_daily_summary(self) -> dict:
        return {
            "date":           self._state.get("date", ""),
            "daily_counts":   self._state.get("daily_counts", {}),
            "session_counts": self._state.get("session_counts", {}),
            "total_counts":   self._state.get("total_counts", {}),
            "sessions_today": self._state.get("sessions_today", 0),
            "is_rate_limited":self._state.get("is_rate_limited", False),
            "remaining": {
                "follows":   self.get_remaining("followed"),
                "likes":     self.get_remaining("liked"),
                "unfollows": self.get_remaining("unfollowed")
            }
        }

    def print_daily_summary(self):
        s = self.get_daily_summary()
        d = s["daily_counts"]
        r = s["remaining"]
        log("=" * 48, "INFO")
        log(f"📊 DAILY SUMMARY - {s['date']}", "INFO")
        log("=" * 48, "INFO")
        log(f"✅ Followed:   {d.get('followed',0)}"
            f"  | Remaining: {r['follows']}",   "INFO")
        log(f"❤️  Liked:      {d.get('liked',0)}"
            f"  | Remaining: {r['likes']}",     "INFO")
        log(f"➖ Unfollowed: {d.get('unfollowed',0)}"
            f"  | Remaining: {r['unfollows']}", "INFO")
        log(f"❌ Errors:     {d.get('errors',0)}",  "INFO")
        log(f"🔄 Sessions:   {s['sessions_today']}", "INFO")
        log("=" * 48, "INFO")
