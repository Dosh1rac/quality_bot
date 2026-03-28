import asyncio
import logging
from datetime import datetime
from aiogram import Bot
import config
import database as db

async def check_stock_task(bot: Bot):
    """Улучшенная фоновая задача проверки остатков с настройками"""
    # Получаем настройки
    last_notified = {}  # Словарь для отслеживания последних уведомлений о товарах
    
    while True:
        try:
            # Получаем настройки из базы данных
            low_threshold = int(db.get_notification_setting('low_stock_threshold') or '5')
            critical_threshold = int(db.get_notification_setting('critical_stock_threshold') or '2')
            enable_low = int(db.get_notification_setting('enable_low_stock_notify') or '1')
            enable_out = int(db.get_notification_setting('enable_out_of_stock_notify') or '1')
            notify_admins = int(db.get_notification_setting('notify_admins') or '1')
            notify_each = int(db.get_notification_setting('notify_admins_about_each') or '1')
            
            # Получаем все активные товары
            conn = db.get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, name, stock, is_preorder 
                FROM products 
                WHERE is_active = 1 AND is_preorder = 0
                ORDER BY stock ASC
            ''')
            all_products = cursor.fetchall()
            conn.close()
            
            # Разделяем товары по категориям
            low_stock_products = []  # Низкий остаток
            critical_stock_products = []  # Критический остаток
            out_of_stock_products = []  # Закончились
            
            for product in all_products:
                stock = product['stock']
                
                if stock <= 0:
                    out_of_stock_products.append(product)
                elif stock <= critical_threshold:
                    critical_stock_products.append(product)
                elif stock <= low_threshold:
                    low_stock_products.append(product)
            
            # Отправляем уведомления, если они включены
            current_time = datetime.now()
            
            # 1. Уведомления о критическом остатке (самые важные)
            if critical_stock_products and enable_low:
                if notify_each:
                    # Отправляем отдельное сообщение для каждого товара
                    for product in critical_stock_products:
                        # Проверяем, не отправляли ли уведомление недавно
                        product_key = f"critical_{product['id']}"
                        last_time = last_notified.get(product_key)
                        
                        if not last_time or (current_time - last_time).seconds > 3600:  # Не чаще раза в час
                            text = (
                                f"🔴 <b>КРИТИЧЕСКИЙ ОСТАТОК!</b>\n\n"
                                f"📦 <b>{product['name']}</b>\n"
                                f"⚠️ Осталось: <b>{product['stock']} шт.</b>\n"
                                f"🚨 Срочно пополните склад!\n\n"
                                f"<i>Порог критического остатка: {critical_threshold} шт.</i>"
                            )
                            
                            if notify_admins:
                                for admin_id in config.ADMIN_IDS:
                                    await bot.send_message(admin_id, text, parse_mode="HTML")
                            
                            last_notified[product_key] = current_time
                else:
                    # Отправляем одно сообщение со всеми товарами
                    text = "🔴 <b>КРИТИЧЕСКИЙ ОСТАТОК ТОВАРОВ!</b>\n\n"
                    for product in critical_stock_products:
                        text += f"📦 <b>{product['name']}</b> - {product['stock']} шт.\n"
                    text += f"\n<i>Порог критического остатка: {critical_threshold} шт.</i>"
                    
                    if notify_admins:
                        for admin_id in config.ADMIN_IDS:
                            await bot.send_message(admin_id, text, parse_mode="HTML")
            
            # 2. Уведомления о низком остатке
            if low_stock_products and enable_low:
                if notify_each:
                    for product in low_stock_products:
                        product_key = f"low_{product['id']}"
                        last_time = last_notified.get(product_key)
                        
                        if not last_time or (current_time - last_time).seconds > 3600:
                            text = (
                                f"⚠️ <b>НИЗКИЙ ОСТАТОК</b>\n\n"
                                f"📦 <b>{product['name']}</b>\n"
                                f"Осталось: <b>{product['stock']} шт.</b>\n\n"
                                f"<i>Порог низкого остатка: {low_threshold} шт.</i>"
                            )
                            
                            if notify_admins:
                                for admin_id in config.ADMIN_IDS:
                                    await bot.send_message(admin_id, text, parse_mode="HTML")
                            
                            last_notified[product_key] = current_time
                else:
                    text = "⚠️ <b>НИЗКИЙ ОСТАТОК ТОВАРОВ</b>\n\n"
                    for product in low_stock_products:
                        text += f"📦 {product['name']} - {product['stock']} шт.\n"
                    text += f"\n<i>Порог низкого остатка: {low_threshold} шт.</i>"
                    
                    if notify_admins:
                        for admin_id in config.ADMIN_IDS:
                            await bot.send_message(admin_id, text, parse_mode="HTML")
            
            # 3. Уведомления о закончившихся товарах
            if out_of_stock_products and enable_out:
                text = "❌ <b>ТОВАРЫ ЗАКОНЧИЛИСЬ!</b>\n\n"
                for product in out_of_stock_products:
                    text += f"📦 <b>{product['name']}</b>\n"
                text += f"\n<i>Товары автоматически скрыты из каталога.</i>"
                
                if notify_admins:
                    for admin_id in config.ADMIN_IDS:
                        await bot.send_message(admin_id, text, parse_mode="HTML")
                
                # Автоматически деактивируем товары, которые закончились
                for product in out_of_stock_products:
                    db.update_product_quantity(product['id'], 0)
            
            # Получаем интервал проверки из настроек
            frequency_hours = int(db.get_notification_setting('notify_frequency_hours') or '1')
            await asyncio.sleep(frequency_hours * 3600)
            
        except Exception as e:
            logging.error(f"Ошибка в check_stock_task: {e}")
            await asyncio.sleep(3600)