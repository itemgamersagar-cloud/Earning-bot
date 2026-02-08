import os
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

BOT_TOKEN = "8474661998:AAHWJS1WehX6xtgcvMG4KBkB5XQiKKfV7WU"
ADMIN_ID = 7503462902  # your numeric Telegram ID
FORCE_CHANNELS = ["@earn_easy_crypto_money"]
PAYMENT_CHANNEL = "@payment_earn_easy"

conn = sqlite3.connect("bot.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    ref_by INTEGER,
    balance REAL DEFAULT 0,
    wallet TEXT
)""")
conn.commit()

async def is_subscribed(bot, user_id):
    for ch in FORCE_CHANNELS:
        try:
            member = await bot.get_chat_member(ch, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except:
            return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    ref = int(args[0]) if args and args[0].isdigit() else None

    cur.execute("INSERT OR IGNORE INTO users(user_id, ref_by) VALUES (?,?)", (user.id, ref))
    conn.commit()

    if not await is_subscribed(context.bot, user.id):
        btn = [[InlineKeyboardButton("✅ Joined", callback_data="checksub")]]
        await update.message.reply_text("❌ Join all channels first:", reply_markup=InlineKeyboardMarkup(btn))
        return

    link = f"https://t.me/{context.bot.username}?start={user.id}"
    await update.message.reply_text(
        f"Welcome!\n\n👤 Your ID: {user.id}\n🔗 Ref link:\n{link}\n\n/balance\n/setwallet\n/withdraw"
    )

async def checksub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if await is_subscribed(context.bot, q.from_user.id):
        await q.edit_message_text("✅ Verified! Send /start")
    else:
        await q.answer("❌ Still not joined all channels", show_alert=True)

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cur.execute("SELECT balance FROM users WHERE user_id=?", (update.effective_user.id,))
    bal = cur.fetchone()
    await update.message.reply_text(f"💰 Your balance: {bal[0] if bal else 0}")

async def setwallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Send: /setwallet YOUR_WALLET_ADDRESS")
        return
    wallet = context.args[0]
    cur.execute("UPDATE users SET wallet=? WHERE user_id=?", (wallet, update.effective_user.id))
    conn.commit()
    await update.message.reply_text("✅ Wallet saved!")

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cur.execute("SELECT balance, wallet FROM users WHERE user_id=?", (update.effective_user.id,))
    data = cur.fetchone()
    if not data or data[0] <= 0:
        await update.message.reply_text("❌ No balance")
        return
    if not data[1]:
        await update.message.reply_text("❌ Set wallet first using /setwallet")
        return

    msg = f"🔔 Withdraw Request\nUser: {update.effective_user.id}\nAmount: {data[0]}\nWallet: {data[1]}"
    await context.bot.send_message(chat_id=ADMIN_ID, text=msg)
    await context.bot.send_message(chat_id=PAYMENT_CHANNEL, text=msg)

    cur.execute("UPDATE users SET balance=0 WHERE user_id=?", (update.effective_user.id,))
    conn.commit()
    await update.message.reply_text("✅ Withdraw requested. Wait for admin approval.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]
    await update.message.reply_text(f"📊 Total users: {total}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(checksub, pattern="checksub"))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("setwallet", setwallet))
    app.add_handler(CommandHandler("withdraw", withdraw))
    app.add_handler(CommandHandler("stats", stats))
    app.run_polling()

if __name__ == "__main__":
    main()
