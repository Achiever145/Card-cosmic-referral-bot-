import os
import sqlite3
import logging
from datetime import datetime, timezone

from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

# Configure these in Replit Secrets (do not paste your bot token into this file).
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "7605421515") or "7605421515")
CARD_COSMIC_LINK = os.getenv("CARD_COSMIC_LINK", "").strip()
CARD_COSMIC_CODE = os.getenv("CARD_COSMIC_CODE", "ACH145").strip()
REWARD_NAIRA = 300
DB_PATH = "referral_bot.db"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

PHOTO_ONE, PHOTO_TWO, BANK_DETAILS = range(3)

MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🔗 Get referral link"), KeyboardButton("📤 Submit proof")],
        [KeyboardButton("💰 My balance"), KeyboardButton("📊 My referrals")],
        [KeyboardButton("🏦 Withdraw"), KeyboardButton("❓ Help")],
    ],
    resize_keyboard=True
)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                joined_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                referral_screenshot TEXT NOT NULL,
                dashboard_screenshot TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                reviewed_at TEXT,
                reviewed_by INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                bank_details TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT
            )
        """)
        conn.commit()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def register_user(user):
    with db() as conn:
        conn.execute("""
            INSERT INTO users (user_id, username, first_name, joined_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name
        """, (user.id, user.username or "", user.first_name or "", now()))
        conn.commit()


def balance_for(user_id):
    with db() as conn:
        earned = conn.execute(
            "SELECT COUNT(*) AS n FROM claims WHERE user_id=? AND status='approved'",
            (user_id,)
        ).fetchone()["n"] * REWARD_NAIRA
        reserved_or_paid = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS n FROM withdrawals "
            "WHERE user_id=? AND status IN ('pending', 'paid')",
            (user_id,)
        ).fetchone()["n"]
        return max(0, earned - reserved_or_paid)


def claim_counts(user_id):
    with db() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM claims WHERE user_id=? GROUP BY status",
            (user_id,)
        ).fetchall()
    return {row["status"]: row["n"] for row in rows}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user)
    await update.message.reply_text(
        "Welcome to CardCosmic Referral Rewards! 🎉\n\n"
        "Earn ₦300 from this programme for each signup you submit that is "
        "reviewed and approved by the admin.\n\n"
        "How it works:\n"
        "1. Get the referral link below.\n"
        "2. Register using that link.\n"
        "3. Return here and submit two screenshots:\n"
        "   • evidence showing the referral code/link was used\n"
        "   • your account dashboard after signup\n"
        "4. Wait for manual review. Approved claims add ₦300 to your balance.\n\n"
        "The ₦300 is paid manually by the bot owner. Any separate CardCosmic "
        "reward is subject to CardCosmic's own terms and eligibility.",
        reply_markup=MENU
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Your Telegram numeric ID is:\n{update.effective_user.id}")


async def referral_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not CARD_COSMIC_LINK:
        await update.message.reply_text(
            "The referral link has not been configured yet. Please contact the admin."
        )
        return
    await update.message.reply_text(
        "Here is the CardCosmic referral link:\n"
        f"{CARD_COSMIC_LINK}\n\n"
        "Open it and complete signup. Then come back and tap “📤 Submit proof”. "
        "Only submit your own genuine signup. Do not share passwords or OTPs."
    )


async def begin_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("proof_one", None)
    await update.message.reply_text(
        "Please upload screenshot 1 of 2: evidence that you used the referral link/code.\n\n"
        "Make sure the relevant referral information is visible. Hide passwords, OTPs, "
        "full card details and other sensitive information."
    )
    return PHOTO_ONE


async def receive_photo_one(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Please send a screenshot as a photo, or type /cancel.")
        return PHOTO_ONE
    context.user_data["proof_one"] = update.message.photo[-1].file_id
    await update.message.reply_text(
        "Screenshot 1 received. Now upload screenshot 2 of 2: your CardCosmic account dashboard after signup."
    )
    return PHOTO_TWO


async def receive_photo_two(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Please send the dashboard screenshot as a photo, or type /cancel.")
        return PHOTO_TWO

    user_id = update.effective_user.id
    proof_one = context.user_data.get("proof_one")
    proof_two = update.message.photo[-1].file_id

    if proof_one == proof_two:
        await update.message.reply_text("These look like the same screenshot. Please start again with two different screenshots.")
        context.user_data.pop("proof_one", None)
        return ConversationHandler.END

    with db() as conn:
        duplicate = conn.execute(
            "SELECT id FROM claims WHERE referral_screenshot=? OR dashboard_screenshot=?",
            (proof_one, proof_two)
        ).fetchone()
        if duplicate:
            await update.message.reply_text(
                "One of these screenshots has already been submitted. If this is a mistake, contact the admin.",
                reply_markup=MENU
            )
            context.user_data.pop("proof_one", None)
            return ConversationHandler.END

        cur = conn.execute(
            "INSERT INTO claims (user_id, referral_screenshot, dashboard_screenshot, status, created_at) "
            "VALUES (?, ?, ?, 'pending', ?)",
            (user_id, proof_one, proof_two, now())
        )
        claim_id = cur.lastrowid
        conn.commit()

    context.user_data.pop("proof_one", None)
    await update.message.reply_text(
        f"Your submission #{claim_id} has been received and is pending manual review. "
        "Submitting screenshots does not guarantee approval. You will receive a message when it is reviewed.",
        reply_markup=MENU
    )

    if ADMIN_ID:
        user = update.effective_user
        who = f"{user.full_name} (@{user.username})" if user.username else user.full_name
        await context.bot.send_message(
            ADMIN_ID,
            f"🆕 New referral claim #{claim_id}\n"
            f"User: {who}\nTelegram ID: {user_id}\n"
            f"Review both screenshots below."
        )
        await context.bot.send_photo(ADMIN_ID, proof_one, caption=f"Claim #{claim_id} — referral evidence")
        await context.bot.send_photo(ADMIN_ID, proof_two, caption=f"Claim #{claim_id} — account dashboard")
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve ₦300", callback_data=f"claim:approve:{claim_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"claim:reject:{claim_id}")
        ]])
        await context.bot.send_message(ADMIN_ID, f"Review claim #{claim_id}:", reply_markup=keyboard)

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("proof_one", None)
    await update.message.reply_text("Cancelled. You can start again from the menu.", reply_markup=MENU)
    return ConversationHandler.END


async def my_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = balance_for(update.effective_user.id)
    counts = claim_counts(update.effective_user.id)
    await update.message.reply_text(
        f"💰 Available balance: ₦{amount:,}\n\n"
        f"Pending claims: {counts.get('pending', 0)}\n"
        f"Approved claims: {counts.get('approved', 0)}\n"
        f"Rejected claims: {counts.get('rejected', 0)}",
        reply_markup=MENU
    )


async def my_referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    counts = claim_counts(update.effective_user.id)
    await update.message.reply_text(
        "📊 Your submissions\n"
        f"Pending: {counts.get('pending', 0)}\n"
        f"Approved: {counts.get('approved', 0)}\n"
        f"Rejected: {counts.get('rejected', 0)}",
        reply_markup=MENU
    )


async def review_claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("You are not authorized to review claims.")
        return

    _, action, claim_id_text = query.data.split(":")
    claim_id = int(claim_id_text)
    new_status = "approved" if action == "approve" else "rejected"

    with db() as conn:
        claim = conn.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
        if not claim:
            await query.edit_message_text("Claim not found.")
            return
        if claim["status"] != "pending":
            await query.edit_message_text(f"Claim #{claim_id} was already reviewed ({claim['status']}).")
            return
        conn.execute(
            "UPDATE claims SET status=?, reviewed_at=?, reviewed_by=? WHERE id=?",
            (new_status, now(), ADMIN_ID, claim_id)
        )
        conn.commit()

    if new_status == "approved":
        await context.bot.send_message(
            claim["user_id"],
            f"✅ Your claim #{claim_id} has been approved. ₦300 has been added to your bot balance."
        )
        await query.edit_message_text(f"Claim #{claim_id} approved. ₦300 credited.")
    else:
        await context.bot.send_message(
            claim["user_id"],
            f"❌ Your claim #{claim_id} was not approved. Please contact the admin if you believe this is an error."
        )
        await query.edit_message_text(f"Claim #{claim_id} rejected.")


async def begin_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = balance_for(update.effective_user.id)
    if amount < REWARD_NAIRA:
        await update.message.reply_text(
            f"Your available balance is ₦{amount:,}. You need at least ₦300 to request a withdrawal.",
            reply_markup=MENU
        )
        return ConversationHandler.END

    context.user_data["withdraw_amount"] = amount
    await update.message.reply_text(
        f"Your available balance is ₦{amount:,}.\n\n"
        "Send your bank details in ONE message using this format:\n"
        "Bank name | Account name | Account number\n\n"
        "Never send your PIN, password, OTP or card details. Type /cancel to stop."
    )
    return BANK_DETAILS


async def receive_bank_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    details = (update.message.text or "").strip()
    parts = [part.strip() for part in details.split("|")]
    if len(parts) != 3 or any(not part for part in parts) or len(parts[2]) < 8:
        await update.message.reply_text(
            "Please use this format:\nBank name | Account name | Account number\nOr type /cancel."
        )
        return BANK_DETAILS

    user_id = update.effective_user.id
    amount = balance_for(user_id)
    if amount < REWARD_NAIRA:
        await update.message.reply_text("Your available balance is no longer enough for withdrawal.", reply_markup=MENU)
        return ConversationHandler.END

    with db() as conn:
        pending = conn.execute(
            "SELECT id FROM withdrawals WHERE user_id=? AND status='pending'",
            (user_id,)
        ).fetchone()
        if pending:
            await update.message.reply_text("You already have a pending withdrawal request.", reply_markup=MENU)
            return ConversationHandler.END
        cur = conn.execute(
            "INSERT INTO withdrawals (user_id, amount, bank_details, status, created_at) "
            "VALUES (?, ?, ?, 'pending', ?)",
            (user_id, amount, details, now())
        )
        withdrawal_id = cur.lastrowid
        conn.commit()

    await update.message.reply_text(
        f"🏦 Withdrawal request #{withdrawal_id} for ₦{amount:,} submitted. "
        "The admin will process it manually.",
        reply_markup=MENU
    )
    if ADMIN_ID:
        user = update.effective_user
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Mark as paid", callback_data=f"withdraw:paid:{withdrawal_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"withdraw:reject:{withdrawal_id}")
        ]])
        await context.bot.send_message(
            ADMIN_ID,
            f"🏦 Withdrawal request #{withdrawal_id}\n"
            f"User: {user.full_name}\nTelegram ID: {user_id}\n"
            f"Amount: ₦{amount:,}\nBank details: {details}",
            reply_markup=keyboard
        )
    return ConversationHandler.END


async def review_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("You are not authorized to process withdrawals.")
        return

    _, action, wid_text = query.data.split(":")
    wid = int(wid_text)
    status = "paid" if action == "paid" else "rejected"
    with db() as conn:
        row = conn.execute("SELECT * FROM withdrawals WHERE id=?", (wid,)).fetchone()
        if not row:
            await query.edit_message_text("Withdrawal request not found.")
            return
        if row["status"] != "pending":
            await query.edit_message_text(f"Withdrawal #{wid} is already {row['status']}.")
            return
        conn.execute(
            "UPDATE withdrawals SET status=?, updated_at=? WHERE id=?",
            (status, now(), wid)
        )
        conn.commit()

    if status == "paid":
        await context.bot.send_message(row["user_id"], f"✅ Withdrawal #{wid} marked as paid. Amount: ₦{row['amount']:,}.")
        await query.edit_message_text(f"Withdrawal #{wid} marked as paid.")
    else:
        await context.bot.send_message(row["user_id"], f"Your withdrawal #{wid} was rejected. Your balance is available again.")
        await query.edit_message_text(f"Withdrawal #{wid} rejected. Reserved balance released.")


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    with db() as conn:
        users = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        pending_claims = conn.execute("SELECT COUNT(*) AS n FROM claims WHERE status='pending'").fetchone()["n"]
        pending_withdrawals = conn.execute("SELECT COUNT(*) AS n FROM withdrawals WHERE status='pending'").fetchone()["n"]
    await update.message.reply_text(
        f"🛠 Admin dashboard\nUsers: {users}\nPending claims: {pending_claims}\n"
        f"Pending withdrawals: {pending_withdrawals}"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "How to earn:\n"
        "1. Tap Get referral link.\n"
        "2. Register using the link.\n"
        "3. Tap Submit proof and send two screenshots.\n"
        "4. Wait for manual review.\n"
        "5. Each approved claim adds ₦300 to your balance.\n"
        "6. Request a withdrawal when you have an available balance.\n\n"
        "Screenshots are manually reviewed and do not guarantee approval. "
        "Never send passwords, OTPs, PINs or card details.",
        reply_markup=MENU
    )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("Missing BOT_TOKEN. Add it to Replit Secrets.")
    if not ADMIN_ID:
        raise RuntimeError("Missing ADMIN_ID. Add your numeric Telegram ID to Replit Secrets.")
    if not CARD_COSMIC_LINK:
        logger.info("No clickable referral URL configured; bot will display referral code ACH145.")

    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    proof_conversation = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^📤 Submit proof$"), begin_proof)],
        states={
            PHOTO_ONE: [MessageHandler(filters.PHOTO, receive_photo_one)],
            PHOTO_TWO: [MessageHandler(filters.PHOTO, receive_photo_two)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    withdrawal_conversation = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^🏦 Withdraw$"), begin_withdrawal)],
        states={
            BANK_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_bank_details)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(proof_conversation)
    app.add_handler(withdrawal_conversation)
    app.add_handler(CallbackQueryHandler(review_claim, pattern=r"^claim:"))
    app.add_handler(CallbackQueryHandler(review_withdrawal, pattern=r"^withdraw:"))
    app.add_handler(MessageHandler(filters.Regex(r"^🔗 Get referral link$"), referral_link))
    app.add_handler(MessageHandler(filters.Regex(r"^💰 My balance$"), my_balance))
    app.add_handler(MessageHandler(filters.Regex(r"^📊 My referrals$"), my_referrals))
    app.add_handler(MessageHandler(filters.Regex(r"^❓ Help$"), help_command))

    logger.info("Bot is running.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
