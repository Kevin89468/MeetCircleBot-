from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# --- In-memory storage (later can be database) ---
users = {}  # key: user_id, value: profile dict
posts = []  # list of dict: {'user_id', 'text'}

# --- Start Command ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to MeetCircle! 🌟\n"
        "A social and dating platform where posts turn into conversations.\n"
        "Use /help to see available commands."
    )

# --- Help Command ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start - Welcome message\n"
        "/profile - Create or view your profile\n"
        "/post - Share a post\n"
        "/feed - See all posts\n"
        "/help - Show commands"
    )

# --- Profile Command ---
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in users:
        # Create new profile
        users[user_id] = {
            "name": update.effective_user.first_name,
            "age": None,
            "intent": None
        }
        await update.message.reply_text("Let's set up your profile. What's your age?")
        return  # next message will handle age input

    # Show existing profile
    profile = users[user_id]
    await update.message.reply_text(
        f"Your profile:\n"
        f"Name: {profile['name']}\n"
        f"Age: {profile['age']}\n"
        f"Looking for: {profile['intent']}"
    )

# --- Capture Age and Intent ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # If profile exists but age not set
    if user_id in users and users[user_id]['age'] is None:
        if text.isdigit() and 18 <= int(text) <= 99:
            users[user_id]['age'] = int(text)
            # Ask for intent
            keyboard = [["Friends"], ["Dating"], ["Both"]]
            reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
            await update.message.reply_text("What are you looking for?", reply_markup=reply_markup)
        else:
            await update.message.reply_text("Please enter a valid age (18-99).")
        return

    # If profile exists but intent not set
    if user_id in users and users[user_id]['intent'] is None:
        if text in ["Friends", "Dating", "Both"]:
            users[user_id]['intent'] = text
            await update.message.reply_text("Profile setup complete! 🎉 You can now post and view feeds.")
        else:
            await update.message.reply_text("Choose one option: Friends / Dating / Both.")
        return

    # If post creation mode
    if user_id in context.chat_data and context.chat_data[user_id] == "posting":
        posts.append({"user_id": user_id, "text": text})
        context.chat_data[user_id] = None
        await update.message.reply_text("Your post has been shared! ✅")
        return

# --- Post Command ---
async def post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users or users[user_id]['age'] is None:
        await update.message.reply_text("Please complete your profile first using /profile.")
        return

    context.chat_data[user_id] = "posting"
    await update.message.reply_text("Send your post text now:")

# --- Feed Command ---
async def feed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not posts:
        await update.message.reply_text("No posts yet. Be the first to post with /post!")
        return

    messages = []
    for p in posts[-10:]:  # show last 10 posts
        user_profile = users.get(p['user_id'], {"name": "Unknown"})
        messages.append(f"{user_profile['name']}: {p['text']}")
    await update.message.reply_text("\n\n".join(messages))

# --- Main Bot Setup ---
app = ApplicationBuilder().token("8358674170:AAFL_7Nu3QF7K9-vVLpFkvgT5rssNcSCeKc").build()

# Commands
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("profile", profile))
app.add_handler(CommandHandler("post", post))
app.add_handler(CommandHandler("feed", feed))

# Handle text messages for profile setup and posts
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

print("Bot is running...")
app.run_polling()
