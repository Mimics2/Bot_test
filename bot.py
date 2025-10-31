import logging
import sqlite3
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.error import BadRequest, Forbidden

# ===== КОНФИГУРАЦИЯ =====
BOT_TOKEN = "7557745613:AAFTpWsCJ2bZMqD6GDwTynnqA8Nc-mRF1Rs"
ADMIN_ID = 6646433980
DB_PATH = "bot_database.db"

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

print("🚀 Инициализация бота...")

# ===== БАЗА ДАННЫХ =====
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
                joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                url TEXT,
                name TEXT,
                channel_type TEXT DEFAULT 'public',
                telegram_chat_id TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER,
                channel_id INTEGER,
                confirmed BOOLEAN DEFAULT FALSE,
                PRIMARY KEY (user_id, channel_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS final_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                name TEXT,
                description TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✅ База данных инициализирована")
    
    def add_user(self, user_id, username, full_name):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                'INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)',
                (user_id, username, full_name)
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления пользователя: {e}")
            return False
    
    def add_channel(self, username, url, name, channel_type='public', telegram_chat_id=None):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO channels (username, url, name, channel_type, telegram_chat_id) VALUES (?, ?, ?, ?, ?)',
                (username, url, name, channel_type, telegram_chat_id)
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления канала: {e}")
            return False
    
    def get_channels(self):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM channels ORDER BY id')
            channels = cursor.fetchall()
            conn.close()
            return channels
        except Exception as e:
            logger.error(f"Ошибка получения каналов: {e}")
            return []
    
    def add_final_channel(self, url, name, description=""):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO final_channels (url, name, description) VALUES (?, ?, ?)',
                (url, name, description)
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления финального канала: {e}")
            return False
    
    def get_final_channels(self):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM final_channels ORDER BY id')
            channels = cursor.fetchall()
            conn.close()
            return channels
        except Exception as e:
            logger.error(f"Ошибка получения финальных каналов: {e}")
            return []
    
    def confirm_subscription(self, user_id, channel_id):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                'INSERT OR REPLACE INTO subscriptions (user_id, channel_id, confirmed) VALUES (?, ?, TRUE)',
                (user_id, channel_id)
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Ошибка подтверждения подписки: {e}")
            return False
    
    def is_subscribed(self, user_id, channel_id):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                'SELECT confirmed FROM subscriptions WHERE user_id = ? AND channel_id = ?',
                (user_id, channel_id)
            )
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else False
        except Exception as e:
            logger.error(f"Ошибка проверки подписки: {e}")
            return False
    
    def get_user_count(self):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM users')
            result = cursor.fetchone()[0]
            conn.close()
            return result
        except Exception as e:
            logger.error(f"Ошибка подсчета пользователей: {e}")
            return 0
    
    def remove_channel(self, channel_id):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('DELETE FROM channels WHERE id = ?', (channel_id,))
            cursor.execute('DELETE FROM subscriptions WHERE channel_id = ?', (channel_id,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления канала: {e}")
            return False
    
    def remove_final_channel(self, channel_id):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('DELETE FROM final_channels WHERE id = ?', (channel_id,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления финального канала: {e}")
            return False

# Инициализация базы данных
db = Database(DB_PATH)

# ===== УЛУЧШЕННАЯ ПРОВЕРКА ПОДПИСОК =====
async def check_user_subscriptions(user_id, bot):
    """Проверка подписок пользователя с правильным поиском каналов"""
    channels = db.get_channels()
    missing_channels = []
    all_subscribed = True
    
    for channel in channels:
        channel_id, username, url, name, channel_type, telegram_chat_id = channel
        
        if channel_type == 'public':
            try:
                subscribed = False
                
                # 🔧 СПОСОБ 1: Поиск по username (самый надежный)
                if username and username.startswith('@'):
                    try:
                        clean_username = username.lstrip('@')
                        logger.info(f"🔍 Проверяем канал '{name}' по username: @{clean_username}")
                        
                        # Получаем информацию о канале
                        chat = await bot.get_chat(f"@{clean_username}")
                        logger.info(f"✅ Найден канал: {chat.title} (ID: {chat.id})")
                        
                        # Проверяем подписку пользователя
                        chat_member = await bot.get_chat_member(chat.id, user_id)
                        subscribed = chat_member.status in ['member', 'administrator', 'creator']
                        
                        logger.info(f"📊 Пользователь {user_id} подписан на '{name}': {subscribed}")
                        
                    except BadRequest as e:
                        logger.error(f"❌ Ошибка при проверке по username @{clean_username}: {e}")
                        
                        # 🔧 СПОСОБ 2: Пробуем по ссылке (если есть telegram_chat_id)
                        if telegram_chat_id:
                            try:
                                logger.info(f"🔄 Пробуем проверку по chat_id: {telegram_chat_id}")
                                chat_member = await bot.get_chat_member(telegram_chat_id, user_id)
                                subscribed = chat_member.status in ['member', 'administrator', 'creator']
                                logger.info(f"✅ Проверка по chat_id успешна: {subscribed}")
                            except BadRequest as e2:
                                logger.error(f"❌ Ошибка проверки по chat_id {telegram_chat_id}: {e2}")
                                subscribed = False
                        else:
                            subscribed = False
                
                # Если не удалось проверить подписку
                if not subscribed:
                    all_subscribed = False
                    missing_channels.append({
                        'id': channel_id,
                        'name': name,
                        'url': url,
                        'type': 'public'
                    })
                    
            except Exception as e:
                logger.error(f"❌ Критическая ошибка проверки канала '{name}': {e}")
                all_subscribed = False
                missing_channels.append({
                    'id': channel_id,
                    'name': f"{name} (ошибка проверки)",
                    'url': url,
                    'type': 'public'
                })
        
        elif channel_type == 'private':
            if not db.is_subscribed(user_id, channel_id):
                all_subscribed = False
                missing_channels.append({
                    'id': channel_id,
                    'name': name,
                    'url': url,
                    'type': 'private'
                })
    
    return all_subscribed, missing_channels

# ===== ОСНОВНЫЕ КОМАНДЫ =====
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    logger.info(f"Пользователь {user.id} запустил бота")
    
    db.add_user(user.id, user.username, user.full_name)
    
    welcome_text = f"""
🤖 Добро пожаловать, {user.first_name}!

Для доступа к контенту необходимо подписаться на каналы.

Нажмите кнопку ниже для проверки подписок 👇
    """
    
    keyboard = [[InlineKeyboardButton("🔍 Проверить подписки", callback_data="check_subscriptions")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /check"""
    user = update.effective_user
    db.add_user(user.id, user.username, user.full_name)
    
    await update.message.reply_text("🔍 Проверяю подписки...")
    
    all_subscribed, missing_channels = await check_user_subscriptions(user.id, context.bot)
    
    if all_subscribed:
        await show_final_content(update, context)
    else:
        await show_subscription_requests(update, context, missing_channels)

async def show_subscription_requests(update: Update, context: ContextTypes.DEFAULT_TYPE, missing_channels):
    """Показать запросы на подписку"""
    if not missing_channels:
        await update.message.reply_text("✅ Вы подписаны на все каналы!")
        return
    
    keyboard = []
    
    for channel in missing_channels:
        if channel['type'] == 'public':
            keyboard.append([InlineKeyboardButton(f"📢 Подписаться на {channel['name']}", url=channel['url'])])
        else:
            keyboard.append([
                InlineKeyboardButton(f"🔐 {channel['name']}", url=channel['url']),
                InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{channel['id']}")
            ])
    
    keyboard.append([InlineKeyboardButton("🔄 Проверить снова", callback_data="check_subscriptions")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = "📋 Необходимо подписаться на следующие каналы:\n\n"
    for channel in missing_channels:
        if channel['type'] == 'public':
            message_text += f"• {channel['name']} (публичный)\n"
        else:
            message_text += f"• {channel['name']} (приватный - требуется подтверждение)\n"
    
    message_text += "\nПосле подписки нажмите кнопку проверки"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup)

async def show_final_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать финальный контент"""
    final_channels = db.get_final_channels()
    
    if not final_channels:
        message_text = """
✅ Поздравляем!

Вы подписались на все необходимые каналы.

Ссылка на основной контент скоро будет добавлена.
        """
        
        keyboard = [[InlineKeyboardButton("🔄 Проверить снова", callback_data="check_subscriptions")]]
        
        if update.effective_user.id == ADMIN_ID:
            keyboard.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data="admin_panel")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(message_text, reply_markup=reply_markup)
        return
    
    channel = final_channels[0]
    channel_id, url, name, description = channel
    
    message_text = f"""
🎉 Доступ открыт!

📁 {name}
{description or 'Эксклюзивный контент'}

Нажмите кнопку ниже для перехода 👇
    """
    
    keyboard = [
        [InlineKeyboardButton("🚀 Перейти к контенту", url=url)],
        [InlineKeyboardButton("🔄 Проверить подписки", callback_data="check_subscriptions")]
    ]
    
    if update.effective_user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup)

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать админ-панель"""
    user_count = db.get_user_count()
    channels = db.get_channels()
    final_channels = db.get_final_channels()
    
    message_text = f"""
⚙️ Панель администратора

📊 Статистика:
• 👥 Пользователей: {user_count}
• 📺 Каналов: {len(channels)}
• 💎 Финальных каналов: {len(final_channels)}

Выберите действие:
    """
    
    keyboard = [
        [InlineKeyboardButton("📺 Управление каналами", callback_data="manage_channels")],
        [InlineKeyboardButton("🔄 Проверить подписки", callback_data="check_subscriptions")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup)

async def show_manage_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать управление каналами"""
    channels = db.get_channels()
    final_channels = db.get_final_channels()
    
    message_text = f"""
📊 Управление каналами

📺 Каналы для подписки ({len(channels)}):
"""
    
    for channel in channels:
        channel_id, username, url, name, channel_type, telegram_chat_id = channel
        type_icon = "🔓" if channel_type == 'public' else "🔒"
        identifier = f"@{username}" if username else "ссылка"
        message_text += f"{type_icon} {name} ({identifier})\n"
    
    message_text += f"\n💎 Финальные каналы ({len(final_channels)}):\n"
    
    for channel in final_channels:
        channel_id, url, name, description = channel
        message_text += f"💎 {name}\n"
    
    keyboard = [
        [InlineKeyboardButton("➕ Публичный канал", callback_data="add_public_channel")],
        [InlineKeyboardButton("➕ Приватный канал", callback_data="add_private_channel")],
        [InlineKeyboardButton("💎 Финальный канал", callback_data="add_final_channel")],
    ]
    
    if channels:
        keyboard.append([InlineKeyboardButton("🗑 Удалить канал подписки", callback_data="show_delete_channels")])
    
    if final_channels:
        keyboard.append([InlineKeyboardButton("🗑 Удалить финальный канал", callback_data="show_delete_final")])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup)

async def show_delete_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать каналы для удаления"""
    channels = db.get_channels()
    
    if not channels:
        await update.callback_query.answer("❌ Нет каналов для удаления", show_alert=True)
        return
    
    message_text = "🗑 Выберите канал для удаления:"
    
    keyboard = []
    for channel in channels:
        channel_id, username, url, name, channel_type, telegram_chat_id = channel
        type_icon = "🔓" if channel_type == 'public' else "🔒"
        keyboard.append([InlineKeyboardButton(f"{type_icon} {name}", callback_data=f"delete_channel_{channel_id}")])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="manage_channels")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)

async def show_delete_final(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать финальные каналы для удаления"""
    channels = db.get_final_channels()
    
    if not channels:
        await update.callback_query.answer("❌ Нет финальных каналов для удаления", show_alert=True)
        return
    
    message_text = "🗑 Выберите финальный канал для удаления:"
    
    keyboard = []
    for channel in channels:
        channel_id, url, name, description = channel
        keyboard.append([InlineKeyboardButton(f"💎 {name}", callback_data=f"delete_final_{channel_id}")])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="manage_channels")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий кнопок"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    data = query.data
    
    logger.info(f"Нажата кнопка: {data} пользователем {user.id}")
    
    try:
        if data == "check_subscriptions":
            db.add_user(user.id, user.username, user.full_name)
            all_subscribed, missing_channels = await check_user_subscriptions(user.id, context.bot)
            
            if all_subscribed:
                await show_final_content(update, context)
            else:
                await show_subscription_requests(update, context, missing_channels)
        
        elif data.startswith("confirm_"):
            channel_id = int(data.split("_")[1])
            
            if db.confirm_subscription(user.id, channel_id):
                await query.answer("✅ Подписка подтверждена!")
                all_subscribed, missing_channels = await check_user_subscriptions(user.id, context.bot)
                
                if all_subscribed:
                    await show_final_content(update, context)
                else:
                    await show_subscription_requests(update, context, missing_channels)
            else:
                await query.answer("❌ Ошибка подтверждения")
        
        elif data == "admin_panel":
            if user.id == ADMIN_ID:
                await show_admin_panel(update, context)
            else:
                await query.answer("❌ Нет доступа")
        
        elif data == "manage_channels":
            if user.id == ADMIN_ID:
                await show_manage_channels(update, context)
            else:
                await query.answer("❌ Нет доступа")
        
        elif data == "add_public_channel":
            if user.id == ADMIN_ID:
                context.user_data['awaiting_channel'] = 'public'
                await query.edit_message_text(
                    "➕ Добавить публичный канал\n\n"
                    "Отправьте в формате:\n"
                    "@username Название канала\n\n"
                    "Пример:\n"
                    "@my_channel Мой Канал\n\n"
                    "⚠️ Убедитесь, что:\n"
                    "• Канал публичный\n" 
                    "• Есть username (@...)\n"
                    "• Бот - администратор канала"
                )
            else:
                await query.answer("❌ Нет доступа")
        
        elif data == "add_private_channel":
            if user.id == ADMIN_ID:
                context.user_data['awaiting_channel'] = 'private'
                await query.edit_message_text(
                    "➕ Добавить приватный канал\n\n"
                    "Отправьте пригласительную ссылку и название:\n"
                    "ссылка Название канала\n\n"
                    "Пример:\n"
                    "https://t.me/+ABC123def456 Приватный Канал"
                )
            else:
                await query.answer("❌ Нет доступа")
        
        elif data == "add_final_channel":
            if user.id == ADMIN_ID:
                context.user_data['awaiting_channel'] = 'final'
                await query.edit_message_text(
                    "💎 Добавить финальный канал\n\n"
                    "Отправьте в формате:\n"
                    "ссылка Название Описание\n\n"
                    "Пример:\n"
                    "https://t.me/premium Премиум Эксклюзивный контент"
                )
            else:
                await query.answer("❌ Нет доступа")
        
        elif data == "show_delete_channels":
            if user.id == ADMIN_ID:
                await show_delete_channels(update, context)
            else:
                await query.answer("❌ Нет доступа")
        
        elif data == "show_delete_final":
            if user.id == ADMIN_ID:
                await show_delete_final(update, context)
            else:
                await query.answer("❌ Нет доступа")
        
        elif data.startswith("delete_channel_"):
            if user.id == ADMIN_ID:
                channel_id = int(data.split("_")[2])
                if db.remove_channel(channel_id):
                    await query.answer("✅ Канал удален!")
                    await show_manage_channels(update, context)
                else:
                    await query.answer("❌ Ошибка при удалении канала")
            else:
                await query.answer("❌ Нет доступа")
        
        elif data.startswith("delete_final_"):
            if user.id == ADMIN_ID:
                channel_id = int(data.split("_")[2])
                if db.remove_final_channel(channel_id):
                    await query.answer("✅ Финальный канал удален!")
                    await show_manage_channels(update, context)
                else:
                    await query.answer("❌ Ошибка при удалении финального канала")
            else:
                await query.answer("❌ Нет доступа")
        
        else:
            logger.warning(f"Неизвестный callback_data: {data}")
            await query.answer("❌ Неизвестная команда")
    
    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}")
        await query.answer("❌ Произошла ошибка")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user = update.effective_user
    
    if user.id == ADMIN_ID and context.user_data.get('awaiting_channel'):
        channel_type = context.user_data['awaiting_channel']
        text = update.message.text.strip()
        
        logger.info(f"Обработка сообщения для типа {channel_type}: {text}")
        
        try:
            if channel_type == 'public':
                parts = text.split(' ', 1)
                if len(parts) == 2 and parts[0].startswith('@'):
                    username = parts[0]
                    name = parts[1]
                    clean_username = username.lstrip('@')
                    url = f"https://t.me/{clean_username}"
                    
                    # 🔧 Пытаемся найти канал и получить его ID
                    try:
                        chat = await context.bot.get_chat(f"@{clean_username}")
                        telegram_chat_id = str(chat.id)
                        logger.info(f"✅ Найден канал: {chat.title} (ID: {telegram_chat_id})")
                        
                        if db.add_channel(username, url, name, 'public', telegram_chat_id):
                            await update.message.reply_text(
                                f"✅ Публичный канал добавлен!\n\n"
                                f"📝 Название: {name}\n"
                                f"🔗 Ссылка: {url}\n"
                                f"👤 Username: {username}\n"
                                f"🆔 ID канала: {telegram_chat_id}"
                            )
                            await show_manage_channels(update, context)
                        else:
                            await update.message.reply_text("❌ Ошибка добавления канала")
                    
                    except BadRequest as e:
                        logger.error(f"❌ Не удалось найти канал @{clean_username}: {e}")
                        await update.message.reply_text(
                            f"❌ Не удалось найти канал @{clean_username}\n\n"
                            f"Проверьте:\n"
                            f"• Канал существует и публичный\n"
                            f"• Username правильный\n"
                            f"• Бот является администратором канала"
                        )
                        return
                    
                else:
                    await update.message.reply_text(
                        "❌ Неверный формат. Используйте:\n"
                        "@username Название канала\n\n"
                        "Пример:\n"
                        "@my_channel Мой Канал"
                    )
            
            elif channel_type == 'private':
                parts = text.split(' ', 1)
                if len(parts) == 2:
                    url = parts[0]
                    name = parts[1]
                    
                    if db.add_channel(None, url, name, 'private'):
                        await update.message.reply_text(
                            f"✅ Приватный канал добавлен!\n\n"
                            f"📝 Название: {name}\n"
                            f"🔗 Ссылка: {url}"
                        )
                        await show_manage_channels(update, context)
                    else:
                        await update.message.reply_text("❌ Ошибка добавления канала")
                else:
                    await update.message.reply_text(
                        "❌ Неверный формат. Используйте:\n"
                        "ссылка Название канала\n\n"
                        "Пример:\n"
                        "https://t.me/+ABC123def456 Приватный Канал"
                    )
            
            elif channel_type == 'final':
                parts = text.split(' ', 2)
                if len(parts) >= 2:
                    url = parts[0]
                    name = parts[1]
                    description = parts[2] if len(parts) > 2 else ""
                    
                    if db.add_final_channel(url, name, description):
                        await update.message.reply_text(
                            f"💎 Финальный канал добавлен!\n\n"
                            f"📝 Название: {name}\n"
                            f"🔗 Ссылка: {url}\n"
                            f"📄 Описание: {description or 'не указано'}"
                        )
                        await show_manage_channels(update, context)
                    else:
                        await update.message.reply_text("❌ Ошибка добавления канала")
                else:
                    await update.message.reply_text("❌ Неверный формат. Используйте: ссылка Название [Описание]")
            
            context.user_data['awaiting_channel'] = None
            
        except Exception as e:
            logger.error(f"Ошибка обработки сообщения: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
            context.user_data['awaiting_channel'] = None
    else:
        await update.message.reply_text(
            "Используйте команды:\n"
            "/start - начать работу\n"
            "/check - проверить подписки\n"
            "/admin - панель управления (только для админа)"
        )

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /admin"""
    if update.effective_user.id == ADMIN_ID:
        await show_admin_panel(update, context)
    else:
        await update.message.reply_text("❌ У вас нет доступа к этой команде")

async def set_commands(application: Application):
    """Установка команд бота"""
    commands = [
        BotCommand("start", "🚀 Начать работу с ботом"),
        BotCommand("check", "🔍 Проверить подписки"),
        BotCommand("admin", "⚙️ Панель управления")
    ]
    await application.bot.set_my_commands(commands)

def main():
    """Запуск бота"""
    print("🚀 Запуск бота с улучшенным поиском каналов...")
    print("🔧 Основные улучшения:")
    print("   • Бот ищет канал по username и получает его ID")
    print("   • Сохраняет ID канала для надежной проверки")
    print("   • Улучшена обработка ошибок 'чат не найден'")
    print("   • Детальное логирование процесса поиска каналов")
    
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Добавляем обработчики
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("check", check_command))
        application.add_handler(CommandHandler("admin", admin_command))
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Устанавливаем команды
        application.post_init = set_commands
        
        print("✅ Бот запущен!")
        print("📝 Инструкция:")
        print("   1. Убедитесь что канал публичный и имеет username")
        print("   2. Добавьте бота как администратора в канал") 
        print("   3. В боте: /admin → Управление каналами → Публичный канал")
        print("   4. Отправьте: @username_канала Название")
        
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Ошибка запуска: {e}")
        print(f"❌ Критическая ошибка: {e}")

if __name__ == "__main__":
    main()
