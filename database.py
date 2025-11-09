import sqlite3
import json
from datetime import datetime

def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect('groups.db')
    cursor = conn.cursor()
    
    # Таблица очереди проверок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS check_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER,
            group_title TEXT,
            user_id INTEGER,
            invite_link TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица результатов проверок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS group_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER,
            group_title TEXT,
            user_id INTEGER,
            bot_check_result TEXT,
            userbot_check_result TEXT,
            final_result BOOLEAN,
            issues TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица для очереди на выход
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leave_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER,
            reason TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

def add_to_queue(group_id, group_title, user_id, invite_link):
    """Добавляем группу в очередь на проверку"""
    conn = sqlite3.connect('groups.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO check_queue (group_id, group_title, user_id, invite_link) VALUES (?, ?, ?, ?)',
        (group_id, group_title, user_id, invite_link)
    )
    queue_id = cursor.lastrowid
    conn.commit()
    conn.close()
    print(f"✅ Группа {group_title} добавлена в очередь (ID: {queue_id})")
    return queue_id

def update_queue_status(queue_id, status):
    """Обновляем статус в очереди"""
    conn = sqlite3.connect('groups.db')
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE check_queue SET status = ? WHERE id = ?',
        (status, queue_id)
    )
    conn.commit()
    conn.close()

def get_pending_checks():
    """Получаем ожидающие проверки"""
    conn = sqlite3.connect('groups.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM check_queue WHERE status = "pending"')
    pending = cursor.fetchall()
    conn.close()
    return pending

def save_check_result(group_id, group_title, user_id, bot_result, userbot_result, final_result, issues):
    """Сохраняем результаты проверки"""
    conn = sqlite3.connect('groups.db')
    cursor = conn.cursor()
    cursor.execute(
        '''INSERT INTO group_checks 
        (group_id, group_title, user_id, bot_check_result, userbot_check_result, final_result, issues) 
        VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (group_id, group_title, user_id, json.dumps(bot_result), json.dumps(userbot_result), final_result, issues)
    )
    conn.commit()
    conn.close()
    print(f"✅ Результаты проверки для {group_title} сохранены")

def get_userbot_result(group_id):
    """Получаем результаты UserBot для группы"""
    conn = sqlite3.connect('groups.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT userbot_check_result FROM group_checks WHERE group_id = ?',
        (group_id,)
    )
    result = cursor.fetchone()
    conn.close()
    
    if result and result[0]:
        return json.loads(result[0])
    return None

def is_check_complete(group_id):
    """Проверяем, завершена ли проверка группы"""
    conn = sqlite3.connect('groups.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT userbot_check_result FROM group_checks WHERE group_id = ?',
        (group_id,)
    )
    result = cursor.fetchone()
    conn.close()
    
    return result is not None and result[0] is not None

def add_to_leave_queue(group_id, reason="manual"):
    """Добавляем группу в очередь на выход"""
    conn = sqlite3.connect('groups.db')
    cursor = conn.cursor()
    
    cursor.execute(
        'INSERT INTO leave_queue (group_id, reason) VALUES (?, ?)',
        (group_id, reason)
    )
    queue_id = cursor.lastrowid
    conn.commit()
    conn.close()
    print(f"✅ Группа {group_id} добавлена в очередь на выход (ID: {queue_id})")
    return queue_id
