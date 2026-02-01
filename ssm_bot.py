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
from datetime import datetime
from typing import Dict, Optional
from uuid import uuid4
from io import BytesIO

import fitz  # PyMuPDF
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping
import google.generativeai as genai
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
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
MY_USER_ID = 6130994941  # أيديك

# تسعيرة الخدمات
DEFAULT_PRICES = {
    "exemption": 1000,
    "summarize": 1000,
    "qa": 1000,
    "materials": 1000
}

WELCOME_BONUS = 1000
REFERRAL_BONUS = 500

# حالات المحادثة
(
    EXEMPTION_COURSE1, EXEMPTION_COURSE2, EXEMPTION_COURSE3,
    SUMMARIZE_PDF,
    QA_QUESTION,
    ADMIN_CHARGE_USER, ADMIN_CHARGE_AMOUNT,
    ADMIN_BAN_USER, ADMIN_UNBAN_USER,
    ADMIN_ADD_NAME, ADMIN_ADD_DESC, ADMIN_ADD_FILE, ADMIN_ADD_CATEGORY,
    ADMIN_CHANGE_PRICE,
    ADMIN_BROADCAST,
    ADMIN_SET_CHANNEL,
    ADMIN_SET_SUPPORT,
    ADMIN_SET_WELCOME,
    ADMIN_SET_REFERRAL
) = range(20)

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

# ========== قاعدة البيانات ==========
def init_database():
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    c = conn.cursor()
    
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
    
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        type TEXT,
        amount INTEGER,
        service TEXT,
        details TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS service_stats (
        service TEXT PRIMARY KEY,
        usage_count INTEGER DEFAULT 0,
        total_income INTEGER DEFAULT 0
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS bot_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS materials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        description TEXT,
        file_id TEXT,
        category TEXT,
        added_by INTEGER,
        added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # إعدادات افتراضية
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

db_conn = init_database()

# ========== دوال قاعدة البيانات ==========
def get_user(user_id: int):
    c = db_conn.cursor()
    c.execute('''SELECT * FROM users WHERE user_id = ?''', (user_id,))
    row = c.fetchone()
    if row:
        columns = [desc[0] for desc in c.description]
        return dict(zip(columns, row))
    return None

def update_balance(user_id: int, amount: int, trans_type: str, service: str = None):
    c = db_conn.cursor()
    c.execute('''UPDATE users SET balance = balance + ? WHERE user_id = ?''', 
              (amount, user_id))
    
    if trans_type == 'purchase' and amount < 0:
        c.execute('''UPDATE users SET total_spent = total_spent + ? WHERE user_id = ?''',
                  (abs(amount), user_id))
    
    details = json.dumps({"service": service} if service else {})
    c.execute('''INSERT INTO transactions (user_id, type, amount, service, details)
                 VALUES (?, ?, ?, ?, ?)''',
              (user_id, trans_type, amount, service or '', details))
    
    if trans_type == 'purchase' and service:
        c.execute('''INSERT OR REPLACE INTO service_stats (service, usage_count, total_income)
                     VALUES (?, COALESCE((SELECT usage_count FROM service_stats WHERE service = ?), 0) + 1,
                     COALESCE((SELECT total_income FROM service_stats WHERE service = ?), 0) + ?)''',
                  (service, service, service, abs(amount)))
    
    db_conn.commit()

def get_bot_setting(key: str, default=None):
    c = db_conn.cursor()
    c.execute('''SELECT value FROM bot_settings WHERE key = ?''', (key,))
    result = c.fetchone()
    return result[0] if result else default

def set_bot_setting(key: str, value: str):
    c = db_conn.cursor()
    c.execute('''INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)''',
              (key, str(value)))
    db_conn.commit()

def get_all_users():
    c = db_conn.cursor()
    c.execute('''SELECT * FROM users ORDER BY join_date DESC''')
    columns = [desc[0] for desc in c.description]
    return [dict(zip(columns, row)) for row in c.fetchall()]

def get_user_stats():
    c = db_conn.cursor()
    stats = {}
    c.execute('''SELECT COUNT(*) FROM users''')
    stats['total'] = c.fetchone()[0]
    c.execute('''SELECT COUNT(*) FROM users WHERE date(join_date) = date('now')''')
    stats['today'] = c.fetchone()[0]
    c.execute('''SELECT COUNT(*) FROM users WHERE is_banned = 1''')
    stats['banned'] = c.fetchone()[0]
    c.execute('''SELECT COUNT(*) FROM users WHERE is_admin = 1''')
    stats['admins'] = c.fetchone()[0]
    c.execute('''SELECT SUM(balance) FROM users''')
    stats['balance'] = c.fetchone()[0] or 0
    c.execute('''SELECT SUM(total_spent) FROM users''')
    stats['spent'] = c.fetchone()[0] or 0
    return stats

def add_material(name: str, description: str, file_id: str, category: str, added_by: int):
    c = db_conn.cursor()
    c.execute('''INSERT INTO materials (name, description, file_id, category, added_by)
                 VALUES (?, ?, ?, ?, ?)''',
              (name, description, file_id, category, added_by))
    db_conn.commit()

def get_materials():
    c = db_conn.cursor()
    c.execute('''SELECT * FROM materials ORDER BY added_date DESC''')
    columns = [desc[0] for desc in c.description]
    return [dict(zip(columns, row)) for row in c.fetchall()]

def is_admin_user(user_id: int):
    user = get_user(user_id)
    return user and (user['user_id'] == MY_USER_ID or user.get('is_admin') == 1)

# ========== الذكاء الاصطناعي Gemini ==========
try:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-pro')
    logger.info("✅ Gemini AI متصل بنجاح")
except Exception as e:
    logger.error(f"❌ خطأ في ربط Gemini: {e}")
    gemini_model = None

def extract_text_from_pdf(pdf_path: str) -> str:
    text = ""
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            text += page.get_text() + "\n"
        doc.close()
    except Exception as e:
        logger.error(f"خطأ في استخراج النص: {e}")
    return text

async def summarize_pdf_with_ai(pdf_text: str) -> str:
    if not gemini_model:
        return "❌ خدمة الذكاء الاصطناعي غير متاحة حالياً"
    
    try:
        prompt = f"""أنت مساعد تعليمي عراقي. قم بتلخيص النص الدراسي التالي:
        
{pdf_text[:3000]}
        
الرجاء التلخيص ب:
1. لغة عربية واضحة
2. ترتيب الأفكار الرئيسية
3. حذف المعلومات غير المهمة
4. جعل التلخيص مناسب للمراجعة"""
        
        response = await asyncio.to_thread(gemini_model.generate_content, prompt)
        return response.text if response.text else "❌ لم أتمكن من التلخيص"
    except Exception as e:
        logger.error(f"خطأ في التلخيص: {e}")
        return f"❌ حدث خطأ: {str(e)}"

async def answer_question_with_ai(question: str) -> str:
    if not gemini_model:
        return "❌ خدمة الذكاء الاصطناعي غير متاحة حالياً"
    
    try:
        prompt = f"""أنت معلم عراقي متخصص. أجب على السؤال التالي:
        
{question}
        
الرجاء الإجابة ب:
1. معلومات علمية دقيقة
2. لغة عربية واضحة
3. أمثلة إن أمكن
4. مناسبة للمناهج العراقية"""
        
        response = await asyncio.to_thread(gemini_model.generate_content, prompt)
        return response.text if response.text else "❌ لم أتمكن من الإجابة"
    except Exception as e:
        logger.error(f"خطأ في الإجابة: {e}")
        return f"❌ حدث خطأ: {str(e)}"

def create_pdf(content: str, title: str = "ملخص دراسي") -> BytesIO:
    buffer = BytesIO()
    try:
        c = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        
        c.setFont("Helvetica-Bold", 16)
        c.drawCentredString(width/2, height - 50, title)
        
        c.setFont("Helvetica", 12)
        y = height - 100
        lines = content.split('\n')
        
        for line in lines:
            if y < 50:
                c.showPage()
                c.setFont("Helvetica", 12)
                y = height - 50
            c.drawString(50, y, line[:90])
            y -= 20
        
        c.save()
        buffer.seek(0)
        return buffer
    except Exception as e:
        logger.error(f"خطأ في إنشاء PDF: {e}")
        return None

# ========== دوال مساعدة ==========
def format_money(amount: int) -> str:
    return f"{amount:,} دينار عراقي"

def get_main_keyboard(user_id: int):
    keyboard = [
        [InlineKeyboardButton("📊 حساب درجة الإعفاء", callback_data="service_exemption")],
        [InlineKeyboardButton("📝 تلخيص الملازم", callback_data="service_summarize")],
        [InlineKeyboardButton("❓ سؤال وجواب", callback_data="service_qa")],
        [InlineKeyboardButton("📚 ملازمي ومرشحاتي", callback_data="service_materials")],
        [
            InlineKeyboardButton("💰 رصيدي", callback_data="balance"),
            InlineKeyboardButton("👥 دعوة أصدقاء", callback_data="referral"),
            InlineKeyboardButton("ℹ️ معلومات", callback_data="info")
        ]
    ]
    
    if is_admin_user(user_id):
        keyboard.append([InlineKeyboardButton("👑 لوحة التحكم", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(keyboard)

async def check_balance(update_or_query, service: str, user_id: int = None) -> bool:
    if user_id is None:
        if isinstance(update_or_query, Update):
            user_id = update_or_query.effective_user.id
        else:
            user_id = update_or_query.from_user.id
    
    user = get_user(user_id)
    if not user:
        return False
    
    # التحقق من الصيانة
    if get_bot_setting('maintenance_mode') == '1':
        msg = "⚙️ البوت في وضع الصيانة حالياً"
        if isinstance(update_or_query, Update):
            await update_or_query.message.reply_text(msg)
        else:
            await update_or_query.edit_message_text(msg)
        return False
    
    # التحقق من الحظر
    if user.get('is_banned'):
        msg = "🚫 حسابك محظور"
        if isinstance(update_or_query, Update):
            await update_or_query.message.reply_text(msg)
        else:
            await update_or_query.edit_message_text(msg)
        return False
    
    price = int(get_bot_setting(f'price_{service}', DEFAULT_PRICES.get(service, 1000)))
    
    if user['balance'] >= price:
        update_balance(user_id, -price, 'purchase', service)
        
        # إشعار الخصم
        new_balance = user['balance'] - price
        msg = f"✅ تم خصم {format_money(price)}\n💰 الرصيد المتبقي: {format_money(new_balance)}"
        
        if isinstance(update_or_query, Update):
            await update_or_query.message.reply_text(msg)
        else:
            try:
                await update_or_query.edit_message_text(
                    f"{update_or_query.message.text}\n\n{msg}"
                )
            except:
                pass
        
        return True
    else:
        msg = f"⚠️ رصيدك غير كافي\nالسعر: {format_money(price)}\nرصيدك: {format_money(user['balance'])}"
        if isinstance(update_or_query, Update):
            await update_or_query.message.reply_text(msg)
        else:
            await update_or_query.edit_message_text(msg)
        return False

# ========== الأمر /start ==========
async def start_command(update: Update, context: CallbackContext):
    user = update.effective_user
    user_id = user.id
    
    c = db_conn.cursor()
    c.execute('''INSERT OR IGNORE INTO users 
                 (user_id, username, first_name, last_name, referral_code) 
                 VALUES (?, ?, ?, ?, ?)''',
              (user_id, user.username, user.first_name, user.last_name, str(uuid4())[:8]))
    
    # نظام الدعوة
    if context.args and context.args[0].startswith('ref_'):
        referral_code = context.args[0][4:]
        c.execute('''SELECT user_id FROM users WHERE referral_code = ?''', (referral_code,))
        referrer = c.fetchone()
        if referrer:
            referral_bonus = int(get_bot_setting('referral_bonus', REFERRAL_BONUS))
            update_balance(referrer[0], referral_bonus, 'referral')
            c.execute('''UPDATE users SET referred_by = ? WHERE user_id = ?''', (referrer[0], user_id))
    
    # هدية ترحيبية للمستخدم الجديد
    if c.rowcount > 0:
        welcome_bonus = int(get_bot_setting('welcome_bonus', WELCOME_BONUS))
        update_balance(user_id, welcome_bonus, 'bonus', 'welcome')
    
    db_conn.commit()
    
    user_data = get_user(user_id)
    referral_link = f"https://t.me/{BOT_USERNAME.replace('@', '')}?start=ref_{user_data.get('referral_code', '')}"
    
    welcome_text = f"""
🎓 <b>مرحباً بك في بوت 'يلا نتعلم'!</b>

💰 <b>رصيدك الحالي:</b> {format_money(user_data.get('balance', 0) if user_data else 0)}
🆔 <b>الأيدي الخاص بك:</b> {user_id}

🔗 <b>رابط الدعوة:</b>
{referral_link}

💸 <b>مكافأة الدعوة:</b> {format_money(int(get_bot_setting('referral_bonus', REFERRAL_BONUS)))}
🎁 <b>الهدية الترحيبية:</b> {format_money(int(get_bot_setting('welcome_bonus', WELCOME_BONUS)))}

📌 <b>الخدمات المتاحة:</b>
• حساب درجة الإعفاء - {format_money(int(get_bot_setting('price_exemption', 1000)))}
• تلخيص الملازم - {format_money(int(get_bot_setting('price_summarize', 1000)))}
• سؤال وجواب - {format_money(int(get_bot_setting('price_qa', 1000)))}
• ملازمي ومرشحاتي - {format_money(int(get_bot_setting('price_materials', 1000)))}
    """
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_keyboard(user_id),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

# ========== معالج الأزرار الرئيسي ==========
async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    if data == "service_exemption":
        await start_exemption_service(query, context)
    elif data == "service_summarize":
        await start_summarize_service(query, context)
    elif data == "service_qa":
        await start_qa_service(query, context)
    elif data == "service_materials":
        await show_materials_menu(query)
    elif data == "balance":
        await show_balance_info(query)
    elif data == "referral":
        await show_referral_info(query)
    elif data == "info":
        await show_bot_info(query)
    elif data == "admin_panel":
        if is_admin_user(user_id):
            await show_admin_panel_menu(query)
        else:
            await query.edit_message_text("⛔ غير مصرح لك!")
    elif data.startswith("mat_"):
        await send_material_file(query, context)
    elif data == "back_to_main":
        await return_to_main_menu(query)
    elif data.startswith("admin_"):
        await handle_admin_buttons(query, context)

# ========== الخدمة 1: حساب الإعفاء ==========
async def start_exemption_service(query, context):
    if await check_balance(query, 'exemption'):
        await query.edit_message_text(
            "📊 <b>حساب درجة الإعفاء</b>\n\n"
            "أدخل <b>درجة الكورس الأول</b> (0-100):",
            parse_mode=ParseMode.HTML
        )
        context.user_data['exemption_user'] = query.from_user.id
        return EXEMPTION_COURSE1
    return ConversationHandler.END

async def process_exemption_course1(update: Update, context: CallbackContext):
    try:
        score = float(update.message.text)
        if 0 <= score <= 100:
            context.user_data['course1'] = score
            await update.message.reply_text(
                f"✅ تم حفظ الدرجة: {score}\n\n"
                "أدخل <b>درجة الكورس الثاني</b> (0-100):",
                parse_mode=ParseMode.HTML
            )
            return EXEMPTION_COURSE2
    except:
        pass
    
    await update.message.reply_text("❌ الرجاء إدخال رقم بين 0 و 100")
    return EXEMPTION_COURSE1

async def process_exemption_course2(update: Update, context: CallbackContext):
    try:
        score = float(update.message.text)
        if 0 <= score <= 100:
            context.user_data['course2'] = score
            await update.message.reply_text(
                f"✅ تم حفظ الدرجة: {score}\n\n"
                "أدخل <b>درجة الكورس الثالث</b> (0-100):",
                parse_mode=ParseMode.HTML
            )
            return EXEMPTION_COURSE3
    except:
        pass
    
    await update.message.reply_text("❌ الرجاء إدخال رقم بين 0 و 100")
    return EXEMPTION_COURSE2

async def process_exemption_course3(update: Update, context: CallbackContext):
    try:
        score = float(update.message.text)
        if 0 <= score <= 100:
            c1 = context.user_data.get('course1', 0)
            c2 = context.user_data.get('course2', 0)
            c3 = score
            
            average = (c1 + c2 + c3) / 3
            
            if average >= 90:
                result = "🎉 <b>مبروك! أنت معفي من المادة</b> 🎉"
                emoji = "✅"
            else:
                result = "📝 <b>أنت غير معفي من المادة</b>"
                emoji = "❌"
            
            msg = f"""
{emoji} <b>نتيجة حساب الإعفاء</b> {emoji}

📊 <b>الدرجات المدخلة:</b>
• الكورس الأول: {c1}
• الكورس الثاني: {c2}
• الكورس الثالث: {c3}

⚖️ <b>المعدل العام:</b> {average:.2f}

{result}

{"🎯 تحتاج إلى " + str(90 - average) + " درجة إضافية للإعفاء" if average < 90 else "🎊 تهانينا على هذا الإنجاز!"}
            """
            
            await update.message.reply_text(
                msg,
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_keyboard(update.effective_user.id)
            )
            
            context.user_data.clear()
            return ConversationHandler.END
    except:
        pass
    
    await update.message.reply_text("❌ الرجاء إدخال رقم بين 0 و 100")
    return EXEMPTION_COURSE3

# ========== الخدمة 2: تلخيص PDF ==========
async def start_summarize_service(query, context):
    if await check_balance(query, 'summarize'):
        await query.edit_message_text(
            "📝 <b>تلخيص الملازم</b>\n\n"
            "⏳ الرجاء إرسال ملف PDF الآن:\n"
            "<i>يمكن أن يستغرق التلخيص بضع دقائق</i>",
            parse_mode=ParseMode.HTML
        )
        return SUMMARIZE_PDF
    return ConversationHandler.END

async def process_pdf_summarize(update: Update, context: CallbackContext):
    if update.message.document and update.message.document.mime_type == 'application/pdf':
        processing_msg = await update.message.reply_text(
            "⏳ <b>جاري معالجة الملف وتلخيصه...</b>",
            parse_mode=ParseMode.HTML
        )
        
        try:
            file = await context.bot.get_file(update.message.document.file_id)
            file_path = f"temp_{update.message.document.file_id}.pdf"
            await file.download_to_drive(file_path)
            
            # استخراج النص
            pdf_text = extract_text_from_pdf(file_path)
            
            if len(pdf_text) < 50:
                await processing_msg.edit_text("❌ الملف فارغ أو لا يمكن قراءته")
                os.remove(file_path)
                return SUMMARIZE_PDF
            
            # التلخيص بالذكاء الاصطناعي
            await processing_msg.edit_text("🤖 <b>جاري تلخيص المحتوى باستخدام الذكاء الاصطناعي...</b>", 
                                         parse_mode=ParseMode.HTML)
            
            summary = await summarize_pdf_with_ai(pdf_text)
            
            # إنشاء PDF
            await processing_msg.edit_text("📄 <b>جاري إنشاء ملف PDF ملخص...</b>", 
                                         parse_mode=ParseMode.HTML)
            
            pdf_buffer = create_pdf(summary, "ملخص دراسي")
            
            if pdf_buffer:
                await update.message.reply_document(
                    document=InputFile(pdf_buffer, filename="ملخص_دراسي.pdf"),
                    caption="📚 <b>ملخص دراسي جاهز</b>\n\n✅ تم تلخيص الملف بنجاح",
                    parse_mode=ParseMode.HTML
                )
                pdf_buffer.close()
            else:
                await update.message.reply_text(
                    f"📝 <b>ملخص المحتوى:</b>\n\n{summary[:2000]}...",
                    parse_mode=ParseMode.HTML
                )
            
            os.remove(file_path)
            await processing_msg.delete()
            
            await update.message.reply_text(
                "✅ تم الانتهاء من التلخيص",
                reply_markup=get_main_keyboard(update.effective_user.id)
            )
            return ConversationHandler.END
            
        except Exception as e:
            logger.error(f"خطأ في معالجة PDF: {e}")
            await processing_msg.edit_text(f"❌ حدث خطأ: {str(e)}")
            return SUMMARIZE_PDF
    
    await update.message.reply_text("❌ الرجاء إرسال ملف PDF فقط")
    return SUMMARIZE_PDF

# ========== الخدمة 3: سؤال وجواب ==========
async def start_qa_service(query, context):
    if await check_balance(query, 'qa'):
        await query.edit_message_text(
            "❓ <b>سؤال وجواب</b>\n\n"
            "🧠 يمكنني الإجابة على أسئلتك الدراسية باستخدام الذكاء الاصطناعي\n\n"
            "📝 <b>أرسل سؤالك الآن:</b>",
            parse_mode=ParseMode.HTML
        )
        return QA_QUESTION
    return ConversationHandler.END

async def process_qa_question(update: Update, context: CallbackContext):
    question = update.message.text
    
    if len(question) < 5:
        await update.message.reply_text("❌ الرجاء كتابة سؤال واضح ومفصل")
        return QA_QUESTION
    
    processing_msg = await update.message.reply_text(
        "🤖 <b>جاري تحليل السؤال وإعداد الإجابة...</b>",
        parse_mode=ParseMode.HTML
    )
    
    try:
        answer = await answer_question_with_ai(question)
        
        await processing_msg.delete()
        await update.message.reply_text(
            f"💡 <b>إجابة على سؤالك:</b>\n\n{answer}\n\n"
            f"📌 <i>تمت الإجابة باستخدام الذكاء الاصطناعي</i>",
            parse_mode=ParseMode.HTML
        )
        
        await update.message.reply_text(
            "✅ تم الانتهاء من الإجابة",
            reply_markup=get_main_keyboard(update.effective_user.id)
        )
        return ConversationHandler.END
        
    except Exception as e:
        await processing_msg.edit_text(f"❌ حدث خطأ: {str(e)}")
        return QA_QUESTION

# ========== الخدمة 4: المواد التعليمية ==========
async def show_materials_menu(query):
    if not await check_balance(query, 'materials'):
        return
    
    materials = get_materials()
    
    if not materials:
        await query.edit_message_text(
            "📚 <b>ملازمي ومرشحاتي</b>\n\n"
            "⚠️ لا توجد مواد متاحة حالياً.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard(query.from_user.id)
        )
        return
    
    keyboard = []
    for mat in materials[:10]:
        keyboard.append([InlineKeyboardButton(f"📄 {mat['name'][:30]}", callback_data=f"mat_{mat['id']}")])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")])
    
    await query.edit_message_text(
        "📚 <b>ملازمي ومرشحاتي</b>\n\n"
        "اختر المادة التي تريد تحميلها:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def send_material_file(query, context):
    material_id = int(query.data.replace("mat_", ""))
    
    c = db_conn.cursor()
    c.execute('''SELECT * FROM materials WHERE id = ?''', (material_id,))
    material = c.fetchone()
    
    if material:
        try:
            await context.bot.send_document(
                chat_id=query.from_user.id,
                document=material[3],  # file_id
                caption=f"📚 <b>{material[1]}</b>\n\n{material[2]}\n\n📁 التصنيف: {material[4]}",
                parse_mode=ParseMode.HTML
            )
            await query.answer("✅ تم إرسال الملف")
        except Exception as e:
            await query.edit_message_text("❌ حدث خطأ في إرسال الملف")
            logger.error(f"خطأ في إرسال الملف: {e}")
    else:
        await query.edit_message_text("❌ المادة غير موجودة")
    
    await show_materials_menu(query)

# ========== معلومات المستخدم ==========
async def show_balance_info(query):
    user = get_user(query.from_user.id)
    if user:
        c = db_conn.cursor()
        c.execute('''SELECT COUNT(*) FROM users WHERE referred_by = ?''', (query.from_user.id,))
        referrals = c.fetchone()[0]
        
        await query.edit_message_text(
            f"💰 <b>حسابك المالي</b>\n\n"
            f"⚖️ <b>الرصيد الحالي:</b> {format_money(user.get('balance', 0))}\n"
            f"💸 <b>إجمالي المشتريات:</b> {format_money(user.get('total_spent', 0))}\n"
            f"👥 <b>عدد المدعوين:</b> {referrals}\n\n"
            f"💳 <b>للتعبئة راسل:</b> {get_bot_setting('support_username', ADMIN_USERNAME)}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard(query.from_user.id)
        )

async def show_referral_info(query):
    user = get_user(query.from_user.id)
    if user:
        referral_link = f"https://t.me/{BOT_USERNAME.replace('@', '')}?start=ref_{user.get('referral_code', '')}"
        
        c = db_conn.cursor()
        c.execute('''SELECT COUNT(*) FROM users WHERE referred_by = ?''', (query.from_user.id,))
        referrals = c.fetchone()[0]
        
        total_bonus = referrals * int(get_bot_setting('referral_bonus', REFERRAL_BONUS))
        
        await query.edit_message_text(
            f"👥 <b>نظام الدعوة</b>\n\n"
            f"🔗 <b>رابط دعوتك:</b>\n{referral_link}\n\n"
            f"📊 <b>إحصائيات:</b>\n"
            f"• عدد المدعوين: {referrals}\n"
            f"• إجمالي المكافآت: {format_money(total_bonus)}\n"
            f"• مكافأة كل دعوة: {format_money(int(get_bot_setting('referral_bonus', REFERRAL_BONUS)))}",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=get_main_keyboard(query.from_user.id)
        )

async def show_bot_info(query):
    stats = get_user_stats()
    
    await query.edit_message_text(
        f"🤖 <b>معلومات البوت</b>\n\n"
        f"👨‍💻 <b>المطور:</b> {ADMIN_USERNAME}\n"
        f"💰 <b>نظام الدفع:</b> الدينار العراقي\n"
        f"👤 <b>عدد المستخدمين:</b> {stats['total']}\n"
        f"💸 <b>أقل سعر خدمة:</b> {format_money(1000)}\n\n"
        f"📞 <b>الدعم الفني:</b> {get_bot_setting('support_username', ADMIN_USERNAME)}\n"
        f"📢 <b>القناة:</b> {get_bot_setting('channel_url', 'غير محدد')}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(query.from_user.id)
    )

async def return_to_main_menu(query):
    user = query.from_user
    user_data = get_user(user.id)
    
    welcome_text = f"""
🎓 <b>مرحباً بك في بوت 'يلا نتعلم'!</b>

💰 <b>رصيدك الحالي:</b> {format_money(user_data.get('balance', 0) if user_data else 0)}
🆔 <b>الأيدي الخاص بك:</b> {user.id}
    """
    
    await query.edit_message_text(
        welcome_text,
        reply_markup=get_main_keyboard(user.id),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

# ========== لوحة التحكم ==========
async def show_admin_panel_menu(query):
    keyboard = [
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
        [InlineKeyboardButton("💰 شحن رصيد", callback_data="admin_charge")],
        [InlineKeyboardButton("🚫 حظر مستخدم", callback_data="admin_ban")],
        [InlineKeyboardButton("✅ فك حظر", callback_data="admin_unban")],
        [InlineKeyboardButton("📤 إضافة مادة", callback_data="admin_add_material")],
        [InlineKeyboardButton("⚙️ تغيير الأسعار", callback_data="admin_change_prices")],
        [InlineKeyboardButton("📢 إرسال إشعار", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🔧 الإعدادات العامة", callback_data="admin_settings")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        "👑 <b>لوحة التحكم</b>\n\n"
        "اختر القسم الذي تريد إدارته:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_admin_buttons(query, context):
    data = query.data
    
    if data == "admin_stats":
        await show_admin_stats(query)
    elif data == "admin_charge":
        await query.edit_message_text(
            "💰 <b>شحن رصيد مستخدم</b>\n\n"
            "أرسل <b>آيدي المستخدم</b> الذي تريد شحن رصيده:",
            parse_mode=ParseMode.HTML
        )
        return ADMIN_CHARGE_USER
    elif data == "admin_ban":
        await query.edit_message_text(
            "🚫 <b>حظر مستخدم</b>\n\n"
            "أرسل <b>آيدي المستخدم</b> الذي تريد حظره:",
            parse_mode=ParseMode.HTML
        )
        return ADMIN_BAN_USER
    elif data == "admin_unban":
        await query.edit_message_text(
            "✅ <b>فك حظر مستخدم</b>\n\n"
            "أرسل <b>آيدي المستخدم</b> الذي تريد فك حظره:",
            parse_mode=ParseMode.HTML
        )
        return ADMIN_UNBAN_USER
    elif data == "admin_add_material":
        await query.edit_message_text(
            "📤 <b>إضافة مادة تعليمية</b>\n\n"
            "أرسل <b>اسم المادة</b>:",
            parse_mode=ParseMode.HTML
        )
        return ADMIN_ADD_NAME
    elif data == "admin_change_prices":
        await show_change_prices_menu(query)
    elif data == "admin_broadcast":
        await query.edit_message_text(
            "📢 <b>إرسال إشعار جماعي</b>\n\n"
            "أرسل <b>نص الإشعار</b> الذي تريد إرساله لجميع المستخدمين:",
            parse_mode=ParseMode.HTML
        )
        return ADMIN_BROADCAST
    elif data == "admin_settings":
        await show_admin_settings_menu(query)
    elif data.startswith("change_price_"):
        service = data.replace("change_price_", "")
        context.user_data['change_price_service'] = service
        
        service_name = {
            "exemption": "حساب الإعفاء",
            "summarize": "تلخيص PDF",
            "qa": "سؤال وجواب",
            "materials": "الملازم"
        }.get(service, service)
        
        current_price = int(get_bot_setting(f'price_{service}', 1000))
        
        await query.edit_message_text(
            f"💰 <b>تغيير سعر الخدمة</b>\n\n"
            f"الخدمة: {service_name}\n"
            f"السعر الحالي: {format_money(current_price)}\n\n"
            f"أرسل <b>السعر الجديد</b> (بالدينار العراقي):",
            parse_mode=ParseMode.HTML
        )
        return ADMIN_CHANGE_PRICE

async def show_admin_stats(query):
    stats = get_user_stats()
    
    c = db_conn.cursor()
    c.execute('''SELECT service, usage_count, total_income FROM service_stats''')
    service_stats = c.fetchall()
    
    stats_text = f"""
📊 <b>إحصائيات البوت الشاملة</b>

👤 <b>المستخدمين:</b>
• الإجمالي: {stats['total']}
• الجدد اليوم: {stats['today']}
• المحظورين: {stats['banned']}
• المشرفين: {stats['admins']}

💰 <b>المالية:</b>
• إجمالي الأرصدة: {format_money(stats['balance'])}
• إجمالي المشتريات: {format_money(stats['spent'])}

🛠 <b>إحصائيات الخدمات:</b>
"""
    
    for service_stat in service_stats:
        service_name = {
            'exemption': 'حساب الإعفاء',
            'summarize': 'تلخيص PDF',
            'qa': 'سؤال وجواب',
            'materials': 'الملازم'
        }.get(service_stat[0], service_stat[0])
        
        stats_text += f"• {service_name}: {service_stat[1]} استخدام ({format_money(service_stat[2])})\n"
    
    c.execute('''SELECT COUNT(*) FROM materials''')
    materials_count = c.fetchone()[0]
    
    stats_text += f"\n📚 <b>المواد التعليمية:</b> {materials_count} مادة"
    
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]
    
    await query.edit_message_text(
        stats_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_change_prices_menu(query):
    keyboard = [
        [InlineKeyboardButton("💰 حساب الإعفاء", callback_data="change_price_exemption")],
        [InlineKeyboardButton("💰 تلخيص PDF", callback_data="change_price_summarize")],
        [InlineKeyboardButton("💰 سؤال وجواب", callback_data="change_price_qa")],
        [InlineKeyboardButton("💰 الملازم", callback_data="change_price_materials")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
    ]
    
    prices_text = f"""
⚙️ <b>الأسعار الحالية</b>

• حساب الإعفاء: {format_money(int(get_bot_setting('price_exemption', 1000)))}
• تلخيص PDF: {format_money(int(get_bot_setting('price_summarize', 1000)))}
• سؤال وجواب: {format_money(int(get_bot_setting('price_qa', 1000)))}
• الملازم: {format_money(int(get_bot_setting('price_materials', 1000)))}
    """
    
    await query.edit_message_text(
        prices_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_admin_settings_menu(query):
    maintenance = "✅ مفعل" if get_bot_setting('maintenance_mode') == '1' else "❌ معطل"
    
    keyboard = [
        [InlineKeyboardButton(f"🔄 وضع الصيانة: {maintenance}", callback_data="admin_toggle_maintenance")],
        [InlineKeyboardButton("📢 تغيير رابط القناة", callback_data="admin_set_channel")],
        [InlineKeyboardButton("👤 تغيير يوزر الدعم", callback_data="admin_set_support")],
        [InlineKeyboardButton("🎁 تغيير الهدية الترحيبية", callback_data="admin_set_welcome")],
        [InlineKeyboardButton("💰 تغيير مكافأة الدعوة", callback_data="admin_set_referral")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
    ]
    
    settings_text = f"""
🔧 <b>الإعدادات العامة</b>

• وضع الصيانة: {maintenance}
• رابط القناة: {get_bot_setting('channel_url', 'غير محدد')}
• يوزر الدعم: {get_bot_setting('support_username', ADMIN_USERNAME)}
• الهدية الترحيبية: {format_money(int(get_bot_setting('welcome_bonus', WELCOME_BONUS)))}
• مكافأة الدعوة: {format_money(int(get_bot_setting('referral_bonus', REFERRAL_BONUS)))}
    """
    
    await query.edit_message_text(
        settings_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ========== معالجة أوامر الإدارة ==========
async def process_admin_charge_user(update: Update, context: CallbackContext):
    try:
        user_id = int(update.message.text)
        user = get_user(user_id)
        
        if user:
            context.user_data['charge_user_id'] = user_id
            await update.message.reply_text(
                f"✅ تم تحديد المستخدم: {user_id}\n\n"
                f"أرسل <b>المبلغ</b> الذي تريد شحنه (بالدينار العراقي):",
                parse_mode=ParseMode.HTML
            )
            return ADMIN_CHARGE_AMOUNT
        else:
            await update.message.reply_text("❌ المستخدم غير موجود")
            return ADMIN_CHARGE_USER
    except:
        await update.message.reply_text("❌ آيدي غير صالح")
        return ADMIN_CHARGE_USER

async def process_admin_charge_amount(update: Update, context: CallbackContext):
    try:
        amount = int(update.message.text)
        user_id = context.user_data.get('charge_user_id')
        
        if user_id:
            update_balance(user_id, amount, 'deposit')
            
            # إرسال إشعار للمستخدم
            try:
                await context.bot.send_message(
                    user_id,
                    f"🎉 <b>تم شحن رصيدك!</b>\n\n"
                    f"💰 المبلغ: {format_money(amount)}\n"
                    f"⚖️ تمت العملية من قبل الإدارة",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
            
            await update.message.reply_text(
                f"✅ <b>تم شحن الرصيد بنجاح</b>\n\n"
                f"👤 آيدي المستخدم: {user_id}\n"
                f"💰 المبلغ: {format_money(amount)}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_keyboard(update.effective_user.id)
            )
            
            context.user_data.clear()
            return ConversationHandler.END
    except:
        await update.message.reply_text("❌ مبلغ غير صالح")
        return ADMIN_CHARGE_AMOUNT

async def process_admin_ban_user(update: Update, context: CallbackContext):
    try:
        user_id = int(update.message.text)
        
        c = db_conn.cursor()
        c.execute('''UPDATE users SET is_banned = 1 WHERE user_id = ?''', (user_id,))
        db_conn.commit()
        
        await update.message.reply_text(
            f"✅ <b>تم حظر المستخدم</b>\n\n"
            f"👤 الآيدي: {user_id}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard(update.effective_user.id)
        )
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ آيدي غير صالح")
        return ADMIN_BAN_USER

async def process_admin_unban_user(update: Update, context: CallbackContext):
    try:
        user_id = int(update.message.text)
        
        c = db_conn.cursor()
        c.execute('''UPDATE users SET is_banned = 0 WHERE user_id = ?''', (user_id,))
        db_conn.commit()
        
        await update.message.reply_text(
            f"✅ <b>تم فك حظر المستخدم</b>\n\n"
            f"👤 الآيدي: {user_id}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard(update.effective_user.id)
        )
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ آيدي غير صالح")
        return ADMIN_UNBAN_USER

async def process_admin_add_material_name(update: Update, context: CallbackContext):
    context.user_data['material_name'] = update.message.text
    await update.message.reply_text(
        "📝 أرسل <b>وصف المادة</b>:",
        parse_mode=ParseMode.HTML
    )
    return ADMIN_ADD_DESC

async def process_admin_add_material_desc(update: Update, context: CallbackContext):
    context.user_data['material_desc'] = update.message.text
    await update.message.reply_text(
        "📎 أرسل <b>ملف PDF</b> للمادة:",
        parse_mode=ParseMode.HTML
    )
    return ADMIN_ADD_FILE

async def process_admin_add_material_file(update: Update, context: CallbackContext):
    if update.message.document and update.message.document.mime_type == 'application/pdf':
        context.user_data['material_file'] = update.message.document.file_id
        await update.message.reply_text(
            "📁 أرسل <b>تصنيف المادة</b> (مثل: رياضيات, فيزياء, كيمياء):",
            parse_mode=ParseMode.HTML
        )
        return ADMIN_ADD_CATEGORY
    else:
        await update.message.reply_text("❌ الرجاء إرسال ملف PDF فقط")
        return ADMIN_ADD_FILE

async def process_admin_add_material_category(update: Update, context: CallbackContext):
    name = context.user_data.get('material_name')
    desc = context.user_data.get('material_desc')
    file_id = context.user_data.get('material_file')
    category = update.message.text
    
    add_material(name, desc, file_id, category, update.effective_user.id)
    
    await update.message.reply_text(
        f"✅ <b>تم إضافة المادة بنجاح</b>\n\n"
        f"📚 الاسم: {name}\n"
        f"📝 الوصف: {desc}\n"
        f"📁 التصنيف: {category}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(update.effective_user.id)
    )
    
    context.user_data.clear()
    return ConversationHandler.END

async def process_admin_broadcast(update: Update, context: CallbackContext):
    text = update.message.text
    
    all_users = get_all_users()
    total = len(all_users)
    
    progress_msg = await update.message.reply_text(f"📤 جاري الإرسال لـ {total} مستخدم...")
    
    success = 0
    failed = 0
    
    for user in all_users:
        try:
            await context.bot.send_message(
                user['user_id'],
                text,
                parse_mode=ParseMode.HTML
            )
            success += 1
            await asyncio.sleep(0.1)
        except:
            failed += 1
    
    await progress_msg.delete()
    
    await update.message.reply_text(
        f"✅ <b>تم إرسال الإشعارات</b>\n\n"
        f"📊 <b>الإحصائيات:</b>\n"
        f"• الإجمالي: {total}\n"
        f"• الناجحة: {success}\n"
        f"• الفاشلة: {failed}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(update.effective_user.id)
    )
    return ConversationHandler.END

async def process_admin_change_price(update: Update, context: CallbackContext):
    try:
        price = int(update.message.text)
        service = context.user_data.get('change_price_service')
        
        if service and price > 0:
            set_bot_setting(f'price_{service}', str(price))
            
            service_name = {
                "exemption": "حساب الإعفاء",
                "summarize": "تلخيص PDF",
                "qa": "سؤال وجواب",
                "materials": "الملازم"
            }.get(service, service)
            
            await update.message.reply_text(
                f"✅ <b>تم تغيير السعر بنجاح</b>\n\n"
                f"🛠 الخدمة: {service_name}\n"
                f"💰 السعر الجديد: {format_money(price)}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_keyboard(update.effective_user.id)
            )
            
            context.user_data.clear()
            return ConversationHandler.END
    except:
        pass
    
    await update.message.reply_text("❌ سعر غير صالح")
    return ADMIN_CHANGE_PRICE

# ========== معالجة إعدادات الإدارة ==========
async def handle_admin_settings_buttons(query, context):
    data = query.data
    
    if data == "admin_toggle_maintenance":
        current = get_bot_setting('maintenance_mode', '0')
        new_value = '1' if current == '0' else '0'
        set_bot_setting('maintenance_mode', new_value)
        
        status = "✅ مفعل" if new_value == '1' else "❌ معطل"
        await query.edit_message_text(
            f"🔄 <b>وضع الصيانة</b>\n\n"
            f"الحالة الجديدة: {status}",
            parse_mode=ParseMode.HTML
        )
        await asyncio.sleep(2)
        await show_admin_settings_menu(query)
        
    elif data == "admin_set_channel":
        await query.edit_message_text(
            "📢 <b>تغيير رابط القناة</b>\n\n"
            "أرسل <b>رابط القناة</b> الجديد:",
            parse_mode=ParseMode.HTML
        )
        return ADMIN_SET_CHANNEL
    
    elif data == "admin_set_support":
        await query.edit_message_text(
            "👤 <b>تغيير يوزر الدعم</b>\n\n"
            "أرسل <b>يوزر الدعم</b> الجديد (مع @):",
            parse_mode=ParseMode.HTML
        )
        return ADMIN_SET_SUPPORT
    
    elif data == "admin_set_welcome":
        await query.edit_message_text(
            "🎁 <b>تغيير الهدية الترحيبية</b>\n\n"
            "أرسل <b>مبلغ الهدية</b> الجديد (بالدينار العراقي):",
            parse_mode=ParseMode.HTML
        )
        return ADMIN_SET_WELCOME
    
    elif data == "admin_set_referral":
        await query.edit_message_text(
            "💰 <b>تغيير مكافأة الدعوة</b>\n\n"
            "أرسل <b>مبلغ المكافأة</b> الجديد (بالدينار العراقي):",
            parse_mode=ParseMode.HTML
        )
        return ADMIN_SET_REFERRAL
    
    return ConversationHandler.END

async def process_admin_set_channel(update: Update, context: CallbackContext):
    channel_url = update.message.text
    set_bot_setting('channel_url', channel_url)
    
    await update.message.reply_text(
        f"✅ <b>تم تغيير رابط القناة</b>\n\n"
        f"الرابط الجديد: {channel_url}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(update.effective_user.id)
    )
    return ConversationHandler.END

async def process_admin_set_support(update: Update, context: CallbackContext):
    support_username = update.message.text
    if support_username.startswith('@'):
        set_bot_setting('support_username', support_username)
        
        await update.message.reply_text(
            f"✅ <b>تم تغيير يوزر الدعم</b>\n\n"
            f"اليوزر الجديد: {support_username}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard(update.effective_user.id)
        )
    else:
        await update.message.reply_text("❌ اليوزر يجب أن يبدأ ب @")
        return ADMIN_SET_SUPPORT
    
    return ConversationHandler.END

async def process_admin_set_welcome(update: Update, context: CallbackContext):
    try:
        amount = int(update.message.text)
        if amount >= 0:
            set_bot_setting('welcome_bonus', str(amount))
            
            await update.message.reply_text(
                f"✅ <b>تم تغيير الهدية الترحيبية</b>\n\n"
                f"المبلغ الجديد: {format_money(amount)}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_keyboard(update.effective_user.id)
            )
        else:
            await update.message.reply_text("❌ المبلغ يجب أن يكون موجباً")
            return ADMIN_SET_WELCOME
    except:
        await update.message.reply_text("❌ مبلغ غير صالح")
        return ADMIN_SET_WELCOME
    
    return ConversationHandler.END

async def process_admin_set_referral(update: Update, context: CallbackContext):
    try:
        amount = int(update.message.text)
        if amount >= 0:
            set_bot_setting('referral_bonus', str(amount))
            
            await update.message.reply_text(
                f"✅ <b>تم تغيير مكافأة الدعوة</b>\n\n"
                f"المبلغ الجديد: {format_money(amount)}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_keyboard(update.effective_user.id)
            )
        else:
            await update.message.reply_text("❌ المبلغ يجب أن يكون موجباً")
            return ADMIN_SET_REFERRAL
    except:
        await update.message.reply_text("❌ مبلغ غير صالح")
        return ADMIN_SET_REFERRAL
    
    return ConversationHandler.END

# ========== الدالة الرئيسية ==========
def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    # معالج الخدمات التعليمية
    service_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_exemption_service, pattern="^service_exemption$"),
            CallbackQueryHandler(start_summarize_service, pattern="^service_summarize$"),
            CallbackQueryHandler(start_qa_service, pattern="^service_qa$")
        ],
        states={
            EXEMPTION_COURSE1: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_exemption_course1)],
            EXEMPTION_COURSE2: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_exemption_course2)],
            EXEMPTION_COURSE3: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_exemption_course3)],
            SUMMARIZE_PDF: [MessageHandler(filters.Document.PDF, process_pdf_summarize)],
            QA_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_qa_question)]
        },
        fallbacks=[]
    )
    
    # معالج الإدارة
    admin_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(lambda q, c: ADMIN_CHARGE_USER, pattern="^admin_charge$"),
            CallbackQueryHandler(lambda q, c: ADMIN_BAN_USER, pattern="^admin_ban$"),
            CallbackQueryHandler(lambda q, c: ADMIN_UNBAN_USER, pattern="^admin_unban$"),
            CallbackQueryHandler(lambda q, c: ADMIN_ADD_NAME, pattern="^admin_add_material$"),
            CallbackQueryHandler(lambda q, c: ADMIN_BROADCAST, pattern="^admin_broadcast$"),
            CallbackQueryHandler(lambda q, c: ADMIN_CHANGE_PRICE, pattern="^change_price_"),
            CallbackQueryHandler(lambda q, c: ADMIN_SET_CHANNEL, pattern="^admin_set_channel$"),
            CallbackQueryHandler(lambda q, c: ADMIN_SET_SUPPORT, pattern="^admin_set_support$"),
            CallbackQueryHandler(lambda q, c: ADMIN_SET_WELCOME, pattern="^admin_set_welcome$"),
            CallbackQueryHandler(lambda q, c: ADMIN_SET_REFERRAL, pattern="^admin_set_referral$")
        ],
        states={
            ADMIN_CHARGE_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_charge_user)],
            ADMIN_CHARGE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_charge_amount)],
            ADMIN_BAN_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_ban_user)],
            ADMIN_UNBAN_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_unban_user)],
            ADMIN_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_add_material_name)],
            ADMIN_ADD_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_add_material_desc)],
            ADMIN_ADD_FILE: [MessageHandler(filters.Document.PDF, process_admin_add_material_file)],
            ADMIN_ADD_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_add_material_category)],
            ADMIN_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_broadcast)],
            ADMIN_CHANGE_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_change_price)],
            ADMIN_SET_CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_set_channel)],
            ADMIN_SET_SUPPORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_set_support)],
            ADMIN_SET_WELCOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_set_welcome)],
            ADMIN_SET_REFERRAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_set_referral)]
        },
        fallbacks=[]
    )
    
    # Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(service_conv)
    application.add_handler(admin_conv)
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(CallbackQueryHandler(handle_admin_settings_buttons, 
                                                pattern="^admin_toggle_maintenance$|^admin_set_"))
    application.add_handler(CallbackQueryHandler(handle_admin_buttons, 
                                                pattern="^admin_"))
    
    # تشغيل البوت
    logger.info("=" * 50)
    logger.info("🤖 بوت 'يلا نتعلم' يعمل الآن...")
    logger.info(f"👑 المدير: {MY_USER_ID}")
    logger.info(f"🤖 البوت: {BOT_USERNAME}")
    logger.info(f"👨‍💻 الدعم: {ADMIN_USERNAME}")
    logger.info("=" * 50)
    
    print("\n" + "=" * 50)
    print("🎓 بوت 'يلا نتعلم' يعمل بنجاح!")
    print(f"🤖 اليوزر: {BOT_USERNAME}")
    print(f"👑 المدير: {MY_USER_ID}")
    print(f"👨‍💻 المطور: {ADMIN_USERNAME}")
    print(f"💎 الذكاء الاصطناعي: Gemini API متصل ✅")
    print("=" * 50)
    print("📁 قاعدة البيانات: bot_database.db")
    print("📝 سجلات البوت: bot.log")
    print("=" * 50 + "\n")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
