import re
import os
from src.utils import log


class Validator:
    """
    Validates credentials, config,
    Instagram data, and environment.
    """

    # ─────────────────────────────────────────
    # CREDENTIALS
    # ─────────────────────────────────────────

    @staticmethod
    def validate_username(username: str) -> tuple:
        if not username or not isinstance(username, str):
            return False, "Username is empty or not a string"
        username = username.strip()
        if len(username) < 1:
            return False, "Username too short"
        if len(username) > 30:
            return False, "Username too long (max 30)"
        if not re.match(r'^[a-zA-Z0-9._]+$', username):
            return False, (
                "Only letters, numbers, periods, underscores allowed"
            )
        if username.startswith(".") or username.endswith("."):
            return False, "Cannot start/end with period"
        if ".." in username:
            return False, "Cannot have consecutive periods"
        return True, ""

    @staticmethod
    def validate_password(password: str) -> tuple:
        if not password or not isinstance(password, str):
            return False, "Password empty or not a string"
        if len(password) < 6:
            return False, "Too short (min 6)"
        if len(password) > 150:
            return False, "Too long (max 150)"
        return True, ""

    # ─────────────────────────────────────────
    # CONFIG
    # ─────────────────────────────────────────

    @staticmethod
    def validate_config(config: dict) -> tuple:
        """Returns (is_valid, errors_list)"""
        errors = []

        if not isinstance(config, dict):
            return False, ["Config must be a dict"]

        # Top-level keys
        for key in ["username", "password", "hashtags",
                    "limits", "delays", "features", "schedule"]:
            if key not in config:
                errors.append(f"Missing key: '{key}'")

        if errors:
            return False, errors

        # ── Limits ──
        limits = config.get("limits", {})
        limit_rules = {
            "follow_per_day":         (1, 150),
            "follow_per_session":     (1,  50),
            "unfollow_per_day":       (1, 150),
            "unfollow_per_session":   (1,  50),
            "like_per_day":           (1, 300),
            "like_per_session":       (1, 100),
            "hashtag_posts_to_fetch": (1,  50),
            "max_sessions_per_day":   (1,  10),
        }
        for key, (mn, mx) in limit_rules.items():
            if key not in limits:
                errors.append(f"Missing limit: '{key}'")
                continue
            val = limits[key]
            if not isinstance(val, int):
                errors.append(f"Limit '{key}' must be int")
                continue
            if val < mn:
                errors.append(f"Limit '{key}'={val} < min={mn}")
            if val > mx:
                errors.append(
                    f"Limit '{key}'={val} > max={mx} (ban risk!)"
                )

        # ── Delays ──
        delays = config.get("delays", {})
        delay_rules = {
            "between_follows":   (5,   3600),
            "between_likes":     (3,   3600),
            "between_unfollows": (5,   3600),
            "between_hashtags":  (10,  7200),
            "session_break":     (60, 86400),
        }
        for key, (mn, _) in delay_rules.items():
            if key not in delays:
                errors.append(f"Missing delay: '{key}'")
                continue
            val = delays[key]
            if not isinstance(val, (tuple, list)) or len(val) != 2:
                errors.append(f"Delay '{key}' must be (min, max)")
                continue
            dmin, dmax = val
            if not isinstance(dmin, (int, float)) or \
               not isinstance(dmax, (int, float)):
                errors.append(f"Delay '{key}' values must be numbers")
                continue
            if dmin < mn:
                errors.append(
                    f"Delay '{key}' min={dmin} too low (min {mn}s)"
                )
            if dmin >= dmax:
                errors.append(f"Delay '{key}' min must be < max")

        # ── Hashtags ──
        hashtags = config.get("hashtags", [])
        if not isinstance(hashtags, list):
            errors.append("'hashtags' must be a list")
        elif len(hashtags) == 0:
            errors.append("'hashtags' is empty")
        else:
            for i, tag in enumerate(hashtags):
                ok, err = Validator.validate_hashtag(tag)
                if not ok:
                    errors.append(f"hashtags[{i}] '{tag}': {err}")

        # ── Features ──
        features = config.get("features", {})
        for feat in ["auto_follow", "auto_like", "auto_unfollow",
                     "follow_by_hashtag", "like_by_hashtag"]:
            if feat not in features:
                errors.append(f"Missing feature: '{feat}'")
            elif not isinstance(features[feat], bool):
                errors.append(f"Feature '{feat}' must be bool")

        # ── Schedule ──
        schedule = config.get("schedule", {})
        if not isinstance(schedule, dict):
            errors.append("'schedule' must be dict")
        else:
            for name, tstr in schedule.items():
                ok, err = Validator.validate_time_string(tstr)
                if not ok:
                    errors.append(f"schedule.{name}: {err}")

        return len(errors) == 0, errors

    # ─────────────────────────────────────────
    # INSTAGRAM DATA
    # ─────────────────────────────────────────

    @staticmethod
    def validate_hashtag(hashtag: str) -> tuple:
        if not hashtag or not isinstance(hashtag, str):
            return False, "Empty or not a string"
        tag = hashtag.lstrip("#").strip()
        if not tag:
            return False, "Empty after cleaning"
        if len(tag) > 30:
            return False, "Too long (max 30)"
        if " " in tag:
            return False, "No spaces allowed"
        # Allow ASCII word chars + unicode letters/symbols
        if re.search(r'[^\w\u0080-\uFFFF]', tag):
            return False, "Invalid characters"
        return True, ""

    @staticmethod
    def validate_user_id(user_id) -> tuple:
        if user_id is None:
            return False, "user_id is None"
        try:
            uid = int(user_id)
            if uid <= 0:
                return False, "Must be positive integer"
            return True, ""
        except (ValueError, TypeError):
            return False, f"Not numeric: {type(user_id)}"

    @staticmethod
    def validate_media_id(media_id) -> tuple:
        if media_id is None:
            return False, "media_id is None"
        if not str(media_id).strip():
            return False, "media_id is empty"
        return True, ""

    @staticmethod
    def validate_time_string(time_str: str) -> tuple:
        if not isinstance(time_str, str):
            return False, "Must be string"
        if not re.match(r'^\d{2}:\d{2}$', time_str):
            return False, "Must be HH:MM"
        h, m = time_str.split(":")
        if not (0 <= int(h) <= 23):
            return False, "Hour 00-23"
        if not (0 <= int(m) <= 59):
            return False, "Minute 00-59"
        return True, ""

    # ─────────────────────────────────────────
    # ENVIRONMENT
    # ─────────────────────────────────────────

    @staticmethod
    def validate_environment() -> tuple:
        errors = []
        if not os.getenv("IG_USERNAME", "").strip():
            errors.append("IG_USERNAME not set")
        if not os.getenv("IG_PASSWORD", "").strip():
            errors.append("IG_PASSWORD not set")
        return len(errors) == 0, errors

    @staticmethod
    def run_startup_checks(config: dict) -> bool:
        """Run all checks. Returns True only if all pass."""
        log("🔍 Running startup checks...", "INFO")
        all_ok = True

        env_ok, env_errs = Validator.validate_environment()
        if not env_ok:
            all_ok = False
            for e in env_errs:
                log(f"❌ ENV: {e}", "ERROR")
        else:
            log("✅ Environment OK", "SUCCESS")

        cfg_ok, cfg_errs = Validator.validate_config(config)
        if not cfg_ok:
            all_ok = False
            for e in cfg_errs:
                log(f"❌ CONFIG: {e}", "ERROR")
        else:
            log("✅ Config OK", "SUCCESS")

        base     = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        data_dir = os.path.join(base, "data")
        try:
            os.makedirs(data_dir, exist_ok=True)
            log("✅ Data directory OK", "SUCCESS")
        except Exception as e:
            log(f"❌ Data dir: {e}", "ERROR")
            all_ok = False

        if all_ok:
            log("✅ All startup checks passed!", "SUCCESS")
        else:
            log("❌ Fix errors above before running", "ERROR")

        return all_ok
