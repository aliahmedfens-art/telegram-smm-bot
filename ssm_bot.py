#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بوت يلا نتعلم - Telegram Bot for Students
مطور بواسطة: Allawi04@
الإصدار: 2.0 كامل
"""

import logging
import sqlite3
import json
import os
import asyncio
import re
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from uuid import uuid4
from io import BytesIO
from collections import defaultdict
import html

import fitz  # PyMuPDF
from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
import google.generativeai as genai
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InputFile, InputMediaDocument, InputMediaPhoto,
    WebAppInfo, MenuButtonWebApp, ChatPermissions
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, CallbackContext, ConversationHandler,
    ContextTypes, ExtBot, JobQueue
)
from telegram.constants import ParseMode, ChatAction
from telegram.error import TelegramError, BadRequest

# ========== إعدادات البوت الأساسية ==========
BOT_TOKEN = "8481569753:AAHTdbWwu0BHmoo_iHPsye8RkTptWzfiQWU"
GEMINI_API_KEY = "AIzaSyAqlug21bw_eI60ocUtc1Z76NhEUc-zuzY"
BOT_USERNAME = "@FC4Xbot"
ADMIN_USERNAME = "@Allawi04"
OWNER_ID = 6130994941  # أيدي المالك
SUPPORT_CHAT_ID = -1001234567890  # أيدي مجموعة الدعم (اختياري)

# إصدار البوت
BOT_VERSION = "2.0.0"
BOT_RELEASE_DATE = "2024"

# تسعيرة الخدمات الأساسية
DEFAULT_PRICES = {
    "exemption": 1000,    # حساب درجة الإعفاء
    "summarize": 1000,    # تلخيص PDF
    "qa": 1000,           # سؤال وجواب
    "materials": 1000,    # قسم الملازم
    "exam_generator": 1500,  # مولد أسئلة (مستقبلي)
    "plagiarism_check": 2000  # كشف الانتحال (مستقبلي)
}

# المكافآت
WELCOME_BONUS = 1000
REFERRAL_BONUS = 500
DAILY_BONUS = 100  # مكافأة يومية
WEEKLY_BONUS = 500  # مكافأة أسبوعية

# حالات المحادثة (تم توسيعها)
(
    # حالات الخدمات التعليمية
    EXEMPTION_COURSE1, EXEMPTION_COURSE2, EXEMPTION_COURSE3,
    SUMMARIZE_PDF, SUMMARIZE_OPTIONS,
    QA_QUESTION, QA_FOLLOWUP,
    MATERIALS_BROWSE, MATERIALS_SEARCH,
    
    # حالات لوحة التحكم
    ADMIN_CHARGE_USER, ADMIN_CHARGE_AMOUNT,
    ADMIN_BAN_USER, ADMIN_BAN_REASON, ADMIN_BAN_DURATION,
    ADMIN_UNBAN_USER,
    ADMIN_ADD_MATERIAL_NAME, ADMIN_ADD_MATERIAL_DESC,
    ADMIN_ADD_MATERIAL_FILE, ADMIN_ADD_MATERIAL_CATEGORY, ADMIN_ADD_MATERIAL_SUBCATEGORY,
    ADMIN_EDIT_MATERIAL, ADMIN_DELETE_MATERIAL_CONFIRM,
    ADMIN_CHANGE_PRICE_SERVICE, ADMIN_CHANGE_PRICE_AMOUNT,
    ADMIN_BROADCAST_MESSAGE, ADMIN_BROADCAST_CONFIRM,
    ADMIN_SETTINGS_MAIN, ADMIN_SETTINGS_CHANNEL, ADMIN_SETTINGS_SUPPORT,
    ADMIN_SETTINGS_WELCOME, ADMIN_SETTINGS_REFERRAL,
    ADMIN_SETTINGS_MAINTENANCE, ADMIN_SETTINGS_LANGUAGE,
    ADMIN_STATISTICS_DETAILED,
    ADMIN_BACKUP_CREATE, ADMIN_BACKUP_RESTORE,
    
    # حالات المستخدم
    USER_PROFILE_EDIT, USER_PROFILE_NAME, USER_PROFILE_BIO,
    USER_WITHDRAW_REQUEST, USER_WITHDRAW_AMOUNT, USER_WITHDRAW_METHOD,
    USER_FEEDBACK,
    USER_REPORT_PROBLEM,
    
    # حالات إضافية
    PAYMENT_CONFIRMATION,
    REFERRAL_TRACKING,
    RATE_SERVICE
) = range(50)

# إعدادات التسجيل المتقدمة
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8', mode='a'),
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            'bot_debug.log', maxBytes=10485760, backupCount=5, encoding='utf-8'
        )
    ]
)
logger = logging.getLogger(__name__)

# إعدادات خاصة للتصحيح
DEBUG_MODE = True

# ========== إدارة قاعدة البيانات المتقدمة ==========
class DatabaseManager:
    """مدير قاعدة البيانات المتقدم"""
    
    def __init__(self, db_path='bot_database.db'):
        self.db_path = db_path
        self.conn = None
        self._init_database()
    
    def _init_database(self):
        """تهيئة قاعدة البيانات مع جميع الجداول"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.cursor()
        
        # جدول المستخدمين الموسع
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                phone TEXT,
                email TEXT,
                balance INTEGER DEFAULT 0,
                referral_code TEXT UNIQUE,
                referred_by INTEGER,
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_banned INTEGER DEFAULT 0,
                ban_reason TEXT,
                ban_until TIMESTAMP,
                is_admin INTEGER DEFAULT 0,
                admin_level INTEGER DEFAULT 0,
                total_spent INTEGER DEFAULT 0,
                total_earned INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                xp INTEGER DEFAULT 0,
                daily_streak INTEGER DEFAULT 0,
                last_daily_bonus TIMESTAMP,
                settings TEXT DEFAULT '{}',
                metadata TEXT DEFAULT '{}'
            )
        ''')
        
        # جدول المعاملات الموسع
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                transaction_id TEXT UNIQUE,
                type TEXT,
                amount INTEGER,
                service TEXT,
                service_details TEXT,
                status TEXT DEFAULT 'completed',
                payment_method TEXT,
                payment_details TEXT,
                admin_id INTEGER,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # جدول إحصائيات الخدمات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS service_stats (
                service TEXT PRIMARY KEY,
                usage_count INTEGER DEFAULT 0,
                total_income INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                avg_rating REAL DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # جدول إعدادات البوت
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                category TEXT DEFAULT 'general',
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # جدول المواد التعليمية الموسع
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_id TEXT UNIQUE,
                name TEXT,
                description TEXT,
                file_id TEXT,
                file_type TEXT,
                file_size INTEGER,
                category TEXT,
                subcategory TEXT,
                tags TEXT,
                grade_level TEXT,
                subject TEXT,
                language TEXT DEFAULT 'ar',
                download_count INTEGER DEFAULT 0,
                view_count INTEGER DEFAULT 0,
                rating REAL DEFAULT 0,
                is_featured INTEGER DEFAULT 0,
                is_approved INTEGER DEFAULT 1,
                added_by INTEGER,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT DEFAULT '{}'
            )
        ''')
        
        # جدول الأسئلة والأجوبة
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS qa_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                question TEXT,
                answer TEXT,
                source TEXT,
                language TEXT,
                tokens_used INTEGER,
                processing_time REAL,
                rating INTEGER,
                feedback TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # جدول التلخيصات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                original_file TEXT,
                original_size INTEGER,
                summary_text TEXT,
                summary_file_id TEXT,
                language TEXT,
                tokens_used INTEGER,
                processing_time REAL,
                rating INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # جدول الإشعارات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT,
                title TEXT,
                message TEXT,
                data TEXT,
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # جدول الدعم الفني
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT UNIQUE,
                user_id INTEGER,
                subject TEXT,
                message TEXT,
                status TEXT DEFAULT 'open',
                priority TEXT DEFAULT 'medium',
                assigned_to INTEGER,
                resolved_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # جدول ردود الدعم
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS support_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER,
                user_id INTEGER,
                message TEXT,
                is_admin INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ticket_id) REFERENCES support_tickets (id),
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # جدول سجل النشاط
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                details TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # جدول النسخ الاحتياطي
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                backup_id TEXT UNIQUE,
                name TEXT,
                description TEXT,
                file_path TEXT,
                size INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # إنشاء الفهارس لتحسين الأداء
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_balance ON users(balance)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_referral ON users(referral_code)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_materials_category ON materials(category)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_activity_user ON activity_log(user_id, created_at)')
        
        # إدخال الإعدادات الافتراضية
        self._insert_default_settings(cursor)
        
        self.conn.commit()
        logger.info("✅ قاعدة البيانات المهيأة بنجاح")
    
    def _insert_default_settings(self, cursor):
        """إدخال الإعدادات الافتراضية"""
        default_settings = [
            # الأسعار
            ('price_exemption', '1000', 'prices', 'سعر خدمة حساب الإعفاء'),
            ('price_summarize', '1000', 'prices', 'سعر خدمة تلخيص PDF'),
            ('price_qa', '1000', 'prices', 'سعر خدمة سؤال وجواب'),
            ('price_materials', '1000', 'prices', 'سعر خدمة المواد التعليمية'),
            
            # المكافآت
            ('welcome_bonus', '1000', 'bonuses', 'الهدية الترحيبية'),
            ('referral_bonus', '500', 'bonuses', 'مكافأة الدعوة'),
            ('daily_bonus', '100', 'bonuses', 'المكافأة اليومية'),
            ('weekly_bonus', '500', 'bonuses', 'المكافأة الأسبوعية'),
            ('streak_bonus', '50', 'bonuses', 'مكافأة الاستمرارية'),
            
            # الإعدادات العامة
            ('maintenance_mode', '0', 'general', 'وضع الصيانة'),
            ('registration_open', '1', 'general', 'التسجيل مفتوح'),
            ('withdrawal_enabled', '1', 'general', 'السحب مفعل'),
            ('min_withdrawal', '5000', 'general', 'الحد الأدنى للسحب'),
            ('max_withdrawal', '1000000', 'general', 'الحد الأقصى للسحب'),
            
            # الروابط
            ('channel_url', 'https://t.me/your_channel', 'links', 'رابط القناة'),
            ('group_url', 'https://t.me/your_group', 'links', 'رابط المجموعة'),
            ('website_url', 'https://example.com', 'links', 'رابط الموقع'),
            ('support_username', '@Allawi04', 'links', 'يوزر الدعم'),
            ('support_chat_id', '', 'links', 'أيدي مجموعة الدعم'),
            
            # الإعدادات التقنية
            ('max_file_size', '10485760', 'technical', 'الحد الأقصى لحجم الملف (10MB)'),
            ('max_summary_length', '4000', 'technical', 'الحد الأقصى لطول التلخيص'),
            ('max_qa_length', '1000', 'technical', 'الحد الأقصى لطول السؤال'),
            ('session_timeout', '1800', 'technical', 'مهلة الجلسة (ثانية)'),
            ('backup_interval', '86400', 'technical', 'فترة النسخ الاحتياطي (ثانية)'),
            
            # إعدادات الذكاء الاصطناعي
            ('ai_model', 'gemini-pro', 'ai', 'نموذج الذكاء الاصطناعي'),
            ('ai_temperature', '0.7', 'ai', 'درجة الإبداع'),
            ('ai_max_tokens', '2000', 'ai', 'الحد الأقصى للرموز'),
            
            # الإعدادات الإدارية
            ('admin_notifications', '1', 'admin', 'إشعارات المديرين'),
            ('auto_backup', '1', 'admin', 'النسخ الاحتياطي التلقائي'),
            ('log_retention_days', '30', 'admin', 'فترة الاحتفاظ بالسجلات'),
            ('backup_retention_days', '7', 'admin', 'فترة الاحتفاظ بالنسخ الاحتياطية'),
            
            # إعدادات المحتوى
            ('default_language', 'ar', 'content', 'اللغة الافتراضية'),
            ('content_moderation', '1', 'content', 'مراقبة المحتوى'),
            ('auto_translate', '0', 'content', 'الترجمة التلقائية'),
            
            # إعدادات التصميم
            ('theme_color', '#0088cc', 'design', 'لون السمة'),
            ('welcome_message', 'مرحباً بك في بوت يلا نتعلم!', 'design', 'رسالة الترحيب'),
            ('footer_text', 'بوت يلا نتعلم - © 2024', 'design', 'نص التذييل'),
        ]
        
        for key, value, category, description in default_settings:
            cursor.execute('''
                INSERT OR IGNORE INTO bot_settings (key, value, category, description)
                VALUES (?, ?, ?, ?)
            ''', (key, value, category, description))
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """الحصول على بيانات مستخدم"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def create_user(self, user_data: Dict) -> bool:
        """إنشاء مستخدم جديد"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO users 
                (user_id, username, first_name, last_name, referral_code, settings)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                user_data['user_id'],
                user_data.get('username'),
                user_data.get('first_name'),
                user_data.get('last_name'),
                user_data.get('referral_code', str(uuid4())[:8]),
                json.dumps(user_data.get('settings', {}))
            ))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"خطأ في إنشاء المستخدم: {e}")
            return False
    
    def update_balance(self, user_id: int, amount: int, transaction_type: str, 
                      service: str = None, details: Dict = None) -> bool:
        """تحديث رصيد المستخدم"""
        try:
            cursor = self.conn.cursor()
            
            # تحديث رصيد المستخدم
            cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', 
                         (amount, user_id))
            
            # تحديث الإحصائيات
            if amount > 0:
                cursor.execute('UPDATE users SET total_earned = total_earned + ? WHERE user_id = ?',
                             (amount, user_id))
            elif amount < 0:
                cursor.execute('UPDATE users SET total_spent = total_spent + ? WHERE user_id = ?',
                             (abs(amount), user_id))
            
            # تسجيل المعاملة
            transaction_id = f"TX{datetime.now().strftime('%Y%m%d%H%M%S')}{user_id}"
            cursor.execute('''
                INSERT INTO transactions 
                (transaction_id, user_id, type, amount, service, service_details, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                transaction_id,
                user_id,
                transaction_type,
                amount,
                service,
                json.dumps(details) if details else None,
                'completed'
            ))
            
            # تحديث إحصائيات الخدمة إذا كانت عملية شراء
            if transaction_type == 'purchase' and service:
                cursor.execute('''
                    INSERT OR REPLACE INTO service_stats (service, usage_count, total_income)
                    VALUES (?, 
                        COALESCE((SELECT usage_count FROM service_stats WHERE service = ?), 0) + 1,
                        COALESCE((SELECT total_income FROM service_stats WHERE service = ?), 0) + ?
                    )
                ''', (service, service, service, abs(amount)))
            
            self.conn.commit()
            
            # تسجيل النشاط
            self.log_activity(user_id, 'balance_update', {
                'amount': amount,
                'type': transaction_type,
                'service': service,
                'new_balance': self.get_user(user_id)['balance']
            })
            
            return True
        except Exception as e:
            logger.error(f"خطأ في تحديث الرصيد: {e}")
            self.conn.rollback()
            return False
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """الحصول على إعداد"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT value FROM bot_settings WHERE key = ?', (key,))
        row = cursor.fetchone()
        if row:
            try:
                # محاولة تحويل القيم الرقمية
                value = row['value']
                if value.isdigit():
                    return int(value)
                elif value.replace('.', '', 1).isdigit():
                    return float(value)
                elif value.lower() in ('true', 'false'):
                    return value.lower() == 'true'
                else:
                    return value
            except:
                return row['value']
        return default
    
    def set_setting(self, key: str, value: Any, category: str = None, 
                   description: str = None) -> bool:
        """تحديث إعداد"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO bot_settings 
                (key, value, category, description, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (key, str(value), category, description))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"خطأ في تحديث الإعداد: {e}")
            return False
    
    def add_material(self, material_data: Dict) -> Optional[int]:
        """إضافة مادة تعليمية"""
        try:
            cursor = self.conn.cursor()
            material_id = f"MAT{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            cursor.execute('''
                INSERT INTO materials 
                (material_id, name, description, file_id, file_type, file_size,
                 category, subcategory, tags, grade_level, subject, language,
                 added_by, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                material_id,
                material_data['name'],
                material_data['description'],
                material_data['file_id'],
                material_data.get('file_type', 'pdf'),
                material_data.get('file_size', 0),
                material_data.get('category', 'عام'),
                material_data.get('subcategory', 'غير محدد'),
                ','.join(material_data.get('tags', [])),
                material_data.get('grade_level', 'جميع المستويات'),
                material_data.get('subject', 'عام'),
                material_data.get('language', 'ar'),
                material_data.get('added_by'),
                json.dumps(material_data.get('metadata', {}))
            ))
            
            self.conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"خطأ في إضافة المادة: {e}")
            return None
    
    def get_materials(self, filters: Dict = None, limit: int = 50, 
                     offset: int = 0) -> List[Dict]:
        """الحصول على المواد التعليمية"""
        cursor = self.conn.cursor()
        
        query = 'SELECT * FROM materials WHERE 1=1'
        params = []
        
        if filters:
            if filters.get('category'):
                query += ' AND category = ?'
                params.append(filters['category'])
            if filters.get('subcategory'):
                query += ' AND subcategory = ?'
                params.append(filters['subcategory'])
            if filters.get('subject'):
                query += ' AND subject = ?'
                params.append(filters['subject'])
            if filters.get('grade_level'):
                query += ' AND grade_level = ?'
                params.append(filters['grade_level'])
            if filters.get('language'):
                query += ' AND language = ?'
                params.append(filters['language'])
            if filters.get('is_featured'):
                query += ' AND is_featured = 1'
            if filters.get('search'):
                query += ' AND (name LIKE ? OR description LIKE ? OR tags LIKE ?)'
                search_term = f"%{filters['search']}%"
                params.extend([search_term, search_term, search_term])
        
        query += ' ORDER BY added_date DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    
    def log_activity(self, user_id: int, action: str, details: Dict = None) -> bool:
        """تسجيل نشاط المستخدم"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO activity_log (user_id, action, details)
                VALUES (?, ?, ?)
            ''', (user_id, action, json.dumps(details) if details else None))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"خطأ في تسجيل النشاط: {e}")
            return False
    
    def get_statistics(self) -> Dict:
        """الحصول على إحصائيات البوت"""
        cursor = self.conn.cursor()
        stats = {}
        
        # إحصائيات المستخدمين
        cursor.execute('SELECT COUNT(*) FROM users')
        stats['total_users'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE date(join_date) = date("now")')
        stats['new_users_today'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_banned = 1')
        stats['banned_users'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1')
        stats['admin_users'] = cursor.fetchone()[0]
        
        # إحصائيات مالية
        cursor.execute('SELECT SUM(balance) FROM users')
        stats['total_balance'] = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT SUM(total_spent) FROM users')
        stats['total_spent'] = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT SUM(total_earned) FROM users')
        stats['total_earned'] = cursor.fetchone()[0] or 0
        
        # إحصائيات المعاملات
        cursor.execute('SELECT COUNT(*) FROM transactions WHERE date(created_at) = date("now")')
        stats['transactions_today'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT SUM(amount) FROM transactions WHERE date(created_at) = date("now") AND amount > 0')
        stats['deposits_today'] = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT SUM(amount) FROM transactions WHERE date(created_at) = date("now") AND amount < 0')
        stats['withdrawals_today'] = cursor.fetchone()[0] or 0
        
        # إحصائيات الخدمات
        cursor.execute('SELECT service, usage_count, total_income FROM service_stats')
        stats['service_stats'] = [dict(row) for row in cursor.fetchall()]
        
        # إحصائيات المواد
        cursor.execute('SELECT COUNT(*) FROM materials')
        stats['total_materials'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT SUM(download_count) FROM materials')
        stats['total_downloads'] = cursor.fetchone()[0] or 0
        
        # إحصائيات النشاط
        cursor.execute('SELECT COUNT(*) FROM activity_log WHERE date(created_at) = date("now")')
        stats['activities_today'] = cursor.fetchone()[0]
        
        return stats
    
    def create_backup(self) -> Optional[str]:
        """إنشاء نسخة احتياطية"""
        try:
            backup_id = f"BKP{datetime.now().strftime('%Y%m%d%H%M%S')}"
            backup_file = f"backups/backup_{backup_id}.db"
            
            # إنشاء مجلد النسخ الاحتياطية إذا لم يكن موجوداً
            os.makedirs('backups', exist_ok=True)
            
            # نسخ قاعدة البيانات
            backup_conn = sqlite3.connect(backup_file)
            self.conn.backup(backup_conn)
            backup_conn.close()
            
            # تسجيل النسخة الاحتياطية
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO backups (backup_id, name, description, file_path, size)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                backup_id,
                f"Backup {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                f"نسخة احتياطية تلقائية",
                backup_file,
                os.path.getsize(backup_file)
            ))
            
            self.conn.commit()
            
            # حذف النسخ القديمة (احتفاظ بـ 7 أيام فقط)
            cursor.execute('''
                DELETE FROM backups 
                WHERE date(created_at) < date('now', '-7 days')
            ''')
            self.conn.commit()
            
            return backup_id
        except Exception as e:
            logger.error(f"خطأ في إنشاء النسخة الاحتياطية: {e}")
            return None

# تهيئة مدير قاعدة البيانات
db = DatabaseManager()

# ========== مدير الذكاء الاصطناعي ==========
class AIManager:
    """مدير الذكاء الاصطناعي"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.model = None
        self._init_model()
    
    def _init_model(self):
        """تهيئة نموذج الذكاء الاصطناعي"""
        try:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-pro')
            logger.info("✅ Gemini AI متصل بنجاح")
        except Exception as e:
            logger.error(f"❌ خطأ في ربط Gemini AI: {e}")
            self.model = None
    
    async def summarize_text(self, text: str, language: str = 'ar') -> Dict:
        """تلخيص النص"""
        if not self.model:
            return {"success": False, "error": "خدمة الذكاء الاصطناعي غير متاحة"}
        
        try:
            start_time = datetime.now()
            
            prompt = f"""أنت مساعد تعليمي عراقي متخصص. قم بتلخيص النص الدراسي التالي وفقاً للمعايير:
            
1. استخدم لغة عربية فصحى واضحة
2. رتب الأفكار الرئيسية بشكل هرمي
3. احذف المعلومات الثانوية وغير المهمة
4. أضف عناوين فرعية للفقرات المهمة
5. ضع النقاط الأساسية في قوائم مرقمة
6. حافظ على المصطلحات العلمية كما هي
7. اجعل التلخيص مناسباً للمراجعة السريعة

النص:
{text[:4000]}

قدم التلخيص في تقرير منظم مع مقدمة وعناوين رئيسية وختام."""
            
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt,
                generation_config={
                    'temperature': float(db.get_setting('ai_temperature', 0.7)),
                    'max_output_tokens': int(db.get_setting('ai_max_tokens', 2000)),
                }
            )
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            if response.text:
                return {
                    "success": True,
                    "summary": response.text,
                    "processing_time": processing_time,
                    "tokens_used": len(response.text.split()),
                    "language": language
                }
            else:
                return {"success": False, "error": "لم أتمكن من توليد التلخيص"}
                
        except Exception as e:
            logger.error(f"خطأ في التلخيص: {e}")
            return {"success": False, "error": str(e)}
    
    async def answer_question(self, question: str, context: str = None, 
                            language: str = 'ar') -> Dict:
        """الإجابة على الأسئلة"""
        if not self.model:
            return {"success": False, "error": "خدمة الذكاء الاصطناعي غير متاحة"}
        
        try:
            start_time = datetime.now()
            
            prompt = f"""أنت معلم عراقي متخصص في المناهج الدراسية العراقية.
            
السؤال: {question}

{context if context else ""}

قدم إجابة علمية دقيقة وفقاً للمعايير:
1. مناسبة للمناهج العراقية
2. بلغة عربية واضحة وسلسة
3. مع أمثلة توضيحية إذا لزم الأمر
4. مختصرة وشاملة في نفس الوقت
5. مع ذكر المصادر أو المراجع العلمية
6. إذا كان السؤال يحتاج لرسم أو جدول، صفه نصياً

إذا كان السؤال غير واضح، اطلب توضيحاً."""
            
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt,
                generation_config={
                    'temperature': float(db.get_setting('ai_temperature', 0.7)),
                    'max_output_tokens': int(db.get_setting('ai_max_tokens', 2000)),
                }
            )
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            if response.text:
                return {
                    "success": True,
                    "answer": response.text,
                    "processing_time": processing_time,
                    "tokens_used": len(response.text.split()),
                    "language": language
                }
            else:
                return {"success": False, "error": "لم أتمكن من توليد الإجابة"}
                
        except Exception as e:
            logger.error(f"خطأ في الإجابة: {e}")
            return {"success": False, "error": str(e)}

# تهيئة مدير الذكاء الاصطناعي
ai_manager = AIManager(GEMINI_API_KEY)

# ========== مدير ملفات PDF ==========
class PDFManager:
    """مدير ملفات PDF"""
    
    @staticmethod
    def extract_text(pdf_path: str) -> str:
        """استخراج النص من PDF"""
        try:
            doc = fitz.open(pdf_path)
            text = ""
            
            for page_num, page in enumerate(doc):
                text += f"\n{'='*50}\nالصفحة {page_num + 1}\n{'='*50}\n"
                page_text = page.get_text()
                # تنظيف النص
                page_text = re.sub(r'\s+', ' ', page_text)
                text += page_text + "\n"
            
            doc.close()
            logger.info(f"تم استخراج نص من PDF: {len(text)} حرف")
            return text
        except Exception as e:
            logger.error(f"خطأ في استخراج النص: {e}")
            return f"خطأ في قراءة الملف: {str(e)}"
    
    @staticmethod
    def create_summary_pdf(content: str, title: str = "ملخص دراسي", 
                          author: str = "بوت يلا نتعلم") -> BytesIO:
        """إنشاء PDF ملخص"""
        buffer = BytesIO()
        
        try:
            # إعداد المستند
            doc = SimpleDocTemplate(buffer, pagesize=A4, 
                                   rightMargin=72, leftMargin=72,
                                   topMargin=72, bottomMargin=72)
            
            # الأنماط
            styles = getSampleStyleSheet()
            
            # نمط العنوان
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=18,
                alignment=TA_CENTER,
                textColor=colors.HexColor('#2E86C1'),
                spaceAfter=30
            )
            
            # نمط النص العربي
            arabic_style = ParagraphStyle(
                'ArabicStyle',
                parent=styles['Normal'],
                fontSize=12,
                alignment=TA_RIGHT,
                textColor=colors.black,
                spaceAfter=12,
                wordWrap='CJK'
            )
            
            # نمط العنوان الفرعي
            subtitle_style = ParagraphStyle(
                'SubtitleStyle',
                parent=styles['Heading2'],
                fontSize=14,
                alignment=TA_RIGHT,
                textColor=colors.HexColor('#3498DB'),
                spaceBefore=20,
                spaceAfter=15
            )
            
            # بناء المحتوى
            story = []
            
            # العنوان الرئيسي
            story.append(Paragraph(f"<b>{title}</b>", title_style))
            story.append(Spacer(1, 20))
            
            # معلومات المستند
            info_text = f"""
            <font size="10">
            <b>المؤلف:</b> {author}<br/>
            <b>تاريخ الإنشاء:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}<br/>
            <b>المصدر:</b> بوت يلا نتعلم (@FC4Xbot)<br/>
            <b>الدعم:</b> {db.get_setting('support_username', '@Allawi04')}
            </font>
            """
            story.append(Paragraph(info_text, arabic_style))
            story.append(Spacer(1, 30))
            
            # خط فاصل
            story.append(Paragraph("<hr/>", styles['Normal']))
            story.append(Spacer(1, 30))
            
            # تقسيم المحتوى إلى فقرات
            sections = content.split('\n\n')
            
            for section in sections:
                if section.strip():
                    # التحقق إذا كان العنوان
                    if len(section) < 100 and ':' not in section and '.' not in section:
                        story.append(Paragraph(f"<b>{section.strip()}</b>", subtitle_style))
                    else:
                        # تنظيف النص
                        clean_text = section.strip()
                        clean_text = re.sub(r'\s+', ' ', clean_text)
                        clean_text = html.escape(clean_text)
                        
                        story.append(Paragraph(clean_text, arabic_style))
                        story.append(Spacer(1, 10))
            
            # تذييل الصفحة
            story.append(Spacer(1, 50))
            footer_text = f"""
            <font size="8" color="gray">
            <b>بوت يلا نتعلم</b> - مساعدك الدراسي الذكي<br/>
            {db.get_setting('footer_text', '© 2024 جميع الحقوق محفوظة')}
            </font>
            """
            story.append(Paragraph(footer_text, arabic_style))
            
            # بناء المستند
            doc.build(story)
            buffer.seek(0)
            
            logger.info(f"تم إنشاء PDF: {title}")
            return buffer
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء PDF: {e}")
            # نسخة احتياطية بسيطة
            return PDFManager._create_simple_pdf(content, title)
    
    @staticmethod
    def _create_simple_pdf(content: str, title: str) -> BytesIO:
        """إنشاء PDF بسيط (نسخة احتياطية)"""
        buffer = BytesIO()
        
        try:
            c = canvas.Canvas(buffer, pagesize=A4)
            width, height = A4
            
            # العنوان
            c.setFont("Helvetica-Bold", 16)
            c.drawCentredString(width/2, height - 50, title)
            
            # التاريخ
            c.setFont("Helvetica", 10)
            c.drawString(50, height - 80, f"التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            
            # المحتوى
            c.setFont("Helvetica", 12)
            y = height - 120
            lines = content.split('\n')
            
            for line in lines:
                if y < 50:
                    c.showPage()
                    c.setFont("Helvetica", 12)
                    y = height - 50
                
                # تقسيم الخط الطويل
                if len(line) > 100:
                    words = line.split()
                    current_line = []
                    line_text = ""
                    
                    for word in words:
                        if len(' '.join(current_line + [word])) <= 80:
                            current_line.append(word)
                        else:
                            c.drawString(50, y, ' '.join(current_line))
                            y -= 20
                            current_line = [word]
                    
                    if current_line:
                        c.drawString(50, y, ' '.join(current_line))
                        y -= 20
                else:
                    c.drawString(50, y, line[:90])
                    y -= 20
            
            # التذييل
            c.setFont("Helvetica", 8)
            c.drawCentredString(width/2, 30, "بوت يلا نتعلم - @FC4Xbot")
            
            c.save()
            buffer.seek(0)
            return buffer
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء PDF بسيط: {e}")
            return None

# ========== مدير المستخدمين ==========
class UserManager:
    """مدير المستخدمين"""
    
    @staticmethod
    async def register_user(update: Update, context: CallbackContext) -> Dict:
        """تسجيل مستخدم جديد"""
        user = update.effective_user
        user_id = user.id
        
        # التحقق من وضع الصيانة
        if db.get_setting('maintenance_mode') == '1' and user_id != OWNER_ID:
            return {"success": False, "error": "البوت في وضع الصيانة"}
        
        # التحقق من فتح التسجيل
        if db.get_setting('registration_open') != '1' and user_id != OWNER_ID:
            return {"success": False, "error": "التسجيل مغلق حالياً"}
        
        # التحقق من الحظر
        existing_user = db.get_user(user_id)
        if existing_user and existing_user.get('is_banned'):
            ban_reason = existing_user.get('ban_reason', 'غير محدد')
            ban_until = existing_user.get('ban_until')
            
            if ban_until:
                try:
                    ban_date = datetime.fromisoformat(ban_until)
                    if ban_date > datetime.now():
                        return {
                            "success": False,
                            "error": f"حسابك محظور حتى {ban_date.strftime('%Y-%m-%d %H:%M')}\nالسبب: {ban_reason}"
                        }
                except:
                    pass
        
        # إنشاء أو تحديث المستخدم
        user_data = {
            'user_id': user_id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'referral_code': str(uuid4())[:8]
        }
        
        is_new_user = False
        if not existing_user:
            is_new_user = True
            db.create_user(user_data)
            
            # منح الهدية الترحيبية
            welcome_bonus = int(db.get_setting('welcome_bonus', WELCOME_BONUS))
            if welcome_bonus > 0:
                db.update_balance(user_id, welcome_bonus, 'bonus', 'welcome')
            
            # تسجيل النشاط
            db.log_activity(user_id, 'user_registered')
        
        # معالجة رابط الدعوة
        if context.args and context.args[0].startswith('ref_'):
            referral_code = context.args[0][4:]
            
            # البحث عن المدعو
            cursor = db.conn.cursor()
            cursor.execute('SELECT user_id FROM users WHERE referral_code = ?', (referral_code,))
            referrer = cursor.fetchone()
            
            if referrer and referrer['user_id'] != user_id:
                # منح مكافأة الدعوة للمدعو
                referral_bonus = int(db.get_setting('referral_bonus', REFERRAL_BONUS))
                if referral_bonus > 0:
                    db.update_balance(referrer['user_id'], referral_bonus, 'referral')
                
                # تحديث المرجع
                cursor.execute('UPDATE users SET referred_by = ? WHERE user_id = ?', 
                             (referrer['user_id'], user_id))
                db.conn.commit()
                
                # إرسال إشعار للمدعو
                try:
                    await context.bot.send_message(
                        referrer['user_id'],
                        f"🎉 <b>مبروك!</b> لقد قام صديقك بالتسجيل عبر رابط دعوتك!\n"
                        f"💰 تم إضافة {format_money(referral_bonus)} إلى رصيدك.",
                        parse_mode=ParseMode.HTML
                    )
                except:
                    pass
        
        # تحديث وقت النشاط الأخير
        cursor = db.conn.cursor()
        cursor.execute('UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?', 
                     (user_id,))
        db.conn.commit()
        
        return {
            "success": True,
            "is_new_user": is_new_user,
            "user_id": user_id,
            "welcome_bonus": int(db.get_setting('welcome_bonus', WELCOME_BONUS)) if is_new_user else 0
        }
    
    @staticmethod
    def format_money(amount: int) -> str:
        """تنسيق المبالغ المالية"""
        return f"{amount:,} دينار عراقي"
    
    @staticmethod
    async def check_service_access(update: Update, service: str, 
                                 context: CallbackContext = None) -> bool:
        """التحقق من إمكانية الوصول للخدمة"""
        user_id = update.effective_user.id if isinstance(update, Update) else update.from_user.id
        
        # التحقق من وضع الصيانة
        if db.get_setting('maintenance_mode') == '1' and user_id != OWNER_ID:
            msg = "⚙️ البوت في وضع الصيانة حالياً. الرجاء المحاولة لاحقاً."
            if isinstance(update, Update):
                await update.message.reply_text(msg)
            else:
                await update.edit_message_text(msg)
            return False
        
        # التحقق من الحظر
        user = db.get_user(user_id)
        if user and user.get('is_banned'):
            ban_reason = user.get('ban_reason', 'غير محدد')
            msg = f"🚫 حسابك محظور.\nالسبب: {ban_reason}"
            
            if isinstance(update, Update):
                await update.message.reply_text(msg)
            else:
                await update.edit_message_text(msg)
            return False
        
        # التحقق من الرصيد
        price_key = f'price_{service}'
        price = int(db.get_setting(price_key, DEFAULT_PRICES.get(service, 1000)))
        
        if user['balance'] < price:
            msg = (
                f"⚠️ <b>رصيدك غير كافٍ</b>\n\n"
                f"💰 سعر الخدمة: {UserManager.format_money(price)}\n"
                f"💵 رصيدك الحالي: {UserManager.format_money(user['balance'])}\n\n"
                f"للتعبئة راسل الدعم: {db.get_setting('support_username', '@Allawi04')}"
            )
            
            if isinstance(update, Update):
                await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
            else:
                await update.edit_message_text(msg, parse_mode=ParseMode.HTML)
            return False
        
        # خصم المبلغ
        db.update_balance(user_id, -price, 'purchase', service)
        
        # إرسال إشعار الخصم
        new_balance = user['balance'] - price
        notice = (
            f"✅ تم خصم {UserManager.format_money(price)} لخدمة {service}\n"
            f"💰 الرصيد المتبقي: {UserManager.format_money(new_balance)}"
        )
        
        try:
            if isinstance(update, Update):
                await update.message.reply_text(notice)
            else:
                await update.answer(notice, show_alert=False)
        except:
            pass
        
        # تسجيل النشاط
        db.log_activity(user_id, 'service_purchased', {
            'service': service,
            'price': price,
            'new_balance': new_balance
        })
        
        return True

# ========== واجهة المستخدم ==========
class UIManager:
    """مدير واجهة المستخدم"""
    
    @staticmethod
    def get_main_menu(user_id: int) -> InlineKeyboardMarkup:
        """القائمة الرئيسية"""
        keyboard = [
            [
                InlineKeyboardButton("📊 حساب الإعفاء", callback_data="service_exemption"),
                InlineKeyboardButton("📝 تلخيص PDF", callback_data="service_summarize")
            ],
            [
                InlineKeyboardButton("❓ سؤال وجواب", callback_data="service_qa"),
                InlineKeyboardButton("📚 المواد التعليمية", callback_data="service_materials")
            ],
            [
                InlineKeyboardButton("💰 رصيدي", callback_data="user_balance"),
                InlineKeyboardButton("👥 الدعوة", callback_data="user_referral"),
                InlineKeyboardButton("⚙️ الملف الشخصي", callback_data="user_profile")
            ],
            [
                InlineKeyboardButton("ℹ️ معلومات", callback_data="bot_info"),
                InlineKeyboardButton("📞 الدعم", callback_data="user_support")
            ]
        ]
        
        if user_id == OWNER_ID or (db.get_user(user_id) and db.get_user(user_id).get('is_admin')):
            keyboard.append([
                InlineKeyboardButton("👑 لوحة التحكم", callback_data="admin_panel")
            ])
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def get_admin_menu() -> InlineKeyboardMarkup:
        """قائمة لوحة التحكم"""
        keyboard = [
            [
                InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats"),
                InlineKeyboardButton("👥 المستخدمين", callback_data="admin_users")
            ],
            [
                InlineKeyboardButton("💰 الشحن", callback_data="admin_charge"),
                InlineKeyboardButton("🚫 الحظر", callback_data="admin_ban")
            ],
            [
                InlineKeyboardButton("📁 المواد", callback_data="admin_materials"),
                InlineKeyboardButton("⚙️ الأسعار", callback_data="admin_prices")
            ],
            [
                InlineKeyboardButton("📢 الإشعارات", callback_data="admin_broadcast"),
                InlineKeyboardButton("🔧 الإعدادات", callback_data="admin_settings")
            ],
            [
                InlineKeyboardButton("💾 النسخ الاحتياطي", callback_data="admin_backup"),
                InlineKeyboardButton("📋 السجلات", callback_data="admin_logs")
            ],
            [
                InlineKeyboardButton("🔙 الرئيسية", callback_data="back_to_main")
            ]
        ]
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def get_materials_menu(materials: List[Dict], page: int = 0, 
                          total_pages: int = 1) -> InlineKeyboardMarkup:
        """قائمة المواد التعليمية"""
        keyboard = []
        
        for material in materials:
            keyboard.append([
                InlineKeyboardButton(
                    f"📄 {material['name'][:30]}",
                    callback_data=f"material_{material['id']}"
                )
            ])
        
        # أزرار التنقل بين الصفحات
        navigation = []
        if page > 0:
            navigation.append(InlineKeyboardButton("◀️ السابق", callback_data=f"materials_page_{page-1}"))
        
        navigation.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="materials_info"))
        
        if page < total_pages - 1:
            navigation.append(InlineKeyboardButton("التالي ▶️", callback_data=f"materials_page_{page+1}"))
        
        if navigation:
            keyboard.append(navigation)
        
        keyboard.append([
            InlineKeyboardButton("🔍 بحث", callback_data="materials_search"),
            InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
        ])
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    async def send_welcome_message(update: Update, context: CallbackContext, 
                                 user_data: Dict) -> None:
        """إرسال رسالة الترحيب"""
        user = update.effective_user
        welcome_bonus = user_data.get('welcome_bonus', 0)
        
        welcome_text = f"""
🎓 <b>مرحباً بك في بوت 'يلا نتعلم' {user.first_name}!</b>

{db.get_setting('welcome_message', 'مساعدك الدراسي الذكي')}

💰 <b>رصيدك الحالي:</b> {UserManager.format_money(user_data.get('balance', 0))}
🆔 <b>الأيدي الخاص بك:</b> {user.id}

🎁 <b>الهدية الترحيبية:</b> {UserManager.format_money(welcome_bonus) if welcome_bonus > 0 else 'غير متاحة'}

🔗 <b>رابط الدعوة:</b>
https://t.me/FC4Xbot?start=ref_{user_data.get('referral_code', '')}

💸 <b>مكافأة كل دعوة:</b> {UserManager.format_money(int(db.get_setting('referral_bonus', REFERRAL_BONUS)))}

📌 <b>الخدمات المتاحة:</b>
• حساب درجة الإعفاء - {UserManager.format_money(int(db.get_setting('price_exemption', 1000)))}
• تلخيص الملازم - {UserManager.format_money(int(db.get_setting('price_summarize', 1000)))}
• سؤال وجواب - {UserManager.format_money(int(db.get_setting('price_qa', 1000)))}
• المواد التعليمية - {UserManager.format_money(int(db.get_setting('price_materials', 1000)))}

📢 <b>قناتنا:</b> {db.get_setting('channel_url', 'قناة البوت')}
👨‍💻 <b>الدعم الفني:</b> {db.get_setting('support_username', '@Allawi04')}
        """
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=UIManager.get_main_menu(user.id),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )

# ========== Handlers الأساسية ==========
async def start_command(update: Update, context: CallbackContext):
    """معالجة أمر /start"""
    try:
        # تسجيل المستخدم
        registration = await UserManager.register_user(update, context)
        
        if not registration['success']:
            await update.message.reply_text(registration['error'])
            return
        
        # الحصول على بيانات المستخدم
        user_data = db.get_user(update.effective_user.id)
        
        # إرسال رسالة الترحيب
        await UIManager.send_welcome_message(update, context, user_data)
        
    except Exception as e:
        logger.error(f"خطأ في أمر /start: {e}")
        await update.message.reply_text(
            "حدث خطأ في المعالجة. الرجاء المحاولة مرة أخرى.",
            reply_markup=ReplyKeyboardRemove()
        )

async def button_callback_handler(update: Update, context: CallbackContext):
    """معالجة أزرار Inline"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    try:
        if data == "back_to_main":
            await return_to_main_menu(query)
        
        elif data.startswith("service_"):
            await handle_service_selection(query, context, data)
        
        elif data.startswith("user_"):
            await handle_user_actions(query, context, data)
        
        elif data.startswith("admin_"):
            await handle_admin_actions(query, context, data)
        
        elif data.startswith("material_"):
            await handle_material_selection(query, context, data)
        
        elif data.startswith("materials_page_"):
            await handle_materials_pagination(query, context, data)
        
        elif data == "bot_info":
            await show_bot_info(query)
        
        elif data == "user_support":
            await show_support_info(query)
    
    except Exception as e:
        logger.error(f"خطأ في معالجة الزر: {data} - {e}")
        await query.edit_message_text(
            "حدث خطأ في المعالجة. الرجاء المحاولة مرة أخرى.",
            reply_markup=UIManager.get_main_menu(user_id)
        )

async def return_to_main_menu(query):
    """العودة للقائمة الرئيسية"""
    user_id = query.from_user.id
    user_data = db.get_user(user_id)
    
    welcome_text = f"""
🎓 <b>مرحباً بك في بوت 'يلا نتعلم'!</b>

💰 <b>رصيدك الحالي:</b> {UserManager.format_money(user_data.get('balance', 0) if user_data else 0)}
🆔 <b>الأيدي الخاص بك:</b> {user_id}
    """
    
    await query.edit_message_text(
        welcome_text,
        reply_markup=UIManager.get_main_menu(user_id),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

# ========== معالجة الخدمات ==========
async def handle_service_selection(query, context, data):
    """معالجة اختيار الخدمة"""
    service = data.replace("service_", "")
    
    if service == "exemption":
        await start_exemption_service(query, context)
    elif service == "summarize":
        await start_summarize_service(query, context)
    elif service == "qa":
        await start_qa_service(query, context)
    elif service == "materials":
        await show_materials_list(query, context)

async def start_exemption_service(query, context):
    """بدء خدمة حساب الإعفاء"""
    if await UserManager.check_service_access(query, 'exemption', context):
        await query.edit_message_text(
            "📊 <b>حساب درجة الإعفاء</b>\n\n"
            "أدخل <b>درجة الكورس الأول</b> (0-100):",
            parse_mode=ParseMode.HTML
        )
        context.user_data['service'] = 'exemption'
        return EXEMPTION_COURSE1
    return ConversationHandler.END

async def start_summarize_service(query, context):
    """بدء خدمة تلخيص PDF"""
    if await UserManager.check_service_access(query, 'summarize', context):
        await query.edit_message_text(
            "📝 <b>تلخيص الملازم</b>\n\n"
            "⏳ الرجاء إرسال ملف PDF الآن:\n"
            "<i>يمكن أن يستغرق التلخيص بضع دقائق</i>",
            parse_mode=ParseMode.HTML
        )
        context.user_data['service'] = 'summarize'
        return SUMMARIZE_PDF
    return ConversationHandler.END

async def start_qa_service(query, context):
    """بدء خدمة سؤال وجواب"""
    if await UserManager.check_service_access(query, 'qa', context):
        await query.edit_message_text(
            "❓ <b>سؤال وجواب</b>\n\n"
            "🧠 يمكنني الإجابة على أسئلتك الدراسية باستخدام الذكاء الاصطناعي\n\n"
            "📝 <b>أرسل سؤالك الآن:</b>\n"
            "<i>يمكن أن يكون نصاً أو صورة تحتوي على سؤال</i>",
            parse_mode=ParseMode.HTML
        )
        context.user_data['service'] = 'qa'
        return QA_QUESTION
    return ConversationHandler.END

# ========== معالجة إدخالات الخدمات ==========
async def process_exemption_course1(update: Update, context: CallbackContext):
    """معالجة درجة الكورس الأول"""
    try:
        score = float(update.message.text)
        if 0 <= score <= 100:
            context.user_data['course1'] = score
            await update.message.reply_text(
                f"✅ تم حفظ درجة الكورس الأول: {score}\n\n"
                "أدخل <b>درجة الكورس الثاني</b> (0-100):",
                parse_mode=ParseMode.HTML
            )
            return EXEMPTION_COURSE2
    except ValueError:
        pass
    
    await update.message.reply_text(
        "❌ الرجاء إدخال رقم بين 0 و 100:",
        parse_mode=ParseMode.HTML
    )
    return EXEMPTION_COURSE1

async def process_exemption_course2(update: Update, context: CallbackContext):
    """معالجة درجة الكورس الثاني"""
    try:
        score = float(update.message.text)
        if 0 <= score <= 100:
            context.user_data['course2'] = score
            await update.message.reply_text(
                f"✅ تم حفظ درجة الكورس الثاني: {score}\n\n"
                "أدخل <b>درجة الكورس الثالث</b> (0-100):",
                parse_mode=ParseMode.HTML
            )
            return EXEMPTION_COURSE3
    except ValueError:
        pass
    
    await update.message.reply_text(
        "❌ الرجاء إدخال رقم بين 0 و 100:",
        parse_mode=ParseMode.HTML
    )
    return EXEMPTION_COURSE2

async def process_exemption_course3(update: Update, context: CallbackContext):
    """معالجة درجة الكورس الثالث وحساب النتيجة"""
    try:
        score = float(update.message.text)
        if 0 <= score <= 100:
            course1 = context.user_data.get('course1', 0)
            course2 = context.user_data.get('course2', 0)
            course3 = score
            
            # حساب المعدل
            average = (course1 + course2 + course3) / 3
            
            # إعداد النتيجة
            if average >= 90:
                result = "🎉 <b>مبروك! أنت معفي من المادة</b> 🎉"
                emoji = "✅"
            else:
                result = "📝 <b>أنت غير معفي من المادة</b>"
                emoji = "❌"
            
            # بناء رسالة النتيجة
            result_msg = f"""
{emoji} <b>نتيجة حساب الإعفاء</b> {emoji}

📊 <b>الدرجات المدخلة:</b>
• الكورس الأول: {course1}
• الكورس الثاني: {course2}
• الكورس الثالث: {course3}

⚖️ <b>المعدل العام:</b> {average:.2f}

{result}

{"🎯 تحتاج إلى " + f"{(90 - average):.2f}" + " درجة إضافية للإعفاء" if average < 90 else "🎊 تهانينا على هذا الإنجاز!"}

📌 <b>ملاحظة:</b> هذا الحساب لأغراض تقريبية، الرجاء التأكد من لوائح جامعتك.
            """
            
            await update.message.reply_text(
                result_msg,
                parse_mode=ParseMode.HTML,
                reply_markup=UIManager.get_main_menu(update.effective_user.id)
            )
            
            # تسجيل النشاط
            db.log_activity(update.effective_user.id, 'exemption_calculated', {
                'scores': [course1, course2, course3],
                'average': average,
                'result': 'exempt' if average >= 90 else 'not_exempt'
            })
            
            # مسح بيانات المحادثة
            context.user_data.clear()
            return ConversationHandler.END
    except ValueError:
        pass
    
    await update.message.reply_text(
        "❌ الرجاء إدخال رقم بين 0 و 100:",
        parse_mode=ParseMode.HTML
    )
    return EXEMPTION_COURSE3

async def process_pdf_summarize(update: Update, context: CallbackContext):
    """معالجة ملف PDF للتلخيص"""
    if update.message.document and 'pdf' in update.message.document.mime_type.lower():
        processing_msg = await update.message.reply_text(
            "⏳ <b>جاري معالجة الملف وتلخيصه...</b>\n"
            "قد يستغرق ذلك من 30 ثانية إلى دقيقة.",
            parse_mode=ParseMode.HTML
        )
        
        try:
            user_id = update.effective_user.id
            
            # تحميل الملف
            file = await context.bot.get_file(update.message.document.file_id)
            file_path = f"temp_{file.file_id}.pdf"
            await file.download_to_drive(file_path)
            
            # استخراج النص من PDF
            pdf_text = PDFManager.extract_text(file_path)
            
            if len(pdf_text) < 50:
                await processing_msg.edit_text("❌ الملف فارغ أو لا يمكن قراءته.")
                os.remove(file_path)
                return SUMMARIZE_PDF
            
            # التلخيص باستخدام الذكاء الاصطناعي
            await processing_msg.edit_text(
                "🤖 <b>جاري تلخيص المحتوى باستخدام الذكاء الاصطناعي...</b>",
                parse_mode=ParseMode.HTML
            )
            
            summary_result = await ai_manager.summarize_text(pdf_text)
            
            if not summary_result['success']:
                await processing_msg.edit_text(f"❌ {summary_result['error']}")
                os.remove(file_path)
                return SUMMARIZE_PDF
            
            # إنشاء PDF ملخص
            await processing_msg.edit_text(
                "📄 <b>جاري إنشاء ملف PDF ملخص...</b>",
                parse_mode=ParseMode.HTML
            )
            
            pdf_buffer = PDFManager.create_summary_pdf(
                summary_result['summary'],
                "ملخص دراسي",
                f"بوت يلا نتعلم - {update.effective_user.first_name}"
            )
            
            if pdf_buffer:
                # إرسال الملف
                await update.message.reply_document(
                    document=InputFile(pdf_buffer, filename="ملخص_دراسي.pdf"),
                    caption=(
                        "📚 <b>ملخص دراسي جاهز</b>\n\n"
                        "✅ تم تلخيص الملف بنجاح\n"
                        f"📊 حجم النص الأصلي: {len(pdf_text)} حرف\n"
                        f"⏱ وقت المعالجة: {summary_result['processing_time']:.1f} ثانية\n"
                        f"🎯 تم التركيز على النقاط الرئيسية\n\n"
                        "شكراً لاستخدامك بوت 'يلا نتعلم'! 🎓"
                    ),
                    parse_mode=ParseMode.HTML
                )
                pdf_buffer.close()
                
                # تسجيل النشاط
                db.log_activity(user_id, 'pdf_summarized', {
                    'file_size': update.message.document.file_size,
                    'original_length': len(pdf_text),
                    'summary_length': len(summary_result['summary']),
                    'processing_time': summary_result['processing_time']
                })
            else:
                # إرسال النص فقط إذا فشل إنشاء PDF
                await update.message.reply_text(
                    f"📝 <b>ملخص المحتوى:</b>\n\n{summary_result['summary'][:3000]}...\n\n"
                    "📌 <i>تم قص النص بسبب طوله، للحصول على النسخة الكاملة راجع الملف الأصلي.</i>",
                    parse_mode=ParseMode.HTML
                )
            
            # تنظيف الملفات المؤقتة
            os.remove(file_path)
            await processing_msg.delete()
            
        except Exception as e:
            logger.error(f"خطأ في معالجة PDF: {e}")
            await processing_msg.edit_text(f"❌ حدث خطأ في المعالجة: {str(e)}")
            return SUMMARIZE_PDF
        
        await update.message.reply_text(
            "✅ تم الانتهاء من التلخيص.",
            reply_markup=UIManager.get_main_menu(update.effective_user.id)
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "❌ الرجاء إرسال ملف PDF فقط.",
        parse_mode=ParseMode.HTML
    )
    return SUMMARIZE_PDF

async def process_qa_question(update: Update, context: CallbackContext):
    """معالجة سؤال المستخدم"""
    question = update.message.text
    
    if question.lower() in ['إلغاء', 'cancel', 'الغاء']:
        await update.message.reply_text(
            "تم إلغاء خدمة سؤال وجواب.",
            reply_markup=UIManager.get_main_menu(update.effective_user.id)
        )
        return ConversationHandler.END
    
    if len(question) < 5:
        await update.message.reply_text(
            "❌ <b>السؤال قصير جداً</b>\n\n"
            "الرجاء كتابة سؤال واضح ومفصل:",
            parse_mode=ParseMode.HTML
        )
        return QA_QUESTION
    
    processing_msg = await update.message.reply_text(
        "🤖 <b>جاري تحليل السؤال وإعداد الإجابة...</b>\n"
        "قد يستغرق ذلك بضع ثوانٍ.",
        parse_mode=ParseMode.HTML
    )
    
    try:
        # الحصول على الإجابة باستخدام الذكاء الاصطناعي
        answer_result = await ai_manager.answer_question(question)
        
        if not answer_result['success']:
            await processing_msg.edit_text(f"❌ {answer_result['error']}")
            return QA_QUESTION
        
        await processing_msg.delete()
        
        # إرسال الإجابة
        await update.message.reply_text(
            f"💡 <b>إجابة على سؤالك:</b>\n\n{answer_result['answer']}\n\n"
            f"📌 <i>تمت الإجابة باستخدام الذكاء الاصطناعي المتخصص في المناهج العراقية</i>",
            parse_mode=ParseMode.HTML
        )
        
        # تسجيل السؤال والإجابة
        db.log_activity(update.effective_user.id, 'qa_answered', {
            'question_length': len(question),
            'answer_length': len(answer_result['answer']),
            'processing_time': answer_result['processing_time']
        })
        
    except Exception as e:
        logger.error(f"خطأ في الإجابة على السؤال: {e}")
        await processing_msg.edit_text(
            f"❌ <b>حدث خطأ في معالجة السؤال:</b>\n{str(e)}\n\n"
            f"الرجاء المحاولة مرة أخرى أو إعادة صياغة السؤال.",
            parse_mode=ParseMode.HTML
        )
        return QA_QUESTION
    
    await update.message.reply_text(
        "✅ تم الانتهاء من الإجابة على السؤال.\n"
        "يمكنك إرسال سؤال جديد أو العودة للرئيسية.",
        reply_markup=UIManager.get_main_menu(update.effective_user.id)
    )
    return ConversationHandler.END

# ========== المواد التعليمية ==========
async def show_materials_list(query, context, page: int = 0):
    """عرض قائمة المواد التعليمية"""
    materials = db.get_materials(limit=10, offset=page * 10)
    total_materials = len(db.get_materials())
    total_pages = math.ceil(total_materials / 10) if total_materials > 0 else 1
    
    if not materials:
        await query.edit_message_text(
            "📚 <b>ملازمي ومرشحاتي</b>\n\n"
            "⚠️ لا توجد مواد متاحة حالياً.\n"
            "سيتم إضافة المواد قريباً من قبل الإدارة.",
            parse_mode=ParseMode.HTML,
            reply_markup=UIManager.get_main_menu(query.from_user.id)
        )
        return
    
    materials_text = "📚 <b>ملازمي ومرشحاتي</b>\n\n"
    materials_text += f"📄 <b>إجمالي المواد:</b> {total_materials}\n"
    materials_text += f"📖 <b>الصفحة:</b> {page + 1} من {total_pages}\n\n"
    
    for i, material in enumerate(materials, 1):
        materials_text += f"{i}. <b>{material['name']}</b>\n"
        materials_text += f"   📁 {material['category']} | 📊 {material['download_count']} تحميل\n\n"
    
    await query.edit_message_text(
        materials_text,
        parse_mode=ParseMode.HTML,
        reply_markup=UIManager.get_materials_menu(materials, page, total_pages)
    )

async def handle_material_selection(query, context, data):
    """معالجة اختيار مادة"""
    material_id = int(data.replace("material_", ""))
    
    cursor = db.conn.cursor()
    cursor.execute('SELECT * FROM materials WHERE id = ?', (material_id,))
    material = cursor.fetchone()
    
    if material:
        # زيادة عدد المشاهدات
        cursor.execute('UPDATE materials SET view_count = view_count + 1 WHERE id = ?', (material_id,))
        db.conn.commit()
        
        # عرض تفاصيل المادة
        material_text = f"""
📚 <b>{material['name']}</b>

📝 <b>الوصف:</b>
{material['description']}

📁 <b>التصنيف:</b> {material['category']}
🎓 <b>المستوى:</b> {material['grade_level']}
📖 <b>المادة:</b> {material['subject']}
🌐 <b>اللغة:</b> {material['language']}
📊 <b>عدد التحميلات:</b> {material['download_count']}
⭐ <b>التقييم:</b> {material['rating'] if material['rating'] > 0 else 'لم يتم التقييم بعد'}

📅 <b>تاريخ الإضافة:</b> {material['added_date'][:10]}
        """
        
        keyboard = [
            [
                InlineKeyboardButton("📥 تحميل المادة", callback_data=f"download_{material_id}"),
                InlineKeyboardButton("⭐ تقييم", callback_data=f"rate_{material_id}")
            ],
            [
                InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="materials_page_0")
            ]
        ]
        
        await query.edit_message_text(
            material_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await query.edit_message_text(
            "❌ المادة غير موجودة.",
            reply_markup=UIManager.get_main_menu(query.from_user.id)
        )

async def handle_materials_pagination(query, context, data):
    """معالجة التنقل بين صفحات المواد"""
    page = int(data.replace("materials_page_", ""))
    await show_materials_list(query, context, page)

# ========== إجراءات المستخدم ==========
async def handle_user_actions(query, context, data):
    """معالجة إجراءات المستخدم"""
    action = data.replace("user_", "")
    
    if action == "balance":
        await show_user_balance(query)
    elif action == "referral":
        await show_user_referral(query)
    elif action == "profile":
        await show_user_profile(query)
    elif action == "support":
        await show_support_info(query)

async def show_user_balance(query):
    """عرض رصيد المستخدم"""
    user = db.get_user(query.from_user.id)
    
    if user:
        cursor = db.conn.cursor()
        
        # الحصول على عدد المدعوين
        cursor.execute('SELECT COUNT(*) FROM users WHERE referred_by = ?', (query.from_user.id,))
        referrals = cursor.fetchone()[0]
        
        # الحصول على آخر المعاملات
        cursor.execute('''
            SELECT type, amount, service, created_at 
            FROM transactions 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT 5
        ''', (query.from_user.id,))
        transactions = cursor.fetchall()
        
        balance_text = f"""
💰 <b>حسابك المالي</b>

⚖️ <b>الرصيد الحالي:</b> {UserManager.format_money(user['balance'])}
💸 <b>إجمالي المشتريات:</b> {UserManager.format_money(user['total_spent'])}
🎁 <b>إجمالي الأرباح:</b> {UserManager.format_money(user['total_earned'])}
👥 <b>عدد المدعوين:</b> {referrals}

💳 <b>للتعبئة راسل:</b> {db.get_setting('support_username', '@Allawi04')}
        """
        
        if transactions:
            balance_text += "\n\n📋 <b>آخر المعاملات:</b>\n"
            trans_names = {
                'deposit': 'إيداع 💰',
                'purchase': 'شراء 🛒',
                'bonus': 'هدية 🎁',
                'referral': 'دعوة 👥',
                'welcome': 'ترحيب 🎉'
            }
            
            for trans in transactions:
                trans_type = trans_names.get(trans['type'], trans['type'])
                amount = trans['amount']
                sign = "+" if amount > 0 else ""
                balance_text += f"• {trans_type}: {sign}{UserManager.format_money(amount)}"
                if trans['service']:
                    balance_text += f" ({trans['service']})"
                balance_text += f" - {trans['created_at'][:16]}\n"
        
        await query.edit_message_text(
            balance_text,
            parse_mode=ParseMode.HTML,
            reply_markup=UIManager.get_main_menu(query.from_user.id)
        )

async def show_user_referral(query):
    """عرض معلومات الدعوة"""
    user = db.get_user(query.from_user.id)
    
    if user:
        referral_link = f"https://t.me/FC4Xbot?start=ref_{user['referral_code']}"
        
        cursor = db.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users WHERE referred_by = ?', (query.from_user.id,))
        referral_count = cursor.fetchone()[0]
        
        total_bonus = referral_count * int(db.get_setting('referral_bonus', REFERRAL_BONUS))
        
        referral_text = f"""
👥 <b>نظام الدعوة</b>

🔗 <b>رابط الدعوة الخاص بك:</b>
{referral_link}

📊 <b>إحصائيات دعوتك:</b>
👤 عدد المدعوين: {referral_count}
💰 إجمالي المكافآت: {UserManager.format_money(total_bonus)}
🎁 مكافأة لكل دعوة: {UserManager.format_money(int(db.get_setting('referral_bonus', REFERRAL_BONUS)))}

💡 <b>كيفية الاستفادة:</b>
1. شارك الرابط أعلاه مع أصدقائك
2. عندما يسجل صديقك لأول مرة
3. تحصل أنت وهو على مكافأة!

📢 <b>نص دعوة جاهز:</b>
مرحباً! جرب هذا البوت التعليمي الرائع:
{referral_link}
        """
        
        await query.edit_message_text(
            referral_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=UIManager.get_main_menu(query.from_user.id)
        )

async def show_user_profile(query):
    """عرض الملف الشخصي للمستخدم"""
    user = db.get_user(query.from_user.id)
    
    if user:
        cursor = db.conn.cursor()
        
        # الحصول على الإحصائيات
        cursor.execute('SELECT COUNT(*) FROM transactions WHERE user_id = ?', (query.from_user.id,))
        total_transactions = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM materials WHERE added_by = ?', (query.from_user.id,))
        added_materials = cursor.fetchone()[0]
        
        profile_text = f"""
👤 <b>ملفك الشخصي</b>

🆔 <b>الأيدي:</b> {user['user_id']}
👤 <b>الاسم:</b> {user['first_name']} {user['last_name']}
📧 <b>اليوزر:</b> @{user['username'] if user['username'] else 'غير محدد'}
📅 <b>تاريخ الانضمام:</b> {user['join_date'][:10]}
📈 <b>المستوى:</b> {user['level']}
⭐ <b>النقاط:</b> {user['xp']}
🔥 <b>سلسلة النشاط:</b> {user['daily_streak']} يوم

📊 <b>إحصائيات:</b>
• إجمالي المعاملات: {total_transactions}
• المواد المضافة: {added_materials}
• أيام النشاط: {user['daily_streak']}
        """
        
        keyboard = [
            [
                InlineKeyboardButton("✏️ تعديل الملف", callback_data="edit_profile"),
                InlineKeyboardButton("📊 إحصائيات متقدمة", callback_data="advanced_stats")
            ],
            [
                InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
            ]
        ]
        
        await query.edit_message_text(
            profile_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def show_bot_info(query):
    """عرض معلومات البوت"""
    stats = db.get_statistics()
    
    info_text = f"""
🤖 <b>معلومات بوت 'يلا نتعلم'</b>

🎯 <b>الهدف:</b> مساعدة الطلاب العراقيين في دراستهم
👨‍💻 <b>المطور:</b> {ADMIN_USERNAME}
📱 <b>الإصدار:</b> {BOT_VERSION}
📅 <b>تاريخ الإطلاق:</b> {BOT_RELEASE_DATE}

💰 <b>نظام الدفع:</b> الدينار العراقي
💸 <b>أقل سعر خدمة:</b> {UserManager.format_money(1000)}

📊 <b>إحصائيات البوت:</b>
• إجمالي المستخدمين: {stats['total_users']}
• المستخدمين النشطين اليوم: {stats['new_users_today']}
• إجمالي المواد: {stats['total_materials']}
• إجمالي التحميلات: {stats['total_downloads']}

🛠 <b>الخدمات المتاحة:</b>
1. حساب درجة الإعفاء
2. تلخيص الملازم بالذكاء الاصطناعي
3. سؤال وجواب دراسي
4. مكتبة الملازم والمرشحات

📞 <b>الدعم الفني:</b> {db.get_setting('support_username', '@Allawi04')}
📢 <b>قناتنا:</b> {db.get_setting('channel_url', 'قناة البوت')}
🌐 <b>الموقع:</b> {db.get_setting('website_url', 'غير متوفر')}
        """
    
    await query.edit_message_text(
        info_text,
        parse_mode=ParseMode.HTML,
        reply_markup=UIManager.get_main_menu(query.from_user.id)
    )

async def show_support_info(query):
    """عرض معلومات الدعم"""
    support_text = f"""
📞 <b>الدعم الفني</b>

👨‍💻 <b>المطور والدعم:</b> {db.get_setting('support_username', '@Allawi04')}
💬 <b>مجموعة الدعم:</b> {db.get_setting('group_url', 'غير متوفرة')}
📧 <b>للتواصل:</b> {ADMIN_USERNAME}

🕒 <b>أوقات الدعم:</b>
• الأحد - الخميس: 9:00 ص - 5:00 م
• الجمعة: 9:00 ص - 12:00 م
• السبت: إجازة

📋 <b>خدمات الدعم:</b>
1. المساعدة في استخدام البوت
2. مشاكل في الدفع
3. اقتراحات وتحسينات
4. الإبلاغ عن أخطاء
5. الاستفسارات العامة

⚠️ <b>ملاحظات مهمة:</b>
• الرجاء تقديم تفاصيل المشكلة بوضوح
• أرفق صوراً أو مقاطع إذا لزم الأمر
• استخدم اليوزر @{db.get_setting('support_username', '@Allawi04').replace('@', '')} للتواصل المباشر
        """
    
    keyboard = [
        [
            InlineKeyboardButton("📩 فتح تذكرة دعم", callback_data="open_ticket"),
            InlineKeyboardButton("📋 الشروط والأحكام", callback_data="terms")
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
        ]
    ]
    
    await query.edit_message_text(
        support_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ========== إدارة لوحة التحكم ==========
async def handle_admin_actions(query, context, data):
    """معالجة إجراءات لوحة التحكم"""
    if query.from_user.id != OWNER_ID and not (db.get_user(query.from_user.id) and db.get_user(query.from_user.id).get('is_admin')):
        await query.edit_message_text("⛔ غير مصرح لك!")
        return
    
    action = data.replace("admin_", "")
    
    if action == "panel":
        await show_admin_panel(query)
    elif action == "stats":
        await show_admin_statistics(query)
    elif action == "users":
        await show_admin_users(query)
    elif action == "charge":
        await start_admin_charge(query, context)
    elif action == "ban":
        await start_admin_ban(query, context)
    elif action == "materials":
        await show_admin_materials(query)
    elif action == "prices":
        await show_admin_prices(query)
    elif action == "broadcast":
        await start_admin_broadcast(query, context)
    elif action == "settings":
        await show_admin_settings(query)
    elif action == "backup":
        await show_admin_backup(query)
    elif action == "logs":
        await show_admin_logs(query)

async def show_admin_panel(query):
    """عرض لوحة التحكم"""
    stats = db.get_statistics()
    
    admin_text = f"""
👑 <b>لوحة التحكم الإدارية</b>

📊 <b>الإحصائيات السريعة:</b>
• المستخدمين: {stats['total_users']}
• الرصيد الإجمالي: {UserManager.format_money(stats['total_balance'])}
• المشتريات اليوم: {UserManager.format_money(abs(stats['withdrawals_today']))}
• المواد: {stats['total_materials']}

🛠 <b>أدوات الإدارة:</b>
1. 📊 الإحصائيات - عرض إحصائيات مفصلة
2. 👥 المستخدمين - إدارة حسابات المستخدمين
3. 💰 الشحن - شحن أرصدة المستخدمين
4. 🚫 الحظر - حظر أو فك حظر المستخدمين
5. 📁 المواد - إدارة المواد التعليمية
6. ⚙️ الأسعار - تغيير أسعار الخدمات
7. 📢 الإشعارات - إرسال إشعارات جماعية
8. 🔧 الإعدادات - تعديل إعدادات البوت
9. 💾 النسخ الاحتياطي - إدارة النسخ الاحتياطية
10. 📋 السجلات - عرض سجلات النشاط
        """
    
    await query.edit_message_text(
        admin_text,
        parse_mode=ParseMode.HTML,
        reply_markup=UIManager.get_admin_menu()
    )

async def show_admin_statistics(query):
    """عرض إحصائيات مفصلة"""
    stats = db.get_statistics()
    
    stats_text = f"""
📊 <b>الإحصائيات التفصيلية</b>

👥 <b>المستخدمين:</b>
• الإجمالي: {stats['total_users']}
• الجدد اليوم: {stats['new_users_today']}
• المحظورين: {stats['banned_users']}
• المديرين: {stats['admin_users']}

💰 <b>المالية:</b>
• إجمالي الأرصدة: {UserManager.format_money(stats['total_balance'])}
• إجمالي المشتريات: {UserManager.format_money(stats['total_spent'])}
• إجمالي الأرباح: {UserManager.format_money(stats['total_earned'])}
• الإيداعات اليوم: {UserManager.format_money(stats['deposits_today'])}
• السحوبات اليوم: {UserManager.format_money(abs(stats['withdrawals_today']))}

🛠 <b>الخدمات:</b>
"""
    
    for service_stat in stats['service_stats']:
        service_name = {
            'exemption': 'حساب الإعفاء',
            'summarize': 'تلخيص PDF',
            'qa': 'سؤال وجواب',
            'materials': 'الملازم'
        }.get(service_stat['service'], service_stat['service'])
        
        stats_text += f"• {service_name}: {service_stat['usage_count']} استخدام ({UserManager.format_money(service_stat['total_income'])})\n"
    
    stats_text += f"""
📚 <b>المواد:</b>
• الإجمالي: {stats['total_materials']}
• التحميلات: {stats['total_downloads']}

📈 <b>النشاط:</b>
• المعاملات اليوم: {stats['transactions_today']}
• الأنشطة اليوم: {stats['activities_today']}
        """
    
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]
    
    await query.edit_message_text(
        stats_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ========== الدالة الرئيسية ==========
def main():
    """الدالة الرئيسية لتشغيل البوت"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # معالج المحادثات للخدمات التعليمية
    service_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_exemption_service, pattern="^service_exemption$"),
            CallbackQueryHandler(start_summarize_service, pattern="^service_summarize$"),
            CallbackQueryHandler(start_qa_service, pattern="^service_qa$")
        ],
        states={
            EXEMPTION_COURSE1: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_exemption_course1)
            ],
            EXEMPTION_COURSE2: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_exemption_course2)
            ],
            EXEMPTION_COURSE3: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_exemption_course3)
            ],
            SUMMARIZE_PDF: [
                MessageHandler(filters.Document.PDF, process_pdf_summarize),
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_pdf_summarize)
            ],
            QA_QUESTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_qa_question),
                MessageHandler(filters.PHOTO, process_qa_question),
                MessageHandler(filters.Document.ALL, process_qa_question)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", lambda u, c: ConversationHandler.END),
            CallbackQueryHandler(return_to_main_menu, pattern="^back_to_main$")
        ]
    )
    
    # معالج المحادثات للإدارة
    admin_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_admin_charge, pattern="^admin_charge$"),
            CallbackQueryHandler(start_admin_ban, pattern="^admin_ban$"),
            CallbackQueryHandler(start_admin_broadcast, pattern="^admin_broadcast$")
        ],
        states={
            ADMIN_CHARGE_USER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_charge_user)
            ],
            ADMIN_CHARGE_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_charge_amount)
            ],
            ADMIN_BAN_USER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_ban_user)
            ],
            ADMIN_BAN_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_ban_reason)
            ],
            ADMIN_BAN_DURATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_ban_duration)
            ],
            ADMIN_BROADCAST_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_broadcast_message)
            ],
            ADMIN_BROADCAST_CONFIRM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_broadcast_confirm)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", lambda u, c: ConversationHandler.END),
            CallbackQueryHandler(show_admin_panel, pattern="^admin_panel$")
        ]
    )
    
    # تسجيل Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", start_command))
    application.add_handler(CommandHandler("menu", start_command))
    
    application.add_handler(service_handler)
    application.add_handler(admin_handler)
    
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    
    # إضافة معالج للأخطاء
    application.add_error_handler(error_handler)
    
    # تشغيل البوت
    logger.info("=" * 60)
    logger.info("🤖 بوت 'يلا نتعلم' يعمل الآن...")
    logger.info(f"👑 المالك: {OWNER_ID}")
    logger.info(f"🤖 اليوزر: {BOT_USERNAME}")
    logger.info(f"👨‍💻 الدعم: {ADMIN_USERNAME}")
    logger.info(f"💎 الذكاء الاصطناعي: {'✅ متصل' if ai_manager.model else '❌ غير متصل'}")
    logger.info("=" * 60)
    
    print("\n" + "=" * 60)
    print("🎓 بوت 'يلا نتعلم' الإصدار 2.0")
    print("=" * 60)
    print(f"🤖 اليوزر: {BOT_USERNAME}")
    print(f"👑 المالك: {OWNER_ID}")
    print(f"👨‍💻 المطور: {ADMIN_USERNAME}")
    print(f"💎 الذكاء الاصطناعي: {'✅ متصل' if ai_manager.model else '❌ غير متصل'}")
    print(f"📊 قاعدة البيانات: {db.db_path}")
    print(f"📝 سجلات البوت: bot.log")
    print("=" * 60)
    print("✅ البوت يعمل وجاهز للاستخدام!")
    print("=" * 60 + "\n")
    
    # إنشاء النسخة الاحتياطية الأولى
    if db.get_setting('auto_backup') == '1':
        backup_id = db.create_backup()
        if backup_id:
            logger.info(f"✅ تم إنشاء النسخة الاحتياطية: {backup_id}")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

async def error_handler(update: Update, context: CallbackContext):
    """معالجة الأخطاء"""
    logger.error(f"حدث خطأ: {context.error}", exc_info=context.error)
    
    try:
        if update and update.effective_user:
            await update.message.reply_text(
                "❌ حدث خطأ غير متوقع. الرجاء المحاولة مرة أخرى.\n"
                "إذا تكرر الخطأ، راسل الدعم الفني.",
                reply_markup=UIManager.get_main_menu(update.effective_user.id)
            )
    except:
        pass

# ========== دوال مساعدة للإدارة (مبسطة) ==========
async def start_admin_charge(query, context):
    """بدء عملية شحن رصيد"""
    await query.edit_message_text("💰 أرسل أيدي المستخدم:")
    return ADMIN_CHARGE_USER

async def process_admin_charge_user(update: Update, context: CallbackContext):
    """معالجة أيدي المستخدم للشحن"""
    try:
        user_id = int(update.message.text)
        context.user_data['charge_user_id'] = user_id
        await update.message.reply_text("💵 أرسل المبلغ:")
        return ADMIN_CHARGE_AMOUNT
    except:
        await update.message.reply_text("❌ أيدي غير صالح")
        return ADMIN_CHARGE_USER

async def process_admin_charge_amount(update: Update, context: CallbackContext):
    """معالجة مبلغ الشحن"""
    try:
        amount = int(update.message.text)
        user_id = context.user_data.get('charge_user_id')
        
        if user_id and amount > 0:
            db.update_balance(user_id, amount, 'deposit')
            
            await update.message.reply_text(
                f"✅ تم شحن {UserManager.format_money(amount)} للمستخدم {user_id}",
                reply_markup=UIManager.get_main_menu(update.effective_user.id)
            )
            return ConversationHandler.END
    except:
        pass
    
    await update.message.reply_text("❌ مبلغ غير صالح")
    return ADMIN_CHARGE_AMOUNT

async def start_admin_ban(query, context):
    """بدء عملية حظر"""
    await query.edit_message_text("🚫 أرسل أيدي المستخدم:")
    return ADMIN_BAN_USER

async def process_admin_ban_user(update: Update, context: CallbackContext):
    """معالجة حظر المستخدم"""
    try:
        user_id = int(update.message.text)
        
        cursor = db.conn.cursor()
        cursor.execute('UPDATE users SET is_banned = 1 WHERE user_id = ?', (user_id,))
        db.conn.commit()
        
        await update.message.reply_text(
            f"✅ تم حظر المستخدم {user_id}",
            reply_markup=UIManager.get_main_menu(update.effective_user.id)
        )
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ أيدي غير صالح")
        return ADMIN_BAN_USER

async def start_admin_broadcast(query, context):
    """بدء عملية إرسال إشعار"""
    await query.edit_message_text("📢 أرسل نص الإشعار:")
    return ADMIN_BROADCAST_MESSAGE

async def process_admin_broadcast_message(update: Update, context: CallbackContext):
    """معالجة نص الإشعار"""
    message = update.message.text
    context.user_data['broadcast_message'] = message
    
    await update.message.reply_text(
        f"📢 تأكيد الإرسال:\n\n{message[:200]}...\n\n"
        f"✅ أرسل 'نعم' للتأكيد أو 'لا' للإلغاء"
    )
    return ADMIN_BROADCAST_CONFIRM

async def process_admin_broadcast_confirm(update: Update, context: CallbackContext):
    """تأكيد إرسال الإشعار"""
    if update.message.text.lower() == 'نعم':
        message = context.user_data.get('broadcast_message')
        users = db.get_all_users()
        
        progress = await update.message.reply_text(f"📤 جاري الإرسال لـ {len(users)} مستخدم...")
        
        success = 0
        for user in users:
            try:
                await update._bot.send_message(user['user_id'], message)
                success += 1
                await asyncio.sleep(0.1)
            except:
                pass
        
        await progress.delete()
        await update.message.reply_text(
            f"✅ تم إرسال الإشعار لـ {success} من {len(users)} مستخدم",
            reply_markup=UIManager.get_main_menu(update.effective_user.id)
        )
    else:
        await update.message.reply_text(
            "❌ تم إلغاء الإرسال",
            reply_markup=UIManager.get_main_menu(update.effective_user.id)
        )
    
    return ConversationHandler.END

# دوال إدارية أخرى (مبسطة)
async def show_admin_users(query):
    await query.edit_message_text(
        "👥 <b>إدارة المستخدمين</b>\n\n"
        "استخدم الأوامر التالية:\n"
        "• /ban [user_id] - حظر مستخدم\n"
        "• /unban [user_id] - فك حظر\n"
        "• /users - قائمة المستخدمين\n"
        "• /search [name] - بحث عن مستخدم",
        parse_mode=ParseMode.HTML,
        reply_markup=UIManager.get_admin_menu()
    )

async def show_admin_materials(query):
    await query.edit_message_text(
        "📁 <b>إدارة المواد</b>\n\n"
        "استخدم الأوامر التالية:\n"
        "• /addmaterial - إضافة مادة جديدة\n"
        "• /editmaterial [id] - تعديل مادة\n"
        "• /deletematerial [id] - حذف مادة\n"
        "• /materials - عرض جميع المواد",
        parse_mode=ParseMode.HTML,
        reply_markup=UIManager.get_admin_menu()
    )

async def show_admin_prices(query):
    current_prices = f"""
⚙️ <b>الأسعار الحالية</b>

• حساب الإعفاء: {UserManager.format_money(int(db.get_setting('price_exemption', 1000)))}
• تلخيص PDF: {UserManager.format_money(int(db.get_setting('price_summarize', 1000)))}
• سؤال وجواب: {UserManager.format_money(int(db.get_setting('price_qa', 1000)))}
• المواد: {UserManager.format_money(int(db.get_setting('price_materials', 1000)))}

استخدم الأمر:
/setprice [service] [amount]
مثال: /setprice exemption 1500
    """
    
    await query.edit_message_text(
        current_prices,
        parse_mode=ParseMode.HTML,
        reply_markup=UIManager.get_admin_menu()
    )

async def show_admin_settings(query):
    await query.edit_message_text(
        "🔧 <b>الإعدادات العامة</b>\n\n"
        "استخدم الأوامر التالية:\n"
        "• /maintenance [on/off] - وضع الصيانة\n"
        "• /setchannel [url] - رابط القناة\n"
        "• /setsupport [@username] - يوزر الدعم\n"
        "• /setwelcome [amount] - الهدية الترحيبية\n"
        "• /setreferral [amount] - مكافأة الدعوة",
        parse_mode=ParseMode.HTML,
        reply_markup=UIManager.get_admin_menu()
    )

async def show_admin_backup(query):
    await query.edit_message_text(
        "💾 <b>النسخ الاحتياطي</b>\n\n"
        "استخدم الأوامر التالية:\n"
        "• /backup - إنشاء نسخة احتياطية\n"
        "• /restore [id] - استعادة نسخة\n"
        "• /listbackups - عرض النسخ",
        parse_mode=ParseMode.HTML,
        reply_markup=UIManager.get_admin_menu()
    )

async def show_admin_logs(query):
    await query.edit_message_text(
        "📋 <b>سجلات النشاط</b>\n\n"
        "استخدم الأوامر التالية:\n"
        "• /logs [days] - سجلات الأيام المحددة\n"
        "• /clearlogs - مسح السجلات القديمة\n"
        "• /userlogs [user_id] - سجلات مستخدم",
        parse_mode=ParseMode.HTML,
        reply_markup=UIManager.get_admin_menu()
    )

if __name__ == '__main__':
    # إنشاء المجلدات المطلوبة
    os.makedirs('backups', exist_ok=True)
    os.makedirs('temp', exist_ok=True)
    
    # تشغيل البوت
    main()
