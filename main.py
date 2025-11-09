import asyncio
import logging
import multiprocessing
import time
import sys
import os
from datetime import datetime

# Добавляем текущую директорию в путь для импортов
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_system.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

def run_main_bot():
    """Запуск основного бота в отдельном процессе"""
    try:
        from main_bot import main as main_bot_main
        print("🚀 Запускаю основного бота...")
        main_bot_main()
    except Exception as e:
        logger.error(f"❌ Ошибка запуска основного бота: {e}")
        print(f"❌ Ошибка основного бота: {e}")

def run_userbot():
    """Запуск UserBot в отдельном процессе"""
    try:
        from userbot import main_userbot
        print("🚀 Запускаю UserBot...")
        asyncio.run(main_userbot())
    except Exception as e:
        logger.error(f"❌ Ошибка запуска UserBot: {e}")
        print(f"❌ Ошибка UserBot: {e}")

def check_dependencies():
    """Проверка наличия всех необходимых зависимостей"""
    required_modules = [
        'telegram',
        'telethon',
        'sqlite3',
        'aiosqlite'
    ]
    
    missing_modules = []
    for module in required_modules:
        try:
            if module == 'telegram':
                import telegram
            elif module == 'telethon':
                import telethon
            elif module == 'sqlite3':
                import sqlite3
            elif module == 'aiosqlite':
                import aiosqlite
        except ImportError:
            missing_modules.append(module)
    
    if missing_modules:
        print("❌ Отсутствуют необходимые модули:")
        for module in missing_modules:
            print(f"   - {module}")
        print("\n📦 Установите их командой:")
        print("pip install python-telegram-bot telethon aiosqlite")
        return False
    
    return True

def check_config():
    """Проверка конфигурации"""
    try:
        from config import BOT_TOKEN, USERBOT_API_ID, USERBOT_API_HASH, ADMIN_ID
        
        if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN":
            print("❌ Не настроен BOT_TOKEN в config.py")
            return False
        
        if not USERBOT_API_ID or USERBOT_API_ID == "YOUR_API_ID":
            print("❌ Не настроен USERBOT_API_ID в config.py")
            return False
            
        if not USERBOT_API_HASH or USERBOT_API_HASH == "YOUR_API_HASH":
            print("❌ Не настроен USERBOT_API_HASH в config.py")
            return False
            
        if not ADMIN_ID or ADMIN_ID == "YOUR_ADMIN_ID":
            print("❌ Не настроен ADMIN_ID в config.py")
            return False
            
        return True
        
    except ImportError as e:
        print("❌ Файл config.py не найден или содержит ошибки")
        print(f"Ошибка: {e}")
        return False
    except Exception as e:
        print(f"❌ Ошибка проверки конфигурации: {e}")
        return False

def show_status():
    """Показать статус системы"""
    print("\n" + "="*50)
    print("🤖 СИСТЕМА БОТА-ОЦЕНЩИКА ГРУПП")
    print("="*50)
    print(f"📅 Дата запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("👥 Запуск в режиме:")
    print("   • Основной бот (Telegram Bot API)")
    print("   • UserBot (Telethon)")
    print("\n⚙️  Функциональность:")
    print("   ✅ Проверка прав администратора")
    print("   ✅ Веб-анализ группы")
    print("   ✅ UserBot анализ (гео-данные, импорт сообщений)")
    print("   ✅ Определение даты создания по первому сообщению")
    print("   ✅ Статистика участников и сообщений")
    print("   ✅ Полный отчет в группу и ЛС")
    print("="*50)

def main():
    """Основная функция запуска"""
    
    # Показываем статус системы
    show_status()
    
    # Проверяем зависимости
    print("\n🔍 Проверяю зависимости...")
    if not check_dependencies():
        sys.exit(1)
    print("✅ Все зависимости установлены")
    
    # Проверяем конфигурацию
    print("🔧 Проверяю конфигурацию...")
    if not check_config():
        print("\n❌ Настройте config.py перед запуском:")
        print("   1. Получите BOT_TOKEN у @BotFather")
        print("   2. Получите API_ID и API_HASH на my.telegram.org")
        print("   3. Укажите ваш ADMIN_ID (можно получить у @userinfobot)")
        sys.exit(1)
    print("✅ Конфигурация корректна")
    
    # Инициализируем базу данных
    try:
        from database import init_db
        init_db()
        print("✅ База данных инициализирована")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        print("❌ Ошибка базы данных")
        sys.exit(1)
    
    print("\n🎯 Запускаю систему...")
    print("💡 Для остановки нажмите Ctrl+C")
    
    # Создаем процессы для ботов
    processes = []
    
    try:
        # Запускаем основной бот
        main_bot_process = multiprocessing.Process(target=run_main_bot)
        main_bot_process.daemon = True
        main_bot_process.start()
        processes.append(main_bot_process)
        print("✅ Основной бот запущен")
        
        # Ждем немного перед запуском UserBot
        time.sleep(3)
        
        # Запускаем UserBot
        userbot_process = multiprocessing.Process(target=run_userbot)
        userbot_process.daemon = True
        userbot_process.start()
        processes.append(userbot_process)
        print("✅ UserBot запущен")
        
        print("\n🎉 Система успешно запущена!")
        print("📱 Добавьте бота в группу для начала проверки")
        print("⏳ Ожидайте обработки очереди...")
        
        # Бесконечный цикл для поддержания работы процессов
        while True:
            time.sleep(1)
            
            # Проверяем статус процессов
            for i, process in enumerate(processes):
                if not process.is_alive():
                    if i == 0:
                        print("❌ Основной бот остановился, перезапускаю...")
                        new_process = multiprocessing.Process(target=run_main_bot)
                        new_process.daemon = True
                        new_process.start()
                        processes[i] = new_process
                    else:
                        print("❌ UserBot остановился, перезапускаю...")
                        new_process = multiprocessing.Process(target=run_userbot)
                        new_process.daemon = True
                        new_process.start()
                        processes[i] = new_process
            
    except KeyboardInterrupt:
        print("\n\n🛑 Останавливаю систему...")
        
        # Останавливаем процессы
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        
        print("👋 Система остановлена")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка системы: {e}")
        print(f"❌ Критическая ошибка: {e}")
        
        # Останавливаем процессы
        for process in processes:
            if process.is_alive():
                process.terminate()
        
        sys.exit(1)

if __name__ == "__main__":
    main()
