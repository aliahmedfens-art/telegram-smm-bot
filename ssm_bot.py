#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بوت يلا نتعلم - Telegram Bot for Students
مطور بواسطة: Allawi04@
"""

import logging
import sqlite3
import json
import os
import asyncio
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import uuid4
from io import BytesIO

import fitz  # PyMuPDF
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping
from reportlab.lib.utils import ImageReader
import google.generativeai as genai
from PIL import Image
import requests
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, Document, PhotoSize,
    InputFile, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, CallbackContext, ConversationHandler
)
from telegram.constants import ParseMode

# ========== إعدادات البوت ==========
BOT_TOKEN = "8481569753:AAHTdbWwu0BHmoo_iHPsye8RkTptWzfiQWU"
GEMINI_API_KEY = "AIzaSyAqlug21bw_eI60ocUtc1Z76NhEUc-zuzY"
BOT_USERNAME = "@FC4Xbot"
ADMIN_USERNAME = "@Allawi04"

# تسعيرة الخدمات (قابلة للتعديل من لوحة التحكم)
DEFAULT_PRICES = {
    "exemption": 1000,    # حساب درجة الإعفاء
    "summarize": 1000,    # تلخيص PDF
    "qa": 1000,           # سؤال وجواب
    "materials": 1000     # قسم الملازم
}

WELCOME_BONUS = 1000  # الهدية الترحيبية
REFERRAL_BONUS = 500  # مكافأة الدعوة

# حالات المحادثة
(
    WAITING_FOR_COURSE1, 
    WAITING_FOR_COURSE2, 
    WAITING_FOR_COURSE3,
    SUMMARIZE_STATE,
    QA_STATE,
    ADMIN_STATE
) = range(6)

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ========== تهيئة قواعد البيانات ==========
def init_database():
    """تهيئة قاعدة بيانات SQLite"""
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    c = conn.cursor()
    
    # جدول المستخدمين
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        balance INTEGER DEFAULT 0,
        referral_code TEXT UNIQUE,
        referred_by TEXT,
        join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_banned INTEGER DEFAULT 0,
        is_admin INTEGER DEFAULT 0,
        total_spent INTEGER DEFAULT 0
    )''')
    
    # جدول المعاملات
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        type TEXT,  -- 'deposit', 'purchase', 'bonus', 'referral'
        amount INTEGER,
        service TEXT,
        details TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )''')
    
    # جدول إحصائيات الخدمات
    c.execute('''CREATE TABLE IF NOT EXISTS service_stats (
        service TEXT PRIMARY KEY,
        usage_count INTEGER DEFAULT 0,
        total_income INTEGER DEFAULT 0
    )''')
    
    # جدول إعدادات البوت
    c.execute('''CREATE TABLE IF NOT EXISTS bot_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    
    # جدول ملفات الملازم
    c.execute('''CREATE TABLE IF NOT EXISTS materials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        description TEXT,
        file_id TEXT,
        category TEXT,
        added_by INTEGER,
        added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # جدول الأسئلة والأجوبة
    c.execute('''CREATE TABLE IF NOT EXISTS qa_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        question TEXT,
        answer TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # إدخال الإعدادات الافتراضية
    for service, price in DEFAULT_PRICES.items():
        c.execute('''INSERT OR IGNORE INTO bot_settings (key, value) VALUES (?, ?)''',
                 (f'price_{service}', str(price)))
    
    c.execute('''INSERT OR IGNORE INTO bot_settings (key, value) VALUES ('welcome_bonus', ?)''',
             (str(WELCOME_BONUS),))
    c.execute('''INSERT OR IGNORE INTO bot_settings (key, value) VALUES ('referral_bonus', ?)''',
             (str(REFERRAL_BONUS),))
    c.execute('''INSERT OR IGNORE INTO bot_settings (key, value) VALUES ('maintenance_mode', '0')''')
    c.execute('''INSERT OR IGNORE INTO bot_settings (key, value) VALUES ('channel_url', '')''')
    c.execute('''INSERT OR IGNORE INTO bot_settings (key, value) VALUES ('support_username', ?)''',
             (ADMIN_USERNAME,))
    
    conn.commit()
    return conn

# تهيئة قاعدة البيانات
db_conn = init_database()

# ========== دوال مساعدة للقاعدة البيانات ==========
def get_user(user_id: int) -> Optional[Dict]:
    """الحصول على بيانات مستخدم"""
    c = db_conn.cursor()
    c.execute('''SELECT * FROM users WHERE user_id = ?''', (user_id,))
    row = c.fetchone()
    if row:
        columns = [desc[0] for desc in c.description]
        return dict(zip(columns, row))
    return None

def update_balance(user_id: int, amount: int, transaction_type: str, service: str = None):
    """تحديث رصيد المستخدم وتسجيل المعاملة"""
    c = db_conn.cursor()
    
    # تحديث الرصيد
    c.execute('''UPDATE users SET balance = balance + ? WHERE user_id = ?''', 
              (amount, user_id))
    
    # تحديث إجمالي الإنفاق إذا كان شراء
    if transaction_type == 'purchase' and amount < 0:
        c.execute('''UPDATE users SET total_spent = total_spent + ? WHERE user_id = ?''',
                  (abs(amount), user_id))
    
    # تسجيل المعاملة
    details = json.dumps({"service": service} if service else {})
    c.execute('''INSERT INTO transactions (user_id, type, amount, service, details)
                 VALUES (?, ?, ?, ?, ?)''',
              (user_id, transaction_type, amount, service or '', details))
    
    # تحديث إحصائيات الخدمة إذا كانت عملية شراء
    if transaction_type == 'purchase' and service:
        c.execute('''INSERT OR REPLACE INTO service_stats (service, usage_count, total_income)
                     VALUES (?, COALESCE((SELECT usage_count FROM service_stats WHERE service = ?), 0) + 1,
                     COALESCE((SELECT total_income FROM service_stats WHERE service = ?), 0) + ?)''',
                  (service, service, service, abs(amount)))
    
    db_conn.commit()

def get_bot_setting(key: str, default=None):
    """الحصول على إعداد من قاعدة البيانات"""
    c = db_conn.cursor()
    c.execute('''SELECT value FROM bot_settings WHERE key = ?''', (key,))
    result = c.fetchone()
    return result[0] if result else default

def set_bot_setting(key: str, value: str):
    """تحديث إعداد في قاعدة البيانات"""
    c = db_conn.cursor()
    c.execute('''INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)''',
              (key, str(value)))
    db_conn.commit()

def add_material(name: str, description: str, file_id: str, category: str, added_by: int):
    """إضافة مادة تعليمية جديدة"""
    c = db_conn.cursor()
    c.execute('''INSERT INTO materials (name, description, file_id, category, added_by)
                 VALUES (?, ?, ?, ?, ?)''',
              (name, description, file_id, category, added_by))
    db_conn.commit()
    return c.lastrowid

def get_materials(category: str = None):
    """الحصول على المواد التعليمية"""
    c = db_conn.cursor()
    if category:
        c.execute('''SELECT * FROM materials WHERE category = ? ORDER BY added_date DESC''', (category,))
    else:
        c.execute('''SELECT * FROM materials ORDER BY added_date DESC''')
    
    columns = [desc[0] for desc in c.description]
    return [dict(zip(columns, row)) for row in c.fetchall()]

def get_all_users():
    """الحصول على جميع المستخدمين"""
    c = db_conn.cursor()
    c.execute('''SELECT * FROM users ORDER BY join_date DESC''')
    columns = [desc[0] for desc in c.description]
    return [dict(zip(columns, row)) for row in c.fetchall()]

def get_user_stats():
    """الحصول على إحصائيات المستخدمين"""
    c = db_conn.cursor()
    stats = {}
    
    c.execute('''SELECT COUNT(*) FROM users''')
    stats['total_users'] = c.fetchone()[0]
    
    c.execute('''SELECT COUNT(*) FROM users WHERE date(join_date) = date('now')''')
    stats['new_today'] = c.fetchone()[0]
    
    c.execute('''SELECT COUNT(*) FROM users WHERE is_banned = 1''')
    stats['banned_users'] = c.fetchone()[0]
    
    c.execute('''SELECT COUNT(*) FROM users WHERE is_admin = 1''')
    stats['admins'] = c.fetchone()[0]
    
    c.execute('''SELECT SUM(balance) FROM users''')
    stats['total_balance'] = c.fetchone()[0] or 0
    
    c.execute('''SELECT SUM(total_spent) FROM users''')
    stats['total_spent'] = c.fetchone()[0] or 0
    
    return stats

def log_qa(user_id: int, question: str, answer: str):
    """تسجيل الأسئلة والأجوبة"""
    c = db_conn.cursor()
    c.execute('''INSERT INTO qa_logs (user_id, question, answer) VALUES (?, ?, ?)''',
              (user_id, question, answer))
    db_conn.commit()

# ========== إعداد الذكاء الاصطناعي (Gemini) ==========
def init_gemini():
    """تهيئة Gemini AI"""
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel('gemini-pro')

gemini_model = init_gemini()

# ========== إعداد الخطوط العربية لـ PDF ==========
def setup_arabic_fonts():
    """إعداد الخطوط العربية والإنجليزية لإنشاء PDF"""
    try:
        arabic_font_path = "arial.ttf"
        
        if not os.path.exists(arabic_font_path):
            pdfmetrics.registerFont(TTFont('Arabic', 'Helvetica'))
        else:
            pdfmetrics.registerFont(TTFont('Arabic', arabic_font_path))
        
        addMapping('Arabic', 0, 0, 'Arabic')
        pdfmetrics.registerFont(TTFont('English', 'Helvetica'))
        logger.info("تم إعداد الخطوط بنجاح")
    except Exception as e:
        logger.warning(f"تعذر تحميل الخطوط العربية: {e}")

setup_arabic_fonts()

# ========== دوال معالجة PDF والصور ==========
def extract_text_from_pdf(pdf_path: str) -> str:
    """استخراج النص من ملف PDF مع دعم العربية"""
    text = ""
    try:
        doc = fitz.open(pdf_path)
        for page_num, page in enumerate(doc):
            text += f"\n--- الصفحة {page_num + 1} ---\n"
            page_text = page.get_text()
            page_text = re.sub(r'\s+', ' ', page_text)
            text += page_text
        doc.close()
        logger.info(f"تم استخراج نص من PDF: {len(text)} حرف")
    except Exception as e:
        logger.error(f"خطأ في استخراج النص من PDF: {e}")
        text = f"خطأ في قراءة الملف: {str(e)}"
    return text

async def download_file_from_telegram(file_id: str, context: CallbackContext) -> Optional[str]:
    """تحميل ملف من تليجرام"""
    try:
        file = await context.bot.get_file(file_id)
        file_path = f"temp_{file_id}.pdf"
        await file.download_to_drive(file_path)
        return file_path
    except Exception as e:
        logger.error(f"خطأ في تحميل الملف: {e}")
        return None

async def summarize_pdf_with_ai(pdf_text: str) -> str:
    """تلخيص النص باستخدام Gemini AI"""
    try:
        prompt = f"""
        أنت مساعد تعليمي للطلاب العراقيين. قم بتلخيص النص الدراسي التالي وفقاً للمعايير التالية:
        
        1. احذف المعلومات الثانوية وغير المهمة
        2. رتب الأفكار الرئيسية بشكل هرمي
        3. استخدم لغة عربية فصحى واضحة
        4. أضف عناوين فرعية للفقرات المهمة
        5. ضع النقاط الأساسية في نقاط مرقمة
        6. حافظ على المصطلحات العلمية كما هي
        7. اجعل التلخيص مناسباً للمراجعة السريعة قبل الامتحان
        
        النص:
        {pdf_text[:4000]}
        
        قدم التلخيص في تقرير منظم مع مقدمة وعناوين رئيسية وختام.
        """
        
        response = await asyncio.to_thread(gemini_model.generate_content, prompt)
        return response.text if response.text else "لم أتمكن من توليد التلخيص، حاول مرة أخرى."
    except Exception as e:
        logger.error(f"خطأ في التلخيص: {e}")
        return f"حدث خطأ في التلخيص: {str(e)}"

async def answer_question_with_ai(question: str, context: str = "") -> str:
    """الإجابة على الأسئلة باستخدام Gemini AI"""
    try:
        prompt = f"""
        أنت معلم عراقي متخصص في المناهج الدراسية العراقية.
        
        السؤال: {question}
        
        {f"السياق الإضافي: {context}" if context else ""}
        
        قدم إجابة:
        1. علمية دقيقة ومنظمة
        2. مناسبة للمناهج العراقية
        3. بلغة عربية واضحة
        4. مع أمثلة إذا لزم الأمر
        5. مختصرة وشاملة في نفس الوقت
        6. مع ذكر المصادر أو المراجع إذا كانت متوفرة
        
        إذا كان السؤال غير واضح، اطلب توضيحاً.
        """
        
        response = await asyncio.to_thread(gemini_model.generate_content, prompt)
        return response.text if response.text else "لم أتمكن من توليد إجابة، حاول صياغة السؤال بشكل أوضح."
    except Exception as e:
        logger.error(f"خطأ في الإجابة على السؤال: {e}")
        return f"حدث خطأ في معالجة السؤال: {str(e)}"

def create_beautiful_pdf(content: str, title: str = "ملخص دراسي") -> BytesIO:
    """إنشاء PDF جميل مع دعم العربية وإرجاعه كـ BytesIO"""
    buffer = BytesIO()
    
    try:
        c = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        
        # إعدادات الصفحة
        c.setTitle(title)
        c.setAuthor("بوت يلا نتعلم")
        c.setSubject("ملخص دراسي")
        
        # خلفية جميلة
        c.setFillColorRGB(0.95, 0.95, 0.97)
        c.rect(0, 0, width, height, fill=1)
        
        # العنوان الرئيسي
        c.setFillColorRGB(0.2, 0.4, 0.6)
        c.setFont("Arabic", 20)
        c.drawCentredString(width/2, height - 60, "📚 " + title + " 📚")
        
        # معلومات البوت
        c.setFillColorRGB(0.4, 0.4, 0.4)
        c.setFont("Arabic", 10)
        c.drawCentredString(width/2, height - 85, "تم الإنشاء بواسطة بوت 'يلا نتعلم'")
        c.drawCentredString(width/2, height - 100, f"التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
        # خط فاصل زخرفي
        c.setStrokeColorRGB(0.2, 0.4, 0.6)
        c.setLineWidth(2)
        c.line(50, height - 120, width - 50, height - 120)
        
        # المحتوى
        y_position = height - 140
        c.setFillColorRGB(0.1, 0.1, 0.1)
        
        # تقسيم المحتوى إلى فقرات
        paragraphs = content.split('\n')
        
        for para in paragraphs:
            if not para.strip():
                y_position -= 20
                continue
                
            if len(para) > 100:
                words = para.split()
                lines = []
                current_line = []
                
                for word in words:
                    if len(' '.join(current_line + [word])) <= 80:
                        current_line.append(word)
                    else:
                        lines.append(' '.join(current_line))
                        current_line = [word]
                
                if current_line:
                    lines.append(' '.join(current_line))
                
                for line in lines:
                    if y_position < 100:
                        c.showPage()
                        c.setFillColorRGB(0.95, 0.95, 0.97)
                        c.rect(0, 0, width, height, fill=1)
                        c.setFillColorRGB(0.1, 0.1, 0.1)
                        y_position = height - 50
                    
                    if any('\u0600' <= char <= '\u06FF' for char in line):
                        c.setFont("Arabic", 12)
                        c.drawString(width - 550, y_position, line[:90])
                    else:
                        c.setFont("English", 11)
                        c.drawString(50, y_position, line[:90])
                    
                    y_position -= 25
            else:
                if y_position < 100:
                    c.showPage()
                    c.setFillColorRGB(0.95, 0.95, 0.97)
                    c.rect(0, 0, width, height, fill=1)
                    c.setFillColorRGB(0.1, 0.1, 0.1)
                    y_position = height - 50
                
                if any('\u0600' <= char <= '\u06FF' for char in para):
                    c.setFont("Arabic", 12)
                    c.drawString(50, y_position, para[:90])
                else:
                    c.setFont("English", 11)
                    c.drawString(50, y_position, para[:90])
                
                y_position -= 30
        
        # تذييل الصفحة
        c.setFillColorRGB(0.4, 0.4, 0.4)
        c.setFont("Helvetica", 8)
        c.drawCentredString(width/2, 40, "بوت يلا نتعلم - @FC4Xbot")
        c.drawCentredString(width/2, 25, f"للدعم الفني: {get_bot_setting('support_username', ADMIN_USERNAME)}")
        
        c.save()
        buffer.seek(0)
        logger.info(f"تم إنشاء PDF: {title}")
        return buffer
    except Exception as e:
        logger.error(f"خطأ في إنشاء PDF: {e}")
        return None

# ========== دوال مساعدة للبوت ==========
def format_money(amount: int) -> str:
    """تنسيق المبالغ المالية"""
    return f"{amount:,} دينار عراقي"

def is_admin(user_id: int) -> bool:
    """التحقق إذا كان المستخدم مديراً"""
    user = get_user(user_id)
    return user and user.get('is_admin', 0) == 1

async def check_balance_and_access(update: Update, service: str, service_name: str) -> bool:
    """التحقق من الرصيد والصيانة قبل استخدام الخدمة"""
    user_id = update.effective_user.id
    
    if get_bot_setting('maintenance_mode') == '1':
        await update.message.reply_text(
            "⚙️ البوت في وضع الصيانة حالياً. الرجاء المحاولة لاحقاً.",
            parse_mode=ParseMode.HTML
        )
        return False
    
    user = get_user(user_id)
    if user and user.get('is_banned'):
        await update.message.reply_text(
            "🚫 حسابك محظور. الرجاء التواصل مع الدعم.",
            parse_mode=ParseMode.HTML
        )
        return False
    
    price = int(get_bot_setting(f'price_{service}', DEFAULT_PRICES.get(service, 1000)))
    
    if user and user.get('balance', 0) >= price:
        update_balance(user_id, -price, 'purchase', service)
        
        try:
            await update.message.reply_text(
                f"✅ تم خصم {format_money(price)} لخدمة {service_name}\n"
                f"💰 الرصيد المتبقي: {format_money(user['balance'] - price)}",
                parse_mode=ParseMode.HTML
            )
        except:
            pass
        
        return True
    else:
        balance = user.get('balance', 0) if user else 0
        await update.message.reply_text(
            f"⚠️ <b>رصيدك غير كافٍ</b>\n\n"
            f"💰 سعر الخدمة: {format_money(price)}\n"
            f"💵 رصيدك الحالي: {format_money(balance)}\n\n"
            f"للتعبئة راسل الدعم: {get_bot_setting('support_username', ADMIN_USERNAME)}",
            parse_mode=ParseMode.HTML
        )
        return False

async def send_notification(user_id: int, message: str, context: CallbackContext):
    """إرسال إشعار للمستخدم"""
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode=ParseMode.HTML
        )
        return True
    except Exception as e:
        logger.error(f"خطأ في إرسال الإشعار للمستخدم {user_id}: {e}")
        return False

# ========== الأوامر الأساسية ==========
async def start_command(update: Update, context: CallbackContext):
    """أمر /start مع نظام الدعوة والهدايا"""
    user = update.effective_user
    user_id = user.id
    
    c = db_conn.cursor()
    c.execute('''INSERT OR IGNORE INTO users 
                 (user_id, username, first_name, last_name, referral_code) 
                 VALUES (?, ?, ?, ?, ?)''',
              (user_id, user.username, user.first_name, user.last_name, str(uuid4())[:8]))
    
    referral_code = None
    if context.args and len(context.args) > 0:
        ref_arg = context.args[0]
        if ref_arg.startswith('ref_'):
            referral_code = ref_arg[4:]
    
    is_new_user = c.rowcount > 0
    if is_new_user:
        welcome_bonus = int(get_bot_setting('welcome_bonus', WELCOME_BONUS))
        update_balance(user_id, welcome_bonus, 'bonus', 'welcome')
        
        if referral_code:
            c.execute('''SELECT user_id FROM users WHERE referral_code = ?''', (referral_code,))
            referrer = c.fetchone()
            if referrer:
                referral_bonus = int(get_bot_setting('referral_bonus', REFERRAL_BONUS))
                update_balance(referrer[0], referral_bonus, 'referral', 'invite')
                
                c.execute('''UPDATE users SET referred_by = ? WHERE user_id = ?''',
                         (referrer[0], user_id))
                
                try:
                    await context.bot.send_message(
                        chat_id=referrer[0],
                        text=f"🎉 <b>مبروك!</b> لقد قام صديقك بالتسجيل عبر رابط دعوتك!\n"
                             f"💰 تم إضافة {format_money(referral_bonus)} إلى رصيدك.",
                        parse_mode=ParseMode.HTML
                    )
                except:
                    pass
    
    db_conn.commit()
    
    user_data = get_user(user_id)
    
    keyboard = [
        ["📊 حساب درجة الإعفاء", "📝 تلخيص الملازم"],
        ["❓ سؤال وجواب", "📚 ملازمي ومرشحاتي"],
        ["💰 رصيدي", "👥 دعوة أصدقاء", "ℹ️ معلومات"]
    ]
    
    if is_admin(user_id):
        keyboard.append(["👑 لوحة التحكم"])
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    welcome_msg = f"""
    <b>👋 أهلاً وسهلاً {user.first_name}!</b>
    
    🎓 في <b>بوت يلا نتعلم</b> - رفيقك الدراسي الذكي
    
    💰 <b>رصيدك:</b> {format_money(user_data.get('balance', 0))}
    🎁 <b>الهدية الترحيبية:</b> {format_money(int(get_bot_setting('welcome_bonus', WELCOME_BONUS)))}
    
    📌 <b>الخدمات المتاحة:</b>
    1️⃣ حساب درجة الإعفاء - {format_money(int(get_bot_setting('price_exemption', 1000)))}
    2️⃣ تلخيص الملازم - {format_money(int(get_bot_setting('price_summarize', 1000)))}
    3️⃣ سؤال وجواب - {format_money(int(get_bot_setting('price_qa', 1000)))}
    4️⃣ ملازمي ومرشحاتي - {format_money(int(get_bot_setting('price_materials', 1000)))}
    
    🔗 <b>رابط الدعوة:</b>
    https://t.me/{BOT_USERNAME.replace('@', '')}?start=ref_{user_data.get('referral_code', '')}
    
    ⚡ <b>لكل دعوة:</b> {format_money(int(get_bot_setting('referral_bonus', REFERRAL_BONUS)))}
    """
    
    channel_url = get_bot_setting('channel_url', '')
    support_user = get_bot_setting('support_username', ADMIN_USERNAME)
    
    if channel_url:
        welcome_msg += f"\n📢 <b>قناتنا:</b> {channel_url}"
    
    welcome_msg += f"\n👨‍💻 <b>الدعم الفني:</b> {support_user}"
    
    await update.message.reply_text(
        welcome_msg,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

async def balance_command(update: Update, context: CallbackContext):
    """عرض رصيد المستخدم"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if user:
        balance_msg = f"""
        💰 <b>حسابك المالي</b>
        
        ⚖️ <b>الرصيد الحالي:</b> {format_money(user.get('balance', 0))}
        💸 <b>إجمالي المشتريات:</b> {format_money(user.get('total_spent', 0))}
        
        🔗 <b>رابط الدعوة:</b>
        https://t.me/{BOT_USERNAME.replace('@', '')}?start=ref_{user.get('referral_code', '')}
        
        💰 <b>مكافأة كل دعوة:</b> {format_money(int(get_bot_setting('referral_bonus', REFERRAL_BONUS)))}
        
        💳 <b>للتعبئة راسل:</b> {get_bot_setting('support_username', ADMIN_USERNAME)}
        """
        
        c = db_conn.cursor()
        c.execute('''SELECT type, amount, date FROM transactions 
                     WHERE user_id = ? ORDER BY date DESC LIMIT 5''', (user_id,))
        transactions = c.fetchall()
        
        if transactions:
            balance_msg += "\n\n📋 <b>آخر المعاملات:</b>\n"
            trans_names = {
                'deposit': 'إيداع 💰',
                'purchase': 'شراء 🛒', 
                'bonus': 'هدية 🎁',
                'referral': 'دعوة 👥',
                'welcome': 'ترحيب 🎉'
            }
            
            for trans in transactions:
                trans_type = trans_names.get(trans[0], trans[0])
                amount = trans[1]
                sign = "+" if amount > 0 else ""
                balance_msg += f"• {trans_type}: {sign}{format_money(amount)} - {trans[2][:16]}\n"
        
        await update.message.reply_text(balance_msg, parse_mode=ParseMode.HTML)

async def referral_command(update: Update, context: CallbackContext):
    """عرض معلومات الدعوة"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if user:
        referral_link = f"https://t.me/{BOT_USERNAME.replace('@', '')}?start=ref_{user.get('referral_code', '')}"
        
        c = db_conn.cursor()
        c.execute('''SELECT COUNT(*) FROM users WHERE referred_by = ?''', (user_id,))
        referral_count = c.fetchone()[0]
        
        total_bonus = referral_count * int(get_bot_setting('referral_bonus', REFERRAL_BONUS))
        
        msg = f"""
        👥 <b>نظام الدعوة</b>
        
        🔗 <b>رابط الدعوة الخاص بك:</b>
        {referral_link}
        
        📊 <b>إحصائيات دعوتك:</b>
        👤 عدد المدعوين: {referral_count}
        💰 إجمالي المكافآت: {format_money(total_bonus)}
        🎁 مكافأة لكل دعوة: {format_money(int(get_bot_setting('referral_bonus', REFERRAL_BONUS)))}
        
        💡 <b>كيفية الاستفادة:</b>
        1. شارك الرابط أعلاه مع أصدقائك
        2. عندما يسجل صديقك لأول مرة
        3. تحصل أنت وهو على مكافأة!
        
        📢 <b>نص دعوة جاهز:</b>
        مرحباً! جرب هذا البوت التعليمي الرائع:
        {referral_link}
        """
        
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def info_command(update: Update, context: CallbackContext):
    """عرض معلومات البوت"""
    info_msg = f"""
    <b>🤖 معلومات بوت 'يلا نتعلم'</b>
    
    <b>🎯 الهدف:</b> مساعدة الطلاب العراقيين في دراستهم
    <b>👨‍💻 المطور:</b> {ADMIN_USERNAME}
    
    <b>💰 نظام الدفع:</b> الدينار العراقي
    <b>💸 أقل سعر خدمة:</b> {format_money(1000)}
    
    <b>📊 عدد المستخدمين:</b> {get_user_stats()['total_users']}
    
    <b>🛠 الخدمات المتاحة:</b>
    1. حساب درجة الإعفاء
    2. تلخيص الملازم بالذكاء الاصطناعي
    3. سؤال وجواب دراسي
    4. مكتبة الملازم والمرشحات
    
    <b>📞 الدعم الفني:</b> {get_bot_setting('support_username', ADMIN_USERNAME)}
    
    <b>📢 قناتنا:</b> {get_bot_setting('channel_url', 'قناة البوت')}
    
    <b>⚙️ الإصدار:</b> 1.0
    <b>📅 تاريخ التأسيس:</b> {datetime.now().strftime('%Y-%m-%d')}
    """
    
    await update.message.reply_text(info_msg, parse_mode=ParseMode.HTML)

# ========== الخدمة 1: حساب درجة الإعفاء ==========
async def exemption_start(update: Update, context: CallbackContext) -> int:
    """بدء خدمة حساب درجة الإعفاء"""
    if not await check_balance_and_access(update, 'exemption', 'حساب درجة الإعفاء'):
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📊 <b>حساب درجة الإعفاء</b>\n\n"
        "أدخل <b>درجة الكورس الأول</b> (0-100):\n"
        "<i>يجب أن تكون بين 0 و 100</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )
    
    return WAITING_FOR_COURSE1

async def get_course1(update: Update, context: CallbackContext) -> int:
    """الحصول على درجة الكورس الأول"""
    try:
        score = float(update.message.text)
        if 0 <= score <= 100:
            context.user_data['course1'] = score
            await update.message.reply_text(
                f"✅ تم حفظ درجة الكورس الأول: {score}\n\n"
                "أدخل <b>درجة الكورس الثاني</b> (0-100):",
                parse_mode=ParseMode.HTML
            )
            return WAITING_FOR_COURSE2
        else:
            await update.message.reply_text(
                "❌ الرجاء إدخال درجة بين 0 و 100:",
                parse_mode=ParseMode.HTML
            )
            return WAITING_FOR_COURSE1
    except ValueError:
        await update.message.reply_text(
            "❌ الرجاء إدخال رقم صحيح:",
            parse_mode=ParseMode.HTML
        )
        return WAITING_FOR_COURSE1

async def get_course2(update: Update, context: CallbackContext) -> int:
    """الحصول على درجة الكورس الثاني"""
    try:
        score = float(update.message.text)
        if 0 <= score <= 100:
            context.user_data['course2'] = score
            await update.message.reply_text(
                f"✅ تم حفظ درجة الكورس الثاني: {score}\n\n"
                "أدخل <b>درجة الكورس الثالث</b> (0-100):",
                parse_mode=ParseMode.HTML
            )
            return WAITING_FOR_COURSE3
        else:
            await update.message.reply_text(
                "❌ الرجاء إدخال درجة بين 0 و 100:",
                parse_mode=ParseMode.HTML
            )
            return WAITING_FOR_COURSE2
    except ValueError:
        await update.message.reply_text(
            "❌ الرجاء إدخال رقم صحيح:",
            parse_mode=ParseMode.HTML
        )
        return WAITING_FOR_COURSE2

async def get_course3(update: Update, context: CallbackContext) -> int:
    """الحصول على درجة الكورس الثالث وحساب النتيجة"""
    try:
        score = float(update.message.text)
        if 0 <= score <= 100:
            course1 = context.user_data.get('course1', 0)
            course2 = context.user_data.get('course2', 0)
            course3 = score
            
            average = (course1 + course2 + course3) / 3
            
            if average >= 90:
                result = "🎉 <b>مبروك! أنت معفي من المادة</b> 🎉"
                emoji = "✅"
            else:
                result = "📝 <b>أنت غير معفي من المادة</b>"
                emoji = "❌"
            
            result_msg = f"""
            {emoji} <b>نتيجة حساب الإعفاء</b> {emoji}
            
            📊 <b>الدرجات المدخلة:</b>
            • الكورس الأول: {course1}
            • الكورس الثاني: {course2}
            • الكورس الثالث: {course3}
            
            ⚖️ <b>المعدل العام:</b> {average:.2f}
            
            {result}
            
            {"🎯 تحتاج إلى " + str(90 - average) + " درجة إضافية للإعفاء" if average < 90 else "🎊 تهانينا على هذا الإنجاز!"}
            
            📌 <b>ملاحظة:</b> هذا الحساب لأغراض تقريبية، الرجاء التأكد من لوائح جامعتك.
            """
            
            await update.message.reply_text(
                result_msg,
                parse_mode=ParseMode.HTML,
                reply_markup=ReplyKeyboardMarkup([["🏠 الرئيسية"]], resize_keyboard=True)
            )
            
            context.user_data.clear()
            return ConversationHandler.END
            
        else:
            await update.message.reply_text(
                "❌ الرجاء إدخال درجة بين 0 و 100:",
                parse_mode=ParseMode.HTML
            )
            return WAITING_FOR_COURSE3
    except ValueError:
        await update.message.reply_text(
            "❌ الرجاء إدخال رقم صحيح:",
            parse_mode=ParseMode.HTML
        )
        return WAITING_FOR_COURSE3

async def cancel_exemption(update: Update, context: CallbackContext) -> int:
    """إلغاء عملية حساب الإعفاء"""
    await update.message.reply_text(
        "تم إلغاء عملية حساب الإعفاء.",
        reply_markup=ReplyKeyboardMarkup([["🏠 الرئيسية"]], resize_keyboard=True)
    )
    context.user_data.clear()
    return ConversationHandler.END

# ========== الخدمة 2: تلخيص الملازم ==========
async def summarize_start(update: Update, context: CallbackContext) -> int:
    """بدء خدمة تلخيص الملازم"""
    if not await check_balance_and_access(update, 'summarize', 'تلخيص الملازم'):
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📝 <b>خدمة تلخيص الملازم</b>\n\n"
        "⏳ الرجاء إرسال ملف PDF المراد تلخيصه:\n"
        "<i>يمكن أن يستغرق التلخيص بضع دقائق</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup([["❌ إلغاء"]], resize_keyboard=True)
    )
    
    return SUMMARIZE_STATE

async def handle_pdf(update: Update, context: CallbackContext) -> int:
    """معالجة ملف PDF المرسل"""
    if update.message.document and update.message.document.mime_type == 'application/pdf':
        processing_msg = await update.message.reply_text(
            "⏳ <b>جاري معالجة الملف وتلخيصه...</b>\n"
            "قد يستغرق ذلك من 30 ثانية إلى دقيقة.",
            parse_mode=ParseMode.HTML
        )
        
        try:
            file_id = update.message.document.file_id
            file_path = await download_file_from_telegram(file_id, context)
            
            if not file_path:
                await processing_msg.delete()
                await update.message.reply_text(
                    "❌ حدث خطأ في تحميل الملف. الرجاء المحاولة مرة أخرى.",
                    reply_markup=ReplyKeyboardMarkup([["🏠 الرئيسية"]], resize_keyboard=True)
                )
                return ConversationHandler.END
            
            pdf_text = extract_text_from_pdf(file_path)
            
            if len(pdf_text) < 50:
                await processing_msg.delete()
                await update.message.reply_text(
                    "❌ الملف فارغ أو لا يمكن قراءته. الرجاء التأكد من محتوى PDF.",
                    reply_markup=ReplyKeyboardMarkup([["🏠 الرئيسية"]], resize_keyboard=True)
                )
                os.remove(file_path)
                return ConversationHandler.END
            
            await processing_msg.edit_text("🤖 <b>جاري تلخيص المحتوى باستخدام الذكاء الاصطناعي...</b>", 
                                         parse_mode=ParseMode.HTML)
            
            summary = await summarize_pdf_with_ai(pdf_text)
            
            await processing_msg.edit_text("📄 <b>جاري إنشاء ملف PDF ملخص...</b>", 
                                         parse_mode=ParseMode.HTML)
            
            pdf_buffer = create_beautiful_pdf(summary, "ملخص دراسي")
            
            if pdf_buffer:
                await update.message.reply_document(
                    document=InputFile(pdf_buffer, filename="ملخص_دراسي.pdf"),
                    caption="📚 <b>ملخص دراسي جاهز</b>\n\n"
                           "✅ تم تلخيص الملف بنجاح\n"
                           "📊 حجم النص الأصلي: " + str(len(pdf_text)) + " حرف\n"
                           "🎯 تم التركيز على النقاط الرئيسية\n\n"
                           "شكراً لاستخدامك بوت 'يلا نتعلم'! 🎓",
                    parse_mode=ParseMode.HTML
                )
                
                pdf_buffer.close()
            else:
                await update.message.reply_text(
                    f"📝 <b>ملخص المحتوى:</b>\n\n{summary[:3000]}...\n\n"
                    "📌 <i>تم قص النص بسبب طوله، للحصول على النسخة الكاملة راجع الملف الأصلي.</i>",
                    parse_mode=ParseMode.HTML
                )
            
            os.remove(file_path)
            await processing_msg.delete()
            
        except Exception as e:
            logger.error(f"خطأ في معالجة PDF: {e}")
            await processing_msg.delete()
            await update.message.reply_text(
                f"❌ حدث خطأ في المعالجة: {str(e)}\nالرجاء المحاولة مرة أخرى.",
                reply_markup=ReplyKeyboardMarkup([["🏠 الرئيسية"]], resize_keyboard=True)
            )
        
        await update.message.reply_text(
            "✅ تم الانتهاء من التلخيص.",
            reply_markup=ReplyKeyboardMarkup([["🏠 الرئيسية"]], resize_keyboard=True)
        )
        return ConversationHandler.END
    
    else:
        await update.message.reply_text(
            "❌ الرجاء إرسال ملف PDF فقط.",
            parse_mode=ParseMode.HTML
        )
        return SUMMARIZE_STATE

async def cancel_summarize(update: Update, context: CallbackContext) -> int:
    """إلغاء عملية التلخيص"""
    await update.message.reply_text(
        "تم إلغاء عملية التلخيص.",
        reply_markup=ReplyKeyboardMarkup([["🏠 الرئيسية"]], resize_keyboard=True)
    )
    return ConversationHandler.END

# ========== الخدمة 3: سؤال وجواب ==========
async def qa_start(update: Update, context: CallbackContext) -> int:
    """بدء خدمة سؤال وجواب"""
    if not await check_balance_and_access(update, 'qa', 'سؤال وجواب'):
        return ConversationHandler.END
    
    await update.message.reply_text(
        "❓ <b>خدمة سؤال وجواب</b>\n\n"
        "🧠 يمكنني الإجابة على أسئلتك الدراسية باستخدام الذكاء الاصطناعي\n\n"
        "📝 <b>أرسل سؤالك الآن:</b>\n"
        "<i>يمكن أن يكون نصاً أو صورة تحتوي على سؤال</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup([["❌ إلغاء"]], resize_keyboard=True)
    )
    
    return QA_STATE

async def handle_question(update: Update, context: CallbackContext) -> int:
    """معالجة السؤال المقدم"""
    question_text = ""
    
    if update.message.text:
        question_text = update.message.text
    elif update.message.photo:
        await update.message.reply_text(
            "📷 <b>لقد أرسلت صورة</b>\n\n"
            "الرجاء كتابة السؤال الموجود في الصورة نصياً:",
            parse_mode=ParseMode.HTML
        )
        return QA_STATE
    elif update.message.document:
        await update.message.reply_text(
            "❌ <b>الخدمة لا تدعم الملفات حالياً</b>\n\n"
            "الرجاء إرسال السؤال كنص أو كتابة نص السؤال الموجود في الصورة:",
            parse_mode=ParseMode.HTML
        )
        return QA_STATE
    
    if question_text.lower() in ['إلغاء', '❌ إلغاء']:
        await update.message.reply_text(
            "تم إلغاء خدمة سؤال وجواب.",
            reply_markup=ReplyKeyboardMarkup([["🏠 الرئيسية"]], resize_keyboard=True)
        )
        return ConversationHandler.END
    
    if len(question_text) < 5:
        await update.message.reply_text(
            "❌ <b>السؤال قصير جداً</b>\n\n"
            "الرجاء كتابة سؤال واضح ومفصل:",
            parse_mode=ParseMode.HTML
        )
        return QA_STATE
    
    processing_msg = await update.message.reply_text(
        "🤖 <b>جاري تحليل السؤال وإعداد الإجابة...</b>\n"
        "قد يستغرق ذلك بضع ثوانٍ.",
        parse_mode=ParseMode.HTML
    )
    
    try:
        answer = await answer_question_with_ai(question_text)
        
        log_qa(update.effective_user.id, question_text[:500], answer[:500])
        
        await processing_msg.delete()
        await update.message.reply_text(
            f"💡 <b>إجابة على سؤالك:</b>\n\n{answer}\n\n"
            f"📌 <i>تمت الإجابة باستخدام الذكاء الاصطناعي المتخصص في المناهج العراقية</i>",
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        logger.error(f"خطأ في الإجابة على السؤال: {e}")
        await processing_msg.delete()
        await update.message.reply_text(
            f"❌ <b>حدث خطأ في معالجة السؤال:</b>\n{str(e)}\n\n"
            f"الرجاء المحاولة مرة أخرى أو إعادة صياغة السؤال.",
            parse_mode=ParseMode.HTML
        )
    
    await update.message.reply_text(
        "✅ تم الانتهاء من الإجابة على السؤال.\n"
        "يمكنك إرسال سؤال جديد أو العودة للرئيسية.",
        reply_markup=ReplyKeyboardMarkup([["🏠 الرئيسية"]], resize_keyboard=True)
    )
    return ConversationHandler.END

# ========== الخدمة 4: ملازمي ومرشحاتي ==========
async def materials_command(update: Update, context: CallbackContext):
    """عرض المواد التعليمية"""
    if not await check_balance_and_access(update, 'materials', 'ملازمي ومرشحاتي'):
        return
    
    materials_list = get_materials()
    
    if not materials_list:
        await update.message.reply_text(
            "📚 <b>ملازمي ومرشحاتي</b>\n\n"
            "⚠️ لا توجد مواد متاحة حالياً.\n"
            "سيتم إضافة المواد قريباً من قبل الإدارة.",
            parse_mode=ParseMode.HTML,
            reply_markup=ReplyKeyboardMarkup([["🏠 الرئيسية"]], resize_keyboard=True)
        )
        return
    
    keyboard = []
    for material in materials_list[:10]:
        btn_text = f"📄 {material['name'][:20]}"
        keyboard.append([btn_text])
    
    keyboard.append(["🏠 الرئيسية"])
    
    await update.message.reply_text(
        "📚 <b>ملازمي ومرشحاتي</b>\n\n"
        "اختر المادة التي تريد تحميلها:",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    
    context.user_data['materials'] = materials_list

async def handle_material_selection(update: Update, context: CallbackContext):
    """معالجة اختيار مادة"""
    selected_text = update.message.text[2:].strip()
    materials = context.user_data.get('materials', [])
    
    for material in materials:
        if material['name'].startswith(selected_text):
            try:
                await update.message.reply_document(
                    document=material['file_id'],
                    caption=f"📚 <b>{material['name']}</b>\n\n"
                           f"📝 {material['description']}\n"
                           f"📁 التصنيف: {material['category']}\n"
                           f"📅 تاريخ الإضافة: {material['added_date'][:10]}\n\n"
                           f"شكراً لاستخدامك بوت 'يلا نتعلم'! 🎓",
                    parse_mode=ParseMode.HTML
                )
                return
            except Exception as e:
                logger.error(f"خطأ في إرسال الملف: {e}")
    
    await update.message.reply_text(
        "❌ لم يتم العثور على المادة المحددة.",
        reply_markup=ReplyKeyboardMarkup([["🏠 الرئيسية"]], resize_keyboard=True)
    )

# ========== لوحة التحكم الإدارية ==========
async def admin_panel(update: Update, context: CallbackContext):
    """لوحة التحكم الإدارية"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text(
            "⛔ <b>غير مصرح لك بالوصول إلى لوحة التحكم</b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    keyboard = [
        ["📊 الإحصائيات", "👥 إدارة المستخدمين"],
        ["💰 الشحن والرصيد", "⚙️ إعدادات البوت"],
        ["📁 إدارة المواد", "🔧 إعدادات الخدمات"],
        ["📢 إرسال إشعار", "🏠 الرئيسية"]
    ]
    
    await update.message.reply_text(
        "👑 <b>لوحة التحكم الإدارية</b>\n\n"
        "اختر القسم الذي تريد إدارته:",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def admin_stats(update: Update, context: CallbackContext):
    """عرض إحصائيات البوت"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    stats = get_user_stats()
    
    c = db_conn.cursor()
    c.execute('''SELECT service, usage_count, total_income FROM service_stats''')
    service_stats = c.fetchall()
    
    c.execute('''SELECT COUNT(*), SUM(amount) FROM transactions 
                 WHERE date(date) = date('now') AND type = 'purchase' ''')
    today_stats = c.fetchone()
    
    stats_msg = f"""
    📊 <b>إحصائيات البوت الشاملة</b>
    
    👤 <b>المستخدمين:</b>
    • إجمالي المستخدمين: {stats['total_users']}
    • مسجلين اليوم: {stats['new_today']}
    • المحظورين: {stats['banned_users']}
    • المشرفين: {stats['admins']}
    
    💰 <b>المالية:</b>
    • إجمالي الأرصدة: {format_money(stats['total_balance'])}
    • إجمالي المشتريات: {format_money(stats['total_spent'])}
    • المشتريات اليوم: {today_stats[0] or 0} عملية ({format_money(today_stats[1] or 0)})
    
    🛠 <b>إحصائيات الخدمات:</b>
    """
    
    for service_stat in service_stats:
        service_name = {
            'exemption': 'حساب الإعفاء',
            'summarize': 'تلخيص PDF',
            'qa': 'سؤال وجواب',
            'materials': 'الملازم'
        }.get(service_stat[0], service_stat[0])
        
        stats_msg += f"• {service_name}: {service_stat[1]} استخدام ({format_money(service_stat[2])})\n"
    
    c.execute('''SELECT COUNT(*) FROM materials''')
    materials_count = c.fetchone()[0]
    
    stats_msg += f"\n📚 <b>المواد التعليمية:</b> {materials_count} مادة"
    
    await update.message.reply_text(stats_msg, parse_mode=ParseMode.HTML)

async def admin_charge(update: Update, context: CallbackContext):
    """شحن رصيد المستخدم"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    await update.message.reply_text(
        "💰 <b>شحن رصيد المستخدم</b>\n\n"
        "أرسل <b>آيدي المستخدم</b> الذي تريد شحن رصيده:",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup([["🔙 رجوع للوحة التحكم"]], resize_keyboard=True)
    )
    
    context.user_data['admin_action'] = 'charge_user'
    return ADMIN_STATE

async def handle_admin_action(update: Update, context: CallbackContext):
    """معالجة الإجراءات الإدارية"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return ConversationHandler.END
    
    action = context.user_data.get('admin_action')
    text = update.message.text
    
    if action == 'charge_user':
        if text.isdigit():
            target_user_id = int(text)
            context.user_data['charge_user_id'] = target_user_id
            
            await update.message.reply_text(
                f"✅ تم تحديد المستخدم: {target_user_id}\n\n"
                f"أرسل <b>المبلغ</b> الذي تريد شحنه (بالدينار العراقي):",
                parse_mode=ParseMode.HTML
            )
            
            context.user_data['admin_action'] = 'charge_amount'
            return ADMIN_STATE
        else:
            await update.message.reply_text(
                "❌ آيدي المستخدم يجب أن يكون رقماً. أرسل الآيدي الصحيح:",
                parse_mode=ParseMode.HTML
            )
            return ADMIN_STATE
    
    elif action == 'charge_amount':
        if text.isdigit():
            amount = int(text)
            target_user_id = context.user_data.get('charge_user_id')
            
            if target_user_id:
                update_balance(target_user_id, amount, 'deposit')
                
                try:
                    await send_notification(
                        target_user_id,
                        f"🎉 <b>تم شحن رصيدك!</b>\n\n"
                        f"💰 المبلغ: {format_money(amount)}\n"
                        f"⚖️ تمت العملية من قبل الإدارة\n"
                        f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                        context
                    )
                except:
                    pass
                
                await update.message.reply_text(
                    f"✅ <b>تم شحن الرصيد بنجاح</b>\n\n"
                    f"👤 آيدي المستخدم: {target_user_id}\n"
                    f"💰 المبلغ: {format_money(amount)}\n"
                    f"📅 الوقت: {datetime.now().strftime('%H:%M:%S')}",
                    parse_mode=ParseMode.HTML,
                    reply_markup=ReplyKeyboardMarkup([["🔙 رجوع للوحة التحكم"]], resize_keyboard=True)
                )
                
                context.user_data.pop('admin_action', None)
                context.user_data.pop('charge_user_id', None)
                
                return ConversationHandler.END
        else:
            await update.message.reply_text(
                "❌ المبلغ يجب أن يكون رقماً. أرسل المبلغ الصحيح:",
                parse_mode=ParseMode.HTML
            )
            return ADMIN_STATE
    
    return ConversationHandler.END

async def admin_settings(update: Update, context: CallbackContext):
    """إعدادات البوت"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    maintenance = "✅ مفعل" if get_bot_setting('maintenance_mode') == '1' else "❌ معطل"
    
    keyboard = [
        ["🔄 تبديل وضع الصيانة", "📢 تغيير رابط القناة"],
        ["👤 تغيير يوزر الدعم", "💰 تغيير مكافأة الدعوة"],
        ["🎁 تغيير الهدية الترحيبية", "🔙 رجوع للوحة التحكم"]
    ]
    
    settings_msg = f"""
    ⚙️ <b>إعدادات البوت</b>
    
    🔧 <b>الإعدادات الحالية:</b>
    • وضع الصيانة: {maintenance}
    • رابط القناة: {get_bot_setting('channel_url', 'غير محدد')}
    • يوزر الدعم: {get_bot_setting('support_username', ADMIN_USERNAME)}
    • مكافأة الدعوة: {format_money(int(get_bot_setting('referral_bonus', REFERRAL_BONUS)))}
    • الهدية الترحيبية: {format_money(int(get_bot_setting('welcome_bonus', WELCOME_BONUS)))}
    
    ⚡ <b>أسعار الخدمات:</b>
    • حساب الإعفاء: {format_money(int(get_bot_setting('price_exemption', 1000)))}
    • تلخيص PDF: {format_money(int(get_bot_setting('price_summarize', 1000)))}
    • سؤال وجواب: {format_money(int(get_bot_setting('price_qa', 1000)))}
    • الملازم: {format_money(int(get_bot_setting('price_materials', 1000)))}
    """
    
    await update.message.reply_text(
        settings_msg,
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def handle_settings_action(update: Update, context: CallbackContext):
    """معالجة إجراءات الإعدادات"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    text = update.message.text
    
    if text == "🔄 تبديل وضع الصيانة":
        current = get_bot_setting('maintenance_mode', '0')
        new_value = '0' if current == '1' else '1'
        set_bot_setting('maintenance_mode', new_value)
        
        status = "✅ مفعل" if new_value == '1' else "❌ معطل"
        await update.message.reply_text(
            f"✅ <b>تم تبديل وضع الصيانة</b>\n\n"
            f"الحالة الجديدة: {status}",
            parse_mode=ParseMode.HTML
        )
    
    elif text == "📢 تغيير رابط القناة":
        await update.message.reply_text(
            "أرسل <b>رابط القناة</b> الجديد:",
            parse_mode=ParseMode.HTML
        )
        context.user_data['admin_action'] = 'change_channel'
        return ADMIN_STATE
    
    elif text == "👤 تغيير يوزر الدعم":
        await update.message.reply_text(
            "أرسل <b>يوزر الدعم</b> الجديد (مع @):",
            parse_mode=ParseMode.HTML
        )
        context.user_data['admin_action'] = 'change_support'
        return ADMIN_STATE
    
    elif text == "💰 تغيير مكافأة الدعوة":
        await update.message.reply_text(
            "أرسل <b>مكافأة الدعوة</b> الجديدة (بالدينار العراقي):",
            parse_mode=ParseMode.HTML
        )
        context.user_data['admin_action'] = 'change_referral_bonus'
        return ADMIN_STATE
    
    elif text == "🎁 تغيير الهدية الترحيبية":
        await update.message.reply_text(
            "أرسل <b>الهدية الترحيبية</b> الجديدة (بالدينار العراقي):",
            parse_mode=ParseMode.HTML
        )
        context.user_data['admin_action'] = 'change_welcome_bonus'
        return ADMIN_STATE
    
    elif text.startswith("تغيير سعر "):
        service_name = text[10:]
        service_key = ''
        
        if "إعفاء" in service_name:
            service_key = 'price_exemption'
        elif "تلخيص" in service_name:
            service_key = 'price_summarize'
        elif "سؤال" in service_name:
            service_key = 'price_qa'
        elif "ملازم" in service_name:
            service_key = 'price_materials'
        
        if service_key:
            await update.message.reply_text(
                f"أرسل <b>السعر الجديد</b> لخدمة {service_name} (بالدينار العراقي):",
                parse_mode=ParseMode.HTML
            )
            context.user_data['admin_action'] = f'change_price_{service_key}'
            return ADMIN_STATE
    
    return ConversationHandler.END

async def handle_settings_input(update: Update, context: CallbackContext):
    """معالجة مدخلات الإعدادات"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return ConversationHandler.END
    
    action = context.user_data.get('admin_action')
    text = update.message.text
    
    if action == 'change_channel':
        set_bot_setting('channel_url', text)
        await update.message.reply_text(
            f"✅ <b>تم تغيير رابط القناة</b>\n\n"
            f"الرابط الجديد: {text}",
            parse_mode=ParseMode.HTML,
            reply_markup=ReplyKeyboardMarkup([["🔙 رجوع للوحة التحكم"]], resize_keyboard=True)
        )
    
    elif action == 'change_support':
        if text.startswith('@'):
            set_bot_setting('support_username', text)
            await update.message.reply_text(
                f"✅ <b>تم تغيير يوزر الدعم</b>\n\n"
                f"اليوزر الجديد: {text}",
                parse_mode=ParseMode.HTML,
                reply_markup=ReplyKeyboardMarkup([["🔙 رجوع للوحة التحكم"]], resize_keyboard=True)
            )
        else:
            await update.message.reply_text(
                "❌ اليوزر يجب أن يبدأ ب @",
                parse_mode=ParseMode.HTML
            )
            return ADMIN_STATE
    
    elif action == 'change_referral_bonus':
        if text.isdigit():
            set_bot_setting('referral_bonus', text)
            await update.message.reply_text(
                f"✅ <b>تم تغيير مكافأة الدعوة</b>\n\n"
                f"المبلغ الجديد: {format_money(int(text))}",
                parse_mode=ParseMode.HTML,
                reply_markup=ReplyKeyboardMarkup([["🔙 رجوع للوحة التحكم"]], resize_keyboard=True)
            )
        else:
            await update.message.reply_text(
                "❌ المبلغ يجب أن يكون رقماً.",
                parse_mode=ParseMode.HTML
            )
            return ADMIN_STATE
    
    elif action == 'change_welcome_bonus':
        if text.isdigit():
            set_bot_setting('welcome_bonus', text)
            await update.message.reply_text(
                f"✅ <b>تم تغيير الهدية الترحيبية</b>\n\n"
                f"المبلغ الجديد: {format_money(int(text))}",
                parse_mode=ParseMode.HTML,
                reply_markup=ReplyKeyboardMarkup([["🔙 رجوع للوحة التحكم"]], resize_keyboard=True)
            )
        else:
            await update.message.reply_text(
                "❌ المبلغ يجب أن يكون رقماً.",
                parse_mode=ParseMode.HTML
            )
            return ADMIN_STATE
    
    elif action and action.startswith('change_price_'):
        if text.isdigit():
            service_key = action[13:]
            set_bot_setting(service_key, text)
            
            service_name = {
                'price_exemption': 'حساب الإعفاء',
                'price_summarize': 'تلخيص PDF',
                'price_qa': 'سؤال وجواب',
                'price_materials': 'الملازم'
            }.get(service_key, service_key)
            
            await update.message.reply_text(
                f"✅ <b>تم تغيير سعر الخدمة</b>\n\n"
                f"الخدمة: {service_name}\n"
                f"السعر الجديد: {format_money(int(text))}",
                parse_mode=ParseMode.HTML,
                reply_markup=ReplyKeyboardMarkup([["🔙 رجوع للوحة التحكم"]], resize_keyboard=True)
            )
        else:
            await update.message.reply_text(
                "❌ السعر يجب أن يكون رقماً.",
                parse_mode=ParseMode.HTML
            )
            return ADMIN_STATE
    
    context.user_data.pop('admin_action', None)
    return ConversationHandler.END

async def admin_materials(update: Update, context: CallbackContext):
    """إدارة المواد التعليمية"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    keyboard = [
        ["📤 إضافة مادة جديدة", "🗑️ حذف مادة"],
        ["📋 عرض جميع المواد", "🔙 رجوع للوحة التحكم"]
    ]
    
    await update.message.reply_text(
        "📁 <b>إدارة المواد التعليمية</b>\n\n"
        "اختر العملية المطلوبة:",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def admin_services(update: Update, context: CallbackContext):
    """إعدادات الخدمات والأسعار"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    keyboard = [
        ["تغيير سعر حساب الإعفاء", "تغيير سعر تلخيص PDF"],
        ["تغيير سعر سؤال وجواب", "تغيير سعر الملازم"],
        ["🔙 رجوع للوحة التحكم"]
    ]
    
    await update.message.reply_text(
        "🔧 <b>إعدادات الخدمات والأسعار</b>\n\n"
        "اختر الخدمة التي تريد تغيير سعرها:",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def admin_broadcast(update: Update, context: CallbackContext):
    """إرسال إشعار جماعي"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    await update.message.reply_text(
        "📢 <b>إرسال إشعار جماعي</b>\n\n"
        "أرسل <b>النص</b> الذي تريد إرساله لجميع المستخدمين:\n"
        "<i>يمكنك استخدام HTML للتنسيق</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup([["❌ إلغاء"]], resize_keyboard=True)
    )
    
    context.user_data['admin_action'] = 'broadcast'
    return ADMIN_STATE

async def handle_broadcast(update: Update, context: CallbackContext):
    """معالجة الإشعار الجماعي"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return ConversationHandler.END
    
    broadcast_text = update.message.text
    
    if broadcast_text == "❌ إلغاء":
        await update.message.reply_text(
            "تم إلغاء الإشعار الجماعي.",
            reply_markup=ReplyKeyboardMarkup([["🔙 رجوع للوحة التحكم"]], resize_keyboard=True)
        )
        return ConversationHandler.END
    
    confirm_keyboard = [
        ["✅ نعم، أرسل الإشعار", "❌ لا، إلغاء الإرسال"]
    ]
    
    await update.message.reply_text(
        f"📢 <b>تأكيد الإرسال</b>\n\n"
        f"النص:\n{broadcast_text[:500]}...\n\n"
        f"<b>سيتم إرسال هذا الإشعار لجميع المستخدمين.</b>\n"
        f"هل تريد المتابعة؟",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(confirm_keyboard, resize_keyboard=True)
    )
    
    context.user_data['broadcast_text'] = broadcast_text
    return ADMIN_STATE

async def confirm_broadcast(update: Update, context: CallbackContext):
    """تأكيد وإرسال الإشعار الجماعي"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return ConversationHandler.END
    
    if update.message.text == "✅ نعم، أرسل الإشعار":
        broadcast_text = context.user_data.get('broadcast_text', '')
        
        progress_msg = await update.message.reply_text(
            "📤 <b>جاري إرسال الإشعارات...</b>\n"
            "قد يستغرق ذلك بضع دقائق.",
            parse_mode=ParseMode.HTML
        )
        
        all_users = get_all_users()
        success_count = 0
        fail_count = 0
        
        for user in all_users:
            if not user.get('is_banned'):
                try:
                    await send_notification(user['user_id'], broadcast_text, context)
                    success_count += 1
                    await asyncio.sleep(0.1)
                except Exception as e:
                    logger.error(f"خطأ في إرسال إشعار للمستخدم {user['user_id']}: {e}")
                    fail_count += 1
        
        await progress_msg.delete()
        
        await update.message.reply_text(
            f"✅ <b>تم إرسال الإشعارات بنجاح</b>\n\n"
            f"📊 <b>الإحصائيات:</b>\n"
            f"• الإشعارات الناجحة: {success_count}\n"
            f"• الإشعارات الفاشلة: {fail_count}\n"
            f"• الإجمالي: {len(all_users)}\n\n"
            f"📅 الوقت: {datetime.now().strftime('%H:%M:%S')}",
            parse_mode=ParseMode.HTML,
            reply_markup=ReplyKeyboardMarkup([["🔙 رجوع للوحة التحكم"]], resize_keyboard=True)
        )
        
        context.user_data.pop('broadcast_text', None)
        context.user_data.pop('admin_action', None)
        
        return ConversationHandler.END
    
    else:
        await update.message.reply_text(
            "تم إلغاء الإشعار الجماعي.",
            reply_markup=ReplyKeyboardMarkup([["🔙 رجوع للوحة التحكم"]], resize_keyboard=True)
        )
        return ConversationHandler.END

async def cancel_admin(update: Update, context: CallbackContext) -> int:
    """إلغاء الإجراءات الإدارية"""
    await update.message.reply_text(
        "تم إلغاء العملية.",
        reply_markup=ReplyKeyboardMarkup([["🔙 رجوع للوحة التحكم"]], resize_keyboard=True)
    )
    
    for key in list(context.user_data.keys()):
        if key.startswith('admin_') or key in ['charge_user_id', 'broadcast_text']:
            context.user_data.pop(key, None)
    
    return ConversationHandler.END

# ========== معالجة الرسائل العادية ==========
async def handle_message(update: Update, context: CallbackContext):
    """معالجة الرسائل النصية العادية"""
    text = update.message.text
    
    if text == "🏠 الرئيسية":
        await start_command(update, context)
    
    elif text == "📊 حساب درجة الإعفاء":
        await exemption_start(update, context)
    
    elif text == "📝 تلخيص الملازم":
        await summarize_start(update, context)
    
    elif text == "❓ سؤال وجواب":
        await qa_start(update, context)
    
    elif text == "📚 ملازمي ومرشحاتي":
        await materials_command(update, context)
    
    elif text == "💰 رصيدي":
        await balance_command(update, context)
    
    elif text == "👥 دعوة أصدقاء":
        await referral_command(update, context)
    
    elif text == "ℹ️ معلومات":
        await info_command(update, context)
    
    elif text == "👑 لوحة التحكم":
        await admin_panel(update, context)
    
    elif text == "📊 الإحصائيات":
        await admin_stats(update, context)
    
    elif text == "👥 إدارة المستخدمين":
        await admin_panel(update, context)
    
    elif text == "💰 الشحن والرصيد":
        await admin_charge(update, context)
    
    elif text == "⚙️ إعدادات البوت":
        await admin_settings(update, context)
    
    elif text == "📁 إدارة المواد":
        await admin_materials(update, context)
    
    elif text == "🔧 إعدادات الخدمات":
        await admin_services(update, context)
    
    elif text == "📢 إرسال إشعار":
        await admin_broadcast(update, context)
    
    elif text == "🔙 رجوع للوحة التحكم":
        await admin_panel(update, context)
    
    elif text.startswith("📄 "):
        await handle_material_selection(update, context)
    
    elif text in ["❌ إلغاء", "إلغاء"]:
        await update.message.reply_text(
            "تم الإلغاء.",
            reply_markup=ReplyKeyboardMarkup([["🏠 الرئيسية"]], resize_keyboard=True)
        )
    
    else:
        if context.user_data.get('admin_action'):
            if context.user_data.get('admin_action') == 'broadcast':
                await handle_broadcast(update, context)
            elif update.message.text in ["✅ نعم، أرسل الإشعار", "❌ لا، إلغاء الإرسال"]:
                await confirm_broadcast(update, context)
            else:
                await handle_settings_input(update, context)
        else:
            await update.message.reply_text(
                "لم أفهم رسالتك. الرجاء استخدام الأزرار أو الأوامر المتاحة.",
                reply_markup=ReplyKeyboardMarkup([["🏠 الرئيسية"]], resize_keyboard=True)
            )

async def error_handler(update: Update, context: CallbackContext):
    """معالجة الأخطاء"""
    logger.error(f"حدث خطأ: {context.error}", exc_info=context.error)
    
    try:
        if update and update.effective_user:
            await update.message.reply_text(
                "❌ حدث خطأ غير متوقع. الرجاء المحاولة مرة أخرى.\n"
                "إذا تكرر الخطأ، راسل الدعم الفني.",
                reply_markup=ReplyKeyboardMarkup([["🏠 الرئيسية"]], resize_keyboard=True)
            )
    except:
        pass

# ========== الدالة الرئيسية ==========
def main():
    """الدالة الرئيسية لتشغيل البوت"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    exemption_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📊 حساب درجة الإعفاء$"), exemption_start)],
        states={
            WAITING_FOR_COURSE1: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_course1)],
            WAITING_FOR_COURSE2: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_course2)],
            WAITING_FOR_COURSE3: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_course3)],
        },
        fallbacks=[MessageHandler(filters.Regex("^(إلغاء|❌ إلغاء)$"), cancel_exemption)],
    )
    
    summarize_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📝 تلخيص الملازم$"), summarize_start)],
        states={
            SUMMARIZE_STATE: [
                MessageHandler(filters.Document.PDF, handle_pdf),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_pdf)
            ],
        },
        fallbacks=[MessageHandler(filters.Regex("^(إلغاء|❌ إلغاء)$"), cancel_summarize)],
    )
    
    qa_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^❓ سؤال وجواب$"), qa_start)],
        states={
            QA_STATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question),
                MessageHandler(filters.PHOTO, handle_question),
                MessageHandler(filters.Document.ALL, handle_question)
            ],
        },
        fallbacks=[MessageHandler(filters.Regex("^(إلغاء|❌ إلغاء)$"), handle_question)],
    )
    
    admin_conv = ConversationHandler(
        entry_points=[],
        states={
            ADMIN_STATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_action),
            ],
        },
        fallbacks=[MessageHandler(filters.Regex("^(إلغاء|❌ إلغاء)$"), cancel_admin)],
    )
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("referral", referral_command))
    application.add_handler(CommandHandler("info", info_command))
    
    application.add_handler(exemption_conv)
    application.add_handler(summarize_conv)
    application.add_handler(qa_conv)
    application.add_handler(admin_conv)
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    
    logger.info("🤖 بوت 'يلا نتعلم' يعمل الآن...")
    print("=" * 50)
    print("🎓 بوت 'يلا نتعلم' يعمل بنجاح!")
    print(f"🤖 اليوزر: {BOT_USERNAME}")
    print(f"👨‍💻 المطور: {ADMIN_USERNAME}")
    print(f"📊 قاعدة البيانات: bot_database.db")
    print(f"📝 السجلات: bot.log")
    print("=" * 50)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
