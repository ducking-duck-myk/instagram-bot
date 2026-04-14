import time
import random
import functools
from src.utils import log

# ── Error categories ──
RETRYABLE_ERRORS = [
    "please wait a few minutes",
    "connectionerror",
    "timeout",
    "servererror",
    "502", "503", "504",
    "jsondecode",
    "clientconnectionerror",
    "socket",
    "timed out",
    "network",
    "remotedisconnected"
]

FATAL_ERRORS = [
    "checkpoint_required",
    "challengerequired",
    "login_required",
    "badpassword",
    "invalid credentials",
    "account has been disabled",
    "iglogintowofactorrequired",
    "consent_required",
    "useridnotfound"
]

RATE_LIMIT_ERRORS = [
    "feedback_required",
    "please wait a few minutes before you try again",
    "action_blocked",
    "action blocked",
    "spam",
    "too many",
    "rate limit",
    "429",
    "throttled"
]


class BotFatalError(Exception):
    """Raised on unrecoverable Instagram errors"""
    pass


class RetryHandler:
    """
    Smart retry with:
    - Exponential backoff + jitter
    - Error categorization
    - Rate limit handling
    - Interruptible sleep
    """

    def __init__(self, state_manager=None):
        self.state_manager = state_manager

    def _classify(self, error: Exception) -> str:
        """Returns: fatal | rate_limit | retryable | unknown"""
        err = str(error).lower()
        if any(e in err for e in FATAL_ERRORS):
            return "fatal"
        if any(e in err for e in RATE_LIMIT_ERRORS):
            return "rate_limit"
        if any(e in err for e in RETRYABLE_ERRORS):
            return "retryable"
        return "unknown"

    def get_backoff_time(
        self,
        attempt: int,
        base: float = 30.0,
        max_wait: float = 600.0
    ) -> float:
        """Exponential backoff with ±20% jitter"""
        attempt = min(attempt, 10)          # Clamp to avoid overflow
        backoff = min(base * (2 ** (attempt - 1)), max_wait)
        jitter  = backoff * 0.2 * random.uniform(-1, 1)
        return max(5.0, backoff + jitter)

    @staticmethod
    def _interruptible_sleep(seconds: float):
        """Sleep in 5s chunks so CTRL+C works"""
        remaining = float(seconds)
        while remaining > 0:
            time.sleep(min(5.0, remaining))
            remaining -= 5.0

    def execute(
        self,
        func,
        *args,
        max_attempts: int = 3,
        action_name:  str = "action",
        **kwargs
    ):
        """
        Execute with smart retry.
        Returns (result, True)  on success
                (None,   False) on all failures
        Raises  BotFatalError   on fatal errors
        """
        last_error = None

        for attempt in range(1, max_attempts + 1):
            try:
                result = func(*args, **kwargs)
                if attempt > 1:
                    log(f"✅ '{action_name}' OK on attempt {attempt}",
                        "SUCCESS")
                return result, True

            except Exception as e:
                last_error = e
                category   = self._classify(e)

                log(
                    f"⚠️ '{action_name}' attempt {attempt}/"
                    f"{max_attempts} [{category}]: {str(e)[:100]}",
                    "WARNING"
                )

                if category == "fatal":
                    log(f"🚨 Fatal: {e}", "ERROR")
                    raise BotFatalError(str(e)) from e

                if category == "rate_limit":
                    wait_m = random.randint(15, 30)
                    log(f"⏳ Rate limited - pausing {wait_m} min",
                        "WARNING")
                    if self.state_manager:
                        self.state_manager.set_rate_limited(wait_m)
                    self._interruptible_sleep(wait_m * 60)
                    continue

                if attempt < max_attempts:
                    base = 30.0 if category == "retryable" else 10.0
                    wait = self.get_backoff_time(attempt, base=base)
                    log(f"🔄 Retry in {wait:.0f}s...", "INFO")
                    self._interruptible_sleep(wait)

        log(
            f"❌ '{action_name}' failed after {max_attempts} "
            f"attempts: {str(last_error)[:100]}",
            "ERROR"
        )
        return None, False


def with_retry(
    max_attempts: int = 3,
    action_name:  str = None,
    state_manager=None
):
    """Decorator: add retry to any function"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            handler = RetryHandler(state_manager)
            name    = action_name or func.__name__
            result, _ = handler.execute(
                func, *args,
                max_attempts=max_attempts,
                action_name=name,
                **kwargs
            )
            return result
        return wrapper
    return decorator
