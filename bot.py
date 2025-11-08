import random
import re
from datetime import datetime
from typing import Dict, List, Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, MessageReactionHandler, ContextTypes, filters
from config import BOT_TOKEN, ADMIN_IDS


# Хранилище аукционов
# Структура: {message_id: {'number': str, 'item': str, 'participants': {user_id: {'username': str, 'name': str}}}}
auctions: Dict[int, Dict] = {}


def parse_auction_message(text: str) -> Optional[tuple]:
    """Парсит сообщение об аукционе и извлекает номер и название предмета."""
    # Паттерн: "Аукцион [номер]: [название]" или "Аукцион: [название]"
    pattern = r'Аукцион\s*(\d+)?\s*:\s*(.+)'
    match = re.match(pattern, text, re.IGNORECASE)
    if match:
        number = match.group(1) or '?'
        item = match.group(2).strip()
        return number, item
    return None


def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором."""
    return user_id in ADMIN_IDS if ADMIN_IDS else True


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    welcome_text = """
🤖 Добро пожаловать в бота для проведения аукционов!

**Как это работает:**
1. Создайте сообщение, начинающееся с "Аукцион [номер]: [название предмета]"
2. Участники ставят реакции под сообщением
3. Используйте команду /завершить для выбора победителя

**Команды:**
/start - показать это сообщение
/finish_auction или /завершить - завершить аукцион и выбрать победителя
/list_auctions - список активных аукционов
/help - справка

Удачи в аукционах! 🎲
"""
    await update.message.reply_text(welcome_text, parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help."""
    help_text = """
📖 **Справка по командам:**

/start - приветствие и инструкция
/finish_auction или /завершить - завершить аукцион и выбрать победителя
/list_auctions - показать список активных аукционов
/help - эта справка

**Формат сообщения об аукционе:**
"Аукцион 10: Клетка атаки сила"
или
"Аукцион: Клетка атаки сила"

**Как работает:**
- Бот автоматически отслеживает сообщения, начинающиеся с "Аукцион"
- Участники ставят реакции под сообщением
- Администратор использует /завершить для выбора случайного победителя
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def list_auctions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /list_auctions."""
    if not auctions:
        await update.message.reply_text("❌ Активных аукционов нет.")
        return
    
    text = "📋 **Активные аукционы:**\n\n"
    for message_id, auction_data in auctions.items():
        number = auction_data['number']
        item = auction_data['item']
        participants_count = len(auction_data['participants'])
        text += f"• Аукцион {number}: {item}\n"
        text += f"  Участников: {participants_count}\n\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')


async def finish_auction_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /finish_auction или /завершить."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
        return
    
    if not auctions:
        await update.message.reply_text("❌ Активных аукционов нет.")
        return
    
    # Если указан message_id в аргументах, завершаем конкретный аукцион
    if context.args and context.args[0].isdigit():
        message_id = int(context.args[0])
        if message_id in auctions:
            await finish_specific_auction(update, context, message_id)
            return
    
    # Иначе завершаем последний созданный аукцион
    if auctions:
        last_message_id = max(auctions.keys())
        await finish_specific_auction(update, context, last_message_id)


async def finish_specific_auction(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id: int):
    """Завершает конкретный аукцион и выбирает победителя."""
    if message_id not in auctions:
        await update.message.reply_text("❌ Аукцион не найден.")
        return
    
    auction = auctions[message_id]
    participants = auction['participants']
    
    if not participants:
        number = auction['number']
        await update.message.reply_text(f"❌ В аукционе {number} нет участников.")
        return
    
    # Случайный выбор победителя
    winner_id = random.choice(list(participants.keys()))
    winner_info = participants[winner_id]
    
    number = auction['number']
    item = auction['item']
    username = winner_info['username'] or 'без username'
    name = winner_info['name']
    
    # Формируем сообщение о победителе
    result_text = f"🏆 **Победитель аукциона {number}:** {item}\n\n"
    result_text += f"👤 @{username} ({name})"
    
    # Отправляем сообщение
    try:
        # Пытаемся отправить в тот же чат, где был аукцион
        chat_id = auction.get('chat_id')
        if chat_id:
            await context.bot.send_message(chat_id=chat_id, text=result_text, parse_mode='Markdown')
        else:
            await update.message.reply_text(result_text, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(result_text, parse_mode='Markdown')
    
    # Удаляем аукцион из активных
    del auctions[message_id]
    
    await update.message.reply_text(f"✅ Аукцион {number} завершен. Победитель объявлен!")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик новых сообщений для поиска аукционов."""
    if not update.message or not update.message.text:
        return
    
    text = update.message.text
    parsed = parse_auction_message(text)
    
    if parsed:
        number, item = parsed
        message_id = update.message.message_id
        chat_id = update.message.chat_id
        
        # Создаем запись об аукционе
        auctions[message_id] = {
            'number': number,
            'item': item,
            'participants': {},
            'chat_id': chat_id,
            'created_at': datetime.now()
        }
        
        await update.message.reply_text(
            f"✅ Аукцион {number} зарегистрирован!\n"
            f"📦 Предмет: {item}\n"
            f"👥 Ставьте реакции для участия!"
        )


async def handle_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик реакций под сообщениями."""
    if not update.message_reaction:
        return
    
    message_reaction = update.message_reaction
    message_id = message_reaction.message_id
    chat_id = message_reaction.chat.id
    
    # Проверяем, есть ли это сообщение в списке аукционов
    if message_id not in auctions:
        return
    
    auction = auctions[message_id]
    user = message_reaction.user
    
    # Получаем новые и старые реакции
    new_reactions = message_reaction.new_reaction or []
    old_reactions = message_reaction.old_reaction or []
    
    # Если есть новые реакции, добавляем пользователя
    if new_reactions:
        # Получаем информацию о пользователе
        try:
            member = await context.bot.get_chat_member(chat_id, user.id)
            username = member.user.username or ''
            name = member.user.full_name or f"User {user.id}"
        except:
            username = user.username or ''
            name = user.full_name or f"User {user.id}"
        
        auction['participants'][user.id] = {
            'username': username,
            'name': name
        }
    
    # Если все реакции удалены, убираем пользователя
    if old_reactions and not new_reactions and user.id in auction['participants']:
        del auction['participants'][user.id]


def main():
    """Запуск бота."""
    if not BOT_TOKEN:
        print("❌ Ошибка: BOT_TOKEN не установлен!")
        print("Создайте файл .env и добавьте BOT_TOKEN=ваш_токен")
        return
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("finish_auction", finish_auction_command))
    application.add_handler(CommandHandler("завершить", finish_auction_command))
    application.add_handler(CommandHandler("list_auctions", list_auctions_command))
    
    # Регистрируем обработчики сообщений и реакций
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageReactionHandler(handle_reaction))
    
    # Запускаем бота
    print("🤖 Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

