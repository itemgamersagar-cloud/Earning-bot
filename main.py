import sqlite3
import time
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# ===== CONFIG =====
BOT_TOKEN = "8474661998:AAHWJS1WehX6xtgcvMG4KBkB5XQiKKfV7WU"
ADMIN_ID = 7503462902
FORCE_CHANNELS = ["@earn_easy_crypto_money"]
PAYMENT_CHANNEL = "@payment_earn_easy"
MIN_WITHDRAW = 1.0
DAILY_WD_LIMIT = 1
REF_BONUS = 0.1
# ==================

# ===== DATABASE =====
db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    ref_by INTEGER,
    balance REAL DEFAULT 0,
    wallet TEXT,
    chain TEXT,
    joined INTEGER DEFAULT 0,
    captcha_ok INTEGER DEFAULT 0,
    created_at INTEGER
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS withdraws(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    wallet TEXT,
    chain TEXT,
    amount REAL,
    status TEXT,
    ts INTEGER
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS referrals(
    referrer INTEGER,
    referred INTEGER
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS wd_daily(
    user_id INTEGER,
    day TEXT,
    cnt INTEGER
)""")

db.commit()

SESS = {}
CAPTCHA = {}

# ===== FUNCTIONS =====
async def is_joined_all(bot, uid):
    for ch in FORCE_CHANNELS:
        try:
            m = await bot.get_chat_member(ch, uid)
            if m.status in ("left", "kicked"): return False
        except: return False
    return True

def ensure_user(uid, ref_by=None):
    cur.execute("SELECT 1 FROM users WHERE user_id=?", (uid,))
    if not cur.fetchone():
        cur.execute("INSERT INTO users(user_id, ref_by, created_at) VALUES(?,?,?)",
                    (uid, ref_by, int(time.time())))
        if ref_by and ref_by != uid:
            cur.execute("INSERT INTO referrals(referrer, referred) VALUES(?,?)", (ref_by, uid))
            cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (REF_BONUS, ref_by))
        db.commit()

def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Balance", callback_data="bal"),
         InlineKeyboardButton("💸 Withdraw", callback_data="wd")],
        [InlineKeyboardButton("🔗 Referral", callback_data="ref"),
         InlineKeyboardButton("📊 Stats", callback_data="stats")]
    ])

# ===== HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ref_by = int(context.args[0]) if context.args and context.args[0].isdigit() else None
    ensure_user(uid, ref_by)

    if not await is_joined_all(context.bot, uid):
        btns = [[InlineKeyboardButton(f"Join Channel", url=f"https://t.me/earn_easy_crypto_money")]]
        btns.append([InlineKeyboardButton("✅ Joined", callback_data="chk")])
        await update.message.reply_text("Join required channel first:", reply_markup=InlineKeyboardMarkup(btns))
        return

    a, b = random.randint(2,9), random.randint(2,9)
    CAPTCHA[uid] = a + b
    await update.message.reply_text(f"🧩 Captcha: {a} + {b} = ?")

async def chk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    if await is_joined_all(context.bot, uid):
        a, b = random.randint(2,9), random.randint(2,9)
        CAPTCHA[uid] = a + b
        await q.message.reply_text(f"🧩 Captcha: {a} + {b} = ?")
    else:
        await q.message.reply_text("❌ Join the channel first.")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    txt = update.message.text.strip()

    if uid in CAPTCHA:
        if txt.isdigit() and int(txt) == CAPTCHA[uid]:
            CAPTCHA.pop(uid, None)
            cur.execute("UPDATE users SET joined=1, captcha_ok=1 WHERE user_id=?", (uid,))
            db.commit()
            await update.message.reply_text("✅ Verified! Menu unlocked:", reply_markup=menu())
        else:
            await update.message.reply_text("❌ Wrong captcha. Try again.")
        return

    step = SESS.get(uid)
    if not step: return

    if step == "chain":
        if txt.upper() not in ("BSC", "ETH", "TON"):
            await update.message.reply_text("Choose chain: BSC / ETH / TON"); return
        cur.execute("UPDATE users SET chain=? WHERE user_id=?", (txt.upper(), uid))
        db.commit()
        SESS[uid] = "wallet"
        await update.message.reply_text("Send wallet address:")

    elif step == "wallet":
        cur.execute("UPDATE users SET wallet=? WHERE user_id=?", (txt, uid))
        db.commit()
        SESS[uid] = "amount"
        await update.message.reply_text("Enter withdraw amount:")

    elif step == "amount":
        try: amt = float(txt)
        except:
            await update.message.reply_text("❌ Number only"); return

        cur.execute("SELECT balance, wallet, chain FROM users WHERE user_id=?", (uid,))
        bal, wallet, chain = cur.fetchone()
        if amt < MIN_WITHDRAW or amt > bal:
            await update.message.reply_text("❌ Invalid/insufficient balance"); return

        day = time.strftime("%Y-%m-%d")
        cur.execute("SELECT cnt FROM wd_daily WHERE user_id=? AND day=?", (uid, day))
        row = cur.fetchone()
        if row and row[0] >= DAILY_WD_LIMIT:
            await update.message.reply_text("❌ Daily withdraw limit reached"); return

        cur.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (amt, uid))
        cur.execute("INSERT INTO withdraws(user_id, wallet, chain, amount, status, ts) VALUES(?,?,?,?,?,?)",
                    (uid, wallet, chain, amt, "pending", int(time.time())))
        if row:
            cur.execute("UPDATE wd_daily SET cnt=cnt+1 WHERE user_id=? AND day=?", (uid, day))
        else:
            cur.execute("INSERT INTO wd_daily(user_id, day, cnt) VALUES(?,?,1)", (uid, day))
        db.commit()
        SESS.pop(uid, None)

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve", callback_data=f"ap:{uid}:{amt}:{wallet}:{chain}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"rj:{uid}:{amt}")
        ]])
        await context.bot.send_message(ADMIN_ID, f"💸 Withdraw Request\nUser: {uid}\nChain: {chain}\nWallet: {wallet}\nAmount: {amt}", reply_markup=kb)
        await update.message.reply_text("✅ Request submitted. Wait for admin approval.")

async def bal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    cur.execute("SELECT balance, wallet, chain FROM users WHERE user_id=?", (uid,))
    b, w, c = cur.fetchone()
    await q.message.reply_text(f"💰 Balance: {b:.4f}\n🏦 Wallet: {w or 'Not set'}\n🔗 Chain: {c or '-'}")

async def wd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    SESS[uid] = "chain"
    await q.message.reply_text("Select chain: BSC / ETH / TON")

async def ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    link = f"https://t.me/{context.bot.username}?start={uid}"
    cur.execute("SELECT COUNT(*) FROM referrals WHERE referrer=?", (uid,))
    cnt = cur.fetchone()[0]
    await q.message.reply_text(f"🔗 Your link:\n{link}\n👥 Referrals: {cnt}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    cur.execute("SELECT COUNT(*) FROM users"); users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM withdraws WHERE status='pending'"); pend = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM withdraws WHERE status='paid'"); paid = cur.fetchone()[0]
    await q.message.reply_text(f"📊 Stats\n👤 Users: {users}\n⏳ Pending: {pend}\n✅ Paid: {paid}")

async def admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    data = q.data

    if data.startswith("ap:"):
        _, uid, amt, wallet, chain = data.split(":")
        cur.execute("UPDATE withdraws SET status='paid' WHERE user_id=? AND amount=? AND wallet=? AND chain=? AND status='pending'",
                    (int(uid), float(amt), wallet, chain))
        db.commit()
        await context.bot.send_message(int(uid), f"✅ Paid {amt} on {chain} to {wallet}")
        await context.bot.send_message(PAYMENT_CHANNEL, f"💸 Payment Proof\nUser: {uid}\nChain: {chain}\nAmount: {amt}\nWallet: {wallet}")
        await q.message.edit_text("Approved & posted to payment channel.")

    if data.startswith("rj:"):
        _, uid, amt = data.split(":")
        cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (float(amt), int(uid)))
        cur.execute("UPDATE withdraws SET status='rejected' WHERE user_id=? AND amount=? AND status='pending'",
                    (int(uid), float(amt)))
        db.commit()
        await context.bot.send_message(int(uid), "❌ Withdraw rejected. Balance refunded.")
        await q.message.edit_text("Rejected & refunded.")

# ===== MAIN =====
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(chk, pattern="chk"))
    app.add_handler(CallbackQueryHandler(bal, pattern="bal"))
    app.add_handler(CallbackQueryHandler(wd, pattern="wd"))
    app.add_handler(CallbackQueryHandler(ref, pattern="ref"))
    app.add_handler(CallbackQueryHandler(stats, pattern="stats"))
    app.add_handler(CallbackQueryHandler(admin_cb, pattern="^(ap:|rj:)"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
