import logging
import sqlite3
import os
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

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
    """Проверка подписок"""
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
            except Exception as e:
                result["all_subscribed"] = False
                result["missing_channels"].append({
                    "id": channel_id,
                    "name": channel_name,
                    "type": "public",
                    "url": f"https://t.me/{clean_username}"
                })
        
        elif channel_type == 'private':
            is_confirmed = db.is_subscription_confirmed(user.id, channel_id)
            
            if not is_confirmed:
                result["all_subscribed"] = False
                result["missing_channels"].append({
                    "id": channel_id,
                    "name": channel_name,
                    "type": "private", 
                    "url": channel_url
                })
    
    return result

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт бота"""
    if not db:
        await update.message.reply_text("🔧 Техработы... Попробуй позже")
        return
    
    user = update.effective_user
    db.add_user(user.id, user.username, user.full_name)
    
    await update.message.reply_text("👋 Привет! Проверю подписки...")
    
    subscription_status = await check_subscriptions(update, context)
    
    if subscription_status["all_subscribed"]:
        await show_success_message(update, context)
    else:
        await show_subscription_request(update, context, subscription_status["missing_channels"])

async def show_success_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Успешная проверка"""
    referral_channels = db.get_referral_channels()
    
    if not referral_channels:
        message = "✅ Все подписки активны!"
        if update.callback_query:
            await update.callback_query.edit_message_text(message)
        else:
            await update.message.reply_text(message)
        return
    
    channel = referral_channels[0]
    channel_id, channel_url, channel_name, description, _ = channel
    
    success_text = f"🎉 *Доступ открыт!*\n\n📁 {channel_name}\n{description or 'Премиум контент'}"
    
    keyboard = [
        [InlineKeyboardButton("🚀 Перейти", url=channel_url)],
        [InlineKeyboardButton("🔄 Проверить", callback_data="check_subs")]
    ]
    
    if update.effective_user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Админ", callback_data="admin_panel")])
    
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
    
    keyboard.append([InlineKeyboardButton("🔄 Проверить", callback_data="check_subs")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if missing_channels:
        channels_list = ""
        for channel in missing_channels:
            icon = "📺" if channel["type"] == "public" else "🔒"
            channels_list += f"{icon} {channel['name']}\n"
        
        request_text = f"📋 *Нужно подписаться:*\n\n{channels_list}\n🔐 После подписки нажми 'Проверить'"
    else:
        request_text = "📋 Нужно подписаться на каналы"
    
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(request_text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception:
            pass
    else:
        await update.message.reply_text(request_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ-панель"""
    if not db:
        error_msg = "🔴 База недоступна"
        if update.callback_query:
            await update.callback_query.edit_message_text(error_msg)
        else:
            await update.message.reply_text(error_msg)
        return
    
    total_users = db.get_all_users_count()
    sub_channels = db.get_subscription_channels()
    ref_channels = db.get_referral_channels()
    
    admin_text = f"⚙️ *Панель управления*\n\n👥 Пользователей: {total_users}\n📊 Каналов: {len(sub_channels)}\n💎 Финальных: {len(ref_channels)}"
    
    keyboard = [
        [InlineKeyboardButton("📊 Управление каналами", callback_data="manage_channels")],
        [InlineKeyboardButton("🔙 Назад", callback_data="check_subs")]
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
            await update.callback_query.edit_message_text("🔴 База недоступна")
        else:
            await update.message.reply_text("🔴 База недоступна")
        return
    
    sub_channels = db.get_subscription_channels()
    ref_channels = db.get_referral_channels()
    
    text = f"📊 *Управление каналами*\n\n📺 Подписки: {len(sub_channels)}\n💎 Финальные: {len(ref_channels)}"
    
    keyboard = [
        [InlineKeyboardButton("➕ Публичный", callback_data="add_public_channel")],
        [InlineKeyboardButton("➕ Приватный", callback_data="add_private_channel")],
        [InlineKeyboardButton("💎 Финальный", callback_data="add_referral_channel")]
    ]
    
    if sub_channels:
        keyboard.append([InlineKeyboardButton("🗑️ Удалить канал", callback_data="show_delete_sub")])
    
    if ref_channels:
        keyboard.append([InlineKeyboardButton("🗑️ Удалить финальный", callback_data="show_delete_ref")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок"""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    
    if query.data == "check_subs":
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
            await query.answer("✅ Подтверждено!", show_alert=True)
            subscription_status = await check_subscriptions(update, context)
            
            if subscription_status["all_subscribed"]:
                await show_success_message(update, context)
            else:
                await show_subscription_request(update, context, subscription_status["missing_channels"])
        else:
            await query.answer("🔴 Ошибка", show_alert=True)
    
    elif query.data == "admin_panel":
        if user.id == ADMIN_ID:
            await show_admin_panel(update, context)
        else:
            await query.answer("🚫 Нет доступа", show_alert=True)
    
    elif query.data == "manage_channels":
        if user.id == ADMIN_ID:
            await show_manage_channels(update, context)
        else:
            await query.answer("🚫 Нет доступа", show_alert=True)

async def set_commands(application: Application):
    """Команды бота"""
    commands = [
        BotCommand("start", "🚀 Старт"),
        BotCommand("admin", "⚙️ Админка"),
        BotCommand("check", "🔄 Проверить")
    ]
    await application.bot.set_my_commands(commands)

def main():
    """Запуск бота"""
    if not db:
        logger.error("🔴 БД не работает")
        return
    
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("admin", start))
        application.add_handler(CommandHandler("check", start))
        
        application.add_handler(CallbackQueryHandler(button_handler))
        
        application.post_init = set_commands
        
        logger.info("🤖 Бот запущен")
        application.run_polling()
        
    except Exception as e:
        logger.error(f"🔴 Ошибка: {e}")

if __name__ == "__main__":
    main()
