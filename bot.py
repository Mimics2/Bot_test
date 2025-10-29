import logging
import sqlite3
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from datetime import datetime

# === НАСТРОЙКИ ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
DB_PATH = "/tmp/bot.db"

# Проверка переменных
if not BOT_TOKEN:
    logging.error("❌ BOT_TOKEN не найден!")
    exit(1)

if ADMIN_ID == 0:
    logging.error("❌ ADMIN_ID не настроен!")
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
        
        # Пользователи с улучшенной структурой
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
        
        # Каналы для проверки
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
        
        # Подтвержденные подписки
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS confirmed_subscriptions (
                user_id INTEGER,
                channel_id INTEGER,
                confirmed BOOLEAN DEFAULT FALSE,
                confirmed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, channel_id)
            )
        ''')
        
        # Финальные каналы
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS referral_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_url TEXT NOT NULL,
                channel_name TEXT,
                description TEXT,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Статистика проверок
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
        """Добавление пользователя с обновлением активности"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Проверяем существующего пользователя
            cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
            existing_user = cursor.fetchone()
            
            if existing_user:
                # Обновляем последнюю активность
                cursor.execute('''
                    UPDATE users 
                    SET last_active = CURRENT_TIMESTAMP, total_checks = total_checks + 1 
                    WHERE user_id = ?
                ''', (user_id,))
                logger.info(f"📊 Обновлен пользователь: {user_id} ({username})")
            else:
                # Добавляем нового пользователя
                cursor.execute('''
                    INSERT INTO users (user_id, username, full_name, last_active, total_checks)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP, 1)
                ''', (user_id, username, full_name))
                logger.info(f"👤 Новый пользователь: {user_id} ({username})")
            
            # Обновляем ежедневную статистику
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
        """Получение статистики пользователя"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT total_checks, joined_date, last_active 
                FROM users WHERE user_id = ?
            ''', (user_id,))
            result = cursor.fetchone()
            conn.close()
            return result
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return None

    def get_all_users_count(self):
        """Получение общего количества пользователей"""
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
        """Статистика за сегодня"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM user_stats WHERE check_date = DATE('now')
            ''')
            today_checks = cursor.fetchone()[0]
            
            cursor.execute('''
                SELECT COUNT(*) FROM users WHERE DATE(joined_date) = DATE('now')
            ''')
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
    """Упрощенная проверка подписок - как в старой версии"""
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
            if channel_username:
                try:
                    clean_username = channel_username.lstrip('@')
                    chat_member = await bot.get_chat_member(f"@{clean_username}", user.id)
                    actually_subscribed = chat_member.status in ['member', 'administrator', 'creator']
                    
                    if actually_subscribed:
                        db.confirm_subscription(user.id, channel_id)
                    else:
                        db.remove_subscription_confirmation(user.id, channel_id)
                        result["all_subscribed"] = False
                        result["missing_channels"].append({
                            "id": channel_id,
                            "name": channel_name,
                            "type": "private",
                            "url": channel_url
                        })
                        
                except Exception as e:
                    confirmed = db.is_subscription_confirmed(user.id, channel_id)
                    if not confirmed:
                        result["all_subscribed"] = False
                        result["missing_channels"].append({
                            "id": channel_id,
                            "name": channel_name,
                            "type": "private",
                            "url": channel_url
                        })
            else:
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
    """🎪 КРАСИВОЕ ПРИВЕТСТВИЕ"""
    if db is None:
        await update.message.reply_text("🔧 Сервис временно недоступен. Попробуйте позже.")
        return
        
    user = update.effective_user
    
    # Добавляем/обновляем пользователя
    success = db.add_user(user.id, user.username, user.full_name)
    
    if not success:
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте снова.")
        return

    # Красивое приветствие
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
    
    # Проверяем подписки
    subscription_status = await check_subscriptions(update, context)
    
    if subscription_status["all_subscribed"]:
        await show_success_message(update, context)
    else:
        await show_subscription_request(update, context, subscription_status["missing_channels"])

async def show_success_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎉 КРАСИВОЕ СООБЩЕНИЕ ОБ УСПЕХЕ"""
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
    
    # Получаем первую реферальную ссылку
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

⚡ *Нажмите на кнопку ниже для перехода*
    """
    
    keyboard = [
        [InlineKeyboardButton(f"🚀 Перейти в {channel_name}", url=channel_url)],
        [InlineKeyboardButton("🔄 Проверить подписку", callback_data="check_subs")],
        [InlineKeyboardButton("📊 Статистика", callback_data="user_stats")]
    ]
    
    if update.effective_user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Панель управления", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(success_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(success_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_subscription_request(update: Update, context: ContextTypes.DEFAULT_TYPE, missing_channels=None):
    """📋 КРАСИВЫЙ ЗАПРОС НА ПОДПИСКУ"""
    keyboard = []
    
    # Создаем красивые кнопки
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
                    f"✅ Подтвердить {channel_info['name']}",
                    callback_data=f"confirm_{channel_info['id']}"
                )
            ])
    
    keyboard.append([InlineKeyboardButton("🔄 Проверить все подписки", callback_data="check_subs")])
    keyboard.append([InlineKeyboardButton("📊 Моя статистика", callback_data="user_stats")])
    
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

async def show_user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ статистики пользователя"""
    user = update.effective_user
    stats = db.get_user_stats(user.id)
    
    if not stats:
        stats_text = "📊 *Статистика пока недоступна*"
    else:
        total_checks, joined_date, last_active = stats
        joined_str = joined_date.split()[0] if joined_date else "Неизвестно"
        last_active_str = last_active.split()[0] if last_active else "Неизвестно"
        
        stats_text = f"""
📊 *ВАША СТАТИСТИКА*

👤 *Пользователь:* {user.first_name}
🆔 *ID:* `{user.id}`
📅 *Дата регистрации:* {joined_str}
🕐 *Последняя активность:* {last_active_str}
🔢 *Всего проверок:* {total_checks}

✨ *Спасибо, что используете нашего бота!*
        """
    
    keyboard = [[InlineKeyboardButton("🔄 Назад", callback_data="check_subs")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обновленная админ-панель со статистикой"""
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
⚙️ *ПАНЕЛЬ УПРАВЛЕНИЯ* ⚙️

📈 *СТАТИСТИКА:*
• 👥 Всего пользователей: *{total_users}*
• 🔄 Проверок сегодня: *{today_checks}*
• 🆕 Новых сегодня: *{today_new}*
• 📺 Каналов для проверки: *{len(sub_channels)}*
• 💎 Финальных каналов: *{len(ref_channels)}*

🛠 *ДОСТУПНЫЕ ДЕЙСТВИЯ:*
    """
    
    keyboard = [
        [InlineKeyboardButton("📺 Управление каналами", callback_data="manage_channels")],
        [InlineKeyboardButton("📊 Подробная статистика", callback_data="detailed_stats")],
        [InlineKeyboardButton("👥 Список пользователей", callback_data="users_list")],
        [InlineKeyboardButton("◀️ Назад", callback_data="check_subs")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(admin_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(admin_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_detailed_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подробная статистика для админа"""
    if update.effective_user.id != ADMIN_ID:
        await update.callback_query.answer("🚫 Нет доступа", show_alert=True)
        return
        
    total_users = db.get_all_users_count()
    today_checks, today_new = db.get_today_stats()
    all_users = db.get_all_users()
    
    # Статистика по последним пользователям
    recent_users = all_users[:10]  # Последние 10 пользователей
    
    stats_text = f"""
📊 *ДЕТАЛЬНАЯ СТАТИСТИКА*

👥 *Всего пользователей:* {total_users}
🔄 *Проверок сегодня:* {today_checks}
🆕 *Новых сегодня:* {today_new}

📋 *Последние пользователи:*
"""
    
    for user in recent_users:
        user_id, username, full_name, joined_date = user
        username_display = f"@{username}" if username else "Без username"
        joined_str = joined_date.split()[0] if joined_date else "Неизвестно"
        stats_text += f"• {full_name} ({username_display}) - {joined_str}\n"
    
    if not recent_users:
        stats_text += "• Пользователей пока нет\n"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_manage_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Управление каналами"""
    if update.effective_user.id != ADMIN_ID:
        await update.callback_query.answer("🚫 Нет доступа", show_alert=True)
        return
        
    sub_channels = db.get_subscription_channels()
    ref_channels = db.get_referral_channels()
    
    text = f"""
📊 *Управление каналами*

📺 *Каналы для подписки ({len(sub_channels)}):*
"""
    
    for channel in sub_channels:
        channel_id, username, url, name, channel_type, _ = channel
        type_icon = "🔓" if channel_type == 'public' else "🔒"
        text += f"{type_icon} {name} (@{username})\n"
    
    text += f"\n💎 *Финальные каналы ({len(ref_channels)}):*\n"
    
    for channel in ref_channels:
        channel_id, url, name, description, _ = channel
        text += f"💎 {name}\n"
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить публичный канал", callback_data="add_public_channel")],
        [InlineKeyboardButton("➕ Добавить приватный канал", callback_data="add_private_channel")],
        [InlineKeyboardButton("💎 Добавить финальный канал", callback_data="add_referral_channel")]
    ]
    
    if sub_channels:
        keyboard.append([InlineKeyboardButton("🗑 Удалить канал подписки", callback_data="show_delete_sub")])
    
    if ref_channels:
        keyboard.append([InlineKeyboardButton("🗑 Удалить финальный канал", callback_data="show_delete_ref")])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    
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
    
    elif query.data == "user_stats":
        await show_user_stats(update, context)
    
    elif query.data == "detailed_stats":
        await show_detailed_stats(update, context)
    
    elif query.data == "manage_channels":
        if user.id == ADMIN_ID:
            await show_manage_channels(update, context)
        else:
            await query.answer("🚫 У вас нет доступа", show_alert=True)
    
    elif query.data == "add_public_channel":
        if user.id == ADMIN_ID:
            context.user_data['awaiting_channel'] = True
            context.user_data['channel_type'] = 'public'
            await query.edit_message_text(
                "➕ **Добавить публичный канал**\n\nВведите в формате:\n`@username Название`\n\n**Пример:**\n`@my_channel Мой канал`",
                parse_mode='Markdown'
            )
        else:
            await query.answer("🚫 У вас нет доступа", show_alert=True)
    
    elif query.data == "add_private_channel":
        if user.id == ADMIN_ID:
            context.user_data['awaiting_channel'] = True
            context.user_data['channel_type'] = 'private'
            await query.edit_message_text(
                "➕ **Добавить канал по ссылке**\n\nВведите в формате:\n`ссылка Название`\n\n**Пример:**\n`https://t.me/my_channel Мой канал`",
                parse_mode='Markdown'
            )
        else:
            await query.answer("🚫 У вас нет доступа", show_alert=True)
    
    elif query.data == "add_referral_channel":
        if user.id == ADMIN_ID:
            context.user_data['awaiting_channel'] = True
            context.user_data['channel_type'] = 'referral'
            await query.edit_message_text(
                "💎 **Добавить финальный канал**\n\nВведите в формате:\n`ссылка Название Описание`\n\n**Пример:**\n`https://t.me/final_channel Основной канал Эксклюзивный контент`",
                parse_mode='Markdown'
            )
        else:
            await query.answer("🚫 У вас нет доступа", show_alert=True)
    
    elif query.data.startswith("delete_sub_"):
        if user.id == ADMIN_ID:
            channel_id = int(query.data.replace("delete_sub_", ""))
            if db.remove_subscription_channel(channel_id):
                await query.answer("✅ Канал удален!", show_alert=True)
                await show_manage_channels(update, context)
            else:
                await query.answer("❌ Ошибка при удалении!", show_alert=True)
        else:
            await query.answer("🚫 У вас нет доступа", show_alert=True)
    
    elif query.data.startswith("delete_ref_"):
        if user.id == ADMIN_ID:
            channel_id = int(query.data.replace("delete_ref_", ""))
            if db.remove_referral_channel(channel_id):
                await query.answer("✅ Канал удален!", show_alert=True)
                await show_manage_channels(update, context)
            else:
                await query.answer("❌ Ошибка при удалении!", show_alert=True)
        else:
            await query.answer("🚫 У вас нет доступа", show_alert=True)
    
    elif query.data == "show_delete_sub":
        if user.id == ADMIN_ID:
            channels = db.get_subscription_channels()
            if not channels:
                await query.answer("❌ Нет каналов для удаления", show_alert=True)
                return
                
            keyboard = []
            for channel in channels:
                channel_id, username, url, name, channel_type, _ = channel
                type_icon = "🔓" if channel_type == 'public' else "🔒"
                keyboard.append([InlineKeyboardButton(f"{type_icon} {name}", callback_data=f"delete_sub_{channel_id}")])
            
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="manage_channels")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text("🗑 *Выберите канал для удаления:*", reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await query.answer("🚫 У вас нет доступа", show_alert=True)
    
    elif query.data == "show_delete_ref":
        if user.id == ADMIN_ID:
            channels = db.get_referral_channels()
            if not channels:
                await query.answer("❌ Нет каналов для удаления", show_alert=True)
                return
                
            keyboard = []
            for channel in channels:
                channel_id, url, name, description, _ = channel
                keyboard.append([InlineKeyboardButton(f"💎 {name}", callback_data=f"delete_ref_{channel_id}")])
            
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="manage_channels")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text("🗑 *Выберите финальный канал для удаления:*", reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await query.answer("🚫 У вас нет доступа", show_alert=True)
    
    elif query.data == "users_list":
        if user.id == ADMIN_ID:
            users = db.get_all_users()
            if not users:
                await query.edit_message_text("👥 *Пользователи не найдены*", parse_mode='Markdown')
                return
                
            users_text = "👥 *Список пользователей:*\n\n"
            for i, user_data in enumerate(users[:50], 1):  # Ограничиваем 50 пользователями
                user_id, username, full_name, joined_date = user_data
                username_display = f"@{username}" if username else "Без username"
                joined_str = joined_date.split()[0] if joined_date else "Неизвестно"
                users_text += f"{i}. {full_name} ({username_display}) - {joined_str}\n"
            
            if len(users) > 50:
                users_text += f"\n... и еще {len(users) - 50} пользователей"
            
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(users_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await query.answer("🚫 У вас нет доступа", show_alert=True)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений для добавления каналов"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    if context.user_data.get('awaiting_channel'):
        channel_type = context.user_data.get('channel_type')
        text = update.message.text.strip()
        
        try:
            if channel_type == 'public':
                parts = text.split(' ', 1)
                if len(parts) == 2 and parts[0].startswith('@'):
                    username = parts[0]
                    name = parts[1]
                    url = f"https://t.me/{username.lstrip('@')}"
                    
                    if db.add_subscription_channel(username, url, name, 'public'):
                        await update.message.reply_text(f"✅ *Публичный канал добавлен!*\n\n📺 {name}\n🔗 {url}", parse_mode='Markdown')
                        await show_manage_channels(update, context)
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
                        await show_manage_channels(update, context)
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
                        await show_manage_channels(update, context)
                    else:
                        await update.message.reply_text("❌ Ошибка при добавлении")
                else:
                    await update.message.reply_text("❌ Неверный формат. Используйте: ссылка Название [Описание]")
            
            # Сбрасываем флаг ожидания
            context.user_data['awaiting_channel'] = False
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки сообщения: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
            context.user_data['awaiting_channel'] = False

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await show_admin_panel(update, context)
    else:
        await update.message.reply_text("🚫 У вас нет доступа к этой команде")

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для проверки подписки"""
    db.add_user(update.effective_user.id, update.effective_user.username, update.effective_user.full_name)
    subscription_status = await check_subscriptions(update, context)
    
    if subscription_status["all_subscribed"]:
        await show_success_message(update, context)
    else:
        await update.message.reply_text("❌ Вы не подписаны на все необходимые каналы!")
        await show_subscription_request(update, context, subscription_status["missing_channels"])

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для просмотра статистики"""
    await show_user_stats(update, context)

async def add_final_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для быстрого добавления финальной ссылки"""
    user = update.effective_user
    
    if user.id != ADMIN_ID:
        await update.message.reply_text("🚫 *У вас нет доступа к этой команде*", parse_mode='Markdown')
        return
        
    if not context.args or len(context.args) < 2:
        help_text = """
📝 *Добавление финальной ссылки*

💡 *Использование:*
`/add_final "Название канала" "Описание" ссылка`

✨ *Пример:*
`/add_final "Premium Content" "Эксклюзивные материалы" https://t.me/your_channel`

🎯 *Или просто:*  
`/add_final "Мой канал" https://t.me/link`
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
        return
    
    # Обрабатываем аргументы
    args = context.args
    channel_name = args[0]
    
    # Проверяем формат ввода
    if len(args) == 2:
        # Формат: /add_final "Название" ссылка
        channel_url = args[1]
        description = ""
    else:
        # Формат: /add_final "Название" "Описание" ссылка
        description = args[1]
        channel_url = args[2]
    
    # Проверяем валидность ссылки
    if not (channel_url.startswith('https://t.me/') or channel_url.startswith('t.me/')):
        await update.message.reply_text("❌ *Ссылка должна вести на Telegram (t.me/...)*", parse_mode='Markdown')
        return
    
    # Добавляем канал
    if db.add_referral_channel(channel_url, channel_name, description):
        success_text = f"""
✅ *Финальная ссылка добавлена!*

🏷 *Название:* {channel_name}
📝 *Описание:* {description or "Не указано"}
🔗 *Ссылка:* {channel_url}

🎉 *Теперь пользователи будут получать эту ссылку после проверки подписок!*
        """
        await update.message.reply_text(success_text, parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ *Ошибка при добавлении ссылки*", parse_mode='Markdown')

async def set_commands(application: Application):
    """Установка команд бота"""
    commands = [
        BotCommand("start", "🚀 Запустить бота"),
        BotCommand("check", "🔍 Проверить подписку"),
        BotCommand("stats", "📊 Моя статистика"),
        BotCommand("admin", "⚙️ Панель управления"),
        BotCommand("add_final", "💎 Добавить финальную ссылку (админ)")
    ]
    await application.bot.set_my_commands(commands)

def main():
    if db is None:
        logger.error("❌ Не удалось инициализировать базу данных. Бот не может быть запущен.")
        return
        
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("check", check_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("add_final", add_final_link_command))
    
    # Обработчики кнопок
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Установка команд бота
    application.post_init = set_commands
    
    # Запуск бота
    logger.info("🚀 Бот запускается...")
    application.run_polling()

if __name__ == "__main__":
    main()
