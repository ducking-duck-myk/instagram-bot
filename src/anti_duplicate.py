import json
import os
from datetime import datetime
from src.utils import log

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

FOLLOWED_FILE  = os.path.join(DATA_DIR, "followed_users.json")
LIKED_FILE     = os.path.join(DATA_DIR, "liked_posts.json")
BLACKLIST_FILE = os.path.join(DATA_DIR, "blacklist.json")
HASHTAG_FILE   = os.path.join(DATA_DIR, "seen_hashtags.json")


class AntiDuplicate:
    """
    Prevents duplicate follows, likes.
    Manages blacklist and hashtag rotation.
    All data persists across sessions.
    """

    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self._followed      = self._load(FOLLOWED_FILE)
        self._liked         = self._load(LIKED_FILE)
        self._blacklist     = self._load(BLACKLIST_FILE)
        self._seen_hashtags = self._load(HASHTAG_FILE)

    # ─────────────────────────────────────────
    # FILE I/O
    # ─────────────────────────────────────────

    def _load(self, filepath: str) -> dict:
        if not os.path.exists(filepath):
            return {}
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if not content:
                return {}
            data = json.loads(content)
            if not isinstance(data, dict):
                log(f"⚠️ {os.path.basename(filepath)} not dict, reset",
                    "WARNING")
                return {}
            return data
        except json.JSONDecodeError as e:
            log(f"⚠️ JSON error {os.path.basename(filepath)}: {e}",
                "WARNING")
            return {}
        except IOError as e:
            log(f"❌ IO error {os.path.basename(filepath)}: {e}",
                "ERROR")
            return {}

    def _save(self, filepath: str, data: dict):
        """Atomic save"""
        tmp = filepath + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, filepath)
        except IOError as e:
            log(f"❌ Save error {os.path.basename(filepath)}: {e}",
                "ERROR")
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat()

    # ─────────────────────────────────────────
    # FOLLOW TRACKING
    # ─────────────────────────────────────────

    def has_followed(self, user_id) -> bool:
        return str(user_id) in self._followed

    def mark_followed(self, user_id, username: str = ""):
        uid      = str(user_id)
        existing = self._followed.get(uid, {})
        self._followed[uid] = {
            "username":     username or existing.get("username", ""),
            "followed_at":  self._now(),
            "unfollowed":   False,
            "unfollowed_at": None,
            # Preserve existing count
            "follow_count": existing.get("follow_count", 0) + 1
        }
        self._save(FOLLOWED_FILE, self._followed)

    def mark_unfollowed(self, user_id):
        uid = str(user_id)
        if uid in self._followed:
            self._followed[uid]["unfollowed"]    = True
            self._followed[uid]["unfollowed_at"] = self._now()
            self._save(FOLLOWED_FILE, self._followed)

    def get_users_to_unfollow(self, after_days: int = 3) -> list:
        """Oldest first (most overdue at top)"""
        result = []
        now    = datetime.now()

        for uid, data in self._followed.items():
            if not isinstance(data, dict):
                continue
            if data.get("unfollowed", False):
                continue
            followed_at_str = data.get("followed_at", "")
            if not followed_at_str:
                continue
            try:
                followed_at = datetime.fromisoformat(followed_at_str)
                days_passed = (now - followed_at).days
                if days_passed >= after_days:
                    result.append({
                        "user_id":     uid,
                        "username":    data.get("username", "unknown"),
                        "followed_at": followed_at_str,
                        "days_ago":    days_passed
                    })
            except ValueError:
                continue

        result.sort(key=lambda x: x["days_ago"], reverse=True)
        return result

    def followed_count(self) -> int:
        return len(self._followed)

    def active_following_count(self) -> int:
        return sum(
            1 for d in self._followed.values()
            if isinstance(d, dict) and not d.get("unfollowed", False)
        )

    # ─────────────────────────────────────────
    # LIKE TRACKING
    # ─────────────────────────────────────────

    def has_liked(self, media_id) -> bool:
        return str(media_id) in self._liked

    def mark_liked(
        self,
        media_id,
        username: str = "",
        hashtag:  str = ""
    ):
        self._liked[str(media_id)] = {
            "username": username,
            "hashtag":  hashtag,
            "liked_at": self._now()
        }
        self._save(LIKED_FILE, self._liked)

    def liked_count(self) -> int:
        return len(self._liked)

    # ─────────────────────────────────────────
    # BLACKLIST
    # ─────────────────────────────────────────

    def is_blacklisted(
        self,
        user_id  = None,
        username: str = ""
    ) -> bool:
        ids       = self._blacklist.get("ids", {})
        usernames = self._blacklist.get("usernames", {})
        if user_id and str(user_id) in ids:
            return True
        if username and username.lower() in usernames:
            return True
        return False

    def add_to_blacklist(
        self,
        user_id  = None,
        username: str = "",
        reason:   str = ""
    ):
        self._blacklist.setdefault("ids", {})
        self._blacklist.setdefault("usernames", {})
        entry = {
            "username": username,
            "reason":   reason,
            "added_at": self._now()
        }
        if user_id:
            self._blacklist["ids"][str(user_id)] = entry
        if username:
            self._blacklist["usernames"][username.lower()] = entry
        self._save(BLACKLIST_FILE, self._blacklist)
        log(f"🚫 Blacklisted @{username}: {reason}", "WARNING")

    def remove_from_blacklist(
        self,
        user_id  = None,
        username: str = ""
    ):
        if user_id:
            self._blacklist.get("ids", {}).pop(str(user_id), None)
        if username:
            self._blacklist.get("usernames", {}).pop(
                username.lower(), None
            )
        self._save(BLACKLIST_FILE, self._blacklist)

    # ─────────────────────────────────────────
    # HASHTAG ROTATION
    # ─────────────────────────────────────────

    def get_next_hashtags(
        self,
        hashtag_list: list,
        count: int = 3
    ) -> list:
        """Return least-recently-used hashtags first"""
        if not hashtag_list:
            log("⚠️ Hashtag list is empty", "WARNING")
            return []

        scored = []
        for tag in hashtag_list:
            if not isinstance(tag, str):
                continue
            clean = tag.lstrip("#").lower().strip()
            if not clean:
                continue
            info = self._seen_hashtags.get(clean, {})
            scored.append({
                "tag":       clean,
                "last_used": info.get("last_used", ""),
                "use_count": info.get("use_count", 0)
            })

        if not scored:
            return []

        # Sort: fewest uses first, then oldest
        scored.sort(key=lambda x: (x["use_count"], x["last_used"]))
        return [s["tag"] for s in scored[:min(count, len(scored))]]

    def mark_hashtag_used(self, hashtag: str):
        tag = hashtag.lstrip("#").lower().strip()
        if not tag:
            return
        existing = self._seen_hashtags.get(tag, {})
        self._seen_hashtags[tag] = {
            "last_used": self._now(),
            "use_count": existing.get("use_count", 0) + 1
        }
        self._save(HASHTAG_FILE, self._seen_hashtags)

    # ─────────────────────────────────────────
    # STATS
    # ─────────────────────────────────────────

    def get_stats(self) -> dict:
        return {
            "total_followed_ever":   self.followed_count(),
            "currently_following":   self.active_following_count(),
            "total_liked":           self.liked_count(),
            "blacklisted_ids":       len(
                self._blacklist.get("ids", {})
            ),
            "blacklisted_usernames": len(
                self._blacklist.get("usernames", {})
            ),
            "hashtags_tracked":      len(self._seen_hashtags)
  }
