#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import sqlite3
import json
import os
import asyncio
import uuid
import random
import string
import time
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
import pytz
from pathlib import Path

# PDF Generation
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib import colors
from reportlab.lib.units import inch, cm
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics import renderPDF

# Arabic Text Support
import arabic_reshaper
from bidi.algorithm import get_display

# QR Code
import qrcode
from PIL import Image as PILImage, ImageDraw, ImageFont

# Telegram
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, 
    ReplyKeyboardMarkup, KeyboardButton, WebAppInfo,
    ReplyKeyboardRemove, InputFile, MenuButtonCommands
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler,
    PicklePersistence
)
from telegram.constants import ParseMode, ChatAction

# ========== إعدادات البوت ==========
TOKEN = "8436742877:AAGJBn79jB5N91e-0IpzU57JrcJV5qSaWPs"
ADMIN_ID = 6130994941
DATABASE_NAME = "smm_bot.db"
BACKUP_DIR = "backups"
LOG_FILE = "bot.log"
BOT_USERNAME = "SMMServicesBot"

# ========== إعدادات الأمان ==========
MAX_REQUESTS_PER_MINUTE = 30
USER_REQUEST_TRACKER = {}

# ========== إعدادات النقاط ==========
DEFAULT_DAILY_BONUS = 50
DEFAULT_REFERRAL_POINTS = 100
DEFAULT_CHANNEL_POINTS = 10
DEFAULT_FUNDING_RATE = 5.0

# ========== حالات المحادثة ==========
class BotStates:
    MAIN_MENU = 1
    ADMIN_PANEL = 2
    ADMIN_ADD_SERVICE = 3
    ADMIN_EDIT_SERVICE = 4
    ADMIN_ADD_CATEGORY = 5
    ADMIN_BROADCAST = 6
    ADMIN_SEND_POINTS = 7
    ADMIN_SEARCH_USER = 8
    ADMIN_CREATE_CODE = 9
    ADMIN_MANAGE_CHANNELS = 10
    ADMIN_SETTINGS = 11
    ADMIN_ORDER_DETAILS = 12
    SERVICE_SELECTION = 13
    SERVICE_QUANTITY = 14
    SERVICE_CONFIRMATION = 15
    CHANNEL_FUNDING_URL = 16
    CHANNEL_FUNDING_COUNT = 17
    CHANNEL_FUNDING_CONFIRM = 18
    RECHARGE_CODE = 19
    SUPPORT_MESSAGE = 20
    USER_PROFILE = 21
    USER_ORDERS = 22
    USER_FUNDING = 23
    USER_REFERRALS = 24

# ========== إعداد التسجيل ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ========== أدوات المساعدة للنص العربي ==========
def arabic_text(text):
    """تحويل النص العربي للعرض الصحيح"""
    reshaped_text = arabic_reshaper.reshape(text)
    return get_display(reshaped_text)

def format_number(num):
    """تنسيق الأرقام مع فواصل"""
    return f"{num:,}"

def format_date(date_str):
    """تنسيق التاريخ"""
    if not date_str:
        return "غير محدد"
    dt = datetime.fromisoformat(date_str)
    return dt.strftime("%Y/%m/%d %H:%M")

# ========== نظام تتبع الطلبات ==========
def rate_limit(user_id):
    """منع إساءة الاستخدام"""
    current_time = time.time()
    if user_id not in USER_REQUEST_TRACKER:
        USER_REQUEST_TRACKER[user_id] = []
    
    # حذف الطلبات القديمة
    USER_REQUEST_TRACKER[user_id] = [
        t for t in USER_REQUEST_TRACKER[user_id] 
        if current_time - t < 60
    ]
    
    # التحقق من الحد
    if len(USER_REQUEST_TRACKER[user_id]) >= MAX_REQUESTS_PER_MINUTE:
        return False
    
    USER_REQUEST_TRACKER[user_id].append(current_time)
    return True

# ========== قاعدة البيانات ==========
@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_database():
    """تهيئة قاعدة البيانات مع جميع الجداول"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # جدول المستخدمين
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT NOT NULL,
                last_name TEXT,
                phone TEXT,
                balance REAL DEFAULT 0,
                total_spent REAL DEFAULT 0,
                total_earned REAL DEFAULT 0,
                referrals INTEGER DEFAULT 0,
                referral_code TEXT UNIQUE,
                referred_by INTEGER,
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_daily_bonus TIMESTAMP,
                daily_streak INTEGER DEFAULT 0,
                banned INTEGER DEFAULT 0,
                ban_reason TEXT,
                ban_date TIMESTAMP,
                language TEXT DEFAULT 'ar',
                notifications INTEGER DEFAULT 1,
                CONSTRAINT fk_referred_by FOREIGN KEY (referred_by) REFERENCES users(user_id)
            )
        ''')
        
        # جدول الخدمات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                price_per_1000 REAL NOT NULL,
                min_amount INTEGER DEFAULT 100,
                max_amount INTEGER DEFAULT 10000,
                average_time TEXT DEFAULT '24 ساعة',
                quality TEXT DEFAULT 'عالية',
                api_id TEXT,
                active INTEGER DEFAULT 1,
                position INTEGER DEFAULT 0,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # جدول الأقسام
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                icon TEXT DEFAULT '📁',
                description TEXT,
                active INTEGER DEFAULT 1,
                position INTEGER DEFAULT 0
            )
        ''')
        
        # جدول الطلبات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                service_id INTEGER NOT NULL,
                service_name TEXT NOT NULL,
                amount INTEGER NOT NULL,
                price_per_1000 REAL NOT NULL,
                total_price REAL NOT NULL,
                link TEXT,
                status TEXT DEFAULT 'pending',
                order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                start_date TIMESTAMP,
                completed_date TIMESTAMP,
                admin_notes TEXT,
                invoice_sent INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (service_id) REFERENCES services(id)
            )
        ''')
        
        # جدول قنوات الاشتراك الإجباري
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT NOT NULL UNIQUE,
                channel_name TEXT,
                channel_url TEXT,
                required INTEGER DEFAULT 1,
                points_reward REAL DEFAULT 10,
                check_interval INTEGER DEFAULT 24,
                position INTEGER DEFAULT 0,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # جدول اشتراكات المستخدمين في القنوات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                subscribed INTEGER DEFAULT 0,
                last_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                points_rewarded INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (channel_id) REFERENCES channels(id),
                UNIQUE(user_id, channel_id)
            )
        ''')
        
        # جدول أكواد الشحن
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recharge_codes (
                code TEXT PRIMARY KEY,
                points REAL NOT NULL,
                max_uses INTEGER DEFAULT 1,
                used_count INTEGER DEFAULT 0,
                created_by INTEGER,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_date TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                note TEXT
            )
        ''')
        
        # جدول استخدامات الأكواد
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS code_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                used_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                points_received REAL NOT NULL,
                FOREIGN KEY (code) REFERENCES recharge_codes(code),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        # جدول تمويل القنوات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channel_funding (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                channel_url TEXT NOT NULL,
                channel_name TEXT,
                current_members INTEGER,
                target_members INTEGER,
                points_per_member REAL DEFAULT 5.0,
                total_points REAL,
                status TEXT DEFAULT 'pending',
                progress INTEGER DEFAULT 0,
                completed_members INTEGER DEFAULT 0,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_date TIMESTAMP,
                completed_date TIMESTAMP,
                admin_notes TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        # جدول إحصائيات تمويل القنوات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS funding_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                funding_id INTEGER NOT NULL,
                check_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                member_count INTEGER,
                new_members INTEGER DEFAULT 0,
                points_added REAL DEFAULT 0,
                FOREIGN KEY (funding_id) REFERENCES channel_funding(id)
            )
        ''')
        
        # جدول الإعدادات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                description TEXT,
                category TEXT DEFAULT 'general',
                editable INTEGER DEFAULT 1,
                updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # جدول الإشعارات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                is_read INTEGER DEFAULT 0,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                related_id INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        # جدول الأزرار المخصصة
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS custom_buttons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                text TEXT NOT NULL,
                callback_data TEXT,
                url TEXT,
                position INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # جدول سجل الأنشطة
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                details TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        # جدول الفواتير
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_number TEXT UNIQUE NOT NULL,
                order_id INTEGER,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                pdf_path TEXT,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent_date TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders(id),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        # إدخال الإعدادات الافتراضية
        default_settings = [
            ('daily_bonus_points', str(DEFAULT_DAILY_BONUS), 'النقاط اليومية', 'points', 1),
            ('referral_points', str(DEFAULT_REFERRAL_POINTS), 'نقاط الدعوة', 'points', 1),
            ('channel_sub_points', str(DEFAULT_CHANNEL_POINTS), 'نقاط الاشتراك في القنوات', 'points', 1),
            ('funding_rate', str(DEFAULT_FUNDING_RATE), 'سعر تمويل القناة لكل عضو', 'points', 1),
            ('min_funding_members', '100', 'الحد الأدنى لأعضاء التمويل', 'funding', 1),
            ('max_funding_members', '10000', 'الحد الأقصى لأعضاء التمويل', 'funding', 1),
            ('support_channel', '@SMMSupport', 'قناة الدعم', 'contact', 1),
            ('bot_channel', '@SMMBotChannel', 'قناة البوت', 'contact', 1),
            ('support_username', '@SMMAdmin', 'يوزر الدعم', 'contact', 1),
            ('contact_email', 'support@smmbot.com', 'البريد الإلكتروني', 'contact', 1),
            ('maintenance_mode', '0', 'وضع الصيانة', 'system', 1),
            ('notifications_enabled', '1', 'تفعيل الإشعارات', 'system', 1),
            ('registration_enabled', '1', 'تفعيل التسجيل', 'system', 1),
            ('min_order_amount', '100', 'الحد الأدنى للطلب', 'orders', 1),
            ('max_order_amount', '100000', 'الحد الأقصى للطلب', 'orders', 1),
            ('auto_approve_orders', '0', 'الموافقة التلقائية على الطلبات', 'orders', 1),
            ('invoice_enabled', '1', 'تفعيل الفواتير', 'invoices', 1),
            ('currency', 'نقطة', 'العملة', 'general', 1),
            ('language', 'ar', 'اللغة الافتراضية', 'general', 1),
            ('timezone', 'Asia/Riyadh', 'المنطقة الزمنية', 'general', 1),
            ('backup_enabled', '1', 'تفعيل النسخ الاحتياطي', 'system', 1),
            ('backup_interval', '24', 'فترة النسخ الاحتياطي (ساعة)', 'system', 1),
            ('admin_notify_orders', '1', 'إشعار المدير بالطلبات الجديدة', 'notifications', 1),
            ('admin_notify_funding', '1', 'إشعار المدير بطلبات التمويل', 'notifications', 1),
            ('admin_notify_users', '1', 'إشعار المدير بالمستخدمين الجدد', 'notifications', 1),
            ('welcome_message', 'مرحبا بك في بوت خدمات SMM!', 'رسالة الترحيب', 'messages', 1),
            ('help_message', 'للحصول على المساعدة، تواصل مع الدعم الفني.', 'رسالة المساعدة', 'messages', 1),
            ('terms_url', 'https://example.com/terms', 'رابط الشروط والأحكام', 'legal', 1),
            ('privacy_url', 'https://example.com/privacy', 'رابط الخصوصية', 'legal', 1)
        ]
        
        cursor.executemany('''
            INSERT OR IGNORE INTO settings (key, value, description, category, editable)
            VALUES (?, ?, ?, ?, ?)
        ''', default_settings)
        
        # إضافة أقسام افتراضية
        default_categories = [
            ('متابعين', '👥', 'خدمات المتابعين لمختلف المنصات', 1),
            ('مشاهدات', '👁️', 'خدمات المشاهدات', 2),
            ('لايكات', '❤️', 'خدمات الإعجابات', 3),
            ('تعليقات', '💬', 'خدمات التعليقات', 4),
            ('تصويتات', '🗳️', 'خدمات التصويت', 5),
            ('تفاعل', '🔥', 'خدمات التفاعل', 6)
        ]
        
        cursor.executemany('''
            INSERT OR IGNORE INTO categories (name, icon, description, position)
            VALUES (?, ?, ?, ?)
        ''', default_categories)
        
        # إضافة خدمات افتراضية
        default_services = [
            ('متابعين', 'متابعين إنستغرام', 'متابعين إنستغرام حقيقيين، جودة عالية، ضمان 30 يوم', 2.5, 100, 5000, '24-48 ساعة', 'عالية'),
            ('متابعين', 'متابعين تويتر', 'متابعين تويتر نشطين، تضاعف متابعينك بسرعة', 3.0, 100, 10000, '24-72 ساعة', 'متوسطة'),
            ('مشاهدات', 'مشاهدات يوتيوب', 'مشاهدات يوتيوب من أشخاص حقيقيين، زيادة في الوقت المناسب', 1.5, 500, 100000, '12-24 ساعة', 'عالية'),
            ('لايكات', 'لايكات إنستغرام', 'لايكات إنستغرام من مستخدمين نشطين', 2.0, 100, 50000, '1-3 ساعات', 'عالية'),
            ('تعليقات', 'تعليقات يوتيوب', 'تعليقات يوتيوب إيجابية ومتنوعة', 5.0, 10, 1000, '6-12 ساعة', 'عالية'),
            ('تصويتات', 'تصويتات تيك توك', 'تصويتات تيك توك لزيادة التفاعل', 4.0, 50, 5000, '1-2 ساعات', 'متوسطة')
        ]
        
        cursor.executemany('''
            INSERT OR IGNORE INTO services 
            (category, name, description, price_per_1000, min_amount, max_amount, average_time, quality)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', default_services)
        
        # إضافة أزرار مخصصة افتراضية
        default_buttons = [
            ('الدعم الفني', '💬 الدعم الفني', 'support', 'https://t.me/SMMSupport', 1),
            ('قناة البوت', '📢 قناة البوت', 'channel', 'https://t.me/SMMBotChannel', 2),
            ('الشروط والأحكام', '📜 الشروط', 'terms', 'https://example.com/terms', 3),
            ('الأسئلة الشائعة', '❓ الأسئلة الشائعة', 'faq', 'https://example.com/faq', 4)
        ]
        
        cursor.executemany('''
            INSERT OR IGNORE INTO custom_buttons (name, text, callback_data, url, position)
            VALUES (?, ?, ?, ?, ?)
        ''', default_buttons)
        
        conn.commit()
    
    logger.info("✅ تم تهيئة قاعدة البيانات بنجاح")

# ========== أدوات قاعدة البيانات ==========
def get_setting(key, default=None):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        result = cursor.fetchone()
        return result['value'] if result else default

def update_setting(key, value):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE settings SET value = ?, updated_date = CURRENT_TIMESTAMP
            WHERE key = ?
        ''', (value, key))
        conn.commit()

def get_user(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        return cursor.fetchone()

def create_user(user_id, username, first_name, last_name="", phone=""):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        referral_code = generate_referral_code()
        
        cursor.execute('''
            INSERT OR IGNORE INTO users 
            (user_id, username, first_name, last_name, phone, referral_code, last_active)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, username, first_name, last_name, phone, referral_code))
        
        if cursor.rowcount > 0:
            conn.commit()
            return True
        else:
            cursor.execute('''
                UPDATE users SET last_active = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (user_id,))
            conn.commit()
            return False

def update_user_activity(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET last_active = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (user_id,))
        conn.commit()

def update_balance(user_id, amount, reason=""):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        if amount > 0:
            cursor.execute('''
                UPDATE users 
                SET balance = balance + ?, total_earned = total_earned + ?
                WHERE user_id = ?
            ''', (amount, amount, user_id))
        else:
            cursor.execute('''
                UPDATE users 
                SET balance = balance + ?, total_spent = total_spent + ABS(?)
                WHERE user_id = ?
            ''', (amount, amount, user_id))
        
        # تسجيل العملية
        cursor.execute('''
            INSERT INTO activity_log (user_id, action, details)
            VALUES (?, 'balance_update', ?)
        ''', (user_id, f'{amount} points - {reason}'))
        
        conn.commit()

def generate_referral_code(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# ========== إدارة الإشعارات ==========
async def send_notification(user_id, notification_type, title, message, related_id=None):
    if get_setting('notifications_enabled') != '1':
        return
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO notifications (user_id, type, title, message, related_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, notification_type, title, message, related_id))
        conn.commit()
    
    # إرسال إشعار فوري عبر البوت
    try:
        app = Application.builder().token(TOKEN).build()
        await app.bot.send_message(
            chat_id=user_id,
            text=f"🔔 *{title}*\n\n{message}",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"فشل إرسال إشعار للمستخدم {user_id}: {e}")

async def send_admin_notification(message, notification_type="info"):
    """إرسال إشعار للمدير"""
    if get_setting(f'admin_notify_{notification_type}') != '1':
        return
    
    try:
        app = Application.builder().token(TOKEN).build()
        await app.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"👨‍💼 *إشعار المدير*\n\n{message}",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"فشل إرسال إشعار للمدير: {e}")

# ========== إنشاء لوحات المفاتيح ==========
def main_menu_keyboard():
    """لوحة المفاتيح الرئيسية"""
    keyboard = [
        [KeyboardButton("🛒 خدمات SMM"), KeyboardButton("💰 رصيدي")],
        [KeyboardButton("🎁 الهدية اليومية"), KeyboardButton("👥 دعوة أصدقاء")],
        [KeyboardButton("📊 إحصائياتي"), KeyboardButton("💸 تمويل قناتي")],
        [KeyboardButton("📜 طلباتي"), KeyboardButton("🎫 شحن الرصيد")],
        [KeyboardButton("🔔 إشعاراتي"), KeyboardButton("ℹ️ المساعدة")]
    ]
    
    # إضافة الأزرار المخصصة
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT text, callback_data, url 
            FROM custom_buttons 
            WHERE is_active = 1 
            ORDER BY position
        ''')
        custom_buttons = cursor.fetchall()
        
        if custom_buttons:
            row = []
            for btn in custom_buttons:
                row.append(KeyboardButton(btn['text']))
                if len(row) == 2:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)
    
    # زر لوحة التحكم للمدير فقط
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def admin_keyboard():
    """لوحة تحكم المدير"""
    keyboard = [
        [InlineKeyboardButton("📊 لوحة التحكم", callback_data="admin_dashboard")],
        [InlineKeyboardButton("👥 إدارة المستخدمين", callback_data="admin_users")],
        [InlineKeyboardButton("🛒 إدارة الخدمات", callback_data="admin_services")],
        [InlineKeyboardButton("📢 البث والإذاعة", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🎫 أكواد الشحن", callback_data="admin_codes")],
        [InlineKeyboardButton("📺 إدارة القنوات", callback_data="admin_channels")],
        [InlineKeyboardButton("💸 طلبات التمويل", callback_data="admin_funding")],
        [InlineKeyboardButton("📋 الطلبات الجديدة", callback_data="admin_orders")],
        [InlineKeyboardButton("⚙️ الإعدادات", callback_data="admin_settings")],
        [InlineKeyboardButton("📈 الإحصائيات", callback_data="admin_stats")],
        [InlineKeyboardButton("📁 النسخ الاحتياطي", callback_data="admin_backup")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def services_menu_keyboard():
    """قائمة الخدمات حسب الأقسام"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.name, c.icon, c.description
            FROM categories c
            WHERE c.active = 1
            ORDER BY c.position
        ''')
        categories = cursor.fetchall()
    
    keyboard = []
    for category in categories:
        keyboard.append([InlineKeyboardButton(
            f"{category['icon']} {category['name']}",
            callback_data=f"category_{category['name']}"
        )])
    
    keyboard.append([
        InlineKeyboardButton("🔍 بحث عن خدمة", callback_data="search_service"),
        InlineKeyboardButton("🔙 الرئيسية", callback_data="back_to_main")
    ])
    
    return InlineKeyboardMarkup(keyboard)

def category_services_keyboard(category_name):
    """خدمات قسم معين"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, name, price_per_1000, min_amount, max_amount
            FROM services
            WHERE category = ? AND active = 1
            ORDER BY position
        ''', (category_name,))
        services = cursor.fetchall()
    
    keyboard = []
    for service in services:
        btn_text = f"{service['name']} - {service['price_per_1000']} لكل 1000"
        keyboard.append([InlineKeyboardButton(
            btn_text,
            callback_data=f"service_{service['id']}"
        )])
    
    keyboard.append([
        InlineKeyboardButton("🔙 الأقسام", callback_data="back_to_categories"),
        InlineKeyboardButton("🏠 الرئيسية", callback_data="back_to_main")
    ])
    
    return InlineKeyboardMarkup(keyboard)

def order_confirmation_keyboard(order_id):
    """أزرار تأكيد الطلب"""
    keyboard = [
        [
            InlineKeyboardButton("✅ تأكيد الطلب", callback_data=f"confirm_order_{order_id}"),
            InlineKeyboardButton("❌ إلغاء", callback_data=f"cancel_order_{order_id}")
        ],
        [
            InlineKeyboardButton("✏️ تعديل الكمية", callback_data=f"edit_quantity_{order_id}"),
            InlineKeyboardButton("🔄 تغيير الخدمة", callback_data="back_to_services")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def admin_order_actions_keyboard(order_id):
    """أزرار إدارة الطلب للمدير"""
    keyboard = [
        [
            InlineKeyboardButton("✅ موافقة", callback_data=f"admin_approve_order_{order_id}"),
            InlineKeyboardButton("❌ رفض", callback_data=f"admin_reject_order_{order_id}")
        ],
        [
            InlineKeyboardButton("⏸️ إيقاف", callback_data=f"admin_pause_order_{order_id}"),
            InlineKeyboardButton("▶️ استئناف", callback_data=f"admin_resume_order_{order_id}")
        ],
        [
            InlineKeyboardButton("👁️ عرض التفاصيل", callback_data=f"admin_view_order_{order_id}"),
            InlineKeyboardButton("📄 إنشاء فاتورة", callback_data=f"admin_invoice_{order_id}")
        ],
        [
            InlineKeyboardButton("👤 حظر المستخدم", callback_data=f"admin_ban_user_order_{order_id}"),
            InlineKeyboardButton("💬 مراسلة", callback_data=f"admin_message_user_{order_id}")
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data="admin_orders")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ========== معالجة الأوامر الرئيسية ==========
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /start"""
    user = update.effective_user
    user_id = user.id
    
    # تحديث نشاط المستخدم
    update_user_activity(user_id)
    
    # التحقق من حالة الصيانة
    if get_setting('maintenance_mode') == '1' and user_id != ADMIN_ID:
        await update.message.reply_text(
            "⚙️ *البوت قيد الصيانة حالياً*\n\n"
            "نعمل على تحسين الخدمة لتقديم الأفضل لك. الرجاء المحاولة لاحقاً.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard()
        )
        return
    
    # التحقق من الاشتراك في القنوات
    if not await check_channels_subscription(update, context):
        return
    
    # إنشاء المستخدم إذا لم يكن موجوداً
    is_new_user = create_user(
        user_id, 
        user.username or "", 
        user.first_name, 
        user.last_name or ""
    )
    
    # معالجة رابط الإحالة
    if context.args:
        referral_code = context.args[0]
        await handle_referral(user_id, referral_code)
    
    # رسالة الترحيب
    welcome_msg = get_setting('welcome_message', 'مرحبا بك في بوت خدمات SMM!')
    
    if is_new_user:
        # إشعار المدير بمستخدم جديد
        user_info = (
            f"🆕 *مستخدم جديد*\n\n"
            f"👤 ID: `{user_id}`\n"
            f"📛 الاسم: {user.first_name} {user.last_name or ''}\n"
            f"🌐 اليوزر: @{user.username or 'لا يوجد'}\n"
            f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        await send_admin_notification(user_info, "users")
        
        # إرسال نقاط ترحيبية
        welcome_points = 10
        update_balance(user_id, welcome_points, "نقاط ترحيبية")
        
        welcome_msg += f"\n\n🎁 *حصلت على {welcome_points} نقطة ترحيبية!*"
    
    # عرض القائمة الرئيسية
    user_data = get_user(user_id)
    balance_msg = f"\n💰 *رصيدك الحالي:* {user_data['balance']:.0f} نقطة" if user_data else ""
    
    full_message = f"""
{welcome_msg}
{balance_msg}

📊 *إحصائيات سريعة:*
• 🎁 الهدية اليومية: {get_setting('daily_bonus_points')} نقطة
• 👥 الدعوة: {get_setting('referral_points')} نقطة لكل صديق
• 📺 الاشتراك بالقنوات: {get_setting('channel_sub_points')} نقطة

🔗 *رابط الدعوة الخاص بك:*
`https://t.me/{BOT_USERNAME}?start={user_data['referral_code'] if user_data else ''}`

اختر من القائمة أدناه 👇
"""
    
    await update.message.reply_text(
        full_message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard()
    )

async def handle_referral(user_id, referral_code):
    """معالجة رابط الإحالة"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # البحث عن صاحب كود الإحالة
        cursor.execute(
            'SELECT user_id FROM users WHERE referral_code = ? AND user_id != ?',
            (referral_code, user_id)
        )
        referrer = cursor.fetchone()
        
        if referrer:
            # تحديث بيانات الإحالة
            cursor.execute('''
                UPDATE users 
                SET referred_by = ?, referrals = referrals + 1
                WHERE user_id = ? AND referred_by IS NULL
            ''', (referrer['user_id'], user_id))
            
            # منح نقاط الإحالة
            referral_points = float(get_setting('referral_points', DEFAULT_REFERRAL_POINTS))
            update_balance(referrer['user_id'], referral_points, "نقاط دعوة")
            
            # إشعار المدير
            notification = (
                f"👥 *إحالة جديدة*\n\n"
                f"👤 المستخدم: {user_id}\n"
                f"📛 تمت دعوته بواسطة: {referrer['user_id']}\n"
                f"💰 النقاط الممنوحة: {referral_points}"
            )
            await send_admin_notification(notification, "referrals")
            
            conn.commit()

async def check_channels_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """التحقق من اشتراك المستخدم في القنوات المطلوبة"""
    user_id = update.effective_user.id
    
    # استثناء المدير
    if user_id == ADMIN_ID:
        return True
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT channel_id, channel_name, channel_url, points_reward
            FROM channels 
            WHERE required = 1
            ORDER BY position
        ''')
        channels = cursor.fetchall()
    
    if not channels:
        return True
    
    # التحقق من الاشتراكات
    unsubscribed = []
    app = Application.builder().token(TOKEN).build()
    
    for channel in channels:
        try:
            member = await app.bot.get_chat_member(channel['channel_id'], user_id)
            if member.status in ['left', 'kicked']:
                unsubscribed.append(channel)
        except Exception as e:
            logger.error(f"خطأ في التحقق من القناة {channel['channel_id']}: {e}")
            unsubscribed.append(channel)
    
    if unsubscribed:
        # إنشاء لوحة أزرار للقنوات
        buttons = []
        for channel in unsubscribed:
            channel_name = channel['channel_name'] or channel['channel_id']
            channel_url = channel['channel_url'] or f"https://t.me/{channel['channel_id'].replace('@', '')}"
            buttons.append([InlineKeyboardButton(
                f"📢 {channel_name} (+{channel['points_reward']} نقطة)",
                url=channel_url
            )])
        
        buttons.append([InlineKeyboardButton(
            "✅ تحقق من الاشتراكات",
            callback_data="check_subscription"
        )])
        
        await update.message.reply_text(
            "⚠️ *يجب الاشتراك في القنوات التالية لاستخدام البوت:*\n\n"
            "اشترك في جميع القنوات ثم اضغط على زر التحقق",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return False
    
    # منح نقاط الاشتراك إذا لم يكن قد حصل عليها من قبل
    with get_db_connection() as conn:
        cursor = conn.cursor()
        for channel in channels:
            cursor.execute('''
                SELECT 1 FROM user_channels 
                WHERE user_id = ? AND channel_id = ? AND points_rewarded = 1
            ''', (user_id, channel['channel_id']))
            
            if not cursor.fetchone():
                points = float(channel['points_reward'])
                update_balance(user_id, points, f"اشتراك في {channel['channel_name']}")
                
                # تحديث سجل الاشتراك
                cursor.execute('''
                    INSERT OR REPLACE INTO user_channels 
                    (user_id, channel_id, subscribed, points_rewarded, last_check)
                    VALUES (?, ?, 1, 1, CURRENT_TIMESTAMP)
                ''', (user_id, channel['channel_id']))
        
        conn.commit()
    
    return True

# ========== أوامر القائمة الرئيسية ==========
async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض رصيد المستخدم"""
    user_id = update.effective_user.id
    update_user_activity(user_id)
    
    user = get_user(user_id)
    if not user:
        await update.message.reply_text("❌ لم يتم العثور على حسابك!")
        return
    
    # جمع الإحصائيات
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) as count FROM orders WHERE user_id = ?', (user_id,))
        total_orders = cursor.fetchone()['count']
        
        cursor.execute('SELECT SUM(total_price) as total FROM orders WHERE user_id = ? AND status = "completed"', (user_id,))
        total_spent = cursor.fetchone()['total'] or 0
        
        cursor.execute('SELECT COUNT(*) as count FROM users WHERE referred_by = ?', (user_id,))
        successful_refs = cursor.fetchone()['count']
    
    message = f"""
💰 *حسابك الشخصي*

📊 *المعلومات الأساسية:*
• 🆔 المعرف: `{user_id}`
• 👤 الاسم: {user['first_name']} {user['last_name'] or ''}
• 🌐 اليوزر: @{user['username'] or 'لا يوجد'}
• 📅 تاريخ الانضمام: {format_date(user['join_date'])}
• 🕒 آخر نشاط: {format_date(user['last_active'])}

💳 *الحالة المالية:*
• 💰 الرصيد الحالي: *{user['balance']:.0f} نقطة*
• 💸 إجمالي المصروف: *{total_spent:.0f} نقطة*
• 💰 إجمالي المكتسب: *{user['total_earned']:.0f} نقطة*

📈 *الإحصائيات:*
• 🛒 الطلبات الكلية: *{total_orders}*
• 👥 عدد الدعوات: *{user['referrals']}*
• ✅ الدعوات الناجحة: *{successful_refs}*
• 🔥 متتالية الهدايا: *{user['daily_streak']} يوم*

🔗 *كود الدعوة الخاص بك:*
`{user['referral_code']}`

📤 *رابط الدعوة:*
https://t.me/{BOT_USERNAME}?start={user['referral_code']}

🎁 *ستحصل أنت وصديقك على {get_setting('referral_points')} نقطة لكل دعوة ناجحة!*
"""
    
    keyboard = [
        [InlineKeyboardButton("📤 مشاركة رابط الدعوة", switch_inline_query=f"انضم عبر رابطي واحصل على {get_setting('referral_points')} نقطة!")],
        [InlineKeyboardButton("🎫 شحن الرصيد", callback_data="recharge_menu"),
         InlineKeyboardButton("📜 سجل المعاملات", callback_data="transaction_history")],
        [InlineKeyboardButton("🔙 الرئيسية", callback_data="back_to_main")]
    ]
    
    await update.message.reply_text(
        message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def daily_bonus_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الهدية اليومية"""
    user_id = update.effective_user.id
    update_user_activity(user_id)
    
    user = get_user(user_id)
    if not user:
        await update.message.reply_text("❌ لم يتم العثور على حسابك!")
        return
    
    now = datetime.now()
    last_bonus = None
    
    if user['last_daily_bonus']:
        last_bonus = datetime.fromisoformat(user['last_daily_bonus'])
    
    can_claim = True
    streak = user['daily_streak']
    
    if last_bonus:
        # حساب الوقت المنقضي
        time_diff = now - last_bonus
        hours_diff = time_diff.total_seconds() / 3600
        
        if hours_diff < 24:
            can_claim = False
            next_bonus = last_bonus + timedelta(hours=24)
            time_left = next_bonus - now
            
            hours = int(time_left.seconds // 3600)
            minutes = int((time_left.seconds % 3600) // 60)
            
            await update.message.reply_text(
                f"⏳ *لقد حصلت على الهدية اليومية بالفعل!*\n\n"
                f"🎁 **المتتالية الحالية:** {streak} يوم\n"
                f"⏰ **الموعد القادم:** بعد {hours} ساعة و {minutes} دقيقة\n\n"
                f"حافظ على متتالية الهدايا لتحصل على مكافآت أكبر!",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        elif hours_diff > 48:
            # كسر المتتالية
            streak = 0
    
    if can_claim:
        # حساب المكافأة
        base_points = float(get_setting('daily_bonus_points', DEFAULT_DAILY_BONUS))
        streak_bonus = min(streak * 5, 100)  # 5 نقاط إضافية لكل يوم بحد أقصى 100
        total_points = base_points + streak_bonus
        
        # تحديث المستخدم
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET balance = balance + ?, 
                    last_daily_bonus = ?,
                    daily_streak = ?
                WHERE user_id = ?
            ''', (total_points, now.isoformat(), streak + 1, user_id))
            conn.commit()
        
        update_balance(user_id, total_points, "هدية يومية")
        
        # إشعار المدير
        notification = (
            f"🎁 *هدية يومية*\n\n"
            f"👤 المستخدم: {user_id}\n"
            f"📛 الاسم: {user['first_name']}\n"
            f"🔥 المتتالية: {streak + 1} يوم\n"
            f"💰 النقاط: {total_points} ({base_points} أساسي + {streak_bonus} مكافأة)"
        )
        await send_admin_notification(notification, "bonus")
        
        # رسالة النجاح
        message = f"""
🎉 *مبروك! حصلت على الهدية اليومية!*

💰 **المكافأة:**
• 🎁 النقاط الأساسية: {base_points}
• 🔥 مكافأة المتتالية: {streak_bonus}
• 💰 **الإجمالي: {total_points} نقطة**

📊 **المتتالية الحالية:** {streak + 1} يوم

💳 **رصيدك الجديد:** {user['balance'] + total_points:.0f} نقطة

🎯 *تحدي:* حافظ على المتتالية لـ7 أيام متتالية لتحصل على مكافأة 100 نقطة إضافية!
"""
        
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN
        )

async def services_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض خدمات SMM"""
    user_id = update.effective_user.id
    update_user_activity(user_id)
    
    await update.message.reply_text(
        "🛒 *قائمة خدمات SMM*\n\n"
        "اختر القسم الذي تريده من القائمة أدناه:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=services_menu_keyboard()
    )

async def channel_funding_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تمويل القنوات"""
    user_id = update.effective_user.id
    update_user_activity(user_id)
    
    rate_per_member = get_setting('funding_rate', DEFAULT_FUNDING_RATE)
    min_members = get_setting('min_funding_members', '100')
    max_members = get_setting('max_funding_members', '10000')
    
    message = f"""
💸 *تمويل قناتك - Earn Points*

📊 *كيف يعمل النظام؟*
1️⃣ أرسل رابط قناتك العامة
2️⃣ نقوم بحساب عدد الأعضاء الحالي
3️⃣ تحدد عدد الأعضاء الإضافي المطلوب
4️⃣ تحصل على نقاط لكل عضو جديد ينضم

💰 *التعريفة الحالية:*
• {rate_per_member} نقطة لكل عضو جديد

⚡ *الشروط والمتطلبات:*
• القناة يجب أن تكون عامة (Public)
• الحد الأدنى: {min_members} عضو
• الحد الأقصى: {max_members} عضو
• يجب أن يكون لديك صلاحيات إدارية في القناة

📈 *مثال:*
إذا طلبت 1000 عضو → 1000 × {rate_per_member} = {float(rate_per_member)*1000:.0f} نقطة!

🎯 *ملاحظة:* النقاط تمنح فقط للأعضاء الجدد بعد بدء الحملة.

أرسل رابط قناتك الآن 👇
"""
    
    await update.message.reply_text(
        message,
        parse_mode=ParseMode.MARKDOWN
    )
    
    context.user_data['awaiting_funding'] = True
    return BotStates.CHANNEL_FUNDING_URL

async def handle_funding_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة رابط القناة للتمويل"""
    user_id = update.effective_user.id
    channel_url = update.message.text
    
    # التحقق الأساسي من الرابط
    if not ('t.me/' in channel_url or 'telegram.me/' in channel_url):
        await update.message.reply_text(
            "❌ *رابط غير صحيح!*\n\n"
            "الرجاء إرسال رابط قناة تلغرام صحيح مثل:\n"
            "• https://t.me/channel_name\n"
            "• @channel_name",
            parse_mode=ParseMode.MARKDOWN
        )
        return BotStates.CHANNEL_FUNDING_URL
    
    # حفظ الرابط مؤقتاً
    context.user_data['funding_channel_url'] = channel_url
    
    # طلب عدد الأعضاء الحالي
    await update.message.reply_text(
        "✅ *تم استلام رابط القناة*\n\n"
        "الآن أرسل عدد الأعضاء الحالي في قناتك:\n"
        "(يجب أن يكون رقمًا فقط، مثال: 1500)",
        parse_mode=ParseMode.MARKDOWN
    )
    
    return BotStates.CHANNEL_FUNDING_COUNT

async def handle_funding_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة عدد الأعضاء الحالي"""
    user_id = update.effective_user.id
    
    try:
        current_members = int(update.message.text)
        
        min_members = int(get_setting('min_funding_members', '100'))
        if current_members < min_members:
            await update.message.reply_text(
                f"❌ *عدد الأعضاء أقل من الحد الأدنى!*\n\n"
                f"الحد الأدنى المطلوب: {min_members} عضو\n"
                f"عدد أعضائك الحالي: {current_members}",
                parse_mode=ParseMode.MARKDOWN
            )
            return BotStates.CHANNEL_FUNDING_COUNT
        
    except ValueError:
        await update.message.reply_text(
            "❌ *الرجاء إدخال رقم صحيح فقط!*\n"
            "مثال: 1500",
            parse_mode=ParseMode.MARKDOWN
        )
        return BotStates.CHANNEL_FUNDING_COUNT
    
    # حفظ عدد الأعضاء
    context.user_data['current_members'] = current_members
    
    # طلب عدد الأعضاء المطلوب
    max_members = int(get_setting('max_funding_members', '10000'))
    
    await update.message.reply_text(
        f"✅ *تم تسجيل عدد الأعضاء: {current_members}*\n\n"
        f"الآن أرسل عدد الأعضاء الإضافي المطلوب:\n"
        f"(من {min_members} إلى {max_members - current_members} عضو)",
        parse_mode=ParseMode.MARKDOWN
    )
    
    return BotStates.CHANNEL_FUNDING_CONFIRM

async def handle_funding_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأكيد طلب التمويل"""
    user_id = update.effective_user.id
    
    try:
        target_members = int(update.message.text)
        current_members = context.user_data.get('current_members', 0)
        channel_url = context.user_data.get('funding_channel_url', '')
        
        min_members = int(get_setting('min_funding_members', '100'))
        max_total = int(get_setting('max_funding_members', '10000'))
        
        if target_members < min_members:
            await update.message.reply_text(
                f"❌ *الحد الأدنى هو {min_members} عضو!*",
                parse_mode=ParseMode.MARKDOWN
            )
            return BotStates.CHANNEL_FUNDING_CONFIRM
        
        total_members = current_members + target_members
        if total_members > max_total:
            await update.message.reply_text(
                f"❌ *الحد الأقصى الإجمالي هو {max_total} عضو!*\n"
                f"يمكنك طلب حتى {max_total - current_members} عضو إضافي.",
                parse_mode=ParseMode.MARKDOWN
            )
            return BotStates.CHANNEL_FUNDING_CONFIRM
        
        # حساب النقاط
        rate = float(get_setting('funding_rate', DEFAULT_FUNDING_RATE))
        total_points = target_members * rate
        
        # حفظ طلب التمويل
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO channel_funding 
                (user_id, channel_url, current_members, target_members, 
                 points_per_member, total_points, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
            ''', (user_id, channel_url, current_members, target_members, rate, total_points))
            
            funding_id = cursor.lastrowid
            conn.commit()
        
        # إشعار المدير
        user = get_user(user_id)
        notification = (
            f"💸 *طلب تمويل جديد*\n\n"
            f"🆔 رقم الطلب: #{funding_id}\n"
            f"👤 المستخدم: {user_id} (@{user['username'] or 'لا يوجد'})\n"
            f"📢 القناة: {channel_url}\n"
            f"👥 الأعضاء الحاليين: {current_members}\n"
            f"🎯 المطلوب: {target_members} عضو جديد\n"
            f"💰 النقاط المحتملة: {total_points:.0f}\n"
            f"⏰ الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        await send_admin_notification(notification, "funding")
        
        # رسالة التأكيد للمستخدم
        message = f"""
✅ *تم استلام طلب التمويل بنجاح!*

📋 *تفاصيل الطلب:*
• 🆔 رقم الطلب: #{funding_id}
• 📢 رابط القناة: {channel_url}
• 👥 الأعضاء الحاليين: {current_members}
• 🎯 الأعضاء المطلوبين: {target_members}
• 💰 النقاط المحتملة: {total_points:.0f}
• ⏳ الحالة: قيد المراجعة

📊 *سيتم مراجعة طلبك من قبل الإدارة خلال 24 ساعة.*
📬 *ستصلك إشعار عند الموافقة على الطلب.*

🔍 يمكنك متابعة حالة طلبك من قسم 'تمويلاتي'
"""
        
        keyboard = [
            [InlineKeyboardButton("📋 تمويلاتي", callback_data="my_funding")],
            [InlineKeyboardButton("🛒 خدمات SMM", callback_data="services_menu"),
             InlineKeyboardButton("🏠 الرئيسية", callback_data="back_to_main")]
        ]
        
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # تنظيف البيانات المؤقتة
        context.user_data.pop('funding_channel_url', None)
        context.user_data.pop('current_members', None)
        context.user_data.pop('awaiting_funding', None)
        
        return BotStates.MAIN_MENU
        
    except ValueError:
        await update.message.reply_text(
            "❌ *الرجاء إدخال رقم صحيح فقط!*",
            parse_mode=ParseMode.MARKDOWN
        )
        return BotStates.CHANNEL_FUNDING_CONFIRM

# ========== لوحة تحكم المدير ==========
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فتح لوحة تحكم المدير"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text(
            "⛔ *غير مصرح لك بالدخول!*\n\n"
            "هذه الصفحة مخصصة للمدير فقط.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # إحصائيات سريعة
    stats = get_admin_stats()
    
    message = f"""
🛠️ *لوحة التحكم - الإدارة*

📊 *الإحصائيات الحالية:*
• 👥 المستخدمون: {stats['total_users']}
• 💰 إجمالي النقاط: {stats['total_balance']:.0f}
• 🛒 الطلبات النشطة: {stats['active_orders']}
• 💸 طلبات التمويل: {stats['pending_funding']}
• 📈 الإيرادات: {stats['total_revenue']:.0f} نقطة

⚙️ *حالة النظام:*
• 🔧 الصيانة: {'✅ مفعلة' if get_setting('maintenance_mode') == '1' else '❌ معطلة'}
• 🔔 الإشعارات: {'✅ مفعلة' if get_setting('notifications_enabled') == '1' else '❌ معطلة'}
• 📝 التسجيل: {'✅ مفتوح' if get_setting('registration_enabled') == '1' else '❌ مغلق'}

📅 *اليوم:* {datetime.now().strftime('%Y-%m-%d %H:%M')}

اختر الخيار المطلوب 👇
"""
    
    await update.message.reply_text(
        message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=admin_keyboard()
    )

def get_admin_stats():
    """جمع إحصائيات المدير"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # المستخدمون
        cursor.execute('SELECT COUNT(*) as count FROM users')
        total_users = cursor.fetchone()['count']
        
        cursor.execute('SELECT SUM(balance) as total FROM users')
        total_balance = cursor.fetchone()['total'] or 0
        
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE DATE(join_date) = DATE('now')")
        new_users_today = cursor.fetchone()['count']
        
        # الطلبات
        cursor.execute("SELECT COUNT(*) as count FROM orders WHERE status = 'pending'")
        pending_orders = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM orders WHERE status = 'active'")
        active_orders = cursor.fetchone()['count']
        
        cursor.execute("SELECT SUM(total_price) as total FROM orders WHERE status = 'completed'")
        total_revenue = cursor.fetchone()['total'] or 0
        
        # طلبات التمويل
        cursor.execute("SELECT COUNT(*) as count FROM channel_funding WHERE status = 'pending'")
        pending_funding = cursor.fetchone()['count']
        
        # الأكواد
        cursor.execute("SELECT COUNT(*) as count FROM recharge_codes WHERE is_active = 1")
        active_codes = cursor.fetchone()['count']
        
        return {
            'total_users': total_users,
            'total_balance': total_balance,
            'new_users_today': new_users_today,
            'pending_orders': pending_orders,
            'active_orders': active_orders,
            'total_revenue': total_revenue,
            'pending_funding': pending_funding,
            'active_codes': active_codes
        }

# ========== معالجة الاستدعاءات ==========
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة جميع استدعاءات الأزرار"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    logger.info(f"Callback from {user_id}: {data}")
    
    # تحديث نشاط المستخدم
    update_user_activity(user_id)
    
    # التحقق من الصيانة
    if get_setting('maintenance_mode') == '1' and user_id != ADMIN_ID:
        await query.edit_message_text(
            "⚙️ البوت قيد الصيانة حالياً. الرجاء المحاولة لاحقاً.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 تحديث", callback_data="back_to_main")]])
        )
        return
    
    # التحقق من الاشتراك في القنوات
    if not await check_channels_subscription_callback(query, context):
        return
    
    # توجيه الاستدعاءات
    if data == "back_to_main":
        await show_main_menu(query)
    
    elif data == "admin_panel" or data == "admin_dashboard":
        await admin_command_callback(query, context)
    
    elif data.startswith("category_"):
        category = data.replace("category_", "")
        await show_category_services(query, category)
    
    elif data == "back_to_categories":
        await services_command_callback(query)
    
    elif data.startswith("service_"):
        service_id = int(data.replace("service_", ""))
        await show_service_details(query, service_id)
    
    elif data == "recharge_menu":
        await show_recharge_menu(query)
    
    elif data == "my_funding":
        await show_user_funding(query)
    
    elif data == "transaction_history":
        await show_transaction_history(query)
    
    elif data == "admin_users":
        await admin_users_menu(query)
    
    elif data == "admin_services":
        await admin_services_menu(query)
    
    elif data == "admin_orders":
        await admin_orders_menu(query)
    
    elif data == "admin_funding":
        await admin_funding_menu(query)
    
    elif data == "admin_broadcast":
        await admin_broadcast_menu(query)
    
    elif data == "admin_codes":
        await admin_codes_menu(query)
    
    elif data == "admin_channels":
        await admin_channels_menu(query)
    
    elif data == "admin_settings":
        await admin_settings_menu(query)
    
    elif data == "admin_stats":
        await admin_stats_detailed(query)
    
    elif data == "admin_backup":
        await admin_backup_menu(query)
    
    elif data.startswith("admin_view_order_"):
        order_id = int(data.replace("admin_view_order_", ""))
        await admin_view_order(query, order_id)
    
    elif data.startswith("admin_approve_order_"):
        order_id = int(data.replace("admin_approve_order_", ""))
        await admin_approve_order(query, order_id)
    
    elif data.startswith("confirm_order_"):
        order_id = int(data.replace("confirm_order_", ""))
        await confirm_user_order(query, order_id)
    
    elif data == "check_subscription":
        if await check_channels_subscription_callback(query, context):
            await query.edit_message_text(
                "✅ *تم الاشتراك في جميع القنوات بنجاح!*\n\n"
                "يمكنك الآن استخدام البوت بشكل كامل.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_to_main")]
                ])
            )
    
    else:
        await query.edit_message_text(
            "⚠️ هذا الزر غير معروف أو لم يتم برمجته بعد.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
            ])
        )

async def check_channels_subscription_callback(query, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """التحقق من الاشتراك للاستدعاءات"""
    user_id = query.from_user.id
    
    if user_id == ADMIN_ID:
        return True
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT channel_id, channel_name, channel_url
            FROM channels 
            WHERE required = 1
        ''')
        channels = cursor.fetchall()
    
    if not channels:
        return True
    
    app = Application.builder().token(TOKEN).build()
    unsubscribed = []
    
    for channel in channels:
        try:
            member = await app.bot.get_chat_member(channel['channel_id'], user_id)
            if member.status in ['left', 'kicked']:
                unsubscribed.append(channel)
        except:
            unsubscribed.append(channel)
    
    if unsubscribed:
        buttons = []
        for channel in unsubscribed:
            channel_name = channel['channel_name'] or channel['channel_id']
            channel_url = channel['channel_url'] or f"https://t.me/{channel['channel_id'].replace('@', '')}"
            buttons.append([InlineKeyboardButton(
                f"📢 {channel_name}",
                url=channel_url
            )])
        
        buttons.append([InlineKeyboardButton(
            "✅ تحقق من الاشتراك",
            callback_data="check_subscription"
        )])
        
        await query.edit_message_text(
            "⚠️ *يجب الاشتراك في القنوات التالية:*",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return False
    
    return True

async def show_main_menu(query):
    """عرض القائمة الرئيسية"""
    user_id = query.from_user.id
    user = get_user(user_id)
    
    welcome = f"مرحباً {user['first_name']}!" if user else "مرحباً!"
    balance = f"\n💰 رصيدك: {user['balance']:.0f} نقطة" if user else ""
    
    await query.edit_message_text(
        f"{welcome}{balance}\n\n"
        "اختر من القائمة أدناه 👇",
        reply_markup=main_menu_keyboard()
    )

async def admin_command_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """لوحة تحكم المدير عبر الاستدعاء"""
    user_id = query.from_user.id
    
    if user_id != ADMIN_ID:
        await query.edit_message_text(
            "⛔ غير مصرح لك بالدخول!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
            ])
        )
        return
    
    stats = get_admin_stats()
    
    message = f"""
🛠️ *لوحة التحكم - الإدارة*

📊 *الإحصائيات السريعة:*
• 👥 المستخدمون: {stats['total_users']}
• 💰 إجمالي النقاط: {stats['total_balance']:.0f}
• 🛒 الطلبات النشطة: {stats['active_orders']}
• 📈 الإيرادات: {stats['total_revenue']:.0f}

اختر من القائمة 👇
"""
    
    await query.edit_message_text(
        message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=admin_keyboard()
    )

async def show_category_services(query, category_name):
    """عرض خدمات قسم معين"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # الحصول على تفاصيل القسم
        cursor.execute('SELECT icon, description FROM categories WHERE name = ?', (category_name,))
        category = cursor.fetchone()
        
        # الحصول على الخدمات
        cursor.execute('''
            SELECT id, name, description, price_per_1000, min_amount, max_amount, average_time, quality
            FROM services
            WHERE category = ? AND active = 1
            ORDER BY position
        ''', (category_name,))
        services = cursor.fetchall()
    
    if not services:
        await query.edit_message_text(
            f"⚠️ *لا توجد خدمات في قسم {category_name} حالياً.*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 الأقسام", callback_data="back_to_categories")],
                [InlineKeyboardButton("🏠 الرئيسية", callback_data="back_to_main")]
            ])
        )
        return
    
    icon = category['icon'] if category else '📁'
    desc = category['description'] if category else ''
    
    message = f"""
{icon} *قسم {category_name}*

{desc}

*الخدمات المتاحة:*
"""
    
    for service in services:
        message += f"\n🔸 *{service['name']}*"
        message += f"\n📝 {service['description']}"
        message += f"\n💰 السعر: {service['price_per_1000']} لكل 1000"
        message += f"\n🔢 النطاق: {service['min_amount']:,} - {service['max_amount']:,}"
        message += f"\n⏰ الوقت: {service['average_time']}"
        message += f"\n⚡ الجودة: {service['quality']}"
        message += f"\n📥 الطلب: /order_{service['id']}\n"
    
    keyboard = []
    for service in services:
        keyboard.append([InlineKeyboardButton(
            f"🛒 {service['name']} - {service['price_per_1000']}",
            callback_data=f"service_{service['id']}"
        )])
    
    keyboard.append([
        InlineKeyboardButton("🔙 الأقسام", callback_data="back_to_categories"),
        InlineKeyboardButton("🏠 الرئيسية", callback_data="back_to_main")
    ])
    
    await query.edit_message_text(
        message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_service_details(query, service_id):
    """عرض تفاصيل خدمة مع إمكانية الطلب"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.*, c.name as category_name, c.icon as category_icon
            FROM services s
            LEFT JOIN categories c ON s.category = c.name
            WHERE s.id = ? AND s.active = 1
        ''', (service_id,))
        
        service = cursor.fetchone()
    
    if not service:
        await query.edit_message_text(
            "❌ *الخدمة غير متوفرة!*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 الأقسام", callback_data="back_to_categories")]
            ])
        )
        return
    
    user_id = query.from_user.id
    user = get_user(user_id)
    
    message = f"""
{service['category_icon']} *{service['name']}*

📝 *الوصف:*
{service['description']}

📊 *تفاصيل الخدمة:*
• 🏷️ السعر: *{service['price_per_1000']} نقطة لكل 1000*
• 🔢 النطاق: *{service['min_amount']:,} - {service['max_amount']:,}*
• ⏰ الوقت المتوسط: *{service['average_time']}*
• ⚡ الجودة: *{service['quality']}*
• 📁 القسم: *{service['category_name']}*

💡 *مثال:*
طلب 1000 = {service['price_per_1000']} نقطة
طلب 5000 = {service['price_per_1000'] * 5} نقطة

💰 *رصيدك الحالي:* {user['balance']:.0f} نقطة

أرسل الكمية المطلوبة (رقم فقط):
"""
    
    # حفظ معرف الخدمة للاستخدام لاحقاً
    context = query.message._bot_data.get('context')
    if context:
        context.user_data['selected_service'] = service_id
        context.user_data['service_price'] = service['price_per_1000']
        context.user_data['min_amount'] = service['min_amount']
        context.user_data['max_amount'] = service['max_amount']
    
    keyboard = [
        [InlineKeyboardButton("🔢 طلب 1000", callback_data=f"quick_order_{service_id}_1000")],
        [InlineKeyboardButton("🔢 طلب 5000", callback_data=f"quick_order_{service_id}_5000")],
        [InlineKeyboardButton("🔢 طلب 10000", callback_data=f"quick_order_{service_id}_10000")],
        [
            InlineKeyboardButton("🔙 القسم", callback_data=f"category_{service['category_name']}"),
            InlineKeyboardButton("🏠 الرئيسية", callback_data="back_to_main")
        ]
    ]
    
    await query.edit_message_text(
        message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # تعيين حالة انتظار الكمية
    return BotStates.SERVICE_QUANTITY

async def services_command_callback(query):
    """عرض خدمات SMM عبر الاستدعاء"""
    await query.edit_message_text(
        "🛒 *قائمة خدمات SMM*\n\nاختر القسم:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=services_menu_keyboard()
    )

# ========== نظام الطلبات ==========
async def handle_service_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة كمية الطلب"""
    user_id = update.effective_user.id
    
    try:
        quantity = int(update.message.text)
        
        service_id = context.user_data.get('selected_service')
        min_amount = context.user_data.get('min_amount', 100)
        max_amount = context.user_data.get('max_amount', 10000)
        price_per_1000 = context.user_data.get('service_price', 5.0)
        
        if quantity < min_amount or quantity > max_amount:
            await update.message.reply_text(
                f"❌ *الكمية خارج النطاق المسموح!*\n\n"
                f"النطاق المسموح: {min_amount:,} - {max_amount:,}\n"
                f"الرجاء إرسال كمية ضمن هذا النطاق:",
                parse_mode=ParseMode.MARKDOWN
            )
            return BotStates.SERVICE_QUANTITY
        
        # حساب السعر
        total_price = (quantity / 1000) * price_per_1000
        
        # الحصول على معلومات الخدمة
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT name FROM services WHERE id = ?', (service_id,))
            service = cursor.fetchone()
        
        if not service:
            await update.message.reply_text("❌ الخدمة غير موجودة!")
            return BotStates.MAIN_MENU
        
        # حفظ بيانات الطلب
        context.user_data['order_quantity'] = quantity
        context.user_data['order_total'] = total_price
        context.user_data['order_service_name'] = service['name']
        
        # التحقق من الرصيد
        user = get_user(user_id)
        if user['balance'] < total_price:
            await update.message.reply_text(
                f"❌ *رصيدك غير كافي!*\n\n"
                f"💰 المطلوب: {total_price:.2f} نقطة\n"
                f"💰 رصيدك الحالي: {user['balance']:.2f} نقطة\n"
                f"🔸 الناقص: {total_price - user['balance']:.2f} نقطة\n\n"
                f"يمكنك شحن رصيدك من خلال:\n"
                f"1. 🎫 أكواد الشحن\n"
                f"2. 👥 دعوة الأصدقاء\n"
                f"3. 💸 تمويل القناة\n"
                f"4. 🎁 الهدية اليومية",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎫 شحن الرصيد", callback_data="recharge_menu")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
                ])
            )
            return BotStates.MAIN_MENU
        
        # عرض تأكيد الطلب
        message = f"""
✅ *تفاصيل الطلب*

📦 *الخدمة:* {service['name']}
🔢 *الكمية:* {quantity:,}
💰 *السعر لكل 1000:* {price_per_1000} نقطة
💵 *الإجمالي:* {total_price:.2f} نقطة

👤 *المستخدم:* {user['first_name']}
💰 *الرصيد قبل:* {user['balance']:.2f} نقطة
💰 *الرصيد بعد:* {user['balance'] - total_price:.2f} نقطة

⚠️ *ملاحظة:* بعد التأكيد، سيتم خصم المبلغ من رصيدك وسيبدأ تنفيذ الطلب.

هل تريد تأكيد الطلب؟
"""
        
        keyboard = [
            [
                InlineKeyboardButton("✅ تأكيد الطلب", callback_data=f"confirm_final_{service_id}"),
                InlineKeyboardButton("❌ إلغاء", callback_data="cancel_order")
            ],
            [
                InlineKeyboardButton("✏️ تعديل الكمية", callback_data=f"edit_quantity_{service_id}"),
                InlineKeyboardButton("🔄 تغيير الخدمة", callback_data="back_to_categories")
            ]
        ]
        
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return BotStates.SERVICE_CONFIRMATION
        
    except ValueError:
        await update.message.reply_text(
            "❌ *الرجاء إدخال رقم صحيح فقط!*\n"
            "مثال: 1000, 5000, 10000",
            parse_mode=ParseMode.MARKDOWN
        )
        return BotStates.SERVICE_QUANTITY

async def confirm_final_order(query, service_id):
    """تأكيد الطلب النهائي"""
    user_id = query.from_user.id
    context = query.message._bot_data.get('context')
    
    if not context:
        await query.edit_message_text("❌ خطأ في النظام!")
        return
    
    quantity = context.user_data.get('order_quantity')
    total_price = context.user_data.get('order_total')
    service_name = context.user_data.get('order_service_name')
    
    user = get_user(user_id)
    
    # التحقق النهائي من الرصيد
    if user['balance'] < total_price:
        await query.edit_message_text(
            "❌ رصيدك غير كافي! الرجاء شحن الرصيد.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎫 شحن الرصيد", callback_data="recharge_menu")]
            ])
        )
        return
    
    # إنشاء الطلب في قاعدة البيانات
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO orders 
            (user_id, service_id, service_name, amount, price_per_1000, total_price, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, service_id, service_name, quantity, 
              context.user_data.get('service_price'), total_price, 'pending'))
        
        order_id = cursor.lastrowid
        
        # خصم الرصيد
        update_balance(user_id, -total_price, f"طلب #{order_id}")
        
        # تحديث إحصائيات المستخدم
        cursor.execute('''
            UPDATE users SET total_spent = total_spent + ?
            WHERE user_id = ?
        ''', (total_price, user_id))
        
        conn.commit()
    
    # إشعار المدير
    if get_setting('admin_notify_orders') == '1':
        notification = f"""
🛒 *طلب جديد #${order_id}*

👤 *المستخدم:*
• ID: `{user_id}`
• الاسم: {user['first_name']} {user['last_name'] or ''}
• اليوزر: @{user['username'] or 'لا يوجد'}

📦 *تفاصيل الطلب:*
• الخدمة: {service_name}
• الكمية: {quantity:,}
• السعر الإجمالي: {total_price:.2f} نقطة
• الرصيد المتبقي: {user['balance'] - total_price:.2f} نقطة

⏰ *الوقت:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        keyboard = [
            [InlineKeyboardButton("👁️ عرض الطلب", callback_data=f"admin_view_order_{order_id}"),
             InlineKeyboardButton("✅ الموافقة", callback_data=f"admin_approve_order_{order_id}")],
            [InlineKeyboardButton("📊 لوحة التحكم", callback_data="admin_panel")]
        ]
        
        try:
            app = Application.builder().token(TOKEN).build()
            await app.bot.send_message(
                chat_id=ADMIN_ID,
                text=notification,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"فشل إرسال إشعار للمدير: {e}")
    
    # رسالة النجاح للمستخدم
    message = f"""
🎉 *تم إنشاء طلبك بنجاح!*

📋 *تفاصيل الطلب:*
• 🆔 رقم الطلب: #{order_id}
• 📦 الخدمة: {service_name}
• 🔢 الكمية: {quantity:,}
• 💰 السعر الإجمالي: {total_price:.2f} نقطة
• 📅 الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M')}
• ⏳ الحالة: قيد المراجعة

💰 *تم خصم {total_price:.2f} نقطة من رصيدك*
💰 *رصيدك الجديد: {user['balance'] - total_price:.2f} نقطة*

📬 *ستصلك إشعارات بتحديثات الطلب.*
⏰ *سيتم البدء بالتنفيذ بعد موافقة الإدارة.*

🔍 يمكنك متابعة طلباتك من قسم 'طلباتي'
"""
    
    keyboard = [
        [InlineKeyboardButton("📜 طلباتي", callback_data="my_orders")],
        [InlineKeyboardButton("📄 طباعة الفاتورة", callback_data=f"generate_invoice_{order_id}")],
        [
            InlineKeyboardButton("🛒 طلب جديد", callback_data="services_menu"),
            InlineKeyboardButton("🏠 الرئيسية", callback_data="back_to_main")
        ]
    ]
    
    await query.edit_message_text(
        message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # تنظيف البيانات المؤقتة
    context.user_data.pop('selected_service', None)
    context.user_data.pop('order_quantity', None)
    context.user_data.pop('order_total', None)
    context.user_data.pop('order_service_name', None)
    context.user_data.pop('service_price', None)
    context.user_data.pop('min_amount', None)
    context.user_data.pop('max_amount', None)

# ========== إدارة المدير المتقدمة ==========
async def admin_users_menu(query):
    """قائمة إدارة المستخدمين"""
    keyboard = [
        [InlineKeyboardButton("🔍 بحث عن مستخدم", callback_data="admin_search_user")],
        [InlineKeyboardButton("📋 جميع المستخدمين", callback_data="admin_all_users")],
        [InlineKeyboardButton("📈 أفضل المستخدمين", callback_data="admin_top_users")],
        [InlineKeyboardButton("🚫 المستخدمون المحظورون", callback_data="admin_banned_users")],
        [InlineKeyboardButton("📊 إحصائيات المستخدمين", callback_data="admin_users_stats")],
        [InlineKeyboardButton("📤 تصدير البيانات", callback_data="admin_export_users")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
    ]
    
    await query.edit_message_text(
        "👥 *إدارة المستخدمين*\n\nاختر الخيار المطلوب:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_services_menu(query):
    """قائمة إدارة الخدمات"""
    keyboard = [
        [InlineKeyboardButton("➕ إضافة خدمة جديدة", callback_data="admin_add_service")],
        [InlineKeyboardButton("✏️ تعديل الخدمات", callback_data="admin_edit_services")],
        [InlineKeyboardButton("📁 إدارة الأقسام", callback_data="admin_manage_categories")],
        [InlineKeyboardButton("📊 إحصائيات الخدمات", callback_data="admin_services_stats")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
    ]
    
    await query.edit_message_text(
        "🛒 *إدارة الخدمات*\n\nاختر الخيار المطلوب:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_orders_menu(query):
    """قائمة إدارة الطلبات"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) as count FROM orders WHERE status = 'pending'")
        pending = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM orders WHERE status = 'active'")
        active = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM orders WHERE status = 'completed'")
        completed = cursor.fetchone()['count']
    
    message = f"""
📋 *إدارة الطلبات*

📊 *حالة الطلبات:*
• ⏳ قيد الانتظار: {pending}
• 🔄 قيد التنفيذ: {active}
• ✅ مكتملة: {completed}
• 📈 الإجمالي: {pending + active + completed}

اختر الخيار المطلوب:
"""
    
    keyboard = [
        [InlineKeyboardButton(f"⏳ الطلبات الجديدة ({pending})", callback_data="admin_pending_orders")],
        [InlineKeyboardButton(f"🔄 قيد التنفيذ ({active})", callback_data="admin_active_orders")],
        [InlineKeyboardButton("📋 جميع الطلبات", callback_data="admin_all_orders")],
        [InlineKeyboardButton("📊 إحصائيات الطلبات", callback_data="admin_orders_stats")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
    ]
    
    await query.edit_message_text(
        message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_view_order(query, order_id):
    """عرض تفاصيل طلب معين"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT o.*, u.username, u.first_name, u.last_name, u.balance
            FROM orders o
            JOIN users u ON o.user_id = u.user_id
            WHERE o.id = ?
        ''', (order_id,))
        
        order = cursor.fetchone()
    
    if not order:
        await query.edit_message_text("❌ الطلب غير موجود!")
        return
    
    status_icons = {
        'pending': '⏳',
        'active': '🔄',
        'completed': '✅',
        'cancelled': '❌',
        'refunded': '↩️'
    }
    
    icon = status_icons.get(order['status'], '📋')
    
    message = f"""
{icon} *طلب #{order_id}*

👤 *المعلومات الشخصية:*
• 🆔 المعرف: `{order['user_id']}`
• 👤 الاسم: {order['first_name']} {order['last_name'] or ''}
• 🌐 اليوزر: @{order['username'] or 'لا يوجد'}
• 💰 الرصيد: {order['balance']:.0f} نقطة

📦 *تفاصيل الطلب:*
• 🏷️ الخدمة: {order['service_name']}
• 🔢 الكمية: {order['amount']:,}
• 💰 السعر/1000: {order['price_per_1000']} نقطة
• 💵 الإجمالي: {order['total_price']:.2f} نقطة
• 🔗 الرابط: {order['link'] or 'لم يتم إضافته'}

📊 *الحالة:*
• 📍 الحالة: {order['status']}
• 📅 تاريخ الطلب: {format_date(order['order_date'])}
• 🕒 تاريخ البدء: {format_date(order['start_date']) or 'لم يبدأ'}
• ✅ تاريخ الإكمال: {format_date(order['completed_date']) or 'غير مكتمل'}

📝 *ملاحظات الإدارة:* {order['admin_notes'] or 'لا توجد'}
"""
    
    await query.edit_message_text(
        message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=admin_order_actions_keyboard(order_id)
    )

async def admin_approve_order(query, order_id):
    """موافقة المدير على طلب"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # تحديث حالة الطلب
        cursor.execute('''
            UPDATE orders 
            SET status = 'active', start_date = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (order_id,))
        
        # الحصول على معلومات الطلب
        cursor.execute('''
            SELECT o.*, u.user_id, u.first_name
            FROM orders o
            JOIN users u ON o.user_id = u.user_id
            WHERE o.id = ?
        ''', (order_id,))
        
        order = cursor.fetchone()
        
        conn.commit()
    
    # إرسال إشعار للمستخدم
    notification_msg = f"""
✅ *تمت الموافقة على طلبك!*

📦 *تفاصيل الطلب:*
• 🆔 رقم الطلب: #{order_id}
• 🏷️ الخدمة: {order['service_name']}
• 🔢 الكمية: {order['amount']:,}
• ⏰ الحالة: قيد التنفيذ

⏳ *سيبدأ التنفيذ خلال 24 ساعة.*
📬 *ستصلك إشعارات بالتحديثات.*
"""
    
    await send_notification(
        order['user_id'],
        'order_approved',
        '✅ طلبك قيد التنفيذ',
        notification_msg,
        order_id
    )
    
    # إشعار المدير
    await send_admin_notification(
        f"✅ تمت الموافقة على الطلب #{order_id}\n👤 المستخدم: {order['user_id']}",
        "orders"
    )
    
    await query.edit_message_text(
        f"✅ *تمت الموافقة على الطلب #{order_id} بنجاح!*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 الطلبات", callback_data="admin_orders"),
             InlineKeyboardButton("🏠 الرئيسية", callback_data="admin_panel")]
        ])
    )

# ========== نظام الفواتير PDF ==========
def create_invoice_pdf(order_id):
    """إنشاء فاتورة PDF للطلب"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT o.*, u.first_name, u.last_name, u.username, u.user_id
            FROM orders o
            JOIN users u ON o.user_id = u.user_id
            WHERE o.id = ?
        ''', (order_id,))
        
        order = cursor.fetchone()
    
    if not order:
        return None
    
    # إنشاء اسم ملف فريد
    invoice_number = f"INV-{order_id}-{datetime.now().strftime('%Y%m%d')}"
    filename = f"invoices/{invoice_number}.pdf"
    
    os.makedirs("invoices", exist_ok=True)
    
    # إنشاء المستند
    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=18
    )
    
    # المحتوى
    story = []
    
    # إضافة عنوان
    title_style = ParagraphStyle(
        'CustomTitle',
        fontName='Helvetica-Bold',
        fontSize=24,
        alignment=1,  # center
        spaceAfter=30
    )
    
    story.append(Paragraph("فاتورة شراء", title_style))
    story.append(Spacer(1, 20))
    
    # معلومات الفاتورة
    info_style = ParagraphStyle(
        'CustomText',
        fontName='Helvetica',
        fontSize=12,
        spaceAfter=12
    )
    
    invoice_info = f"""
    <b>رقم الفاتورة:</b> {invoice_number}<br/>
    <b>تاريخ الفاتورة:</b> {datetime.now().strftime('%Y/%m/%d %H:%M')}<br/>
    <b>رقم الطلب:</b> #{order_id}<br/>
    <b>حالة الطلب:</b> {order['status']}<br/>
    """
    
    story.append(Paragraph(invoice_info, info_style))
    story.append(Spacer(1, 30))
    
    # معلومات العميل
    customer_info = f"""
    <b>معلومات العميل:</b><br/>
    <b>المعرف:</b> {order['user_id']}<br/>
    <b>الاسم:</b> {order['first_name']} {order['last_name'] or ''}<br/>
    <b>اسم المستخدم:</b> @{order['username'] or 'لا يوجد'}<br/>
    """
    
    story.append(Paragraph(customer_info, info_style))
    story.append(Spacer(1, 30))
    
    # تفاصيل الخدمة
    service_info = f"""
    <b>تفاصيل الخدمة:</b><br/>
    <b>الخدمة:</b> {order['service_name']}<br/>
    <b>الكمية:</b> {order['amount']:,}<br/>
    <b>السعر لكل 1000:</b> {order['price_per_1000']} نقطة<br/>
    <b>الإجمالي:</b> {order['total_price']:.2f} نقطة<br/>
    """
    
    story.append(Paragraph(service_info, info_style))
    story.append(Spacer(1, 40))
    
    # شكر
    thanks_style = ParagraphStyle(
        'Thanks',
        fontName='Helvetica-Oblique',
        fontSize=14,
        alignment=1,
        textColor=colors.gray,
        spaceBefore=20
    )
    
    story.append(Paragraph("شكراً لتعاملك معنا!", thanks_style))
    story.append(Spacer(1, 10))
    
    story.append(Paragraph("للاستفسارات: @" + get_setting('support_username', '@SMMSupport'), info_style))
    
    # إنشاء PDF
    doc.build(story)
    
    # حفظ الفاتورة في قاعدة البيانات
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO invoices (invoice_number, order_id, user_id, amount, pdf_path)
            VALUES (?, ?, ?, ?, ?)
        ''', (invoice_number, order_id, order['user_id'], order['total_price'], filename))
        conn.commit()
    
    return filename

async def generate_invoice_callback(query, order_id):
    """إنشاء وإرسال فاتورة PDF"""
    await query.answer("جاري إنشاء الفاتورة...")
    
    # إنشاء PDF
    pdf_path = create_invoice_pdf(order_id)
    
    if not pdf_path:
        await query.edit_message_text("❌ فشل في إنشاء الفاتورة!")
        return
    
    try:
        # إرسال الملف
        with open(pdf_path, 'rb') as pdf_file:
            await query.message.reply_document(
                document=pdf_file,
                filename=f"invoice_{order_id}.pdf",
                caption=f"📄 *فاتورة الطلب #{order_id}*\n\nتم إنشاء الفاتورة بنجاح.",
                parse_mode=ParseMode.MARKDOWN
            )
        
        # تحديث حالة الفاتورة
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE invoices SET sent_date = CURRENT_TIMESTAMP
                WHERE order_id = ?
            ''', (order_id,))
            conn.commit()
        
    except Exception as e:
        logger.error(f"فشل إرسال الفاتورة: {e}")
        await query.message.reply_text("❌ فشل في إرسال الفاتورة!")

# ========== معالجات الرسائل العامة ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل النصية العامة"""
    user_id = update.effective_user.id
    message_text = update.message.text
    
    # تحديث نشاط المستخدم
    update_user_activity(user_id)
    
    # التحقق من الصيانة
    if get_setting('maintenance_mode') == '1' and user_id != ADMIN_ID:
        await update.message.reply_text("⚙️ البوت قيد الصيانة حالياً.")
        return
    
    # معالجة الأوامر النصية
    if message_text == "💰 رصيدي":
        await balance_command(update, context)
    
    elif message_text == "🎁 الهدية اليومية":
        await daily_bonus_command(update, context)
    
    elif message_text == "🛒 خدمات SMM":
        await services_command(update, context)
    
    elif message_text == "💸 تمويل قناتي":
        await channel_funding_command(update, context)
    
    elif message_text == "👥 دعوة أصدقاء":
        await show_referral_info(update, context)
    
    elif message_text == "📜 طلباتي":
        await show_user_orders(update, context)
    
    elif message_text == "🎫 شحن الرصيد":
        await show_recharge_menu_message(update, context)
    
    elif message_text == "🔔 إشعاراتي":
        await show_user_notifications(update, context)
    
    elif message_text == "ℹ️ المساعدة":
        await show_help_message(update, context)
    
    elif message_text == "📊 إحصائياتي":
        await show_user_statistics(update, context)
    
    # زر الدعم الفني المخصص
    elif "الدعم الفني" in message_text:
        support_user = get_setting('support_username', '@SMMSupport')
        await update.message.reply_text(
            f"💬 *الدعم الفني*\n\n"
            f"للتواصل مع الدعم الفني:\n"
            f"• اليوزر: {support_user}\n"
            f"• البريد: {get_setting('contact_email', 'support@smmbot.com')}\n"
            f"• القناة: {get_setting('support_channel', '@SMMSupport')}\n\n"
            f"⏰ *أوقات الدعم:* 24/7",
            parse_mode=ParseMode.MARKDOWN
        )
    
    # زر قناة البوت المخصص
    elif "قناة البوت" in message_text:
        bot_channel = get_setting('bot_channel', '@SMMBotChannel')
        await update.message.reply_text(
            f"📢 *قناة البوت الرسمية*\n\n"
            f"انضم إلى قناتنا للحصول على:\n"
            f"• آخر التحديثات\n"
            f"• العروض الخاصة\n"
            f"• الشروحات\n"
            f"• الإعلانات الهامة\n\n"
            f"🔗 الرابط: {bot_channel}",
            parse_mode=ParseMode.MARKDOWN
        )
    
    else:
        # التحقق من حالة المحادثة
        if 'awaiting_funding' in context.user_data:
            # معالجة تمويل القناة
            if context.user_data.get('funding_state') == 'url':
                await handle_funding_url(update, context)
            elif context.user_data.get('funding_state') == 'count':
                await handle_funding_count(update, context)
            elif context.user_data.get('funding_state') == 'confirm':
                await handle_funding_confirm(update, context)
        
        elif 'selected_service' in context.user_data:
            # معالجة كمية الطلب
            await handle_service_quantity(update, context)
        
        else:
            # رد افتراضي
            await update.message.reply_text(
                "👋 *مرحباً بك!*\n\n"
                "استخدم القائمة أدناه للتنقل بين خيارات البوت.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=main_menu_keyboard()
            )

async def show_referral_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض معلومات نظام الدعوة"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not user:
        await update.message.reply_text("❌ لم يتم العثور على حسابك!")
        return
    
    referral_points = get_setting('referral_points', DEFAULT_REFERRAL_POINTS)
    
    message = f"""
👥 *نظام الدعوة والأحالة*

💰 *المكافأة:* {referral_points} نقطة لكل صديق

🎯 *كيف تعمل:*
1. شارك رابط الدعوة الخاص بك مع أصدقائك
2. عندما ينضم صديق عبر رابطك
3. تحصل أنت وصديقك على {referral_points} نقطة

📊 *إحصائياتك:*
• عدد الدعوات: {user['referrals']}
• النقاط المكتسبة: {user['referrals'] * float(referral_points):.0f}

🔗 *رابط الدعوة الخاص بك:*
`https://t.me/{BOT_USERNAME}?start={user['referral_code']}`

📤 *مشاركة الرابط:*
"""
    
    keyboard = [
        [InlineKeyboardButton("📤 مشاركة الرابط", switch_inline_query=f"انضم عبر رابطي واحصل على {referral_points} نقطة مجانية!")],
        [InlineKeyboardButton("📊 أحالتي", callback_data="my_referrals"),
         InlineKeyboardButton("💰 رصيدي", callback_data="balance_menu")],
        [InlineKeyboardButton("🔙 الرئيسية", callback_data="back_to_main")]
    ]
    
    if update.message:
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.callback_query.edit_message_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def show_user_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض طلبات المستخدم"""
    user_id = update.effective_user.id
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, service_name, amount, total_price, status, order_date
            FROM orders
            WHERE user_id = ?
            ORDER BY order_date DESC
            LIMIT 10
        ''', (user_id,))
        
        orders = cursor.fetchall()
    
    if not orders:
        message = "📭 *لا توجد طلبات حتى الآن*\n\nيمكنك طلب خدمة من قسم 'خدمات SMM'"
    else:
        message = "📜 *طلباتك الأخيرة*\n\n"
        
        for order in orders:
            status_icons = {
                'pending': '⏳',
                'active': '🔄',
                'completed': '✅',
                'cancelled': '❌'
            }
            
            icon = status_icons.get(order['status'], '📋')
            message += f"{icon} *طلب #{order['id']}*\n"
            message += f"📦 {order['service_name']}\n"
            message += f"🔢 {order['amount']:,} | 💰 {order['total_price']:.2f}\n"
            message += f"📍 {order['status']} | 📅 {format_date(order['order_date'])}\n\n"
    
    keyboard = [
        [InlineKeyboardButton("🛒 طلب جديد", callback_data="services_menu")],
        [InlineKeyboardButton("📋 جميع الطلبات", callback_data="all_my_orders")],
        [InlineKeyboardButton("🔙 الرئيسية", callback_data="back_to_main")]
    ]
    
    if update.message:
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.callback_query.edit_message_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def show_recharge_menu_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة شحن الرصيد"""
    message = """
🎫 *شحن الرصيد*

💰 *طرق شحن الرصيد:*

1. 🎁 *الهدية اليومية*
   - احصل على نقاط مجانية يومياً
   - كل يوم تحصل على مكافأة أكبر

2. 👥 *دعوة الأصدقاء*
   - كل صديق ينضم عبر رابطك = نقاط لك وله
   - طريقة مربحة لزيادة رصيدك

3. 📺 *الاشتراك في القنوات*
   - اشترك في القنوات المطلوبة
   - احصل على نقاط لكل قناة

4. 💸 *تمويل قناتك*
   - ارسل رابط قناتك
   - احصل على نقاط لكل عضو جديد

5. 🎫 *أكواد الشحن*
   - استخدم أكواد الشحن من الإدارة
   - أدخل الكود واحصل على نقاط

اختر الطريقة المناسبة لك 👇
"""
    
    keyboard = [
        [InlineKeyboardButton("🎁 الهدية اليومية", callback_data="daily_bonus")],
        [InlineKeyboardButton("👥 دعوة الأصدقاء", callback_data="referral_info")],
        [InlineKeyboardButton("📺 الاشتراك بالقنوات", callback_data="channel_subscription")],
        [InlineKeyboardButton("💸 تمويل قناتي", callback_data="channel_funding_menu")],
        [InlineKeyboardButton("🎫 إدخال كود شحن", callback_data="enter_recharge_code")],
        [InlineKeyboardButton("🔙 الرئيسية", callback_data="back_to_main")]
    ]
    
    if update.message:
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.callback_query.edit_message_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# ========== الدالة الرئيسية لتشغيل البوت ==========
def main():
    """الدالة الرئيسية لتشغيل البوت"""
    # تهيئة قاعدة البيانات
    init_database()
    
    # إنشاء مجلدات التخزين
    os.makedirs("invoices", exist_ok=True)
    os.makedirs("backups", exist_ok=True)
    
    # إنشاء تطبيق البوت مع الحفاظ على الحالة
    persistence = PicklePersistence(filepath="bot_data.pickle")
    app = Application.builder() \
        .token(TOKEN) \
        .persistence(persistence) \
        .build()
    
    # إضافة معالجات الأوامر
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("daily", daily_bonus_command))
    app.add_handler(CommandHandler("services", services_command))
    app.add_handler(CommandHandler("funding", channel_funding_command))
    
    # إضافة معالجات المحادثة
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message),
            CallbackQueryHandler(handle_callback_query)
        ],
        states={
            BotStates.CHANNEL_FUNDING_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_funding_url)
            ],
            BotStates.CHANNEL_FUNDING_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_funding_count)
            ],
            BotStates.CHANNEL_FUNDING_CONFIRM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_funding_confirm)
            ],
            BotStates.SERVICE_QUANTITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_service_quantity)
            ],
            BotStates.SERVICE_CONFIRMATION: [
                CallbackQueryHandler(handle_callback_query, pattern=r'^confirm_final_\d+$'),
                CallbackQueryHandler(handle_callback_query, pattern=r'^cancel_order$'),
                CallbackQueryHandler(handle_callback_query, pattern=r'^edit_quantity_\d+$')
            ]
        },
        fallbacks=[
            CommandHandler("start", start_command),
            CommandHandler("cancel", lambda u, c: ConversationHandler.END)
        ],
        allow_reentry=True
    )
    
    app.add_handler(conv_handler)
    
    # إضافة معالجات الاستدعاء
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    
    # إضافة معالجات الرسائل
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # بدء البوت
    print("=" * 50)
    print("✅ بوت SMM يعمل الآن...")
    print(f"🤖 البوت: @{BOT_USERNAME}")
    print(f"👨‍💼 المدير: {ADMIN_ID}")
    print(f"💾 قاعدة البيانات: {DATABASE_NAME}")
    print("=" * 50)
    
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n❌ تم إيقاف البوت.")
    except Exception as e:
        logger.error(f"خطأ في تشغيل البوت: {e}")
        print(f"❌ خطأ: {e}")
