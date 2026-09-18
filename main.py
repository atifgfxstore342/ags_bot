import os
import io
import json
import logging
import asyncio
import time
from aiohttp import web
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════
BOT_TOKEN = "8758213254:AAG68VLPzfYVksN_-d057yNaphQ1VwNU7c8"
PRIMARY_OWNER_ID = 6101405394
ADMIN_IDS = [6101405394, 7734488722]
REQUIRED_CHANNEL = "@rixorchat" 

DATA_FILE = "bot_data.json"
GUEST_ACCOUNTS_FILE = "BD_accounts.json"

logging.basicConfig(level=logging.ERROR)
logging.getLogger("httpx").setLevel(logging.CRITICAL)
logging.getLogger("telegram").setLevel(logging.ERROR)

bot_lock = asyncio.Lock()

# ═══════════════════════════════════════════════════════════════════════════
# DATABASE & CACHE
# ═══════════════════════════════════════════════════════════════════════════
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"users": {}, "redeem_codes": {}, "stats": {"date": "", "today_given": 0}}

def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def load_accounts():
    if os.path.exists(GUEST_ACCOUNTS_FILE):
        try:
            with open(GUEST_ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            return []
    return []

def save_accounts(accounts):
    try:
        with open(GUEST_ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(accounts, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

BOT_DATA = load_data()
ACCOUNTS_CACHE = load_accounts()

def get_user(user_id):
    uid = str(user_id)
    if uid not in BOT_DATA["users"]:
        BOT_DATA["users"][uid] = {
            "credits": 0,
            "is_vip": False,
            "last_free_claim": 0,
            "referred_by": None,
            "joined_verified": False
        }
    return BOT_DATA["users"][uid]

def check_daily_stats():
    today = datetime.now().strftime("%Y-%m-%d")
    if BOT_DATA["stats"].get("date") != today:
        BOT_DATA["stats"]["date"] = today
        BOT_DATA["stats"]["today_given"] = 0

async def is_user_joined(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

# ═══════════════════════════════════════════════════════════════════════════
# KEYBOARDS
# ═══════════════════════════════════════════════════════════════════════════
def main_keyboard(user_id):
    buttons = [
        ["🎮 GUEST ACCOUNTS", "💳 GET CREDIT"],
        ["💎 BUY PREMIUM", "🎟️ REDEEM CODE"],
        ["🔄 START AGAIN"],
        ["👨‍💻 CONTACT ADMIN", "👑 CONTACT BOT OWNER"]
    ]
    if user_id in ADMIN_IDS:
        buttons.append(["⚙️ ADMIN PANEL"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def admin_keyboard(user_id):
    keyboard = [
        [InlineKeyboardButton("📝 MAKE REDEEM CODE", callback_data="admin_make_code")],
        [InlineKeyboardButton("❌ REMOVE REDEEM CODE", callback_data="admin_remove_code")],
        [InlineKeyboardButton("🎟️ REDEEMS", callback_data="admin_view_redeems")],
        [InlineKeyboardButton("📁 LOAD GUEST ACCOUNT FILE", callback_data="admin_load_file")],
        [InlineKeyboardButton("🗑️ REMOVE GUEST ACCOUNT FILE", callback_data="admin_remove_file")],
        [InlineKeyboardButton("📊 TODAY GUEST GIVEN", callback_data="admin_today_stats")],
        [InlineKeyboardButton("📦 REMAINING ACCOUNTS", callback_data="admin_remaining")]
    ]
    if user_id == PRIMARY_OWNER_ID:
        keyboard.append([InlineKeyboardButton("⭐ SET USER VIP MEMBERSHIP", callback_data="admin_set_vip")])
    return InlineKeyboardMarkup(keyboard)

# ═══════════════════════════════════════════════════════════════════════════
# REFERRAL & FORCE JOIN HANDLERS
# ═══════════════════════════════════════════════════════════════════════════
async def check_and_award_referral(user_id, context):
    user = get_user(user_id)
    if user.get("referred_by") and not user.get("joined_verified"):
        ref_id = user["referred_by"]
        if ref_id in BOT_DATA["users"]:
            BOT_DATA["users"][ref_id]["credits"] += 1
            user["joined_verified"] = True
            save_data(BOT_DATA)
            try:
                await context.bot.send_message(
                    chat_id=int(ref_id),
                    text="🎉 Congratulations! আপনার রেফার করা ইউজার সফলভাবে চ্যানেলে জয়েন করেছে। আপনি ১ ক্রেডিট পেয়েছেন! (১ ক্রেডিট = ২০০ একাউন্ট)"
                )
            except Exception:
                pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if context.args and not user.get("referred_by") and not user.get("joined_verified"):
        ref_id = context.args[0]
        if ref_id != str(user_id) and ref_id in BOT_DATA["users"]:
            user["referred_by"] = ref_id
    save_data(BOT_DATA)

    if not await is_user_joined(user_id, context):
        join_btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Join Channel", url="https://t.me/rixorchat")],
            [InlineKeyboardButton("✅ Check Verification", callback_data="check_join")]
        ])
        await update.message.reply_text(
            "⚠️ বটটি ব্যবহার করতে হলে অবশ্যই আপনাকে আমাদের টেলিগ্রাম চ্যানেলে জয়েন করতে হবে!",
            reply_markup=join_btn
        )
        return

    await check_and_award_referral(user_id, context)
    await update.message.reply_text(
        f"👋 হ্যালো {update.effective_user.first_name}!\nআপনার প্রয়োজনীয় অপশন নির্বাচন করুন:",
        reply_markup=main_keyboard(user_id)
    )

async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if await is_user_joined(user_id, context):
        await query.message.delete()
        await check_and_award_referral(user_id, context)
        await query.message.reply_text("✅ ভেরিফিকেশন সফল হয়েছে!", reply_markup=main_keyboard(user_id))
    else:
        await query.answer("❌ আপনি এখনও চ্যানেলে যোগ দেননি! আগে চ্যানেলে জয়েন করুন।", show_alert=True)

# ═══════════════════════════════════════════════════════════════════════════
# ACCOUNT DISPATCH ENGINE
# ═══════════════════════════════════════════════════════════════════════════
async def dispatch_accounts(chat_id, user_id, cost_type, context: ContextTypes.DEFAULT_TYPE):
    async with bot_lock:
        user = get_user(user_id)
        available_total = len(ACCOUNTS_CACHE)
        if available_total == 0:
            await context.bot.send_message(chat_id=chat_id, text="❌ পর্যাপ্ত একাউন্ট নেই। Contact To Owner")
            return

        batch_size = min(200, available_total)
        current_time = time.time()

        if cost_type == "FREE (12-HOURS)":
            user["last_free_claim"] = current_time
        elif cost_type == "1 CREDIT USED":
            if user.get("credits", 0) >= 1:
                user["credits"] -= 1
            else:
                await context.bot.send_message(chat_id=chat_id, text="❌ আপনার পর্যাপ্ত ক্রেডিট নেই!")
                return

        delivered_accounts = [ACCOUNTS_CACHE.pop(0) for _ in range(batch_size)]
        save_accounts(ACCOUNTS_CACHE)
        BOT_DATA["stats"]["today_given"] += batch_size
        save_data(BOT_DATA)

        json_bytes = json.dumps(delivered_accounts, indent=4, ensure_ascii=False).encode('utf-8')
        file_stream = io.BytesIO(json_bytes)
        filename = f"AGS_ACCOUNTS_{int(time.time())}.json"
        file_stream.name = filename

        caption = (
            f"✅ **{batch_size} Accounts Delivered!**\n\n"
            f"📦 ফরম্যাট: JSON File\n"
            f"🎟️ মেথড: {cost_type}\n"
            f"📁 অবশিষ্ট স্টক: {len(ACCOUNTS_CACHE)} টি\n\n"
            f"🔥 Powered by AGS-GEN"
        )

        await context.bot.send_document(
            chat_id=chat_id,
            document=file_stream,
            filename=filename,
            caption=caption,
            parse_mode="Markdown"
        )

# ═══════════════════════════════════════════════════════════════════════════
# MESSAGE HANDLERS
# ═══════════════════════════════════════════════════════════════════════════
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if not await is_user_joined(user_id, context):
        join_btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Join Channel", url="https://t.me/rixorchat")],
            [InlineKeyboardButton("✅ Check Verification", callback_data="check_join")]
        ])
        await update.message.reply_text("⚠️ আগে চ্যানেলে জয়েন করুন:", reply_markup=join_btn)
        return

    user = get_user(user_id)
    check_daily_stats()

    if text == "🔄 START AGAIN":
        context.user_data.clear()
        await update.message.reply_text("🔄 বট সফলভাবে রিফ্রেশ করা হয়েছে!", reply_markup=main_keyboard(user_id))
        return

    elif text == "👨‍💻 CONTACT ADMIN":
        await update.message.reply_text("👨‍💻 **Contact Admin:** [7734488722](tg://user?id=7734488722)", parse_mode="Markdown")
        return

    elif text == "👑 CONTACT BOT OWNER":
        await update.message.reply_text("👑 **Contact Bot Owner:** [@ags_owner_atif](https://t.me/ags_owner_atif) (ID: `6101405394`)", parse_mode="Markdown")
        return

    elif text == "🎮 GUEST ACCOUNTS":
        available_total = len(ACCOUNTS_CACHE)
        if available_total == 0:
            await update.message.reply_text("❌ পর্যাপ্ত একাউন্ট নেই। Contact To Owner")
            return

        current_time = time.time()
        time_diff = current_time - user.get("last_free_claim", 0)
        twelve_hours = 12 * 3600

        can_give = False
        cost_type = ""

        if user.get("is_vip", False):
            can_give = True
            cost_type = "VIP UNLIMITED"
        elif time_diff >= twelve_hours:
            can_give = True
            cost_type = "FREE (12-HOURS)"
        elif user.get("credits", 0) >= 1:
            can_give = True
            cost_type = "1 CREDIT USED"
        else:
            remaining_sec = int(twelve_hours - time_diff)
            rem_h = remaining_sec // 3600
            rem_m = (remaining_sec % 3600) // 60
            await update.message.reply_text(
                f"⚠️ **ফ্রি লিমিট শেষ!**\n\n"
                f"আপনি প্রতি ১২ ঘণ্টায় একবার ফ্রি ২০০টি একাউন্ট নিতে পারবেন।\n"
                f"⏳ পরবর্তী ফ্রি ক্লেইম করতে বাকি: **{rem_h} ঘণ্টা {rem_m} মিনিট**।\n\n"
                f"💡 এখনই একাউন্ট নিতে বন্ধুদের রেফার করে ক্রেডিট আর্ন করুন (GET CREDIT)।",
                parse_mode="Markdown"
            )
            return

        if can_give:
            if available_total < 200:
                context.user_data["pending_cost_type"] = cost_type
                confirm_keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ YES GIVE", callback_data="claim_yes"),
                        InlineKeyboardButton("❌ NO I WILL WAIT", callback_data="claim_no")
                    ]
                ])
                await update.message.reply_text(
                    f"⚠️ **নোটিশ: স্টকে পর্যাপ্ত একাউন্ট নেই!**\n\n"
                    f"বর্তমানে স্টকে মাত্র **{available_total}টি** একাউন্ট অবশিষ্ট আছে।\n"
                    f"আপনি কি এখন এই **{available_total}টি** একাউন্টই নিতে চান? নাকি কিছুক্ষণ অপেক্ষা করবেন?\n\n"
                    f"💡 কিছুক্ষণ পর ট্রাই করলে নতুন ফাইল লোড হতে পারে এবং তখন একসাথে পূর্ণ ২০০টি একাউন্ট পাবেন।",
                    reply_markup=confirm_keyboard,
                    parse_mode="Markdown"
                )
            else:
                await dispatch_accounts(update.effective_chat.id, user_id, cost_type, context)
        return

    elif text == "💳 GET CREDIT":
        bot_info = await context.bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
        vip_status = "🌟 ACTIVE (UNLIMITED)" if user.get("is_vip") else "❌ INACTIVE"
        
        current_time = time.time()
        time_diff = current_time - user.get("last_free_claim", 0)
        if time_diff >= 12 * 3600:
            free_status = "🎁 AVAILABLE NOW"
        else:
            rem_sec = int((12 * 3600) - time_diff)
            free_status = f"⏳ {rem_sec // 3600}h {(rem_sec % 3600) // 60}m remaining"

        await update.message.reply_text(
            f"🎁 **আপনার রেফারেল লিংক:**\n`{ref_link}`\n\n"
            f"👤 বর্তমান ক্রেডিট: {user['credits']}\n"
            f"🕒 ফ্রি কোটা স্ট্যাটাস: {free_status}\n"
            f"⭐ VIP স্ট্যাটাস: {vip_status}\n\n"
            f"⚠️ **শর্ত:** যাকে রেফার করবেন তাকে অবশ্যই চ্যানেলে জয়েন হতে হবে, জয়েন করলেই আপনি ১ ক্রেডিট পাবেন (১ ক্রেডিট = ২০০ একাউন্ট)।",
            parse_mode="Markdown"
        )
        return

    elif text == "💎 BUY PREMIUM":
        await update.message.reply_text(
            "💎 **Premium Subscription**\n\n"
            "প্রিমিয়াম আনলিমিটেড একাউন্ট নিতে যোগাযোগ করুন:\n"
            "👑 Bot Owner : [@ags_owner_atif](https://t.me/ags_owner_atif) (`6101405394`)\n"
            "👨‍💻 Admin : [7734488722](tg://user?id=7734488722)",
            parse_mode="Markdown"
        )
        return

    elif text == "🎟️ REDEEM CODE":
        context.user_data["awaiting_code"] = True
        await update.message.reply_text("🔑 আপনার রিডিম কোডটি লিখে পাঠান:")
        return

    elif text == "⚙️ ADMIN PANEL" and user_id in ADMIN_IDS:
        await update.message.reply_text("👑 **Admin Panel:**", reply_markup=admin_keyboard(user_id), parse_mode="Markdown")
        return

    # ═══════════ STATE HANDLING ═══════════
    if context.user_data.get("awaiting_custom_code") and user_id in ADMIN_IDS:
        context.user_data["awaiting_custom_code"] = False
        parts = text.split()
        if len(parts) == 3:
            code_name = parts[0]
            try:
                max_users = int(parts[1])
                credit_amount = int(parts[2])
                BOT_DATA["redeem_codes"][code_name] = {
                    "credits": credit_amount,
                    "max_uses": max_users,
                    "used_by": []
                }
                save_data(BOT_DATA)
                await update.message.reply_text(
                    f"✅ **নতুন রিডিম কোড তৈরি হয়েছে:**\n`{code_name}`\nইউজার: {max_users} জন | ক্রেডিট: {credit_amount} টি",
                    parse_mode="Markdown"
                )
            except ValueError:
                await update.message.reply_text("❌ ভুল ইনপুট! সংখ্যা সঠিক দিন।")
        else:
            await update.message.reply_text("❌ উদাহরণ: `AGS-RIXOR 10 4`", parse_mode="Markdown")
        return

    if context.user_data.get("awaiting_remove_code") and user_id in ADMIN_IDS:
        context.user_data["awaiting_remove_code"] = False
        code_to_remove = text
        if code_to_remove in BOT_DATA.get("redeem_codes", {}):
            del BOT_DATA["redeem_codes"][code_to_remove]
            save_data(BOT_DATA)
            await update.message.reply_text(f"🗑️ রিডিম কোড `{code_to_remove}` সফলভাবে ডিলিট করা হয়েছে!", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"❌ `{code_to_remove}` নামের কোনো রিডিম কোড পাওয়া যায়নি!", parse_mode="Markdown")
        return

    if context.user_data.get("awaiting_vip_id") and user_id == PRIMARY_OWNER_ID:
        context.user_data["awaiting_vip_id"] = False
        target_uid = text
        target_user = get_user(target_uid)
        target_user["is_vip"] = True
        save_data(BOT_DATA)
        await update.message.reply_text(f"🌟 ইউজার `{target_uid}` কে **VIP** করা হয়েছে!", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=int(target_uid), text="🎉 আপনাকে বটের **VIP Membership** দেওয়া হয়েছে! এখন আনলিমিটেড একাউন্ট নিতে পারবেন।")
        except Exception:
            pass
        return

    if context.user_data.get("awaiting_code"):
        code = text
        context.user_data["awaiting_code"] = False
        uid_str = str(user_id)
        
        if code in BOT_DATA["redeem_codes"]:
            c_data = BOT_DATA["redeem_codes"][code]
            if uid_str in c_data["used_by"]:
                await update.message.reply_text("⚠️ আপনি ইতিমধ্যে কোডটি ব্যবহার করেছেন!")
                return
            if len(c_data["used_by"]) >= c_data["max_uses"]:
                await update.message.reply_text("❌ এই রিডিম কোডটি Expired!")
                return

            c_data["used_by"].append(uid_str)
            user["credits"] += c_data["credits"]
            
            if len(c_data["used_by"]) >= c_data["max_uses"]:
                del BOT_DATA["redeem_codes"][code]
                
            save_data(BOT_DATA)
            await update.message.reply_text(f"🎉 রিডিম সফল! {c_data['credits']} ক্রেডিট যোগ হয়েছে।")
        else:
            await update.message.reply_text("❌ ভুল বা মেয়াদোত্তীর্ণ রিডিম কোড!")
        return

# ═══════════════════════════════════════════════════════════════════════════
# CALLBACK HANDLERS
# ═══════════════════════════════════════════════════════════════════════════
async def callbacks_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ACCOUNTS_CACHE
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "claim_yes":
        cost_type = context.user_data.get("pending_cost_type", "FREE (12-HOURS)")
        context.user_data.pop("pending_cost_type", None)
        await query.message.delete()
        await dispatch_accounts(query.message.chat_id, user_id, cost_type, context)
        return

    elif data == "claim_no":
        context.user_data.pop("pending_cost_type", None)
        await query.message.edit_text("⏳ **Please wait Few Minute.** পরে চেষ্টা করলে ফুল ২০০ একাউন্ট পাবেন।", parse_mode="Markdown")
        return

    if user_id not in ADMIN_IDS:
        return

    check_daily_stats()

    if data == "admin_remove_code":
        active_codes = BOT_DATA.get("redeem_codes", {})
        if not active_codes:
            await query.message.reply_text("ℹ️ ডিলিট করার মতো কোনো সক্রিয় রিডিম কোড নেই।")
            return
        context.user_data["awaiting_remove_code"] = True
        available_list = "\n".join([f"• `{c}`" for c in active_codes.keys()])
        await query.message.reply_text(
            f"❌ **যে কোডটি ডিলিট করতে চান তা লিখে পাঠান:**\n\n"
            f"📋 **বর্তমান কোডগুলো:**\n{available_list}",
            parse_mode="Markdown"
        )

    elif data == "admin_view_redeems":
        active_codes = BOT_DATA.get("redeem_codes", {})
        if not active_codes:
            await query.message.reply_text("ℹ️ বর্তমানে কোনো সক্রিয় রিডিম কোড নেই।")
            return

        report = "🎟️ **ACTIVE REDEEM CODES OVERVIEW**\n"
        report += "═" * 32 + "\n\n"
        for code, info in active_codes.items():
            used = len(info.get("used_by", []))
            total = info.get("max_uses", 0)
            left = total - used
            creds = info.get("credits", 0)
            report += (
                f"┌──────────────────────────────\n"
                f"│ 🔑 **Code**     : `{code}`\n"
                f"│ 💳 **Credit**   : {creds} টি (প্রতিজনে)\n"
                f"│ 👥 **Used**     : {used}/{total} জন\n"
                f"│ ⏳ **Left**     : {left} জন নিতে পারবে\n"
                f"└──────────────────────────────\n\n"
            )
        report += f"📊 মোট কার্যকর কোড: {len(active_codes)} টি"
        await query.message.reply_text(report, parse_mode="Markdown")

    elif data == "admin_today_stats":
        await query.message.reply_text(
            f"📊 **Today's Stats:**\n"
            f"▸ আজ একাউন্ট দেওয়া হয়েছে: {BOT_DATA['stats']['today_given']} টি\n"
            f"▸ স্টকে অবশিষ্ট আছে: {len(ACCOUNTS_CACHE)} টি",
            parse_mode="Markdown"
        )

    elif data == "admin_remaining":
        await query.message.reply_text(f"📦 দেওয়ার মতো বাকি একাউন্ট আছে: {len(ACCOUNTS_CACHE)} টি")

    elif data == "admin_load_file":
        context.user_data["awaiting_file"] = True
        await query.message.reply_text("📂 অনুগ্রহ করে `BD_accounts.json` ফাইলটি সেন্ড করুন:")

    elif data == "admin_remove_file":
        async with bot_lock:
            ACCOUNTS_CACHE.clear()
            if os.path.exists(GUEST_ACCOUNTS_FILE):
                os.remove(GUEST_ACCOUNTS_FILE)
            await query.message.reply_text("🗑️ সফলভাবে একাউন্ট ফাইল ডিলিট ও মেমোরি খালি করা হয়েছে।")

    elif data == "admin_make_code":
        context.user_data["awaiting_custom_code"] = True
        await query.message.reply_text("📝 ফরম্যাট: `[কোড] [ইউজার সংখ্যা] [ক্রেডিট]`\n💡 উদাহরণ: `AGS-RIXOR 10 4`", parse_mode="Markdown")

    elif data == "admin_set_vip":
        if user_id != PRIMARY_OWNER_ID:
            await query.answer("❌ শুধুমাত্র Bot Owner এই অপশনটি অ্যাক্সেস করতে পারবেন!", show_alert=True)
            return
        context.user_data["awaiting_vip_id"] = True
        await query.message.reply_text("👑 যাকে VIP করতে চান তার Telegram Chat ID দিন:", parse_mode="Markdown")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ACCOUNTS_CACHE
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return

    if context.user_data.get("awaiting_file"):
        doc = update.message.document
        if not doc.file_name.endswith(".json"):
            await update.message.reply_text("❌ শুধু JSON ফাইল দিন!")
            return

        file = await context.bot.get_file(doc.file_id)
        await file.download_to_drive(GUEST_ACCOUNTS_FILE)
        context.user_data["awaiting_file"] = False

        async with bot_lock:
            ACCOUNTS_CACHE = load_accounts()
        await update.message.reply_text(f"✅ ফাইল সফলভাবে লোড হয়েছে! মোট {len(ACCOUNTS_CACHE)} টি একাউন্ট যুক্ত হয়েছে।")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    pass

# ═══════════════════════════════════════════════════════════════════════════
# RENDER DUMMY PORT BINDING (PREVENTS TIMEOUT)
# ═══════════════════════════════════════════════════════════════════════════
async def dummy_server(request):
    return web.Response(text="Bot is running!")

async def start_dummy_port():
    app = web.Application()
    app.router.add_get('/', dummy_server)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def post_init(application):
    await start_dummy_port()

# ═══════════════════════════════════════════════════════════════════════════
# RUN BOT
# ═══════════════════════════════════════════════════════════════════════════
def main():
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .connection_pool_size(100)
        .pool_timeout(30.0)
        .post_init(post_init)
        .build()
    )

    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"))
    app.add_handler(CallbackQueryHandler(callbacks_router, pattern="^(claim_|admin_)"))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))

    print("⚡ Bot is running with Render Port Binding & Stock Confirmation logic!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()