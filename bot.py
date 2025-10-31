import logging
import sqlite3
import os
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# ===== КОНФИГУРАЦИЯ =====
BOT_TOKEN = "7557745613:AAFTpWsCJ2bZMqD6GDwTynnqA8Nc-mRF1Rs"  # ЗАМЕНИТЕ НА ВАШ ТОКЕН
ADMIN_ID =  6646433980  # ЗАМЕНИТЕ НА ВАШ TELEGRAM ID
DB_PATH = "bot_database.db"

# Проверка токена
if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
    print("❌ ОШИБКА: Замените BOT_TOKEN на ваш настоящий токен!")
    exit(1)

if ADMIN_ID == 123456789:
    print("❌ ОШИБКА: Замените ADMIN_ID на ваш Telegram ID!")
    exit(1)

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
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица каналов для подписки (ДОБАВЛЕНО ПОЛЕ ДЛЯ TELEGRAM CHAT ID)
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
        
        # Таблица подтвержденных подписок
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER,
                channel_id INTEGER,
                confirmed BOOLEAN DEFAULT FALSE,
                PRIMARY KEY (user_id, channel_id)
            )
        ''')
        
        # Таблица финальных каналов
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

# ===== ОСНОВНЫЕ ФУНКЦИИ =====
async def check_user_subscriptions(user_id, bot):
    """Проверка подписок пользователя с использованием ID канала"""
    channels = db.get_channels()
    missing_channels = []
    all_subscribed = True
    
    for channel in channels:
        channel_id, username, url, name, channel_type, telegram_chat_id = channel
        
        if channel_type == 'public':
            try:
                # 🔧 ПЕРВОЕ ИСПРАВЛЕНИЕ: Используем telegram_chat_id если доступен
                if telegram_chat_id:
                    # Используем числовой ID для проверки [citation:5]
                    chat_member = await bot.get_chat_member(telegram_chat_id, user_id)
                    subscribed = chat_member.status in ['member', 'administrator', 'creator']
                    
                    if not subscribed:
                        all_subscribed = False
                        missing_channels.append({
                            'id': channel_id,
                            'name': name,
                            'url': url,
                            'type': 'public'
                        })
                elif username:
                    # Резервный вариант через username
                    clean_username = username.lstrip('@')
                    chat_member = await bot.get_chat_member(f"@{clean_username}", user_id)
                    subscribed = chat_member.status in ['member', 'administrator', 'creator']
                    
                    if not subscribed:
                        all_subscribed = False
                        missing_channels.append({
                            'id': channel_id,
                            'name': name,
                            'url': url,
                            'type': 'public'
                        })
            except Exception as e:
                logger.error(f"Ошибка проверки канала {name}: {e}")
                all_subscribed = False
                missing_channels.append({
                    'id': channel_id,
                    'name': f"{name} (ошибка проверки)",
                    'url': url,
                    'type': 'public'
                })
        
        elif channel_type == 'private':
            # Для приватных каналов проверяем подтверждение
            if not db.is_subscribed(user_id, channel_id):
                all_subscribed = False
                missing_channels.append({
                    'id': channel_id,
                    'name': name,
                    'url': url,
                    'type': 'private'
                })
    
    return all_subscribed, missing_channels

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
        [InlineKeyboardButton("📺 Управление каналами", callback_data="admin_manage_channels")],
        [InlineKeyboardButton("🔄 Проверить подписки", callback_data="check_subscriptions")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_manage_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать управление каналами с исправленными кнопками удаления"""
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
        [InlineKeyboardButton("➕ Публичный канал", callback_data="admin_add_public")],
        [InlineKeyboardButton("➕ Приватный канал", callback_data="admin_add_private")],
        [InlineKeyboardButton("🆔 Добавить по ID", callback_data="admin_add_by_id")],
        [InlineKeyboardButton("💎 Финальный канал", callback_data="admin_add_final")],
    ]
    
    # 🔧 ВТОРОЕ ИСПРАВЛЕНИЕ: Рабочие кнопки удаления
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
    
    keyboard = []
    for channel in channels:
        channel_id, username, url, name, channel_type, telegram_chat_id = channel
        type_icon = "🔓" if channel_type == 'public' else "🔒"
        keyboard.append([InlineKeyboardButton(f"{type_icon} {name}", callback_data=f"delete_channel_{channel_id}")])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="manage_channels")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text("🗑 *Выберите канал для удаления:*", reply_markup=reply_markup, parse_mode='Markdown')

async def show_delete_final(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать финальные каналы для удаления"""
    channels = db.get_final_channels()
    
    if not channels:
        await update.callback_query.answer("❌ Нет финальных каналов для удаления", show_alert=True)
        return
    
    keyboard = []
    for channel in channels:
        channel_id, url, name, description = channel
        keyboard.append([InlineKeyboardButton(f"💎 {name}", callback_data=f"delete_final_{channel_id}")])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="manage_channels")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text("🗑 *Выберите финальный канал для удаления:*", reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий кнопок с исправленным удалением"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    data = query.data
    
    logger.info(f"Нажата кнопка: {data}")
    
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
    
    elif data == "admin_manage_channels":
        if user.id == ADMIN_ID:
            await show_manage_channels(update, context)
        else:
            await query.answer("❌ Нет доступа")
    
    elif data == "admin_add_public":
        if user.id == ADMIN_ID:
            context.user_data['awaiting_channel'] = 'public'
            await query.edit_message_text(
                "➕ *Добавить публичный канал*\n\n"
                "Отправьте в формате:\n"
                "`@username Название канала`\n\n"
                "Пример:\n"
                "`@my_channel Мой Канал`",
                parse_mode='Markdown'
            )
        else:
            await query.answer("❌ Нет доступа")
    
    elif data == "admin_add_private":
        if user.id == ADMIN_ID:
            context.user_data['awaiting_channel'] = 'private'
            await query.edit_message_text(
                "➕ *Добавить приватный канал*\n\n"
                "Отправьте в формате:\n"
                "`ссылка Название канала`\n\n"
                "Пример:\n"
                "`https://t.me/private_channel Приватный Канал`",
                parse_mode='Markdown'
            )
        else:
            await query.answer("❌ Нет доступа")
    
    elif data == "admin_add_by_id":
        if user.id == ADMIN_ID:
            context.user_data['awaiting_channel'] = 'by_id'
            await query.edit_message_text(
                "🆔 *Добавить канал по ID*\n\n"
                "Отправьте в формате:\n"
                "`chat_id Название канала`\n\n"
                "Пример:\n"
                "`-1001234567890 Мой Канал`\n\n"
                "Где chat_id — числовой идентификатор канала/чата",
                parse_mode='Markdown'
            )
        else:
            await query.answer("❌ Нет доступа")
    
    elif data == "admin_add_final":
        if user.id == ADMIN_ID:
            context.user_data['awaiting_channel'] = 'final'
            await query.edit_message_text(
                "💎 *Добавить финальный канал*\n\n"
                "Отправьте в формате:\n"
                "`ссылка Название Описание`\n\n"
                "Пример:\n"
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
    
    # 🔧 ТРЕТЬЕ ИСПРАВЛЕНИЕ: Рабочие обработчики удаления
    elif data.startswith("delete_channel_"):
        if user.id == ADMIN_ID:
            channel_id = int(data.replace("delete_channel_", ""))
            try:
                if db.remove_channel(channel_id):
                    await query.answer("✅ Канал удален!")
                    # Обновляем сообщение чтобы убрать удаленный канал из списка
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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений с поддержкой добавления по ID"""
    user = update.effective_user
    
    if user.id == ADMIN_ID and context.user_data.get('awaiting_channel'):
        channel_type = context.user_data['awaiting_channel']
        text = update.message.text.strip()
        
        try:
            if channel_type == 'public':
                parts = text.split(' ', 1)
                if len(parts) == 2 and parts[0].startswith('@'):
                    username = parts[0]
                    name = parts[1]
                    url = f"https://t.me/{username.lstrip('@')}"
                    
                    if db.add_channel(username, url, name, 'public'):
                        await update.message.reply_text(f"✅ Публичный канал добавлен:\n{name}\n{url}")
                        await show_manage_channels(update, context)
                    else:
                        await update.message.reply_text("❌ Ошибка добавления канала")
                else:
                    await update.message.reply_text("❌ Неверный формат. Используйте: @username Название")
            
            elif channel_type == 'private':
                parts = text.split(' ', 1)
                if len(parts) == 2:
                    url = parts[0]
                    name = parts[1]
                    
                    if db.add_channel(None, url, name, 'private'):
                        await update.message.reply_text(f"✅ Приватный канал добавлен:\n{name}\n{url}")
                        await show_manage_channels(update, context)
                    else:
                        await update.message.reply_text("❌ Ошибка добавления канала")
                else:
                    await update.message.reply_text("❌ Неверный формат. Используйте: ссылка Название")
            
            elif channel_type == 'by_id':
                parts = text.split(' ', 1)
                if len(parts) == 2:
                    chat_id_str = parts[0]
                    name = parts[1]
                    
                    try:
                        chat_id = int(chat_id_str)
                        # Для каналов ID обычно отрицательные, для супергрупп с префиксом -100
                        url = f"https://t.me/c/{str(chat_id).replace('-100', '')}" if chat_id < 0 else f"https://t.me/{chat_id}"
                        
                        if db.add_channel(None, url, name, 'public', chat_id):
                            await update.message.reply_text(f"✅ Канал по ID добавлен:\n{name}\nID: {chat_id}\n{url}")
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
                        await update.message.reply_text(f"💎 Финальный канал добавлен:\n{name}\n{url}")
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
    print("🚀 Запуск улучшенной версии бота...")
    print("🔧 Основные исправления:")
    print("   • Добавлено добавление каналов по ID")
    print("   • Исправлены кнопки удаления каналов")
    print("   • Улучшена проверка подписок через chat_id")
    
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("check", check_command))
        application.add_handler(CommandHandler("admin", admin_command))
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        application.post_init = set_commands
        
        print("✅ Бот запущен с исправлениями!")
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Ошибка запуска: {e}")

if __name__ == "__main__":
    main()
