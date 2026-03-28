import sqlite3
from datetime import datetime, timedelta
import config
import json
import pandas as pd
import io
import promocodes
import zipfile
import os
import shutil

def get_db_connection():
    conn = sqlite3.connect(config.DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Инициализация базы данных"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            balance REAL DEFAULT 0,
            total_spent REAL DEFAULT 0,
            referrals_count INTEGER DEFAULT 0,
            joined_at TEXT,
            is_banned INTEGER DEFAULT 0
        )
    ''')
    
    # Таблица категорий
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            name TEXT,
            emoji TEXT,
            is_active INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0,
            created_at TEXT
        )
    ''')
    
    # Таблица товаров
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            price REAL,
            cost_price REAL DEFAULT 0,
            stock INTEGER DEFAULT 0,
            category_id INTEGER,
            image_id TEXT,
            is_preorder INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (category_id) REFERENCES categories(id)
        )
    ''')
    
    # Таблица корзины
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cart (
            user_id INTEGER,
            product_id INTEGER,
            quantity INTEGER DEFAULT 1,
            PRIMARY KEY (user_id, product_id)
        )
    ''')
    
    # Таблица для хранения ID последних сообщений
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS last_messages (
            user_id INTEGER PRIMARY KEY,
            message_id INTEGER
        )
    ''')
    
    # Таблица заказов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            items TEXT,
            total_amount REAL,
            total_cost REAL DEFAULT 0,
            username TEXT,
            payment_method TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        )
    ''')
    
    # Таблица настроек
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # Таблица дизайна
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS design_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            description TEXT
        )
    ''')
    
    # Таблица баннеров
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS banners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            image_id TEXT,
            is_active INTEGER DEFAULT 0,
            created_at TEXT
        )
    ''')

    # Таблица конкурсов (ДОБАВЬТЕ ЭТОТ БЛОК)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            prize TEXT,
            winners_count INTEGER DEFAULT 1,
            start_date TEXT,
            end_date TEXT,
            criteria TEXT,
            criteria_value TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT
        )
    ''')

    # Таблица участников конкурсов (тоже понадобится)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contest_participants (
            contest_id INTEGER,
            user_id INTEGER,
            joined_at TEXT,
            PRIMARY KEY (contest_id, user_id)
        )
    ''')
    
    conn.commit()
    
    # Добавляем стандартные категории, если их нет
    cursor.execute('SELECT COUNT(*) FROM categories')
    if cursor.fetchone()[0] == 0:
        default_categories = [
            ('pods', 'Одноразовые вейпы', '💨', 1),
            ('liquid', 'Жидкости', '🧪', 2),
            ('devices', 'Pod-системы', '📟', 3),
            ('accessories', 'Аксессуары', '🔧', 4),
            ('preorder', 'Предзаказы', '⏰', 5),
        ]
        for code, name, emoji, sort_order in default_categories:
            cursor.execute('''
                INSERT INTO categories (code, name, emoji, sort_order, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (code, name, emoji, sort_order, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    
    # Добавляем настройки дизайна по умолчанию
    default_design = [
        ('primary_color', '#2ecc71', 'Основной цвет'),
        ('secondary_color', '#3498db', 'Вторичный цвет'),
        ('accent_color', '#f39c12', 'Акцентный цвет'),
        ('text_color', '#ffffff', 'Цвет текста'),
        ('welcome_text', '👋 Добро пожаловать в наш магазин!', 'Текст приветствия'),
        ('shop_name', '💨 VAPE SHOP', 'Название магазина'),
        ('shop_description', 'Лучшие вейпы и жидкости', 'Описание магазина'),
        ('footer_text', '✨ Спасибо, что выбираете нас!', 'Текст в подвале')
    ]
    
    for key, value, desc in default_design:
        cursor.execute('''
            INSERT OR IGNORE INTO design_settings (key, value, description)
            VALUES (?, ?, ?)
        ''', (key, value, desc))
    
    # Добавляем настройку last_reset
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('last_reset', '1970-01-01 00:00:00')")
    
    conn.commit()
    conn.close()
    print("База данных успешно инициализирована")

# --- ФУНКЦИИ ЗАКАЗОВ ---

def create_order(user_id, items_json, total, total_cost, username, payment_method):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO orders (user_id, items, total_amount, total_cost, username, payment_method, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, items_json, total, total_cost, username, payment_method, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    order_id = cursor.lastrowid
    cursor.execute('UPDATE users SET total_spent = total_spent + ? WHERE user_id = ?', (total, user_id))
    conn.commit()
    conn.close()
    return order_id

def get_order(order_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM orders WHERE id = ?', (order_id,))
    order = cursor.fetchone()
    conn.close()
    return order

def update_order_status(order_id, new_status):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE orders SET status = ? WHERE id = ?', (new_status, order_id))
    conn.commit()
    conn.close()

def get_admin_orders(filter_status=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if filter_status:
        cursor.execute('SELECT * FROM orders WHERE status = ? ORDER BY created_at DESC', (filter_status,))
    else:
        cursor.execute('SELECT * FROM orders ORDER BY created_at DESC LIMIT 50')
    orders = cursor.fetchall()
    conn.close()
    return orders

def get_all_orders():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM orders ORDER BY created_at DESC LIMIT 20')
    orders = cursor.fetchall()
    conn.close()
    return orders

def get_user_orders(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
    orders = cursor.fetchall()
    conn.close()
    return orders

# --- ФУНКЦИИ ПОЛЬЗОВАТЕЛЕЙ ---

def add_user(user_id, username, full_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, full_name, joined_at)
        VALUES (?, ?, ?, ?)
    ''', (user_id, username, full_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def get_user(user_id):
    """Получает пользователя"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    if user:
        # Преобразуем sqlite3.Row в словарь
        return {key: user[key] for key in user.keys()}
    return None

def get_top_users(limit=10):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT full_name, total_spent FROM users ORDER BY total_spent DESC LIMIT ?', (limit,))
    users = cursor.fetchall()
    conn.close()
    return users

def get_all_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

def get_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*), SUM(total_amount) FROM orders')
    res = cursor.fetchone()
    total_orders = res[0] if res[0] else 0
    total_revenue = res[1] if res[1] else 0
    conn.close()
    return total_users, total_orders, total_revenue

def get_total_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_profit_stats():
    """Считает прибыль ТОЛЬКО с момента последнего сброса"""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Сначала узнаем дату сброса
    try:
        cursor.execute("SELECT value FROM settings WHERE key = 'last_reset'")
        last_reset = cursor.fetchone()[0]
    except:
        last_reset = '1970-01-01 00:00:00'

    # Считаем данные с фильтром по дате
    cursor.execute('SELECT SUM(total_amount) FROM orders WHERE created_at >= ?', (last_reset,))
    rev = cursor.fetchone()[0] or 0
    cursor.execute('SELECT SUM(total_cost) FROM orders WHERE created_at >= ?', (last_reset,))
    cost = cursor.fetchone()[0] or 0
    cursor.execute('SELECT COUNT(*) FROM orders WHERE created_at >= ?', (last_reset,))
    orders = cursor.fetchone()[0] or 0
    
    conn.close()
    return rev, cost, rev - cost, orders

def get_profit_by_period(days=30):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT SUM(total_amount), SUM(total_cost), COUNT(*)
        FROM orders 
        WHERE created_at >= datetime('now', '-' || ? || ' days')
    ''', (days,))
    result = cursor.fetchone()
    conn.close()
    total_revenue = result[0] or 0
    total_cost = result[1] or 0
    total_orders = result[2] or 0
    return total_revenue, total_cost, total_revenue - total_cost, total_orders

# --- ФУНКЦИИ КОРЗИНЫ ---

def add_to_cart(user_id, product_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO cart (user_id, product_id, quantity)
        VALUES (?, ?, 1)
        ON CONFLICT(user_id, product_id) DO UPDATE SET quantity = quantity + 1
    ''', (user_id, product_id))
    conn.commit()
    conn.close()

def get_cart_items(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.id, p.name, p.price, c.quantity 
        FROM cart c JOIN products p ON c.product_id = p.id 
        WHERE c.user_id = ?
    ''', (user_id,))
    items = cursor.fetchall()
    conn.close()
    return items

def get_cart_total(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT SUM(p.price * c.quantity) 
        FROM cart c JOIN products p ON c.product_id = p.id 
        WHERE c.user_id = ?
    ''', (user_id,))
    total = cursor.fetchone()[0]
    conn.close()
    return total if total else 0

def clear_cart(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM cart WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def remove_from_cart(user_id, product_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM cart WHERE user_id = ? AND product_id = ?', (user_id, product_id))
    conn.commit()
    conn.close()

# --- ФУНКЦИИ ТОВАРОВ ---

def add_product(name, description, price, cost_price, stock, category_id, image_id, is_preorder=0):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO products (name, description, price, cost_price, stock, category_id, image_id, is_preorder)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (name, description, price, cost_price, stock, category_id, image_id, is_preorder))
    conn.commit()
    conn.close()

def update_product_stock(product_id, quantity_change):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE products SET stock = stock + ? WHERE id = ?', (quantity_change, product_id))
    conn.commit()
    conn.close()

def get_product(product_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products WHERE id = ?', (product_id,))
    product = cursor.fetchone()
    conn.close()
    return product

def get_products_by_category_id(category_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM products 
        WHERE category_id = ? AND is_active = 1 
        ORDER BY is_preorder DESC, name
    ''', (category_id,))
    products = cursor.fetchall()
    conn.close()
    return products

def check_product_availability(product_id, quantity=1):
    product = get_product(product_id)
    if product and product['is_preorder']:
        return True
    if product and product['stock'] >= quantity:
        return True
    return False

def get_low_stock_products(threshold=5):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM products 
        WHERE stock <= ? AND stock > 0 AND is_preorder = 0
        ORDER BY stock ASC
    ''', (threshold,))
    products = cursor.fetchall()
    conn.close()
    return products

def get_out_of_stock_products():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM products 
        WHERE stock <= 0 AND is_preorder = 0 AND is_active = 1
    ''')
    products = cursor.fetchall()
    conn.close()
    return products

def disable_out_of_stock_products():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE products 
        SET is_active = 0 
        WHERE stock <= 0 AND is_preorder = 0
    ''')
    conn.commit()
    conn.close()

def delete_product(product_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM products WHERE id = ?', (product_id,))
    cursor.execute('DELETE FROM cart WHERE product_id = ?', (product_id,))
    conn.commit()
    conn.close()


def init_settings():
    """Создает таблицу настроек, если её нет"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings 
                      (key TEXT PRIMARY KEY, value TEXT)''')
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('last_reset', '1970-01-01 00:00:00')")
    conn.commit()
    conn.close()

def reset_profit_stats():
    """Устанавливает текущее время как точку нового отсчета"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_reset', ?)", (now,))
    conn.commit()
    conn.close()

# ОБНОВЛЕННАЯ ФУНКЦИЯ (замените старую)
def init_settings():
    """Создает таблицу настроек, если её нет"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings 
                      (key TEXT PRIMARY KEY, value TEXT)''')
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('last_reset', '1970-01-01 00:00:00')")
    conn.commit()
    conn.close()

def get_report_text():
    """Текст для файла .txt"""
    # Берем вашу существующую функцию за 30 дней
    rev, cost, prof, counts = get_profit_by_period(30)
    return (f"=== ОТЧЕТ ЗА 30 ДНЕЙ ===\nДата: {datetime.now()}\n"
            f"Выручка: {rev}\nСебестоимость: {cost}\nПрибыль: {prof}\nЗаказов: {counts}")

# --- ФУНКЦИИ ДЛЯ КАТЕГОРИЙ ---

def get_all_categories(include_inactive=False):
    conn = get_db_connection()
    cursor = conn.cursor()
    if include_inactive:
        cursor.execute('SELECT * FROM categories ORDER BY sort_order')
    else:
        cursor.execute('SELECT * FROM categories WHERE is_active = 1 ORDER BY sort_order')
    categories = cursor.fetchall()
    conn.close()
    return categories

def get_category(category_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM categories WHERE id = ?', (category_id,))
    category = cursor.fetchone()
    conn.close()
    return category

def get_category_by_code(code):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM categories WHERE code = ?', (code,))
    category = cursor.fetchone()
    conn.close()
    return category

def add_category(code, name, emoji, sort_order=0):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO categories (code, name, emoji, sort_order, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (code, name, emoji, sort_order, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def update_category(category_id, name=None, emoji=None, is_active=None, sort_order=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    category = get_category(category_id)
    if category:
        new_name = name if name is not None else category['name']
        new_emoji = emoji if emoji is not None else category['emoji']
        new_is_active = is_active if is_active is not None else category['is_active']
        new_sort_order = sort_order if sort_order is not None else category['sort_order']
        cursor.execute('''
            UPDATE categories 
            SET name=?, emoji=?, is_active=?, sort_order=?
            WHERE id=?
        ''', (new_name, new_emoji, new_is_active, new_sort_order, category_id))
        conn.commit()
    conn.close()

def delete_category(category_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM products WHERE category_id = ?', (category_id,))
    count = cursor.fetchone()[0]
    if count == 0:
        cursor.execute('DELETE FROM categories WHERE id = ?', (category_id,))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

async def save_message(user_id, message_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('REPLACE INTO last_messages (user_id, message_id) VALUES (?, ?)', (user_id, message_id))
    conn.commit()
    conn.close()

async def get_last_message_id(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT message_id FROM last_messages WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

# --- ФУНКЦИИ ДЛЯ КОНКУРСОВ ---

def init_contests_table():
    """Создает таблицу для конкурсов"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Таблица конкурсов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            start_date TEXT,
            end_date TEXT,
            criteria_type TEXT,
            criteria_value TEXT,
            prize TEXT,
            is_active INTEGER DEFAULT 1,
            winners_count INTEGER DEFAULT 1,
            created_at TEXT,
            winners TEXT
        )
    ''')
    
    # Таблица участников конкурсов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contest_participants (
            contest_id INTEGER,
            user_id INTEGER,
            join_date TEXT,
            is_winner INTEGER DEFAULT 0,
            FOREIGN KEY (contest_id) REFERENCES contests(id),
            PRIMARY KEY (contest_id, user_id)
        )
    ''')
    
    conn.commit()
    conn.close()

def create_contest(name, description, start_date, end_date, criteria_type, criteria_value, prize, winners_count=1):
    """Создает новый конкурс"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO contests (name, description, start_date, end_date, criteria_type, criteria_value, prize, winners_count, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (name, description, start_date, end_date, criteria_type, criteria_value, prize, winners_count, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    contest_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return contest_id

def get_active_contest():
    """Получает активный конкурс"""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        SELECT * FROM contests 
        WHERE is_active = 1 AND end_date > ? AND start_date <= ?
        ORDER BY id DESC LIMIT 1
    ''', (now, now))
    contest = cursor.fetchone()
    conn.close()
    return contest

def get_all_contests(include_inactive=False):
    """Получает все конкурсы"""
    conn = get_db_connection()
    cursor = conn.cursor()
    if include_inactive:
        cursor.execute('SELECT * FROM contests ORDER BY created_at DESC')
    else:
        cursor.execute('SELECT * FROM contests WHERE is_active = 1 ORDER BY created_at DESC')
    contests = cursor.fetchall()
    conn.close()
    return contests

def get_contest(contest_id):
    """Получает конкурс по ID"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM contests WHERE id = ?', (contest_id,))
    contest = cursor.fetchone()
    conn.close()
    return contest

def update_contest(contest_id, **kwargs):
    """Обновляет данные конкурса"""
    conn = get_db_connection()
    cursor = conn.cursor()
    allowed_fields = ['name', 'description', 'start_date', 'end_date', 'criteria_type', 
                      'criteria_value', 'prize', 'is_active', 'winners_count', 'winners']
    updates = []
    values = []
    for key, value in kwargs.items():
        if key in allowed_fields:
            updates.append(f"{key} = ?")
            values.append(value)
    if updates:
        values.append(contest_id)
        cursor.execute(f"UPDATE contests SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
    conn.close()

def add_contest_participant(contest_id, user_id):
    """Добавляет участника в конкурс"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO contest_participants (contest_id, user_id, join_date)
        VALUES (?, ?, ?)
    ''', (contest_id, user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def get_contest_participants(contest_id):
    """Получает участников конкурса"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT cp.*, u.full_name, u.username, u.total_spent
        FROM contest_participants cp
        JOIN users u ON cp.user_id = u.user_id
        WHERE cp.contest_id = ?
        ORDER BY cp.join_date
    ''', (contest_id,))
    participants = cursor.fetchall()
    conn.close()
    return participants

def is_user_participating(contest_id, user_id):
    """Проверяет, участвует ли пользователь в конкурсе"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM contest_participants WHERE contest_id = ? AND user_id = ?', (contest_id, user_id))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def get_user_orders_count(user_id):
    """Получает количество заказов пользователя"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM orders WHERE user_id = ?', (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_user_orders_sum(user_id):
    """Получает сумму заказов пользователя"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT SUM(total_amount) FROM orders WHERE user_id = ?', (user_id,))
    total = cursor.fetchone()[0] or 0
    conn.close()
    return total

def check_contest_criteria(contest, user_id):
    """Проверяет, соответствует ли пользователь критериям конкурса"""
    criteria_type = contest['criteria_type']
    criteria_value = contest['criteria_value']
    
    if criteria_type == 'auto_participate':
        # Автоматическое участие всех
        return True
    elif criteria_type == 'min_orders':
        # Минимальное количество заказов
        orders_count = get_user_orders_count(user_id)
        return orders_count >= int(criteria_value)
    elif criteria_type == 'min_spent':
        # Минимальная сумма покупок
        total_spent = get_user_orders_sum(user_id)
        return total_spent >= float(criteria_value)
    elif criteria_type == 'manual':
        # Ручное добавление (кнопка участия)
        return True
    return False

def select_winners(contest_id):
    """Выбирает победителей конкурса"""
    contest = get_contest(contest_id)
    if not contest:
        return []
    
    participants = get_contest_participants(contest_id)
    if not participants:
        return []
    
    import random
    winners_count = min(contest['winners_count'], len(participants))
    
    # Сортируем участников по критериям
    if contest['criteria_type'] == 'min_orders':
        # Получаем количество заказов для каждого участника
        for p in participants:
            p['orders_count'] = get_user_orders_count(p['user_id'])
        participants.sort(key=lambda x: x['orders_count'], reverse=True)
        winners = participants[:winners_count]
    elif contest['criteria_type'] == 'min_spent':
        # Сортируем по сумме покупок
        participants.sort(key=lambda x: x['total_spent'], reverse=True)
        winners = participants[:winners_count]
    else:
        # Рандомный выбор
        winners = random.sample(participants, min(winners_count, len(participants)))
    
    # Обновляем победителей в БД
    winners_data = []
    for winner in winners:
        winners_data.append({
            'user_id': winner['user_id'],
            'full_name': winner['full_name'],
            'username': winner['username']
        })
    
    update_contest(contest_id, winners=json.dumps(winners_data, ensure_ascii=False))
    
    # Отмечаем победителей в таблице участников
    conn = get_db_connection()
    cursor = conn.cursor()
    for winner in winners:
        cursor.execute('UPDATE contest_participants SET is_winner = 1 WHERE contest_id = ? AND user_id = ?', 
                      (contest_id, winner['user_id']))
    conn.commit()
    conn.close()
    
    return winners

import pandas as pd
import io

def parse_products_from_excel(file_content, category_id):
    """Парсит товары из Excel файла"""
    try:
        import pandas as pd
        import io
        
        # Читаем Excel файл
        df = pd.read_excel(io.BytesIO(file_content))
        
        # Ожидаемые колонки
        required_columns = ['name', 'description', 'price', 'cost_price', 'stock']
        
        # Проверяем наличие необходимых колонок
        for col in required_columns:
            if col not in df.columns:
                return None, [f"❌ Отсутствует колонка: {col}"]
        
        products = []
        errors = []
        
        for idx, row in df.iterrows():
            try:
                product = {
                    'name': str(row['name']).strip(),
                    'description': str(row['description']).strip() if pd.notna(row['description']) else '',
                    'price': float(row['price']),
                    'cost_price': float(row['cost_price']) if pd.notna(row['cost_price']) else 0,
                    'stock': int(row['stock']) if pd.notna(row['stock']) else 0,
                    'category_id': category_id,
                    'is_preorder': 0
                }
                
                if not product['name']:
                    errors.append(f"Строка {idx + 2}: отсутствует название")
                    continue
                if product['price'] <= 0:
                    errors.append(f"Строка {idx + 2}: цена должна быть больше 0")
                    continue
                    
                products.append(product)
                
            except Exception as e:
                errors.append(f"Строка {idx + 2}: ошибка - {str(e)}")
        
        return products, errors
        
    except Exception as e:
        return None, [f"Ошибка чтения файла: {str(e)}"]
    
def check_existing_products(products):
    """Проверяет, какие товары уже существуют"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    existing = []
    new = []
    
    for product in products:
        cursor.execute('SELECT id, stock, price, cost_price FROM products WHERE name = ?', (product['name'],))
        existing_product = cursor.fetchone()
        
        if existing_product:
            product['existing_id'] = existing_product['id']
            product['existing_stock'] = existing_product['stock']
            product['existing_price'] = existing_product['price']
            product['existing_cost'] = existing_product['cost_price']
            existing.append(product)
        else:
            new.append(product)
    
    conn.close()
    return existing, new

def update_existing_products(products):
    """Обновляет существующие товары (добавляет количество)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    updated = 0
    for product in products:
        new_stock = product['existing_stock'] + product['stock']
        cursor.execute('''
            UPDATE products 
            SET stock = ?, 
                price = ?,
                cost_price = ?,
                description = ?,
                category_id = ?
            WHERE id = ?
        ''', (new_stock, product['price'], product['cost_price'], 
              product['description'], product['category_id'], product['existing_id']))
        updated += 1
    
    conn.commit()
    conn.close()
    return updated

def add_products_batch(products):
    """Массовое добавление товаров"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    added_count = 0
    for product in products:
        try:
            cursor.execute('''
                INSERT INTO products (name, description, price, cost_price, stock, category_id, image_id, is_preorder)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (product['name'], product['description'], product['price'], 
                  product['cost_price'], product['stock'], product['category_id'],
                  product['image_id'], product['is_preorder']))
            added_count += 1
        except Exception as e:
            print(f"Ошибка добавления {product['name']}: {e}")
    
    conn.commit()
    conn.close()
    return added_count

def update_product_quantity(product_id, new_quantity):
    """Обновляет количество товара"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE products SET stock = ? WHERE id = ?', (new_quantity, product_id))
    
    # Если количество стало 0, деактивируем товар
    if new_quantity <= 0:
        cursor.execute('UPDATE products SET is_active = 0 WHERE id = ?', (product_id,))
    
    conn.commit()
    conn.close()

    # В database.py добавьте:
def get_low_stock_products(threshold=5):
    """Получает товары с низким остатком"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM products 
        WHERE stock <= ? AND stock > 0 AND is_preorder = 0 AND is_active = 1
        ORDER BY stock ASC
    ''', (threshold,))
    products = cursor.fetchall()
    conn.close()
    return products
def init_notification_settings():
    """Инициализирует настройки уведомлений"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Создаем таблицу настроек уведомлений, если её нет
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notification_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            setting_key TEXT UNIQUE,
            setting_value TEXT,
            description TEXT
        )
    ''')
    
    # Добавляем настройки по умолчанию, если их нет
    default_settings = [
        ('low_stock_threshold', '5', 'Порог низкого остатка (шт.)'),
        ('critical_stock_threshold', '2', 'Порог критического остатка (шт.)'),
        ('enable_low_stock_notify', '1', 'Включить уведомления о низком остатке'),
        ('enable_out_of_stock_notify', '1', 'Включить уведомления о закончившихся товарах'),
        ('notify_frequency_hours', '1', 'Частота проверки (часы)'),
        ('notify_admins', '1', 'Уведомлять админов'),
        ('notify_admins_about_each', '1', 'Уведомлять о каждом товаре отдельно')
    ]
    
    for key, value, desc in default_settings:
        cursor.execute('''
            INSERT OR IGNORE INTO notification_settings (setting_key, setting_value, description)
            VALUES (?, ?, ?)
        ''', (key, value, desc))
    
    conn.commit()
    conn.close()

def get_notification_setting(key):
    """Получает настройку уведомлений"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT setting_value FROM notification_settings WHERE setting_key = ?', (key,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def update_notification_setting(key, value):
    """Обновляет настройку уведомлений"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE notification_settings 
        SET setting_value = ? 
        WHERE setting_key = ?
    ''', (value, key))
    conn.commit()
    conn.close()

def get_all_notification_settings():
    """Получает все настройки уведомлений"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT setting_key, setting_value, description FROM notification_settings')
        settings = cursor.fetchall()
        conn.close()
        return {row[0]: {'value': row[1], 'description': row[2]} for row in settings}
    except Exception as e:
        print(f"Ошибка получения настроек: {e}")
        return {}
    
def create_temp_dir():
    """Создает временную директорию"""
    temp_dir = os.path.join(BASE_DIR, 'temp_uploads')
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    return temp_dir

def process_zip_with_photos(zip_content, category_id):
    """Обрабатывает ZIP архив с фото и Excel файлом"""
    temp_dir = create_temp_dir()
    zip_path = os.path.join(temp_dir, f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip")
    
    # Сохраняем ZIP файл
    with open(zip_path, 'wb') as f:
        f.write(zip_content)
    
    # Распаковываем
    extract_dir = os.path.join(temp_dir, 'extracted')
    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir)
    
    with zipfile.ZipFile(zip_path, 'rb') as zip_ref:
        zip_ref.extractall(extract_dir)
    
    # Ищем Excel файл
    excel_file = None
    for file in os.listdir(extract_dir):
        if file.endswith(('.xlsx', '.xls')):
            excel_file = os.path.join(extract_dir, file)
            break
    
    if not excel_file:
        return None, "Excel файл не найден в архиве"
    
    # Читаем Excel
    try:
        df = pd.read_excel(excel_file)
        
        # Ожидаемые колонки
        required_columns = ['name', 'description', 'price', 'cost_price', 'stock', 'photo_filename']
        
        for col in required_columns:
            if col not in df.columns:
                return None, f"Отсутствует колонка: {col}"
        
        products = []
        errors = []
        photos = {}
        
        # Собираем все фото из папки
        for file in os.listdir(extract_dir):
            if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                photos[file] = os.path.join(extract_dir, file)
        
        for idx, row in df.iterrows():
            try:
                photo_filename = str(row['photo_filename']).strip()
                
                if photo_filename not in photos:
                    errors.append(f"Строка {idx + 2}: фото {photo_filename} не найдено")
                    continue
                
                product = {
                    'name': str(row['name']).strip(),
                    'description': str(row['description']).strip() if pd.notna(row['description']) else '',
                    'price': float(row['price']),
                    'cost_price': float(row['cost_price']) if pd.notna(row['cost_price']) else 0,
                    'stock': int(row['stock']) if pd.notna(row['stock']) else 0,
                    'category_id': category_id,
                    'photo_path': photos[photo_filename],
                    'is_preorder': 0
                }
                
                if not product['name']:
                    errors.append(f"Строка {idx + 2}: отсутствует название")
                    continue
                if product['price'] <= 0:
                    errors.append(f"Строка {idx + 2}: цена должна быть больше 0")
                    continue
                    
                products.append(product)
                
            except Exception as e:
                errors.append(f"Строка {idx + 2}: ошибка - {str(e)}")
        
        return products, errors
        
    except Exception as e:
        return None, [f"Ошибка чтения файла: {str(e)}"]
    finally:
        # Очищаем временные файлы
        shutil.rmtree(extract_dir, ignore_errors=True)
        os.remove(zip_path)

def add_products_batch_with_photos(products, bot):
    """Массовое добавление товаров с фото"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    added_count = 0
    for product in products:
        try:
            # Загружаем фото в Telegram
            with open(product['photo_path'], 'rb') as photo_file:
                # Здесь нужно отправить фото через бота
                # Это будет сделано в обработчике
                pass
            
            cursor.execute('''
                INSERT INTO products (name, description, price, cost_price, stock, category_id, image_id, is_preorder)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (product['name'], product['description'], product['price'], 
                  product['cost_price'], product['stock'], product['category_id'],
                  None, product['is_preorder']))
            added_count += 1
        except Exception as e:
            print(f"Ошибка добавления {product['name']}: {e}")
    
    conn.commit()
    conn.close()
    return added_count
def update_product(product_id, **kwargs):
    """Обновляет данные товара"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    allowed_fields = ['name', 'description', 'price', 'cost_price', 'stock', 
                      'category_id', 'image_id', 'is_active']
    
    updates = []
    values = []
    
    for key, value in kwargs.items():
        if key in allowed_fields:
            updates.append(f"{key} = ?")
            values.append(value)
    
    if updates:
        values.append(product_id)
        cursor.execute(f"UPDATE products SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
    
    conn.close()

def auto_delete_completed_orders(days=30):
    """Автоматически удаляет завершенные заказы старше N дней"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Получаем дату, старше которой нужно удалить
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    
    # Удаляем завершенные заказы старше cutoff_date
    cursor.execute('''
        DELETE FROM orders 
        WHERE status = 'completed' 
        AND created_at <= ?
    ''', (cutoff_date,))
    
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted

def init_design_settings():
    """Инициализация настроек дизайна"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS design_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            description TEXT
        )
    ''')
    
    default_settings = [
        ('primary_color', '#2ecc71', 'Основной цвет'),
        ('secondary_color', '#3498db', 'Вторичный цвет'),
        ('accent_color', '#f39c12', 'Акцентный цвет'),
        ('text_color', '#ffffff', 'Цвет текста'),
        ('welcome_text', '👋 Добро пожаловать в наш магазин!', 'Текст приветствия'),
        ('shop_name', '💨 VAPE SHOP', 'Название магазина'),
        ('shop_description', 'Лучшие вейпы и жидкости', 'Описание магазина')
    ]
    
    for key, value, desc in default_settings:
        cursor.execute('''
            INSERT OR IGNORE INTO design_settings (key, value, description)
            VALUES (?, ?, ?)
        ''', (key, value, desc))
    
    conn.commit()
    conn.close()
    
    # Таблица настроек дизайна
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS design_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            description TEXT
        )
    ''')
    
    # Настройки по умолчанию
    default_settings = [
        ('primary_color', '#2ecc71', 'Основной цвет кнопок'),
        ('secondary_color', '#3498db', 'Вторичный цвет'),
        ('accent_color', '#f39c12', 'Акцентный цвет'),
        ('text_color', '#ffffff', 'Цвет текста'),
        ('button_style', 'rounded', 'Стиль кнопок (rounded/square)'),
        ('show_banner_global', '1', 'Показывать баннеры глобально'),
        ('welcome_text', '👋 Добро пожаловать в наш магазин!', 'Текст приветствия'),
        ('footer_text', '✨ Спасибо, что выбираете нас!', 'Текст в подвале'),
        ('shop_name', '💨 VAPE SHOP', 'Название магазина'),
        ('shop_description', 'Лучшие вейпы и жидкости', 'Описание магазина')
    ]
    
    for key, value, desc in default_settings:
        cursor.execute('''
            INSERT OR IGNORE INTO design_settings (key, value, description)
            VALUES (?, ?, ?)
        ''', (key, value, desc))
    
    conn.commit()
    conn.close()

def get_design_setting(key):
    """Получить настройку дизайна"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM design_settings WHERE key = ?', (key,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def update_design_setting(key, value):
    """Обновить настройку дизайна"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE design_settings SET value = ? WHERE key = ?', (value, key))
    conn.commit()
    conn.close()

def add_banner(name, image_id):
    """Добавить баннер"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO banners (name, image_id, is_active, created_at)
        VALUES (?, ?, 1, ?)
    ''', (name, image_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    banner_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return banner_id

def get_active_banner():
    """Получить активный баннер"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM banners WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1')
    banner = cursor.fetchone()
    conn.close()
    return dict(banner) if banner else None

def get_all_banners():
    """Получить все баннеры"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM banners ORDER BY created_at DESC')
    banners = cursor.fetchall()
    conn.close()
    # Преобразуем в список словарей
    return [dict(b) for b in banners] if banners else []

def delete_banner(banner_id):
    """Удалить баннер"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM banners WHERE id = ?', (banner_id,))
    conn.commit()
    conn.close()

def get_banner_for_section(section):
    """Получить баннер для определенного раздела"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    section_map = {
        'welcome': 'show_on_welcome',
        'catalog': 'show_on_catalog',
        'cart': 'show_on_cart',
        'orders': 'show_on_orders',
        'profile': 'show_on_profile',
        'contest': 'show_on_contest',
        'support': 'show_on_support'
    }
    
    column = section_map.get(section, 'show_on_welcome')
    
    cursor.execute(f'''
        SELECT * FROM banners 
        WHERE {column} = 1 AND is_active = 1
        ORDER BY created_at DESC LIMIT 1
    ''')
    banner = cursor.fetchone()
    conn.close()
    return banner

def update_banner_settings(banner_id, settings):
    """Обновить настройки баннера"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE banners SET
            show_on_welcome = ?,
            show_on_catalog = ?,
            show_on_cart = ?,
            show_on_orders = ?,
            show_on_profile = ?,
            show_on_contest = ?,
            show_on_support = ?
        WHERE id = ?
    ''', (
        settings.get('show_on_welcome', 0),
        settings.get('show_on_catalog', 0),
        settings.get('show_on_cart', 0),
        settings.get('show_on_orders', 0),
        settings.get('show_on_profile', 0),
        settings.get('show_on_contest', 0),
        settings.get('show_on_support', 0),
        banner_id
    ))
    conn.commit()
    conn.close()

def update_banners_table():
    """Обновляет таблицу banners, добавляя недостающие колонки"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Проверяем существующие колонки
    cursor.execute("PRAGMA table_info(banners)")
    existing_columns = [col[1] for col in cursor.fetchall()]
    
    # Колонки, которые нужно добавить
    new_columns = [
        ('show_on_welcome', 'INTEGER DEFAULT 1'),
        ('show_on_catalog', 'INTEGER DEFAULT 0'),
        ('show_on_cart', 'INTEGER DEFAULT 0'),
        ('show_on_orders', 'INTEGER DEFAULT 0'),
        ('show_on_profile', 'INTEGER DEFAULT 0'),
        ('show_on_contest', 'INTEGER DEFAULT 0'),
        ('show_on_support', 'INTEGER DEFAULT 0')
    ]
    
    # Добавляем недостающие колонки
    for col_name, col_type in new_columns:
        if col_name not in existing_columns:
            try:
                cursor.execute(f'ALTER TABLE banners ADD COLUMN {col_name} {col_type}')
                print(f"✅ Добавлена колонка: {col_name}")
            except Exception as e:
                print(f"Ошибка добавления {col_name}: {e}")
    
    conn.commit()
    conn.close()

def add_missing_columns():
    """Добавляет недостающие колонки в таблицу banners"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Проверяем существование таблицы banners
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='banners'")
    table_exists = cursor.fetchone()
    
    if table_exists:
        # Получаем список существующих колонок
        cursor.execute("PRAGMA table_info(banners)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Добавляем колонки, если их нет
        if 'show_on_welcome' not in columns:
            try:
                cursor.execute('ALTER TABLE banners ADD COLUMN show_on_welcome INTEGER DEFAULT 1')
                print("✅ Добавлена колонка show_on_welcome")
            except Exception as e:
                print(f"Ошибка добавления show_on_welcome: {e}")
        
        if 'show_on_catalog' not in columns:
            try:
                cursor.execute('ALTER TABLE banners ADD COLUMN show_on_catalog INTEGER DEFAULT 0')
                print("✅ Добавлена колонка show_on_catalog")
            except Exception as e:
                print(f"Ошибка добавления show_on_catalog: {e}")
        
        if 'show_on_cart' not in columns:
            try:
                cursor.execute('ALTER TABLE banners ADD COLUMN show_on_cart INTEGER DEFAULT 0')
                print("✅ Добавлена колонка show_on_cart")
            except Exception as e:
                print(f"Ошибка добавления show_on_cart: {e}")
        
        if 'show_on_orders' not in columns:
            try:
                cursor.execute('ALTER TABLE banners ADD COLUMN show_on_orders INTEGER DEFAULT 0')
                print("✅ Добавлена колонка show_on_orders")
            except Exception as e:
                print(f"Ошибка добавления show_on_orders: {e}")
        
        if 'show_on_profile' not in columns:
            try:
                cursor.execute('ALTER TABLE banners ADD COLUMN show_on_profile INTEGER DEFAULT 0')
                print("✅ Добавлена колонка show_on_profile")
            except Exception as e:
                print(f"Ошибка добавления show_on_profile: {e}")
        
        if 'show_on_contest' not in columns:
            try:
                cursor.execute('ALTER TABLE banners ADD COLUMN show_on_contest INTEGER DEFAULT 0')
                print("✅ Добавлена колонка show_on_contest")
            except Exception as e:
                print(f"Ошибка добавления show_on_contest: {e}")
        
        if 'show_on_support' not in columns:
            try:
                cursor.execute('ALTER TABLE banners ADD COLUMN show_on_support INTEGER DEFAULT 0')
                print("✅ Добавлена колонка show_on_support")
            except Exception as e:
                print(f"Ошибка добавления show_on_support: {e}")
    
    conn.commit()
    conn.close()

def set_active_banner(banner_id):
    """Установить активный баннер"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE banners SET is_active = 0')
    cursor.execute('UPDATE banners SET is_active = 1 WHERE id = ?', (banner_id,))
    conn.commit()
    conn.close()

def create_banners_table():
    """Создание таблицы баннеров"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS banners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            image_id TEXT,
            is_active INTEGER DEFAULT 0,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()
