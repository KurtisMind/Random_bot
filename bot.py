import random
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pytz
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, MessageReactionHandler, ContextTypes, filters
from config import BOT_TOKEN, ADMIN_IDS

# Московское время
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# Хранилище аукционов
# Структура: {message_id: {'number': str, 'item': str, 'participants': {user_id: {'username': str, 'name': str}}, 
#                          'status_message_id': int, 'chat_id': int, 'finish_time': datetime, 'job': Job}}
auctions: Dict[int, Dict] = {}


def parse_auction_message(text: str) -> Optional[tuple]:
    """Парсит сообщение об аукционе и извлекает номер, название предмета и время завершения."""
    # Паттерн: "Аукцион [номер]: [название]" или "Аукцион: [название]"
    # Также ищем время завершения: "через N часов" или "в HH:MM"
    pattern = r'Аукцион\s*(\d+)?\s*:\s*(.+?)(?:\s+через\s+(\d+)\s+час(?:ов|а)?)?(?:\s+в\s+(\d{1,2}):(\d{2}))?$'
    match = re.match(pattern, text, re.IGNORECASE)
    if match:
        number = match.group(1) or '?'
        item = match.group(2).strip()
        hours = match.group(3)
        hour = match.group(4)
        minute = match.group(5)
        
        finish_time = None
        if hours:
            # Завершение через N часов
            finish_time = datetime.now(MOSCOW_TZ) + timedelta(hours=int(hours))
        elif hour and minute:
            # Завершение в определенное время (сегодня или завтра)
            now = datetime.now(MOSCOW_TZ)
            finish_time = now.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
            if finish_time <= now:
                finish_time += timedelta(days=1)
        
        return number, item, finish_time
    return None


def format_participants_list(participants: Dict) -> str:
    """Форматирует список участников для отображения."""
    if not participants:
        return "👥 Участников пока нет"
    
    text = f"👥 **Участников: {len(participants)}**\n\n"
    for idx, (user_id, info) in enumerate(participants.items(), 1):
        username = info['username'] or 'без username'
        name = info['name']
        text += f"{idx}. @{username} ({name})\n"
    
    return text


def format_finish_time(finish_time: Optional[datetime]) -> str:
    """Форматирует время завершения аукциона."""
    if not finish_time:
        return "⏰ Завершение: по команде администратора"
    
    moscow_time = finish_time.astimezone(MOSCOW_TZ)
    time_str = moscow_time.strftime("%H:%M %d.%m.%Y")
    return f"⏰ Завершение: {time_str} (МСК)"


async def update_auction_status(context: ContextTypes.DEFAULT_TYPE, message_id: int):
    """Обновляет сообщение со статусом аукциона."""
    if message_id not in auctions:
        return
    
    auction = auctions[message_id]
    status_message_id = auction.get('status_message_id')
    chat_id = auction.get('chat_id')
    
    if not status_message_id or not chat_id:
        return
    
    number = auction['number']
    item = auction['item']
    participants = auction['participants']
    finish_time = auction.get('finish_time')
    
    # Формируем текст сообщения
    text = f"🎯 **Аукцион {number}: {item}**\n\n"
    text += format_participants_list(participants) + "\n\n"
    text += format_finish_time(finish_time)
    
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_message_id,
            text=text,
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"Ошибка при обновлении сообщения: {e}")


def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором."""
    return user_id in ADMIN_IDS if ADMIN_IDS else True


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    welcome_text = """
🤖 Добро пожаловать в бота для проведения аукционов!

**Как это работает:**
1. Создайте сообщение, начинающееся с "Аукцион [номер]: [название предмета]"
2. Можно указать время завершения: "через N часов" или "в HH:MM"
3. Участники ставят реакции под сообщением
4. Бот автоматически обновляет список участников
5. Аукцион завершится автоматически или по команде /завершить

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
"Аукцион 10: Клетка атаки сила через 2 часа"
"Аукцион 10: Клетка атаки сила в 20:00"

**Как работает:**
- Бот автоматически отслеживает сообщения, начинающиеся с "Аукцион"
- Участники ставят реакции под сообщением
- Бот обновляет список участников в реальном времени
- Аукцион завершится автоматически в указанное время или по команде администратора
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
        finish_time = auction_data.get('finish_time')
        text += f"• Аукцион {number}: {item}\n"
        text += f"  Участников: {participants_count}\n"
        if finish_time:
            moscow_time = finish_time.astimezone(MOSCOW_TZ)
            text += f"  Завершение: {moscow_time.strftime('%H:%M %d.%m')}\n"
        text += "\n"
    
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
    
    # Отменяем запланированное завершение, если есть
    job = auction.get('job')
    if job:
        job.schedule_removal()
    
    if not participants:
        number = auction['number']
        await update.message.reply_text(f"❌ В аукционе {number} нет участников.")
        # Удаляем статус-сообщение
        status_message_id = auction.get('status_message_id')
        chat_id = auction.get('chat_id')
        if status_message_id and chat_id:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=status_message_id)
            except:
                pass
        del auctions[message_id]
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
    
    # Удаляем статус-сообщение
    status_message_id = auction.get('status_message_id')
    chat_id = auction.get('chat_id')
    if status_message_id and chat_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=status_message_id)
        except:
            pass
    
    # Отправляем сообщение
    try:
        if chat_id:
            await context.bot.send_message(chat_id=chat_id, text=result_text, parse_mode='Markdown')
        else:
            await update.message.reply_text(result_text, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(result_text, parse_mode='Markdown')
    
    # Удаляем аукцион из активных
    del auctions[message_id]
    
    await update.message.reply_text(f"✅ Аукцион {number} завершен. Победитель объявлен!")


async def auto_finish_auction(context: ContextTypes.DEFAULT_TYPE):
    """Автоматически завершает аукцион по истечении времени."""
    message_id = context.job.data
    if message_id not in auctions:
        return
    
    auction = auctions[message_id]
    chat_id = auction.get('chat_id')
    
    if not chat_id:
        return
    
    participants = auction['participants']
    
    if not participants:
        # Нет участников - просто удаляем
        status_message_id = auction.get('status_message_id')
        if status_message_id:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=status_message_id)
            except:
                pass
        del auctions[message_id]
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Аукцион {auction['number']} завершен. Участников не было."
        )
        return
    
    # Выбираем победителя
    winner_id = random.choice(list(participants.keys()))
    winner_info = participants[winner_id]
    
    number = auction['number']
    item = auction['item']
    username = winner_info['username'] or 'без username'
    name = winner_info['name']
    
    # Удаляем статус-сообщение
    status_message_id = auction.get('status_message_id')
    if status_message_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=status_message_id)
        except:
            pass
    
    # Отправляем сообщение о победителе
    result_text = f"🏆 **Победитель аукциона {number}:** {item}\n\n"
    result_text += f"👤 @{username} ({name})"
    
    await context.bot.send_message(chat_id=chat_id, text=result_text, parse_mode='Markdown')
    
    # Удаляем аукцион
    del auctions[message_id]


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик новых сообщений для поиска аукционов."""
    if not update.message or not update.message.text:
        return
    
    text = update.message.text
    parsed = parse_auction_message(text)
    
    if parsed:
        number, item, finish_time = parsed
        message_id = update.message.message_id
        chat_id = update.message.chat_id
        
        # Создаем запись об аукционе
        auctions[message_id] = {
            'number': number,
            'item': item,
            'participants': {},
            'chat_id': chat_id,
            'created_at': datetime.now(MOSCOW_TZ),
            'finish_time': finish_time
        }
        
        # Создаем статус-сообщение
        status_text = f"🎯 **Аукцион {number}: {item}**\n\n"
        status_text += format_participants_list({}) + "\n\n"
        status_text += format_finish_time(finish_time)
        
        status_message = await update.message.reply_text(status_text, parse_mode='Markdown')
        auctions[message_id]['status_message_id'] = status_message.message_id
        
        # Планируем автоматическое завершение, если указано время
        if finish_time:
            # Вычисляем время до завершения
            now = datetime.now(MOSCOW_TZ)
            delay = (finish_time - now).total_seconds()
            
            if delay > 0:
                job = context.job_queue.run_once(
                    auto_finish_auction,
                    when=delay,
                    data=message_id,
                    name=f"finish_auction_{message_id}"
                )
                auctions[message_id]['job'] = job


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
        # Обновляем статус-сообщение
        await update_auction_status(context, message_id)
    
    # Если все реакции удалены, убираем пользователя
    if old_reactions and not new_reactions and user.id in auction['participants']:
        del auction['participants'][user.id]
        # Обновляем статус-сообщение
        await update_auction_status(context, message_id)


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
