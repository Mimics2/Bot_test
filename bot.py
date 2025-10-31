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
                telegram_chat_id INTEGER
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
    """Проверка подписок пользователя с улучшенной обработкой ошибок"""
    channels = db.get_channels()
    missing_channels = []
    all_subscribed = True
    
    for channel in channels:
        channel_id, username, url, name, channel_type, telegram_chat_id = channel
        
        if channel_type == 'public':
            try:
                subscribed = False
                
                # 🔧 ПРИОРИТЕТ 1: Проверка по chat_id (самый надежный способ)
                if telegram_chat_id:
                    try:
                        logger.info(f"🔍 Проверка канала '{name}' по ID: {telegram_chat_id}")
                        chat_member = await bot.get_chat_member(telegram_chat_id, user_id)
                        subscribed = chat_member.status in ['member', 'administrator', 'creator']
                        if subscribed:
                            logger.info(f"✅ Пользователь {user_id} подписан на канал '{name}'")
                        else:
                            logger.info(f"❌ Пользователь {user_id} НЕ подписан на канал '{name}'")
                            
                    except BadRequest as e:
                        error_msg = str(e)
                        if "Chat not found" in error_msg:
                            logger.error(f"❌ Чат не найден по ID {telegram_chat_id} для канала '{name}'")
                            # Пробуем через username как запасной вариант
                            if username and username.startswith('@'):
                                try:
                                    clean_username = username.lstrip('@')
                                    logger.info(f"🔄 Пробуем проверку по username: {clean_username}")
                                    chat_member = await bot.get_chat_member(f"@{clean_username}", user_id)
                                    subscribed = chat_member.status in ['member', 'administrator', 'creator']
                                    logger.info(f"✅ Проверка по username успешна: {subscribed}")
                                except BadRequest as e2:
                                    logger.error(f"❌ Ошибка проверки по username {username}: {e2}")
                                    subscribed = False
                        elif "User not found" in error_msg:
                            logger.error(f"❌ Пользователь {user_id} не найден в канале '{name}'")
                            subscribed = False
                        elif "bot is not a member" in error_msg.lower():
                            logger.error(f"❌ Бот не является участником канала '{name}'")
                            # Если бот не в канале, считаем что пользователь не подписан
                            subscribed = False
                        else:
                            logger.error(f"❌ Неизвестная ошибка при проверке канала '{name}': {e}")
                            subscribed = False
                
                # 🔧 ПРИОРИТЕТ 2: Проверка по username (если нет chat_id)
                elif username and username.startswith('@'):
                    try:
                        clean_username = username.lstrip('@')
                        logger.info(f"🔍 Проверка канала '{name}' по username: {clean_username}")
                        chat_member = await bot.get_chat_member(f"@{clean_username}", user_id)
                        subscribed = chat_member.status in ['member', 'administrator', 'creator']
                        logger.info(f"✅ Проверка по username успешна: {subscribed}")
                    except BadRequest as e:
                        error_msg = str(e)
                        if "Chat not found" in error_msg:
                            logger.error(f"❌ Чат не найден по username @{clean_username}")
                        elif "User not found" in error_msg:
                            logger.error(f"❌ Пользователь {user_id} не найден в канале '{name}'")
                        else:
                            logger.error(f"❌ Ошибка проверки канала '{name}' по username: {e}")
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
🤖 *Добро пожаловать, {user.first_name}!*

Для доступа к контенту необходимо подписаться на каналы.

Нажмите кнопку ниже для проверки подписок 👇
    """
    
    keyboard = [[InlineKeyboardButton("🔍 Проверить подписки", callback_data="check_subscriptions")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

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
    
    message_text = "📋 *Необходимо подписаться на следующие каналы:*\n\n"
    for channel in missing_channels:
        if channel['type'] == 'public':
            message_text += f"• {channel['name']} (публичный)\n"
        else:
            message_text += f"• {channel['name']} (приватный - требуется подтверждение)\n"
    
    message_text += "\nПосле подписки нажмите кнопку проверки"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_final_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать финальный контент"""
    final_channels = db.get_final_channels()
    
    if not final_channels:
        message_text = """
✅ *Поздравляем!*

Вы подписались на все необходимые каналы.

Ссылка на основной контент скоро будет добавлена.
        """
        
        keyboard = [[InlineKeyboardButton("🔄 Проверить снова", callback_data="check_subscriptions")]]
        
        if update.effective_user.id == ADMIN_ID:
            keyboard.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data="admin_panel")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
        return
    
    channel = final_channels[0]
    channel_id, url, name, description = channel
    
    message_text = f"""
🎉 *Доступ открыт!*

📁 *{name}*
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
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать админ-панель"""
    user_count = db.get_user_count()
    channels = db.get_channels()
    final_channels = db.get_final_channels()
    
    message_text = f"""
⚙️ *Панель администратора*

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
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_manage_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать управление каналами"""
    channels = db.get_channels()
    final_channels = db.get_final_channels()
    
    message_text = f"""
📊 *Управление каналами*

📺 Каналы для подписки ({len(channels)}):
"""
    
    for channel in channels:
        channel_id, username, url, name, channel_type, telegram_chat_id = channel
        type_icon = "🔓" if channel_type == 'public' else "🔒"
        identifier = f"ID: {telegram_chat_id}" if telegram_chat_id else f"@{username}" if username else "ссылка"
        message_text += f"{type_icon} {name} ({identifier})\n"
    
    message_text += f"\n💎 Финальные каналы ({len(final_channels)}):\n"
    
    for channel in final_channels:
        channel_id, url, name, description = channel
        message_text += f"💎 {name}\n"
    
    keyboard = [
        [InlineKeyboardButton("➕ Публичный канал", callback_data="add_channel_public")],
        [InlineKeyboardButton("➕ Приватный канал", callback_data="add_channel_private")],
        [InlineKeyboardButton("🆔 Добавить по ID", callback_data="add_channel_id")],
        [InlineKeyboardButton("💎 Финальный канал", callback_data="add_final_channel")],
    ]
    
    if channels:
        keyboard.append([InlineKeyboardButton("🗑 Удалить канал подписки", callback_data="show_delete_channels")])
    
    if final_channels:
        keyboard.append([InlineKeyboardButton("🗑 Удалить финальный канал", callback_data="show_delete_final")])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_delete_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать каналы для удаления"""
    channels = db.get_channels()
    
    if not channels:
        await update.callback_query.answer("❌ Нет каналов для удаления", show_alert=True)
        return
    
    message_text = "🗑 *Выберите канал для удаления:*"
    
    keyboard = []
    for channel in channels:
        channel_id, username, url, name, channel_type, telegram_chat_id = channel
        type_icon = "🔓" if channel_type == 'public' else "🔒"
        keyboard.append([InlineKeyboardButton(f"{type_icon} {name}", callback_data=f"delete_channel_{channel_id}")])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="manage_channels")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_delete_final(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать финальные каналы для удаления"""
    channels = db.get_final_channels()
    
    if not channels:
        await update.callback_query.answer("❌ Нет финальных каналов для удаления", show_alert=True)
        return
    
    message_text = "🗑 *Выберите финальный канал для удаления:*"
    
    keyboard = []
    for channel in channels:
        channel_id, url, name, description = channel
        keyboard.append([InlineKeyboardButton(f"💎 {name}", callback_data=f"delete_final_{channel_id}")])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="manage_channels")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий кнопок"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    data = query.data
    
    logger.info(f"Нажата кнопка: {data} пользователем {user.id}")
    
    if data == "check_subscriptions":
        db.add_user(user.id, user.username, user.full_name)
        all_subscribed, missing_channels = await check_user_subscriptions(user.id, context.bot)
        
        if all_subscribed:
            await show_final_content(update, context)
        else:
            await show_subscription_requests(update, context, missing_channels)
    
    elif data.startswith("confirm_"):
        channel_id = int(data.replace("confirm_", ""))
        
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
    
    elif data == "add_channel_public":
        if user.id == ADMIN_ID:
            context.user_data['awaiting_channel'] = 'public'
            await query.edit_message_text(
                "➕ *Добавить публичный канал*\n\n"
                "📝 Отправьте в формате:\n"
                "`@username Название канала`\n\n"
                "✅ Пример:\n"
                "`@my_channel Мой Канал`\n\n"
                "🔗 Бот создаст ссылку: https://t.me/my_channel",
                parse_mode='Markdown'
            )
        else:
            await query.answer("❌ Нет доступа")
    
    elif data == "add_channel_private":
        if user.id == ADMIN_ID:
            context.user_data['awaiting_channel'] = 'private'
            await query.edit_message_text(
                "➕ *Добавить приватный канал*\n\n"
                "📝 Отправьте в формате:\n"
                "`ссылка Название канала`\n\n"
                "✅ Пример:\n"
                "`https://t.me/+ABC123def456 Приватный Канал`\n\n"
                "⚠️ Используйте пригласительные ссылки из настроек канала!",
                parse_mode='Markdown'
            )
        else:
            await query.answer("❌ Нет доступа")
    
    elif data == "add_channel_id":
        if user.id == ADMIN_ID:
            context.user_data['awaiting_channel'] = 'by_id'
            await query.edit_message_text(
                "🆔 *Добавить канал по ID*\n\n"
                "⚠️ *Внимание!* Этот метод создает ссылку формата https://t.me/c/ID\n"
                "*Такая ссылка может не работать для пользователей!*\n\n"
                "✅ *Рекомендуемые методы:*\n"
                "• Для публичных каналов: используйте '@username'\n"
                "• Для приватных каналов: используйте пригласительные ссылки\n\n"
                "Если все равно хотите добавить по ID:\n"
                "📝 Отправьте в формате:\n"
                "`chat_id Название_канала`\n\n"
                "Пример:\n"
                "`-1001234567890 Мой Канал`",
                parse_mode='Markdown'
            )
        else:
            await query.answer("❌ Нет доступа")
    
    elif data == "add_final_channel":
        if user.id == ADMIN_ID:
            context.user_data['awaiting_channel'] = 'final'
            await query.edit_message_text(
                "💎 *Добавить финальный канал*\n\n"
                "📝 Отправьте в формате:\n"
                "`ссылка Название Описание`\n\n"
                "✅ Пример:\n"
                "`https://t.me/premium Премиум Эксклюзивный контент`",
                parse_mode='Markdown'
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
            channel_id = int(data.replace("delete_channel_", ""))
            try:
                if db.remove_channel(channel_id):
                    await query.answer("✅ Канал удален!")
                    await show_manage_channels(update, context)
                else:
                    await query.answer("❌ Ошибка при удалении канала")
            except Exception as e:
                logger.error(f"Ошибка удаления канала: {e}")
                await query.answer("❌ Ошибка удаления")
        else:
            await query.answer("❌ Нет доступа")
    
    elif data.startswith("delete_final_"):
        if user.id == ADMIN_ID:
            channel_id = int(data.replace("delete_final_", ""))
            try:
                if db.remove_final_channel(channel_id):
                    await query.answer("✅ Финальный канал удален!")
                    await show_manage_channels(update, context)
                else:
                    await query.answer("❌ Ошибка при удалении финального канала")
            except Exception as e:
                logger.error(f"Ошибка удаления финального канала: {e}")
                await query.answer("❌ Ошибка удаления")
        else:
            await query.answer("❌ Нет доступа")
    
    else:
        logger.warning(f"Неизвестный callback_data: {data}")
        await query.answer("❌ Неизвестная команда")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user = update.effective_user
    
    # Проверяем, ожидаем ли мы ввод канала от админа
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
                    # 🔧 ИСПРАВЛЕНИЕ: Правильная ссылка для публичного канала
                    clean_username = username.lstrip('@')
                    url = f"https://t.me/{clean_username}"
                    
                    if db.add_channel(username, url, name, 'public'):
                        await update.message.reply_text(
                            f"✅ *Публичный канал добавлен!*\n\n"
                            f"📝 Название: {name}\n"
                            f"🔗 Ссылка: {url}\n"
                            f"👤 Username: {username}",
                            parse_mode='Markdown'
                        )
                        await show_manage_channels(update, context)
                    else:
                        await update.message.reply_text("❌ Ошибка добавления канала")
                else:
                    await update.message.reply_text(
                        "❌ Неверный формат. Используйте:\n"
                        "`@username Название канала`\n\n"
                        "Пример:\n"
                        "`@my_channel Мой Канал`",
                        parse_mode='Markdown'
                    )
            
            elif channel_type == 'private':
                parts = text.split(' ', 1)
                if len(parts) == 2:
                    url = parts[0]
                    name = parts[1]
                    
                    # 🔧 ПРОВЕРКА: Убедимся что ссылка правильная
                    if not (url.startswith('https://t.me/+') or url.startswith('https://t.me/joinchat/')):
                        await update.message.reply_text(
                            "⚠️ *Внимание! Неправильный формат ссылки!*\n\n"
                            "✅ Для приватного канала используйте пригласительную ссылку формата:\n"
                            "• `https://t.me/+xxxxxxxxxx`\n"
                            "• `https://t.me/joinchat/xxxxxxxx`\n\n"
                            "📝 Создайте ссылку в настройках канала: \n"
                            "Канал → Информация → Пригласительные ссылки",
                            parse_mode='Markdown'
                        )
                        return
                    
                    if db.add_channel(None, url, name, 'private'):
                        await update.message.reply_text(
                            f"✅ *Приватный канал добавлен!*\n\n"
                            f"📝 Название: {name}\n"
                            f"🔗 Ссылка: {url}",
                            parse_mode='Markdown'
                        )
                        await show_manage_channels(update, context)
                    else:
                        await update.message.reply_text("❌ Ошибка добавления канала")
                else:
                    await update.message.reply_text(
                        "❌ Неверный формат. Используйте:\n"
                        "`ссылка Название канала`\n\n"
                        "Пример:\n"
                        "`https://t.me/+ABC123def456 Приватный Канал`",
                        parse_mode='Markdown'
                    )
            
            # 🔧 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Правильное формирование ссылки для каналов по ID
            elif channel_type == 'by_id':
                parts = text.split(' ', 1)
                if len(parts) == 2:
                    chat_id_str = parts[0]
                    name = parts[1]
                    
                    try:
                        chat_id = int(chat_id_str)
                        
                        # 🔧 ИСПРАВЛЕНИЕ: Правильное формирование ссылки
                        if chat_id < 0:
                            # Для каналов и супергрупп
                            url = f"https://t.me/c/{abs(chat_id)}"
                            
                            await update.message.reply_text(
                                f"⚠️ *Внимание! Ограниченная функциональность!*\n\n"
                                f"✅ Канал по ID добавлен:\n"
                                f"📝 Название: {name}\n"
                                f"🆔 ID: {chat_id}\n"
                                f"🔗 Ссылка: {url}\n\n"
                                f"❌ *Проблемы:*\n"
                                f"• Ссылка может не работать для пользователей\n"
                                f"• Проверка подписки может не работать\n\n"
                                f"💡 *Рекомендация:*\n"
                                f"Используйте добавление по @username для публичных каналов",
                                parse_mode='Markdown'
                            )
                        else:
                            # Для пользователей (обычно не используется для каналов)
                            url = f"https://t.me/{chat_id}"
                        
                        if db.add_channel(None, url, name, 'public', chat_id):
                            await show_manage_channels(update, context)
                        else:
                            await update.message.reply_text("❌ Ошибка добавления канала")
                    except ValueError:
                        await update.message.reply_text("❌ ID должен быть числом")
                else:
                    await update.message.reply_text("❌ Неверный формат. Используйте: chat_id Название")
            
            elif channel_type == 'final':
                parts = text.split(' ', 2)
                if len(parts) >= 2:
                    url = parts[0]
                    name = parts[1]
                    description = parts[2] if len(parts) > 2 else ""
                    
                    if db.add_final_channel(url, name, description):
                        await update.message.reply_text(
                            f"💎 *Финальный канал добавлен!*\n\n"
                            f"📝 Название: {name}\n"
                            f"🔗 Ссылка: {url}\n"
                            f"📄 Описание: {description or 'не указано'}",
                            parse_mode='Markdown'
                        )
                        await show_manage_channels(update, context)
                    else:
                        await update.message.reply_text("❌ Ошибка добавления канала")
                else:
                    await update.message.reply_text("❌ Неверный формат. Используйте: ссылка Название [Описание]")
            
            # Сбрасываем состояние ожидания
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

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)
    
    if update and update.callback_query:
        try:
            await update.callback_query.answer("❌ Произошла ошибка, попробуйте еще раз")
        except:
            pass

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
    print("🚀 Запуск исправленной версии бота...")
    print("🔧 Основные исправления:")
    print("   • Правильное формирование ссылок для публичных каналов")
    print("   • Проверка формата ссылок для приватных каналов")
    print("   • Улучшенные сообщения об ошибках")
    print("   • Предупреждения о проблемных ссылках")
    
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Добавляем обработчики
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("check", check_command))
        application.add_handler(CommandHandler("admin", admin_command))
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Добавляем обработчик ошибок
        application.add_error_handler(error_handler)
        
        # Устанавливаем команды
        application.post_init = set_commands
        
        print("✅ Бот запущен!")
        print("📝 Рекомендации по добавлению каналов:")
        print("   • Публичные каналы: @username Название")
        print("   • Приватные каналы: пригласительная ссылка Название")
        print("   • Избегайте добавления по ID - создает нерабочие ссылки")
        
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Ошибка запуска: {e}")
        print(f"❌ Критическая ошибка: {e}")

if __name__ == "__main__":
    main()
