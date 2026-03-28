import database as db
import json
from datetime import datetime, timedelta

def init_promocodes_table():
    """Создает таблицу для промокодов"""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promocodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            discount_type TEXT,
            discount_value REAL,
            valid_from TEXT,
            valid_to TEXT,
            usage_limit INTEGER,
            used_count INTEGER DEFAULT 0,
            min_order_amount REAL DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promocode_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            promocode_id INTEGER,
            user_id INTEGER,
            order_id INTEGER,
            used_at TEXT,
            FOREIGN KEY (promocode_id) REFERENCES promocodes(id)
        )
    ''')
    
    conn.commit()
    conn.close()

def create_promocode(code, discount_type, discount_value, valid_days=30, usage_limit=0, min_order_amount=0):
    """Создает новый промокод"""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    valid_from = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    valid_to = (datetime.now() + timedelta(days=valid_days)).strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        cursor.execute('''
            INSERT INTO promocodes (code, discount_type, discount_value, valid_from, valid_to, 
                                   usage_limit, min_order_amount, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (code.upper(), discount_type, discount_value, valid_from, valid_to, 
              usage_limit, min_order_amount, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        promocode_id = cursor.lastrowid
        conn.commit()
        return promocode_id, True, "Промокод создан"
    except Exception as e:
        return None, False, f"Ошибка: {e}"
    finally:
        conn.close()

def validate_promocode(code, user_id, order_amount):
    """Проверяет промокод"""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        SELECT * FROM promocodes 
        WHERE code = ? AND is_active = 1 
        AND valid_from <= ? AND valid_to >= ?
    ''', (code.upper(), now, now))
    
    promocode = cursor.fetchone()
    
    if not promocode:
        conn.close()
        return None, "Промокод не найден или истек срок действия"
    
    # Проверяем лимит использования
    if promocode['usage_limit'] > 0 and promocode['used_count'] >= promocode['usage_limit']:
        conn.close()
        return None, "Промокод больше не действителен (достигнут лимит использований)"
    
    # Проверяем минимальную сумму заказа
    if order_amount < promocode['min_order_amount']:
        conn.close()
        return None, f"Минимальная сумма заказа для этого промокода: {promocode['min_order_amount']}₽"
    
    conn.close()
    return promocode, None

def apply_discount(amount, promocode):
    """Применяет скидку к сумме"""
    if promocode['discount_type'] == 'percentage':
        discount = amount * (promocode['discount_value'] / 100)
        return amount - discount, discount, f"{promocode['discount_value']}%"
    elif promocode['discount_type'] == 'fixed':
        discount = min(promocode['discount_value'], amount)
        return amount - discount, discount, f"{promocode['discount_value']}₽"
    return amount, 0, "0"

def use_promocode(promocode_id, user_id, order_id):
    """Отмечает использование промокода"""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    # Обновляем счетчик использований
    cursor.execute('''
        UPDATE promocodes SET used_count = used_count + 1 
        WHERE id = ?
    ''', (promocode_id,))
    
    # Записываем использование
    cursor.execute('''
        INSERT INTO promocode_usage (promocode_id, user_id, order_id, used_at)
        VALUES (?, ?, ?, ?)
    ''', (promocode_id, user_id, order_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    
    conn.commit()
    conn.close()

def get_all_promocodes():
    """Получает все промокоды"""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM promocodes ORDER BY created_at DESC')
    promocodes = cursor.fetchall()
    conn.close()
    return promocodes

def deactivate_promocode(promocode_id):
    """Деактивирует промокод"""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE promocodes SET is_active = 0 WHERE id = ?', (promocode_id,))
    conn.commit()
    conn.close()