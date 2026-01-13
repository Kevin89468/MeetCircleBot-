MeetCircleBot - improved main entrypoint.

Key changes:
- Read TELEGRAM_TOKEN from env (no hardcoded token).
- Use context.user_data for per-user state.
- Simple JSON persistence (data.json).
- Input validation, logging, error handler.
"""
import os
import json
import logging
import asyncio
import threading
from typing import Dict, List, Any

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Constants
DATA_FILE = os.environ.get("MEETCIRCLE_DATA_FILE", "data.json")
TOKEN = os.environ.get("TELEGRAM_TOKEN")
MAX_POST_LENGTH = 1000
MIN_AGE = 18
MAX_AGE = 99

# In-memory data (backed by DATA_FILE)
_data_lock = threading.Lock()
_users: Dict[int, Dict[str, Any]] = {}
_posts: List[Dict[str, Any]] = []

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger("meetcircle")


def load_data() -> None:
    """Load users and posts from DATA_FILE if present."""
    global _users, _posts
    try:
        if os.path.isfile(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                payload = json.load(f)
            _users = {int(k): v for k, v in payload.get("users", {}).items()}
            _posts = payload.get("posts", [])
            logger.info("Loaded data: %d users, %d posts", len(_users), len(_posts))
        else:
            _users = {}
            _posts = []
            logger.info("No data file found, starting fresh.")
    except Exception:
        logger.exception("Failed to load data file; starting with empty store.")
        _users = {}
        _posts = []


def save_data_sync() -> None:
    """Synchronous save to disk (protected by lock)."""
    with _data_lock:
        payload = {"users": {str(k): v for k, v in _users.items()}, "posts": _posts}
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)


async def save_data() -> None:
    """Async wrapper to avoid blocking the event loop."""
    await asyncio.to_thread(save_data_sync)


# --- Command handlers ---


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message."""
    if update.message is None:
        return
    await update.message.reply_text(
        "Welcome to MeetCircle! 🌟\n"
        "A social and dating platform where posts turn into conversations.\n"
        "Use /help to see available commands."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text(
        "/start - Welcome message\n"
        "/profile - Create or view your profile\n"
        "/post - Share a post\n"
        "/feed - See recent posts\n"
        "/help - Show commands"
    )


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create or show profile. If creating, prompt for age next."""
    if update.message is None or update.effective_user is None:
        return
    user_id = update.effective_user.id

    if user_id not in _users:
        # Create new profile and ask for age
        _users[user_id] = {
            "name": update.effective_user.first_name or "Unknown",
            "age": None,
            "intent": None,
        }
        # mark that we expect age next from this user
        context.user_data["expect"] = "age"
        await update.message.reply_text("Let's set up your profile. What's your age?")
        await save_data()
        return

    # Show existing profile
    profile_data = _users[user_id]
    age = profile_data["age"] if profile_data["age"] is not None else "Not set"
    intent = profile_data["intent"] or "Not set"
    await update.message.reply_text(f"Your profile:\nName: {profile_data['name']}\nAge: {age}\nLooking for: {intent}")


async def post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Enter posting mode for the user."""
    if update.message is None or update.effective_user is None:
        return
    user_id = update.effective_user.id
    user = _users.get(user_id)
    if not user or user.get("age") is None:
        await update.message.reply_text("Please complete your profile first using /profile.")
        return

    context.user_data["mode"] = "posting"
    await update.message.reply_text("Send your post text now (max 1000 chars):")


async def feed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the last 10 posts (newest first)."""
    if update.message is None:
        return
    if not _posts:
        await update.message.reply_text("No posts yet. Be the first to post with /post!")
        return

    messages = []
    for p in reversed(_posts[-10:]):  # newest first
        user_profile = _users.get(p["user_id"], {"name": "Unknown"})
        messages.append(f"{user_profile.get('name','Unknown')}: {p['text']}")
    await update.message.reply_text("\n\n".join(messages))


# --- Message handler for profile setup and posting ---


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle plain text messages for profile creation and posts."""
    if update.message is None or update.effective_user is None:
        return
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # Profile age expected
    if context.user_data.get("expect") == "age":
        if text.isdigit() and MIN_AGE <= int(text) <= MAX_AGE:
            _users.setdefault(user_id, {})["age"] = int(text)
            context.user_data["expect"] = "intent"
            # Ask for intent using a keyboard
            keyboard = [["Friends"], ["Dating"], ["Both"]]
            reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
            await update.message.reply_text("What are you looking for?", reply_markup=reply_markup)
            await save_data()
        else:
            await update.message.reply_text(f"Please enter a valid age ({MIN_AGE}-{MAX_AGE}).")
        return

    # Profile intent expected
    if context.user_data.get("expect") == "intent":
        if text in ["Friends", "Dating", "Both"]:
            _users.setdefault(user_id, {})["intent"] = text
            context.user_data.pop("expect", None)
            # remove keyboard
            await update.message.reply_text("Profile setup complete! 🎉 You can now post and view feeds.", reply_markup=ReplyKeyboardRemove())
            await save_data()
        else:
            await update.message.reply_text("Choose one option: Friends / Dating / Both.")
        return

    # Posting mode
    if context.user_data.get("mode") == "posting":
        if not text:
            await update.message.reply_text("Cannot post empty text. Send a message or cancel.")
            return
        if len(text) > MAX_POST_LENGTH:
            await update.message.reply_text(f"Post too long (max {MAX_POST_LENGTH} characters).")
            return
        _posts.append({"user_id": user_id, "text": text})
        context.user_data.pop("mode", None)
        await update.message.reply_text("Your post has been shared! ✅")
        await save_data()
        return

    # Otherwise: no-op or small help
    await update.message.reply_text("I didn't understand that. Use /help to see commands.")


# --- Error handler ---


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors raised during update handling."""
    logger.exception("Exception while handling update: %s", update)


# --- Main setup ---


def main() -> None:
    if not TOKEN:
        logger.error("TELEGRAM_TOKEN environment variable is not set. Exiting.")
        raise SystemExit("Set TELEGRAM_TOKEN before running the bot.")

    load_data()

    app = ApplicationBuilder().token(TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("post", post))
    app.add_handler(CommandHandler("feed", feed))

    # Text messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    # Error handler
    app.add_error_handler(error_handler)

    logger.info("Bot is starting... (polling)")
    app.run_polling()


if __name__ == "__main__":
    main()
