import schedule
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import CONFIG
from src.bot import InstagramBot
from src.utils import log, print_banner, print_stats
from src.validator import Validator
from src.retry_handler import BotFatalError

HELP_TEXT = (
    "Usage: python main.py [option]\n"
    "  --full      Run follow + like + unfollow\n"
    "  --follow    Follow session only\n"
    "  --like      Like session only\n"
    "  --unfollow  Unfollow session only\n"
    "  --schedule  Run on auto-schedule\n"
    "  --stats     Print today's stats\n"
)


def run_bot():
    print_banner()

    # Startup checks
    if not Validator.run_startup_checks(CONFIG):
        log("❌ Startup checks failed - fix errors above", "ERROR")
        sys.exit(1)

    # Login
    bot = InstagramBot(CONFIG)
    if not bot.login():
        log("❌ Login failed", "ERROR")
        sys.exit(1)

    arg = sys.argv[1] if len(sys.argv) > 1 else "--full"

    try:
        if arg == "--follow":
            log("▶️ Follow session only", "INFO")
            bot.run_follow_session()
            if bot.actions:
                print_stats(bot.actions.get_stats())

        elif arg == "--like":
            log("▶️ Like session only", "INFO")
            bot.run_like_session()
            if bot.actions:
                print_stats(bot.actions.get_stats())

        elif arg == "--unfollow":
            log("▶️ Unfollow session only", "INFO")
            bot.run_unfollow_session()
            if bot.actions:
                print_stats(bot.actions.get_stats())

        elif arg == "--full":
            log("▶️ Full session", "INFO")
            stats = bot.run_full_session()
            print_stats(stats)

        elif arg == "--schedule":
            run_scheduled(bot)

        elif arg == "--stats":
            if bot.state:
                bot.state.print_daily_summary()
            else:
                log("❌ State not available", "ERROR")

        else:
            log(f"❌ Unknown argument: '{arg}'", "ERROR")
            print(HELP_TEXT)
            sys.exit(1)

    except BotFatalError as e:
        log(f"🚨 Fatal error: {e}", "ERROR")
        sys.exit(1)
    except KeyboardInterrupt:
        log("🛑 Stopped by user", "WARNING")
        sys.exit(0)


def run_scheduled(bot: InstagramBot):
    """Run on timed schedule"""
    log("📅 Scheduled mode", "INFO")
    sc = CONFIG["schedule"]

    schedule.every().day.at(sc["morning"]).do(
        run_with_stats, bot, "Morning"
    )
    schedule.every().day.at(sc["afternoon"]).do(
        run_with_stats, bot, "Afternoon"
    )
    schedule.every().day.at(sc["evening"]).do(
        run_with_stats, bot, "Evening"
    )

    log(
        f"⏰ Scheduled: {sc['morning']} | "
        f"{sc['afternoon']} | {sc['evening']}",
        "INFO"
    )
    log("✅ Running... CTRL+C to stop", "SUCCESS")

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        log("🛑 Stopped by user", "WARNING")
        sys.exit(0)


def run_with_stats(bot: InstagramBot, session_name: str):
    """Called by scheduler - plain function, not lambda"""
    log(f"🕐 {session_name} session starting", "ACTION")
    try:
        stats = bot.run_full_session()
        print_stats(stats)
    except BotFatalError as e:
        log(f"🚨 Fatal: {e}", "ERROR")
    except Exception as e:
        log(f"❌ Session error: {str(e)[:80]}", "ERROR")


if __name__ == "__main__":
    run_bot()
