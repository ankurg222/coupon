import os
import json
import requests
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Env vars from Railway
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHAT_ID = int(os.getenv('CHAT_ID'))
assert BOT_TOKEN and CHAT_ID, "Set BOT_TOKEN and CHAT_ID env vars"

# Voucher config from checknew.py
VOUCHER_VALUES = {"SVH": 4000, "SVD": 1000, "SVC": 2000, "SVA": 500}
STATUS_APPLIED, STATUS_REDEEMED, STATUS_USED = "✅WORKING", "⚠️REDEEMED", "❌USED"
STATUS_NOT_ELIGIBLE, STATUS_INVALID, STATUS_UNKNOWN = "🚧NOT_ELIGIBLE", "👀INVALID", "❌ERROR"

cookies = None  # Global session cookies

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_headers(cookie_str):
    return {
        "accept": "application/json", "content-type": "application/json",
        "origin": "https://www.sheinindia.in", "referer": "https://www.sheinindia.in/cart",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "x-tenant-id": "SHEIN", "cookie": cookie_str
    }

def classify_response(data):
    if not data or "errorMessage" not in data: 
        return STATUS_APPLIED, data.get("voucherInfo", {}).get("savedAmount", 0)
    msg = data["errorMessage"].get("errors", [{}])[0].get("message", "").lower()
    if "redeemed" in msg: return STATUS_REDEEMED, 0
    if "applicable" in msg or "used" in msg: return STATUS_USED, 0
    if "eligible" in msg: return STATUS_NOT_ELIGIBLE, 0
    if "invalid" in msg: return STATUS_INVALID, 0
    return STATUS_UNKNOWN, 0

def get_value(code): 
    return VOUCHER_VALUES.get(code[:3].upper(), 0)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    global cookies
    if not cookies:
        await update.message.reply_text("🔑 Send your SHEIN cookies (copy from browser F12 > Application > Cookies):")
        return
    await update.message.reply_text("✅ Cookies loaded! Send vouchers (one per line).")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global cookies
    if update.effective_chat.id != CHAT_ID: return
    
    text = update.message.text.strip()
    if not cookies:  # First message = cookies
        cookies = text
        await update.message.reply_text("✅ Cookies set! Now send vouchers.")
        return
    
    # Parse vouchers
    vouchers = [line.strip() for line in text.split('
') if line.strip()]
    if not vouchers:
        await update.message.reply_text("❌ No codes found.")
        return
    
    headers = get_headers(cookies)
    await update.message.reply_text(f"⚡ Checking {len(vouchers)}...")
    
    valid, results, total = [], [], 0
    for code in vouchers:
        data = requests.post(
            "https://www.sheinindia.in/api/cart/apply-voucher",
            json={"voucherId": code, "device": {"client_type": "web"}},
            headers=headers, timeout=10
        ).json()
        status, value = classify_response(data)
        value = get_value(code) or value
        results.append(f"{status} {code} (₹{value})")
        if status == STATUS_APPLIED and value > 0:
            valid.append(code)
            total += value
        
        # Reset
        requests.post("https://www.sheinindia.in/api/cart/reset-voucher", 
                     json={"voucherId": code, "device": {"client_type": "web"}}, 
                     headers=headers)
    
    copy_text = '
'.join(valid)
    msg = f"✅ {len(valid)} VALID | ₹{total:,}

" + '
'.join(results[:15])
    if valid:
        msg += f"

📋 Copy:
```{copy_text}```"
    else:
        msg += "
😔 No working vouchers."
    
    await update.message.reply_text(msg, parse_mode='Markdown')

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("🤖 Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()