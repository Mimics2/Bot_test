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
    print(f"❌ Ошибка загрузки config.py: {e}")
    sys.exit(1)

# Проверка обязательных настроек
if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or not BOT_TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не настроен!")
    sys.exit(1)

if ADMIN_ID == 123456789:
    print("❌ ОШИБКА: ADMIN_ID не настроен!")
    sys.exit(1)

# Настройка логирования
log_level = logging.DEBUG if DEBUG else logging.INFO
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=log_level
)
logger = logging.getLogger(__name__)

logger.info("🚀 Инициализация бота...")

class Database:
    def __init__(self, db_path):
        self.db_path = db_path
        self._ensure_db_directory()
        self.init_db()
    
    def _ensure_db_directory(self):
        """Создает директорию для БД если нужно"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
    
    def get_connection(self):
        """Соединение с БД"""
        return sqlite3.connect(self.db_path)
    
    def init_db(self):
        """Инициализация таблиц"""
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
            logger.info("✅ База данных инициализирована")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации БД: {e}")
            raise
    
    def add_user(self, user_id, username, full_name):
        """Добавление пользователя"""
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
            logger.error(f"❌ Ошибка добавления пользователя: {e}")
            return False
    
    def add_subscription_channel(self, channel_username, channel_url, channel_name, channel_type='public'):
        """Добавление канала для проверки"""
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
            logger.error(f"❌ Ошибка добавления канала: {e}")
            return False
    
    def get_subscription_channels(self):
        """Получение каналов для проверки"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM subscription_channels ORDER BY id')
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"❌ Ошибка получения каналов: {e}")
            return []
    
    def confirm_subscription(self, user_id, channel_id):
        """Подтверждение подписки"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT OR REPLACE INTO confirmed_subscriptions (user_id, channel_id, confirmed) VALUES (?, ?, TRUE)',
                    (user_id, channel_id)
                )
                conn.commit()
            logger.info(f"✅ Подписка подтверждена: user_id={user_id}, channel_id={channel_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка подтверждения: {e}")
            return False
    
    def is_subscription_confirmed(self, user_id, channel_id):
        """Проверка подтверждения подписки"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT confirmed FROM confirmed_subscriptions WHERE user_id = ? AND channel_id = ?',
                    (user_id, channel_id)
                )
                result = cursor.fetchone()
                confirmed = result[0] if result else False
                logger.info(f"🔍 Проверка подписки: user_id={user_id}, channel_id={channel_id} -> {confirmed}")
                return confirmed
        except Exception as e:
            logger.error(f"❌ Ошибка проверки: {e}")
            return False
    
    def remove_subscription_confirmation(self, user_id, channel_id):
        """Удаление подтверждения подписки"""
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
            logger.error(f"❌ Ошибка удаления подтверждения: {e}")
            return False
    
    def add_referral_channel(self, channel_url, channel_name, description=""):
        """Добавление финального канала"""
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
            logger.error(f"❌ Ошибка добавления финального канала: {e}")
            return False
    
    def get_referral_channels(self):
        """Получение финальных каналов"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM referral_channels ORDER BY id')
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"❌ Ошибка получения финальных каналов: {e}")
            return []
    
    def remove_subscription_channel(self, channel_id):
        """Удаление канала для проверки"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM subscription_channels WHERE id = ?', (channel_id,))
                cursor.execute('DELETE FROM confirmed_subscriptions WHERE channel_id = ?', (channel_id,))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка удаления канала: {e}")
            return False
    
    def remove_referral_channel(self, channel_id):
        """Удаление финального канала"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM referral_channels WHERE id = ?', (channel_id,))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка удаления финального канала: {e}")
            return False
    
    def get_all_users_count(self):
        """Получение количества пользователей"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM users')
                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"❌ Ошибка подсчета пользователей: {e}")
            return 0

# Инициализация базы данных
try:
    db = Database(DB_PATH)
except Exception as e:
    logger.error(f"❌ Критическая ошибка БД: {e}")
    db = None

async def check_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка подписок пользователя"""
    if not db:
        return {"all_subscribed": False, "missing_channels": []}
    
    user = update.effective_user
    bot = context.bot
    channels = db.get_subscription_channels()
    
    result = {
        "all_subscribed": True,
        "missing_channels": []
    }
    
    logger.info(f"🔍 Начинаем проверку подписок для пользователя {user.id}")
    
    for channel in channels:
        channel_id, channel_username, channel_url, channel_name, channel_type, _ = channel
        
        logger.info(f"🔍 Проверяем канал: {channel_name} (тип: {channel_type})")
        
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
                    logger.info(f"❌ Пользователь {user.id} не подписан на публичный канал {channel_name}")
                else:
                    logger.info(f"✅ Пользователь {user.id} подписан на публичный канал {channel_name}")
                    
            except Exception as e:
                logger.error(f"Ошибка проверки публичного канала {channel_username}: {e}")
                result["all_subscribed"] = False
                result["missing_channels"].append({
                    "id": channel_id,
                    "name": channel_name,
                    "type": "public",
                    "url": f"https://t.me/{clean_username}"
                })
        
        elif channel_type == 'private':
            # 🔥 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Для приватных каналов всегда считаем, что пользователь НЕ подписан
            # и требуем ручного подтверждения через кнопку
            confirmed = db.is_subscription_confirmed(user.id, channel_id)
            if not confirmed:
                result["all_subscribed"] = False
                result["missing_channels"].append({
                    "id": channel_id,
                    "name": channel_name,
                    "type": "private",
                    "url": channel_url
                })
                logger.info(f"❌ Пользователь {user.id} не подтвердил приватный канал {channel_name}")
            else:
                logger.info(f"✅ Пользователь {user.id} подтвердил приватный канал {channel_name}")
    
    logger.info(f"🔍 Итог проверки: all_subscribed={result['all_subscribed']}, missing={len(result['missing_channels'])}")
    return result

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда начала работы"""
    if not db:
        await update.message.reply_text("🔧 Сервис временно недоступен. Попробуйте позже.")
        return
    
    user = update.effective_user
    db.add_user(user.id, user.username, user.full_name)
    
    await update.message.reply_text(TEXTS["start"])
    
    # Проверяем подписки
    subscription_status = await check_subscriptions(update, context)
    
    if subscription_status["all_subscribed"]:
        await show_success_message(update, context)
    else:
        await show_subscription_request(update, context, subscription_status["missing_channels"])

async def show_success_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ сообщения об успешной проверке"""
    referral_channels = db.get_referral_channels()
    
    if not referral_channels:
        message = "✅ Вы подписаны на все необходимые каналы."
        if update.callback_query:
            await update.callback_query.edit_message_text(message)
        else:
            await update.message.reply_text(message)
        return
    
    # Берем первый финальный канал
    channel = referral_channels[0]
    channel_id, channel_url, channel_name, description, _ = channel
    
    success_text = TEXTS["success"].format(
        channel_name=channel_name,
        description=description or "📁 Закрытый контент",
        channel_url=channel_url
    )
    
    keyboard = [
        [InlineKeyboardButton("🚀 Перейти к контенту", url=channel_url)],
        [InlineKeyboardButton(BUTTONS["check"], callback_data="check_subs")]
    ]
    
    if update.effective_user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton(BUTTONS["admin"], callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(success_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(success_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_subscription_request(update: Update, context: ContextTypes.DEFAULT_TYPE, missing_channels=None):
    """Показ запроса на подписку"""
    if not missing_channels:
        missing_channels = []
    
    keyboard = []
    
    # Создаем кнопки для каналов
    for channel_info in missing_channels:
        if channel_info["type"] == "public":
            keyboard.append([
                InlineKeyboardButton(
                    f"{BUTTONS['subscribe']} {channel_info['name']}",
                    url=channel_info["url"]
                )
            ])
        elif channel_info["type"] == "private":
            # Для приватных каналов показываем кнопку подтверждения
            keyboard.append([
                InlineKeyboardButton(f"🔗 {channel_info['name']}", url=channel_info["url"]),
                InlineKeyboardButton(f"{BUTTONS['confirm']}", callback_data=f"confirm_{channel_info['id']}")
            ])
    
    keyboard.append([InlineKeyboardButton(BUTTONS["check"], callback_data="check_subs")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if missing_channels:
        channels_list = ""
        for channel in missing_channels:
            icon = "📺" if channel["type"] == "public" else "🔒"
            channels_list += f"{icon} {channel['name']}\n"
        
        request_text = TEXTS["subscription_required"].format(channels_list=channels_list)
    else:
        request_text = "📋 Необходимо подписаться на каналы"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(request_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(request_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ панели администратора"""
    if not db:
        error_msg = "❌ База данных недоступна"
        if update.callback_query:
            await update.callback_query.edit_message_text(error_msg)
        else:
            await update.message.reply_text(error_msg)
        return
    
    total_users = db.get_all_users_count()
    sub_channels = db.get_subscription_channels()
    ref_channels = db.get_referral_channels()
    
    admin_text = TEXTS["admin_welcome"].format(
        total_users=total_users,
        today_checks=0,
        today_new=0,
        subscription_channels=len(sub_channels),
        referral_channels=len(ref_channels)
    )
    
    keyboard = [
        [InlineKeyboardButton(BUTTONS["manage"], callback_data="manage_channels")],
        [InlineKeyboardButton(BUTTONS["back"], callback_data="check_subs")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(admin_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(admin_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_manage_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ управления каналами"""
    if not db:
        if update.callback_query:
            await update.callback_query.edit_message_text("❌ База данных недоступна")
        else:
            await update.message.reply_text("❌ База данных недоступна")
        return
    
    sub_channels = db.get_subscription_channels()
    ref_channels = db.get_referral_channels()
    
    # Формируем списки каналов
    sub_list = "\n".join([f"• {ch[3]} ({'🔓 публичный' if ch[4] == 'public' else '🔒 приватный'})" for ch in sub_channels]) if sub_channels else "❌ Нет каналов"
    ref_list = "\n".join([f"• {ch[2]}" for ch in ref_channels]) if ref_channels else "❌ Нет каналов"
    
    text = TEXTS["manage_channels"].format(
        subscription_channels_list=sub_list,
        referral_channels_list=ref_list
    )
    
    keyboard = [
        [InlineKeyboardButton(BUTTONS["add_public"], callback_data="add_public_channel")],
        [InlineKeyboardButton(BUTTONS["add_private"], callback_data="add_private_channel")],
        [InlineKeyboardButton(BUTTONS["add_final"], callback_data="add_referral_channel")]
    ]
    
    # Добавляем кнопки удаления если есть каналы
    if sub_channels:
        keyboard.append([InlineKeyboardButton(f"{BUTTONS['delete']} канал проверки", callback_data="show_delete_sub")])
    
    if ref_channels:
        keyboard.append([InlineKeyboardButton(f"{BUTTONS['delete']} финальный канал", callback_data="show_delete_ref")])
    
    keyboard.append([InlineKeyboardButton(BUTTONS["back"], callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_delete_subscription_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ каналов для удаления"""
    if not db:
        await update.callback_query.edit_message_text("❌ База данных недоступна")
        return
    
    channels = db.get_subscription_channels()
    
    if not channels:
        await update.callback_query.edit_message_text("❌ Нет каналов для удаления")
        return
    
    text = "🗑️ Выберите канал для удаления:\n\n"
    
    keyboard = []
    for channel in channels:
        channel_id, _, _, channel_name, channel_type, _ = channel
        type_icon = "🔓" if channel_type == 'public' else "🔒"
        keyboard.append([
            InlineKeyboardButton(f"{type_icon} {channel_name}", callback_data=f"delete_sub_{channel_id}")
        ])
    
    keyboard.append([InlineKeyboardButton(BUTTONS["back"], callback_data="manage_channels")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup)

async def show_delete_referral_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ финальных каналов для удаления"""
    if not db:
        await update.callback_query.edit_message_text("❌ База данных недоступна")
        return
    
    channels = db.get_referral_channels()
    
    if not channels:
        await update.callback_query.edit_message_text("❌ Нет финальных каналов для удаления")
        return
    
    text = "🗑️ Выберите финальный канал для удаления:\n\n"
    
    keyboard = []
    for channel in channels:
        channel_id, _, channel_name, _, _ = channel
        keyboard.append([
            InlineKeyboardButton(f"💎 {channel_name}", callback_data=f"delete_ref_{channel_id}")
        ])
    
    keyboard.append([InlineKeyboardButton(BUTTONS["back"], callback_data="manage_channels")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    
    logger.info(f"🔘 Нажата кнопка: {query.data} пользователем {user.id}")
    
    if query.data == "check_subs":
        db.add_user(user.id, user.username, user.full_name)
        subscription_status = await check_subscriptions(update, context)
        
        if subscription_status["all_subscribed"]:
            await show_success_message(update, context)
        else:
            await show_subscription_request(update, context, subscription_status["missing_channels"])
    
    elif query.data.startswith("confirm_"):
        channel_id = int(query.data.replace("confirm_", ""))
        logger.info(f"🔘 Подтверждение канала {channel_id} пользователем {user.id}")
        
        if db.confirm_subscription(user.id, channel_id):
            await query.answer("✅ Подписка подтверждена!", show_alert=True)
            
            # Сразу проверяем все подписки
            subscription_status = await check_subscriptions(update, context)
            logger.info(f"🔍 Статус после подтверждения: {subscription_status}")
            
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
    
    elif query.data == "manage_channels":
        if user.id == ADMIN_ID:
            await show_manage_channels(update, context)
        else:
            await query.answer("🚫 Доступ запрещен", show_alert=True)
    
    elif query.data == "show_delete_sub":
        if user.id == ADMIN_ID:
            await show_delete_subscription_channels(update, context)
        else:
            await query.answer("🚫 Доступ запрещен", show_alert=True)
    
    elif query.data == "show_delete_ref":
        if user.id == ADMIN_ID:
            await show_delete_referral_channels(update, context)
        else:
            await query.answer("🚫 Доступ запрещен", show_alert=True)
    
    elif query.data.startswith("delete_sub_"):
        if user.id == ADMIN_ID:
            channel_id = int(query.data.replace("delete_sub_", ""))
            if db.remove_subscription_channel(channel_id):
                await query.answer("✅ Канал удален", show_alert=True)
                await show_manage_channels(update, context)
            else:
                await query.answer("❌ Ошибка удаления", show_alert=True)
        else:
            await query.answer("🚫 Доступ запрещен", show_alert=True)
    
    elif query.data.startswith("delete_ref_"):
        if user.id == ADMIN_ID:
            channel_id = int(query.data.replace("delete_ref_", ""))
            if db.remove_referral_channel(channel_id):
                await query.answer("✅ Канал удален", show_alert=True)
                await show_manage_channels(update, context)
            else:
                await query.answer("❌ Ошибка удаления", show_alert=True)
        else:
            await query.answer("🚫 Доступ запрещен", show_alert=True)
    
    elif query.data == "add_public_channel":
        if user.id == ADMIN_ID:
            context.user_data['awaiting_channel'] = True
            context.user_data['channel_type'] = 'public'
            await query.edit_message_text(
                "➕ Добавление публичного канала:\n\n"
                "Введите в формате:\n"
                "@username Название_канала\n\n"
                "📝 Пример:\n"
                "@my_channel Мой канал"
            )
        else:
            await query.answer("🚫 Доступ запрещен", show_alert=True)
    
    elif query.data == "add_private_channel":
        if user.id == ADMIN_ID:
            context.user_data['awaiting_channel'] = True
            context.user_data['channel_type'] = 'private'
            await query.edit_message_text(
                "➕ Добавление приватного канала:\n\n"
                "Введите в формате:\n"
                "ссылка Название_канала\n\n"
                "📝 Пример:\n"
                "https://t.me/private_channel Приватный канал"
            )
        else:
            await query.answer("🚫 Доступ запрещен", show_alert=True)
    
    elif query.data == "add_referral_channel":
        if user.id == ADMIN_ID:
            context.user_data['awaiting_channel'] = True
            context.user_data['channel_type'] = 'referral'
            await query.edit_message_text(
                "💎 Добавление финального канала:\n\n"
                "Введите в формате:\n"
                "ссылка Название [Описание]\n\n"
                "📝 Пример:\n"
                "https://t.me/premium Премиум Эксклюзивный контент"
            )
        else:
            await query.answer("🚫 Доступ запрещен", show_alert=True)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений для добавления каналов"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    if context.user_data.get('awaiting_channel'):
        channel_type = context.user_data.get('channel_type')
        text = update.message.text.strip()
        
        logger.info(f"📨 Получено сообщение для добавления канала: {text}")
        
        try:
            if channel_type == 'public':
                parts = text.split(' ', 1)
                if len(parts) == 2 and parts[0].startswith('@'):
                    username = parts[0]
                    name = parts[1]
                    url = f"https://t.me/{username.lstrip('@')}"
                    
                    if db.add_subscription_channel(username, url, name, 'public'):
                        await update.message.reply_text(f"✅ Публичный канал '{name}' добавлен")
                        # Возвращаемся к управлению каналами через callback
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
                        await update.message.reply_text(f"✅ Приватный канал '{name}' добавлен")
                        # Возвращаемся к управлению каналами через callback
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
                    description = parts[2] if len(parts) > 2 else "📁 Закрытый контент"
                    
                    if db.add_referral_channel(url, name, description):
                        await update.message.reply_text(f"💎 Финальный канал '{name}' добавлен")
                        # Возвращаемся к управлению каналами через callback
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
    """Команда для админ-панели"""
    if update.effective_user.id == ADMIN_ID:
        await show_admin_panel(update, context)
    else:
        await update.message.reply_text("🚫 Доступ запрещен")

async def set_commands(application: Application):
    """Установка команд бота"""
    commands = [
        BotCommand("start", "🚀 Начать работу"),
        BotCommand("admin", "⚙️ Панель управления"),
        BotCommand("check", "🔄 Проверить подписки")
    ]
    await application.bot.set_my_commands(commands)

def main():
    """Главная функция"""
    if not db:
        logger.error("❌ Не удалось инициализировать базу данных")
        return
    
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Обработчики команд
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("admin", admin_command))
        application.add_handler(CommandHandler("check", start))
        
        # Обработчики кнопок
        application.add_handler(CallbackQueryHandler(button_handler))
        
        # Обработчик текстовых сообщений
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Установка команд
        application.post_init = set_commands
        
        # Запуск
        logger.info("🚀 Бот запускается...")
        application.run_polling()
        
    except Exception as e:
        logger.error(f"❌ Ошибка запуска: {e}")

if __name__ == "__main__":
    main()
