# -*- coding: utf-8 -*-
import os
import json
import logging
import random
import string
import asyncio
from datetime import datetime, timedelta
from io import BytesIO
from typing import Dict, List, Optional
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
import qrcode
from PIL import Image, ImageDraw, ImageFont
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, 
    ReplyKeyboardMarkup, KeyboardButton, ChatPermissions
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.constants import ParseMode, ChatMemberStatus

# ========== إعدادات البوت ==========
BOT_TOKEN = "8436742877:AAGJBn79jB5N91e-0IpzU57JrcJV5qSaWPs"
ADMIN_ID = 6130994941
BOT_USERNAME = "@Flashback70bot"

# ========== إعدادات التسجيل ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== إعدادات الخط العربي ==========
try:
    pdfmetrics.registerFont(TTFont('Arabic', 'fonts/arial.ttf'))
except:
    pass

# ========== قاعدة البيانات ==========
class Database:
    def __init__(self):
        self.data_files = {
            'users': 'data/users.json',
            'services': 'data/services.json',
            'categories': 'data/categories.json',
            'orders': 'data/orders.json',
            'codes': 'data/codes.json',
            'channels': 'data/channels.json',
            'settings': 'data/settings.json',
            'funding': 'data/funding.json',
            'subscriptions': 'data/subscriptions.json',
            'admins': 'data/admins.json',
            'buttons': 'data/buttons.json'
        }
        self.create_data_dir()
        self.load_all_data()
    
    def create_data_dir(self):
        if not os.path.exists('data'):
            os.makedirs('data')
        for file in self.data_files.values():
            if not os.path.exists(file):
                with open(file, 'w', encoding='utf-8') as f:
                    json.dump({}, f, ensure_ascii=False)
    
    def load_all_data(self):
        self.users = self.load_data('users')
        self.services = self.load_data('services')
        self.categories = self.load_data('categories')
        self.orders = self.load_data('orders')
        self.codes = self.load_data('codes')
        self.channels = self.load_data('channels')
        self.settings = self.load_data('settings')
        self.funding = self.load_data('funding')
        self.subscriptions = self.load_data('subscriptions')
        self.admins = self.load_data('admins')
        self.buttons = self.load_data('buttons')
        
        # إعدادات افتراضية
        if 'daily_reward' not in self.settings:
            self.settings.update({
                'daily_reward': 50,
                'invite_reward': 100,
                'daily_active': True,
                'invite_active': True,
                'maintenance': False,
                'notifications': True,
                'bot_channel': '@Flashback70bot',
                'support_user': '@support',
                'channel_funding_rate': 5,
                'subscription_reward': 10,
                'min_withdraw': 1000,
                'max_withdraw': 10000,
                'welcome_message': 'مرحباً بك في بوت طاش للخدمات الإلكترونية!',
                'currency': 'نقطة'
            })
        
        # إضافة المدير الأساسي
        if str(ADMIN_ID) not in self.admins:
            self.admins[str(ADMIN_ID)] = {
                'level': 3,  # أعلى مستوى
                'added_by': 'system',
                'added_date': datetime.now().isoformat(),
                'permissions': ['all']
            }
            self.save_data('admins')
    
    def load_data(self, key):
        try:
            with open(self.data_files[key], 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    
    def save_data(self, key):
        with open(self.data_files[key], 'w', encoding='utf-8') as f:
            json.dump(getattr(self, key), f, ensure_ascii=False, indent=2)
    
    def save_all(self):
        for key in self.data_files.keys():
            self.save_data(key)
    
    def get_user(self, user_id):
        uid = str(user_id)
        if uid not in self.users:
            self.users[uid] = {
                'id': user_id,
                'username': '',
                'first_name': '',
                'join_date': datetime.now().isoformat(),
                'points': 0,
                'invited_by': None,
                'invited_users': [],
                'daily_date': None,
                'total_orders': 0,
                'total_spent': 0,
                'banned': False,
                'ban_reason': '',
                'funding_requests': [],
                'pending_orders': [],
                'completed_orders': [],
                'subscriptions_done': [],
                'last_active': datetime.now().isoformat()
            }
            self.save_data('users')
        return self.users[uid]
    
    def update_user(self, user_id, data):
        self.users[str(user_id)].update(data)
        self.save_data('users')
    
    def is_admin(self, user_id, min_level=1):
        uid = str(user_id)
        return uid in self.admins and self.admins[uid]['level'] >= min_level
    
    def get_admin_level(self, user_id):
        uid = str(user_id)
        return self.admins.get(uid, {}).get('level', 0)

db = Database()

# ========== دوال المساعدة ==========
def format_arabic(text):
    """تنسيق النصوص العربية"""
    try:
        reshaped_text = arabic_reshaper.reshape(text)
        return get_display(reshaped_text)
    except:
        return text

def generate_code(length=8):
    """إنشاء كود عشوائي"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """فحص اشتراك المستخدم في القنوات المطلوبة"""
    if not db.channels:
        return True
    
    for channel_id, channel_data in db.channels.items():
        try:
            member = await context.bot.get_chat_member(channel_id, user_id)
            if member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]:
                return False
        except Exception as e:
            logger.error(f"Error checking subscription: {e}")
            return False
    return True

async def send_notification_to_admin(message: str, context: ContextTypes.DEFAULT_TYPE):
    """إرسال إشعار إلى المدير"""
    try:
        await context.bot.send_message(ADMIN_ID, message, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error sending notification: {e}")

async def notify_admins(message: str, context: ContextTypes.DEFAULT_TYPE, min_level=1):
    """إرسال إشعار لجميع المديرين"""
    for admin_id in db.admins:
        if db.get_admin_level(int(admin_id)) >= min_level:
            try:
                await context.bot.send_message(int(admin_id), message, parse_mode=ParseMode.HTML)
            except:
                pass

def create_pdf_invoice(order_data: dict, user_data: dict) -> BytesIO:
    """إنشاء فاتورة PDF باللغة العربية"""
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    
    # إضافة نص عربي
    try:
        pdfmetrics.registerFont(TTFont('Arabic', 'arial.ttf'))
        c.setFont('Arabic', 16)
    except:
        c.setFont('Helvetica', 16)
    
    # العنوان
    c.drawString(100, 800, format_arabic("فاتورة خدمات SMM"))
    c.drawString(100, 780, format_arabic("بوت طاش للخدمات الإلكترونية"))
    
    # معلومات العميل
    c.setFont('Helvetica', 12)
    c.drawString(100, 750, format_arabic(f"اسم العميل: {user_data.get('first_name', '')}"))
    c.drawString(100, 730, format_arabic(f"معرف العميل: {user_data.get('id', '')}"))
    c.drawString(100, 710, format_arabic(f"تاريخ الفاتورة: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    c.drawString(100, 690, format_arabic(f"رقم الفاتورة: #{order_data.get('id', '0000')}"))
    
    # تفاصيل الطلب
    c.drawString(100, 650, format_arabic("تفاصيل الطلب:"))
    c.drawString(120, 630, format_arabic(f"الخدمة: {order_data.get('service_name', '')}"))
    c.drawString(120, 610, format_arabic(f"الكمية: {order_data.get('quantity', 0)}"))
    c.drawString(120, 590, format_arabic(f"السعر للنقطة: {order_data.get('price_per_unit', 0)}"))
    c.drawString(120, 570, format_arabic(f"المبلغ الإجمالي: {order_data.get('total_price', 0)} نقطة"))
    c.drawString(120, 550, format_arabic(f"حالة الطلب: {order_data.get('status', 'معلق')}"))
    
    # رسالة شكر
    c.setFont('Helvetica-Bold', 14)
    c.drawString(100, 450, format_arabic("شكراً لثقتك ببوت طاش للخدمات الإلكترونية!"))
    c.setFont('Helvetica', 12)
    c.drawString(100, 420, format_arabic("للاستفسارات: @Flashback70bot"))
    
    c.save()
    buffer.seek(0)
    return buffer

# ========== معالجة الأوامر ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء البوت"""
    user = update.effective_user
    user_id = user.id
    
    # تسجيل المستخدم
    db_user = db.get_user(user_id)
    db.update_user(user_id, {
        "username": user.username or "",
        "first_name": user.first_name or "",
        "last_active": datetime.now().isoformat()
    })
    
    # التحقق من الحظر
    if db_user.get('banned'):
        await update.message.reply_text(
            "❌ حسابك محظور من استخدام البوت.\n"
            f"السبب: {db_user.get('ban_reason', 'غير محدد')}"
        )
        return
    
    # التحقق من الصيانة
    if db.settings.get('maintenance') and not db.is_admin(user_id):
        await update.message.reply_text(
            "🔧 البوت تحت الصيانة حاليًا.\n"
            "يرجى المحاولة مرة أخرى لاحقًا."
        )
        return
    
    # التحقق من الاشتراك الإجباري
    if not await check_subscription(user_id, context):
        channels_text = "\n".join([f"• {ch['name']}" for ch in db.channels.values()])
        keyboard = [[InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_subscription")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📢 يجب الاشتراك في القنوات التالية لاستخدام البوت:\n\n"
            f"{channels_text}\n\n"
            "بعد الاشتراك، اضغط على الزر أدناه:",
            reply_markup=reply_markup
        )
        return
    
    # معالجة رابط الدعوة
    if context.args:
        try:
            inviter_id = int(context.args[0])
            if inviter_id != user_id and str(inviter_id) in db.users:
                db_user = db.get_user(user_id)
                if not db_user.get('invited_by'):
                    db.update_user(user_id, {'invited_by': inviter_id})
                    inviter = db.get_user(inviter_id)
                    inviter['invited_users'].append(user_id)
                    db.update_user(inviter_id, inviter)
                    
                    # منح النقاط للمدعو
                    if db.settings.get('invite_active'):
                        reward = db.settings.get('invite_reward', 100)
                        db.update_user(inviter_id, {
                            'points': inviter['points'] + reward
                        })
                        
                        await context.bot.send_message(
                            inviter_id,
                            f"🎉 حصلت على {reward} نقطة!\n"
                            f"المستخدم {user.first_name} انضم عبر رابط دعوتك!"
                        )
        except:
            pass
    
    # إشعار المدير
    if db.settings.get('notifications'):
        await send_notification_to_admin(
            f"👤 مستخدم جديد!\n"
            f"🆔: {user_id}\n"
            f"👤: {user.first_name}\n"
            f"📅: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            context
        )
    
    # عرض لوحة التحكم للمديرين
    if db.is_admin(user_id):
        keyboard = [
            [KeyboardButton("📊 لوحة التحكم"), KeyboardButton("👤 حسابي")],
            [KeyboardButton("🛒 الخدمات"), KeyboardButton("🎁 هدية اليومية")],
            [KeyboardButton("👥 دعوة صديق"), KeyboardButton("💸 تمويل قناتي")],
            [KeyboardButton("💳 شحن الرصيد"), KeyboardButton("📞 الدعم الفني")],
            [KeyboardButton("📋 تمويلاتي"), KeyboardButton("📦 طلباتي")]
        ]
    else:
        keyboard = [
            [KeyboardButton("👤 حسابي"), KeyboardButton("🛒 الخدمات")],
            [KeyboardButton("🎁 هدية اليومية"), KeyboardButton("👥 دعوة صديق")],
            [KeyboardButton("💸 تمويل قناتي"), KeyboardButton("💳 شحن الرصيد")],
            [KeyboardButton("📞 الدعم الفني"), KeyboardButton("📋 تمويلاتي")],
            [KeyboardButton("📦 طلباتي")]
        ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    welcome_msg = db.settings.get('welcome_message', 
        "مرحباً بك في بوت طاش للخدمات الإلكترونية!\n\n"
        "✨ اختر من القائمة أدناه:")
    
    await update.message.reply_text(welcome_msg, reply_markup=reply_markup)

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل النصية"""
    user_id = update.effective_user.id
    text = update.message.text
    
    # التحقق من الحظر
    user_data = db.get_user(user_id)
    if user_data.get('banned'):
        return
    
    # التحقق من الصيانة
    if db.settings.get('maintenance') and not db.is_admin(user_id):
        await update.message.reply_text("🔧 البوت تحت الصيانة حالياً.")
        return
    
    # التحقق من الاشتراك
    if not await check_subscription(user_id, context):
        await update.message.reply_text("يرجى الاشتراك في القنوات أولاً.")
        return
    
    # حالة المستخدم النشطة
    if 'user_state' not in context.user_data:
        context.user_data['user_state'] = {}
    
    # معالجة حالات خاصة
    state = context.user_data['user_state'].get(user_id, {})
    
    if state.get('type') == 'waiting_code':
        await handle_code_usage(update, context, text)
    elif state.get('type') == 'funding_members':
        await handle_funding_members(update, context, text, state)
    elif state.get('type') == 'funding_channel':
        await handle_funding_channel(update, context, text, state)
    else:
        # معالجة الأزرار الرئيسية
        if text == "👤 حسابي":
            await show_profile(update, context)
        elif text == "📊 لوحة التحكم" and db.is_admin(user_id):
            await admin_panel(update, context)
        elif text == "🛒 الخدمات":
            await show_services(update, context)
        elif text == "🎁 هدية اليومية":
            await daily_gift(update, context)
        elif text == "👥 دعوة صديق":
            await invite_friends(update, context)
        elif text == "💸 تمويل قناتي":
            await start_channel_funding(update, context)
        elif text == "💳 شحن الرصيد":
            await charge_points(update, context)
        elif text == "📞 الدعم الفني":
            await support(update, context)
        elif text == "📋 تمويلاتي":
            await my_funding(update, context)
        elif text == "📦 طلباتي":
            await my_orders(update, context)
        else:
            # البحث عن أزرار مخصصة
            for btn_id, btn_data in db.buttons.items():
                if btn_data.get('text') == text:
                    if btn_data.get('type') == 'url':
                        keyboard = [[InlineKeyboardButton("فتح الرابط", url=btn_data['content'])]]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        await update.message.reply_text(
                            f"🔗 {btn_data.get('description', 'اضغط لفتح الرابط')}",
                            reply_markup=reply_markup
                        )
                    elif btn_data.get('type') == 'text':
                        await update.message.reply_text(btn_data['content'])
                    return

# ========== أوامر المستخدم ==========
async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض ملف المستخدم"""
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    profile_text = f"""
👤 <b>الملف الشخصي</b>

🆔 المعرف: <code>{user_id}</code>
📛 الاسم: {user_data['first_name']}
📅 تاريخ الانضمام: {user_data['join_date'][:10]}
📊 النقاط: {user_data['points']} 💎

📈 <b>الإحصائيات:</b>
   📦 عدد الطلبات: {user_data['total_orders']}
   💰 إجمالي المشتريات: {user_data['total_spent']} نقطة
   👥 عدد المدعوين: {len(user_data['invited_users'])}
   
🔗 <b>رابط الدعوة:</b>
<code>https://t.me/{(await context.bot.get_me()).username}?start={user_id}</code>

🎯 <b>معلومات الإحالة:</b>
   🎁 لكل صديق: {db.settings.get('invite_reward', 100)} نقطة
   📊 إجمالي الأرباح: {len(user_data['invited_users']) * db.settings.get('invite_reward', 100)} نقطة
"""
    
    # إضافة معلومات المدير إذا كان
    if db.is_admin(user_id):
        admin_level = db.get_admin_level(user_id)
        profile_text += f"\n👑 <b>صلاحية المدير:</b> المستوى {admin_level}"
    
    await update.message.reply_text(profile_text, parse_mode=ParseMode.HTML)

async def show_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الخدمات المتاحة"""
    if not db.categories:
        await update.message.reply_text("⚠️ لا توجد خدمات متاحة حالياً.")
        return
    
    keyboard = []
    for cat_id, category in db.categories.items():
        keyboard.append([
            InlineKeyboardButton(
                f"📂 {category['name']} ({len(category.get('services', {}))})",
                callback_data=f"cat_{cat_id}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("📦 طلباتي", callback_data="my_orders_btn")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🛒 <b>خدمات SMM المتاحة</b>\n\n"
        "اختر القسم المناسب:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )

async def daily_gift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الهدية اليومية"""
    if not db.settings.get('daily_active', True):
        await update.message.reply_text("🎁 الهدية اليومية معطلة حالياً.")
        return
    
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    today = datetime.now().date().isoformat()
    
    if user_data.get('daily_date') == today:
        await update.message.reply_text("🎁 لقد استلمت هدية اليوم بالفعل!\nعد غداً للحصول على هدية جديدة.")
        return
    
    reward = db.settings.get('daily_reward', 50)
    new_points = user_data['points'] + reward
    
    db.update_user(user_id, {
        "points": new_points,
        "daily_date": today
    })
    
    await update.message.reply_text(
        f"🎉 <b>مبروك! لقد حصلت على هدية اليوم!</b>\n\n"
        f"🎁 المكافأة: {reward} نقطة\n"
        f"💰 رصيدك الجديد: {new_points} نقطة\n\n"
        f"عد غداً للحصول على هدية جديدة!",
        parse_mode=ParseMode.HTML
    )
    
    # إشعار للمدير
    if db.settings.get('notifications'):
        await notify_admins(
            f"🎁 المستخدم {user_id} استلم الهدية اليومية\n"
            f"المكافأة: {reward} نقطة",
            context
        )

async def invite_friends(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دعوة الأصدقاء"""
    if not db.settings.get('invite_active', True):
        await update.message.reply_text("👥 نظام الدعوة معطل حالياً.")
        return
    
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    reward = db.settings.get('invite_reward', 100)
    invite_link = f"https://t.me/{(await context.bot.get_me()).username}?start={user_id}"
    
    invited_count = len(user_data.get('invited_users', []))
    total_earned = invited_count * reward
    
    text = f"""
👥 <b>دعوة الأصدقاء</b>

🎁 <b>مكافأة الدعوة:</b>
   لكل صديق تدعوه: {reward} نقطة
   
📊 <b>إحصائياتك:</b>
   👥 عدد المدعوين: {invited_count}
   💰 إجمالي الأرباح: {total_earned} نقطة
   
🔗 <b>رابط الدعوة الخاص بك:</b>
<code>{invite_link}</code>

📝 <b>طريقة الاستخدام:</b>
1. أرسل الرابط لصديقك
2. يجب أن ينضم صديقك عبر الرابط
3. تحصل على {reward} نقطة تلقائياً
"""
    
    keyboard = [[InlineKeyboardButton("📤 مشاركة الرابط", url=f"tg://msg_url?url={invite_link}&text=انضم%20للبوت%20للحصول%20على%20خدمات%20SMM%20رائعة!")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def start_channel_funding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء تمويل القناة"""
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    rate = db.settings.get('channel_funding_rate', 5)
    
    text = f"""
💸 <b>تمويل قناتي</b>

📊 <b>معلومات الخدمة:</b>
   لكل عضو: {rate} نقطة
   الحد الأدنى: 10 أعضاء
   الحد الأقصى: 1000 عضو
   
💰 <b>مثال:</b>
   100 عضو = {100 * rate} نقطة
   
📝 <b>شروط الخدمة:</b>
1. يجب أن يكون البوت مشرفاً في القناة
2. القناة يجب أن تكون عامة
3. لا يمكن إلغاء الطلب بعد التأكيد
   
⚡ <b>لبدء الطلب:</b>
أرسل عدد الأعضاء المطلوبين (مثال: 100)
"""
    
    context.user_data['user_state'][user_id] = {'type': 'funding_members'}
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def handle_funding_members(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, state: dict):
    """معالجة عدد أعضاء التمويل"""
    try:
        members_count = int(text)
        if members_count < 10:
            await update.message.reply_text("❌ الحد الأدنى هو 10 أعضاء")
            return
        if members_count > 1000:
            await update.message.reply_text("❌ الحد الأقصى هو 1000 عضو")
            return
        
        user_id = update.effective_user.id
        rate = db.settings.get('channel_funding_rate', 5)
        total_cost = members_count * rate
        
        user_data = db.get_user(user_id)
        if user_data['points'] < total_cost:
            await update.message.reply_text(
                f"❌ نقاطك غير كافية!\n"
                f"💎 النقاط المطلوبة: {total_cost}\n"
                f"💰 رصيدك الحالي: {user_data['points']}"
            )
            return
        
        # حفظ عدد الأعضاء والمبلغ
        state['members_count'] = members_count
        state['total_cost'] = total_cost
        context.user_data['user_state'][user_id] = state
        
        # طلب رابط القناة
        await update.message.reply_text(
            f"✅ تم تحديد {members_count} عضو\n"
            f"💰 التكلفة الإجمالية: {total_cost} نقطة\n\n"
            "📢 الآن أرسل رابط القناة (يجب أن يكون البوت مشرفاً فيها):"
        )
        
        # تغيير حالة المستخدم
        context.user_data['user_state'][user_id]['type'] = 'funding_channel'
        
    except ValueError:
        await update.message.reply_text("❌ رجاءً أرسل رقم صحيح (مثال: 100)")

async def handle_funding_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, state: dict):
    """معالجة رابط قناة التمويل"""
    user_id = update.effective_user.id
    
    try:
        # استخراج معرف القناة من الرابط
        channel_link = text.strip()
        if 't.me/' in channel_link:
            channel_username = channel_link.split('t.me/')[-1].replace('@', '')
        elif channel_link.startswith('@'):
            channel_username = channel_link[1:]
        else:
            channel_username = channel_link
        
        # محاولة الحصول على معلومات القناة
        try:
            chat = await context.bot.get_chat(f"@{channel_username}")
            channel_id = chat.id
            
            # التحقق من إدارة البوت للقناة
            try:
                bot_member = await context.bot.get_chat_member(channel_id, context.bot.id)
                if bot_member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                    await update.message.reply_text(
                        "❌ يجب أن أكون مشرفاً في القناة!\n"
                        "أضفني كمسؤول ثم حاول مرة أخرى."
                    )
                    return
            except:
                await update.message.reply_text(
                    "❌ يجب أن أكون مشرفاً في القناة!\n"
                    "أضفني كمسؤول ثم حاول مرة أخرى."
                )
                return
            
            # خصم النقاط
            user_data = db.get_user(user_id)
            total_cost = state['total_cost']
            
            if user_data['points'] < total_cost:
                await update.message.reply_text("❌ نقاطك غير كافية!")
                return
            
            # تحديث نقاط المستخدم
            db.update_user(user_id, {
                'points': user_data['points'] - total_cost
            })
            
            # إنشاء طلب التمويل
            funding_id = generate_code(6)
            funding_data = {
                'id': funding_id,
                'user_id': user_id,
                'channel_id': channel_id,
                'channel_username': channel_username,
                'channel_name': chat.title,
                'members_count': state['members_count'],
                'rate': db.settings.get('channel_funding_rate', 5),
                'total_cost': total_cost,
                'status': 'active',
                'current_members': 0,
                'remaining': state['members_count'],
                'start_date': datetime.now().isoformat(),
                'completed_date': None,
                'subscribers': []
            }
            
            db.funding[funding_id] = funding_data
            db.save_data('funding')
            
            # إضافة للقائمة الشخصية
            user_data['funding_requests'].append(funding_id)
            db.update_user(user_id, user_data)
            
            # إشعار المدير
            await notify_admins(
                f"💸 <b>طلب تمويل جديد</b>\n\n"
                f"👤 المستخدم: {user_data['first_name']} (ID: {user_id})\n"
                f"📢 القناة: {chat.title}\n"
                f"👥 العدد المطلوب: {state['members_count']}\n"
                f"💰 التكلفة: {total_cost} نقطة\n"
                f"🆔 رقم الطلب: {funding_id}",
                context
            )
            
            # رسالة تأكيد للمستخدم
            keyboard = [[InlineKeyboardButton("📋 الانتقال إلى تمويلاتي", callback_data="my_funding_btn")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✅ <b>تم إنشاء طلب التمويل بنجاح!</b>\n\n"
                f"🆔 رقم الطلب: <code>{funding_id}</code>\n"
                f"📢 القناة: {chat.title}\n"
                f"👥 العدد المطلوب: {state['members_count']} عضو\n"
                f"💰 التكلفة: {total_cost} نقطة\n\n"
                f"📊 سيبدأ تجميع الأعضاء تلقائياً.\n"
                f"📨 ستستلم إشعاراً بكل عضو جديد.",
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
            
            # مسح حالة المستخدم
            if user_id in context.user_data['user_state']:
                del context.user_data['user_state'][user_id]
                
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ في الحصول على معلومات القناة: {str(e)}")
            
    except Exception as e:
        await update.message.reply_text("❌ رابط غير صحيح!")

async def my_funding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض تمويلاتي"""
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    if not user_data.get('funding_requests'):
        await update.message.reply_text("📭 لا توجد طلبات تمويل حالياً.")
        return
    
    text = "📋 <b>طلبات التمويل الخاصة بي</b>\n\n"
    keyboard = []
    
    for funding_id in user_data['funding_requests'][-10:]:  # آخر 10 طلبات
        if funding_id in db.funding:
            funding = db.funding[funding_id]
            
            status_icon = "🟢" if funding['status'] == 'active' else "🔴" if funding['status'] == 'completed' else "🟡"
            progress = ((funding['current_members'] / funding['members_count']) * 100) if funding['members_count'] > 0 else 0
            
            text += f"{status_icon} <b>{funding['channel_name']}</b>\n"
            text += f"   🆔: <code>{funding_id}</code>\n"
            text += f"   👥: {funding['current_members']}/{funding['members_count']}\n"
            text += f"   📊: {progress:.1f}%\n"
            text += f"   📅: {funding['start_date'][:10]}\n"
            text += f"   🔄: {funding['remaining']} باقي\n\n"
            
            keyboard.append([InlineKeyboardButton(
                f"📊 {funding['channel_name']} - {funding['current_members']}/{funding['members_count']}",
                callback_data=f"funding_details_{funding_id}"
            )])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def charge_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شحن النقاط"""
    keyboard = [
        [InlineKeyboardButton("🎫 استخدام كود شحن", callback_data="use_code")],
        [InlineKeyboardButton("👑 طلب شحن من المدير", callback_data="request_charge")],
        [InlineKeyboardButton("💳 طرق الدفع الأخرى", url=f"tg://user?id={ADMIN_ID}")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "💳 <b>شحن الرصيد</b>\n\n"
        "اختر طريقة الشحن المناسبة:\n\n"
        "1. 🎫 <b>كود شحن:</b> أدخل كود شحن صالح\n"
        "2. 👑 <b>طلب من المدير:</b> لشحن كميات كبيرة\n"
        "3. 💳 <b>طرق أخرى:</b> تواصل مع الدعم\n\n"
        "📞 للاستفسارات: @Flashback70bot",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )

async def handle_code_usage(update: Update, context: ContextTypes.DEFAULT_TYPE, code_text: str):
    """معالجة استخدام كود الشحن"""
    user_id = update.effective_user.id
    code = code_text.upper().strip()
    
    if code in db.codes:
        code_data = db.codes[code]
        
        if code_data.get('used_count', 0) >= code_data.get('max_uses', 1):
            await update.message.reply_text("❌ هذا الكود قد استخدم بالفعل!")
            return
        
        if datetime.fromisoformat(code_data['expiry_date']) < datetime.now():
            await update.message.reply_text("❌ هذا الكود منتهي الصلاحية!")
            return
        
        # إضافة النقاط للمستخدم
        points = code_data['points']
        user_data = db.get_user(user_id)
        new_points = user_data['points'] + points
        
        db.update_user(user_id, {'points': new_points})
        
        # تحديث استخدام الكود
        if 'used_by' not in code_data:
            code_data['used_by'] = []
        
        code_data['used_by'].append({
            'user_id': user_id,
            'username': update.effective_user.username,
            'date': datetime.now().isoformat()
        })
        code_data['used_count'] = code_data.get('used_count', 0) + 1
        
        db.codes[code] = code_data
        db.save_data('codes')
        
        # إشعار المدير
        await notify_admins(
            f"🎫 <b>تم استخدام كود الشحن</b>\n\n"
            f"🆔 الكود: {code}\n"
            f"👤 المستخدم: {user_data['first_name']} (ID: {user_id})\n"
            f"💰 النقاط: {points}\n"
            f"📊 الاستخدامات: {code_data['used_count']}/{code_data['max_uses']}",
            context
        )
        
        await update.message.reply_text(
            f"✅ <b>تم شحن رصيدك بنجاح!</b>\n\n"
            f"🎫 الكود: {code}\n"
            f"💰 النقاط المضافة: {points}\n"
            f"💎 رصيدك الجديد: {new_points} نقطة",
            parse_mode=ParseMode.HTML
        )
        
        # مسح حالة المستخدم
        if user_id in context.user_data.get('user_state', {}):
            del context.user_data['user_state'][user_id]
            
    else:
        await update.message.reply_text("❌ الكود غير صحيح أو غير موجود!")

async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الدعم الفني"""
    support_user = db.settings.get('support_user', '@Flashback70bot')
    bot_channel = db.settings.get('bot_channel', '@Flashback70bot')
    
    keyboard = [
        [InlineKeyboardButton("📢 قناة البوت", url=bot_channel)],
        [InlineKeyboardButton("💬 تواصل مع الدعم", url=f"tg://user?id={ADMIN_ID}")]
    ]
    
    # إضافة الأزرار المخصصة
    custom_buttons = []
    for btn_id, btn_data in db.buttons.items():
        if btn_data.get('position') == 'support':
            if btn_data['type'] == 'url':
                custom_buttons.append([InlineKeyboardButton(btn_data['text'], url=btn_data['content'])])
            elif btn_data['type'] == 'text':
                custom_buttons.append([InlineKeyboardButton(btn_data['text'], callback_data=f"btn_{btn_id}")])
    
    if custom_buttons:
        keyboard.extend(custom_buttons)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""
📞 <b>الدعم الفني</b>

🔗 <b>روابط التواصل:</b>
   📢 القناة: {bot_channel}
   👤 الدعم: {support_user}

⏰ <b>أوقات الدعم:</b>
   24/7 على مدار الساعة

📝 <b>للتقديم على شغل:</b>
   @Flashback70bot

⚡ <b>للإعلان:</b>
   @Flashback70bot
"""
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض طلباتي"""
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    pending_orders = user_data.get('pending_orders', [])
    completed_orders = user_data.get('completed_orders', [])
    
    if not pending_orders and not completed_orders:
        await update.message.reply_text("📭 لا توجد طلبات حالياً.")
        return
    
    text = "📦 <b>طلباتي</b>\n\n"
    
    if pending_orders:
        text += "⏳ <b>الطلبات المعلقة:</b>\n"
        for order_id in pending_orders[-5:]:
            if order_id in db.orders:
                order = db.orders[order_id]
                text += f"   📌 {order['service_name']}\n"
                text += f"   🆔: <code>{order_id}</code>\n"
                text += f"   📅: {order['date'][:10]}\n"
                text += f"   💰: {order['total_price']} نقطة\n\n"
    
    if completed_orders:
        text += "✅ <b>الطلبات المكتملة:</b>\n"
        for order_id in completed_orders[-5:]:
            if order_id in db.orders:
                order = db.orders[order_id]
                text += f"   ✓ {order['service_name']}\n"
                text += f"   🆔: <code>{order_id}</code>\n"
                text += f"   📅: {order['date'][:10]}\n"
                text += f"   💰: {order['total_price']} نقطة\n\n"
    
    keyboard = [[InlineKeyboardButton("🛒 طلب جديد", callback_data="back_to_services")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

# ========== لوحة التحكم للمدير ==========
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لوحة تحكم المدير"""
    user_id = update.effective_user.id
    admin_level = db.get_admin_level(user_id)
    
    keyboard = []
    
    # مستوى 1: صلاحيات أساسية
    if admin_level >= 1:
        keyboard.extend([
            [InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
            [InlineKeyboardButton("👥 إدارة المستخدمين", callback_data="admin_users")],
            [InlineKeyboardButton("📦 إدارة الطلبات", callback_data="admin_orders")],
            [InlineKeyboardButton("🎫 أكواد الشحن", callback_data="admin_codes")]
        ])
    
    # مستوى 2: صلاحيات متوسطة
    if admin_level >= 2:
        keyboard.extend([
            [InlineKeyboardButton("🛒 إدارة الخدمات", callback_data="admin_services")],
            [InlineKeyboardButton("📢 إدارة القنوات", callback_data="admin_channels")],
            [InlineKeyboardButton("💸 إدارة التمويلات", callback_data="admin_funding")],
            [InlineKeyboardButton("⚙️ الإعدادات العامة", callback_data="admin_settings")]
        ])
    
    # مستوى 3: صلاحيات كاملة
    if admin_level >= 3:
        keyboard.extend([
            [InlineKeyboardButton("👑 إدارة المديرين", callback_data="admin_admins")],
            [InlineKeyboardButton("🔧 إدارة الأزرار", callback_data="admin_buttons")],
            [InlineKeyboardButton("📨 الإذاعة", callback_data="admin_broadcast")],
            [InlineKeyboardButton("🚫 الصيانة والإغلاق", callback_data="admin_maintenance")]
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="back_to_main")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    level_text = {1: "أساسي", 2: "متوسط", 3: "كامل"}
    
    await update.message.reply_text(
        f"🛠️ <b>لوحة تحكم المدير</b>\n\n"
        f"👤 المستخدم: {update.effective_user.first_name}\n"
        f"👑 المستوى: {level_text.get(admin_level, 'غير معروف')}\n\n"
        f"اختر القسم الذي تريد إدارته:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )

async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة ردود لوحة التحكم"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    await query.answer()
    
    # التحقق من صلاحية المدير
    if not db.is_admin(user_id):
        await query.message.reply_text("❌ هذا القسم للمديرين فقط!")
        return
    
    admin_level = db.get_admin_level(user_id)
    
    # فروع الأوامر الإدارية
    if data == "admin_stats":
        await admin_stats_panel(query, context)
    elif data == "admin_users":
        await admin_users_panel(query, context)
    elif data == "admin_services":
        await admin_services_panel(query, context)
    elif data == "admin_codes":
        await admin_codes_panel(query, context)
    elif data == "admin_orders":
        await admin_orders_panel(query, context)
    elif data == "admin_channels":
        await admin_channels_panel(query, context)
    elif data == "admin_funding":
        await admin_funding_panel(query, context)
    elif data == "admin_settings":
        await admin_settings_panel(query, context)
    elif data == "admin_admins" and admin_level >= 3:
        await admin_admins_panel(query, context)
    elif data == "admin_buttons" and admin_level >= 3:
        await admin_buttons_panel(query, context)
    elif data == "admin_broadcast" and admin_level >= 3:
        await admin_broadcast_panel(query, context)
    elif data == "admin_maintenance" and admin_level >= 3:
        await admin_maintenance_panel(query, context)
    elif data == "back_to_main":
        await start(update, context)
    elif data.startswith("cat_"):
        await show_category_services(query, context, data.split("_")[1])
    elif data.startswith("service_"):
        await show_service_details(query, context, data.split("_")[1])
    elif data == "use_code":
        await use_code_start(query, context)
    elif data == "my_funding_btn":
        await my_funding(update, context)
    elif data == "my_orders_btn":
        await my_orders(update, context)
    elif data.startswith("funding_details_"):
        await show_funding_details(query, context, data.split("_")[2])

async def admin_stats_panel(query, context):
    """إحصائيات البوت"""
    total_users = len(db.users)
    active_today = len([u for u in db.users.values() 
                       if datetime.fromisoformat(u.get('last_active', '2000-01-01')).date() == datetime.now().date()])
    total_points = sum(u['points'] for u in db.users.values())
    total_orders = sum(u['total_orders'] for u in db.users.values())
    total_spent = sum(u['total_spent'] for u in db.users.values())
    
    # المستخدمين النشطين هذا الأسبوع
    week_ago = datetime.now() - timedelta(days=7)
    active_week = len([u for u in db.users.values() 
                      if datetime.fromisoformat(u.get('last_active', '2000-01-01')) >= week_ago])
    
    # الطلبات اليومية
    today_orders = 0
    for order in db.orders.values():
        if datetime.fromisoformat(order['date']).date() == datetime.now().date():
            today_orders += 1
    
    text = f"""
📊 <b>إحصائيات البوت</b>

👥 <b>المستخدمين:</b>
   إجمالي المستخدمين: {total_users}
   النشطين اليوم: {active_today}
   النشطين هذا الأسبوع: {active_week}

💰 <b>المالية:</b>
   إجمالي النقاط: {total_points:,}
   إجمالي الصرف: {total_spent:,} نقطة

📦 <b>الطلبات:</b>
   إجمالي الطلبات: {total_orders}
   طلبات اليوم: {today_orders}

🛒 <b>الخدمات:</b>
   الأقسام: {len(db.categories)}
   الخدمات: {sum(len(cat.get('services', {})) for cat in db.categories.values())}

💸 <b>التمويلات:</b>
   النشطة: {len([f for f in db.funding.values() if f['status'] == 'active'])}
   المكتملة: {len([f for f in db.funding.values() if f['status'] == 'completed'])}
"""
    
    keyboard = [
        [InlineKeyboardButton("🔄 تحديث", callback_data="admin_stats")],
        [InlineKeyboardButton("📈 تفاصيل أكثر", callback_data="admin_stats_detailed")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def admin_users_panel(query, context):
    """إدارة المستخدمين"""
    keyboard = [
        [InlineKeyboardButton("🔍 بحث عن مستخدم", callback_data="admin_search_user")],
        [InlineKeyboardButton("📋 قائمة المستخدمين", callback_data="admin_list_users")],
        [InlineKeyboardButton("🚫 حظر مستخدم", callback_data="admin_ban_user")],
        [InlineKeyboardButton("✅ فك حظر مستخدم", callback_data="admin_unban_user")],
        [InlineKeyboardButton("💰 شحن رصيد مستخدم", callback_data="admin_charge_user")],
        [InlineKeyboardButton("📨 إرسال رسالة", callback_data="admin_message_user")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "👥 <b>إدارة المستخدمين</b>\n\n"
        "اختر الإجراء المناسب:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )

async def admin_services_panel(query, context):
    """إدارة الخدمات"""
    keyboard = [
        [InlineKeyboardButton("📂 إضافة قسم", callback_data="admin_add_category")],
        [InlineKeyboardButton("✏️ تعديل قسم", callback_data="admin_edit_category")],
        [InlineKeyboardButton("🗑️ حذف قسم", callback_data="admin_delete_category")],
        [InlineKeyboardButton("➕ إضافة خدمة", callback_data="admin_add_service")],
        [InlineKeyboardButton("📝 تعديل خدمة", callback_data="admin_edit_service")],
        [InlineKeyboardButton("❌ حذف خدمة", callback_data="admin_delete_service")],
        [InlineKeyboardButton("📋 عرض جميع الخدمات", callback_data="admin_list_services")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🛒 <b>إدارة الخدمات</b>\n\n"
        "اختر الإجراء المناسب:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )

async def admin_codes_panel(query, context):
    """إدارة أكواد الشحن"""
    total_codes = len(db.codes)
    active_codes = len([c for c in db.codes.values() 
                       if datetime.fromisoformat(c.get('expiry_date', '2000-01-01')) > datetime.now()])
    used_codes = len([c for c in db.codes.values() if c.get('used_count', 0) > 0])
    total_points = sum(c.get('points', 0) for c in db.codes.values())
    
    keyboard = [
        [InlineKeyboardButton("🎫 إنشاء كود جديد", callback_data="admin_create_code")],
        [InlineKeyboardButton("📋 قائمة الأكواد", callback_data="admin_list_codes")],
        [InlineKeyboardButton("🗑️ حذف كود", callback_data="admin_delete_code")],
        [InlineKeyboardButton("📊 إحصائيات الأكواد", callback_data="admin_codes_stats")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""
🎫 <b>إدارة أكواد الشحن</b>

📊 <b>الإحصائيات:</b>
   إجمالي الأكواد: {total_codes}
   الأكواد النشطة: {active_codes}
   الأكواد المستخدمة: {used_codes}
   إجمالي النقاط: {total_points:,}

📝 <b>خيارات الإدارة:</b>
"""
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def admin_orders_panel(query, context):
    """إدارة الطلبات"""
    total_orders = len(db.orders)
    pending_orders = len([o for o in db.orders.values() if o.get('status') == 'pending'])
    completed_orders = len([o for o in db.orders.values() if o.get('status') == 'completed'])
    cancelled_orders = len([o for o in db.orders.values() if o.get('status') == 'cancelled'])
    
    today_income = 0
    for order in db.orders.values():
        if datetime.fromisoformat(order['date']).date() == datetime.now().date() and order.get('status') == 'completed':
            today_income += order.get('total_price', 0)
    
    keyboard = [
        [InlineKeyboardButton("📋 الطلبات المعلقة", callback_data="admin_pending_orders")],
        [InlineKeyboardButton("✅ الطلبات المكتملة", callback_data="admin_completed_orders")],
        [InlineKeyboardButton("❌ الطلبات الملغاة", callback_data="admin_cancelled_orders")],
        [InlineKeyboardButton("📊 إحصائيات الطلبات", callback_data="admin_orders_stats")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""
📦 <b>إدارة الطلبات</b>

📊 <b>الإحصائيات:</b>
   إجمالي الطلبات: {total_orders}
   المعلقة: {pending_orders}
   المكتملة: {completed_orders}
   الملغاة: {cancelled_orders}
   
💰 <b>المبيعات اليوم:</b>
   {today_income:,} نقطة
"""
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def admin_channels_panel(query, context):
    """إدارة القنوات"""
    total_channels = len(db.channels)
    
    keyboard = [
        [InlineKeyboardButton("➕ إضافة قناة", callback_data="admin_add_channel")],
        [InlineKeyboardButton("🗑️ حذف قناة", callback_data="admin_delete_channel")],
        [InlineKeyboardButton("📋 قائمة القنوات", callback_data="admin_list_channels")],
        [InlineKeyboardButton("🔧 تعديل قناة", callback_data="admin_edit_channel")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""
📢 <b>إدارة القنوات</b>

📊 <b>الإحصائيات:</b>
   عدد القنوات: {total_channels}
   
📝 <b>ملاحظات:</b>
   • القنوات المضافة تكون إجبارية للمستخدمين
   • يجب أن يكون البوت مشرفاً في القناة
   • يمكن إضافة قنوات متعددة
"""
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def admin_funding_panel(query, context):
    """إدارة التمويلات"""
    active_funding = len([f for f in db.funding.values() if f['status'] == 'active'])
    completed_funding = len([f for f in db.funding.values() if f['status'] == 'completed'])
    cancelled_funding = len([f for f in db.funding.values() if f['status'] == 'cancelled'])
    
    total_members = sum(f['members_count'] for f in db.funding.values())
    completed_members = sum(f['current_members'] for f in db.funding.values() if f['status'] == 'completed')
    
    keyboard = [
        [InlineKeyboardButton("📋 التمويلات النشطة", callback_data="admin_active_funding")],
        [InlineKeyboardButton("✅ التمويلات المكتملة", callback_data="admin_completed_funding")],
        [InlineKeyboardButton("❌ إلغاء تمويل", callback_data="admin_cancel_funding")],
        [InlineKeyboardButton("📊 إحصائيات التمويل", callback_data="admin_funding_stats")],
        [InlineKeyboardButton("⚙️ إعدادات التمويل", callback_data="admin_funding_settings")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""
💸 <b>إدارة التمويلات</b>

📊 <b>الإحصائيات:</b>
   النشطة: {active_funding}
   المكتملة: {completed_funding}
   الملغاة: {cancelled_funding}
   
👥 <b>الأعضاء:</b>
   المطلوبين: {total_members:,}
   المتحققين: {completed_members:,}
   
💰 <b>السعر الحالي:</b>
   {db.settings.get('channel_funding_rate', 5)} نقطة لكل عضو
"""
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def admin_settings_panel(query, context):
    """الإعدادات العامة"""
    keyboard = [
        [InlineKeyboardButton("🎁 إعدادات الهدايا", callback_data="admin_gift_settings")],
        [InlineKeyboardButton("👥 إعدادات الدعوة", callback_data="admin_invite_settings")],
        [InlineKeyboardButton("💸 سعر التمويل", callback_data="admin_funding_price")],
        [InlineKeyboardButton("📞 بيانات التواصل", callback_data="admin_contact_info")],
        [InlineKeyboardButton("💬 رسالة الترحيب", callback_data="admin_welcome_msg")],
        [InlineKeyboardButton("🔔 الإشعارات", callback_data="admin_notifications")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = """
⚙️ <b>الإعدادات العامة</b>

📝 <b>الإعدادات الحالية:</b>
   • الهدية اليومية: {} نقطة
   • مكافأة الدعوة: {} نقطة
   • سعر التمويل: {} نقطة/عضو
   • الإشعارات: {}
   
🔧 <b>خيارات التعديل:</b>
""".format(
        db.settings.get('daily_reward', 50),
        db.settings.get('invite_reward', 100),
        db.settings.get('channel_funding_rate', 5),
        "✅ مفعلة" if db.settings.get('notifications', True) else "❌ معطلة"
    )
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def admin_admins_panel(query, context):
    """إدارة المديرين"""
    total_admins = len(db.admins)
    level_1 = len([a for a in db.admins.values() if a['level'] == 1])
    level_2 = len([a for a in db.admins.values() if a['level'] == 2])
    level_3 = len([a for a in db.admins.values() if a['level'] == 3])
    
    keyboard = [
        [InlineKeyboardButton("👑 رفع مدير", callback_data="admin_promote_admin")],
        [InlineKeyboardButton("📋 قائمة المديرين", callback_data="admin_list_admins")],
        [InlineKeyboardButton("📊 صلاحيات المديرين", callback_data="admin_admin_permissions")],
        [InlineKeyboardButton("⬇️ خفض صلاحية", callback_data="admin_demote_admin")],
        [InlineKeyboardButton("🗑️ حذف مدير", callback_data="admin_remove_admin")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""
👑 <b>إدارة المديرين</b>

📊 <b>الإحصائيات:</b>
   إجمالي المديرين: {total_admins}
   المستوى 1: {level_1}
   المستوى 2: {level_2}
   المستوى 3: {level_3}
   
📝 <b>مستويات الصلاحيات:</b>
   • المستوى 1: صلاحيات أساسية
   • المستوى 2: صلاحيات متوسطة
   • المستوى 3: صلاحيات كاملة
"""
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def admin_buttons_panel(query, context):
    """إدارة الأزرار المخصصة"""
    total_buttons = len(db.buttons)
    url_buttons = len([b for b in db.buttons.values() if b['type'] == 'url'])
    text_buttons = len([b for b in db.buttons.values() if b['type'] == 'text'])
    
    keyboard = [
        [InlineKeyboardButton("➕ إضافة زر", callback_data="admin_add_button")],
        [InlineKeyboardButton("✏️ تعديل زر", callback_data="admin_edit_button")],
        [InlineKeyboardButton("🗑️ حذف زر", callback_data="admin_delete_button")],
        [InlineKeyboardButton("📋 قائمة الأزرار", callback_data="admin_list_buttons")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""
🔧 <b>إدارة الأزرار المخصصة</b>

📊 <b>الإحصائيات:</b>
   إجمالي الأزرار: {total_buttons}
   أزرار روابط: {url_buttons}
   أزرار نصوص: {text_buttons}
   
📍 <b>مواقع الأزرار:</b>
   • support: في صفحة الدعم
   • main: في الصفحة الرئيسية
   • other: مواقع أخرى
"""
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def admin_broadcast_panel(query, context):
    """الإذاعة للمستخدمين"""
    total_users = len(db.users)
    active_users = len([u for u in db.users.values() 
                       if datetime.fromisoformat(u.get('last_active', '2000-01-01')) > datetime.now() - timedelta(days=30)])
    
    keyboard = [
        [InlineKeyboardButton("📨 إذاعة نصية", callback_data="admin_text_broadcast")],
        [InlineKeyboardButton("🖼️ إذاعة مع صورة", callback_data="admin_photo_broadcast")],
        [InlineKeyboardButton("🎁 إذاعة مع نقاط", callback_data="admin_points_broadcast")],
        [InlineKeyboardButton("📊 إحصائيات الإذاعة", callback_data="admin_broadcast_stats")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""
📨 <b>نظام الإذاعة</b>

📊 <b>الإحصائيات:</b>
   إجمالي المستخدمين: {total_users}
   المستخدمين النشطين (30 يوم): {active_users}
   
💡 <b>أنواع الإذاعة:</b>
   • نصية: رسالة نصية فقط
   • مع صورة: نص مع صورة
   • مع نقاط: رسالة مع إضافة نقاط
"""
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def admin_maintenance_panel(query, context):
    """الصيانة والإغلاق"""
    maintenance_status = "✅ مفعل" if db.settings.get('maintenance', False) else "❌ معطل"
    
    keyboard = [
        [InlineKeyboardButton("🔧 تفعيل/تعطيل الصيانة", callback_data="admin_toggle_maintenance")],
        [InlineKeyboardButton("🚫 إغلاق البوت", callback_data="admin_shutdown")],
        [InlineKeyboardButton("🔄 إعادة تشغيل البوت", callback_data="admin_restart")],
        [InlineKeyboardButton("📊 حالة النظام", callback_data="admin_system_status")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""
🚫 <b>الصيانة والإغلاق</b>

📊 <b>حالة النظام:</b>
   الصيانة: {maintenance_status}
   الإشعارات: {"✅ مفعلة" if db.settings.get('notifications', True) else "❌ معطلة"}
   
⚠️ <b>تحذيرات:</b>
   • الإغلاق سيمنع جميع المستخدمين من استخدام البوت
   • الصيانة تمنع غير المديرين فقط
   • تأكد من حفظ البيانات قبل الإغلاق
"""
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def show_category_services(query, context, cat_id):
    """عرض خدمات قسم معين"""
    if cat_id not in db.categories:
        await query.answer("❌ القسم غير موجود!", show_alert=True)
        return
    
    category = db.categories[cat_id]
    services = category.get('services', {})
    
    if not services:
        await query.answer("⚠️ لا توجد خدمات في هذا القسم!", show_alert=True)
        return
    
    keyboard = []
    for service_id, service in services.items():
        keyboard.append([
            InlineKeyboardButton(
                f"{service['name']} - {service['price']} نقطة",
                callback_data=f"service_{service_id}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع للأقسام", callback_data="back_to_categories")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📂 <b>{category['name']}</b>\n\n"
        f"{category.get('description', '')}\n\n"
        f"اختر الخدمة المناسبة:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )

async def show_service_details(query, context, service_id):
    """عرض تفاصيل الخدمة"""
    service_data = None
    category_name = ""
    
    for cat_id, category in db.categories.items():
        if service_id in category.get('services', {}):
            service_data = category['services'][service_id]
            category_name = category['name']
            break
    
    if not service_data:
        await query.answer("❌ الخدمة غير موجودة!", show_alert=True)
        return
    
    user_id = query.from_user.id
    user_data = db.get_user(user_id)
    
    text = f"""
🛒 <b>تفاصيل الخدمة</b>

📦 <b>الخدمة:</b> {service_data['name']}
📂 <b>القسم:</b> {category_name}
💰 <b>السعر:</b> {service_data['price']} نقطة لكل 1000
⚡ <b>السرعة:</b> {service_data.get('speed', 'متوسطة')}
📊 <b>الحد الأدنى:</b> {service_data.get('min', 100):,}
📈 <b>الحد الأقصى:</b> {service_data.get('max', 10000):,}
⏰ <b>الوقت المتوقع:</b> {service_data.get('time', '24 ساعة')}
📝 <b>الوصف:</b>
{service_data.get('description', 'لا يوجد وصف')}

💎 <b>رصيدك:</b> {user_data['points']:,} نقطة
"""
    
    keyboard = [
        [InlineKeyboardButton("🛒 طلب الخدمة", callback_data=f"order_{service_id}")],
        [InlineKeyboardButton("🔙 رجوع للقسم", callback_data=f"cat_{list(db.categories.keys())[0]}")]
    ]
    
    if db.is_admin(user_id):
        keyboard.append([InlineKeyboardButton("✏️ تعديل الخدمة", callback_data=f"edit_service_{service_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def use_code_start(query, context):
    """بدء استخدام كود الشحن"""
    user_id = query.from_user.id
    context.user_data['user_state'] = {user_id: {'type': 'waiting_code'}}
    
    await query.message.reply_text(
        "🎫 <b>استخدام كود الشحن</b>\n\n"
        "أرسل الكود الذي تريد استخدامه:\n"
        "(يجب أن يكون الكود مكون من أحرف وأرقام)",
        parse_mode=ParseMode.HTML
    )

async def show_funding_details(query, context, funding_id):
    """عرض تفاصيل التمويل"""
    if funding_id not in db.funding:
        await query.answer("❌ طلب التمويل غير موجود!", show_alert=True)
        return
    
    funding = db.funding[funding_id]
    user_data = db.get_user(funding['user_id'])
    
    progress = ((funding['current_members'] / funding['members_count']) * 100) if funding['members_count'] > 0 else 0
    
    text = f"""
💸 <b>تفاصيل التمويل</b>

🆔 <b>رقم الطلب:</b> <code>{funding_id}</code>
👤 <b>المستخدم:</b> {user_data['first_name']} (ID: {funding['user_id']})
📢 <b>القناة:</b> {funding['channel_name']}
👥 <b>الأعضاء:</b> {funding['current_members']}/{funding['members_count']}
📊 <b>التقدم:</b> {progress:.1f}%
💰 <b>التكلفة:</b> {funding['total_cost']} نقطة
🎯 <b>المتبقي:</b> {funding['remaining']} عضو
📅 <b>تاريخ البدء:</b> {funding['start_date'][:10]}
🔧 <b>الحالة:</b> {funding['status']}
"""
    
    keyboard = []
    if db.is_admin(query.from_user.id):
        if funding['status'] == 'active':
            keyboard.append([InlineKeyboardButton("❌ إلغاء التمويل", callback_data=f"cancel_funding_{funding_id}")])
            keyboard.append([InlineKeyboardButton("✅ إكمال التمويل", callback_data=f"complete_funding_{funding_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="my_funding_btn")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

# ========== الدالة الرئيسية ==========
async def check_new_members(context: ContextTypes.DEFAULT_TYPE):
    """فحص الأعضاء الجدد في القنوات الممولة"""
    try:
        for funding_id, funding in db.funding.items():
            if funding['status'] == 'active' and funding['remaining'] > 0:
                try:
                    # الحصول على عدد أعضاء القناة الحالي
                    chat = await context.bot.get_chat(funding['channel_id'])
                    
                    # هذا مثال بسيط - في التطبيق الحقيقي تحتاج لطريقة أفضل لتتبع الأعضاء الجدد
                    # يمكن استخدام get_chat_members_count لكنه لا يعطي الأعضاء الجدد فقط
                    
                    # يمكنك تطوير هذا الجزء حسب احتياجاتك
                    pass
                    
                except Exception as e:
                    logger.error(f"Error checking channel {funding['channel_id']}: {e}")
    except Exception as e:
        logger.error(f"Error in check_new_members: {e}")

def main():
    """تشغيل البوت"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # إضافة المعالجات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))
    application.add_handler(CallbackQueryHandler(handle_admin_callback))
    
    # جدولة المهام
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(check_new_members, interval=300, first=10)  # كل 5 دقائق
    
    print("✅ البوت يعمل الآن...")
    print(f"👑 المدير الرئيسي: {ADMIN_ID}")
    print(f"🤖 يوزر البوت: {BOT_USERNAME}")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
