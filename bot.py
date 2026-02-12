# bot.py
import asyncio
import logging
import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import random
import string

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

# ==================== التهيئة والإعدادات ====================
TOKEN = "8215031641:AAEDvTzDXroq2wFlqbqIYe58BZ5kF45GKsE"
OWNER_ID = 6130994941
ADMIN_IDS = [OWNER_ID]

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== قاعدة البيانات ====================
class Database:
    def __init__(self):
        self.conn = sqlite3.connect('ssm_bot.db', check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()
    
    def create_tables(self):
        # جدول المستخدمين
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                points INTEGER DEFAULT 0,
                total_points INTEGER DEFAULT 0,
                joined_date TIMESTAMP,
                is_blocked INTEGER DEFAULT 0,
                block_reason TEXT,
                referred_by INTEGER,
                referral_code TEXT UNIQUE,
                daily_reward_date TIMESTAMP,
                total_referrals INTEGER DEFAULT 0
            )
        ''')
        
        # جدول القنوات الإجبارية
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS forced_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT,
                channel_username TEXT,
                channel_title TEXT,
                added_date TIMESTAMP
            )
        ''')
        
        # جدول قنوات التمويل
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS funded_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT,
                channel_username TEXT,
                channel_title TEXT,
                owner_id INTEGER,
                required_members INTEGER,
                current_members INTEGER DEFAULT 0,
                reward_per_member INTEGER,
                total_cost INTEGER,
                status TEXT DEFAULT 'active',
                added_date TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users (user_id)
            )
        ''')
        
        # جدول اشتراكات المستخدمين في القنوات الممولة
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS channel_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                channel_id INTEGER,
                subscribed_date TIMESTAMP,
                rewarded INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                FOREIGN KEY (channel_id) REFERENCES funded_channels (id)
            )
        ''')
        
        # جدول الإعدادات
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        # جدول أقسام خدمات SSM
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS ssm_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                added_date TIMESTAMP
            )
        ''')
        
        # جدول خدمات SSM
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS ssm_services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER,
                name TEXT,
                description TEXT,
                execution_time TEXT,
                price INTEGER,
                added_date TIMESTAMP,
                FOREIGN KEY (category_id) REFERENCES ssm_categories (id)
            )
        ''')
        
        # جدول حركات المستخدمين
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action_type TEXT,
                details TEXT,
                points INTEGER,
                timestamp TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # جدول الهدايا اليومية
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                claimed_date TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        self.conn.commit()
        self.init_settings()
    
    def init_settings(self):
        # إعدادات النقاط والمكافآت الافتراضية
        default_settings = {
            'daily_reward_points': '10',
            'referral_reward_points': '15',
            'channel_join_reward': '10',
            'member_cost': '8',
            'min_members': '100',
            'max_members': '10000',
            'bot_channel': '',
            'support_user': 'Allawi04',
            'maintenance_mode': '0',
            'welcome_message': 'مرحباً بك في بوت خدمات SSM 🚀'
        }
        
        for key, value in default_settings.items():
            self.cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, value))
        
        self.conn.commit()
    
    def get_setting(self, key):
        self.cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        result = self.cursor.fetchone()
        return result[0] if result else None
    
    def set_setting(self, key, value):
        self.cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
        self.conn.commit()
    
    def add_user(self, user_id, username, first_name, referred_by=None):
        referral_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        
        self.cursor.execute('''
            INSERT OR IGNORE INTO users 
            (user_id, username, first_name, joined_date, referral_code, referred_by) 
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, datetime.now(), referral_code, referred_by))
        self.conn.commit()
    
    def get_user(self, user_id):
        self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        return self.cursor.fetchone()
    
    def get_user_by_username(self, username):
        self.cursor.execute('SELECT * FROM users WHERE username = ?', (username.replace('@', ''),))
        return self.cursor.fetchone()
    
    def get_all_users(self):
        self.cursor.execute('SELECT user_id, username, first_name, points, is_blocked FROM users ORDER BY points DESC')
        return self.cursor.fetchall()
    
    def update_user_points(self, user_id, points, action_type, details=""):
        self.cursor.execute('UPDATE users SET points = points + ? WHERE user_id = ?', (points, user_id))
        self.cursor.execute('UPDATE users SET total_points = total_points + ? WHERE user_id = ?', (points, user_id))
        self.cursor.execute('''
            INSERT INTO user_actions (user_id, action_type, details, points, timestamp) 
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, action_type, details, points, datetime.now()))
        self.conn.commit()
    
    def block_user(self, user_id, reason):
        self.cursor.execute('UPDATE users SET is_blocked = 1, block_reason = ? WHERE user_id = ?', (reason, user_id))
        self.conn.commit()
    
    def unblock_user(self, user_id):
        self.cursor.execute('UPDATE users SET is_blocked = 0, block_reason = NULL WHERE user_id = ?', (user_id,))
        self.conn.commit()
    
    def add_forced_channel(self, channel_id, channel_username, channel_title):
        self.cursor.execute('''
            INSERT INTO forced_channels (channel_id, channel_username, channel_title, added_date) 
            VALUES (?, ?, ?, ?)
        ''', (channel_id, channel_username, channel_title, datetime.now()))
        self.conn.commit()
    
    def get_forced_channels(self):
        self.cursor.execute('SELECT * FROM forced_channels')
        return self.cursor.fetchall()
    
    def delete_forced_channel(self, channel_id):
        self.cursor.execute('DELETE FROM forced_channels WHERE id = ?', (channel_id,))
        self.conn.commit()
    
    def add_funded_channel(self, channel_id, channel_username, channel_title, owner_id, required_members, reward_per_member, total_cost):
        self.cursor.execute('''
            INSERT INTO funded_channels 
            (channel_id, channel_username, channel_title, owner_id, required_members, reward_per_member, total_cost, added_date) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (channel_id, channel_username, channel_title, owner_id, required_members, reward_per_member, total_cost, datetime.now()))
        self.conn.commit()
        return self.cursor.lastrowid
    
    def get_active_funded_channels(self):
        self.cursor.execute('SELECT * FROM funded_channels WHERE status = "active"')
        return self.cursor.fetchall()
    
    def check_user_subscribed_to_channel(self, user_id, channel_db_id):
        self.cursor.execute('''
            SELECT * FROM channel_subscriptions 
            WHERE user_id = ? AND channel_id = ?
        ''', (user_id, channel_db_id))
        return self.cursor.fetchone()
    
    def add_channel_subscription(self, user_id, channel_db_id):
        self.cursor.execute('''
            INSERT INTO channel_subscriptions (user_id, channel_id, subscribed_date) 
            VALUES (?, ?, ?)
        ''', (user_id, channel_db_id, datetime.now()))
        self.conn.commit()
    
    def reward_channel_subscription(self, user_id, channel_db_id, reward_points):
        self.cursor.execute('''
            UPDATE channel_subscriptions SET rewarded = 1 
            WHERE user_id = ? AND channel_id = ?
        ''', (user_id, channel_db_id))
        
        funded_channel = self.cursor.execute('SELECT * FROM funded_channels WHERE id = ?', (channel_db_id,)).fetchone()
        if funded_channel:
            current_members = funded_channel[6] + 1
            self.cursor.execute('''
                UPDATE funded_channels SET current_members = ? 
                WHERE id = ?
            ''', (current_members, channel_db_id))
            
            # إذا اكتمل العدد المطلوب
            if current_members >= funded_channel[5]:
                self.cursor.execute('UPDATE funded_channels SET status = "completed" WHERE id = ?', (channel_db_id,))
                return True  # اكتمل العدد
        
        self.conn.commit()
        return False  # لم يكتمل العدد
    
    def add_ssm_category(self, name):
        self.cursor.execute('''
            INSERT INTO ssm_categories (name, added_date) VALUES (?, ?)
        ''', (name, datetime.now()))
        self.conn.commit()
        return self.cursor.lastrowid
    
    def get_ssm_categories(self):
        self.cursor.execute('SELECT * FROM ssm_categories ORDER BY id DESC')
        return self.cursor.fetchall()
    
    def delete_ssm_category(self, category_id):
        self.cursor.execute('DELETE FROM ssm_categories WHERE id = ?', (category_id,))
        self.cursor.execute('DELETE FROM ssm_services WHERE category_id = ?', (category_id,))
        self.conn.commit()
    
    def add_ssm_service(self, category_id, name, description, execution_time, price):
        self.cursor.execute('''
            INSERT INTO ssm_services (category_id, name, description, execution_time, price, added_date) 
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (category_id, name, description, execution_time, price, datetime.now()))
        self.conn.commit()
        return self.cursor.lastrowid
    
    def get_ssm_services(self, category_id):
        self.cursor.execute('SELECT * FROM ssm_services WHERE category_id = ?', (category_id,))
        return self.cursor.fetchall()
    
    def get_all_ssm_services(self):
        self.cursor.execute('''
            SELECT s.*, c.name as category_name 
            FROM ssm_services s 
            JOIN ssm_categories c ON s.category_id = c.id 
            ORDER BY c.id, s.id
        ''')
        return self.cursor.fetchall()
    
    def delete_ssm_service(self, service_id):
        self.cursor.execute('DELETE FROM ssm_services WHERE id = ?', (service_id,))
        self.conn.commit()
    
    def get_user_actions(self, user_id):
        self.cursor.execute('''
            SELECT * FROM user_actions 
            WHERE user_id = ? 
            ORDER BY timestamp DESC LIMIT 50
        ''', (user_id,))
        return self.cursor.fetchall()
    
    def can_claim_daily_reward(self, user_id):
        today = datetime.now().date()
        self.cursor.execute('''
            SELECT * FROM daily_rewards 
            WHERE user_id = ? AND DATE(claimed_date) = ?
        ''', (user_id, today))
        return self.cursor.fetchone() is None
    
    def claim_daily_reward(self, user_id):
        self.cursor.execute('''
            INSERT INTO daily_rewards (user_id, claimed_date) VALUES (?, ?)
        ''', (user_id, datetime.now()))
        self.conn.commit()

db = Database()

# ==================== دوال التحقق من الاشتراك ====================
async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> Tuple[bool, List]:
    """التحقق من اشتراك المستخدم في القنوات الإجبارية"""
    forced_channels = db.get_forced_channels()
    if not forced_channels:
        return True, []
    
    not_subscribed = []
    
    for channel in forced_channels:
        try:
            member = await context.bot.get_chat_member(chat_id=channel[1], user_id=user_id)
            if member.status in ['left', 'kicked']:
                not_subscribed.append(channel)
        except:
            not_subscribed.append(channel)
    
    return len(not_subscribed) == 0, not_subscribed

async def force_subscribe_markup(not_subscribed_channels: List) -> InlineKeyboardMarkup:
    """إنشاء أزرار الاشتراك الإجباري"""
    keyboard = []
    for channel in not_subscribed_channels:
        keyboard.append([InlineKeyboardButton(f"📢 {channel[3]}", url=f"https://t.me/{channel[2]}")])
    
    keyboard.append([InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_subscription")])
    return InlineKeyboardMarkup(keyboard)

# ==================== واجهة المستخدم الرئيسية ====================
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int = None):
    """عرض القائمة الرئيسية"""
    if not user_id:
        user_id = update.effective_user.id
    
    # التحقق من الاشتراك الإجباري
    is_subscribed, not_subscribed = await check_subscription(user_id, context)
    if not is_subscribed:
        markup = await force_subscribe_markup(not_subscribed)
        await update.message.reply_text(
            "⚠️ عذراً، يجب الاشتراك في هذه القنوات أولاً:\n\n"
            "قم بالاشتراك ثم اضغط على زر التحقق",
            reply_markup=markup
        )
        return False
    
    user = db.get_user(user_id)
    if not user:
        db.add_user(user_id, update.effective_user.username, update.effective_user.first_name)
        user = db.get_user(user_id)
    
    if user[5] == 1:  # إذا كان المستخدم محظور
        await update.message.reply_text(f"⚠️ تم حظرك من استخدام البوت\nالسبب: {user[6]}")
        return False
    
    username = user[2] if user[2] else update.effective_user.first_name
    points = user[3]
    
    welcome_text = f"""
🎯 أهلاً بك {username} في بوت خدمات SSM

🆔 معرفك: `{user_id}`
💎 نقاطك: {points} نقطة

اختر من القائمة أدناه:
    """
    
    keyboard = [
        [
            InlineKeyboardButton("🎁 تجميع النقاط", callback_data="collect_points"),
            InlineKeyboardButton("💰 تمويل قناتي", callback_data="fund_channel")
        ],
        [
            InlineKeyboardButton("🛒 خدمات SSM", callback_data="ssm_services"),
            InlineKeyboardButton("🆘 الدعم الفني", url=f"https://t.me/{db.get_setting('support_user')}")
        ],
        [
            InlineKeyboardButton("📢 قناة البوت", url=db.get_setting('bot_channel') if db.get_setting('bot_channel') else "https://t.me/SSM_Services"),
            InlineKeyboardButton("👤 رصيدي", callback_data="my_balance")
        ]
    ]
    
    if user_id == OWNER_ID:
        keyboard.append([InlineKeyboardButton("⚙️ لوحة التحكم", callback_data="admin_panel")])
    
    markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    elif update.callback_query:
        await update.callback_query.edit_message_text(welcome_text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    
    return True

# ==================== قنوات الاشتراك الإجباري ====================
async def handle_check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة التحقق من الاشتراك"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    is_subscribed, not_subscribed = await check_subscription(user_id, context)
    
    if is_subscribed:
        await query.edit_message_text("✅ تم التحقق بنجاح! جاري تحميل القائمة...")
        await main_menu(update, context, user_id)
    else:
        markup = await force_subscribe_markup(not_subscribed)
        await query.edit_message_text(
            "⚠️ لم تشترك في جميع القنوات بعد.\n"
            "قم بالاشتراك ثم اضغط على زر التحقق",
            reply_markup=markup
        )

# ==================== تجميع النقاط ====================
async def collect_points_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قائمة تجميع النقاط"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # التحقق من الاشتراك الإجباري
    is_subscribed, not_subscribed = await check_subscription(user_id, context)
    if not is_subscribed:
        markup = await force_subscribe_markup(not_subscribed)
        await query.edit_message_text(
            "⚠️ يجب الاشتراك في القنوات الإجبارية أولاً",
            reply_markup=markup
        )
        return
    
    keyboard = [
        [InlineKeyboardButton("📢 مشاركة رابط الدعوة", callback_data="referral_link")],
        [InlineKeyboardButton("🔔 الانضمام إلى القنوات", callback_data="join_channels")],
        [InlineKeyboardButton("🎁 الهدية اليومية", callback_data="daily_reward")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
    ]
    
    markup = InlineKeyboardMarkup(keyboard)
    
    text = """
🎁 **تجميع النقاط**

اختر طريقة تجميع النقاط:
• مشاركة رابط الدعوة - احصل على {referral} نقطة لكل صديق
• الانضمام إلى القنوات - احصل على {join} نقطة لكل اشتراك
• الهدية اليومية - احصل على {daily} نقطة كل يوم
    """.format(
        referral=db.get_setting('referral_reward_points'),
        join=db.get_setting('channel_join_reward'),
        daily=db.get_setting('daily_reward_points')
    )
    
    await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

async def referral_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رابط الدعوة"""
    query = update.callback_query
    await query.answer()
    
    user = db.get_user(query.from_user.id)
    referral_code = user[8]
    bot_username = (await context.bot.get_me()).username
    
    referral_link = f"https://t.me/{bot_username}?start={referral_code}"
    reward = db.get_setting('referral_reward_points')
    
    text = f"""
🔗 **رابط الدعوة الخاص بك**

{referral_link}

🎁 المكافأة: {reward} نقطة لكل صديق يدعوه عبر رابطك
👥 إجمالي من دعوتهم: {user[10]} أشخاص

انسخ الرابط وشاركه مع أصدقائك!
    """
    
    keyboard = [
        [InlineKeyboardButton("🔙 رجوع", callback_data="collect_points")]
    ]
    
    markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

async def daily_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الهدية اليومية"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if db.can_claim_daily_reward(user_id):
        reward_points = int(db.get_setting('daily_reward_points'))
        db.claim_daily_reward(user_id)
        db.update_user_points(user_id, reward_points, "daily_reward", "هدية يومية")
        
        text = f"✅ تم إضافة {reward_points} نقطة إلى رصيدك!"
    else:
        text = "⚠️ لقد استلمت هديتك اليومية بالفعل!\nعود غداً للحصول على هدية جديدة."
    
    keyboard = [
        [InlineKeyboardButton("🔙 رجوع", callback_data="collect_points")]
    ]
    
    markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=markup)

async def join_channels_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قائمة القنوات للانضمام"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    channels = db.get_active_funded_channels()
    
    if not channels:
        text = "📢 لا توجد قنوات متاحة حالياً للانضمام"
        keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="collect_points")]]
        markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=markup)
        return
    
    # تخزين القنوات في context للتنقل
    context.user_data['channels_page'] = 0
    context.user_data['channels_list'] = channels
    
    await show_channels_page(update, context)

async def show_channels_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض صفحة من القنوات"""
    query = update.callback_query
    page = context.user_data.get('channels_page', 0)
    channels = context.user_data.get('channels_list', [])
    
    if not channels:
        return
    
    per_page = 5
    total_pages = (len(channels) + per_page - 1) // per_page
    start = page * per_page
    end = start + per_page
    current_channels = channels[start:end]
    
    text = f"📢 **قنوات متاحة للانضمام** (صفحة {page + 1}/{total_pages})\n\n"
    text += "اختر قناة للانضمام واحصل على {reward} نقطة\n\n".format(reward=db.get_setting('channel_join_reward'))
    
    keyboard = []
    
    for channel in current_channels:
        channel_id, channel_username, channel_title = channel[1], channel[2], channel[3]
        btn_text = f"📺 {channel_title[:20]}"
        keyboard.append([InlineKeyboardButton(btn_text, url=f"https://t.me/{channel_username}")])
        keyboard.append([InlineKeyboardButton(f"✅ تحقق من الاشتراك في {channel_title[:15]}", callback_data=f"verify_channel_{channel[0]}")])
    
    # أزرار التنقل
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ السابق", callback_data="channels_prev"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("التالي ▶️", callback_data="channels_next"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="collect_points")])
    
    markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

async def verify_channel_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """التحقق من الاشتراك في قناة ممولة"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    channel_db_id = int(query.data.replace("verify_channel_", ""))
    
    funded_channel = db.cursor.execute('SELECT * FROM funded_channels WHERE id = ?', (channel_db_id,)).fetchone()
    
    if not funded_channel:
        await query.edit_message_text("⚠️ هذه القناة غير موجودة")
        return
    
    # التحقق من الاشتراك
    try:
        member = await context.bot.get_chat_member(chat_id=funded_channel[1], user_id=user_id)
        if member.status in ['member', 'administrator', 'creator']:
            # تحقق إذا كان المستخدم قد حصل على المكافأة سابقاً
            existing_sub = db.check_user_subscribed_to_channel(user_id, channel_db_id)
            if existing_sub:
                await query.edit_message_text("✅ لقد حصلت على مكافأة هذه القناة مسبقاً!")
                return
            
            # إضافة المكافأة
            reward_points = int(db.get_setting('channel_join_reward'))
            db.add_channel_subscription(user_id, channel_db_id)
            completed = db.reward_channel_subscription(user_id, channel_db_id, reward_points)
            db.update_user_points(user_id, reward_points, "channel_join", f"انضمام إلى {funded_channel[3]}")
            
            # إرسال إشعار لصاحب القناة
            try:
                owner_text = f"✅ قام مستخدم جديد بالاشتراك في قناتك {funded_channel[3]}\n"
                owner_text += f"📊 التقدم: {funded_channel[6] + 1}/{funded_channel[5]}"
                await context.bot.send_message(chat_id=funded_channel[4], text=owner_text)
            except:
                pass
            
            text = f"✅ تم التحقق! تم إضافة {reward_points} نقطة إلى رصيدك"
            
            if completed:
                text += "\n\n🎉 **اكتمل العدد المطلوب للقناة!**"
                # إشعار صاحب القناة
                try:
                    await context.bot.send_message(
                        chat_id=funded_channel[4],
                        text=f"🎉 تم اكتمال العدد المطلوب لقناتك {funded_channel[3]}!\n"
                             f"شكراً لاستخدامك خدماتنا"
                    )
                except:
                    pass
            
            keyboard = [
                [InlineKeyboardButton("🔙 رجوع للقنوات", callback_data="join_channels")],
                [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_to_main")]
            ]
            
            markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        else:
            await query.edit_message_text(
                "❌ أنت لست مشتركاً في هذه القناة بعد!\n"
                "قم بالاشتراك ثم اضغط على زر التحقق مرة أخرى"
            )
    except Exception as e:
        await query.edit_message_text(f"⚠️ حدث خطأ: {str(e)}")

# ==================== تمويل القنوات ====================
async def fund_channel_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قائمة تمويل القنوات"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    member_cost = db.get_setting('member_cost')
    min_members = db.get_setting('min_members')
    max_members = db.get_setting('max_members')
    
    text = f"""
💰 **تمويل قناتك**

احصل على أعضاء حقيقيين لقناتك مقابل نقاطك!
• تكلفة العضو الواحد: {member_cost} نقطة
• الحد الأدنى: {min_members} عضو
• الحد الأقصى: {max_members} عضو

⚠️ **شروط الخدمة:**
• يجب أن تكون القناة عامة
• يجب أن تكون مشرفاً في القناة
• سيتم خصم النقاط فور تأكيد الطلب

لبدء تمويل قناتك، أرسل رابط القناة:
    """
    
    keyboard = [
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
    ]
    
    markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    
    # تخزين حالة المستخدم
    context.user_data['awaiting_channel_link'] = True

async def handle_channel_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة رابط القناة"""
    user_id = update.effective_user.id
    text = update.message.text
    
    if not context.user_data.get('awaiting_channel_link'):
        return
    
    # تنظيف الرابط
    channel_username = text.replace("https://t.me/", "").replace("@", "").strip()
    
    try:
        chat = await context.bot.get_chat(f"@{channel_username}")
        
        # التحقق من أن المستخدم مشرف في القناة
        member = await context.bot.get_chat_member(chat.id, user_id)
        if member.status not in ['administrator', 'creator']:
            await update.message.reply_text(
                "❌ يجب أن تكون مشرفاً في القناة لتمويلها!\n"
                "يرجى التأكد من أنك مشرف وحاول مرة أخرى"
            )
            return
        
        context.user_data['funding_channel'] = {
            'id': chat.id,
            'username': channel_username,
            'title': chat.title
        }
        
        min_members = int(db.get_setting('min_members'))
        max_members = int(db.get_setting('max_members'))
        member_cost = int(db.get_setting('member_cost'))
        
        user = db.get_user(user_id)
        points = user[3]
        
        text = f"""
✅ تم استلام رابط القناة: {chat.title}

الآن أرسل **عدد الأعضاء** المطلوب (من {min_members} إلى {max_members})
• التكلفة للعضو الواحد: {member_cost} نقطة
• رصيدك الحالي: {points} نقطة

أقصى عدد يمكنك شراؤه: {points // member_cost if member_cost > 0 else 0} عضو
        """
        
        await update.message.reply_text(text)
        context.user_data['awaiting_member_count'] = True
        del context.user_data['awaiting_channel_link']
        
    except Exception as e:
        await update.message.reply_text(
            "❌ لم أتمكن من العثور على القناة!\n"
            "تأكد من أن:\n"
            "• الرابط صحيح\n"
            "• القناة عامة\n"
            "• البوت مشرف في القناة\n\n"
            "أرسل الرابط مرة أخرى:"
        )

async def handle_member_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة عدد الأعضاء المطلوب"""
    user_id = update.effective_user.id
    
    if not context.user_data.get('awaiting_member_count'):
        return
    
    try:
        count = int(update.message.text)
        
        min_members = int(db.get_setting('min_members'))
        max_members = int(db.get_setting('max_members'))
        member_cost = int(db.get_setting('member_cost'))
        
        if count < min_members or count > max_members:
            await update.message.reply_text(f"⚠️ العدد يجب أن يكون بين {min_members} و {max_members}")
            return
        
        user = db.get_user(user_id)
        points = user[3]
        total_cost = count * member_cost
        
        if points < total_cost:
            await update.message.reply_text(f"❌ رصيدك غير كافٍ!\nالمطلوب: {total_cost} نقطة\nرصيدك: {points} نقطة")
            return
        
        channel_data = context.user_data['funding_channel']
        
        # خصم النقاط
        db.update_user_points(user_id, -total_cost, "fund_channel", f"تمويل {channel_data['title']} - {count} عضو")
        
        # إضافة القناة
        channel_id = db.add_funded_channel(
            channel_data['id'],
            channel_data['username'],
            channel_data['title'],
            user_id,
            count,
            member_cost,
            total_cost
        )
        
        text = f"""
✅ **تم استلام طلب التمويل بنجاح!**

📢 القناة: {channel_data['title']}
👥 العدد المطلوب: {count} عضو
💰 التكلفة: {total_cost} نقطة
📊 الحالة: قيد التنفيذ

سيتم إشعارك عند اشتراك المستخدمين واكتمال العدد
        """
        
        keyboard = [
            [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_to_main")]
        ]
        
        markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        
        # تنظيف البيانات
        del context.user_data['awaiting_member_count']
        del context.user_data['funding_channel']
        
    except ValueError:
        await update.message.reply_text("❌ الرجاء إرسال عدد صحيح من الأعضاء")

# ==================== خدمات SSM ====================
async def ssm_services_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قائمة خدمات SSM"""
    query = update.callback_query
    await query.answer()
    
    categories = db.get_ssm_categories()
    
    if not categories:
        text = "🛒 لا توجد خدمات متاحة حالياً"
        keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]]
        markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=markup)
        return
    
    text = "🛒 **خدمات SSM**\n\nاختر القسم المطلوب:"
    keyboard = []
    
    for category in categories:
        category_id, name = category[0], category[1]
        keyboard.append([InlineKeyboardButton(f"📁 {name}", callback_data=f"ssm_category_{category_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")])
    
    markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

async def show_ssm_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض خدمات قسم معين"""
    query = update.callback_query
    await query.answer()
    
    category_id = int(query.data.replace("ssm_category_", ""))
    category = db.cursor.execute('SELECT * FROM ssm_categories WHERE id = ?', (category_id,)).fetchone()
    services = db.get_ssm_services(category_id)
    
    if not services:
        text = f"📁 **{category[1]}**\n\nلا توجد خدمات في هذا القسم حالياً"
        keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="ssm_services")]]
        markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        return
    
    text = f"📁 **{category[1]}**\n\nاختر الخدمة المطلوبة:"
    keyboard = []
    
    for service in services:
        service_id, _, name, desc, exec_time, price = service[0], service[1], service[2], service[3], service[4], service[5]
        btn_text = f"🔹 {name} | {price} نقطة"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"ssm_service_{service_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="ssm_services")])
    
    markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

async def show_ssm_service_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض تفاصيل خدمة معينة"""
    query = update.callback_query
    await query.answer()
    
    service_id = int(query.data.replace("ssm_service_", ""))
    service = db.cursor.execute('''
        SELECT s.*, c.name 
        FROM ssm_services s 
        JOIN ssm_categories c ON s.category_id = c.id 
        WHERE s.id = ?
    ''', (service_id,)).fetchone()
    
    if not service:
        await query.edit_message_text("⚠️ هذه الخدمة غير متوفرة")
        return
    
    service_id, category_id, name, description, exec_time, price, _, category_name = service
    
    user = db.get_user(query.from_user.id)
    points = user[3] if user else 0
    
    text = f"""
🔹 **{name}**

📝 الوصف: {description}
⏱ مدة التنفيذ: {exec_time}
💰 السعر: {price} نقطة
💎 رصيدك: {points} نقطة

هل تريد شراء هذه الخدمة؟
    """
    
    keyboard = [
        [
            InlineKeyboardButton("✅ شراء", callback_data=f"buy_service_{service_id}"),
            InlineKeyboardButton("❌ إلغاء", callback_data=f"ssm_category_{category_id}")
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"ssm_category_{category_id}")]
    ]
    
    markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

async def buy_ssm_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شراء خدمة SSM"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    service_id = int(query.data.replace("buy_service_", ""))
    
    service = db.cursor.execute('SELECT * FROM ssm_services WHERE id = ?', (service_id,)).fetchone()
    user = db.get_user(user_id)
    
    if not service or not user:
        await query.edit_message_text("⚠️ حدث خطأ")
        return
    
    points = user[3]
    price = service[5]
    
    if points < price:
        await query.edit_message_text(f"❌ رصيدك غير كافٍ!\nالمطلوب: {price} نقطة\nرصيدك: {points} نقطة")
        return
    
    # خصم النقاط
    db.update_user_points(user_id, -price, "buy_service", f"شراء {service[2]}")
    
    text = f"""
✅ **تم شراء الخدمة بنجاح!**

🔹 الخدمة: {service[2]}
💰 المبلغ المخصوم: {price} نقطة
⏱ مدة التنفيذ: {service[4]}
📊 الحالة: قيد المعالجة

سيتم إشعارك عند اكتمال الخدمة
    """
    
    keyboard = [
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_to_main")],
        [InlineKeyboardButton("🛒 خدمات أخرى", callback_data="ssm_services")]
    ]
    
    markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    
    # إشعار المدير بالطلب
    owner_text = f"""
🛒 **طلب خدمة جديد**

👤 المستخدم: [{user[2]}](tg://user?id={user_id})
🆔 ID: `{user_id}`
🔹 الخدمة: {service[2]}
💰 السعر: {price} نقطة
⏱ المدة: {service[4]}
    """
    
    try:
        await context.bot.send_message(chat_id=OWNER_ID, text=owner_text, parse_mode=ParseMode.MARKDOWN)
    except:
        pass

# ==================== لوحة التحكم ====================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لوحة التحكم الرئيسية"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != OWNER_ID:
        await query.edit_message_text("⛔ هذه الصفحة مخصصة للمشرفين فقط")
        return
    
    text = """
⚙️ **لوحة التحكم**

مرحباً بك في لوحة التحكم
اختر الإجراء المطلوب:
    """
    
    keyboard = [
        [InlineKeyboardButton("👥 جميع المستخدمين", callback_data="admin_users")],
        [InlineKeyboardButton("🔍 بحث عن مستخدم", callback_data="admin_search_user")],
        [InlineKeyboardButton("💰 تغير الأسعار والمكافآت", callback_data="admin_settings")],
        [InlineKeyboardButton("📢 قنوات الاشتراك الإجباري", callback_data="admin_forced_channels")],
        [InlineKeyboardButton("📌 تغير قناة البوت / الدعم", callback_data="admin_bot_settings")],
        [InlineKeyboardButton("🛒 إدارة خدمات SSM", callback_data="admin_ssm")],
        [InlineKeyboardButton("🔄 وضع الصيانة", callback_data="admin_maintenance")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
    ]
    
    markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

async def admin_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض جميع المستخدمين"""
    query = update.callback_query
    await query.answer()
    
    users = db.get_all_users()
    
    text = f"👥 **جميع المستخدمين**\nإجمالي: {len(users)}\n\n"
    
    keyboard = []
    
    for i, user in enumerate(users[:10]):  # عرض أول 10 مستخدمين
        user_id, username, first_name, points, is_blocked = user
        display_name = first_name or "بدون اسم"
        status = "🚫 محظور" if is_blocked else "✅ نشط"
        username_text = f"@{username}" if username else "لا يوجد"
        
        text += f"{i+1}. [{display_name}](tg://user?id={user_id})\n"
        text += f"🆔 `{user_id}`\n"
        text += f"👤 {username_text}\n"
        text += f"💎 {points} نقطة | {status}\n\n"
        
        keyboard.append([InlineKeyboardButton(f"🔍 {display_name[:15]}", callback_data=f"admin_user_{user_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")])
    
    markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

async def admin_search_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """طلب البحث عن مستخدم"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🔍 **البحث عن مستخدم**\n\n"
        "أرسل معرف المستخدم (ID) أو اليوزرنيم للبحث:"
    )
    context.user_data['awaiting_admin_search'] = True

async def handle_admin_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة البحث عن مستخدم"""
    if not context.user_data.get('awaiting_admin_search'):
        return
    
    user_input = update.message.text
    user = None
    
    # البحث بالايدي
    try:
        user_id = int(user_input)
        user = db.get_user(user_id)
    except:
        # البحث باليوزرنيم
        user = db.get_user_by_username(user_input)
    
    if not user:
        await update.message.reply_text("❌ المستخدم غير موجود!")
        return
    
    user_id, username, first_name, points, total_points, joined_date, is_blocked, block_reason, referred_by, referral_code, _, total_referrals = user
    
    # جلب حركات المستخدم
    actions = db.get_user_actions(user_id)
    
    text = f"""
👤 **معلومات المستخدم**

🆔 المعرف: `{user_id}`
👤 الاسم: {first_name}
📱 اليوزر: @{username if username else 'لا يوجد'}
💎 الرصيد: {points} نقطة
🏆 إجمالي النقاط: {total_points} نقطة
📅 تاريخ الانضمام: {joined_date}
👥 عدد الدعوات: {total_referrals}
🔗 كود الدعوة: `{referral_code}`

🚫 الحظر: {'✅ لا' if not is_blocked else '⚠️ نعم'}
    """
    
    if is_blocked and block_reason:
        text += f"📌 سبب الحظر: {block_reason}\n"
    
    text += "\n📊 **آخر الحركات:**\n"
    
    for i, action in enumerate(actions[:10]):
        _, _, action_type, details, points, timestamp = action
        text += f"{i+1}. {action_type} | {points:+d} نقطة | {timestamp[:16]}\n"
        if details:
            text += f"   {details}\n"
    
    keyboard = [
        [InlineKeyboardButton("💰 شحن رصيد", callback_data=f"admin_charge_{user_id}")],
        [InlineKeyboardButton("❌ خصم رصيد", callback_data=f"admin_deduct_{user_id}")],
    ]
    
    if is_blocked:
        keyboard.append([InlineKeyboardButton("✅ رفع الحظر", callback_data=f"admin_unblock_{user_id}")])
    else:
        keyboard.append([InlineKeyboardButton("🚫 حظر", callback_data=f"admin_block_{user_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")])
    
    markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    
    context.user_data['awaiting_admin_search'] = False

async def admin_handle_user_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة إجراءات المستخدم"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = int(data.split("_")[-1])
    
    if "charge" in data:
        await query.edit_message_text(f"💰 أرسل عدد النقاط لشحنها للمستخدم `{user_id}`:")
        context.user_data['awaiting_charge_amount'] = user_id
        
    elif "deduct" in data:
        await query.edit_message_text(f"❌ أرسل عدد النقاط لخصمها من المستخدم `{user_id}`:")
        context.user_data['awaiting_deduct_amount'] = user_id
        
    elif "block" in data:
        await query.edit_message_text(f"🚫 أرسل سبب حظر المستخدم `{user_id}`:")
        context.user_data['awaiting_block_reason'] = user_id
        
    elif "unblock" in data:
        db.unblock_user(user_id)
        await query.edit_message_text(f"✅ تم رفع الحظر عن المستخدم `{user_id}`")

async def admin_handle_charge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة شحن الرصيد"""
    if not context.user_data.get('awaiting_charge_amount'):
        return
    
    user_id = context.user_data['awaiting_charge_amount']
    
    try:
        amount = int(update.message.text)
        db.update_user_points(user_id, amount, "admin_charge", "شحن من المدير")
        
        await update.message.reply_text(f"✅ تم شحن {amount} نقطة للمستخدم `{user_id}`")
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"💰 تم شحن {amount} نقطة إلى رصيدك بواسطة الإدارة"
            )
        except:
            pass
        
    except ValueError:
        await update.message.reply_text("❌ الرجاء إرسال رقم صحيح")
    
    context.user_data['awaiting_charge_amount'] = None

async def admin_handle_deduct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة خصم الرصيد"""
    if not context.user_data.get('awaiting_deduct_amount'):
        return
    
    user_id = context.user_data['awaiting_deduct_amount']
    
    try:
        amount = int(update.message.text)
        user = db.get_user(user_id)
        
        if user[3] < amount:
            await update.message.reply_text(f"❌ رصيد المستخدم غير كافٍ!\nرصيده الحالي: {user[3]} نقطة")
            return
        
        db.update_user_points(user_id, -amount, "admin_deduct", "خصم من المدير")
        await update.message.reply_text(f"✅ تم خصم {amount} نقطة من المستخدم `{user_id}`")
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"❌ تم خصم {amount} نقطة من رصيدك بواسطة الإدارة"
            )
        except:
            pass
        
    except ValueError:
        await update.message.reply_text("❌ الرجاء إرسال رقم صحيح")
    
    context.user_data['awaiting_deduct_amount'] = None

async def admin_handle_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة حظر المستخدم"""
    if not context.user_data.get('awaiting_block_reason'):
        return
    
    user_id = context.user_data['awaiting_block_reason']
    reason = update.message.text
    
    db.block_user(user_id, reason)
    await update.message.reply_text(f"✅ تم حظر المستخدم `{user_id}`\nالسبب: {reason}")
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🚫 تم حظرك من البوت\nالسبب: {reason}"
        )
    except:
        pass
    
    context.user_data['awaiting_block_reason'] = None

async def admin_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قائمة إعدادات الأسعار والمكافآت"""
    query = update.callback_query
    await query.answer()
    
    settings = {
        'daily_reward_points': '🎁 الهدية اليومية',
        'referral_reward_points': '👥 مكافأة الدعوة',
        'channel_join_reward': '📢 مكافأة الاشتراك',
        'member_cost': '💰 تكلفة العضو',
        'min_members': '📊 الحد الأدنى للتمويل',
        'max_members': '📈 الحد الأقصى للتمويل'
    }
    
    text = "💰 **تغير الأسعار والمكافآت**\n\n"
    keyboard = []
    
    for key, name in settings.items():
        value = db.get_setting(key)
        text += f"• {name}: `{value}`\n"
        keyboard.append([InlineKeyboardButton(f"✏️ تعديل {name}", callback_data=f"edit_setting_{key}")])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")])
    
    markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

async def admin_edit_setting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعديل إعداد معين"""
    query = update.callback_query
    await query.answer()
    
    setting_key = query.data.replace("edit_setting_", "")
    setting_names = {
        'daily_reward_points': '🎁 الهدية اليومية',
        'referral_reward_points': '👥 مكافأة الدعوة',
        'channel_join_reward': '📢 مكافأة الاشتراك',
        'member_cost': '💰 تكلفة العضو',
        'min_members': '📊 الحد الأدنى للتمويل',
        'max_members': '📈 الحد الأقصى للتمويل'
    }
    
    current_value = db.get_setting(setting_key)
    
    await query.edit_message_text(
        f"✏️ **تعديل {setting_names.get(setting_key, setting_key)}**\n\n"
        f"القيمة الحالية: `{current_value}`\n\n"
        f"أرسل القيمة الجديدة:"
    )
    
    context.user_data['awaiting_setting_value'] = setting_key

async def admin_handle_setting_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة القيمة الجديدة للإعداد"""
    if not context.user_data.get('awaiting_setting_value'):
        return
    
    setting_key = context.user_data['awaiting_setting_value']
    value = update.message.text
    
    db.set_setting(setting_key, value)
    await update.message.reply_text(f"✅ تم تحديث القيمة بنجاح!")
    
    context.user_data['awaiting_setting_value'] = None

async def admin_forced_channels_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قائمة قنوات الاشتراك الإجباري"""
    query = update.callback_query
    await query.answer()
    
    channels = db.get_forced_channels()
    
    text = "📢 **قنوات الاشتراك الإجباري**\n\n"
    
    if channels:
        for channel in channels:
            text += f"• {channel[3]} - @{channel[2]}\n"
    else:
        text += "لا توجد قنوات إجبارية\n"
    
    keyboard = [
        [InlineKeyboardButton("➕ إضافة قناة", callback_data="admin_add_forced")],
    ]
    
    for channel in channels:
        keyboard.append([
            InlineKeyboardButton(f"❌ حذف {channel[3][:15]}", callback_data=f"del_forced_{channel[0]}")
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")])
    
    markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

async def admin_add_forced_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة قناة إجبارية"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📢 **إضافة قناة اشتراك إجباري**\n\n"
        "أرسل معرف القناة (بالصيغة التالية):\n"
        "`@username`\n"
        "أو رابط القناة: `https://t.me/username`"
    )
    
    context.user_data['awaiting_forced_channel'] = True

async def admin_handle_forced_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة إضافة قناة إجبارية"""
    if not context.user_data.get('awaiting_forced_channel'):
        return
    
    text = update.message.text
    channel_username = text.replace("https://t.me/", "").replace("@", "").strip()
    
    try:
        chat = await context.bot.get_chat(f"@{channel_username}")
        
        # إضافة البوت كمشرف في القناة
        try:
            await context.bot.promote_chat_member(
                chat_id=chat.id,
                user_id=context.bot.id,
                can_invite_users=True
            )
        except:
            pass
        
        db.add_forced_channel(chat.id, channel_username, chat.title)
        
        await update.message.reply_text(f"✅ تم إضافة {chat.title} كقناة إجبارية")
        
    except Exception as e:
        await update.message.reply_text(f"❌ حدث خطأ: {str(e)}")
    
    context.user_data['awaiting_forced_channel'] = False

async def admin_delete_forced_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف قناة إجبارية"""
    query = update.callback_query
    await query.answer()
    
    channel_id = int(query.data.replace("del_forced_", ""))
    db.delete_forced_channel(channel_id)
    
    await query.edit_message_text("✅ تم حذف القناة بنجاح")
    
    # العودة لقائمة القنوات
    await admin_forced_channels_menu(update, context)

async def admin_bot_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إعدادات البوت العامة"""
    query = update.callback_query
    await query.answer()
    
    bot_channel = db.get_setting('bot_channel') or "غير محدد"
    support_user = db.get_setting('support_user')
    
    text = f"""
📌 **إعدادات البوت**

📢 قناة البوت: {bot_channel}
🆘 الدعم الفني: @{support_user}

اختر ما تريد تعديله:
    """
    
    keyboard = [
        [InlineKeyboardButton("📢 تغير قناة البوت", callback_data="edit_bot_channel")],
        [InlineKeyboardButton("🆘 تغير يوزر الدعم", callback_data="edit_support")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
    ]
    
    markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

async def admin_edit_bot_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعديل قناة البوت"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📢 **تغير قناة البوت**\n\n"
        "أرسل رابط قناة البوت:\n"
        "مثال: `https://t.me/SSM_Services`"
    )
    
    context.user_data['awaiting_bot_channel'] = True

async def admin_handle_bot_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة تعديل قناة البوت"""
    if not context.user_data.get('awaiting_bot_channel'):
        return
    
    channel_link = update.message.text
    db.set_setting('bot_channel', channel_link)
    
    await update.message.reply_text(f"✅ تم تحديث قناة البوت إلى: {channel_link}")
    context.user_data['awaiting_bot_channel'] = False

async def admin_edit_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعديل يوزر الدعم"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🆘 **تغير يوزر الدعم**\n\n"
        "أرسل معرف يوزر الدعم:\n"
        "مثال: `Allawi04`\n"
        "(بدون @)"
    )
    
    context.user_data['awaiting_support_user'] = True

async def admin_handle_support_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة تعديل يوزر الدعم"""
    if not context.user_data.get('awaiting_support_user'):
        return
    
    support_user = update.message.text.replace("@", "").strip()
    db.set_setting('support_user', support_user)
    
    await update.message.reply_text(f"✅ تم تحديث يوزر الدعم إلى: @{support_user}")
    context.user_data['awaiting_support_user'] = False

async def admin_ssm_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إدارة خدمات SSM"""
    query = update.callback_query
    await query.answer()
    
    text = """
🛒 **إدارة خدمات SSM**

اختر الإجراء المطلوب:
    """
    
    keyboard = [
        [InlineKeyboardButton("➕ إضافة قسم جديد", callback_data="admin_add_category")],
        [InlineKeyboardButton("📋 عرض الأقسام", callback_data="admin_view_categories")],
        [InlineKeyboardButton("➕ إضافة خدمة", callback_data="admin_add_service")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
    ]
    
    markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

async def admin_add_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة قسم جديد"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "➕ **إضافة قسم جديد**\n\n"
        "أرسل اسم القسم الجديد:"
    )
    
    context.user_data['awaiting_category_name'] = True

async def admin_handle_category_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة إضافة قسم جديد"""
    if not context.user_data.get('awaiting_category_name'):
        return
    
    category_name = update.message.text
    db.add_ssm_category(category_name)
    
    await update.message.reply_text(f"✅ تم إضافة القسم: {category_name}")
    context.user_data['awaiting_category_name'] = False

async def admin_view_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الأقسام مع خيارات الحذف"""
    query = update.callback_query
    await query.answer()
    
    categories = db.get_ssm_categories()
    
    if not categories:
        await query.edit_message_text("📁 لا توجد أقسام بعد")
        return
    
    text = "📁 **الأقسام الحالية:**\n\n"
    keyboard = []
    
    for category in categories:
        category_id, name = category
        text += f"• {name}\n"
        keyboard.append([InlineKeyboardButton(f"❌ حذف {name[:15]}", callback_data=f"del_category_{category_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_ssm")])
    
    markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

async def admin_delete_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف قسم"""
    query = update.callback_query
    await query.answer()
    
    category_id = int(query.data.replace("del_category_", ""))
    db.delete_ssm_category(category_id)
    
    await query.edit_message_text("✅ تم حذف القسم وجميع خدماته")
    
    # العودة لقائمة الأقسام
    await admin_view_categories(update, context)

async def admin_add_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة خدمة جديدة"""
    query = update.callback_query
    await query.answer()
    
    categories = db.get_ssm_categories()
    
    if not categories:
        await query.edit_message_text(
            "⚠️ لا توجد أقسام!\n"
            "الرجاء إضافة قسم أولاً"
        )
        return
    
    text = "➕ **إضافة خدمة جديدة**\n\nاختر القسم:"
    keyboard = []
    
    for category in categories:
        category_id, name = category
        keyboard.append([InlineKeyboardButton(name, callback_data=f"select_category_{category_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_ssm")])
    
    markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

async def admin_select_category_for_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اختيار قسم لإضافة خدمة"""
    query = update.callback_query
    await query.answer()
    
    category_id = int(query.data.replace("select_category_", ""))
    context.user_data['service_category_id'] = category_id
    
    await query.edit_message_text(
        "📝 **إضافة خدمة جديدة**\n\n"
        "أرسل اسم الخدمة:"
    )
    
    context.user_data['awaiting_service_name'] = True

async def admin_handle_service_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة اسم الخدمة"""
    if not context.user_data.get('awaiting_service_name'):
        return
    
    context.user_data['service_name'] = update.message.text
    await update.message.reply_text("✅ تم حفظ الاسم\n\nأرسل وصف الخدمة:")
    context.user_data['awaiting_service_description'] = True
    context.user_data['awaiting_service_name'] = False

async def admin_handle_service_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة وصف الخدمة"""
    if not context.user_data.get('awaiting_service_description'):
        return
    
    context.user_data['service_description'] = update.message.text
    await update.message.reply_text("✅ تم حفظ الوصف\n\nأرسل مدة التنفيذ (مثال: 24 ساعة):")
    context.user_data['awaiting_service_time'] = True
    context.user_data['awaiting_service_description'] = False

async def admin_handle_service_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة مدة التنفيذ"""
    if not context.user_data.get('awaiting_service_time'):
        return
    
    context.user_data['service_time'] = update.message.text
    await update.message.reply_text("✅ تم حفظ المدة\n\nأرسل سعر الخدمة بالنقاط:")
    context.user_data['awaiting_service_price'] = True
    context.user_data['awaiting_service_time'] = False

async def admin_handle_service_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة سعر الخدمة"""
    if not context.user_data.get('awaiting_service_price'):
        return
    
    try:
        price = int(update.message.text)
        category_id = context.user_data['service_category_id']
        name = context.user_data['service_name']
        description = context.user_data['service_description']
        exec_time = context.user_data['service_time']
        
        db.add_ssm_service(category_id, name, description, exec_time, price)
        
        await update.message.reply_text(f"✅ تم إضافة الخدمة بنجاح!")
        
        # تنظيف البيانات
        context.user_data['awaiting_service_price'] = False
        context.user_data.pop('service_category_id', None)
        context.user_data.pop('service_name', None)
        context.user_data.pop('service_description', None)
        context.user_data.pop('service_time', None)
        
    except ValueError:
        await update.message.reply_text("❌ الرجاء إرسال رقم صحيح")

async def admin_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تفعيل/تعطيل وضع الصيانة"""
    query = update.callback_query
    await query.answer()
    
    current_mode = db.get_setting('maintenance_mode')
    
    text = f"""
🔄 **وضع الصيانة**

الحالة الحالية: {'🟢 معطل' if current_mode == '0' else '🔴 مفعل'}

هل تريد {'تعطيل' if current_mode == '1' else 'تفعيل'} وضع الصيانة؟
    """
    
    keyboard = [
        [InlineKeyboardButton("✅ نعم", callback_data=f"toggle_maintenance_{'0' if current_mode == '1' else '1'}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
    ]
    
    markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

async def admin_toggle_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبديل وضع الصيانة"""
    query = update.callback_query
    await query.answer()
    
    new_mode = query.data.replace("toggle_maintenance_", "")
    db.set_setting('maintenance_mode', new_mode)
    
    status = "مفعل" if new_mode == '1' else "معطل"
    await query.edit_message_text(f"✅ تم {status} وضع الصيانة")

# ==================== معالجات الرسائل والأوامر ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر بدء البوت"""
    user_id = update.effective_user.id
    
    # التحقق من وضع الصيانة
    maintenance_mode = db.get_setting('maintenance_mode')
    if maintenance_mode == '1' and user_id != OWNER_ID:
        await update.message.reply_text(
            "🔧 البوت في وضع الصيانة حالياً\n"
            "يرجى المحاولة لاحقاً"
        )
        return
    
    # معالجة كود الدعوة
    args = context.args
    referred_by = None
    
    if args:
        referral_code = args[0]
        # البحث عن المستخدم صاحب كود الدعوة
        db.cursor.execute('SELECT user_id FROM users WHERE referral_code = ?', (referral_code,))
        result = db.cursor.fetchone()
        if result and result[0] != user_id:
            referred_by = result[0]
    
    # إضافة المستخدم
    db.add_user(
        user_id,
        update.effective_user.username,
        update.effective_user.first_name,
        referred_by
    )
    
    # إضافة مكافأة الدعوة
    if referred_by:
        reward = int(db.get_setting('referral_reward_points'))
        db.update_user_points(referred_by, reward, "referral", f"دعوة مستخدم جديد {user_id}")
        db.update_user_points(user_id, 0, "register", "تسجيل جديد")  # زيادة عدد الدعوات في الـ trigger
        
        # تحديث عدد الدعوات
        db.cursor.execute('UPDATE users SET total_referrals = total_referrals + 1 WHERE user_id = ?', (referred_by,))
        db.conn.commit()
        
        try:
            await context.bot.send_message(
                chat_id=referred_by,
                text=f"🎉 قام مستخدم جديد بالتسجيل عبر رابط دعوتك!\n"
                     f"تم إضافة {reward} نقطة إلى رصيدك"
            )
        except:
            pass
    
    await main_menu(update, context)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة جميع الاستدعاءات"""
    query = update.callback_query
    user_id = query.from_user.id
    
    # التحقق من وضع الصيانة
    maintenance_mode = db.get_setting('maintenance_mode')
    if maintenance_mode == '1' and user_id != OWNER_ID:
        await query.answer("⚠️ البوت في وضع الصيانة")
        return
    
    data = query.data
    
    try:
        # القوائم الرئيسية
        if data == "back_to_main":
            await main_menu(update, context, user_id)
        elif data == "check_subscription":
            await handle_check_subscription(update, context)
        elif data == "collect_points":
            await collect_points_menu(update, context)
        elif data == "referral_link":
            await referral_link(update, context)
        elif data == "daily_reward":
            await daily_reward(update, context)
        elif data == "join_channels":
            await join_channels_menu(update, context)
        elif data == "channels_next":
            context.user_data['channels_page'] = context.user_data.get('channels_page', 0) + 1
            await show_channels_page(update, context)
        elif data == "channels_prev":
            context.user_data['channels_page'] = context.user_data.get('channels_page', 0) - 1
            await show_channels_page(update, context)
        elif data == "fund_channel":
            await fund_channel_menu(update, context)
        elif data == "ssm_services":
            await ssm_services_menu(update, context)
        elif data.startswith("ssm_category_"):
            await show_ssm_category(update, context)
        elif data.startswith("ssm_service_"):
            await show_ssm_service_details(update, context)
        elif data.startswith("buy_service_"):
            await buy_ssm_service(update, context)
        elif data.startswith("verify_channel_"):
            await verify_channel_subscription(update, context)
        elif data == "my_balance":
            user = db.get_user(user_id)
            if user:
                await query.answer(f"رصيدك: {user[3]} نقطة", show_alert=True)
        
        # لوحة التحكم
        elif data == "admin_panel":
            await admin_panel(update, context)
        elif data == "admin_users":
            await admin_users_list(update, context)
        elif data.startswith("admin_user_"):
            await admin_handle_user_action(update, context)
        elif data.startswith("admin_charge_"):
            await admin_handle_user_action(update, context)
        elif data.startswith("admin_deduct_"):
            await admin_handle_user_action(update, context)
        elif data.startswith("admin_block_"):
            await admin_handle_user_action(update, context)
        elif data.startswith("admin_unblock_"):
            await admin_handle_user_action(update, context)
        elif data == "admin_search_user":
            await admin_search_user(update, context)
        elif data == "admin_settings":
            await admin_settings_menu(update, context)
        elif data.startswith("edit_setting_"):
            await admin_edit_setting(update, context)
        elif data == "admin_forced_channels":
            await admin_forced_channels_menu(update, context)
        elif data == "admin_add_forced":
            await admin_add_forced_channel(update, context)
        elif data.startswith("del_forced_"):
            await admin_delete_forced_channel(update, context)
        elif data == "admin_bot_settings":
            await admin_bot_settings_menu(update, context)
        elif data == "edit_bot_channel":
            await admin_edit_bot_channel(update, context)
        elif data == "edit_support":
            await admin_edit_support(update, context)
        elif data == "admin_ssm":
            await admin_ssm_menu(update, context)
        elif data == "admin_add_category":
            await admin_add_category(update, context)
        elif data == "admin_view_categories":
            await admin_view_categories(update, context)
        elif data.startswith("del_category_"):
            await admin_delete_category(update, context)
        elif data == "admin_add_service":
            await admin_add_service(update, context)
        elif data.startswith("select_category_"):
            await admin_select_category_for_service(update, context)
        elif data == "admin_maintenance":
            await admin_maintenance(update, context)
        elif data.startswith("toggle_maintenance_"):
            await admin_toggle_maintenance(update, context)
            
    except Exception as e:
        logger.error(f"Error in callback: {e}")
        await query.answer("⚠️ حدث خطأ", show_alert=True)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل النصية"""
    user_id = update.effective_user.id
    
    # التحقق من وضع الصيانة
    maintenance_mode = db.get_setting('maintenance_mode')
    if maintenance_mode == '1' and user_id != OWNER_ID:
        await update.message.reply_text("🔧 البوت في وضع الصيانة حالياً")
        return
    
    # معالجة الحالات المختلفة
    if context.user_data.get('awaiting_channel_link'):
        await handle_channel_link(update, context)
    elif context.user_data.get('awaiting_member_count'):
        await handle_member_count(update, context)
    elif context.user_data.get('awaiting_admin_search'):
        await handle_admin_search(update, context)
    elif context.user_data.get('awaiting_charge_amount'):
        await admin_handle_charge(update, context)
    elif context.user_data.get('awaiting_deduct_amount'):
        await admin_handle_deduct(update, context)
    elif context.user_data.get('awaiting_block_reason'):
        await admin_handle_block(update, context)
    elif context.user_data.get('awaiting_setting_value'):
        await admin_handle_setting_value(update, context)
    elif context.user_data.get('awaiting_forced_channel'):
        await admin_handle_forced_channel(update, context)
    elif context.user_data.get('awaiting_bot_channel'):
        await admin_handle_bot_channel(update, context)
    elif context.user_data.get('awaiting_support_user'):
        await admin_handle_support_user(update, context)
    elif context.user_data.get('awaiting_category_name'):
        await admin_handle_category_name(update, context)
    elif context.user_data.get('awaiting_service_name'):
        await admin_handle_service_name(update, context)
    elif context.user_data.get('awaiting_service_description'):
        await admin_handle_service_description(update, context)
    elif context.user_data.get('awaiting_service_time'):
        await admin_handle_service_time(update, context)
    elif context.user_data.get('awaiting_service_price'):
        await admin_handle_service_price(update, context)
    else:
        await update.message.reply_text(
            "❓ أمر غير معروف\n"
            "استخدم /start للعودة للقائمة الرئيسية"
        )

# ==================== تشغيل البوت ====================
def main():
    """تشغيل البوت"""
    # إنشاء التطبيق
    application = Application.builder().token(TOKEN).build()
    
    # إضافة معالجات الأوامر
    application.add_handler(CommandHandler("start", start))
    
    # معالج الاستدعاءات
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    # معالج الرسائل
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # تشغيل البوت
    print("🚀 بوت SSM يعمل...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
