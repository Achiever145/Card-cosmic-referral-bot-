CARD COSMIC TELEGRAM REFERRAL BOT — CONFIGURED STARTER

Configured:
- Admin Telegram ID: 7605421515
- CardCosmic referral code: ACH145
- Reward per manually approved claim: NGN 300
- Manual screenshot review and manual withdrawal processing

IMPORTANT: ACH145 is a referral code, not a clickable referral URL. The bot will display it to users and ask them to enter it during signup. If CardCosmic provides a full referral URL later, add it as CARD_COSMIC_LINK in Replit Secrets.

SETUP
1. Create a Python Replit project.
2. Upload bot.py and requirements.txt.
3. In Replit Secrets, add:
   BOT_TOKEN = your NEW token from BotFather
   ADMIN_ID = 7605421515
   CARD_COSMIC_CODE = ACH145
   CARD_COSMIC_LINK = (optional; add only if you have the full clickable URL)
4. In the Shell run:
   pip install -r requirements.txt
5. Run:
   python bot.py

SECURITY
- The previously pasted BotFather token should be revoked in @BotFather. Use only the newly generated token in Replit Secrets.
- Never put the bot token in bot.py, README, screenshots, or public chats.
- The bot does not connect to CardCosmic and cannot verify signups automatically.
- Screenshots are only evidence for manual review, not conclusive proof. Review for duplicates and inconsistencies.
- Never request passwords, OTPs, PINs, BVN, card details, or bank login information.
- Test with your own account before sharing the bot publicly.
- SQLite database is local to the Replit project; confirm persistent storage and hosting behavior before relying on it for a live payment programme.
