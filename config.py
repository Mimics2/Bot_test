# =============================================
# 🤖 ОСНОВНЫЕ НАСТРОЙКИ БОТА
# =============================================

# Токен бота от @BotFather (ОБЯЗАТЕЛЬНО ЗАМЕНИТЬ!)
BOT_TOKEN = "7557745613:AAFTpWsCJ2bZMqD6GDwTynnqA8Nc-mRF1Rs"

# ID администратора (узнать через @userinfobot)
ADMIN_ID = 6646433980 # ЗАМЕНИТЬ на свой ID

# =============================================
# 🗄️ НАСТРОЙКИ БАЗЫ ДАННЫХ
# =============================================

# Автоматическое определение пути к БД для разных хостингов
import os
import tempfile

# Для Railway, Heroku и других cloud-хостингов
if 'RAILWAY_STATIC_URL' in os.environ or 'DYNO' in os.environ:
    DB_PATH = os.path.join(tempfile.gettempdir(), "bot.db")
# Для Vercel (без постоянного хранилища)
elif 'VERCEL' in os.environ:
    DB_PATH = "/tmp/bot.db"
# Для локальной разработки
else:
    DB_PATH = "bot.db"

# =============================================
# 🌐 НАСТРОЙКИ ХОСТИНГОВ
# =============================================

# Порт для webhook (для Heroku, Railway, Vercel)
PORT = int(os.environ.get('PORT', 8443))

# URL для webhook (автоматически определяется)
if 'RAILWAY_STATIC_URL' in os.environ:
    WEBHOOK_URL = f"https://{os.environ['RAILWAY_STATIC_URL']}/{BOT_TOKEN}"
elif 'VERCEL_URL' in os.environ:
    WEBHOOK_URL = f"https://{os.environ['VERCEL_URL']}/{BOT_TOKEN}"
elif 'HEROKU_APP_NAME' in os.environ:
    WEBHOOK_URL = f"https://{os.environ['HEROKU_APP_NAME']}.herokuapp.com/{BOT_TOKEN}"
else:
    WEBHOOK_URL = None

# =============================================
# 🎨 ДИЗАЙН И ТЕКСТЫ
# =============================================

TEXTS = {
    "start": """
🎊 *Добро пожаловать в Premium Access Bot!* 🎊

🌟 *Ваш ключ к эксклюзивному контенту*

📋 *Всего 3 простых шага:*
1️⃣ **Подпишитесь** на указанные каналы
2️⃣ **Пройдите** автоматическую проверку  
3️⃣ **Получите** доступ к закрытому контенту

🚀 *Готовы начать?*
    """,
    
    "success": """
🎉 *УСПЕХ! ДОСТУП ОТКРЫТ!* 🎉

✨ *Поздравляем! Вы получили доступ к эксклюзивному материалу!*

💎 *Ваш премиум контент:*
*{channel_name}*

📖 *Описание:*
{description}

🔗 *Персональная ссылка:*
`{channel_url}`

⚡ *Нажмите кнопку ниже для перехода*
    """,
    
    "subscription_required": """
🔐 *ТРЕБУЕТСЯ ПОДПИСКА*

📋 *Необходимые действия:*

{channels_list}

💫 *После выполнения нажмите "Проверить подписки"*
    """,
    
    "admin_welcome": """
⚙️ *ПАНЕЛЬ УПРАВЛЕНИЯ* ⚙️

📊 *Статистика системы:*
• 👥 Всего пользователей: *{total_users}*
• 🔄 Проверок сегодня: *{today_checks}*
• 🆕 Новых сегодня: *{today_new}*
• 📺 Каналов для проверки: *{subscription_channels}*
• 💎 Финальных каналов: *{referral_channels}*

🛠 *Доступные действия:*
    """
}

# =============================================
# ⚙️ ТЕХНИЧЕСКИЕ НАСТРОЙКИ
# =============================================

# Режим отладки
DEBUG = True

# Время ожидания проверки подписок (секунды)
CHECK_TIMEOUT = 10

# Автоматическая проверка при старте
AUTO_CHECK_ON_START = True
