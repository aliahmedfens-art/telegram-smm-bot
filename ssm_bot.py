# -*- coding: utf-8 -*-
import os
import json
import logging
import random
import string
import asyncio
from datetime import datetime, timedelta
from io import BytesIO
from typing import Dict, List, Optional, Any
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import qrcode
from PIL import Image, ImageDraw, ImageFont
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, 
    ReplyKeyboardMarkup, KeyboardButton, ChatPermissions,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters,
    ConversationHandler
)
from telegram.constants import ParseMode, ChatMemberStatus
import emoji

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

# ========== حالات المحادثة ==========
WAITING_CODE, WAITING_SERVICE_QUANTITY, WAITING_FUNDING_MEMBERS, WAITING_FUNDING_CHANNEL, \
WAITING_CHARGE_AMOUNT, WAITING_TRANSFER_USER, WAITING_TRANSFER_AMOUNT = range(7)

# ========== قاعدة البيانات المحسنة ==========
class EnhancedDatabase:
    def __init__(self):
        self.data_dir = "data"
        self.data_files = {
            'users': f'{self.data_dir}/users.json',
            'services': f'{self.data_dir}/services.json',
            'categories': f'{self.data_dir}/categories.json',
            'orders': f'{self.data_dir}/orders.json',
            'codes': f'{self.data_dir}/codes.json',
            'channels': f'{self.data_dir}/channels.json',
            'settings': f'{self.data_dir}/settings.json',
            'funding': f'{self.data_dir}/funding.json',
            'subscriptions': f'{self.data_dir}/subscriptions.json',
            'admins': f'{self.data_dir}/admins.json',
            'buttons': f'{self.data_dir}/buttons.json',
            'transactions': f'{self.data_dir}/transactions.json'
        }
        self.ensure_data_dir()
        self.load_all_data()
    
    def ensure_data_dir(self):
        """تأكد من وجود مجلد البيانات"""
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        
        # إنشاء ملفات فارغة إذا لم تكن موجودة
        for file_path in self.data_files.values():
            if not os.path.exists(file_path):
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump({}, f, ensure_ascii=False, indent=2)
    
    def load_all_data(self):
        """تحميل جميع البيانات"""
        try:
            self.users = self.load_json('users')
            self.services = self.load_json('services')
            self.categories = self.load_json('categories')
            self.orders = self.load_json('orders')
            self.codes = self.load_json('codes')
            self.channels = self.load_json('channels')
            self.settings = self.load_json('settings')
            self.funding = self.load_json('funding')
            self.subscriptions = self.load_json('subscriptions')
            self.admins = self.load_json('admins')
            self.buttons = self.load_json('buttons')
            self.transactions = self.load_json('transactions')
            
            # تهيئة الإعدادات الافتراضية
            self.initialize_default_settings()
            
            # التأكد من وجود المدير الأساسي
            self.ensure_admin_exists()
            
            logger.info("✅ تم تحميل جميع البيانات بنجاح")
        except Exception as e:
            logger.error(f"❌ خطأ في تحميل البيانات: {e}")
            # إنشاء بيانات جديدة في حالة الخطأ
            self.initialize_empty_data()
    
    def load_json(self, key):
        """تحميل ملف JSON"""
        try:
            with open(self.data_files[key], 'r', encoding='utf-8') as f:
                data = json.load(f)
                # التأكد من أن البيانات هي dictionary
                if not isinstance(data, dict):
                    return {}
                return data
        except Exception as e:
            logger.error(f"❌ خطأ في تحميل {key}: {e}")
            return {}
    
    def save_json(self, key, data):
        """حفظ بيانات إلى ملف JSON"""
        try:
            with open(self.data_files[key], 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"❌ خطأ في حفظ {key}: {e}")
            return False
    
    def initialize_default_settings(self):
        """تهيئة الإعدادات الافتراضية"""
        default_settings = {
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
            'welcome_message': 'أهلاً بك في بوت طاش للخدمات الإلكترونية\nكل عام وأنت بخير مستخدم طاش مميز',
            'currency': 'كوكيز',
            'currency_symbol': '🍪',
            'completed_orders': 24105313,
            'min_transfer': 100,
            'transfer_fee': 5  # نسبة عمولة التحويل
        }
        
        # دمج الإعدادات الافتراضية مع الإعدادات الحالية
        for key, value in default_settings.items():
            if key not in self.settings:
                self.settings[key] = value
        
        self.save_json('settings', self.settings)
    
    def initialize_empty_data(self):
        """تهيئة بيانات فارغة"""
        self.users = {}
        self.services = {}
        self.categories = {}
        self.orders = {}
        self.codes = {}
        self.channels = {}
        self.settings = {}
        self.funding = {}
        self.subscriptions = {}
        self.admins = {}
        self.buttons = {}
        self.transactions = {}
        
        self.initialize_default_settings()
        self.ensure_admin_exists()
    
    def ensure_admin_exists(self):
        """التأكد من وجود المدير الأساسي"""
        if str(ADMIN_ID) not in self.admins:
            self.admins[str(ADMIN_ID)] = {
                'level': 3,
                'added_by': 'system',
                'added_date': datetime.now().isoformat(),
                'permissions': ['all'],
                'username': '',
                'first_name': 'المدير الرئيسي'
            }
            self.save_json('admins', self.admins)
    
    def save_all(self):
        """حفظ جميع البيانات"""
        try:
            self.save_json('users', self.users)
            self.save_json('services', self.services)
            self.save_json('categories', self.categories)
            self.save_json('orders', self.orders)
            self.save_json('codes', self.codes)
            self.save_json('channels', self.channels)
            self.save_json('settings', self.settings)
            self.save_json('funding', self.funding)
            self.save_json('subscriptions', self.subscriptions)
            self.save_json('admins', self.admins)
            self.save_json('buttons', self.buttons)
            self.save_json('transactions', self.transactions)
            logger.info("✅ تم حفظ جميع البيانات")
        except Exception as e:
            logger.error(f"❌ خطأ في حفظ البيانات: {e}")
    
    def get_user(self, user_id: int) -> Dict:
        """الحصول على بيانات المستخدم أو إنشاء جديدة"""
        uid = str(user_id)
        
        if uid not in self.users:
            # بيانات المستخدم الجديد
            self.users[uid] = {
                'id': user_id,
                'username': '',
                'first_name': '',
                'join_date': datetime.now().isoformat(),
                'last_active': datetime.now().isoformat(),
                'points': 1498,  # قيمة افتراضية كما في الصورة
                'invited_by': None,
                'invited_users': [],
                'daily_date': None,
                'total_orders': 0,
                'total_spent': 0,
                'banned': False,
                'ban_reason': '',
                'ban_date': None,
                'funding_requests': [],
                'pending_orders': [],
                'completed_orders': [],
                'subscriptions_done': [],
                'transactions': [],
                'completed_services': 0,
                'total_earned': 0
            }
            self.save_json('users', self.users)
        
        # تحديث وقت النشاط الأخير
        self.users[uid]['last_active'] = datetime.now().isoformat()
        return self.users[uid]
    
    def update_user(self, user_id: int, data: Dict) -> bool:
        """تحديث بيانات المستخدم"""
        try:
            uid = str(user_id)
            if uid not in self.users:
                self.get_user(user_id)  # إنشاء المستخدم إذا لم يكن موجوداً
            
            self.users[uid].update(data)
            self.users[uid]['last_active'] = datetime.now().isoformat()
            self.save_json('users', self.users)
            return True
        except Exception as e:
            logger.error(f"❌ خطأ في تحديث المستخدم {user_id}: {e}")
            return False
    
    def add_transaction(self, user_id: int, transaction_type: str, amount: int, details: str = "") -> str:
        """إضافة معاملة جديدة"""
        try:
            transaction_id = f"TXN{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}"
            
            transaction_data = {
                'id': transaction_id,
                'user_id': user_id,
                'type': transaction_type,
                'amount': amount,
                'details': details,
                'date': datetime.now().isoformat(),
                'status': 'completed'
            }
            
            # حفظ في سجل المعاملات العام
            self.transactions[transaction_id] = transaction_data
            
            # إضافة إلى سجل معاملات المستخدم
            user_data = self.get_user(user_id)
            if 'transactions' not in user_data:
                user_data['transactions'] = []
            
            user_data['transactions'].append(transaction_id)
            self.update_user(user_id, user_data)
            
            # حفظ سجل المعاملات
            self.save_json('transactions', self.transactions)
            
            return transaction_id
        except Exception as e:
            logger.error(f"❌ خطأ في إضافة معاملة: {e}")
            return ""
    
    def is_admin(self, user_id: int, min_level: int = 1) -> bool:
        """فحص إذا كان المستخدم مديراً"""
        uid = str(user_id)
        return uid in self.admins and self.admins[uid]['level'] >= min_level
    
    def get_admin_level(self, user_id: int) -> int:
        """الحصول على مستوى المدير"""
        uid = str(user_id)
        return self.admins.get(uid, {}).get('level', 0)

# إنشاء كائن قاعدة البيانات
db = EnhancedDatabase()

# ========== دوال المساعدة ==========
def format_arabic(text: str) -> str:
    """تنسيق النصوص العربية"""
    try:
        reshaped_text = arabic_reshaper.reshape(text)
        return get_display(reshaped_text)
    except:
        return text

def generate_code(length: int = 8) -> str:
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
            logger.error(f"❌ خطأ في فحص الاشتراك: {e}")
            continue
    
    return True

async def send_notification_to_admin(message: str, context: ContextTypes.DEFAULT_TYPE):
    """إرسال إشعار إلى المدير"""
    try:
        await context.bot.send_message(ADMIN_ID, message, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ خطأ في إرسال الإشعار: {e}")

async def notify_admins(message: str, context: ContextTypes.DEFAULT_TYPE, min_level: int = 1):
    """إرسال إشعار لجميع المديرين"""
    for admin_id, admin_data in db.admins.items():
        if admin_data.get('level', 0) >= min_level:
            try:
                await context.bot.send_message(int(admin_id), message, parse_mode=ParseMode.HTML)
            except:
                pass

def create_pdf_invoice(order_data: dict, user_data: dict) -> BytesIO:
    """إنشاء فاتورة PDF"""
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    
    # إضافة النص العربي
    c.setFont("Helvetica-Bold", 18)
    c.drawString(100, 800, format_arabic("فاتورة خدمات طاش الإلكترونية"))
    
    c.setFont("Helvetica", 12)
    c.drawString(100, 770, format_arabic(f"رقم الفاتورة: #{order_data.get('id', '0000')}"))
    c.drawString(100, 750, format_arabic(f"التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
    
    # معلومات العميل
    c.drawString(100, 720, format_arabic("معلومات العميل:"))
    c.drawString(120, 700, format_arabic(f"الاسم: {user_data.get('first_name', '')}"))
    c.drawString(120, 680, format_arabic(f"المعرف: {user_data.get('id', '')}"))
    
    # تفاصيل الطلب
    c.drawString(100, 650, format_arabic("تفاصيل الطلب:"))
    c.drawString(120, 630, format_arabic(f"الخدمة: {order_data.get('service_name', '')}"))
    c.drawString(120, 610, format_arabic(f"الكمية: {order_data.get('quantity', 0)}"))
    c.drawString(120, 590, format_arabic(f"السعر: {order_data.get('price', 0)} {db.settings.get('currency', 'نقطة')}"))
    c.drawString(120, 570, format_arabic(f"المجموع: {order_data.get('total', 0)} {db.settings.get('currency', 'نقطة')}"))
    
    # رسالة شكر
    c.setFont("Helvetica-Bold", 14)
    c.drawString(100, 500, format_arabic("شكراً لثقتك ببوت طاش للخدمات الإلكترونية"))
    
    c.save()
    buffer.seek(0)
    return buffer

def get_main_keyboard(user_id: int):
    """الحصول على لوحة المفاتيح الرئيسية حسب الصورة"""
    # تحقق إذا كان مديراً
    if db.is_admin(user_id):
        buttons = [
            ["📊 لوحة التحكم", "👤 حسابي"],
            ["🌙 خدمات الرشق", "💬 خدمات الألعاب والتطبيقات"],
            ["🔵+ تمويل أعضاء حقيقيين متفاعلين", "🟢 استخدام الكود"],
            ["🔴 تحويل الكوكيز", "🔵 معلومات الحساب"],
            ["🔵 قناة البوت", "🔵 فحص طلبي"],
            ["🔵 شروط الاستخدام", "🔵 شحن الكوكيز"]
        ]
    else:
        buttons = [
            ["👤 حسابي", "🌙 خدمات الرشق"],
            ["💬 خدمات الألعاب والتطبيقات", "🔵+ تمويل أعضاء حقيقيين متفاعلين"],
            ["🟢 استخدام الكود", "🔴 تحويل الكوكيز"],
            ["🔵 معلومات الحساب", "🔵 قناة البوت"],
            ["🔵 فحص طلبي", "🔵 شروط الاستخدام"],
            ["🔵 شحن الكوكيز"]
        ]
    
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# ========== معالجة الأوامر الرئيسية ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء البوت - مع تحسين العرض كما في الصورة"""
    user = update.effective_user
    user_id = user.id
    
    # تسجيل أو تحديث بيانات المستخدم
    user_data = db.get_user(user_id)
    
    # تحديث معلومات المستخدم
    db.update_user(user_id, {
        'username': user.username or '',
        'first_name': user.first_name or '',
        'last_active': datetime.now().isoformat()
    })
    
    # التحقق من الحظر
    if user_data.get('banned'):
        await update.message.reply_text(
            f"❌ حسابك محظور!\n"
            f"السبب: {user_data.get('ban_reason', 'غير محدد')}\n"
            f"التاريخ: {user_data.get('ban_date', 'غير معروف')}",
            reply_markup=ReplyKeyboardRemove()
        )
        return
    
    # التحقق من الصيانة
    if db.settings.get('maintenance') and not db.is_admin(user_id):
        await update.message.reply_text(
            "🔧 البوت تحت الصيانة حالياً.\n"
            "يرجى المحاولة مرة أخرى لاحقاً.",
            reply_markup=ReplyKeyboardRemove()
        )
        return
    
    # التحقق من الاشتراك الإجباري
    subscription_status = await check_subscription(user_id, context)
    if not subscription_status:
        channels_list = "\n".join([f"• {ch['name']}" for ch in db.channels.values()])
        
        keyboard = [[InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_subscription")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"📢 يجب الاشتراك في القنوات التالية:\n\n"
            f"{channels_list}\n\n"
            f"بعد الاشتراك، اضغط على الزر أدناه:",
            reply_markup=reply_markup
        )
        return
    
    # معالجة رابط الدعوة
    if context.args:
        try:
            inviter_id = int(context.args[0])
            if inviter_id != user_id and str(inviter_id) in db.users:
                current_user = db.get_user(user_id)
                if not current_user.get('invited_by'):
                    # تحديث بيانات المدعو
                    db.update_user(user_id, {'invited_by': inviter_id})
                    
                    # تحديث بيانات المدعو
                    inviter_data = db.get_user(inviter_id)
                    if user_id not in inviter_data.get('invited_users', []):
                        inviter_data['invited_users'].append(user_id)
                        db.update_user(inviter_id, inviter_data)
                        
                        # منح النقاط للمدعو إذا كان النظام نشطاً
                        if db.settings.get('invite_active'):
                            reward = db.settings.get('invite_reward', 100)
                            new_points = inviter_data.get('points', 0) + reward
                            db.update_user(inviter_id, {'points': new_points})
                            
                            # إضافة معاملة
                            db.add_transaction(
                                inviter_id,
                                'invite_reward',
                                reward,
                                f"مكافأة دعوة للمستخدم {user.first_name}"
                            )
                            
                            # إشعار المدعو
                            try:
                                await context.bot.send_message(
                                    inviter_id,
                                    f"🎉 مبروك! حصلت على {reward} {db.settings.get('currency', 'نقطة')}\n"
                                    f"المستخدم {user.first_name} انضم عبر رابط دعوتك!"
                                )
                            except:
                                pass
        except:
            pass
    
    # إرسال إشعار للمدير
    if db.settings.get('notifications'):
        await notify_admins(
            f"👤 مستخدم جديد!\n"
            f"🆔: {user_id}\n"
            f"👤: {user.first_name}\n"
            f"📊 النقاط: {user_data.get('points', 0)}\n"
            f"📅: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            context
        )
    
    # تحضير رسالة الترحيب كما في الصورة
    welcome_message = db.settings.get('welcome_message', 
        "أهلاً بك في بوت فولو - Follow\nكل عام وأنت بخير مستخدم فولو مميز")
    
    user_points = user_data.get('points', 1498)
    currency = db.settings.get('currency', 'كوكيز')
    
    # بناء الرسالة الرئيسية
    main_message = f"""
{welcome_message}

🆔 إيدييك: {user_id}
🍪 عدد {currency}: {user_points}

📊 إحصائيات البوت:
عدد الطلبات المكتملة: {db.settings.get('completed_orders', 24105313):,}

📍 اختر من القائمة أدناه:
"""
    
    # إرسال الرسالة مع لوحة المفاتيح
    reply_markup = get_main_keyboard(user_id)
    await update.message.reply_text(
        main_message,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل النصية مع جميع الأزرار"""
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
        await update.message.reply_text("📢 يجب الاشتراك في القنوات أولاً.")
        return
    
    # التعامل مع حالات المحادثة
    if 'user_state' in context.user_data and user_id in context.user_data['user_state']:
        state = context.user_data['user_state'][user_id]
        await handle_conversation_state(update, context, text, state)
        return
    
    # معالجة الأزرار الرئيسية
    await handle_main_buttons(update, context, text)

async def handle_conversation_state(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, state: dict):
    """معالجة حالات المحادثة"""
    user_id = update.effective_user.id
    state_type = state.get('type')
    
    if state_type == 'waiting_code':
        await handle_code_input(update, context, text)
    elif state_type == 'waiting_service_quantity':
        await handle_service_quantity(update, context, text, state)
    elif state_type == 'waiting_funding_members':
        await handle_funding_members_input(update, context, text, state)
    elif state_type == 'waiting_funding_channel':
        await handle_funding_channel_input(update, context, text, state)
    elif state_type == 'waiting_charge_amount':
        await handle_charge_amount(update, context, text, state)
    elif state_type == 'waiting_transfer_user':
        await handle_transfer_user(update, context, text, state)
    elif state_type == 'waiting_transfer_amount':
        await handle_transfer_amount(update, context, text, state)

async def handle_main_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """معالجة الأزرار الرئيسية"""
    user_id = update.effective_user.id
    
    if text == "👤 حسابي":
        await show_user_profile(update, context)
    elif text == "📊 لوحة التحكم" and db.is_admin(user_id):
        await admin_panel(update, context)
    elif text == "🌙 خدمات الرشق":
        await show_services_category(update, context, "رشق")
    elif text == "💬 خدمات الألعاب والتطبيقات":
        await show_services_category(update, context, "ألعاب")
    elif text == "🔵+ تمويل أعضاء حقيقيين متفاعلين":
        await start_channel_funding(update, context)
    elif text == "🟢 استخدام الكود":
        await start_code_usage(update, context)
    elif text == "🔴 تحويل الكوكيز":
        await start_cookies_transfer(update, context)
    elif text == "🔵 معلومات الحساب":
        await show_account_info(update, context)
    elif text == "🔵 قناة البوت":
        await show_bot_channel(update, context)
    elif text == "🔵 فحص طلبي":
        await check_my_orders(update, context)
    elif text == "🔵 شروط الاستخدام":
        await show_terms(update, context)
    elif text == "🔵 شحن الكوكيز":
        await charge_cookies(update, context)
    else:
        # البحث عن أزرار مخصصة
        for btn_id, btn_data in db.buttons.items():
            if btn_data.get('text') == text:
                await handle_custom_button(update, context, btn_data)
                return
        
        await update.message.reply_text("⚠️ الأمر غير معروف، استخدم الأزرار المعروضة.")

# ========== معالجة أزرار الخدمات ==========
async def show_user_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض ملف المستخدم"""
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    profile_text = f"""
👤 <b>الملف الشخصي</b>

🆔 المعرف: <code>{user_id}</code>
📛 الاسم: {user_data['first_name']}
📅 تاريخ الانضمام: {user_data['join_date'][:10]}
🍪 عدد {db.settings.get('currency', 'كوكيز')}: {user_data['points']}

📊 <b>الإحصائيات:</b>
   📦 عدد الطلبات: {user_data['total_orders']}
   💰 إجمالي المشتريات: {user_data['total_spent']} {db.settings.get('currency', 'كوكيز')}
   👥 عدد المدعوين: {len(user_data.get('invited_users', []))}
   ✅ خدمات مكتملة: {user_data.get('completed_services', 0)}
   
🔗 <b>رابط الدعوة:</b>
<code>https://t.me/{(await context.bot.get_me()).username}?start={user_id}</code>

🎁 <b>مكافأة الدعوة:</b>
   لكل صديق: {db.settings.get('invite_reward', 100)} {db.settings.get('currency', 'كوكيز')}
"""
    
    # إضافة معلومات المدير إذا كان
    if db.is_admin(user_id):
        admin_level = db.get_admin_level(user_id)
        profile_text += f"\n👑 <b>صلاحية المدير:</b> المستوى {admin_level}"
    
    await update.message.reply_text(profile_text, parse_mode=ParseMode.HTML)

async def show_services_category(update: Update, context: ContextTypes.DEFAULT_TYPE, category_type: str):
    """عرض خدمات فئة معينة"""
    # البحث عن القسم المناسب
    category_id = None
    for cat_id, category in db.categories.items():
        if category.get('type') == category_type:
            category_id = cat_id
            break
    
    if not category_id:
        await update.message.reply_text(f"⚠️ لا توجد خدمات في قسم {category_type} حالياً.")
        return
    
    category = db.categories[category_id]
    services = category.get('services', {})
    
    if not services:
        await update.message.reply_text(f"⚠️ لا توجد خدمات متاحة في قسم {category_type}.")
        return
    
    # إنشاء لوحة المفاتيح للخدمات
    keyboard = []
    for service_id, service in services.items():
        service_name = service.get('name', 'خدمة')
        service_price = service.get('price', 0)
        button_text = f"{service_name} - {service_price} {db.settings.get('currency', 'كوكيز')}/1000"
        
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"service_{service_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🛒 <b>خدمات {category['name']}</b>\n\n"
        f"{category.get('description', 'اختر الخدمة المناسبة:')}",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )

async def start_channel_funding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء تمويل القناة"""
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    rate = db.settings.get('channel_funding_rate', 5)
    
    info_text = f"""
💸 <b>تمويل أعضاء حقيقيين متفاعلين</b>

📊 <b>معلومات الخدمة:</b>
   لكل عضو: {rate} {db.settings.get('currency', 'كوكيز')}
   الحد الأدنى: 10 أعضاء
   الحد الأقصى: 1000 عضو
   
💰 <b>مثال:</b>
   100 عضو = {100 * rate} {db.settings.get('currency', 'كوكيز')}
   
📝 <b>شروط الخدمة:</b>
1. يجب أن يكون البوت مشرفاً في القناة
2. القناة يجب أن تكون عامة
3. لا يمكن إلغاء الطلب بعد التأكيد
4. الأعضاء حقيقيون ومتفاعلون
   
⚡ <b>لبدء الطلب:</b>
أرسل عدد الأعضاء المطلوبين (مثال: 100)
"""
    
    # حفظ حالة المستخدم
    if 'user_state' not in context.user_data:
        context.user_data['user_state'] = {}
    
    context.user_data['user_state'][user_id] = {
        'type': 'waiting_funding_members',
        'action': 'channel_funding'
    }
    
    await update.message.reply_text(info_text, parse_mode=ParseMode.HTML)

async def handle_funding_members_input(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, state: dict):
    """معالجة عدد أعضاء التمويل"""
    try:
        members_count = int(text)
        user_id = update.effective_user.id
        
        if members_count < 10:
            await update.message.reply_text("❌ الحد الأدنى هو 10 أعضاء")
            return
        if members_count > 1000:
            await update.message.reply_text("❌ الحد الأقصى هو 1000 عضو")
            return
        
        rate = db.settings.get('channel_funding_rate', 5)
        total_cost = members_count * rate
        
        user_data = db.get_user(user_id)
        if user_data['points'] < total_cost:
            await update.message.reply_text(
                f"❌ {db.settings.get('currency', 'كوكيز')} غير كافية!\n"
                f"🍪 المطلوبة: {total_cost}\n"
                f"💰 رصيدك الحالي: {user_data['points']}"
            )
            # مسح الحالة
            if user_id in context.user_data['user_state']:
                del context.user_data['user_state'][user_id]
            return
        
        # تحديث الحالة
        state['members_count'] = members_count
        state['total_cost'] = total_cost
        state['type'] = 'waiting_funding_channel'
        context.user_data['user_state'][user_id] = state
        
        await update.message.reply_text(
            f"✅ تم تحديد {members_count} عضو\n"
            f"💰 التكلفة الإجمالية: {total_cost} {db.settings.get('currency', 'كوكيز')}\n\n"
            "📢 الآن أرسل رابط القناة (يجب أن يكون البوت مشرفاً فيها):"
        )
        
    except ValueError:
        await update.message.reply_text("❌ رجاءً أرسل رقم صحيح (مثال: 100)")

async def handle_funding_channel_input(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, state: dict):
    """معالجة رابط قناة التمويل"""
    user_id = update.effective_user.id
    
    try:
        channel_link = text.strip()
        
        # محاولة استخراج معرف القناة
        if 't.me/' in channel_link:
            channel_username = channel_link.split('t.me/')[-1].replace('@', '').split('/')[0]
        elif channel_link.startswith('@'):
            channel_username = channel_link[1:].split('/')[0]
        else:
            channel_username = channel_link.split('/')[0]
        
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
            
            # تحديث نقاط المستخدم
            db.update_user(user_id, {
                'points': user_data['points'] - total_cost,
                'total_spent': user_data.get('total_spent', 0) + total_cost
            })
            
            # إضافة معاملة
            db.add_transaction(
                user_id,
                'channel_funding',
                -total_cost,
                f"تمويل قناة {chat.title} - {state['members_count']} عضو"
            )
            
            # إنشاء طلب التمويل
            funding_id = generate_code(8)
            funding_data = {
                'id': funding_id,
                'user_id': user_id,
                'channel_id': channel_id,
                'channel_username': channel_username,
                'channel_name': chat.title,
                'members_count': state['members_count'],
                'current_members': 0,
                'rate': db.settings.get('channel_funding_rate', 5),
                'total_cost': total_cost,
                'status': 'active',
                'start_date': datetime.now().isoformat(),
                'subscribers': []
            }
            
            db.funding[funding_id] = funding_data
            db.save_json('funding', db.funding)
            
            # تحديث بيانات المستخدم
            user_data = db.get_user(user_id)
            if 'funding_requests' not in user_data:
                user_data['funding_requests'] = []
            user_data['funding_requests'].append(funding_id)
            db.update_user(user_id, user_data)
            
            # إشعار المدير
            await notify_admins(
                f"💸 <b>طلب تمويل جديد</b>\n\n"
                f"👤 المستخدم: {user_data['first_name']} (ID: {user_id})\n"
                f"📢 القناة: {chat.title}\n"
                f"👥 العدد المطلوب: {state['members_count']}\n"
                f"💰 التكلفة: {total_cost} {db.settings.get('currency', 'كوكيز')}\n"
                f"🆔 رقم الطلب: {funding_id}",
                context
            )
            
            # تأكيد للمستخدم
            await update.message.reply_text(
                f"✅ <b>تم إنشاء طلب التمويل بنجاح!</b>\n\n"
                f"🆔 رقم الطلب: <code>{funding_id}</code>\n"
                f"📢 القناة: {chat.title}\n"
                f"👥 العدد المطلوب: {state['members_count']} عضو\n"
                f"💰 التكلفة: {total_cost} {db.settings.get('currency', 'كوكيز')}\n\n"
                f"📊 سيبدأ تجميع الأعضاء تلقائياً.\n"
                f"📨 ستستلم إشعاراً بكل عضو جديد.",
                parse_mode=ParseMode.HTML
            )
            
            # مسح الحالة
            if user_id in context.user_data.get('user_state', {}):
                del context.user_data['user_state'][user_id]
                
        except Exception as e:
            logger.error(f"❌ خطأ في معالجة القناة: {e}")
            await update.message.reply_text("❌ رابط القناة غير صحيح أو لا يمكن الوصول إليها!")
            
    except Exception as e:
        logger.error(f"❌ خطأ عام: {e}")
        await update.message.reply_text("❌ حدث خطأ، يرجى المحاولة مرة أخرى!")

async def start_code_usage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء استخدام الكود"""
    user_id = update.effective_user.id
    
    # حفظ حالة المستخدم
    if 'user_state' not in context.user_data:
        context.user_data['user_state'] = {}
    
    context.user_data['user_state'][user_id] = {
        'type': 'waiting_code'
    }
    
    await update.message.reply_text(
        "🎫 <b>استخدام الكود</b>\n\n"
        "أرسل الكود الذي تريد استخدامه:",
        parse_mode=ParseMode.HTML
    )

async def handle_code_input(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """معالجة إدخال الكود"""
    user_id = update.effective_user.id
    code = text.strip().upper()
    
    if code in db.codes:
        code_data = db.codes[code]
        
        # التحقق من صلاحية الكود
        expiry_date = datetime.fromisoformat(code_data.get('expiry_date', '2000-01-01'))
        if expiry_date < datetime.now():
            await update.message.reply_text("❌ هذا الكود منتهي الصلاحية!")
            if user_id in context.user_data.get('user_state', {}):
                del context.user_data['user_state'][user_id]
            return
        
        # التحقق من عدد الاستخدامات
        max_uses = code_data.get('max_uses', 1)
        used_count = code_data.get('used_count', 0)
        
        if used_count >= max_uses:
            await update.message.reply_text("❌ هذا الكود قد استخدم الحد الأقصى من المرات!")
            if user_id in context.user_data.get('user_state', {}):
                del context.user_data['user_state'][user_id]
            return
        
        # التحقق إذا كان المستخدم قد استخدم الكود من قبل
        used_by = code_data.get('used_by', [])
        if str(user_id) in [str(u['user_id']) for u in used_by]:
            await update.message.reply_text("❌ لقد استخدمت هذا الكود من قبل!")
            if user_id in context.user_data.get('user_state', {}):
                del context.user_data['user_state'][user_id]
            return
        
        # تطبيق الكود
        points = code_data.get('points', 0)
        user_data = db.get_user(user_id)
        new_points = user_data['points'] + points
        
        # تحديث نقاط المستخدم
        db.update_user(user_id, {'points': new_points})
        
        # تحديث بيانات الكود
        used_by.append({
            'user_id': user_id,
            'username': update.effective_user.username or '',
            'first_name': update.effective_user.first_name or '',
            'date': datetime.now().isoformat()
        })
        
        code_data['used_count'] = used_count + 1
        code_data['used_by'] = used_by
        db.codes[code] = code_data
        db.save_json('codes', db.codes)
        
        # إضافة معاملة
        db.add_transaction(
            user_id,
            'code_usage',
            points,
            f"استخدام كود {code}"
        )
        
        # إشعار المدير
        await notify_admins(
            f"🎫 <b>تم استخدام كود</b>\n\n"
            f"🆔 الكود: {code}\n"
            f"👤 المستخدم: {user_data['first_name']} (ID: {user_id})\n"
            f"💰 القيمة: {points} {db.settings.get('currency', 'كوكيز')}\n"
            f"📊 الاستخدامات: {used_count + 1}/{max_uses}",
            context
        )
        
        await update.message.reply_text(
            f"✅ <b>تم استخدام الكود بنجاح!</b>\n\n"
            f"🎫 الكود: {code}\n"
            f"💰 القيمة: {points} {db.settings.get('currency', 'كوكيز')}\n"
            f"🍪 رصيدك الجديد: {new_points}",
            parse_mode=ParseMode.HTML
        )
        
        # مسح الحالة
        if user_id in context.user_data.get('user_state', {}):
            del context.user_data['user_state'][user_id]
    else:
        await update.message.reply_text("❌ الكود غير صحيح أو غير موجود!")

async def start_cookies_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء تحويل الكوكيز"""
    user_id = update.effective_user.id
    
    info_text = f"""
🔴 <b>تحويل {db.settings.get('currency', 'كوكيز')}</b>

📊 <b>معلومات التحويل:</b>
   الحد الأدنى: {db.settings.get('min_transfer', 100)} {db.settings.get('currency', 'كوكيز')}
   عمولة التحويل: {db.settings.get('transfer_fee', 5)}%
   
📝 <b>مثال:</b>
   تحويل 1000 {db.settings.get('currency', 'كوكيز')}
   العمولة: {1000 * db.settings.get('transfer_fee', 5) / 100}
   المستلم يحصل: {1000 - (1000 * db.settings.get('transfer_fee', 5) / 100)}
   
⚡ <b>لبدء التحويل:</b>
أرسل معرف المستخدم الذي تريد التحويل له:
(يمكنك الحصول على المعرف من ملفه الشخصي)
"""
    
    # حفظ حالة المستخدم
    if 'user_state' not in context.user_data:
        context.user_data['user_state'] = {}
    
    context.user_data['user_state'][user_id] = {
        'type': 'waiting_transfer_user'
    }
    
    await update.message.reply_text(info_text, parse_mode=ParseMode.HTML)

async def handle_transfer_user(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """معالجة معرف المستخدم للتحويل"""
    user_id = update.effective_user.id
    
    try:
        target_user_id = int(text.strip())
        
        # التحقق من وجود المستخدم الهدف
        if str(target_user_id) not in db.users:
            await update.message.reply_text("❌ المستخدم غير موجود في قاعدة البيانات!")
            if user_id in context.user_data.get('user_state', {}):
                del context.user_data['user_state'][user_id]
            return
        
        # لا يمكن التحويل لنفسه
        if target_user_id == user_id:
            await update.message.reply_text("❌ لا يمكن التحويل لنفسك!")
            if user_id in context.user_data.get('user_state', {}):
                del context.user_data['user_state'][user_id]
            return
        
        target_user = db.get_user(target_user_id)
        
        # تحديث الحالة
        context.user_data['user_state'][user_id] = {
            'type': 'waiting_transfer_amount',
            'target_user_id': target_user_id,
            'target_username': target_user.get('username', ''),
            'target_name': target_user.get('first_name', '')
        }
        
        await update.message.reply_text(
            f"✅ تم تحديد المستخدم:\n"
            f"👤 الاسم: {target_user.get('first_name', 'غير معروف')}\n"
            f"🆔 المعرف: {target_user_id}\n\n"
            f"الآن أرسل عدد {db.settings.get('currency', 'كوكيز')} التي تريد تحويلها:"
        )
        
    except ValueError:
        await update.message.reply_text("❌ رجاءً أرسل معرف مستخدم صحيح (أرقام فقط)")

async def handle_transfer_amount(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, state: dict):
    """معالجة مبلغ التحويل"""
    user_id = update.effective_user.id
    
    try:
        amount = int(text.strip())
        min_transfer = db.settings.get('min_transfer', 100)
        
        if amount < min_transfer:
            await update.message.reply_text(f"❌ الحد الأدنى للتحويل هو {min_transfer}!")
            return
        
        # التحقق من رصيد المستخدم
        user_data = db.get_user(user_id)
        if user_data['points'] < amount:
            await update.message.reply_text(
                f"❌ رصيدك غير كافي!\n"
                f"🍪 الرصيد الحالي: {user_data['points']}\n"
                f"💰 المبلغ المطلوب: {amount}"
            )
            # مسح الحالة
            if user_id in context.user_data.get('user_state', {}):
                del context.user_data['user_state'][user_id]
            return
        
        target_user_id = state['target_user_id']
        fee_percentage = db.settings.get('transfer_fee', 5)
        fee_amount = int(amount * fee_percentage / 100)
        net_amount = amount - fee_amount
        
        # خصم المبلغ من المرسل
        db.update_user(user_id, {
            'points': user_data['points'] - amount
        })
        
        # إضافة المبلغ للمستلم
        target_data = db.get_user(target_user_id)
        db.update_user(target_user_id, {
            'points': target_data['points'] + net_amount
        })
        
        # إضافة معاملات
        db.add_transaction(
            user_id,
            'transfer_out',
            -amount,
            f"تحويل إلى {state['target_name']} (ID: {target_user_id})"
        )
        
        db.add_transaction(
            target_user_id,
            'transfer_in',
            net_amount,
            f"تحويل من {user_data['first_name']} (ID: {user_id})"
        )
        
        # إشعار المرسل
        await update.message.reply_text(
            f"✅ <b>تم التحويل بنجاح!</b>\n\n"
            f"👤 إلى: {state['target_name']}\n"
            f"🆔 المعرف: {target_user_id}\n"
            f"💰 المبلغ: {amount} {db.settings.get('currency', 'كوكيز')}\n"
            f"💸 العمولة: {fee_amount} ({fee_percentage}%)\n"
            f"🎯 المستلم حصل: {net_amount}\n"
            f"🍪 رصيدك الجديد: {user_data['points'] - amount}",
            parse_mode=ParseMode.HTML
        )
        
        # إشعار المستلم
        try:
            await context.bot.send_message(
                target_user_id,
                f"🎉 <b>استلمت تحويلاً!</b>\n\n"
                f"👤 من: {user_data['first_name']}\n"
                f"🆔 المعرف: {user_id}\n"
                f"💰 المبلغ: {net_amount} {db.settings.get('currency', 'كوكيز')}\n"
                f"🍪 رصيدك الجديد: {target_data['points'] + net_amount}",
                parse_mode=ParseMode.HTML
            )
        except:
            pass
        
        # إشعار المدير
        await notify_admins(
            f"🔴 <b>تحويل {db.settings.get('currency', 'كوكيز')}</b>\n\n"
            f"👤 المرسل: {user_data['first_name']} (ID: {user_id})\n"
            f"👥 المستلم: {state['target_name']} (ID: {target_user_id})\n"
            f"💰 المبلغ: {amount} {db.settings.get('currency', 'كوكيز')}\n"
            f"💸 العمولة: {fee_amount}\n"
            f"🎯 الصافي: {net_amount}",
            context
        )
        
        # مسح الحالة
        if user_id in context.user_data.get('user_state', {}):
            del context.user_data['user_state'][user_id]
        
    except ValueError:
        await update.message.reply_text("❌ رجاءً أرسل رقم صحيح!")

async def show_account_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض معلومات الحساب"""
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    info_text = f"""
🔵 <b>معلومات الحساب</b>

🆔 المعرف: <code>{user_id}</code>
📛 الاسم: {user_data['first_name']}
👤 اليوزر: @{user_data['username'] if user_data['username'] else 'غير متوفر'}
📅 تاريخ الانضمام: {user_data['join_date'][:10]}
⏰ آخر نشاط: {user_data['last_active'][:19]}

💰 <b>المالية:</b>
🍪 {db.settings.get('currency', 'كوكيز')}: {user_data['points']}
📦 طلبات مكتملة: {user_data.get('completed_services', 0)}
💸 إجمالي الصرف: {user_data.get('total_spent', 0)}

📊 <b>الإحصائيات:</b>
👥 مدعوون: {len(user_data.get('invited_users', []))}
📨 طلبات معلقة: {len(user_data.get('pending_orders', []))}
✅ طلبات مكتملة: {len(user_data.get('completed_orders', []))}

🔗 <b>رابط الدعوة:</b>
<code>https://t.me/{(await context.bot.get_me()).username}?start={user_id}</code>
"""
    
    await update.message.reply_text(info_text, parse_mode=ParseMode.HTML)

async def show_bot_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قناة البوت"""
    channel = db.settings.get('bot_channel', '@Flashback70bot')
    
    keyboard = [[InlineKeyboardButton("📢 انضم للقناة", url=channel)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🔵 <b>قناة البوت</b>\n\n"
        f"انضم لقناتنا الرسمية للحصول على:\n"
        f"• آخر التحديثات\n"
        f"• العروض الخاصة\n"
        f"• إعلانات الخدمات الجديدة\n"
        f"• شروحات الاستخدام\n\n"
        f"📢 القناة: {channel}",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )

async def check_my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فحص الطلبات"""
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    pending_orders = user_data.get('pending_orders', [])
    completed_orders = user_data.get('completed_orders', [])
    
    if not pending_orders and not completed_orders:
        await update.message.reply_text("📭 لا توجد طلبات حالياً.")
        return
    
    orders_text = "🔵 <b>فحص الطلبات</b>\n\n"
    
    if pending_orders:
        orders_text += "⏳ <b>الطلبات المعلقة:</b>\n"
        for order_id in pending_orders[-3:]:  # آخر 3 طلبات
            if order_id in db.orders:
                order = db.orders[order_id]
                orders_text += f"   📌 {order.get('service_name', 'خدمة')}\n"
                orders_text += f"   🆔: <code>{order_id}</code>\n"
                orders_text += f"   📅: {order.get('date', '')[:10]}\n"
                orders_text += f"   💰: {order.get('total_price', 0)} {db.settings.get('currency', 'كوكيز')}\n"
                orders_text += f"   🔄: {order.get('status', 'معلق')}\n\n"
    
    if completed_orders:
        orders_text += "✅ <b>الطلبات المكتملة:</b>\n"
        for order_id in completed_orders[-3:]:  # آخر 3 طلبات
            if order_id in db.orders:
                order = db.orders[order_id]
                orders_text += f"   ✓ {order.get('service_name', 'خدمة')}\n"
                orders_text += f"   🆔: <code>{order_id}</code>\n"
                orders_text += f"   📅: {order.get('date', '')[:10]}\n"
                orders_text += f"   💰: {order.get('total_price', 0)} {db.settings.get('currency', 'كوكيز')}\n\n"
    
    # زر لتفاصيل أكثر
    keyboard = [[InlineKeyboardButton("📋 عرض جميع الطلبات", callback_data="show_all_orders")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(orders_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def show_terms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض شروط الاستخدام"""
    terms_text = """
🔵 <b>شروط الاستخدام</b>

📜 <b>الشروط والأحكام:</b>

1. <b>المستخدم:</b>
   • يجب أن يكون عمرك 18 سنة أو أكثر
   • الالتزام بجميع القوانين المحلية والدولية
   • عدم استخدام البوت لأغراض غير قانونية

2. <b>الخدمات:</b>
   • جميع الخدمات رقمية ولا يمكن استرجاعها
   • الأسعار قابلة للتغيير دون إشعار مسبق
   • وقت التنفيذ تقريبي وقد يختلف

3. <b>المدفوعات:</b>
   • جميع المدفوعات غير قابلة للاسترداد
   • يتم خصم النقاط فور تأكيد الطلب
   • أي خطأ في الطلب يتحمله المستخدم

4. <b>الحساب:</b>
   • يحق للإدارة تعليق أي حساب لسبب مقنع
   • عدم مشاركة الحساب مع الآخرين
   • المحافظة على سرية المعلومات

5. <b>عام:</b>
   • يحق للإدارة تعديل الشروط في أي وقت
   • الاستمرار في استخدام البوت يعني الموافقة على التعديلات
   • أي نزاع يتم حله وفقاً للقوانين المحلية

📞 <b>للشكاوى والاقتراحات:</b>
{}

⚠️ <b>ملاحظة:</b>
باستخدامك للبوت فإنك توافق على جميع الشروط والأحكام المذكورة أعلاه.
""".format(db.settings.get('support_user', '@support'))
    
    await update.message.reply_text(terms_text, parse_mode=ParseMode.HTML)

async def charge_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شحن الكوكيز"""
    keyboard = [
        [InlineKeyboardButton("🎫 استخدام كود شحن", callback_data="use_code_charge")],
        [InlineKeyboardButton("💳 شحن عن طريق الدعم", callback_data="charge_via_support")],
        [InlineKeyboardButton("👑 طلب من المدير", callback_data="request_admin_charge")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🔵 <b>شحن {db.settings.get('currency', 'كوكيز')}</b>\n\n"
        f"اختر طريقة الشحن المناسبة:\n\n"
        f"1. 🎫 <b>كود شحن:</b> أدخل كود شحن صالح\n"
        f"2. 💳 <b>شحن عن طريق الدعم:</b> للطرق المتاحة\n"
        f"3. 👑 <b>طلب من المدير:</b> لشحن كميات كبيرة\n\n"
        f"💰 <b>الحد الأدنى للشحن:</b> 1000 {db.settings.get('currency', 'كوكيز')}\n"
        f"📞 <b>للاستفسارات:</b> {db.settings.get('support_user', '@support')}",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )

async def handle_custom_button(update: Update, context: ContextTypes.DEFAULT_TYPE, btn_data: dict):
    """معالجة الأزرار المخصصة"""
    btn_type = btn_data.get('type')
    content = btn_data.get('content', '')
    
    if btn_type == 'url':
        keyboard = [[InlineKeyboardButton("🔗 فتح الرابط", url=content)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"🔗 {btn_data.get('description', 'اضغط لفتح الرابط')}",
            reply_markup=reply_markup
        )
    elif btn_type == 'text':
        await update.message.reply_text(content)
    elif btn_type == 'command':
        # تنفيذ أمر محدد
        if content == 'profile':
            await show_user_profile(update, context)
        elif content == 'services':
            await show_services_category(update, context, "رشق")

# ========== معالجة Callback Queries ==========
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة استدعاءات الأزرار"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    if data == "check_subscription":
        await check_subscription_callback(query, context)
    elif data == "back_to_main":
        await start(update, context)
    elif data.startswith("service_"):
        service_id = data.split("_")[1]
        await handle_service_selection(query, context, service_id)
    elif data == "use_code_charge":
        await start_code_usage(update, context)
    elif data == "show_all_orders":
        await show_all_orders(query, context)

async def check_subscription_callback(query, context):
    """فحص الاشتراك"""
    user_id = query.from_user.id
    
    if await check_subscription(user_id, context):
        await query.edit_message_text("✅ تم الاشتراك بنجاح! يمكنك الآن استخدام البوت.")
        await start(update, context)
    else:
        await query.answer("❌ لم تشترك في جميع القنوات بعد!", show_alert=True)

async def handle_service_selection(query, context, service_id):
    """معالجة اختيار الخدمة"""
    user_id = query.from_user.id
    
    # البحث عن الخدمة في الأقسام
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
    
    # حفظ حالة المستخدم
    if 'user_state' not in context.user_data:
        context.user_data['user_state'] = {}
    
    context.user_data['user_state'][user_id] = {
        'type': 'waiting_service_quantity',
        'service_id': service_id,
        'service_name': service_data['name'],
        'service_price': service_data['price'],
        'category': category_name
    }
    
    info_text = f"""
🛒 <b>تفاصيل الخدمة</b>

📦 الخدمة: {service_data['name']}
📂 القسم: {category_name}
💰 السعر: {service_data['price']} {db.settings.get('currency', 'كوكيز')} لكل 1000
⚡ السرعة: {service_data.get('speed', 'متوسطة')}
⏰ الوقت: {service_data.get('time', '24 ساعة')}
📊 الحد الأدنى: {service_data.get('min', 100):,}
📈 الحد الأقصى: {service_data.get('max', 10000):,}
📝 الوصف: {service_data.get('description', 'لا يوجد وصف')}

💎 <b>رصيدك:</b> {db.get_user(user_id)['points']:,} {db.settings.get('currency', 'كوكيز')}

📝 <b>لطلب الخدمة:</b>
أرسل الكمية المطلوبة (بين {service_data.get('min', 100):,} و {service_data.get('max', 10000):,})
"""
    
    await query.edit_message_text(info_text, parse_mode=ParseMode.HTML)

async def handle_service_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, state: dict):
    """معالجة كمية الخدمة"""
    user_id = update.effective_user.id
    
    try:
        quantity = int(text.strip())
        
        # البحث عن بيانات الخدمة
        service_data = None
        for category in db.categories.values():
            if state['service_id'] in category.get('services', {}):
                service_data = category['services'][state['service_id']]
                break
        
        if not service_data:
            await update.message.reply_text("❌ الخدمة غير موجودة!")
            return
        
        min_qty = service_data.get('min', 100)
        max_qty = service_data.get('max', 10000)
        
        if quantity < min_qty:
            await update.message.reply_text(f"❌ الحد الأدنى هو {min_qty:,}!")
            return
        
        if quantity > max_qty:
            await update.message.reply_text(f"❌ الحد الأقصى هو {max_qty:,}!")
            return
        
        # حساب السعر
        price_per_1000 = service_data.get('price', 0)
        total_price = int((quantity / 1000) * price_per_1000)
        
        # التحقق من رصيد المستخدم
        user_data = db.get_user(user_id)
        if user_data['points'] < total_price:
            await update.message.reply_text(
                f"❌ رصيدك غير كافي!\n"
                f"🍪 المطلوب: {total_price}\n"
                f"💰 رصيدك: {user_data['points']}"
            )
            return
        
        # تأكيد الطلب
        keyboard = [
            [
                InlineKeyboardButton("✅ تأكيد الطلب", callback_data=f"confirm_order_{state['service_id']}_{quantity}"),
                InlineKeyboardButton("❌ إلغاء", callback_data="cancel_order")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"📦 <b>تأكيد الطلب</b>\n\n"
            f"📝 الخدمة: {state['service_name']}\n"
            f"🎯 الكمية: {quantity:,}\n"
            f"💰 السعر: {price_per_1000} لكل 1000\n"
            f"💸 الإجمالي: {total_price} {db.settings.get('currency', 'كوكيز')}\n\n"
            f"هل تريد تأكيد الطلب؟",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        
    except ValueError:
        await update.message.reply_text("❌ رجاءً أرسل رقم صحيح!")

async def show_all_orders(query, context):
    """عرض جميع الطلبات"""
    user_id = query.from_user.id
    user_data = db.get_user(user_id)
    
    all_orders = []
    all_orders.extend(user_data.get('pending_orders', []))
    all_orders.extend(user_data.get('completed_orders', []))
    
    if not all_orders:
        await query.answer("📭 لا توجد طلبات!", show_alert=True)
        return
    
    orders_text = "📋 <b>جميع الطلبات</b>\n\n"
    
    for order_id in all_orders[-10:]:  # آخر 10 طلبات
        if order_id in db.orders:
            order = db.orders[order_id]
            status_icon = "⏳" if order.get('status') == 'pending' else "✅" if order.get('status') == 'completed' else "❌"
            
            orders_text += f"{status_icon} <b>{order.get('service_name', 'خدمة')}</b>\n"
            orders_text += f"   🆔: <code>{order_id}</code>\n"
            orders_text += f"   📅: {order.get('date', '')[:10]}\n"
            orders_text += f"   💰: {order.get('total_price', 0)} {db.settings.get('currency', 'كوكيز')}\n"
            orders_text += f"   🔄: {order.get('status', 'غير معروف')}\n\n"
    
    await query.edit_message_text(orders_text, parse_mode=ParseMode.HTML)

# ========== لوحة التحكم للمدير ==========
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لوحة تحكم المدير"""
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id):
        await update.message.reply_text("❌ هذا القسم للمديرين فقط!")
        return
    
    keyboard = [
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 المستخدمين", callback_data="admin_users")],
        [InlineKeyboardButton("🛒 الخدمات", callback_data="admin_services")],
        [InlineKeyboardButton("🎫 أكواد الشحن", callback_data="admin_codes")],
        [InlineKeyboardButton("📢 القنوات", callback_data="admin_channels")],
        [InlineKeyboardButton("💸 التمويلات", callback_data="admin_funding")],
        [InlineKeyboardButton("⚙️ الإعدادات", callback_data="admin_settings")],
        [InlineKeyboardButton("📨 الإذاعة", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🛠️ <b>لوحة تحكم المدير</b>\n\n"
        "اختر القسم الذي تريد إدارته:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )

# ========== الدالة الرئيسية ==========
async def backup_data(context: ContextTypes.DEFAULT_TYPE):
    """نسخ احتياطي للبيانات"""
    try:
        db.save_all()
        logger.info("✅ تم النسخ الاحتياطي للبيانات")
    except Exception as e:
        logger.error(f"❌ خطأ في النسخ الاحتياطي: {e}")

def main():
    """تشغيل البوت"""
    # إنشاء التطبيق
    application = Application.builder().token(BOT_TOKEN).build()
    
    # إضافة المعالجات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    
    # إضافة معالج المحادثة
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            WAITING_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code_input)],
            WAITING_SERVICE_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_service_quantity)],
            WAITING_FUNDING_MEMBERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_funding_members_input)],
            WAITING_FUNDING_CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_funding_channel_input)],
            WAITING_CHARGE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_charge_amount)],
            WAITING_TRANSFER_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_transfer_user)],
            WAITING_TRANSFER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_transfer_amount)],
        },
        fallbacks=[CommandHandler('start', start)]
    )
    
    application.add_handler(conv_handler)
    
    # جدولة النسخ الاحتياطي كل 5 دقائق
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(backup_data, interval=300, first=10)
    
    print("=" * 50)
    print("✅ بوت طاش للخدمات الإلكترونية يعمل الآن!")
    print(f"🤖 يوزر البوت: {BOT_USERNAME}")
    print(f"👑 المدير الرئيسي: {ADMIN_ID}")
    print(f"👥 عدد المستخدمين: {len(db.users)}")
    print(f"💾 مجلد البيانات: {db.data_dir}")
    print("=" * 50)
    
    # بدء التشغيل
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    # إنشاء بعض البيانات الأولية للاختبار
    if not db.categories:
        # قسم خدمات الرشق
        db.categories['cat1'] = {
            'id': 'cat1',
            'name': 'خدمات الرشق 🌙',
            'type': 'رشق',
            'description': 'خدمات الرشق للمنصات الاجتماعية',
            'services': {
                'srv1': {
                    'id': 'srv1',
                    'name': 'مشاهدات يوتيوب',
                    'price': 50,
                    'min': 100,
                    'max': 10000,
                    'time': '24 ساعة',
                    'speed': 'متوسطة',
                    'description': 'مشاهدات حقيقية عالية الجودة'
                },
                'srv2': {
                    'id': 'srv2',
                    'name': 'متابعين تيك توك',
                    'price': 80,
                    'min': 100,
                    'max': 5000,
                    'time': '48 ساعة',
                    'speed': 'بطيئة',
                    'description': 'متابعين حقيقيين'
                }
            }
        }
        
        # قسم الألعاب والتطبيقات
        db.categories['cat2'] = {
            'id': 'cat2',
            'name': 'خدمات الألعاب والتطبيقات 💬',
            'type': 'ألعاب',
            'description': 'خدمات للألعاب والتطبيقات',
            'services': {
                'srv3': {
                    'id': 'srv3',
                    'name': 'مشاهدات تطبيقات',
                    'price': 60,
                    'min': 100,
                    'max': 10000,
                    'time': '12 ساعة',
                    'speed': 'سريعة',
                    'description': 'زيادة مشاهدات التطبيقات'
                }
            }
        }
        
        db.save_json('categories', db.categories)
        print("✅ تم إنشاء بيانات تجريبية")
    
    main()
