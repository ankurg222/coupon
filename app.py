import os
import requests
import logging
import json
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv('BOT_TOKEN')
CHAT_ID = int(os.getenv('CHAT_ID'))
assert BOT_TOKEN and CHAT_ID, "Set BOT_TOKEN & CHAT_ID"

VOUCHER_VALUES = {"SVH": 4000, "SVD": 1000, "SVC": 2000, "SVA": 500}
STATUS_APPLIED, STATUS_REDEEMED, STATUS_USED = "✅WORKING", "⚠️REDEEMED", "❌USED"
STATUS_NOT_ELIGIBLE, STATUS_INVALID, STATUS_UNKNOWN = "🚧NOT_ELIGIBLE", "👀INVALID", "❌ERROR"

cookies = None

logging.basicConfig(level=logging.INFO)

def format_cookies(raw_cookies):
    """Clean & format cookie string"""
    raw = raw_cookies.strip()
    # Remove newlines, extra spaces
    raw = re.sub(r'[s]+', ' ', raw)
    return raw

def get_headers(cookie_str):
    return {
        "accept": "application/json", "content-type": "application/json",
        "origin": "https://www.sheinindia.in", "referer": "https://www.sheinindia.in/cart",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "x-tenant-id": "SHEIN", "cookie": cookie_str
    }

def safe_json_parse(response):
    try:
        return response.json()
    except:
        return {}

def classify_response(data):
    if not data or "errorMessage" not in data: 
        return STATUS_APPLIED, data.get("voucherInfo", {}).get("savedAmount", 0)
    msg = data["errorMessage"].get("errors", [{}])[0].get("message", "").lower()
    if "redeemed" in msg: return STATUS_REDEEMED, 0
    if any(x in msg for x in ["applicable", "used", "checkout"]): return STATUS_USED, 0
    if "eligible" in msg: return STATUS_NOT_ELIGIBLE, 0
    if "invalid" in msg: return STATUS_INVALID, 0
    return STATUS_UNKNOWN, 0

def get_value(code): 
    return VOUCHER_VALUES.get(code[:3].upper(), 0)

async def test_cookies(cookie_str):
    """Quick cookie validity test"""
    headers = get_headers(cookie_str)
    try:
        r = requests.get("https://www.sheinindia.in/api/user/info", headers=headers, timeout=10)
        data = safe_json_parse(r)
        if r.status_code == 200 and data.get("success"):
            return True, "✅ Valid (logged in)"
        return False, "❌ Invalid/Stale - refresh cookies"
    except:
        return False, "❌ Network error"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    global cookies
    if not cookies:
        await update.message.reply_text(
            "🔑 **Get SHEIN Cookies**:"
            "1. sheinindia.in → F12 → Application tab"
            "2. Storage → Cookies → https://www.sheinindia.in"
            "3. Ctrl+A → Copy ALL cookies"
            "Paste here 👇",
            parse_mode='Markdown'
        )
        return
    await update.message.reply_text("✅ Ready! Send vouchers (one per line).")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global cookies
    if update.effective_chat.id != CHAT_ID: return
    
    text = update.message.text.strip()
    if not cookies:  
        # Format & test cookies
        formatted = format_cookies(text)
        is_valid, status = await test_cookies(formatted)
        cookies = formatted if is_valid else None
        
        if is_valid:
            await update.message.reply_text(
                f"✅ **Cookies VALID **{status}"
                "Send vouchers now:")
        else:
            await update.message.reply_text(
                f"❌ **Cookies FAILED** {status}"
                "Refresh page → recopy → retry",
                parse_mode='Markdown'
            )
        return
    
    # Process vouchers
    vouchers = [line.strip() for line in text.split('\n') if line.strip()]
    if not vouchers:
        await update.message.reply_text("❌ No voucher codes.")
        return
    
    headers = get_headers(cookies)
    msg = await update.message.reply_text(f"⚡ Checking {len(vouchers)}...")
    
    valid, results, total = [], [], 0
    errors = 0
    
    for code in vouchers:
        try:
            r = requests.post("https://www.sheinindia.in/api/cart/apply-voucher",
                json={"voucherId": code, "device": {"client_type": "web"}},
                headers=headers, timeout=12)
            data = safe_json_parse(r)
        except:
            data = {}
            errors += 1
        
        status, value = classify_response(data)
        value = get_value(code) or value or 0
        results.append(f"{status} `{code}` (₹{value})")
        
        if status == STATUS_APPLIED and value > 0:
            valid.append(code)
            total += value
        
        # Reset voucher
        try:
            requests.post("https://www.sheinindia.in/api/cart/reset-voucher",
                json={"voucherId": code, "device": {"client_type": "web"}}, 
                headers=headers, timeout=5)
        except: pass
    
    copy_text = ''.join(valid)
    out = f"✅ **{len(valid)} VALID** | **₹{total:,}**"
    out += ''.join(results[:25])
    
    if valid:
        out += f"📋**Copy:**```{copy_text}```"
    else:
        out += "😔 No working vouchers."
    
    if errors:
        out += f"⚠️ {errors} API errors"
    
    await msg.edit_text(out, parse_mode='Markdown')

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("🤖 Bot live - cookies ready to test!")
    app.run_polling()

if __name__ == "__main__":
    main()