import pandas as pd
import io
from datetime import datetime, timedelta
import json
import database as db
import config
from aiogram.types import BufferedInputFile

async def export_orders_to_excel(period='all', start_date=None, end_date=None):
    """
    Экспорт заказов в Excel
    period: 'today', 'week', 'month', 'all', 'custom'
    """
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    # Формируем запрос в зависимости от периода
    if period == 'today':
        today = datetime.now().strftime("%Y-%m-%d")
        cursor.execute('''
            SELECT * FROM orders 
            WHERE DATE(created_at) = ?
            ORDER BY created_at DESC
        ''', (today,))
    elif period == 'week':
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        cursor.execute('''
            SELECT * FROM orders 
            WHERE DATE(created_at) >= ?
            ORDER BY created_at DESC
        ''', (week_ago,))
    elif period == 'month':
        month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        cursor.execute('''
            SELECT * FROM orders 
            WHERE DATE(created_at) >= ?
            ORDER BY created_at DESC
        ''', (month_ago,))
    elif period == 'custom' and start_date and end_date:
        cursor.execute('''
            SELECT * FROM orders 
            WHERE DATE(created_at) BETWEEN ? AND ?
            ORDER BY created_at DESC
        ''', (start_date, end_date))
    else:  # all
        cursor.execute('SELECT * FROM orders ORDER BY created_at DESC')
    
    orders = cursor.fetchall()
    conn.close()
    
    if not orders:
        return None, "Нет заказов за выбранный период"
    
    # Подготовка данных для Excel
    data = []
    total_revenue = 0
    total_profit = 0
    
    for order in orders:
        # Парсим товары из JSON
        try:
            items = json.loads(order['items'])
            items_text = "\n".join([f"{item['name']} x{item['quantity']} = {item['price'] * item['quantity']}₽" 
                                    for item in items])
        except:
            items_text = "Ошибка загрузки"
        
        profit = order['total_amount'] - order['total_cost']
        total_revenue += order['total_amount']
        total_profit += profit
        
        data.append({
            '№ Заказа': order['id'],
            'Дата': order['created_at'],
            'Покупатель': f"@{order['username']}" if order['username'] else "Без юзернейма",
            'ID пользователя': order['user_id'],
            'Товары': items_text,
            'Сумма (руб)': order['total_amount'],
            'Себестоимость (руб)': order['total_cost'],
            'Прибыль (руб)': profit,
            'Способ оплаты': 'Карта' if order['payment_method'] == 'card' else 'Наличные',
            'Статус': get_status_text(order['status'])
        })
    
    # Создаем DataFrame
    df = pd.DataFrame(data)
    
    # Создаем Excel файл в памяти
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Основной лист с заказами
        df.to_excel(writer, sheet_name='Заказы', index=False)
        
        # Лист с итогами
        summary_data = {
            'Показатель': ['Всего заказов', 'Общая выручка', 'Общая прибыль', 
                          'Средний чек', 'Период'],
            'Значение': [len(orders), total_revenue, total_profit, 
                        total_revenue / len(orders) if orders else 0,
                        get_period_text(period, start_date, end_date)]
        }
        summary_df = pd.DataFrame(summary_data)
        summary_df.to_excel(writer, sheet_name='Итоги', index=False)
        
        # Настраиваем форматирование
        workbook = writer.book
        worksheet = writer.sheets['Заказы']
        
        # Формат для денег
        money_format = workbook.add_format({'num_format': '#,##0.00', 'bold': False})
        worksheet.set_column('F:H', 12, money_format)
        worksheet.set_column('A:A', 10)
        worksheet.set_column('B:B', 20)
        worksheet.set_column('C:C', 20)
        worksheet.set_column('D:D', 15)
        worksheet.set_column('E:E', 40)
        worksheet.set_column('I:I', 15)
        worksheet.set_column('J:J', 15)
    
    output.seek(0)
    return output, f"Экспортировано {len(orders)} заказов. Выручка: {total_revenue}₽, Прибыль: {total_profit}₽"

def get_status_text(status):
    """Переводит статус в читаемый текст"""
    status_map = {
        'pending': '⏳ В ожидании',
        'in_progress': '🛠 В работе',
        'ready': '✅ Готов',
        'completed': '📦 Завершен'
    }
    return status_map.get(status, status)

def get_period_text(period, start_date=None, end_date=None):
    """Текст периода для отчета"""
    if period == 'today':
        return 'Сегодня'
    elif period == 'week':
        return 'Последние 7 дней'
    elif period == 'month':
        return 'Последние 30 дней'
    elif period == 'custom':
        return f'{start_date} - {end_date}'
    else:
        return 'За все время'