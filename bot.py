import logging
import sqlite3
import os
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# Импортируем конфигурацию
try:
    from config import BOT_TOKEN, ADMIN_ID, DB_PATH, TEXTS, DEBUG, PORT, WEBHOOK_URL
except ImportError as e:
    print(f"❌ Ошибка загрузки config.py: {e}")
    print("📝 Создайте файл config.py с настройками бота")
    sys.exit(1)

# Проверка обязательных настроек
if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or not BOT_TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не настроен!")
    print("💡 Откройте config.py и замените YOUR_BOT_TOKEN_HERE на реальный токен")
    sys.exit(1)

if ADMIN_ID == 123456789:
    print("❌ ОШИБКА: ADMIN_ID не настроен!")
    print("💡 Откройте config.py и замените 123456789 на ваш Telegram ID")
    sys.exit(1)

# Настройка логирования
log_level = logging.DEBUG if DEBUG else logging.INFO
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=log_level,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

logger.info("🚀 Инициализация адаптивного бота...")
logger.info(f"📁 Путь к БД: {DB_PATH}")
logger.info(f"👤 Admin ID: {ADMIN_ID}")

class UniversalDatabase:
    """Универсальная база данных для любого хостинга"""
    
    def __init__(self, db_path):
        self.db_path = db_path
        self._ensure_db_directory()
        self.init_db()
    
    def _ensure_db_directory(self):
        """Создает директорию для БД если нужно"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            logger.info(f"📁 Создана директория для БД: {db_dir}")
    
    def get_connection(self):
        """Универсальное соединение с БД"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к БД: {e}")
            raise
    
    def init_db(self):
        """Инициализация таблиц"""
        tables = [
            # Пользователи
            '''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                language_code TEXT,
                joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_checks INTEGER DEFAULT 0
            )
            ''',
            # Каналы для проверки
            '''
            CREATE TABLE IF NOT EXISTS subscription_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_username TEXT,
                channel_url TEXT,
                channel_name TEXT NOT NULL,
                channel_type TEXT DEFAULT 'public',
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''',
            # Подтвержденные подписки
            '''
            CREATE TABLE IF NOT EXISTS confirmed_subscriptions (
                user_id INTEGER,
                channel_id INTEGER,
                confirmed BOOLEAN DEFAULT FALSE,
                confirmed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, channel_id)
            )
            ''',
            # Финальные каналы
            '''
            CREATE TABLE IF NOT EXISTS referral_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_url TEXT NOT NULL,
                channel_name TEXT NOT NULL,
                description TEXT,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''',
            # Статистика
            '''
            CREATE TABLE IF NOT EXISTS user_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            '''
        ]
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                for table_sql in tables:
                    cursor.execute(table_sql)
                conn.commit()
            logger.info("✅ База данных инициализирована")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации БД: {e}")
            raise
    
    def add_user(self, user_id, username, full_name, language_code=None):
        """Добавление/обновление пользователя"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO users 
                    (user_id, username, full_name, language_code, last_active, total_checks)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, COALESCE(
                        (SELECT total_checks + 1 FROM users WHERE user_id = ?), 1
                    ))
                ''', (user_id, username, full_name, language_code, user_id))
                
                # Логируем активность
                cursor.execute('''
                    INSERT INTO user_stats (user_id, action) VALUES (?, ?)
                ''', (user_id, 'start' if not self.user_exists(user_id) else 'active'))
                
            logger.debug(f"👤 Пользователь обновлен: {user_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка добавления пользователя: {e}")
            return False
    
    def user_exists(self, user_id):
        """Проверка существования пользователя"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"❌ Ошибка проверки пользователя: {e}")
            return False

    def add_subscription_channel(self, channel_username, channel_url, channel_name, channel_type='public'):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO subscription_channels 
                    (channel_username, channel_url, channel_name, channel_type)
                    VALUES (?, ?, ?, ?)
                ''', (channel_username, channel_url, channel_name, channel_type))
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка добавления канала: {e}")
            return False

    def get_subscription_channels(self):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM subscription_channels ORDER BY id')
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"❌ Ошибка получения каналов: {e}")
            return []

    def confirm_subscription(self, user_id, channel_id):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO confirmed_subscriptions 
                    (user_id, channel_id, confirmed, confirmed_date)
                    VALUES (?, ?, TRUE, CURRENT_TIMESTAMP)
                ''', (user_id, channel_id))
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка подтверждения: {e}")
            return False

    def is_subscription_confirmed(self, user_id, channel_id):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT confirmed FROM confirmed_subscriptions 
                    WHERE user_id = ? AND channel_id = ?
                ''', (user_id, channel_id))
                result = cursor.fetchone()
                return result['confirmed'] if result else False
        except Exception as e:
            logger.error(f"❌ Ошибка проверки подтверждения: {e}")
            return False

    def add_referral_channel(self, channel_url, channel_name, description=""):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO referral_channels (channel_url, channel_name, description)
                    VALUES (?, ?, ?)
                ''', (channel_url, channel_name, description))
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка добавления финального канала: {e}")
            return False

    def get_referral_channels(self):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM referral_channels ORDER BY id')
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"❌ Ошибка получения финальных каналов: {e}")
            return []

    def get_all_users_count(self):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) as count FROM users')
                return cursor.fetchone()['count']
        except Exception as e:
            logger.error(f"❌ Ошибка подсчета пользователей: {e}")
            return 0

    def get_today_stats(self):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) as count FROM user_stats WHERE DATE(timestamp) = DATE("now")')
                today_checks = cursor.fetchone()['count']
                
                cursor.execute('SELECT COUNT(*) as count FROM users WHERE DATE(joined_date) = DATE("now")')
                today_new = cursor.fetchone()['count']
                
                return today_checks, today_new
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return 0, 0

# Инициализация базы данных
try:
    db = UniversalDatabase(DB_PATH)
    logger.info("✅ База данных загружена успешно")
except Exception as e:
    logger.error(f"❌ Критическая ошибка БД: {e}")
    db = None

async def check_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Универсальная проверка подписок"""
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
        channel_id = channel['id']
        channel_username = channel['channel_username']
        channel_url = channel['channel_url']
        channel_name = channel['channel_name']
        channel_type = channel['channel_type']
        
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
    """Главная команда бота"""
    if not db:
        await update.message.reply_text("🔧 Сервис временно недоступен. Попробуйте позже.")
        return
    
    user = update.effective_user
    
    # Регистрируем пользователя
    success = db.add_user(user.id, user.username, user.full_name, user.language_code)
    
    if not success:
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте снова.")
        return
    
    # Приветственное сообщение
    await update.message.reply_text(TEXTS["start"], parse_mode='Markdown')
    
    # Проверяем подписки
    subscription_status = await check_subscriptions(update, context)
    
    if subscription_status["all_subscribed"]:
        await show_success_message(update, context)
    else:
        await show_subscription_request(update, context, subscription_status["missing_channels"])

async def show_success_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ успешного доступа"""
    referral_channels = db.get_referral_channels()
    
    if not referral_channels:
        message = "🎉 *Поздравляем! Вы подписаны на все каналы!*\n\n💫 Скоро здесь появится эксклюзивный контент!"
        if update.callback_query:
            await update.callback_query.edit_message_text(message, parse_mode='Markdown')
        else:
            await update.message.reply_text(message, parse_mode='Markdown')
        return
    
    channel = referral_channels[0]
    success_text = TEXTS["success"].format(
        channel_name=channel['channel_name'],
        description=channel.get('description', 'Эксклюзивный контент'),
        channel_url=channel['channel_url']
    )
    
    keyboard = [
        [InlineKeyboardButton(f"🚀 Перейти в {channel['channel_name']}", url=channel['channel_url'])],
        [InlineKeyboardButton("🔄 Проверить подписки", callback_data="check_subs")],
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
    """Запрос на подписку"""
    keyboard = []
    
    for channel_info in missing_channels:
        if channel_info["type"] == "public":
            keyboard.append([
                InlineKeyboardButton(
                    f"📺 Подписаться на {channel_info['name']}",
                    url=channel_info["url"]
                )
            ])
        elif channel_info["type"] == "private":
            keyboard.append([
                InlineKeyboardButton(
                    f"🔗 Перейти в {channel_info['name']}",
                    url=channel_info["url"]
                ),
                InlineKeyboardButton(
                    f"✅ Подтвердить {channel_info['name']}",
                    callback_data=f"confirm_{channel_info['id']}"
                )
            ])
    
    keyboard.append([InlineKeyboardButton("🔄 Проверить подписки", callback_data="check_subs")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if missing_channels:
        public_channels = [ch["name"] for ch in missing_channels if ch["type"] == "public"]
        private_channels = [ch["name"] for ch in missing_channels if ch["type"] == "private"]
        
        channels_list = ""
        if public_channels:
            channels_list += "📺 *Публичные каналы:*\n"
            for channel in public_channels:
                channels_list += f"• {channel}\n"
        
        if private_channels:
            if public_channels:
                channels_list += "\n"
            channels_list += "🔐 *Приватные каналы:*\n"
            for channel in private_channels:
                channels_list += f"• {channel}\n"
            channels_list += "\n💡 *После вступления нажмите 'Подтвердить'*"
        
        request_text = TEXTS["subscription_required"].format(channels_list=channels_list)
    else:
        request_text = "📋 Для доступа необходимо подписаться на каналы"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(request_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(request_text, reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок"""
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
            await query.answer("🚫 Доступ запрещен", show_alert=True)

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Панель управления"""
    if not db:
        error_msg = "❌ База данных недоступна"
        if update.callback_query:
            await update.callback_query.edit_message_text(error_msg)
        else:
            await update.message.reply_text(error_msg)
        return
    
    total_users = db.get_all_users_count()
    today_checks, today_new = db.get_today_stats()
    sub_channels = db.get_subscription_channels()
    ref_channels = db.get_referral_channels()
    
    admin_text = TEXTS["admin_welcome"].format(
        total_users=total_users,
        today_checks=today_checks,
        today_new=today_new,
        subscription_channels=len(sub_channels),
        referral_channels=len(ref_channels)
    )
    
    keyboard = [
        [InlineKeyboardButton("📺 Управление каналами", callback_data="manage_channels")],
        [InlineKeyboardButton("🔄 Обновить статистику", callback_data="admin_panel")],
        [InlineKeyboardButton("◀️ Назад", callback_data="check_subs")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(admin_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(admin_text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда админа"""
    if update.effective_user.id == ADMIN_ID:
        await show_admin_panel(update, context)
    else:
        await update.message.reply_text("🚫 У вас нет доступа к этой команде")

async def set_commands(application: Application):
    """Установка команд меню"""
    commands = [
        BotCommand("start", "🚀 Запустить бота"),
        BotCommand("check", "🔍 Проверить подписки"),
        BotCommand("admin", "⚙️ Панель управления (админ)")
    ]
    await application.bot.set_my_commands(commands)

def main():
    """Главная функция запуска"""
    if not db:
        logger.error("❌ Не удалось инициализировать базу данных")
        return
    
    try:
        # Создаем приложение
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Обработчики команд
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("admin", admin_command))
        application.add_handler(CommandHandler("check", start))  # Алиас для start
        
        # Обработчики кнопок
        application.add_handler(CallbackQueryHandler(button_handler))
        
        # Установка команд
        application.post_init = set_commands
        
        # Определяем режим запуска
        is_cloud = any(var in os.environ for var in ['RAILWAY_STATIC_URL', 'DYNO', 'VERCEL'])
        
        if is_cloud and WEBHOOK_URL:
            # Webhook режим для облачных хостингов
            logger.info(f"🌐 Запуск в WEBHOOK режиме на порту {PORT}")
            logger.info(f"🔗 Webhook URL: {WEBHOOK_URL}")
            
            async def set_webhook(app):
                await app.bot.set_webhook(WEBHOOK_URL)
            
            application.run_webhook(
                listen="0.0.0.0",
                port=PORT,
                webhook_url=WEBHOOK_URL,
                secret_token='BOT_SECRET_TOKEN'
            )
        else:
            # Polling режим для локальной разработки
            logger.info("💻 Запуск в POLLING режиме")
            application.run_polling()
            
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
