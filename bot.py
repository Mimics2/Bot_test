import logging
import sqlite3
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from datetime import datetime

# === НАСТРОЙКИ ===
# Выберите один из способов:

# Способ 1: Прямое указание (РАСКОММЕНТИРУЙТЕ И ЗАПОЛНИТЕ)
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Замените на ваш токен
ADMIN_ID = 123456789  # Замените на ваш Telegram ID

# Способ 2: Переменные окружения (если используете)
# BOT_TOKEN = os.environ.get("BOT_TOKEN")
# ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

# Способ 3: Чтение из файла
# try:
#     with open("token.txt", "r") as f:
#         BOT_TOKEN = f.read().strip()
# except FileNotFoundError:
#     pass
# 
# try:
#     with open("admin_id.txt", "r") as f:
#         ADMIN_ID = int(f.read().strip())
# except FileNotFoundError:
#     pass

DB_PATH = "/tmp/bot.db"

# Проверка переменных
if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
    print("❌ BOT_TOKEN не найден!")
    print("Пожалуйста, установите токен одним из способов:")
    print("1. Раскомментируйте и заполните BOT_TOKEN в коде")
    print("2. Установите переменную окружения BOT_TOKEN")
    print("3. Создайте файл token.txt с токеном")
    exit(1)

if ADMIN_ID == 0 or ADMIN_ID == 123456789:
    print("❌ ADMIN_ID не настроен!")
    print("Пожалуйста, установите ваш Telegram ID одним из способов:")
    print("1. Раскомментируйте и заполните ADMIN_ID в коде")
    print("2. Установите переменную окружения ADMIN_ID")
    print("3. Создайте файл admin_id.txt с вашим ID")
    exit(1)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

logger.info(f"✅ Бот инициализирован. ADMIN_ID: {ADMIN_ID}")

class Database:
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_checks INTEGER DEFAULT 0
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscription_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_username TEXT,
                channel_url TEXT,
                channel_name TEXT,
                channel_type TEXT DEFAULT 'public',
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS confirmed_subscriptions (
                user_id INTEGER,
                channel_id INTEGER,
                confirmed BOOLEAN DEFAULT FALSE,
                confirmed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, channel_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS referral_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_url TEXT NOT NULL,
                channel_name TEXT,
                description TEXT,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id INTEGER,
                check_date DATE,
                check_count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, check_date)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✅ База данных создана")

    def add_user(self, user_id, username, full_name):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
            existing_user = cursor.fetchone()
            
            if existing_user:
                cursor.execute('''
                    UPDATE users 
                    SET last_active = CURRENT_TIMESTAMP, total_checks = total_checks + 1 
                    WHERE user_id = ?
                ''', (user_id,))
                logger.info(f"📊 Обновлен пользователь: {user_id}")
            else:
                cursor.execute('''
                    INSERT INTO users (user_id, username, full_name, last_active, total_checks)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP, 1)
                ''', (user_id, username, full_name))
                logger.info(f"👤 Новый пользователь: {user_id}")
            
            cursor.execute('''
                INSERT OR REPLACE INTO user_stats (user_id, check_date, check_count)
                VALUES (?, DATE('now'), COALESCE(
                    (SELECT check_count + 1 FROM user_stats WHERE user_id = ? AND check_date = DATE('now')),
                    1
                ))
            ''', (user_id, user_id))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка добавления пользователя: {e}")
            return False

    def get_user_stats(self, user_id):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT total_checks, joined_date, last_active FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            conn.close()
            return result
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return None

    def get_all_users_count(self):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM users')
            result = cursor.fetchone()[0]
            conn.close()
            return result
        except Exception as e:
            logger.error(f"❌ Ошибка получения количества пользователей: {e}")
            return 0

    def get_today_stats(self):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM user_stats WHERE check_date = DATE("now")')
            today_checks = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM users WHERE DATE(joined_date) = DATE("now")')
            today_new = cursor.fetchone()[0]
            
            conn.close()
            return today_checks, today_new
        except Exception as e:
            logger.error(f"❌ Ошибка получения сегодняшней статистики: {e}")
            return 0, 0

    def add_subscription_channel(self, channel_username, channel_url, channel_name, channel_type='public'):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('INSERT INTO subscription_channels (channel_username, channel_url, channel_name, channel_type) VALUES (?, ?, ?, ?)',
                         (channel_username, channel_url, channel_name, channel_type))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка добавления канала: {e}")
            return False

    def get_subscription_channels(self):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM subscription_channels ORDER BY id')
            channels = cursor.fetchall()
            conn.close()
            return channels
        except Exception as e:
            logger.error(f"❌ Ошибка получения каналов: {e}")
            return []

    def confirm_subscription(self, user_id, channel_id):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('INSERT OR REPLACE INTO confirmed_subscriptions (user_id, channel_id, confirmed) VALUES (?, ?, TRUE)',
                         (user_id, channel_id))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка подтверждения: {e}")
            return False

    def is_subscription_confirmed(self, user_id, channel_id):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT confirmed FROM confirmed_subscriptions WHERE user_id = ? AND channel_id = ?',
                         (user_id, channel_id))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else False
        except Exception as e:
            logger.error(f"❌ Ошибка проверки: {e}")
            return False

    def remove_subscription_confirmation(self, user_id, channel_id):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('DELETE FROM confirmed_subscriptions WHERE user_id = ? AND channel_id = ?',
                         (user_id, channel_id))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка удаления подтверждения: {e}")
            return False

    def add_referral_channel(self, channel_url, channel_name, description=""):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('INSERT INTO referral_channels (channel_url, channel_name, description) VALUES (?, ?, ?)',
                         (channel_url, channel_name, description))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка добавления финального канала: {e}")
            return False

    def get_referral_channels(self):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM referral_channels ORDER BY id')
            channels = cursor.fetchall()
            conn.close()
            return channels
        except Exception as e:
            logger.error(f"❌ Ошибка получения финальных каналов: {e}")
            return []

    def remove_subscription_channel(self, channel_id):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('DELETE FROM subscription_channels WHERE id = ?', (channel_id,))
            cursor.execute('DELETE FROM confirmed_subscriptions WHERE channel_id = ?', (channel_id,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка удаления канала: {e}")
            return False

    def remove_referral_channel(self, channel_id):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('DELETE FROM referral_channels WHERE id = ?', (channel_id,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка удаления финального канала: {e}")
            return False

    def get_all_users(self):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT user_id, username, full_name, joined_date FROM users ORDER BY joined_date DESC')
            users = cursor.fetchall()
            conn.close()
            return users
        except Exception as e:
            logger.error(f"❌ Ошибка получения пользователей: {e}")
            return []

# Инициализация базы данных
try:
    db = Database(DB_PATH)
    logger.info("✅ База данных загружена")
except Exception as e:
    logger.error(f"❌ Критическая ошибка БД: {e}")
    db = None

async def check_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка подписок"""
    user = update.effective_user
    bot = context.bot
    channels = db.get_subscription_channels()
    
    result = {
        "all_subscribed": True,
        "missing_channels": []
    }
    
    if not channels:
        return result
    
    for channel in channels:
        channel_id, channel_username, channel_url, channel_name, channel_type, _ = channel
        
        if channel_type == 'public':
            try:
                if channel_username:
                    clean_username = channel_username.lstrip('@')
                    chat_member = await bot.get_chat_member(f"@{clean_username}", user.id)
                    subscribed = chat_member.status in ['member', 'administrator', 'creator']
                    
                    if not subscribed:
                        result["all_subscribed"] = False
                        result["missing_channels"].append({
                            "id": channel_id,
                            "name": channel_name,
                            "type": "public",
                            "url": f"https://t.me/{clean_username}"
                        })
                else:
                    result["all_subscribed"] = False
                    result["missing_channels"].append({
                        "id": channel_id,
                        "name": channel_name,
                        "type": "public",
                        "url": channel_url
                    })
                    
            except Exception as e:
                logger.error(f"❌ Ошибка проверки {channel_username}: {e}")
                result["all_subscribed"] = False
                result["missing_channels"].append({
                    "id": channel_id,
                    "name": channel_name,
                    "type": "public",
                    "url": f"https://t.me/{clean_username}" if channel_username else channel_url
                })
        
        elif channel_type == 'private':
            confirmed = db.is_subscription_confirmed(user.id, channel_id)
            if not confirmed:
                result["all_subscribed"] = False
                result["missing_channels"].append({
                    "id": channel_id,
                    "name": channel_name,
                    "type": "private",
                    "url": channel_url
                })
    
    return result

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    logger.info(f"🔄 Команда /start от пользователя {update.effective_user.id}")
    
    if db is None:
        await update.message.reply_text("🔧 Сервис временно недоступен. Попробуйте позже.")
        return
        
    user = update.effective_user
    
    success = db.add_user(user.id, user.username, user.full_name)
    
    if not success:
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте снова.")
        return

    welcome_text = f"""
✨ *Добро пожаловать, {user.first_name}!* ✨

🤖 *Premium Access Bot* открывает эксклюзивный контент!

📋 *Как это работает:*
1️⃣ Подпишитесь на необходимые каналы
2️⃣ Пройдите проверку подписки  
3️⃣ Получите доступ к закрытому контенту

🚀 *Начнем ваше путешествие!*
    """
    
    await update.message.reply_text(welcome_text, parse_mode='Markdown')
    
    subscription_status = await check_subscriptions(update, context)
    
    if subscription_status["all_subscribed"]:
        await show_success_message(update, context)
    else:
        await show_subscription_request(update, context, subscription_status["missing_channels"])

async def show_success_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ успешного сообщения"""
    referral_channels = db.get_referral_channels()
    
    if not referral_channels:
        success_text = """
🎊 *Поздравляем!* 🎊

✅ Вы успешно подписались на все каналы!

📬 *Скоро мы добавим эксклюзивный контент для вас!*

🔄 Для повторной проверки используйте /check
        """
        if update.callback_query:
            await update.callback_query.edit_message_text(success_text, parse_mode='Markdown')
        else:
            await update.message.reply_text(success_text, parse_mode='Markdown')
        return
    
    channel = referral_channels[0]
    channel_id, channel_url, channel_name, description, _ = channel
    
    success_text = f"""
🎉 *ДОСТУП ОТКРЫТ!* 🎉

✨ *Поздравляем! Вы получили доступ к эксклюзивному контенту!*

💎 *Ваш эксклюзив:*
*{channel_name}*

📝 *Описание:*
{description or 'Премиум контент для избранных'}

🔗 *Ваша персональная ссылка:*
`{channel_url}`
    """
    
    keyboard = [
        [InlineKeyboardButton(f"🚀 Перейти в {channel_name}", url=channel_url)],
        [InlineKeyboardButton("🔄 Проверить подписку", callback_data="check_subs")]
    ]
    
    if update.effective_user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Панель управления", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(success_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(success_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_subscription_request(update: Update, context: ContextTypes.DEFAULT_TYPE, missing_channels=None):
    """Показ запроса на подписку"""
    if missing_channels is None:
        missing_channels = []
        
    keyboard = []
    
    for channel_info in missing_channels:
        if channel_info["type"] == "public":
            keyboard.append([
                InlineKeyboardButton(
                    f"📢 Подписаться на {channel_info['name']}",
                    url=channel_info["url"]
                )
            ])
        elif channel_info["type"] == "private":
            keyboard.append([
                InlineKeyboardButton(
                    f"🔐 Присоединиться к {channel_info['name']}",
                    url=channel_info["url"]
                ),
                InlineKeyboardButton(
                    f"✅ Подтвердить",
                    callback_data=f"confirm_{channel_info['id']}"
                )
            ])
    
    keyboard.append([InlineKeyboardButton("🔄 Проверить все подписки", callback_data="check_subs")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if missing_channels:
        public_channels = [ch["name"] for ch in missing_channels if ch["type"] == "public"]
        private_channels = [ch["name"] for ch in missing_channels if ch["type"] == "private"]
        
        request_text = "🔒 *ДОСТУП ОГРАНИЧЕН*\n\n"
        request_text += "📋 *Для получения доступа необходимо:*\n\n"
        
        if public_channels:
            request_text += "📢 *Подпишитесь на каналы:*\n"
            for channel in public_channels:
                request_text += f"• {channel}\n"
            request_text += "\n"
        
        if private_channels:
            request_text += "🔐 *Вступите в приватные каналы:*\n"
            for channel in private_channels:
                request_text += f"• {channel}\n"
            request_text += "\n"
            request_text += "_После вступления нажмите кнопку 'Подтвердить'_ ✨\n"
        
        request_text += "\n🎯 *После выполнения всех условий нажмите кнопку проверки* 👇"
    else:
        request_text = "📋 Для получения доступа необходимо подписаться на каналы"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(request_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(request_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ панель"""
    if db is None:
        if update.callback_query:
            await update.callback_query.edit_message_text("❌ База данных недоступна")
        else:
            await update.message.reply_text("❌ База данных недоступна")
        return
        
    total_users = db.get_all_users_count()
    today_checks, today_new = db.get_today_stats()
    sub_channels = db.get_subscription_channels()
    ref_channels = db.get_referral_channels()
    
    admin_text = f"""
⚙️ *ПАНЕЛЬ УПРАВЛЕНИЯ*

📈 *СТАТИСТИКА:*
• 👥 Всего пользователей: *{total_users}*
• 🔄 Проверок сегодня: *{today_checks}*
• 🆕 Новых сегодня: *{today_new}*
• 📺 Каналов для проверки: *{len(sub_channels)}*
• 💎 Финальных каналов: *{len(ref_channels)}*
    """
    
    keyboard = [
        [InlineKeyboardButton("📺 Управление каналами", callback_data="manage_channels")],
        [InlineKeyboardButton("👥 Список пользователей", callback_data="users_list")],
        [InlineKeyboardButton("◀️ Назад", callback_data="check_subs")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(admin_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(admin_text, reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок"""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    
    logger.info(f"🔘 Нажата кнопка: {query.data}")
    
    if query.data == "check_subs":
        db.add_user(user.id, user.username, user.full_name)
        subscription_status = await check_subscriptions(update, context)
        
        if subscription_status["all_subscribed"]:
            await show_success_message(update, context)
        else:
            await show_subscription_request(update, context, subscription_status["missing_channels"])
    
    elif query.data.startswith("confirm_"):
        channel_id = int(query.data.replace("confirm_", ""))
        
        if db.confirm_subscription(user.id, channel_id):
            await query.answer("✅ Подписка подтверждена!", show_alert=True)
            subscription_status = await check_subscriptions(update, context)
            
            if subscription_status["all_subscribed"]:
                await show_success_message(update, context)
            else:
                await show_subscription_request(update, context, subscription_status["missing_channels"])
        else:
            await query.answer("❌ Ошибка подтверждения", show_alert=True)
    
    elif query.data == "admin_panel":
        if user.id == ADMIN_ID:
            await show_admin_panel(update, context)
        else:
            await query.answer("🚫 У вас нет доступа", show_alert=True)
    
    elif query.data == "manage_channels":
        if user.id == ADMIN_ID:
            await show_manage_channels(update, context)
        else:
            await query.answer("🚫 У вас нет доступа", show_alert=True)
    
    elif query.data == "users_list":
        if user.id == ADMIN_ID:
            await show_users_list(update, context)
        else:
            await query.answer("🚫 У вас нет доступа", show_alert=True)

async def show_manage_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Управление каналами"""
    sub_channels = db.get_subscription_channels()
    ref_channels = db.get_referral_channels()
    
    text = f"""
📊 *Управление каналами*

📺 *Каналы для подписки ({len(sub_channels)}):*
"""
    
    for channel in sub_channels:
        channel_id, username, url, name, channel_type, _ = channel
        type_icon = "🔓" if channel_type == 'public' else "🔒"
        username_display = username if username else "ссылка"
        text += f"{type_icon} {name} ({username_display})\n"
    
    text += f"\n💎 *Финальные каналы ({len(ref_channels)}):*\n"
    
    for channel in ref_channels:
        channel_id, url, name, description, _ = channel
        text += f"💎 {name}\n"
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить публичный канал", callback_data="add_public_channel")],
        [InlineKeyboardButton("➕ Добавить приватный канал", callback_data="add_private_channel")],
        [InlineKeyboardButton("💎 Добавить финальный канал", callback_data="add_referral_channel")],
        [InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список пользователей"""
    users = db.get_all_users()
    
    if not users:
        text = "👥 *Пользователи не найдены*"
    else:
        text = "👥 *Список пользователей:*\n\n"
        for i, user_data in enumerate(users[:20], 1):
            user_id, username, full_name, joined_date = user_data
            username_display = f"@{username}" if username else "Без username"
            joined_str = joined_date.split()[0] if joined_date else "Неизвестно"
            text += f"{i}. {full_name} ({username_display}) - {joined_str}\n"
        
        if len(users) > 20:
            text += f"\n... и еще {len(users) - 20} пользователей"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    logger.info(f"📨 Получено сообщение: {update.message.text}")
    
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Я не понимаю текстовые сообщения. Используйте команды /start или /check")
        return
    
    if context.user_data.get('awaiting_channel'):
        channel_type = context.user_data.get('channel_type')
        text = update.message.text.strip()
        
        logger.info(f"📨 Обработка канала типа {channel_type}: {text}")
        
        try:
            if channel_type == 'public':
                parts = text.split(' ', 1)
                if len(parts) == 2 and parts[0].startswith('@'):
                    username = parts[0]
                    name = parts[1]
                    url = f"https://t.me/{username.lstrip('@')}"
                    
                    if db.add_subscription_channel(username, url, name, 'public'):
                        await update.message.reply_text(f"✅ *Публичный канал добавлен!*\n\n📺 {name}\n🔗 {url}", parse_mode='Markdown')
                    else:
                        await update.message.reply_text("❌ Ошибка при добавлении")
                else:
                    await update.message.reply_text("❌ Неверный формат. Используйте: @username Название")
            
            elif channel_type == 'private':
                parts = text.split(' ', 1)
                if len(parts) == 2:
                    url = parts[0]
                    name = parts[1]
                    
                    if db.add_subscription_channel(None, url, name, 'private'):
                        await update.message.reply_text(f"✅ *Приватный канал добавлен!*\n\n🔒 {name}\n🔗 {url}", parse_mode='Markdown')
                    else:
                        await update.message.reply_text("❌ Ошибка при добавлении")
                else:
                    await update.message.reply_text("❌ Неверный формат. Используйте: ссылка Название")
            
            elif channel_type == 'referral':
                parts = text.split(' ', 2)
                if len(parts) >= 2:
                    url = parts[0]
                    name = parts[1]
                    description = parts[2] if len(parts) > 2 else ""
                    
                    if db.add_referral_channel(url, name, description):
                        await update.message.reply_text(f"💎 *Финальный канал добавлен!*\n\n📁 {name}\n🔗 {url}", parse_mode='Markdown')
                    else:
                        await update.message.reply_text("❌ Ошибка при добавлении")
                else:
                    await update.message.reply_text("❌ Неверный формат. Используйте: ссылка Название [Описание]")
            
            context.user_data['awaiting_channel'] = False
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки сообщения: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
            context.user_data['awaiting_channel'] = False
    else:
        await update.message.reply_text("Используйте команды:\n/start - начать работу\n/check - проверить подписки\n/admin - панель управления")

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /admin"""
    if update.effective_user.id == ADMIN_ID:
        await show_admin_panel(update, context)
    else:
        await update.message.reply_text("🚫 У вас нет доступа к этой команде")

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /check"""
    db.add_user(update.effective_user.id, update.effective_user.username, update.effective_user.full_name)
    subscription_status = await check_subscriptions(update, context)
    
    if subscription_status["all_subscribed"]:
        await show_success_message(update, context)
    else:
        await update.message.reply_text("🔍 Проверяем подписки...")
        await show_subscription_request(update, context, subscription_status["missing_channels"])

async def set_commands(application: Application):
    """Установка команд бота"""
    commands = [
        BotCommand("start", "🚀 Запустить бота"),
        BotCommand("check", "🔍 Проверить подписку"),
        BotCommand("admin", "⚙️ Панель управления")
    ]
    await application.bot.set_my_commands(commands)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"❌ Ошибка: {context.error}")
    
    if update and update.effective_user:
        try:
            await update.effective_user.send_message("❌ Произошла ошибка. Попробуйте позже.")
        except:
            pass

def main():
    if db is None:
        logger.error("❌ Не удалось инициализировать базу данных. Бот не может быть запущен.")
        return
    
    print("🚀 Запуск бота...")
    print(f"🤖 Токен: {BOT_TOKEN[:10]}...{BOT_TOKEN[-10:]}")
    print(f"👤 Админ: {ADMIN_ID}")
    
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Обработчики команд
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("check", check_command))
        application.add_handler(CommandHandler("admin", admin_command))
        
        # Обработчики кнопок
        application.add_handler(CallbackQueryHandler(button_handler))
        
        # Обработчик текстовых сообщений
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Обработчик ошибок
        application.add_error_handler(error_handler)
        
        # Установка команд бота
        application.post_init = set_commands
        
        # Запуск бота
        logger.info("✅ Бот запущен и готов к работе!")
        print("✅ Бот запущен! Напишите /start в Telegram")
        
        application.run_polling()
        
    except Exception as e:
        logger.error(f"❌ Ошибка запуска: {e}")
        print(f"❌ Критическая ошибка: {e}")

if __name__ == "__main__":
    main()
