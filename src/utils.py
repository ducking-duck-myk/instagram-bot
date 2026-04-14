import time
import random
import json
import os
from datetime import datetime
from colorama import Fore, Style, init

init(autoreset=True)

# ── Paths ──
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_FILE = os.path.join(DATA_DIR, "bot_log.txt")


def ensure_data_dir():
    """Create data directory if not exists"""
    os.makedirs(DATA_DIR, exist_ok=True)


def log(message: str, level: str = "INFO"):
    """Colored terminal logging + file logging"""
    ensure_data_dir()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    colors = {
        "INFO":    Fore.CYAN,
        "SUCCESS": Fore.GREEN,
        "WARNING": Fore.YELLOW,
        "ERROR":   Fore.RED,
        "ACTION":  Fore.MAGENTA
    }

    color = colors.get(level, Fore.WHITE)
    formatted = f"[{timestamp}] [{level}] {message}"
    print(f"{color}{formatted}{Style.RESET_ALL}")

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception as e:
        print(f"{Fore.RED}[LOG ERROR] {e}{Style.RESET_ALL}")


def random_delay(delay_range):
    """Sleep for a random duration within range"""
    if not isinstance(delay_range, (tuple, list)) or len(delay_range) != 2:
        delay_range = (10, 30)
    delay = random.randint(int(delay_range[0]), int(delay_range[1]))
    log(f"⏳ Waiting {delay}s...", "INFO")
    time.sleep(delay)


def print_banner():
    """Print startup banner"""
    print(f"""
{Fore.CYAN}
╔══════════════════════════════════════╗
║     📸 Instagram Auto Bot v2.0      ║
║   Follow | Like | Unfollow | Smart  ║
╚══════════════════════════════════════╝
{Style.RESET_ALL}""")


def print_stats(stats: dict):
    """Print formatted session stats"""
    followed   = stats.get("followed",   0)
    liked      = stats.get("liked",      0)
    unfollowed = stats.get("unfollowed", 0)
    skipped    = stats.get("skipped",    0)
    errors     = stats.get("errors",     0)

    print(f"""
{Fore.GREEN}
╔══════════════════════════════════════╗
║           📊 Session Stats          ║
╠══════════════════════════════════════╣
║  ✅ Followed:   {str(followed).ljust(20)}║
║  ❤️  Liked:      {str(liked).ljust(20)}║
║  ➖ Unfollowed: {str(unfollowed).ljust(20)}║
║  ⏭️  Skipped:    {str(skipped).ljust(20)}║
║  ❌ Errors:     {str(errors).ljust(20)}║
╚══════════════════════════════════════╝
{Style.RESET_ALL}""")
