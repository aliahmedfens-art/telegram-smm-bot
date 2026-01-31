#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import json
from datetime import datetime, timedelta
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.constants import ParseMode
import pymongo

# ===== إعدادات البوت =====
TOKEN = "8436742877:AAGJBn79jB5N91e-0IpzU57JrcJV5qSaWPs"
ADMIN_ID = 6130994941

# ===== إعداد MongoDB =====
client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["smm_bot_db"]

# المجموعات (Collections)
users_col = db["users"]
services_col = db["services"]
orders_col = db["orders"]
channels_col = db["channels"]
settings_col = db["settings"]
codes_col = db["codes"]
funding_col = db["funding"]

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== دوال المساعدة =====
def get_user_data(user_id):
    """الحصول على بيانات المستخدم"""
    user = users_col.find_one({"user_id": user_id})
    if not user:
        user = {
            "user_id": user_id,
            "points": 0,
            "invited_by": None,
            "invite_code": None,
            "joined_date": datetime.now(),
            "banned": False,
            "invited_users": 0
        }
        users_col.insert_one(user)
    return user

def update_user(user_id, data):
    """تحديث بيانات المستخدم"""
    users_col.update_one({"user_id": user_id}, {"$set": data})

def is_admin(user_id):
    """التحقق إذا كان المشرف"""
    return user_id == ADMIN_ID

def get_settings():
    """الحصول على الإعدادات"""
    settings = settings_col.find_one({"id": 1})
    if not settings:
        settings = {
            "id": 1,
            "daily_gift": 50,
            "daily_gift_active": True,
            "invite_points": 100,
            "invite_active": True,
            "maintenance": False,
            "bot_username": "",
            "support_chat": "",
            "bot_channel": "",
            "sub_channels": [],
            "funding_rate": 5
        }
        settings_col.insert_one(settings)
    return settings

def check_subscription(user_id, context):
    """التحقق من الاشتراك في القنوات"""
    settings = get_settings()
    for channel in settings["sub_channels"]:
        try:
            member = context.bot.get_chat_member(channel["id"], user_id)
            if member.status in ["left", "kicked"]:
                return False, channel
        except:
            continue
    return True, None

def create_pdf(order_data, user_data):
    """إنشاء فاتورة PDF"""
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    
    # إضافة محتوى الفاتورة
    c.setFont("Helvetica-Bold", 18)
    c.drawString(100, 750, "فاتورة الخدمة الرقمية")
    c.line(100, 745, 500, 745)
    
    c.setFont("Helvetica", 12)
    c.drawString(100, 700, f"اسم المستخدم: {user_data.get('username', 'غير معروف')}")
    c.drawString(100, 680, f"معرف المستخدم: {user_data['user_id']}")
    c.drawString(100, 660, f"رقم الطلب: #{order_data['order_id']}")
    c.drawString(100, 640, f"الخدمة: {order_data['service_name']}")
    c.drawString(100, 620, f"الكمية: {order_data['quantity']}")
    c.drawString(100, 600, f"السعر: {order_data['price']} نقطة")
    c.drawString(100, 580, f"التاريخ: {order_data['date'].strftime('%Y-%m-%d %H:%M')}")
    
    c.setFont("Helvetica-Bold", 14)
    c.drawString(100, 520, "شكراً لاستخدامك خدماتنا!")
    
    c.save()
    buffer.seek(0)
    return buffer

# ===== الأوامر الأساسية =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء البوت"""
    user = update.effective_user
    user_id = user.id
    
    # التحقق من الصيانة
    settings = get_settings()
    if settings["maintenance"] and not is_admin(user_id):
        await update.message.reply_text("⚙️ البوت قيد الصيانة حالياً. الرجاء المحاولة لاحقاً.")
        return
    
    # التحقق من الاشتراك
    subscribed, channel = check_subscription(user_id, context)
    if not subscribed and not is_admin(user_id):
        keyboard = [[InlineKeyboardButton("✅ اشتراك", url=f"https://t.me/{channel['username']}")],
                   [InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_sub")]]
        await update.message.reply_text(
            f"📢 يجب الاشتراك في القناة أولاً:\n{channel['title']}\n\n"
            f"بعد الاشتراك اضغط على زر التحقق",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # حفظ بيانات المستخدم
    user_data = get_user_data(user_id)
    
    # إرسال اشعار للمدير
    if not is_admin(user_id):
        await context.bot.send_message(
            ADMIN_ID,
            f"👤 دخول مستخدم جديد:\n"
            f"🆔: {user_id}\n"
            f"👤: @{user.username if user.username else 'بدون'}\n"
            f"📛: {user.full_name}\n"
            f"📅: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
    
    # عرض القائمة الرئيسية
    keyboard = [
        [KeyboardButton("🎁 الهدية اليومية"), KeyboardButton("💎 رصيدي")],
        [KeyboardButton("🛒 خدمات SMM"), KeyboardButton("👥 دعوة أصدقاء")],
        [KeyboardButton("📈 تمويل قناتي"), KeyboardButton("📊 تمويلاتي")],
        [KeyboardButton("🎫 شحن النقاط"), KeyboardButton("ℹ️ المساعدة")]
    ]
    
    if is_admin(user_id):
        keyboard.append([KeyboardButton("👑 لوحة التحكم")])
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        f"👋 أهلاً {user.full_name}!\n"
        f"🎮 مرحباً بك في بوت خدمات SMM\n\n"
        f"💎 نقاطك الحالية: {user_data['points']}\n"
        f"📊 المستخدمين المدعوين: {user_data['invited_users']}\n\n"
        f"اختر من القائمة أدناه:",
        reply_markup=reply_markup
    )

async def daily_gift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الهدية اليومية"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    settings = get_settings()
    
    if not settings["daily_gift_active"] and not is_admin(user_id):
        await update.message.reply_text("🎁 الهدية اليومية متوقفة حالياً.")
        return
    
    last_claim = user_data.get("last_daily_claim")
    if last_claim:
        last_date = last_claim.date() if isinstance(last_claim, datetime) else last_claim
        if datetime.now().date() <= last_date:
            await update.message.reply_text("🎁 لقد حصلت على هديتك اليوم بالفعل!\nارجع غداً.")
            return
    
    points = settings["daily_gift"]
    new_points = user_data["points"] + points
    update_user(user_id, {
        "points": new_points,
        "last_daily_claim": datetime.now()
    })
    
    await update.message.reply_text(f"🎁 لقد حصلت على {points} نقطة!\n💎 رصيدك الحالي: {new_points}")
    
    # إرسال اشعار للمدير
    await context.bot.send_message(
        ADMIN_ID,
        f"🎁 هدية يومية:\n"
        f"👤: {user_id}\n"
        f"🎁: {points} نقطة\n"
        f"🕒: {datetime.now().strftime('%H:%M')}"
    )

async def my_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الرصيد"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    keyboard = [
        [InlineKeyboardButton("👥 دعوة أصدقاء", callback_data="invite_friends")],
        [InlineKeyboardButton("🎫 شحن النقاط", callback_data="charge_points")],
        [InlineKeyboardButton("📈 تمويل قناتي", callback_data="fund_channel")]
    ]
    
    await update.message.reply_text(
        f"💎 معلومات حسابك:\n\n"
        f"🆔 المعرف: {user_id}\n"
        f"💎 النقاط: {user_data['points']}\n"
        f"👥 المستخدمين المدعوين: {user_data['invited_users']}\n"
        f"📅 تاريخ الانضمام: {user_data['joined_date'].strftime('%Y-%m-%d')}\n\n"
        f"طرق زيادة النقاط:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def smm_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض خدمات SMM"""
    services = list(services_col.find({"active": True}).sort("category", 1))
    
    if not services:
        await update.message.reply_text("📭 لا توجد خدمات حالياً.")
        return
    
    # تجميع الخدمات حسب الفئة
    categories = {}
    for service in services:
        cat = service.get("category", "عام")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(service)
    
    # إنشاء الكيبورد
    keyboard = []
    for cat, cat_services in categories.items():
        keyboard.append([InlineKeyboardButton(f"📂 {cat}", callback_data=f"cat_{cat}")])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
    
    await update.message.reply_text(
        "🛒 اختر فئة الخدمات:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def invite_friends(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دعوة الأصدقاء"""
    user_id = update.effective_user.id
    settings = get_settings()
    
    if not settings["invite_active"] and not is_admin(user_id):
        await update.message.reply_text("👥 نظام الدعوة متوقف حالياً.")
        return
    
    # إنشاء كود الدعوة
    invite_code = f"INV{user_id}"
    update_user(user_id, {"invite_code": invite_code})
    
    bot_username = context.bot.username
    invite_link = f"https://t.me/{bot_username}?start={invite_code}"
    
    await update.message.reply_text(
        f"👥 دعوة الأصدقاء\n\n"
        f"🎁 تكسب {settings['invite_points']} نقطة لكل صديق\n\n"
        f"🔗 رابط الدعوة:\n`{invite_link}`\n\n"
        f"📊 عدد المدعوين: {get_user_data(user_id)['invited_users']}\n\n"
        f"شارك الرابط مع أصدقائك واحصل على نقاط!",
        parse_mode=ParseMode.MARKDOWN
    )

async def fund_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تمويل القناة"""
    settings = get_settings()
    rate = settings["funding_rate"]
    
    await update.message.reply_text(
        f"📈 تمويل قناتي\n\n"
        f"💰 السعر: {rate} نقطة لكل عضو\n"
        f"📊 الحد الأدنى: 10 أعضاء\n"
        f"📈 الحد الأقصى: 1000 عضو\n\n"
        f"ارسل رابط قناتك الآن:"
    )
    context.user_data["awaiting_channel"] = True

async def my_funding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض طلبات التمويل"""
    user_id = update.effective_user.id
    fundings = list(funding_col.find({"user_id": user_id}).sort("date", -1))
    
    if not fundings:
        await update.message.reply_text("📭 ليس لديك طلبات تمويل.")
        return
    
    text = "📊 طلبات التمويل:\n\n"
    for fund in fundings:
        status = "🟢 مكتمل" if fund["completed"] else "🟡 قيد التنفيذ"
        text += f"📌 رابط: {fund['channel_link']}\n"
        text += f"👥 الأعضاء: {fund['members']}\n"
        text += f"💰 النقاط: {fund['points']}\n"
        text += f"📅 التاريخ: {fund['date'].strftime('%Y-%m-%d')}\n"
        text += f"📊 الحالة: {status}\n"
        text += f"🚀 تم الوصول: {fund.get('reached', 0)} عضو\n"
        text += "─" * 20 + "\n"
    
    await update.message.reply_text(text)

async def charge_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شحن النقاط"""
    keyboard = [
        [InlineKeyboardButton("🎫 استخدام كود", callback_data="use_code")],
        [InlineKeyboardButton("💳 شراء نقاط", callback_data="buy_points")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
    ]
    
    await update.message.reply_text(
        "🎫 طرق شحن النقاط:\n\n"
        "1️⃣ استخدام كود شحن\n"
        "2️⃣ شراء نقاط مباشرة\n\n"
        "اختر الطريقة:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مساعدة"""
    settings = get_settings()
    
    text = "ℹ️ مركز المساعدة:\n\n"
    text += "🎮 طريقة استخدام البوت:\n"
    text += "1️⃣ استخدم الأوامر من القائمة\n"
    text += "2️⃣ اختر الخدمة المطلوبة\n"
    text += "3️⃣ دفع النقاط\n"
    text += "4️⃣ استلام الخدمة\n\n"
    
    if settings["support_chat"]:
        text += f"📞 الدعم الفني: @{settings['support_chat']}\n"
    if settings["bot_channel"]:
        text += f"📢 قناة البوت: @{settings['bot_channel']}\n"
    
    await update.message.reply_text(text)

# ===== لوحة التحكم =====
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لوحة التحكم"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⚠️ هذا القسم للمشرفين فقط!")
        return
    
    keyboard = [
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
        [InlineKeyboardButton("👤 إدارة المستخدمين", callback_data="admin_users")],
        [InlineKeyboardButton("🛒 إدارة الخدمات", callback_data="admin_services")],
        [InlineKeyboardButton("⚙️ الإعدادات", callback_data="admin_settings")],
        [InlineKeyboardButton("📢 إذاعة", callback_data="admin_broadcast")],
        [InlineKeyboardButton("📈 الطلبات", callback_data="admin_orders")],
        [InlineKeyboardButton("🎫 أكواد الشحن", callback_data="admin_codes")],
        [InlineKeyboardButton("📢 قنوات الاشتراك", callback_data="admin_channels")],
        [InlineKeyboardButton("🔧 الصيانة", callback_data="admin_maintenance")]
    ]
    
    await update.message.reply_text(
        "👑 لوحة تحكم المشرف\n\n"
        "اختر القسم الذي تريد التحكم به:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إحصائيات البوت"""
    query = update.callback_query
    await query.answer()
    
    total_users = users_col.count_documents({})
    today_users = users_col.count_documents({
        "joined_date": {"$gte": datetime.now() - timedelta(days=1)}
    })
    active_users = users_col.count_documents({
        "last_active": {"$gte": datetime.now() - timedelta(days=7)}
    })
    total_points = sum(user["points"] for user in users_col.find({}, {"points": 1}))
    total_orders = orders_col.count_documents({})
    today_orders = orders_col.count_documents({
        "date": {"$gte": datetime.now() - timedelta(days=1)}
    })
    
    text = f"📊 إحصائيات البوت:\n\n"
    text += f"👥 إجمالي المستخدمين: {total_users}\n"
    text += f"📈 المستخدمين اليوم: {today_users}\n"
    text += f"🎯 المستخدمين النشطين: {active_users}\n"
    text += f"💎 إجمالي النقاط: {total_points}\n"
    text += f"🛒 إجمالي الطلبات: {total_orders}\n"
    text += f"📦 طلبات اليوم: {today_orders}\n"
    
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إدارة المستخدمين"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🔍 بحث عن مستخدم", callback_data="search_user")],
        [InlineKeyboardButton("📊 أعلى 10 مستخدمين", callback_data="top_users")],
        [InlineKeyboardButton("📋 قائمة المستخدمين", callback_data="list_users")],
        [InlineKeyboardButton("🚫 حظر مستخدم", callback_data="ban_user")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]
    ]
    
    await query.edit_message_text(
        "👤 إدارة المستخدمين:\n\n"
        "اختر الإجراء المطلوب:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إدارة الخدمات"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("➕ إضافة خدمة", callback_data="add_service")],
        [InlineKeyboardButton("✏️ تعديل خدمة", callback_data="edit_service")],
        [InlineKeyboardButton("🗑️ حذف خدمة", callback_data="delete_service")],
        [InlineKeyboardButton("📋 عرض الخدمات", callback_data="list_services")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]
    ]
    
    await query.edit_message_text(
        "🛒 إدارة الخدمات:\n\n"
        "اختر الإجراء المطلوب:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إعدادات البوت"""
    query = update.callback_query
    await query.answer()
    
    settings = get_settings()
    
    text = "⚙️ إعدادات البوت:\n\n"
    text += f"🎁 الهدية اليومية: {settings['daily_gift']} نقطة\n"
    text += f"   الحالة: {'✅ نشط' if settings['daily_gift_active'] else '❌ متوقف'}\n\n"
    text += f"👥 نقاط الدعوة: {settings['invite_points']} نقطة\n"
    text += f"   الحالة: {'✅ نشط' if settings['invite_active'] else '❌ متوقف'}\n\n"
    text += f"📈 سعر التمويل: {settings['funding_rate']} نقطة/عضو\n\n"
    text += f"📞 الدعم: @{settings['support_chat']}\n"
    text += f"📢 القناة: @{settings['bot_channel']}\n"
    
    keyboard = [
        [InlineKeyboardButton("🎁 تعديل الهدية", callback_data="edit_daily")],
        [InlineKeyboardButton("👥 تعديل الدعوة", callback_data="edit_invite")],
        [InlineKeyboardButton("📈 تعديل التمويل", callback_data="edit_funding")],
        [InlineKeyboardButton("📞 تعديل الدعم", callback_data="edit_support")],
        [InlineKeyboardButton("📢 تعديل القناة", callback_data="edit_channel")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الإذاعة"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📢 إرسال رسالة", callback_data="send_broadcast")],
        [InlineKeyboardButton("💎 إرسال نقاط", callback_data="send_points")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]
    ]
    
    await query.edit_message_text(
        "📢 الإذاعة للمستخدمين:\n\n"
        "اختر نوع الإذاعة:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ===== معالجة الكولباك =====
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الأزرار"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    if data == "back_main":
        await start(update, context)
    
    elif data == "admin_back":
        await admin_panel(update, context)
    
    elif data == "admin_stats":
        await admin_stats(update, context)
    
    elif data == "admin_users":
        await admin_users(update, context)
    
    elif data == "admin_services":
        await admin_services(update, context)
    
    elif data == "admin_settings":
        await admin_settings(update, context)
    
    elif data == "admin_broadcast":
        await admin_broadcast(update, context)
    
    elif data.startswith("cat_"):
        category = data.replace("cat_", "")
        services = list(services_col.find({"category": category, "active": True}))
        
        text = f"📂 {category}:\n\n"
        keyboard = []
        
        for service in services:
            btn_text = f"{service['name']} - {service['price']} نقطة"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"service_{service['_id']}")])
        
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_services")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data == "back_services":
        await smm_services(update, context)
    
    elif data == "check_sub":
        subscribed, channel = check_subscription(user_id, context)
        if subscribed:
            await query.message.delete()
            await start(update, context)
        else:
            await query.answer("لم تشترك بعد!", show_alert=True)

# ===== معالجة الرسائل =====
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل النصية"""
    user_id = update.effective_user.id
    text = update.message.text
    
    if text == "🎁 الهدية اليومية":
        await daily_gift(update, context)
    
    elif text == "💎 رصيدي":
        await my_points(update, context)
    
    elif text == "🛒 خدمات SMM":
        await smm_services(update, context)
    
    elif text == "👥 دعوة أصدقاء":
        await invite_friends(update, context)
    
    elif text == "📈 تمويل قناتي":
        await fund_channel(update, context)
    
    elif text == "📊 تمويلاتي":
        await my_funding(update, context)
    
    elif text == "🎫 شحن النقاط":
        await charge_points(update, context)
    
    elif text == "ℹ️ المساعدة":
        await help_command(update, context)
    
    elif text == "👑 لوحة التحكم":
        await admin_panel(update, context)
    
    elif context.user_data.get("awaiting_channel"):
        # معالجة رابط القناة
        if "t.me" in text:
            await update.message.reply_text("📊 الآن ارسل عدد الأعضاء الحالي:")
            context.user_data["channel_link"] = text
            context.user_data["awaiting_members"] = True
        else:
            await update.message.reply_text("❌ الرابط غير صالح. أرسل رابط القناة الصحيح.")
    
    elif context.user_data.get("awaiting_members"):
        # معالجة عدد الأعضاء
        try:
            members = int(text)
            if members < 10:
                await update.message.reply_text("❌ الحد الأدنى 10 أعضاء.")
                return
            
            settings = get_settings()
            points = members * settings["funding_rate"]
            
            # حفظ طلب التمويل
            funding_data = {
                "user_id": user_id,
                "channel_link": context.user_data["channel_link"],
                "members": members,
                "points": points,
                "date": datetime.now(),
                "completed": False,
                "reached": 0
            }
            funding_col.insert_one(funding_data)
            
            await update.message.reply_text(
                f"✅ تم استلام طلب التمويل!\n\n"
                f"📌 الرابط: {context.user_data['channel_link']}\n"
                f"👥 الأعضاء: {members}\n"
                f"💰 النقاط المستحقة: {points}\n\n"
                f"سيتم إضافة النقاط عند اكتمال الطلب."
            )
            
            # إرسال اشعار للمدير
            await context.bot.send_message(
                ADMIN_ID,
                f"📈 طلب تمويل جديد:\n"
                f"👤: {user_id}\n"
                f"📌: {context.user_data['channel_link']}\n"
                f"👥: {members} عضو\n"
                f"💰: {points} نقطة"
            )
            
            # مسح البيانات المؤقتة
            context.user_data.pop("awaiting_channel", None)
            context.user_data.pop("channel_link", None)
            context.user_data.pop("awaiting_members", None)
            
        except ValueError:
            await update.message.reply_text("❌ الرجاء إدخال رقم صحيح.")

# ===== الدالة الرئيسية =====
def main():
    """تشغيل البوت"""
    # إنشاء التطبيق
    application = Application.builder().token(TOKEN).build()
    
    # إضافة handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    # معالجة الكولباك
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # معالجة الرسائل
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    # بدء البوت
    print("🤖 البوت يعمل الآن...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
