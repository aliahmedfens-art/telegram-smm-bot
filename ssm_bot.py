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
from typing import Dict, List, Optional
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
    ReplyKeyboardRemove, InputFile
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
    "exemption": 1000,    # حساب درجة الإعفاء
    "summarize": 1000,    # تلخيص PDF
    "qa": 1000,           # سؤال وجواب
    "materials": 1000     # قسم الملازم
}

WELCOME_BONUS = 1000
REFERRAL_BONUS = 500

# حالات المحادثة
(
    WAITING_FOR_COURSE1, 
    WAITING_FOR_COURSE2, 
    WAITING_FOR_COURSE3,
    WAITING_FOR_PDF,
    WAITING_FOR_QUESTION,
    ADMIN_CHARGE_USER,
    ADMIN_CHARGE_AMOUNT,
    ADMIN_BAN_USER,
    ADMIN_UNBAN_USER,
    ADMIN_ADD_MATERIAL_NAME,
    ADMIN_ADD_MATERIAL_DESC,
    ADMIN_ADD_MATERIAL_FILE,
    ADMIN_ADD_MATERIAL_CATEGORY,
    ADMIN_CHANGE_PRICE,
    ADMIN_BROADCAST
) = range(15)

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== قاعدة البيانات ==========
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
        type TEXT,
        amount INTEGER,
        service TEXT,
        details TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    
    # جعل حسابك مدير
    c.execute('''UPDATE users SET is_admin = 1 WHERE user_id = ?''', (MY_USER_ID,))
    
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
    stats['total_users'] = c.fetchone()[0]
    c.execute('''SELECT COUNT(*) FROM users WHERE date(join_date) = date('now')''')
    stats['new_today'] = c.fetchone()[0]
    c.execute('''SELECT COUNT(*) FROM users WHERE is_banned = 1''')
    stats['banned'] = c.fetchone()[0]
    c.execute('''SELECT SUM(balance) FROM users''')
    stats['total_balance'] = c.fetchone()[0] or 0
    c.execute('''SELECT SUM(total_spent) FROM users''')
    stats['total_spent'] = c.fetchone()[0] or 0
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

# ========== الذكاء الاصطناعي ==========
def init_gemini():
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel('gemini-pro')

gemini_model = init_gemini()

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
    try:
        prompt = f"قم بتلخيص النص الدراسي التالي للطلاب العراقيين:\n\n{pdf_text[:4000]}"
        response = await asyncio.to_thread(gemini_model.generate_content, prompt)
        return response.text if response.text else "لم أتمكن من التلخيص"
    except Exception as e:
        logger.error(f"خطأ في التلخيص: {e}")
        return "حدث خطأ في التلخيص"

async def answer_question_with_ai(question: str) -> str:
    try:
        prompt = f"أجب على السؤال التالي كمعلم عراقي متخصص:\n\n{question}"
        response = await asyncio.to_thread(gemini_model.generate_content, prompt)
        return response.text if response.text else "لم أتمكن من الإجابة"
    except Exception as e:
        logger.error(f"خطأ في الإجابة: {e}")
        return "حدث خطأ في الإجابة"

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
            c.drawString(50, y, line[:100])
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
    
    if user_id == MY_USER_ID:
        keyboard.append([InlineKeyboardButton("👑 لوحة التحكم", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(keyboard)

async def check_balance_for_service(update: Update, service: str) -> bool:
    if isinstance(update, Update):
        user_id = update.effective_user.id
    else:
        user_id = update.from_user.id
    
    user = get_user(user_id)
    if not user:
        return False
    
    if get_bot_setting('maintenance_mode') == '1':
        if isinstance(update, Update):
            await update.message.reply_text("⚙️ البوت في وضع الصيانة")
        else:
            await update.edit_message_text("⚙️ البوت في وضع الصيانة")
        return False
    
    price = int(get_bot_setting(f'price_{service}', DEFAULT_PRICES.get(service, 1000)))
    
    if user['balance'] >= price:
        update_balance(user_id, -price, 'purchase', service)
        return True
    else:
        if isinstance(update, Update):
            await update.message.reply_text(
                f"⚠️ رصيدك غير كافي\nالسعر: {format_money(price)}\nرصيدك: {format_money(user['balance'])}"
            )
        else:
            await update.edit_message_text(
                f"⚠️ رصيدك غير كافي\nالسعر: {format_money(price)}\nرصيدك: {format_money(user['balance'])}"
            )
        return False

# ========== الأمر /start ==========
async def start_command(update: Update, context: CallbackContext):
    user = update.effective_user
    user_id = user.id
    
    # تسجيل المستخدم الجديد
    c = db_conn.cursor()
    c.execute('''INSERT OR IGNORE INTO users 
                 (user_id, username, first_name, last_name, referral_code) 
                 VALUES (?, ?, ?, ?, ?)''',
              (user_id, user.username, user.first_name, user.last_name, str(uuid4())[:8]))
    
    # نظام الدعوة
    referral_code = None
    if context.args and context.args[0].startswith('ref_'):
        referral_code = context.args[0][4:]
    
    is_new_user = c.rowcount > 0
    if is_new_user:
        welcome_bonus = int(get_bot_setting('welcome_bonus', WELCOME_BONUS))
        update_balance(user_id, welcome_bonus, 'bonus', 'welcome')
        
        if referral_code:
            c.execute('''SELECT user_id FROM users WHERE referral_code = ?''', (referral_code,))
            referrer = c.fetchone()
            if referrer:
                referral_bonus = int(get_bot_setting('referral_bonus', REFERRAL_BONUS))
                update_balance(referrer[0], referral_bonus, 'referral')
    
    db_conn.commit()
    user_data = get_user(user_id)
    
    welcome_text = f"""
🎓 <b>مرحباً بك في بوت 'يلا نتعلم'!</b>

💰 <b>رصيدك الحالي:</b> {format_money(user_data.get('balance', 0) if user_data else 0)}
🆔 <b>الأيدي الخاص بك:</b> {user_id}

🔗 <b>رابط الدعوة:</b>
https://t.me/{BOT_USERNAME.replace('@', '')}?start=ref_{user_data.get('referral_code', '')}

💸 <b>مكافأة الدعوة:</b> {format_money(int(get_bot_setting('referral_bonus', REFERRAL_BONUS)))}
🎁 <b>الهدية الترحيبية:</b> {format_money(int(get_bot_setting('welcome_bonus', WELCOME_BONUS)))}
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
        await start_exemption(query)
    elif data == "service_summarize":
        await start_summarize(query)
    elif data == "service_qa":
        await start_qa(query)
    elif data == "service_materials":
        await show_materials(query)
    elif data == "balance":
        await show_balance(query)
    elif data == "referral":
        await show_referral(query)
    elif data == "info":
        await show_info(query)
    elif data == "admin_panel":
        if user_id == MY_USER_ID:
            await show_admin_panel(query)
        else:
            await query.edit_message_text("⛔ غير مصرح لك!")
    elif data.startswith("admin_"):
        await handle_admin_button(query, context)
    elif data == "back_to_main":
        await back_to_main(query)
    elif data.startswith("mat_"):
        await send_material(query, context)

# ========== الخدمات التعليمية ==========
async def start_exemption(query):
    if await check_balance_for_service(query, 'exemption'):
        await query.edit_message_text(
            "📊 <b>حساب درجة الإعفاء</b>\n\nأدخل درجة الكورس الأول (0-100):",
            parse_mode=ParseMode.HTML
        )
        return WAITING_FOR_COURSE1
    return ConversationHandler.END

async def start_summarize(query):
    if await check_balance_for_service(query, 'summarize'):
        await query.edit_message_text(
            "📝 <b>تلخيص الملازم</b>\n\nأرسل ملف PDF الآن:",
            parse_mode=ParseMode.HTML
        )
        return WAITING_FOR_PDF
    return ConversationHandler.END

async def start_qa(query):
    if await check_balance_for_service(query, 'qa'):
        await query.edit_message_text(
            "❓ <b>سؤال وجواب</b>\n\nأرسل سؤالك الآن:",
            parse_mode=ParseMode.HTML
        )
        return WAITING_FOR_QUESTION
    return ConversationHandler.END

# ========== معالجة الخدمات ==========
async def process_exemption(update: Update, context: CallbackContext):
    try:
        score = float(update.message.text)
        if 0 <= score <= 100:
            if 'course1' not in context.user_data:
                context.user_data['course1'] = score
                await update.message.reply_text(f"✅ الكورس الأول: {score}\nأدخل درجة الكورس الثاني:")
                return WAITING_FOR_COURSE2
            elif 'course2' not in context.user_data:
                context.user_data['course2'] = score
                await update.message.reply_text(f"✅ الكورس الثاني: {score}\nأدخل درجة الكورس الثالث:")
                return WAITING_FOR_COURSE3
            else:
                c1 = context.user_data['course1']
                c2 = context.user_data['course2']
                c3 = score
                
                average = (c1 + c2 + c3) / 3
                
                if average >= 90:
                    result = "🎉 <b>مبروك! أنت معفي من المادة</b>"
                else:
                    result = "📝 <b>أنت غير معفي من المادة</b>"
                
                msg = f"""
{result}

📊 <b>الدرجات:</b>
• الكورس الأول: {c1}
• الكورس الثاني: {c2}
• الكورس الثالث: {c3}

⚖️ <b>المعدل:</b> {average:.2f}
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
    return ConversationHandler.END

async def process_pdf(update: Update, context: CallbackContext):
    if update.message.document and update.message.document.mime_type == 'application/pdf':
        msg = await update.message.reply_text("⏳ جاري معالجة الملف...")
        
        try:
            file = await context.bot.get_file(update.message.document.file_id)
            file_path = f"temp_{update.message.document.file_id}.pdf"
            await file.download_to_drive(file_path)
            
            text = extract_text_from_pdf(file_path)
            if len(text) < 50:
                await msg.edit_text("❌ الملف فارغ")
                return WAITING_FOR_PDF
            
            await msg.edit_text("🤖 جاري التلخيص...")
            summary = await summarize_pdf_with_ai(text)
            
            await msg.edit_text("📄 جاري إنشاء PDF...")
            pdf_buffer = create_pdf(summary, "ملخص دراسي")
            
            if pdf_buffer:
                await update.message.reply_document(
                    document=InputFile(pdf_buffer, filename="ملخص.pdf"),
                    caption="✅ تم تلخيص الملف بنجاح"
                )
                pdf_buffer.close()
            else:
                await update.message.reply_text(f"📝 الملخص:\n\n{summary[:2000]}")
            
            os.remove(file_path)
            await msg.delete()
            
            await update.message.reply_text(
                "✅ تم الانتهاء",
                reply_markup=get_main_keyboard(update.effective_user.id)
            )
            return ConversationHandler.END
            
        except Exception as e:
            await msg.edit_text(f"❌ حدث خطأ: {str(e)}")
            return WAITING_FOR_PDF
    
    await update.message.reply_text("❌ الرجاء إرسال ملف PDF فقط")
    return WAITING_FOR_PDF

async def process_question(update: Update, context: CallbackContext):
    question = update.message.text
    if len(question) < 5:
        await update.message.reply_text("❌ الرجاء كتابة سؤال واضح")
        return WAITING_FOR_QUESTION
    
    msg = await update.message.reply_text("🤖 جاري البحث عن الإجابة...")
    
    try:
        answer = await answer_question_with_ai(question)
        await msg.edit_text(f"💡 <b>الإجابة:</b>\n\n{answer}", parse_mode=ParseMode.HTML)
        
        await update.message.reply_text(
            "✅ تم الانتهاء",
            reply_markup=get_main_keyboard(update.effective_user.id)
        )
        return ConversationHandler.END
    except Exception as e:
        await msg.edit_text(f"❌ حدث خطأ: {str(e)}")
        return WAITING_FOR_QUESTION

# ========== عرض المواد ==========
async def show_materials(query):
    if not await check_balance_for_service(query, 'materials'):
        return
    
    materials = get_materials()
    
    if not materials:
        await query.edit_message_text(
            "📚 <b>ملازمي ومرشحاتي</b>\n\nلا توجد مواد متاحة حالياً.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard(query.from_user.id)
        )
        return
    
    keyboard = []
    for mat in materials[:10]:
        keyboard.append([InlineKeyboardButton(f"📄 {mat['name'][:30]}", callback_data=f"mat_{mat['id']}")])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")])
    
    await query.edit_message_text(
        "📚 <b>ملازمي ومرشحاتي</b>\n\nاختر المادة:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def send_material(query, context):
    material_id = int(query.data.replace("mat_", ""))
    
    c = db_conn.cursor()
    c.execute('''SELECT * FROM materials WHERE id = ?''', (material_id,))
    material = c.fetchone()
    
    if material:
        try:
            await context.bot.send_document(
                chat_id=query.from_user.id,
                document=material[3],
                caption=f"📚 {material[1]}\n\n{material[2]}"
            )
            await query.answer("✅ تم إرسال الملف")
        except:
            await query.edit_message_text("❌ حدث خطأ في إرسال الملف")
    else:
        await query.edit_message_text("❌ المادة غير موجودة")
    
    await show_materials(query)

# ========== الأوامر الأخرى ==========
async def show_balance(query):
    user = get_user(query.from_user.id)
    if user:
        await query.edit_message_text(
            f"💰 <b>رصيدك:</b> {format_money(user.get('balance', 0))}\n\n"
            f"💳 للتعبئة: {get_bot_setting('support_username', ADMIN_USERNAME)}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard(query.from_user.id)
        )

async def show_referral(query):
    user = get_user(query.from_user.id)
    if user:
        link = f"https://t.me/{BOT_USERNAME.replace('@', '')}?start=ref_{user.get('referral_code', '')}"
        await query.edit_message_text(
            f"👥 <b>رابط الدعوة:</b>\n{link}\n\n"
            f"🎁 مكافأة كل دعوة: {format_money(int(get_bot_setting('referral_bonus', REFERRAL_BONUS)))}",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=get_main_keyboard(query.from_user.id)
        )

async def show_info(query):
    await query.edit_message_text(
        f"🤖 <b>بوت يلا نتعلم</b>\n\n"
        f"👨‍💻 المطور: {ADMIN_USERNAME}\n"
        f"💰 نظام الدفع: الدينار العراقي\n"
        f"🎯 الخدمات: 4 خدمات تعليمية\n"
        f"📞 الدعم: {get_bot_setting('support_username', ADMIN_USERNAME)}\n"
        f"📢 القناة: {get_bot_setting('channel_url', 'غير محدد')}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(query.from_user.id)
    )

async def back_to_main(query):
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
async def show_admin_panel(query):
    keyboard = [
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
        [InlineKeyboardButton("💰 شحن رصيد", callback_data="admin_charge")],
        [InlineKeyboardButton("🚫 حظر مستخدم", callback_data="admin_ban")],
        [InlineKeyboardButton("✅ فك حظر", callback_data="admin_unban")],
        [InlineKeyboardButton("📤 إضافة مادة", callback_data="admin_add_material")],
        [InlineKeyboardButton("⚙️ تغيير الأسعار", callback_data="admin_change_prices")],
        [InlineKeyboardButton("📢 إرسال إشعار", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🔄 وضع الصيانة", callback_data="admin_toggle_maintenance")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        "👑 <b>لوحة التحكم</b>\n\nاختر القسم:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_admin_button(query, context):
    data = query.data
    
    if data == "admin_stats":
        await admin_stats(query)
    elif data == "admin_charge":
        await query.edit_message_text("💰 <b>شحن رصيد</b>\n\nأرسل أيدي المستخدم:", parse_mode=ParseMode.HTML)
        return ADMIN_CHARGE_USER
    elif data == "admin_ban":
        await query.edit_message_text("🚫 <b>حظر مستخدم</b>\n\nأرسل أيدي المستخدم:", parse_mode=ParseMode.HTML)
        return ADMIN_BAN_USER
    elif data == "admin_unban":
        await query.edit_message_text("✅ <b>فك حظر مستخدم</b>\n\nأرسل أيدي المستخدم:", parse_mode=ParseMode.HTML)
        return ADMIN_UNBAN_USER
    elif data == "admin_add_material":
        await query.edit_message_text("📤 <b>إضافة مادة</b>\n\nأرسل اسم المادة:", parse_mode=ParseMode.HTML)
        return ADMIN_ADD_MATERIAL_NAME
    elif data == "admin_change_prices":
        await admin_change_prices(query)
    elif data == "admin_broadcast":
        await query.edit_message_text("📢 <b>إرسال إشعار</b>\n\nأرسل نص الإشعار:", parse_mode=ParseMode.HTML)
        return ADMIN_BROADCAST
    elif data == "admin_toggle_maintenance":
        await admin_toggle_maintenance(query)
    
    return ConversationHandler.END

async def admin_stats(query):
    stats = get_user_stats()
    service_stats = []
    c = db_conn.cursor()
    c.execute('''SELECT * FROM service_stats''')
    for row in c.fetchall():
        service_stats.append(f"{row[0]}: {row[1]} استخدام - {format_money(row[2])}")
    
    stats_text = f"""
📊 <b>إحصائيات البوت</b>

👤 <b>المستخدمين:</b>
• الإجمالي: {stats['total_users']}
• الجدد اليوم: {stats['new_today']}
• المحظورين: {stats['banned']}

💰 <b>المالية:</b>
• إجمالي الأرصدة: {format_money(stats['total_balance'])}
• إجمالي المشتريات: {format_money(stats['total_spent'])}

🛠 <b>إحصائيات الخدمات:</b>
{chr(10).join(service_stats) if service_stats else 'لا توجد إحصائيات'}
    """
    
    await query.edit_message_text(
        stats_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
        ])
    )

async def admin_toggle_maintenance(query):
    current = get_bot_setting('maintenance_mode', '0')
    new_value = '1' if current == '0' else '0'
    set_bot_setting('maintenance_mode', new_value)
    
    status = "✅ مفعل" if new_value == '1' else "❌ معطل"
    await query.edit_message_text(
        f"🔄 <b>وضع الصيانة</b>\n\nالحالة: {status}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
        ])
    )

async def admin_change_prices(query):
    keyboard = [
        [InlineKeyboardButton("💰 حساب الإعفاء", callback_data="change_price_exemption")],
        [InlineKeyboardButton("💰 تلخيص PDF", callback_data="change_price_summarize")],
        [InlineKeyboardButton("💰 سؤال وجواب", callback_data="change_price_qa")],
        [InlineKeyboardButton("💰 الملازم", callback_data="change_price_materials")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
    ]
    
    prices_text = f"""
⚙️ <b>الأسعار الحالية:</b>

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

async def process_admin_charge_user(update: Update, context: CallbackContext):
    try:
        user_id = int(update.message.text)
        context.user_data['charge_user'] = user_id
        await update.message.reply_text(f"👤 المستخدم: {user_id}\n\nأرسل المبلغ:")
        return ADMIN_CHARGE_AMOUNT
    except:
        await update.message.reply_text("❌ أيدي غير صالح")
        return ADMIN_CHARGE_USER

async def process_admin_charge_amount(update: Update, context: CallbackContext):
    try:
        amount = int(update.message.text)
        user_id = context.user_data.get('charge_user')
        
        if user_id:
            update_balance(user_id, amount, 'deposit')
            
            try:
                await update._bot.send_message(
                    user_id,
                    f"🎉 <b>تم شحن رصيدك!</b>\n\nالمبلغ: {format_money(amount)}\nمن: الإدارة",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
            
            await update.message.reply_text(
                f"✅ <b>تم الشحن</b>\n\nالمستخدم: {user_id}\nالمبلغ: {format_money(amount)}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_keyboard(update.effective_user.id)
            )
            
            context.user_data.clear()
            return ConversationHandler.END
    except:
        pass
    
    await update.message.reply_text("❌ مبلغ غير صالح")
    return ADMIN_CHARGE_AMOUNT

async def process_admin_ban(update: Update, context: CallbackContext):
    try:
        user_id = int(update.message.text)
        c = db_conn.cursor()
        c.execute('''UPDATE users SET is_banned = 1 WHERE user_id = ?''', (user_id,))
        db_conn.commit()
        
        await update.message.reply_text(
            f"✅ <b>تم حظر المستخدم</b>\n\nالأيدي: {user_id}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard(update.effective_user.id)
        )
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ أيدي غير صالح")
        return ADMIN_BAN_USER

async def process_admin_unban(update: Update, context: CallbackContext):
    try:
        user_id = int(update.message.text)
        c = db_conn.cursor()
        c.execute('''UPDATE users SET is_banned = 0 WHERE user_id = ?''', (user_id,))
        db_conn.commit()
        
        await update.message.reply_text(
            f"✅ <b>تم فك حظر المستخدم</b>\n\nالأيدي: {user_id}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard(update.effective_user.id)
        )
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ أيدي غير صالح")
        return ADMIN_UNBAN_USER

async def process_admin_add_material_name(update: Update, context: CallbackContext):
    context.user_data['material_name'] = update.message.text
    await update.message.reply_text("📝 أرسل وصف المادة:")
    return ADMIN_ADD_MATERIAL_DESC

async def process_admin_add_material_desc(update: Update, context: CallbackContext):
    context.user_data['material_desc'] = update.message.text
    await update.message.reply_text("📎 أرسل ملف PDF:")
    return ADMIN_ADD_MATERIAL_FILE

async def process_admin_add_material_file(update: Update, context: CallbackContext):
    if update.message.document and update.message.document.mime_type == 'application/pdf':
        context.user_data['material_file'] = update.message.document.file_id
        await update.message.reply_text("📁 أرسل التصنيف (مثل: رياضيات, فيزياء):")
        return ADMIN_ADD_MATERIAL_CATEGORY
    else:
        await update.message.reply_text("❌ الرجاء إرسال ملف PDF فقط")
        return ADMIN_ADD_MATERIAL_FILE

async def process_admin_add_material_category(update: Update, context: CallbackContext):
    name = context.user_data.get('material_name')
    desc = context.user_data.get('material_desc')
    file_id = context.user_data.get('material_file')
    category = update.message.text
    
    add_material(name, desc, file_id, category, update.effective_user.id)
    
    await update.message.reply_text(
        f"✅ <b>تم إضافة المادة</b>\n\nاسم: {name}\nتصنيف: {category}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(update.effective_user.id)
    )
    
    context.user_data.clear()
    return ConversationHandler.END

async def process_admin_broadcast(update: Update, context: CallbackContext):
    text = update.message.text
    users = get_all_users()
    
    msg = await update.message.reply_text(f"📤 جاري الإرسال لـ {len(users)} مستخدم...")
    
    success = 0
    fail = 0
    
    for user in users:
        try:
            await update._bot.send_message(
                user['user_id'],
                text,
                parse_mode=ParseMode.HTML
            )
            success += 1
            await asyncio.sleep(0.1)
        except:
            fail += 1
    
    await msg.edit_text(
        f"✅ <b>تم الإرسال</b>\n\nالناجح: {success}\nالفاشل: {fail}",
        parse_mode=ParseMode.HTML
    )
    
    await update.message.reply_text(
        "✅ تم الانتهاء",
        reply_markup=get_main_keyboard(update.effective_user.id)
    )
    return ConversationHandler.END

async def process_change_price(update: Update, context: CallbackContext):
    try:
        price = int(update.message.text)
        service = context.user_data.get('change_price_service')
        
        if service:
            set_bot_setting(f'price_{service}', str(price))
            
            await update.message.reply_text(
                f"✅ <b>تم تغيير السعر</b>\n\nالخدمة: {service}\nالسعر الجديد: {format_money(price)}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_keyboard(update.effective_user.id)
            )
            
            context.user_data.clear()
            return ConversationHandler.END
    except:
        pass
    
    await update.message.reply_text("❌ سعر غير صالح")
    return ADMIN_CHANGE_PRICE

# ========== الدالة الرئيسية ==========
def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    # معالج المحادثات للخدمات
    service_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_exemption, pattern="^service_exemption$"),
            CallbackQueryHandler(start_summarize, pattern="^service_summarize$"),
            CallbackQueryHandler(start_qa, pattern="^service_qa$")
        ],
        states={
            WAITING_FOR_COURSE1: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_exemption)],
            WAITING_FOR_COURSE2: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_exemption)],
            WAITING_FOR_COURSE3: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_exemption)],
            WAITING_FOR_PDF: [MessageHandler(filters.Document.PDF, process_pdf)],
            WAITING_FOR_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_question)]
        },
        fallbacks=[]
    )
    
    # معالج المحادثات للإدارة
    admin_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(lambda q, c: ADMIN_CHARGE_USER, pattern="^admin_charge$"),
            CallbackQueryHandler(lambda q, c: ADMIN_BAN_USER, pattern="^admin_ban$"),
            CallbackQueryHandler(lambda q, c: ADMIN_UNBAN_USER, pattern="^admin_unban$"),
            CallbackQueryHandler(lambda q, c: ADMIN_ADD_MATERIAL_NAME, pattern="^admin_add_material$"),
            CallbackQueryHandler(lambda q, c: ADMIN_BROADCAST, pattern="^admin_broadcast$"),
            CallbackQueryHandler(lambda q, c: ADMIN_CHANGE_PRICE, pattern="^change_price_")
        ],
        states={
            ADMIN_CHARGE_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_charge_user)],
            ADMIN_CHARGE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_charge_amount)],
            ADMIN_BAN_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_ban)],
            ADMIN_UNBAN_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_unban)],
            ADMIN_ADD_MATERIAL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_add_material_name)],
            ADMIN_ADD_MATERIAL_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_add_material_desc)],
            ADMIN_ADD_MATERIAL_FILE: [MessageHandler(filters.Document.PDF, process_admin_add_material_file)],
            ADMIN_ADD_MATERIAL_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_add_material_category)],
            ADMIN_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_broadcast)],
            ADMIN_CHANGE_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_change_price)]
        },
        fallbacks=[]
    )
    
    # Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(service_conv)
    application.add_handler(admin_conv)
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # تشغيل البوت
    logger.info("🤖 البوت يعمل...")
    print(f"👑 المدير: {MY_USER_ID}")
    print(f"🤖 البوت: {BOT_USERNAME}")
    application.run_polling()

if __name__ == '__main__':
    main()
