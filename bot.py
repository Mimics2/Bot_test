import logging
import sqlite3
import os
import sys
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.error import BadRequest, Forbidden

# Импортируем конфигурацию
try:
    from config import BOT_TOKEN, ADMIN_ID, DB_PATH, TEXTS, BUTTONS, DEBUG, PORT
except ImportError as e:
    print(f"🔴 Ошибка конфига: {e}")
    sys.exit(1)

# Проверка настроек
if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or not BOT_TOKEN:
    print("🔴 ОШИБКА: Установи BOT_TOKEN!")
    sys.exit(1)

if ADMIN_ID == 123456789:
    print("🔴 ОШИБКА: Установи ADMIN_ID!")
    sys.exit(1)

# Логирование
log_level = logging.DEBUG if DEBUG else logging.INFO
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=log_level
)
logger = logging.getLogger(__name__)

logger.info("🤖 Запускаю бота...")

class Database:
    def __init__(self, db_path):
        self.db_path = db_path
        self._ensure_db_directory()
        self.init_db()
    
    def _ensure_db_directory(self):
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def init_db(self):
        tables = [
            '''CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''',
            '''CREATE TABLE IF NOT EXISTS subscription_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_username TEXT,
                channel_url TEXT,
                channel_name TEXT,
                channel_type TEXT DEFAULT 'public',
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''',
            '''CREATE TABLE IF NOT EXISTS confirmed_subscriptions (
                user_id INTEGER,
                channel_id INTEGER,
                confirmed BOOLEAN DEFAULT FALSE,
                confirmed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, channel_id)
            )''',
            '''CREATE TABLE IF NOT EXISTS referral_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_url TEXT NOT NULL,
                channel_name TEXT,
                description TEXT,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )'''
        ]
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                for table_sql in tables:
                    cursor.execute(table_sql)
                conn.commit()
            logger.info("🟢 База готова")
        except Exception as e:
            logger.error(f"🔴 Ошибка БД: {e}")
            raise
    
    def add_user(self, user_id, username, full_name):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)',
                    (user_id, username, full_name)
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"🔴 Ошибка добавления юзера: {e}")
            return False
    
    def add_subscription_channel(self, channel_username, channel_url, channel_name, channel_type='public'):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO subscription_channels (channel_username, channel_url, channel_name, channel_type) VALUES (?, ?, ?, ?)',
                    (channel_username, channel_url, channel_name, channel_type)
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"🔴 Ошибка добавления канала: {e}")
            return False
    
    def get_subscription_channels(self):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM subscription_channels ORDER BY id')
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"🔴 Ошибка получения каналов: {e}")
            return []
    
    def confirm_subscription(self, user_id, channel_id):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT OR REPLACE INTO confirmed_subscriptions (user_id, channel_id, confirmed) VALUES (?, ?, TRUE)',
                    (user_id, channel_id)
                )
                conn.commit()
            logger.info(f"🟢 Подписка подтверждена: user_id={user_id}, channel_id={channel_id}")
            return True
        except Exception as e:
            logger.error(f"🔴 Ошибка подтверждения: {e}")
            return False
    
    def is_subscription_confirmed(self, user_id, channel_id):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT confirmed FROM confirmed_subscriptions WHERE user_id = ? AND channel_id = ?',
                    (user_id, channel_id)
                )
                result = cursor.fetchone()
                confirmed = result[0] if result else False
                return confirmed
        except Exception as e:
            logger.error(f"🔴 Ошибка проверки: {e}")
            return False
    
    def remove_subscription_confirmation(self, user_id, channel_id):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'DELETE FROM confirmed_subscriptions WHERE user_id = ? AND channel_id = ?',
                    (user_id, channel_id)
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"🔴 Ошибка удаления: {e}")
            return False
    
    def add_referral_channel(self, channel_url, channel_name, description=""):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO referral_channels (channel_url, channel_name, description) VALUES (?, ?, ?)',
                    (channel_url, channel_name, description)
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"🔴 Ошибка добавления канала: {e}")
            return False
    
    def get_referral_channels(self):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM referral_channels ORDER BY id')
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"🔴 Ошибка получения каналов: {e}")
            return []
    
    def remove_subscription_channel(self, channel_id):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM subscription_channels WHERE id = ?', (channel_id,))
                cursor.execute('DELETE FROM confirmed_subscriptions WHERE channel_id = ?', (channel_id,))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"🔴 Ошибка удаления: {e}")
            return False
    
    def remove_referral_channel(self, channel_id):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM referral_channels WHERE id = ?', (channel_id,))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"🔴 Ошибка удаления: {e}")
            return False
    
    def get_all_users_count(self):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM users')
                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"🔴 Ошибка подсчета: {e}")
            return 0

# Инициализация БД
try:
    db = Database(DB_PATH)
except Exception as e:
    logger.error(f"🔴 Критическая ошибка БД: {e}")
    db = None

async def check_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка подписок - ПОЛНОСТЬЮ ПЕРЕРАБОТАННАЯ ВЕРСИЯ"""
    if not db:
        return {"all_subscribed": False, "missing_channels": []}
    
    user = update.effective_user
    bot = context.bot
    channels = db.get_subscription_channels()
    
    result = {"all_subscribed": True, "missing_channels": []}
    
    for channel in channels:
        channel_id, channel_username, channel_url, channel_name, channel_type, _ = channel
        
        if channel_type == 'public' and channel_username:
            try:
                clean_username = channel_username.lstrip('@')
                logger.info(f"🔍 Проверяю канал @{clean_username} для пользователя {user.id}")
                
                # Очищаем username от лишних символов
                clean_username = re.sub(r'[^a-zA-Z0-9_]', '', clean_username)
                
                if not clean_username:
                    logger.error(f"❌ Неверный username канала: {channel_username}")
                    result["all_subscribed"] = False
                    result["missing_channels"].append({
                        "id": channel_id,
                        "name": channel_name,
                        "type": "public",
                        "url": channel_url,
                        "accessible": False,
                        "error": "Неверный username канала"
                    })
                    continue
                
                subscribed = False
                channel_accessible = False
                last_error = None
                
                try:
                    # Пытаемся получить чат по username
                    chat = await bot.get_chat(f"@{clean_username}")
                    channel_accessible = True
                    logger.info(f"✅ Чат доступен: {chat.title}")
                    
                    # Проверяем подписку пользователя
                    try:
                        chat_member = await bot.get_chat_member(chat.id, user.id)
                        status = chat_member.status
                        subscribed = status in ['member', 'administrator', 'creator', 'restricted']
                        
                        logger.info(f"📊 Статус пользователя {user.id} в канале {channel_name}: {status}")
                        
                        if not subscribed:
                            logger.info(f"❌ Пользователь {user.id} НЕ подписан на {channel_name}")
                        else:
                            logger.info(f"✅ Пользователь {user.id} подписан на {channel_name}")
                            
                    except BadRequest as e:
                        error_msg = str(e).lower()
                        if "user not found" in error_msg or "user not participant" in error_msg:
                            logger.info(f"❌ Пользователь {user.id} не найден в канале {channel_name}")
                            subscribed = False
                        else:
                            logger.error(f"🔴 Ошибка проверки подписки: {e}")
                            last_error = e
                            subscribed = False
                    
                except BadRequest as e:
                    error_msg = str(e).lower()
                    last_error = e
                    
                    if "chat not found" in error_msg:
                        logger.error(f"❌ Чат @{clean_username} не существует")
                        channel_accessible = False
                    elif "not enough rights" in error_msg:
                        logger.error(f"🔐 Недостаточно прав для проверки канала @{clean_username}")
                        channel_accessible = False
                    else:
                        logger.error(f"🔴 Неизвестная ошибка BadRequest: {e}")
                        channel_accessible = False
                        
                except Forbidden as e:
                    logger.error(f"🚫 Доступ к каналу @{clean_username} запрещен")
                    channel_accessible = False
                    last_error = e
                    
                except Exception as e:
                    logger.error(f"🔴 Неизвестная ошибка при проверке канала: {e}")
                    channel_accessible = False
                    last_error = e
                
                # Обрабатываем результат проверки
                if channel_accessible:
                    if not subscribed:
                        result["all_subscribed"] = False
                        result["missing_channels"].append({
                            "id": channel_id,
                            "name": channel_name,
                            "type": "public",
                            "url": f"https://t.me/{clean_username}",
                            "accessible": True
                        })
                else:
                    # Канал недоступен - считаем что пользователь не подписан
                    result["all_subscribed"] = False
                    error_msg = "Канал недоступен"
                    if last_error:
                        if "chat not found" in str(last_error).lower():
                            error_msg = "Канал не существует"
                        elif "not enough rights" in str(last_error).lower():
                            error_msg = "Бот не имеет прав для проверки"
                    
                    result["missing_channels"].append({
                        "id": channel_id,
                        "name": channel_name,
                        "type": "public",
                        "url": f"https://t.me/{clean_username}",
                        "accessible": False,
                        "error": error_msg
                    })
                    logger.warning(f"🚫 Канал {channel_name} недоступен: {error_msg}")
                    
            except Exception as e:
                logger.error(f"🔴 Критическая ошибка проверки канала {channel_name}: {e}")
                result["all_subscribed"] = False
                result["missing_channels"].append({
                    "id": channel_id,
                    "name": channel_name,
                    "type": "public",
                    "url": f"https://t.me/{clean_username}",
                    "accessible": False,
                    "error": f"Ошибка проверки: {str(e)}"
                })
        
        elif channel_type == 'private':
            is_confirmed = db.is_subscription_confirmed(user.id, channel_id)
            
            if not is_confirmed:
                result["all_subscribed"] = False
                result["missing_channels"].append({
                    "id": channel_id,
                    "name": channel_name,
                    "type": "private", 
                    "url": channel_url,
                    "accessible": True
                })
    
    return result

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт бота"""
    if not db:
        await update.message.reply_text("🔧 Технические работы... Попробуйте позже")
        return
    
    user = update.effective_user
    db.add_user(user.id, user.username, user.full_name)
    
    welcome_text = (
        "🎉 *Добро пожаловать!*\n\n"
        "🤖 *Subscription Checker Bot*\n\n"
        "📋 *Что я умею:*\n"
        "• ✅ Проверять подписки на каналы\n"
        "• 🔓 Открывать доступ к контенту\n"
        "• 🚀 Быстро и удобно работать\n\n"
        "⚡️ Проверяю ваши подписки..."
    )
    
    await update.message.reply_text(welcome_text, parse_mode='Markdown')
    
    subscription_status = await check_subscriptions(update, context)
    
    if subscription_status["all_subscribed"]:
        await show_success_message(update, context)
    else:
        await show_subscription_request(update, context, subscription_status["missing_channels"])

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда проверки подписок"""
    if not db:
        await update.message.reply_text("🔧 Технические работы... Попробуйте позже")
        return
    
    user = update.effective_user
    db.add_user(user.id, user.username, user.full_name)
    
    await update.message.reply_text("🔄 Проверяю подписки...")
    
    subscription_status = await check_subscriptions(update, context)
    
    if subscription_status["all_subscribed"]:
        await show_success_message(update, context)
    else:
        await show_subscription_request(update, context, subscription_status["missing_channels"])

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда админ-панели"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Недостаточно прав")
        return
        
    await show_admin_panel(update, context)

async def show_success_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Успешная проверка"""
    referral_channels = db.get_referral_channels()
    
    if not referral_channels:
        message = "✅ *Все проверки пройдены!*\n\nДоступ к контенту открыт 🎉"
        if update.callback_query:
            await update.callback_query.edit_message_text(message, parse_mode='Markdown')
        else:
            await update.message.reply_text(message, parse_mode='Markdown')
        return
    
    channel = referral_channels[0]
    channel_id, channel_url, channel_name, description, _ = channel
    
    success_text = f"🎉 *Доступ открыт!*\n\n📁 *{channel_name}*\n{description or '🔥 Эксклюзивный контент'}\n\n💎 Приятного использования!"
    
    keyboard = [
        [InlineKeyboardButton("🚀 Перейти к контенту", url=channel_url)],
        [InlineKeyboardButton("🔄 Проверить снова", callback_data="check_subs")]
    ]
    
    if update.effective_user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(success_text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception:
            pass
    else:
        await update.message.reply_text(success_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_subscription_request(update: Update, context: ContextTypes.DEFAULT_TYPE, missing_channels=None):
    """Запрос подписки"""
    if not missing_channels:
        missing_channels = []
    
    keyboard = []
    
    for channel_info in missing_channels:
        if channel_info["type"] == "public":
            if not channel_info.get("accessible", True):
                # Для недоступных каналов показываем информационную кнопку
                keyboard.append([
                    InlineKeyboardButton(
                        f"⚠️ {channel_info['name']} ({channel_info.get('error', 'ошибка')})",
                        callback_data="channel_check_error"
                    )
                ])
            else:
                # Для доступных публичных каналов показываем кнопку подписки
                keyboard.append([
                    InlineKeyboardButton(
                        f"📺 Подписаться: {channel_info['name']}",
                        url=channel_info["url"]
                    )
                ])
        elif channel_info["type"] == "private":
            keyboard.append([
                InlineKeyboardButton(f"🔗 {channel_info['name']}", url=channel_info["url"]),
                InlineKeyboardButton(f"✅ Подтвердить", callback_data=f"confirm_{channel_info['id']}")
            ])
    
    keyboard.append([InlineKeyboardButton("🔄 Проверить подписки", callback_data="check_subs")])
    
    # Добавляем кнопку для админа для проверки каналов
    if update.effective_user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("🔧 Проверить настройки каналов", callback_data="check_channel_settings")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if missing_channels:
        channels_list = ""
        error_channels = []
        
        for channel in missing_channels:
            if channel.get("accessible", True):
                icon = "📺" if channel["type"] == "public" else "🔒"
                status = " (подписка)" if channel["type"] == "public" else " (подтверждение)"
                channels_list += f"{icon} {channel['name']}{status}\n"
            else:
                channels_list += f"⚠️ {channel['name']} ({channel.get('error', 'ошибка проверки')})\n"
                error_channels.append(channel)
        
        request_text = f"📋 *Требуются действия:*\n\n{channels_list}\n🔐 После выполнения нажмите 'Проверить подписки'"
        
        # Добавляем информацию об ошибках для админа
        if update.effective_user.id == ADMIN_ID and error_channels:
            request_text += f"\n\n⚡️ *Для админа:* {len(error_channels)} каналов имеют проблемы с проверкой"
    
    else:
        request_text = "✅ Все проверки пройдены! Доступ открыт."
    
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(request_text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"🔴 Ошибка редактирования сообщения: {e}")
    else:
        await update.message.reply_text(request_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ-панель"""
    if not db:
        error_msg = "🔴 База данных недоступна"
        if update.callback_query:
            await update.callback_query.edit_message_text(error_msg)
        else:
            await update.message.reply_text(error_msg)
        return
    
    total_users = db.get_all_users_count()
    sub_channels = db.get_subscription_channels()
    ref_channels = db.get_referral_channels()
    
    admin_text = (
        f"⚙️ *Панель управления*\n\n"
        f"📊 *Статистика:*\n"
        f"• 👥 Пользователей: {total_users}\n"
        f"• 📺 Каналов для подписки: {len(sub_channels)}\n"
        f"• 💎 Финальных каналов: {len(ref_channels)}\n\n"
        f"🛠 *Управление ботом*"
    )
    
    keyboard = [
        [InlineKeyboardButton("📊 Управление каналами", callback_data="manage_channels")],
        [InlineKeyboardButton("🔄 Проверить подписки", callback_data="check_subs")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(admin_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(admin_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_manage_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Управление каналами"""
    if not db:
        if update.callback_query:
            await update.callback_query.edit_message_text("🔴 База данных недоступна")
        else:
            await update.message.reply_text("🔴 База данных недоступна")
        return
    
    sub_channels = db.get_subscription_channels()
    ref_channels = db.get_referral_channels()
    
    text = (
        f"📊 *Управление каналами*\n\n"
        f"📺 *Каналы для подписки:* {len(sub_channels)}\n"
        f"💎 *Финальные каналы:* {len(ref_channels)}\n\n"
        f"Выберите действие:"
    )
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить публичный канал", callback_data="add_public_channel")],
        [InlineKeyboardButton("➕ Добавить приватный канал", callback_data="add_private_channel")],
        [InlineKeyboardButton("💎 Добавить финальный канал", callback_data="add_referral_channel")]
    ]
    
    if sub_channels:
        keyboard.append([InlineKeyboardButton("🗑️ Удалить канал подписки", callback_data="show_delete_sub")])
    
    if ref_channels:
        keyboard.append([InlineKeyboardButton("🗑️ Удалить финальный канал", callback_data="show_delete_ref")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад в админку", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_delete_subscription_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ каналов для удаления"""
    if not db:
        await update.callback_query.edit_message_text("🔴 База данных недоступна")
        return
    
    channels = db.get_subscription_channels()
    
    if not channels:
        await update.callback_query.edit_message_text("🔴 Нет каналов для удаления")
        return
    
    text = "🗑️ *Выберите канал для удаления:*\n\n"
    
    keyboard = []
    for channel in channels:
        channel_id, _, _, channel_name, channel_type, _ = channel
        type_icon = "🔓" if channel_type == 'public' else "🔒"
        keyboard.append([
            InlineKeyboardButton(f"{type_icon} {channel_name}", callback_data=f"delete_sub_{channel_id}")
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="manage_channels")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_delete_referral_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ финальных каналов для удаления"""
    if not db:
        await update.callback_query.edit_message_text("🔴 База данных недоступна")
        return
    
    channels = db.get_referral_channels()
    
    if not channels:
        await update.callback_query.edit_message_text("🔴 Нет финальных каналов для удаления")
        return
    
    text = "🗑️ *Выберите финальный канал для удаления:*\n\n"
    
    keyboard = []
    for channel in channels:
        channel_id, _, channel_name, _, _ = channel
        keyboard.append([
            InlineKeyboardButton(f"💎 {channel_name}", callback_data=f"delete_ref_{channel_id}")
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="manage_channels")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def check_channel_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка настроек каналов для админа"""
    if not db:
        await update.callback_query.edit_message_text("🔴 База данных недоступна")
        return
    
    channels = db.get_subscription_channels()
    bot = context.bot
    
    check_results = "🔧 *Проверка настроек каналов:*\n\n"
    
    for channel in channels:
        channel_id, channel_username, channel_url, channel_name, channel_type, _ = channel
        
        if channel_type == 'public' and channel_username:
            clean_username = channel_username.lstrip('@')
            check_results += f"📺 *{channel_name}* (@{clean_username})\n"
            
            try:
                # Пытаемся получить информацию о канале
                chat = await bot.get_chat(f"@{clean_username}")
                check_results += "   ✅ Канал существует\n"
                
                # Проверяем права бота
                try:
                    bot_member = await bot.get_chat_member(chat.id, bot.id)
                    if bot_member.status in ['administrator', 'creator']:
                        check_results += "   ✅ Бот - администратор\n"
                        
                        # Проверяем конкретные права
                        if hasattr(bot_member, 'can_restrict_members') and bot_member.can_restrict_members:
                            check_results += "   ✅ Есть права на управление участниками\n"
                        else:
                            check_results += "   ⚠️ Нет прав на управление участниками\n"
                            
                        if hasattr(bot_member, 'can_invite_users') and bot_member.can_invite_users:
                            check_results += "   ✅ Есть права на приглашение\n"
                        else:
                            check_results += "   ⚠️ Нет прав на приглашение\n"
                    else:
                        check_results += "   ❌ Бот НЕ администратор\n"
                        
                except Exception as e:
                    check_results += f"   ❌ Ошибка проверки прав: {e}\n"
                    
            except BadRequest as e:
                if "chat not found" in str(e).lower():
                    check_results += "   ❌ Канал не существует\n"
                elif "not enough rights" in str(e).lower():
                    check_results += "   ❌ Нет доступа к каналу\n"
                else:
                    check_results += f"   ❌ Ошибка: {e}\n"
            except Exception as e:
                check_results += f"   ❌ Ошибка: {e}\n"
            
            check_results += "\n"
    
    check_results += "💡 *Рекомендации:*\n"
    check_results += "• Убедитесь, что бот добавлен как администратор\n"
    check_results += "• Дайте боту права 'Просмотр участников'\n"
    check_results += "• Проверьте username канала в настройках бота\n"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Проверить подписки", callback_data="check_subs")],
        [InlineKeyboardButton("⚙️ Управление каналами", callback_data="manage_channels")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(check_results, reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок"""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    
    if query.data == "check_subs":
        # Сбрасываем подтверждения для приватных каналов при каждой проверке
        channels = db.get_subscription_channels()
        for channel in channels:
            channel_id, _, _, _, channel_type, _ = channel
            if channel_type == 'private':
                db.remove_subscription_confirmation(user.id, channel_id)
        
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
            await query.answer("🔴 Ошибка подтверждения", show_alert=True)
    
    elif query.data == "admin_panel":
        if user.id == ADMIN_ID:
            await show_admin_panel(update, context)
        else:
            await query.answer("🚫 Недостаточно прав", show_alert=True)
    
    elif query.data == "manage_channels":
        if user.id == ADMIN_ID:
            await show_manage_channels(update, context)
        else:
            await query.answer("🚫 Недостаточно прав", show_alert=True)
    
    elif query.data == "show_delete_sub":
        if user.id == ADMIN_ID:
            await show_delete_subscription_channels(update, context)
        else:
            await query.answer("🚫 Недостаточно прав", show_alert=True)
    
    elif query.data == "show_delete_ref":
        if user.id == ADMIN_ID:
            await show_delete_referral_channels(update, context)
        else:
            await query.answer("🚫 Недостаточно прав", show_alert=True)
    
    elif query.data.startswith("delete_sub_"):
        if user.id == ADMIN_ID:
            channel_id = int(query.data.replace("delete_sub_", ""))
            if db.remove_subscription_channel(channel_id):
                await query.answer("✅ Канал удален", show_alert=True)
                await show_manage_channels(update, context)
            else:
                await query.answer("🔴 Ошибка удаления", show_alert=True)
        else:
            await query.answer("🚫 Недостаточно прав", show_alert=True)
    
    elif query.data.startswith("delete_ref_"):
        if user.id == ADMIN_ID:
            channel_id = int(query.data.replace("delete_ref_", ""))
            if db.remove_referral_channel(channel_id):
                await query.answer("✅ Канал удален", show_alert=True)
                await show_manage_channels(update, context)
            else:
                await query.answer("🔴 Ошибка удаления", show_alert=True)
        else:
            await query.answer("🚫 Недостаточно прав", show_alert=True)
    
    elif query.data == "add_public_channel":
        if user.id == ADMIN_ID:
            context.user_data['awaiting_channel'] = True
            context.user_data['channel_type'] = 'public'
            await query.edit_message_text(
                "➕ *Добавление публичного канала*\n\n"
                "📝 *ВАЖНО:* Бот должен быть администратором в канале!\n\n"
                "Введите данные в формате:\n"
                "`@username Название_канала`\n\n"
                "📋 *Пример:*\n"
                "`@my_channel Мой Канал`"
            )
        else:
            await query.answer("🚫 Недостаточно прав", show_alert=True)
    
    elif query.data == "add_private_channel":
        if user.id == ADMIN_ID:
            context.user_data['awaiting_channel'] = True
            context.user_data['channel_type'] = 'private'
            await query.edit_message_text(
                "➕ *Добавление приватного канала*\n\n"
                "⚠️ *ВАЖНО:* Бот не может проверить подписку на приватные каналы!\n\n"
                "Введите данные в формате:\n"
                "`ссылка Название_канала`\n\n"
                "📋 *Пример:*\n"
                "`https://t.me/private_channel Приватный Канал`"
            )
        else:
            await query.answer("🚫 Недостаточно прав", show_alert=True)
    
    elif query.data == "add_referral_channel":
        if user.id == ADMIN_ID:
            context.user_data['awaiting_channel'] = True
            context.user_data['channel_type'] = 'referral'
            await query.edit_message_text(
                "💎 *Добавление финального канала*\n\n"
                "Введите данные в формате:\n"
                "`ссылка Название Описание`\n\n"
                "📋 *Пример:*\n"
                "`https://t.me/premium Премиум Эксклюзивный контент`"
            )
        else:
            await query.answer("🚫 Недостаточно прав", show_alert=True)
    
    elif query.data == "channel_check_error":
        await query.answer(
            "⚠️ Проблема с проверкой этого канала. "
            "Убедитесь, что:\n"
            "• Канал существует\n"
            "• Бот - администратор канала\n"
            "• У бота есть права на просмотр участников", 
            show_alert=True
        )
    
    elif query.data == "check_channel_settings":
        if user.id == ADMIN_ID:
            await check_channel_settings(update, context)
        else:
            await query.answer("🚫 Недостаточно прав", show_alert=True)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик сообщений для добавления каналов"""
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
                        await update.message.reply_text(
                            f"✅ *Публичный канал добавлен!*\n\n"
                            f"📺 {name}\n"
                            f"🔗 {url}\n\n"
                            f"⚠️ *Не забудьте:* Добавить бота как администратора в канал!"
                        )
                        await show_manage_channels(update, context)
                    else:
                        await update.message.reply_text("🔴 Ошибка при добавлении канала")
                else:
                    await update.message.reply_text("❌ Неверный формат. Используйте: @username Название")
            
            elif channel_type == 'private':
                parts = text.split(' ', 1)
                if len(parts) == 2:
                    url = parts[0]
                    name = parts[1]
                    
                    if db.add_subscription_channel(None, url, name, 'private'):
                        await update.message.reply_text(
                            f"✅ *Приватный канал добавлен!*\n\n"
                            f"🔒 {name}\n"
                            f"🔗 {url}\n\n"
                            f"⚠️ Пользователи будут подтверждать подписку вручную"
                        )
                        await show_manage_channels(update, context)
                    else:
                        await update.message.reply_text("🔴 Ошибка при добавлении канала")
                else:
                    await update.message.reply_text("❌ Неверный формат. Используйте: ссылка Название")
            
            elif channel_type == 'referral':
                parts = text.split(' ', 2)
                if len(parts) >= 2:
                    url = parts[0]
                    name = parts[1]
                    description = parts[2] if len(parts) > 2 else "🔥 Эксклюзивный контент"
                    
                    if db.add_referral_channel(url, name, description):
                        await update.message.reply_text(f"💎 *Финальный канал добавлен!*\n\n📁 {name}\n🔗 {url}")
                        await show_manage_channels(update, context)
                    else:
                        await update.message.reply_text("🔴 Ошибка при добавлении канала")
                else:
                    await update.message.reply_text("❌ Неверный формат. Используйте: ссылка Название [Описание]")
            
            # Сбрасываем флаг ожидания
            context.user_data['awaiting_channel'] = False
            
        except Exception as e:
            logger.error(f"🔴 Ошибка обработки сообщения: {e}")
            await update.message.reply_text("🔴 Ошибка при обработке запроса")
            context.user_data['awaiting_channel'] = False

async def set_commands(application: Application):
    """Команды бота"""
    commands = [
        BotCommand("start", "🚀 Запустить бота"),
        BotCommand("admin", "⚙️ Админ-панель"),
        BotCommand("check", "🔄 Проверить подписки")
    ]
    await application.bot.set_my_commands(commands)

def main():
    """Запуск бота"""
    if not db:
        logger.error("🔴 База данных не инициализирована")
        return
    
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Обработчики команд
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("admin", admin_command))
        application.add_handler(CommandHandler("check", check_command))
        
        # Обработчики кнопок
        application.add_handler(CallbackQueryHandler(button_handler))
        
        # Обработчик текстовых сообщений (для добавления каналов)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        application.post_init = set_commands
        
        logger.info("🤖 Бот запущен и готов к работе!")
        application.run_polling()
        
    except Exception as e:
        logger.error(f"🔴 Ошибка запуска: {e}")

if __name__ == "__main__":
    main()
