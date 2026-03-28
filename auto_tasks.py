import asyncio
import logging
import io
import os
import shutil
from aiogram import Bot
import pandas as pd
from datetime import datetime, timedelta
import config
import database as db
from aiogram.types import BufferedInputFile

async def auto_backup_task(bot):
    """Автоматическое резервное копирование базы данных"""
    backup_dir = "backups"
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    
    while True:
        try:
            # Создаем бэкап каждые 24 часа
            await asyncio.sleep(86400)  # 24 часа
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = f"{backup_dir}/vape_shop_backup_{timestamp}.db"
            shutil.copy2(config.DB_NAME, backup_file)
            
            # Удаляем старые бэкапы (оставляем только последние 7)
            backups = sorted([f for f in os.listdir(backup_dir) if f.endswith('.db')])
            for backup in backups[:-7]:
                os.remove(os.path.join(backup_dir, backup))
            
            # Уведомляем админов
            for admin_id in config.ADMIN_IDS:
                await bot.send_message(admin_id, f"✅ Создана резервная копия: {backup_file}")
                
        except Exception as e:
            logging.error(f"Ошибка в auto_backup_task: {e}")

async def auto_report_task(bot):
    """Автоматическое создание и отправка отчетов"""
    while True:
        now = datetime.now()
        # Ждем до 23:55
        target_time = now.replace(hour=23, minute=55, second=0)
        if now > target_time:
            target_time += timedelta(days=1)
        
        wait_seconds = (target_time - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        
        try:
            # Получаем отчет за день
            report = get_daily_report()
            
            if report['orders'] > 0:
                # Создаем текстовый отчет
                text = (
                    f"📊 <b>ЕЖЕДНЕВНЫЙ ОТЧЕТ</b>\n"
                    f"Дата: {report['date']}\n\n"
                    f"📦 Заказов: {report['orders']}\n"
                    f"💰 Выручка: {report['revenue']} руб.\n"
                    f"📉 Себестоимость: {report['cost']} руб.\n"
                    f"📈 Прибыль: {report['profit']} руб."
                )
                
                for admin_id in config.ADMIN_IDS:
                    await bot.send_message(admin_id, text, parse_mode="HTML")
                    
        except Exception as e:
            logging.error(f"Ошибка в auto_report_task: {e}")

async def auto_finish_contests_task(bot):
    """Автоматическое завершение конкурсов"""
    while True:
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn = db.get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM contests 
                WHERE is_active = 1 AND end_date < ?
            ''', (now,))
            expired_contests = cursor.fetchall()
            conn.close()
            
            for contest in expired_contests:
                # Завершаем конкурс
                db.update_contest(contest['id'], is_active=0)
                
                # Выбираем победителей
                winners = db.select_winners(contest['id'])
                
                # Уведомляем админов
                for admin_id in config.ADMIN_IDS:
                    text = f"🏆 <b>КОНКУРС ЗАВЕРШЕН АВТОМАТИЧЕСКИ</b>\n\n"
                    text += f"Название: {contest['name']}\n"
                    text += f"Победителей: {len(winners)}"
                    await bot.send_message(admin_id, text, parse_mode="HTML")
            
            await asyncio.sleep(3600)  # Проверяем каждый час
        except Exception as e:
            logging.error(f"Ошибка в auto_finish_contests_task: {e}")
            await asyncio.sleep(3600)

async def auto_check_stock_task(bot):
    """Автоматическая проверка остатков товаров"""
    while True:
        try:
            # Получаем товары с низким остатком
            low_stock = db.get_low_stock_products(5)
            if low_stock:
                for admin_id in config.ADMIN_IDS:
                    text = "⚠️ <b>ВНИМАНИЕ! НИЗКИЙ ОСТАТОК ТОВАРОВ:</b>\n\n"
                    for product in low_stock:
                        text += f"📦 {product['name']} - {product['stock']} шт.\n"
                    await bot.send_message(admin_id, text, parse_mode="HTML")
            
            # Проверяем товары, которые закончились
            out_of_stock = db.get_out_of_stock_products()
            if out_of_stock:
                for admin_id in config.ADMIN_IDS:
                    text = "❌ <b>ТОВАРЫ ЗАКОНЧИЛИСЬ:</b>\n\n"
                    for product in out_of_stock:
                        text += f"📦 {product['name']}\n"
                    await bot.send_message(admin_id, text, parse_mode="HTML")
            
            await asyncio.sleep(3600)  # Проверяем каждый час
        except Exception as e:
            logging.error(f"Ошибка в auto_check_stock_task: {e}")
            await asyncio.sleep(3600)

def get_daily_report():
    """Получает данные для дневного отчета"""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    
    cursor.execute('''
        SELECT COUNT(*), SUM(total_amount), SUM(total_cost)
        FROM orders 
        WHERE DATE(created_at) = ?
    ''', (today,))
    
    result = cursor.fetchone()
    conn.close()
    
    orders_count = result[0] or 0
    revenue = result[1] or 0
    cost = result[2] or 0
    
    return {
        'date': today,
        'orders': orders_count,
        'revenue': revenue,
        'cost': cost,
        'profit': revenue - cost
    }

async def auto_delete_old_orders(bot: Bot):
    """Автоматическое удаление старых завершенных заказов"""
    while True:
        try:
            deleted = db.auto_delete_completed_orders(30)
            if deleted > 0:
                for admin_id in config.ADMIN_IDS:
                    await bot.send_message(
                        admin_id,
                        f"🗑 Автоматически удалено {deleted} старых завершенных заказов"
                    )
            await asyncio.sleep(86400)  # Раз в сутки
        except Exception as e:
            logging.error(f"Ошибка в auto_delete_old_orders: {e}")
            await asyncio.sleep(86400)