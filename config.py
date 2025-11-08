import os
from dotenv import load_dotenv

load_dotenv()

# Токен бота (получить у @BotFather)
BOT_TOKEN = os.getenv('BOT_TOKEN', '')

# ID администраторов (можно добавить несколько через запятую)
ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS', '').split(',') if id.strip()]

