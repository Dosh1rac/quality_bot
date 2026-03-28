import asyncio
import logging
import json
import pandas as pd
import io
import os
import shutil
import zipfile

from aiogram.types import BufferedInputFile
from datetime import datetime, timedelta
from aiogram import F, types, Bot
from aiogram.filters import Command
from aiogram.types import (
    Message, 
    CallbackQuery, 
    ReplyKeyboardRemove, 
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
import database as db
import keyboards as kb
from states import (
    AddProductStates, 
    BroadcastStates, 
    CheckoutStates, 
    AddPreorderStates, 
    CategoryStates, 
    ContestStates,
    MassUploadStates,
    EditProductStates,
    DesignStates
)

# ==========================================
#                 УТИЛИТЫ
# ==========================================

async def delete_prev(user_id, chat_id, bot: Bot):
    last_id = await db.get_last_message_id(user_id)
    if last_id:
        try:
            await bot.delete_message(chat_id, last_id)
        except:
            pass

# ==========================================
#            БАЗОВЫЕ КОМАНДЫ
# ==========================================

async def start_command(message: Message):
    """/start"""
    user_id = message.from_user.id
    
    user = db.get_user(user_id)
    if user and user.get('is_banned', 0) == 1:
        await message.answer(
            "🚫 <b>Ваш аккаунт заблокирован</b>\n\n"
            f"Обратитесь: {config.SUPPORT_LINK}",
            parse_mode="HTML"
        )
        return
    
    db.add_user(user_id, message.from_user.username, message.from_user.full_name)
    
    shop_name = db.get_design_setting('shop_name')
    welcome_text = db.get_design_setting('welcome_text')
    
    text = f"{shop_name}\n\n{welcome_text}\n\n👋 Привет, {message.from_user.full_name}!"
    
    await send_with_banner(
        message.bot, message.chat.id, text,
        parse_mode="HTML",
        reply_markup=kb.get_main_keyboard(user_id)
    )
# ==========================================
#         МЕНЮ КЛИЕНТА
# ==========================================

async def catalog_text_btn(message: Message):
    """Каталог - здесь баннер НЕ показываем"""
    await send_with_banner(
        message.bot, message.chat.id,
        "📁 Выберите категорию:",
        skip_banner=True,  # Пропускаем баннер
        reply_markup=kb.get_categories_keyboard()
    )

async def profile_text_btn(message: Message):
    """Профиль"""
    user = db.get_user(message.from_user.id)
    
    if not user:
        await send_with_banner(
            message.bot, message.chat.id,
            "❌ Ошибка загрузки профиля",
            parse_mode="HTML"
        )
        return
    
    text = (f"👤 <b>Профиль</b>\n\n"
            f"ID: <code>{user['user_id']}</code>\n"
            f"Имя: {user['full_name']}\n"
            f"💰 Баланс: {user.get('balance', 0)} руб.\n"
            f"💸 Всего потрачено: {user.get('total_spent', 0)} руб.\n"
            f"👥 Рефералов: {user.get('referrals_count', 0)}")
    
    await send_with_banner(
        message.bot, message.chat.id, text,
        parse_mode="HTML"
    )

async def rating_text_btn(message: Message):
    """Рейтинг"""
    top_users = db.get_top_users()
    
    if not top_users:
        await send_with_banner(
            message.bot, message.chat.id,
            "🏆 Рейтинг пока пуст.",
            parse_mode="HTML"
        )
        return
    
    text = "🏆 <b>ТОП ПОКУПАТЕЛЕЙ</b>\n\n"
    for i, user in enumerate(top_users, 1):
        text += f"{i}. {user['full_name']} — {user['total_spent']} руб.\n"
    
    await send_with_banner(
        message.bot, message.chat.id, text,
        parse_mode="HTML"
    )

async def support_text_btn(message: Message):
    """Поддержка"""
    text = (
        "<b>🆘 СЛУЖБА ПОДДЕРЖКИ</b>\n\n"
        "Есть вопросы по заказу или ассортименту?\n"
        f"Наш менеджер: {config.SUPPORT_LINK}\n\n"
        "<i>Время ответа: от 5 до 30 минут.</i>"
    )
    
    await send_with_banner(
        message.bot, message.chat.id, text,
        parse_mode="HTML"
    )
async def my_orders_text_btn(message: Message):
    """Мои заказы"""
    orders = db.get_user_orders(message.from_user.id)
    
    if not orders:
        await send_with_banner(
            message.bot, message.chat.id,
            "📦 У вас пока нет заказов.",
            parse_mode="HTML"
        )
        return
    
    text = "<b>📋 ИСТОРИЯ ВАШИХ ЗАКАЗОВ</b>\n\n"
    status_map = {
        "pending": "⏳ В ожидании",
        "in_progress": "🛠 В работе",
        "ready": "✅ Готов к выдаче",
        "completed": "📦 Завершен"
    }
    
    for o in orders[:10]:
        status = status_map.get(o['status'], o['status'])
        text += f"🔹 <b>Заказ №{o['id']}</b>\n"
        text += f"Сумма: {o['total_amount']} руб.\n"
        text += f"Статус: {status}\n"
        if o['username']:
            text += f"Контакт: @{o['username']}\n"
        text += f"Дата: {o['created_at'][:16]}\n\n"
    
    await send_with_banner(
        message.bot, message.chat.id, text,
        parse_mode="HTML"
    )

async def contest_text_btn(message: Message):
    """Конкурс"""
    contest = db.get_active_contest()
    
    if not contest:
        await send_with_banner(
            message.bot, message.chat.id,
            "🎁 В данный момент нет активных конкурсов.\nСледите за новостями!",
            parse_mode="HTML"
        )
        return
    
    now = datetime.now()
    end_date = datetime.strptime(contest['end_date'], "%Y-%m-%d %H:%M:%S")
    days_left = (end_date - now).days
    
    text = (
        f"<b>🎁 АКТИВНЫЙ КОНКУРС</b>\n\n"
        f"<b>{contest['name']}</b>\n\n"
        f"{contest['description']}\n\n"
        f"🎁 <b>ПРИЗ:</b> {contest['prize']}\n"
        f"📅 <b>ДО ОКОНЧАНИЯ:</b> {days_left} дней\n"
        f"🏆 <b>ПОБЕДИТЕЛЕЙ:</b> {contest['winners_count']}\n\n"
        f"Удачи!"
    )
    
    await send_with_banner(
        message.bot, message.chat.id, text,
        parse_mode="HTML"
    )

async def cancel_action_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.delete()
    except:
        pass
    await callback.message.answer("❌ Действие отменено.", reply_markup=kb.get_main_keyboard(callback.from_user.id))
    await callback.answer()
# ==========================================
#               КАТАЛОГ ТОВАРОВ
# ==========================================

async def show_category_products(callback: CallbackQuery):
    """Показ товаров категории - здесь баннер НЕ показываем"""
    category_id = int(callback.data.split("_")[1])
    products = db.get_products_by_category_id(category_id)
    category = db.get_category(category_id)
    
    if not products:
        await callback.message.answer("В этой категории пока нет товаров.")
        await callback.answer()
        return
    
    builder = InlineKeyboardBuilder()
    for product in products:
        emoji = "⏰" if product['is_preorder'] else "📦"
        builder.add(InlineKeyboardButton(
            text=f"{emoji} {product['name']} - {product['price']}₽",
            callback_data=f"view_product_{product['id']}"
        ))
    
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_categories"))
    
    await send_with_banner(
        callback.message.bot, callback.message.chat.id,
        f"📁 <b>{category['emoji']} {category['name']}</b>\n\nВыберите товар:",
        skip_banner=True,  # Пропускаем баннер
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# ==========================================
#             КОРЗИНА И ЗАКАЗЫ
# ==========================================

async def cart_text_btn(message: Message):
    """Корзина"""
    items = db.get_cart_items(message.from_user.id)
    if not items:
        await send_with_banner(
            message.bot, message.chat.id,
            "🛒 Корзина пуста",
            parse_mode="HTML"
        )
        return
    
    text = "🛒 <b>КОРЗИНА</b>\n\n"
    total = 0
    for item in items:
        sum_price = item['price'] * item['quantity']
        text += f"▪️ {item['name']} x{item['quantity']} = {sum_price} руб.\n"
        total += sum_price
    text += f"\n<b>Итого: {total} руб.</b>"
    
    await send_with_banner(
        message.bot, message.chat.id, text,
        parse_mode="HTML",
        reply_markup=kb.get_cart_keyboard()
    )

async def add_to_cart_callback(callback: CallbackQuery):
    product_id = int(callback.data.replace("buy_", ""))
    product = db.get_product(product_id)
    
    if not product:
        await callback.answer("❌ Товар не найден", show_alert=True)
        return
    
    if product['stock'] <= 0 and not product['is_preorder']:
        await callback.answer("❌ Товар закончился!", show_alert=True)
        return
    
    db.add_to_cart(callback.from_user.id, product_id)
    await callback.answer("✅ Товар добавлен в корзину!")

async def clear_cart_callback(callback: CallbackQuery):
    db.clear_cart(callback.from_user.id)
    await callback.message.delete()
    await callback.message.answer(
        "🛒 Ваша корзина очищена.", 
        reply_markup=kb.get_main_keyboard(callback.from_user.id)
    )
    await callback.answer("Корзина пуста")

async def remove_from_cart_callback(callback: CallbackQuery):
    product_id = int(callback.data.replace("remove_", ""))
    db.remove_from_cart(callback.from_user.id, product_id)
    await callback.answer("🗑 Товар удален из корзины")
    
    items = db.get_cart_items(callback.from_user.id)
    if not items:
        await callback.message.delete()
        await callback.message.answer(
            "🛒 Ваша корзина пуста.", 
            reply_markup=kb.get_main_keyboard(callback.from_user.id)
        )
        return
    
    text = "🛒 <b>ВАША КОРЗИНА:</b>\n\n"
    total = 0
    for item in items:
        sum_price = item['price'] * item['quantity']
        text += f"▪️ {item['name']} x{item['quantity']} = {sum_price} руб.\n"
        total += sum_price
    text += f"\n<b>Итого: {total} руб.</b>"
    
    await callback.message.delete()
    await callback.message.answer(
        text, 
        parse_mode="HTML", 
        reply_markup=kb.get_cart_keyboard()
    )

async def checkout_start(callback: CallbackQuery, state: FSMContext):
    items = db.get_cart_items(callback.from_user.id)
    if not items:
        await callback.answer("🛒 Ваша корзина пуста!", show_alert=True)
        return
    
    for item in items:
        if not db.check_product_availability(item['id'], item['quantity']):
            product = db.get_product(item['id'])
            await callback.answer(f"❌ Товар {product['name']} закончился!", show_alert=True)
            return
    
    total = db.get_cart_total(callback.from_user.id)
    await state.update_data(items=items, total=total)
    
    text = f"<b>💳 ВЫБОР СПОСОБА ОПЛАТЫ</b>\n\n"
    text += f"Сумма заказа: <b>{total} руб.</b>\n\n"
    text += "Выберите способ оплаты:"
    
    # Удаляем старое сообщение и отправляем новое
    await callback.message.delete()
    await callback.message.answer(
        text, 
        parse_mode="HTML", 
        reply_markup=kb.get_payment_keyboard()
    )
    await state.set_state(CheckoutStates.payment)
    await callback.answer()

async def checkout_payment(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Выбор способа оплаты"""
    payment_method = callback.data.replace("payment_", "")
    await state.update_data(payment_method=payment_method)
    
    if payment_method == "card":
        card_text = (
            "<b>💳 ОПЛАТА КАРТОЙ</b>\n\n"
            f"Карта: <code>{config.PAYMENT_REQUISITES['card_number']}</code>\n"
            f"Держатель: {config.PAYMENT_REQUISITES['holder']}\n"
            f"Банк: {config.PAYMENT_REQUISITES['bank']}\n\n"
            "После оплаты нажмите «Я оплатил»"
        )
        await callback.message.edit_text(
            card_text, 
            parse_mode="HTML", 
            reply_markup=kb.get_payment_confirmation_keyboard()
        )
        await state.set_state(CheckoutStates.wait_payment)
        
    elif payment_method == "cash":
        await callback.message.edit_text(
            "💵 Вы выбрали оплату наличными при получении.\n\nПодтвердите заказ:",
            parse_mode="HTML",
            reply_markup=kb.get_confirm_keyboard()
        )
        await state.set_state(CheckoutStates.confirm)
    
    await callback.answer()

    
async def checkout_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if callback.data == "confirm_order":
        data = await state.get_data()
        await create_order_from_data(callback, state, bot, data)
        
        # Удаляем сообщение с клавиатурой
        await callback.message.delete()
        
        # Отправляем новое сообщение с обычной клавиатурой
        await callback.message.answer(
            "✅ Заказ успешно оформлен! Менеджер свяжется с вами.",
            reply_markup=kb.get_main_keyboard(callback.from_user.id)
        )
    elif callback.data == "cancel_order":
        await callback.message.delete()
        await callback.message.answer(
            "❌ Оформление заказа отменено.",
            reply_markup=kb.get_main_keyboard(callback.from_user.id)
        )
    await state.clear()
    await callback.answer()

async def create_order_from_data(callback, state, bot, data):
    """Создает заказ из данных"""
    user_id = callback.from_user.id
    username = callback.from_user.username
    items = data.get('items', [])
    total = data.get('total', 0)
    payment_method = data.get('payment_method', 'cash')
    
    total_cost = 0
    items_list = []
    
    # Обработка товаров
    for item in items:
        product = db.get_product(item['id'])
        if product:
            cost = product['cost_price'] * item['quantity']
            total_cost += cost
            items_list.append({
                'name': item['name'],
                'quantity': item['quantity'],
                'price': item['price'],
                'cost_price': product['cost_price']
            })
            if not product['is_preorder']:
                db.update_product_stock(item['id'], -item['quantity'])
    
    items_json = json.dumps(items_list, ensure_ascii=False)
    order_id = db.create_order(user_id, items_json, total, total_cost, username, payment_method)
    
    # Очистка корзины в БД
    db.clear_cart(user_id)
    db.disable_out_of_stock_products()
    
    # Подготовка текста для админа
    profit = total - total_cost
    admin_text = (
        f"<b>🔔 НОВЫЙ ЗАКАЗ №{order_id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 Покупатель: @{username if username else 'без юзернейма'}\n"
        f"💳 Оплата: {'Карта' if payment_method == 'card' else 'Наличные'}\n"
        f"💰 Выручка: {total} руб.\n"
        f"📦 Себестоимость: {total_cost} руб.\n"
        f"📈 Прибыль: {profit} руб.\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    
    # Рассылка админам (в фоне, чтобы не тормозить юзера)
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, admin_text, parse_mode="HTML")
            # Если есть товары с низким остатком, уведомляем тоже
            low_stock = db.get_low_stock_products()
            if low_stock:
                low_text = "⚠️ <b>Низкий остаток товаров:</b>\n\n"
                for p in low_stock:
                    low_text += f"• {p['name']} - {p['stock']} шт.\n"
                await bot.send_message(admin_id, low_text, parse_mode="HTML")
            await asyncio.sleep(0.05) # Небольшая пауза между админами
        except Exception as e:
            logging.error(f"Ошибка отправки админу {admin_id}: {e}")

# ==========================================
#               АДМИН ПАНЕЛЬ
# ==========================================

async def admin_text_btn(message: Message):
    if message.from_user.id in config.ADMIN_IDS:
        sent = await message.answer("🔧 Панель управления:", reply_markup=kb.get_admin_keyboard())
        await db.save_message(message.from_user.id, sent.message_id)

async def admin_stats_callback(callback: CallbackQuery):
    users, orders, revenue = db.get_stats()
    text = (f"<b>📊 СТАТИСТИКА МАГАЗИНА</b>\n\n"
            f"👥 Всего пользователей: <code>{users}</code>\n"
            f"📦 Всего заказов: <code>{orders}</code>\n"
            f"💰 Общая выручка: <code>{revenue} руб.</code>")
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

async def admin_profit_stats(callback: CallbackQuery):
    if callback.from_user.id not in config.ADMIN_IDS: return
    rev, cost, prof, orders = db.get_profit_stats()
    text = (f"<b>💰 Текущая прибыль</b>\n<i>(после сброса)</i>\n\n"
            f"🛍 Заказов: {orders}\n💰 Выручка: {rev}\n📉 Себестоимость: {cost}\n📈 Прибыль: <b>{prof}</b>")
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_admin_keyboard())
    await callback.answer()

async def admin_confirm_reset(callback: CallbackQuery):
    await callback.message.edit_text("<b>⚠️ СБРОСИТЬ ПРИБЫЛЬ?</b>\nБудет создан .txt отчет.",
                                     parse_mode="HTML", reply_markup=kb.get_confirm_reset_kb())
    await callback.answer()


async def admin_do_reset(callback: CallbackQuery, bot: Bot):
    report = db.get_report_text()
    file = BufferedInputFile(report.encode('utf-8'), filename="report.txt")
    await callback.message.answer_document(file, caption="✅ Статистика сброшена.")
    db.reset_profit_stats()
    await callback.message.answer("🔧 Админ панель:", reply_markup=kb.get_admin_keyboard())
    await callback.message.delete()
    await callback.answer()

async def admin_orders_manage_callback(callback: CallbackQuery):
    """Управление заказами (админ)"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    # Получаем все заказы, не показываем завершенные
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM orders 
        WHERE status != 'completed'
        ORDER BY created_at DESC 
        LIMIT 50
    ''')
    orders = cursor.fetchall()
    conn.close()
    
    if not orders:
        await callback.message.edit_text(
            "📦 Нет активных заказов.\n\n"
            "Все заказы обработаны!",
            reply_markup=kb.get_admin_keyboard()
        )
        await callback.answer()
        return
    
    text = "<b>🗄 УПРАВЛЕНИЕ ЗАКАЗАМИ</b>\n\n"
    text += f"📋 Активных заказов: {len(orders)}\n\n"
    
    builder = InlineKeyboardBuilder()
    status_map = {
        "pending": "🆕 Новый",
        "in_progress": "⚙️ В работе", 
        "ready": "✅ Готов",
        "completed": "📦 Завершен"
    }
    
    for o in orders:
        status = status_map.get(o['status'], o['status'])
        username_display = f"@{o['username']}" if o['username'] else "без юзернейма"
        text += f"🔹 <b>№{o['id']}</b> | {status} | {o['total_amount']}₽ | {username_display}\n"
        
        # Кнопки для каждого заказа
        builder.row(
            InlineKeyboardButton(text=f"⚙️ №{o['id']}", callback_data=f"manage_order_{o['id']}"),
            InlineKeyboardButton(text=f"🗑 Удалить №{o['id']}", callback_data=f"delete_order_{o['id']}")
        )
    
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

async def admin_order_details(callback: CallbackQuery):
    """Детали заказа"""
    order_id = int(callback.data.replace("manage_order_", ""))
    order = db.get_order(order_id)
    
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    
    try:
        items = json.loads(order['items'])
        items_text = "\n".join([f"▫️ {item['name']} x{item['quantity']} = {item['price'] * item['quantity']} руб." for item in items])
    except:
        items_text = "Ошибка загрузки товаров"
    
    status_map = {
        "pending": "🆕 Новый",
        "in_progress": "⚙️ В работе",
        "ready": "✅ Готов",
        "completed": "📦 Завершен"
    }
    status_display = status_map.get(order['status'], order['status'])
    username_display = f"@{order['username']}" if order['username'] else "без юзернейма"
    
    text = (f"<b>📋 ДЕТАЛИ ЗАКАЗА №{order['id']}</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"👤 Покупатель: {username_display}\n"
            f"📅 Дата: {order['created_at']}\n"
            f"🔄 Статус: {status_display}\n"
            f"💳 Оплата: {'Карта' if order['payment_method'] == 'card' else 'Наличные'}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<b>📦 Товары:</b>\n{items_text}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 Сумма: {order['total_amount']} руб.\n"
            f"📦 Себестоимость: {order['total_cost']} руб.\n"
            f"📈 Прибыль: {order['total_amount'] - order['total_cost']} руб.\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>Выберите действие:</b>")
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🛠 В работу", callback_data=f"set_status_{order_id}_in_progress"))
    builder.row(InlineKeyboardButton(text="✅ Готов", callback_data=f"set_status_{order_id}_ready"))
    builder.row(InlineKeyboardButton(text="📦 Завершить", callback_data=f"set_status_{order_id}_completed"))
    builder.row(InlineKeyboardButton(text="🗑 Удалить заказ", callback_data=f"delete_order_{order_id}"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="admin_orders"))
    
    await callback.message.delete()
    await callback.message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

async def admin_set_order_status(callback: CallbackQuery):
    parts = callback.data.split("_")
    order_id = int(parts[2])
    new_status = "_".join(parts[3:])
    db.update_order_status(order_id, new_status)
    status_names = {"in_progress": "В работе", "ready": "Готов", "completed": "Завершен"}
    status_display = status_names.get(new_status, new_status)
    await callback.message.answer(f"✅ Статус заказа №{order_id} изменен на <b>{status_display}</b>", parse_mode="HTML")
    await callback.answer()

async def delete_product_callback(callback: CallbackQuery):
    """Удаление товара (исправлено)"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return

    # Извлекаем ID: поддерживает форматы "delete_product_123" и "delete_123"
    product_id = int(callback.data.split("_")[-1])
    
    product = db.get_product(product_id)
    if not product:
        await callback.answer("❌ Товар уже удален или не найден", show_alert=True)
        return

    db.delete_product(product_id)
    await callback.answer(f"✅ Товар '{product['name']}' удален", show_alert=True)
    
    # Обновляем сообщение (возвращаемся в админку или список категорий)
    await callback.message.delete()
    await callback.message.answer("🔧 Товар удален. Вернитесь в меню категорий.", 
                                 reply_markup=kb.get_admin_keyboard())
    
async def cancel_action_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.delete()
    except:
        pass # Игнорируем, если сообщение уже удалено
    
    # Отправляем сообщение в тот же чат, используя bot или callback.message.chat.id
    await callback.message.answer(
        "❌ Действие отменено.", 
        reply_markup=kb.get_main_keyboard(callback.from_user.id)
    )
    await callback.answer()
# ==========================================
#         АДМИН: ДОБАВЛЕНИЕ ТОВАРА
# ==========================================

async def admin_add_product_start(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await delete_prev(callback.from_user.id, callback.message.chat.id, bot)
    await state.set_state(AddProductStates.name)
    sent = await callback.message.answer("📝 Введите название товара:", reply_markup=kb.get_cancel_keyboard())
    await db.save_message(callback.from_user.id, sent.message_id)
    await callback.answer()

async def add_product_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(AddProductStates.description)
    sent = await message.answer("📄 Введите описание товара:")
    await db.save_message(message.from_user.id, sent.message_id)

async def add_product_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(AddProductStates.price)
    sent = await message.answer("💰 Введите цену продажи (число):")
    await db.save_message(message.from_user.id, sent.message_id)

async def add_product_price(message: Message, state: FSMContext):
    if not message.text.replace('.', '', 1).isdigit():
        await message.answer("⚠️ Введите число.")
        return
    await state.update_data(price=float(message.text))
    await state.set_state(AddProductStates.cost_price)
    await message.answer("💰 Введите цену закупки (себестоимость):")

async def add_product_cost_price(message: Message, state: FSMContext):
    if not message.text.replace('.', '', 1).isdigit():
        await message.answer("⚠️ Введите число.")
        return
    await state.update_data(cost_price=float(message.text))
    await state.set_state(AddProductStates.stock)
    await message.answer("📦 Введите количество товара в наличии:")

async def add_product_stock(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ Введите целое число.")
        return
    await state.update_data(stock=int(message.text))
    await state.set_state(AddProductStates.category)
    await message.answer("📁 Выберите категорию:", reply_markup=kb.get_categories_keyboard())

async def add_product_category(callback: CallbackQuery, state: FSMContext, bot: Bot):
    category_id = int(callback.data.split("_")[1])
    await state.update_data(category_id=category_id)
    await state.set_state(AddProductStates.image)
    await delete_prev(callback.from_user.id, callback.message.chat.id, bot)
    sent = await callback.message.answer("📸 Отправьте фото товара:")
    await db.save_message(callback.from_user.id, sent.message_id)
    await callback.answer()

async def add_product_image(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("⚠️ Отправьте фото.")
        return
    data = await state.get_data()
    photo_id = message.photo[-1].file_id
    db.add_product(data['name'], data['description'], data['price'], data['cost_price'], 
                   data['stock'], data['category_id'], photo_id, 0)
    await state.clear()
    await message.answer("✅ Товар успешно добавлен!", reply_markup=kb.get_main_keyboard(message.from_user.id))

# ==========================================
#         АДМИН: ДОБАВЛЕНИЕ ПРЕДЗАКАЗА
# ==========================================

async def admin_add_preorder_start(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await delete_prev(callback.from_user.id, callback.message.chat.id, bot)
    await state.set_state(AddPreorderStates.name)
    sent = await callback.message.answer("📝 Введите название товара (предзаказ):", reply_markup=kb.get_cancel_keyboard())
    await db.save_message(callback.from_user.id, sent.message_id)
    await callback.answer()

async def add_preorder_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(AddPreorderStates.description)
    await message.answer("📄 Введите описание товара:")

async def add_preorder_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(AddPreorderStates.price)
    await message.answer("💰 Введите цену продажи (число):")

async def add_preorder_price(message: Message, state: FSMContext):
    if not message.text.replace('.', '', 1).isdigit():
        await message.answer("⚠️ Введите число.")
        return
    await state.update_data(price=float(message.text))
    await state.set_state(AddPreorderStates.cost_price)
    await message.answer("💰 Введите цену закупки (себестоимость):")

async def add_preorder_cost_price(message: Message, state: FSMContext):
    if not message.text.replace('.', '', 1).isdigit():
        await message.answer("⚠️ Введите число.")
        return
    await state.update_data(cost_price=float(message.text))
    await state.set_state(AddPreorderStates.category)
    await message.answer("📁 Выберите категорию:", reply_markup=kb.get_categories_keyboard())

async def add_preorder_category(callback: CallbackQuery, state: FSMContext, bot: Bot):
    category_id = int(callback.data.split("_")[1])
    await state.update_data(category_id=category_id)
    await state.set_state(AddPreorderStates.image)
    await delete_prev(callback.from_user.id, callback.message.chat.id, bot)
    sent = await callback.message.answer("📸 Отправьте фото товара:")
    await db.save_message(callback.from_user.id, sent.message_id)
    await callback.answer()

async def add_preorder_image(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("⚠️ Отправьте фото.")
        return
    data = await state.get_data()
    photo_id = message.photo[-1].file_id
    db.add_product(data['name'], data['description'], data['price'], data['cost_price'], 
                   999, data['category_id'], photo_id, 1)
    await state.clear()
    await message.answer("✅ Предзаказ успешно добавлен!", reply_markup=kb.get_main_keyboard(message.from_user.id))

# ==========================================
#         АДМИН: РАССЫЛКА
# ==========================================

async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📢 Введите текст или отправьте фото для рассылки:", reply_markup=kb.get_cancel_keyboard())
    await state.set_state(BroadcastStates.text)
    await callback.answer()

async def admin_broadcast_send(message: Message, state: FSMContext, bot: Bot):
    users = db.get_all_users()
    if not users:
        await message.answer("❌ Нет пользователей.")
        await state.clear()
        return
    count = 0
    msg = await message.answer(f"⏳ Рассылка на {len(users)} чел...")
    for user_id in users:
        try:
            if message.photo:
                await bot.send_photo(user_id, message.photo[-1].file_id, caption=message.caption)
            elif message.text:
                await bot.send_message(user_id, message.text)
            count += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await state.clear()
    await msg.edit_text(f"✅ Рассылка завершена. Получили {count} чел.")

# ==========================================
#         АДМИН: УПРАВЛЕНИЕ КАТЕГОРИЯМИ
# ==========================================

async def admin_categories_menu(callback: CallbackQuery):
    await callback.message.edit_text("<b>📁 УПРАВЛЕНИЕ КАТЕГОРИЯМИ</b>\n\nВыберите действие:", 
                                     parse_mode="HTML", reply_markup=kb.get_category_admin_keyboard())
    await callback.answer()

async def admin_add_category_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📝 Введите код категории (латиницей, без пробелов):", reply_markup=kb.get_cancel_keyboard())
    await state.set_state(CategoryStates.add_code)
    await callback.answer()

async def add_category_code(message: Message, state: FSMContext):
    code = message.text.strip().lower().replace(" ", "_")
    if not code.replace("_", "").isalnum():
        await message.answer("❌ Код может содержать только буквы, цифры и _")
        return
    if db.get_category_by_code(code):
        await message.answer(f"❌ Категория с кодом '{code}' уже существует")
        return
    await state.update_data(code=code)
    await state.set_state(CategoryStates.add_name)
    await message.answer("📝 Введите название категории:")

async def add_category_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(CategoryStates.add_emoji)
    await message.answer("😊 Введите эмодзи для категории (например, 💨):")

async def add_category_emoji(message: Message, state: FSMContext):
    await state.update_data(emoji=message.text.strip())
    await state.set_state(CategoryStates.add_sort)
    await message.answer("🔢 Введите порядок сортировки (число, чем меньше тем выше):")

async def add_category_sort(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ Введите число")
        return
    data = await state.get_data()
    category_id = db.add_category(data['code'], data['name'], data['emoji'], int(message.text))
    if category_id:
        await message.answer(f"✅ Категория {data['emoji']} {data['name']} добавлена!", reply_markup=kb.get_main_keyboard(message.from_user.id))
    else:
        await message.answer("❌ Ошибка при добавлении", reply_markup=kb.get_main_keyboard(message.from_user.id))
    await state.clear()

async def admin_edit_categories(callback: CallbackQuery):
    await callback.message.edit_text("<b>📝 ВЫБЕРИТЕ КАТЕГОРИЮ ДЛЯ РЕДАКТИРОВАНИЯ</b>", 
                                     parse_mode="HTML", reply_markup=kb.get_categories_edit_keyboard())
    await callback.answer()

async def admin_edit_category_select(callback: CallbackQuery):
    category_id = int(callback.data.split("_")[2])
    category = db.get_category(category_id)
    if not category:
        await callback.answer("Категория не найдена")
        return
    await callback.message.edit_text(
        f"<b>Редактирование:</b>\n\n{category['emoji']} <b>{category['name']}</b>\n"
        f"Код: <code>{category['code']}</code>\nСтатус: {'✅ Активна' if category['is_active'] else '❌ Скрыта'}\n"
        f"Порядок: {category['sort_order']}\n\nВыберите действие:",
        parse_mode="HTML", reply_markup=kb.get_category_action_keyboard(category_id))
    await callback.answer()

async def admin_category_rename(callback: CallbackQuery, state: FSMContext):
    category_id = int(callback.data.split("_")[2])
    await state.update_data(edit_category_id=category_id)
    await state.set_state(CategoryStates.edit_name)
    await callback.message.answer("📝 Введите новое название:", reply_markup=kb.get_cancel_keyboard())
    await callback.answer()

async def admin_category_rename_save(message: Message, state: FSMContext):
    data = await state.get_data()
    category_id = data.get('edit_category_id')
    if category_id:
        db.update_category(category_id, name=message.text.strip())
        await message.answer(f"✅ Название изменено на: {message.text}", reply_markup=kb.get_main_keyboard(message.from_user.id))
    await state.clear()

async def admin_category_change_emoji(callback: CallbackQuery, state: FSMContext):
    category_id = int(callback.data.split("_")[3])
    await state.update_data(edit_category_id=category_id)
    await state.set_state(CategoryStates.edit_emoji)
    await callback.message.answer("😊 Введите новый эмодзи:", reply_markup=kb.get_cancel_keyboard())
    await callback.answer()

async def admin_category_emoji_save(message: Message, state: FSMContext):
    data = await state.get_data()
    category_id = data.get('edit_category_id')
    if category_id:
        db.update_category(category_id, emoji=message.text.strip())
        await message.answer(f"✅ Эмодзи изменен на: {message.text}", reply_markup=kb.get_main_keyboard(message.from_user.id))
    await state.clear()

async def admin_category_change_sort(callback: CallbackQuery, state: FSMContext):
    category_id = int(callback.data.split("_")[3])
    await state.update_data(edit_category_id=category_id)
    await state.set_state(CategoryStates.edit_sort)
    await callback.message.answer("🔢 Введите новый порядок сортировки (число):", reply_markup=kb.get_cancel_keyboard())
    await callback.answer()

async def admin_category_sort_save(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ Введите число")
        return
    data = await state.get_data()
    category_id = data.get('edit_category_id')
    if category_id:
        db.update_category(category_id, sort_order=int(message.text))
        await message.answer(f"✅ Порядок изменен на: {message.text}", reply_markup=kb.get_main_keyboard(message.from_user.id))
    await state.clear()

async def admin_category_toggle(callback: CallbackQuery):
    category_id = int(callback.data.split("_")[2])
    category = db.get_category(category_id)
    if category:
        new_status = 0 if category['is_active'] else 1
        db.update_category(category_id, is_active=new_status)
        await callback.answer(f"✅ Категория {'активна' if new_status else 'скрыта'}")
    await admin_edit_categories(callback)

async def admin_delete_category_menu(callback: CallbackQuery):
    await callback.message.edit_text("<b>🗑 УДАЛЕНИЕ КАТЕГОРИЙ</b>\n\n⚠️ Удалить можно только категории без товаров.",
                                     parse_mode="HTML", reply_markup=kb.get_categories_delete_keyboard())
    await callback.answer()

async def admin_category_confirm_delete(callback: CallbackQuery):
    category_id = int(callback.data.split("_")[3])
    category = db.get_category(category_id)
    if category:
        products_count = len(db.get_products_by_category_id(category_id))
        if products_count > 0:
            await callback.message.edit_text(f"❌ В категории {products_count} товаров! Сначала удалите их.",
                                             reply_markup=kb.get_category_admin_keyboard())
        else:
            await callback.message.edit_text(f"⚠️ Удалить категорию {category['emoji']} {category['name']}?",
                                             reply_markup=kb.get_confirm_delete_keyboard(category_id))
    await callback.answer()

async def admin_category_delete(callback: CallbackQuery):
    category_id = int(callback.data.split("_")[2])
    category = db.get_category(category_id)
    if category and db.delete_category(category_id):
        await callback.message.delete()
        await callback.message.answer(f"✅ Категория {category['emoji']} {category['name']} удалена!",
                                      reply_markup=kb.get_main_keyboard(callback.from_user.id))
    else:
        await callback.message.edit_text("❌ Нельзя удалить категорию с товарами!", reply_markup=kb.get_category_admin_keyboard())
    await callback.answer()

async def admin_no_delete(callback: CallbackQuery):
    await callback.answer("❌ Нельзя удалить категорию с товарами!", show_alert=True)

    
async def admin_back(callback: CallbackQuery):
    """Возврат в админ панель"""
    if callback.from_user.id in config.ADMIN_IDS:
        await callback.message.edit_text(
            "🔧 Панель управления:",
            reply_markup=kb.get_admin_keyboard()
        )
        await callback.answer()

async def view_product(callback: CallbackQuery):
    """Показывает подробную информацию о товаре"""
    product_id = int(callback.data.split("_")[2])
    product = db.get_product(product_id)
    
    if not product:
        await callback.answer("❌ Товар не найден", show_alert=True)
        return
    
    is_admin = callback.from_user.id in config.ADMIN_IDS
    
    # Формируем текст с информацией о товаре
    stock_text = ""
    if product['is_preorder']:
        stock_text = "\n\n⚠️ <b>ПРЕДЗАКАЗ!</b>\n⏰ Товар появится после предзаказа."
    elif product['stock'] <= 0:
        stock_text = "\n\n❌ <b>ТОВАР ЗАКОНЧИЛСЯ!</b>"
    elif product['stock'] <= 5:
        stock_text = f"\n\n⚠️ <b>Осталось всего {product['stock']} шт.!</b>"
    
    text = (
        f"<b>{product['name']}</b>\n\n"
        f"{product['description']}\n\n"
        f"💰 <b>Цена:</b> {product['price']} руб.{stock_text}"
    )
    
    # Добавляем для админа информацию о себестоимости и остатке
    if is_admin:
        text += f"\n\n📊 <b>Для админа:</b>\n"
        text += f"📦 Себестоимость: {product['cost_price']} руб.\n"
        text += f"📊 Остаток: {product['stock']} шт.\n"
        if product['is_preorder']:
            text += f"⏰ Тип: Предзаказ"
    
    # Создаем клавиатуру для товара
    builder = InlineKeyboardBuilder()
    
    # Кнопка "В корзину" - если товар есть в наличии
    if (product['stock'] > 0 or product['is_preorder']) and product['is_active']:
        builder.row(InlineKeyboardButton(text="🛒 Добавить в корзину", callback_data=f"buy_{product_id}"))
    
    # Кнопка "Назад к списку"
    builder.row(InlineKeyboardButton(text="⬅️ Назад к списку", callback_data=f"back_to_products_{product['category_id']}"))
    
    # Кнопки для админа
    if is_admin:
        builder.row(InlineKeyboardButton(text="📦 Изменить количество", callback_data=f"update_stock_{product_id}"))
        builder.row(InlineKeyboardButton(text="🗑 Удалить товар", callback_data=f"delete_{product_id}"))
    
    # Отправляем сообщение с фото или без
    if product['image_id']:
        await callback.message.delete()  # Удаляем сообщение со списком товаров
        await callback.message.answer_photo(
            product['image_id'], 
            caption=text, 
            parse_mode="HTML", 
            reply_markup=builder.as_markup()
        )
    else:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    
    await callback.answer()

async def back_to_products(callback: CallbackQuery):
    """Возврат к списку товаров в категории"""
    category_id = int(callback.data.split("_")[3])
    products = db.get_products_by_category_id(category_id)
    category = db.get_category(category_id)
    
    if not products:
        await callback.message.edit_text("В этой категории пока нет товаров.")
        await callback.answer()
        return
    
    # Создаем клавиатуру со списком товаров
    builder = InlineKeyboardBuilder()
    
    for product in products:
        emoji = "⏰" if product['is_preorder'] else "📦"
        if product['stock'] <= 0 and not product['is_preorder']:
            emoji = "❌"
        
        name = product['name']
        if product['stock'] <= 5 and product['stock'] > 0 and not product['is_preorder']:
            name += f" ⚠️{product['stock']}"
        
        builder.add(InlineKeyboardButton(
            text=f"{emoji} {name} - {product['price']}₽",
            callback_data=f"view_product_{product['id']}"
        ))
    
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="⬅️ Назад к категориям", callback_data="back_to_categories"))
    
    # Если предыдущее сообщение было с фото, удаляем его и отправляем новое
    try:
        await callback.message.delete()
    except:
        pass
    
    await callback.message.answer(
        f"📁 <b>{category['emoji']} {category['name']}</b>\n\n"
        "Выберите товар для просмотра:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

async def back_to_categories(callback: CallbackQuery):
    """Возврат к списку категорий"""
    await callback.message.delete()
    await callback.message.answer(
        "📁 Выберите категорию:",
        reply_markup=kb.get_categories_keyboard()
    )
    await callback.answer()

async def back_to_main_menu(callback: CallbackQuery):
    """Возврат в главное меню"""
    await callback.message.delete()
    await callback.message.answer(
        "👋 Главное меню:",
        reply_markup=kb.get_main_keyboard(callback.from_user.id)
    )
    await callback.answer()

async def catalog_text_btn(message: Message):
    """Обработчик кнопки Каталог"""
    await message.answer(
        "📁 Выберите категорию:",
        reply_markup=kb.get_categories_keyboard()
    )

async def admin_mass_upload_start(callback: CallbackQuery, state: FSMContext):
    """Начало массовой загрузки товаров"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    await state.set_state(MassUploadStates.file)
    
    # Создаем пример файла
    sample_data = {
        'name': ['HOOKAH 5000', 'ELF BAR 3000', 'SALT NICOTINE 30ml'],
        'description': ['Вкус: Арбуз', 'Вкус: Манго', 'Крепость: 20mg'],
        'price': [1500, 1200, 800],
        'cost_price': [1000, 800, 500],
        'stock': [50, 30, 100]
    }
    
    df = pd.DataFrame(sample_data)
    
    # Создаем Excel файл в памяти
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Товары')
    
    output.seek(0)
    
    await callback.message.answer_document(
        BufferedInputFile(output.getvalue(), filename="sample_products.xlsx"),
        caption="📊 <b>МАССОВАЯ ЗАГРУЗКА ТОВАРОВ</b>\n\n"
                "1. Скачайте пример файла\n"
                "2. Заполните его своими товарами\n"
                "3. Отправьте файл сюда\n\n"
                "📌 <b>Формат колонок:</b>\n"
                "• name - название товара (обязательно)\n"
                "• description - описание\n"
                "• price - цена (обязательно)\n"
                "• cost_price - себестоимость\n"
                "• stock - количество\n\n"
                "После загрузки вы сможете добавить фото для каждого товара",
        parse_mode="HTML"
    )
    await callback.answer()

async def process_products_file(message: Message, state: FSMContext, bot: Bot):
    """Обработка загруженного файла с товарами"""
    if not message.document:
        await message.answer("❌ Пожалуйста, отправьте файл Excel (.xlsx)")
        return
    
    # Проверяем расширение
    if not message.document.file_name.endswith(('.xlsx', '.xls')):
        await message.answer("❌ Поддерживаются только файлы .xlsx и .xls")
        return
    
    # Скачиваем файл
    file = await bot.get_file(message.document.file_id)
    file_content = await bot.download_file(file.file_path)
    
    # Сохраняем в состоянии
    await state.update_data(file_content=file_content.getvalue())
    
    # Показываем выбор категории
    await state.set_state(MassUploadStates.category)
    await message.answer(
        "📁 Выберите категорию для загружаемых товаров:",
        reply_markup=kb.get_categories_keyboard()
    )

async def process_mass_upload_category(callback: CallbackQuery, state: FSMContext):
    """Выбор категории для массовой загрузки"""
    category_id = int(callback.data.split("_")[1])
    data = await state.get_data()
    file_content = data.get('file_content')
    
    if not file_content:
        await callback.answer("❌ Ошибка: файл не найден", show_alert=True)
        await state.clear()
        return
    
    # Парсим товары
    products, errors = db.parse_products_from_excel(file_content, category_id)
    
    if not products:
        await callback.message.edit_text(
            f"❌ Ошибка загрузки:\n{chr(10).join(errors)}",
            reply_markup=kb.get_cancel_keyboard()
        )
        await state.clear()
        await callback.answer()
        return
    
    # Проверяем существующие товары
    existing_products, new_products = db.check_existing_products(products)
    
    # Сохраняем в состоянии
    await state.update_data(
        products=products,
        new_products=new_products,
        existing_products=existing_products,
        category_id=category_id, 
        current_index=0, 
        product_photos={}
    )
    
    # Показываем предпросмотр с информацией о существующих товарах
    preview_text = "<b>📊 ПРЕДПРОСМОТР ТОВАРОВ</b>\n\n"
    preview_text += f"Всего товаров: {len(products)}\n"
    preview_text += f"🆕 Новых товаров: {len(new_products)}\n"
    preview_text += f"🔄 Обновляемых товаров: {len(existing_products)}\n"
    preview_text += f"📁 Категория: {db.get_category(category_id)['name']}\n\n"
    
    if existing_products:
        preview_text += "<b>🔄 БУДУТ ОБНОВЛЕНЫ:</b>\n"
        for p in existing_products[:5]:
            old_stock = p['existing_stock']
            new_stock = old_stock + p['stock']
            preview_text += f"• {p['name']}: {old_stock} → {new_stock} шт.\n"
        if len(existing_products) > 5:
            preview_text += f"... и еще {len(existing_products) - 5} товаров\n"
        preview_text += "\n"
    
    if new_products:
        preview_text += "<b>🆕 НОВЫЕ ТОВАРЫ:</b>\n"
        for i, p in enumerate(new_products[:5], 1):
            preview_text += f"{i}. {p['name']} - {p['price']}₽ (ост: {p['stock']})\n"
        if len(new_products) > 5:
            preview_text += f"... и еще {len(new_products) - 5} товаров\n"
        preview_text += "\n"
    
    if errors:
        preview_text += f"⚠️ <b>Ошибки:</b>\n{chr(10).join(errors[:3])}\n\n"
    
    # Если есть новые товары, запрашиваем фото
    if new_products:
        preview_text += "📸 <b>Теперь нужно добавить фото для НОВЫХ товаров</b>\n\n"
        preview_text += f"📷 Отправьте фото для: <b>{new_products[0]['name']}</b>\n\n"
        preview_text += "Или нажмите кнопку 'Пропустить', чтобы продолжить без фото\n"
        preview_text += "Для существующих товаров фото не меняются"
        
        # Клавиатура
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="⏭️ Пропустить фото", callback_data="skip_photo"))
        builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_mass_upload"))
        
        await callback.message.edit_text(preview_text, parse_mode="HTML", reply_markup=builder.as_markup())
        await state.set_state(MassUploadStates.waiting_photos)
    else:
        # Нет новых товаров, сразу обновляем существующие
        await finish_upload_without_photos(callback, state)
    
    await callback.answer()


async def confirm_mass_upload(callback: CallbackQuery, state: FSMContext):
    """Подтверждение массовой загрузки"""
    data = await state.get_data()
    products = data.get('products', [])
    
    if not products:
        await callback.answer("❌ Нет товаров для загрузки", show_alert=True)
        await state.clear()
        return
    
    # Добавляем товары
    added_count = db.add_products_batch(products)
    
    await callback.message.edit_text(
        f"✅ <b>УСПЕШНО ДОБАВЛЕНО</b>\n\n"
        f"📦 Товаров: {added_count} из {len(products)}\n\n"
        f"Теперь вы можете добавить фото для каждого товара через раздел управления товарами.",
        parse_mode="HTML",
        reply_markup=kb.get_admin_keyboard()
    )
    
    await state.clear()
    await callback.answer()

async def cancel_mass_upload(callback: CallbackQuery, state: FSMContext):
    """Отмена массовой загрузки"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Массовая загрузка отменена",
        reply_markup=kb.get_admin_keyboard()
    )
    await callback.answer()

async def admin_update_stock_start(callback: CallbackQuery, state: FSMContext):
    """Начало обновления количества товара"""
    product_id = int(callback.data.split("_")[2])
    product = db.get_product(product_id)
    
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return
    
    await state.update_data(product_id=product_id, product_name=product['name'])
    await state.set_state("waiting_stock")
    
    await callback.message.answer(
        f"📦 Товар: <b>{product['name']}</b>\n"
        f"Текущее количество: {product['stock']} шт.\n\n"
        f"Введите новое количество:",
        parse_mode="HTML",
        reply_markup=kb.get_cancel_keyboard()
    )
    await callback.answer()

async def admin_update_stock(message: Message, state: FSMContext):
    """Обновление количества товара"""
    if not message.text.isdigit():
        await message.answer("⚠️ Введите число")
        return
    
    data = await state.get_data()
    product_id = data['product_id']
    new_quantity = int(message.text)
    
    db.update_product_quantity(product_id, new_quantity)
    
    await message.answer(
        f"✅ Количество товара обновлено!\n\n"
        f"📦 {data['product_name']}\n"
        f"Новое количество: {new_quantity} шт.",
        reply_markup=kb.get_main_keyboard(message.from_user.id)
    )
    
    await state.clear()

async def admin_notification_settings(callback: CallbackQuery):
    """Панель настроек уведомлений"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    settings = db.get_all_notification_settings()
    
    text = "<b>⚙️ НАСТРОЙКИ УВЕДОМЛЕНИЙ</b>\n\n"
    text += "Текущие настройки:\n\n"
    
    for key, data in settings.items():
        value = data['value']
        desc = data['description']
        
        if key == 'low_stock_threshold':
            text += f"📊 {desc}: <b>{value} шт.</b>\n"
        elif key == 'critical_stock_threshold':
            text += f"🔴 {desc}: <b>{value} шт.</b>\n"
        elif key == 'enable_low_stock_notify':
            status = "✅ Включено" if value == '1' else "❌ Отключено"
            text += f"⚠️ {desc}: {status}\n"
        elif key == 'enable_out_of_stock_notify':
            status = "✅ Включено" if value == '1' else "❌ Отключено"
            text += f"❌ {desc}: {status}\n"
        elif key == 'notify_frequency_hours':
            text += f"⏰ {desc}: <b>{value} ч.</b>\n"
        elif key == 'notify_admins':
            status = "✅ Включено" if value == '1' else "❌ Отключено"
            text += f"👥 {desc}: {status}\n"
        elif key == 'notify_admins_about_each':
            status = "✅ По отдельности" if value == '1' else "📋 Списком"
            text += f"📢 {desc}: {status}\n"
    
    text += "\nВыберите настройку для изменения:"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 Порог низкого остатка", callback_data="notify_set_low_threshold"))
    builder.row(InlineKeyboardButton(text="🔴 Порог критического остатка", callback_data="notify_set_critical_threshold"))
    builder.row(InlineKeyboardButton(text="⚠️ Вкл/Выкл уведомления о низком остатке", callback_data="notify_toggle_low"))
    builder.row(InlineKeyboardButton(text="❌ Вкл/Выкл уведомления о закончившихся", callback_data="notify_toggle_out"))
    builder.row(InlineKeyboardButton(text="⏰ Частота проверки", callback_data="notify_set_frequency"))
    builder.row(InlineKeyboardButton(text="👥 Уведомлять админов", callback_data="notify_toggle_admins"))
    builder.row(InlineKeyboardButton(text="📢 Формат уведомлений", callback_data="notify_toggle_format"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    
    # Редактируем сообщение
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

async def set_low_stock_threshold(callback: CallbackQuery, state: FSMContext):
    """Установка порога низкого остатка"""
    await state.set_state("waiting_low_threshold")
    
    # Отвечаем на callback
    await callback.answer()
    
    # Отправляем новое сообщение с запросом ввода
    await callback.message.answer(
        "📊 Введите порог низкого остатка (число):\n\n"
        "Пример: если ввести 10, то при остатке 10 и менее будут приходить уведомления\n\n"
        "Или нажмите ❌ Отмена",
        reply_markup=kb.get_cancel_keyboard()
    )

async def set_critical_stock_threshold(callback: CallbackQuery, state: FSMContext):
    """Установка порога критического остатка"""
    await state.set_state("waiting_critical_threshold")
    
    await callback.answer()
    
    await callback.message.answer(
        "🔴 Введите порог критического остатка (число):\n\n"
        "Пример: если ввести 2, то при остатке 2 и менее будут приходить срочные уведомления\n\n"
        "Или нажмите ❌ Отмена",
        reply_markup=kb.get_cancel_keyboard()
    )

async def set_notification_frequency(callback: CallbackQuery, state: FSMContext):
    """Установка частоты проверки"""
    await state.set_state("waiting_frequency")
    
    await callback.answer()
    
    await callback.message.answer(
        "⏰ Введите частоту проверки в часах (число):\n\n"
        "Пример: если ввести 2, то проверка будет каждые 2 часа\n\n"
        "Или нажмите ❌ Отмена",
        reply_markup=kb.get_cancel_keyboard()
    )

async def save_threshold_setting(message: Message, state: FSMContext):
    """Сохранение настройки порога"""
    if not message.text.isdigit():
        await message.answer("⚠️ Введите число")
        return
    
    value = int(message.text)
    current_state = await state.get_state()
    
    if current_state == "waiting_low_threshold":
        if value < 1:
            await message.answer("⚠️ Порог должен быть не менее 1")
            return
        db.update_notification_setting('low_stock_threshold', str(value))
        await message.answer(f"✅ Порог низкого остатка установлен: {value} шт.")
    elif current_state == "waiting_critical_threshold":
        if value < 1:
            await message.answer("⚠️ Порог должен быть не менее 1")
            return
        db.update_notification_setting('critical_stock_threshold', str(value))
        await message.answer(f"✅ Порог критического остатка установлен: {value} шт.")
    
    await state.clear()
    
    # Показываем обновленные настройки
    await message.answer(
        "⚙️ Настройки обновлены!",
        reply_markup=kb.get_main_keyboard(message.from_user.id)
    )

async def save_frequency_setting(message: Message, state: FSMContext):
    """Сохранение частоты проверки"""
    if not message.text.isdigit():
        await message.answer("⚠️ Введите число")
        return
    
    value = int(message.text)
    if value < 1:
        await message.answer("⚠️ Частота должна быть не менее 1 часа")
        return
    
    db.update_notification_setting('notify_frequency_hours', str(value))
    await message.answer(f"✅ Частота проверки установлена: каждые {value} час(ов)")
    await state.clear()

async def toggle_notification_setting(callback: CallbackQuery):
    """Переключение настройки уведомлений"""
    setting_map = {
        'notify_toggle_low': 'enable_low_stock_notify',
        'notify_toggle_out': 'enable_out_of_stock_notify',
        'notify_toggle_admins': 'notify_admins',
        'notify_toggle_format': 'notify_admins_about_each'
    }
    
    callback_data = callback.data
    if callback_data in setting_map:
        setting_key = setting_map[callback_data]
        current_value = db.get_notification_setting(setting_key)
        new_value = '0' if current_value == '1' else '1'
        db.update_notification_setting(setting_key, new_value)
        
        await callback.answer("✅ Настройка изменена")
        
        # Обновляем отображение настроек
        await admin_notification_settings(callback)
    else:
        await callback.answer()

async def checkout_confirm_payment(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Подтверждение оплаты картой"""
    data = await state.get_data()
    
    # Удаляем сообщение, в котором была кнопка "Я оплатил"
    try:
        await callback.message.delete()
    except:
        pass

    # Отправляем НОВОЕ сообщение с Reply-клавиатурой (главное меню)
    await callback.message.answer(
        "✅ Спасибо! Ваш заказ передан в обработку.\nНаш менеджер свяжется с вами.",
        reply_markup=kb.get_main_keyboard(callback.from_user.id)
    )
    
    # Очищаем состояние и закрываем уведомление в Telegram
    await state.clear()
    await callback.answer()
    
    # Запускаем фоновую задачу по созданию заказа и уведомлению админов
    asyncio.create_task(create_order_from_data(callback, state, bot, data))
async def admin_promocodes_menu(callback: CallbackQuery):
    """Меню управления промокодами"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    promocodes_list = promocodes.get_all_promocodes()
    
    text = "<b>🎫 УПРАВЛЕНИЕ ПРОМОКОДАМИ</b>\n\n"
    
    if promocodes_list:
        text += "Активные промокоды:\n\n"
        for p in promocodes_list[:10]:
            status = "✅" if p['is_active'] else "❌"
            text += f"{status} <b>{p['code']}</b> - "
            if p['discount_type'] == 'percentage':
                text += f"{p['discount_value']}% скидка\n"
            else:
                text += f"{p['discount_value']}₽ скидка\n"
            text += f"   Использовано: {p['used_count']}/{p['usage_limit'] if p['usage_limit'] > 0 else '∞'}\n"
    else:
        text += "Нет активных промокодов\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_create_promocode"))
    builder.row(InlineKeyboardButton(text="📊 Экспорт заказов", callback_data="admin_export_orders"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

async def admin_create_promocode_start(callback: CallbackQuery, state: FSMContext):
    """Начало создания промокода"""
    await state.set_state("waiting_promocode_code")
    await callback.message.answer(
        "🎫 Введите код промокода (латиницей, цифры):\n\n"
        "Пример: SUMMER2024",
        reply_markup=kb.get_cancel_keyboard()
    )
    await callback.answer()

async def create_promocode_code(message: Message, state: FSMContext):
    """Получение кода промокода"""
    await state.update_data(code=message.text.upper())
    await state.set_state("waiting_promocode_discount_type")
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Процентная скидка", callback_data="promo_type_percentage"))
    builder.row(InlineKeyboardButton(text="Фиксированная скидка", callback_data="promo_type_fixed"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    
    await message.answer(
        "📊 Выберите тип скидки:",
        reply_markup=builder.as_markup()
    )

async def create_promocode_discount_type(callback: CallbackQuery, state: FSMContext):
    """Выбор типа скидки"""
    discount_type = callback.data.replace("promo_type_", "")
    await state.update_data(discount_type=discount_type)
    await state.set_state("waiting_promocode_discount_value")
    
    text = "💰 Введите размер скидки:\n\n"
    if discount_type == 'percentage':
        text += "Пример: 10 (10% скидка)"
    else:
        text += "Пример: 500 (500₽ скидка)"
    
    await callback.message.answer(text, reply_markup=kb.get_cancel_keyboard())
    await callback.answer()

async def create_promocode_discount_value(message: Message, state: FSMContext):
    """Получение значения скидки"""
    if not message.text.replace('.', '', 1).isdigit():
        await message.answer("⚠️ Введите число")
        return
    
    data = await state.get_data()
    await state.update_data(discount_value=float(message.text))
    await state.set_state("waiting_promocode_usage_limit")
    
    await message.answer(
        "🔢 Введите лимит использований (0 - без лимита):\n\n"
        "Пример: 100 (можно использовать 100 раз)",
        reply_markup=kb.get_cancel_keyboard()
    )

async def create_promocode_usage_limit(message: Message, state: FSMContext):
    """Получение лимита использований"""
    if not message.text.isdigit():
        await message.answer("⚠️ Введите число")
        return
    
    data = await state.get_data()
    await state.update_data(usage_limit=int(message.text))
    await state.set_state("waiting_promocode_min_amount")
    
    await message.answer(
        "💰 Введите минимальную сумму заказа (0 - без ограничений):\n\n"
        "Пример: 1000 (промокод работает от 1000₽)",
        reply_markup=kb.get_cancel_keyboard()
    )

async def create_promocode_min_amount(message: Message, state: FSMContext):
    """Получение минимальной суммы заказа"""
    if not message.text.replace('.', '', 1).isdigit():
        await message.answer("⚠️ Введите число")
        return
    
    data = await state.get_data()
    min_amount = float(message.text)
    
    # Создаем промокод
    result = promocodes.create_promocode(
        code=data['code'],
        discount_type=data['discount_type'],
        discount_value=data['discount_value'],
        usage_limit=data['usage_limit'],
        min_order_amount=min_amount
    )
    
    await message.answer(
        f"✅ Промокод {data['code']} успешно создан!\n\n"
        f"Тип: {'Процентная' if data['discount_type'] == 'percentage' else 'Фиксированная'} скидка\n"
        f"Размер: {data['discount_value']}{'%' if data['discount_type'] == 'percentage' else '₽'}\n"
        f"Лимит: {data['usage_limit'] if data['usage_limit'] > 0 else '∞'}\n"
        f"Мин. сумма: {min_amount}₽",
        reply_markup=kb.get_main_keyboard(message.from_user.id)
    )
    await state.clear()

async def admin_export_orders(callback: CallbackQuery):
    """Экспорт заказов в Excel"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📅 За сегодня", callback_data="export_today"))
    builder.row(InlineKeyboardButton(text="📆 За неделю", callback_data="export_week"))
    builder.row(InlineKeyboardButton(text="📊 За месяц", callback_data="export_month"))
    builder.row(InlineKeyboardButton(text="🗂 За все время", callback_data="export_all"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_promocodes"))
    
    await callback.message.edit_text(
        "📊 Выберите период для экспорта заказов:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

async def export_orders_handler(callback: CallbackQuery):
    """Обработка экспорта заказов"""
    period = callback.data.replace("export_", "")
    
    await callback.message.edit_text("⏳ Экспортирую заказы, подождите...")
    
    output, message = await export_orders_to_excel(period)
    
    if output:
        filename = f"orders_{period}_{datetime.now().strftime('%Y%m%d')}.xlsx"
        await callback.message.delete()
        await callback.message.answer_document(
            BufferedInputFile(output.getvalue(), filename=filename),
            caption=f"✅ {message}"
        )
    else:
        await callback.message.edit_text(f"❌ {message}")
    
    await callback.answer()

async def handle_product_photo(message: Message, state: FSMContext):
    """Обработка фото для НОВОГО товара"""
    if not message.photo:
        await message.answer("❌ Отправьте фото")
        return
    
    data = await state.get_data()
    new_products = data.get('new_products', [])
    current_index = data.get('current_index', 0)
    product_photos = data.get('product_photos', {})
    
    if current_index >= len(new_products):
        await message.answer("❌ Все товары уже обработаны")
        return
    
    # Получаем текущий новый товар
    current_product = new_products[current_index]
    photo_id = message.photo[-1].file_id
    
    # Сохраняем фото
    product_photos[current_product['name']] = photo_id
    await state.update_data(product_photos=product_photos)
    
    # Переходим к следующему товару
    current_index += 1
    await state.update_data(current_index=current_index)
    
    if current_index < len(new_products):
        next_product = new_products[current_index]
        
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="⏭️ Пропустить фото", callback_data="skip_photo"))
        builder.row(InlineKeyboardButton(text="✅ Завершить загрузку", callback_data="finish_upload"))
        builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_mass_upload"))
        
        await message.answer(
            f"✅ Фото для <b>{current_product['name']}</b> сохранено!\n\n"
            f"📸 Теперь отправьте фото для: <b>{next_product['name']}</b>\n\n"
            f"Осталось новых товаров: {len(new_products) - current_index}",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    else:
        # Все фото для новых товаров загружены, завершаем
        await finish_upload(message, state)

async def skip_photo(callback: CallbackQuery, state: FSMContext):
    """Пропустить фото для текущего НОВОГО товара"""
    data = await state.get_data()
    new_products = data.get('new_products', [])
    current_index = data.get('current_index', 0)
    
    if current_index >= len(new_products):
        await callback.answer("Все товары уже обработаны")
        return
    
    current_product = new_products[current_index]
    
    # Переходим к следующему товару
    current_index += 1
    await state.update_data(current_index=current_index)
    
    if current_index < len(new_products):
        next_product = new_products[current_index]
        
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="⏭️ Пропустить фото", callback_data="skip_photo"))
        builder.row(InlineKeyboardButton(text="✅ Завершить загрузку", callback_data="finish_upload"))
        builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_mass_upload"))
        
        await callback.message.edit_text(
            f"⏭️ Фото для <b>{current_product['name']}</b> пропущено!\n\n"
            f"📸 Теперь отправьте фото для: <b>{next_product['name']}</b>\n\n"
            f"Осталось новых товаров: {len(new_products) - current_index}",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    else:
        await finish_upload(callback.message, state)
    
    await callback.answer()

async def finish_upload(message, state: FSMContext):
    """Завершение загрузки и сохранение НОВЫХ товаров"""
    data = await state.get_data()
    new_products = data.get('new_products', [])
    existing_products = data.get('existing_products', [])
    product_photos = data.get('product_photos', {})
    category_id = data.get('category_id')
    
    if not new_products and not existing_products:
        await message.answer("❌ Нет товаров для загрузки")
        await state.clear()
        return
    
    await message.answer("⏳ Сохраняю товары, подождите...")
    
    # Сначала обновляем существующие
    updated_count = 0
    if existing_products:
        updated_count = db.update_existing_products(existing_products)
    
    # Затем добавляем новые
    added_count = 0
    no_photo_count = 0
    
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    for product in new_products:
        try:
            photo_id = product_photos.get(product['name'])
            
            cursor.execute('''
                INSERT INTO products (name, description, price, cost_price, stock, category_id, image_id, is_preorder)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (product['name'], product['description'], product['price'], 
                  product['cost_price'], product['stock'], category_id,
                  photo_id, 0))
            
            added_count += 1
            if not photo_id:
                no_photo_count += 1
                
        except Exception as e:
            print(f"Ошибка добавления {product['name']}: {e}")
    
    conn.commit()
    conn.close()
    
    result_text = f"✅ <b>МАССОВАЯ ЗАГРУЗКА ЗАВЕРШЕНА</b>\n\n"
    
    if updated_count > 0:
        result_text += f"🔄 Обновлено товаров: {updated_count}\n"
        result_text += f"   (количество добавлено к остаткам)\n\n"
    
    if added_count > 0:
        result_text += f"🆕 Добавлено новых товаров: {added_count}\n"
        result_text += f"📸 С фото: {added_count - no_photo_count}\n"
        result_text += f"📷 Без фото: {no_photo_count}\n\n"
    
    if no_photo_count > 0:
        result_text += "💡 Вы можете добавить фото позже через управление товарами."
    
    await message.answer(result_text, parse_mode="HTML", reply_markup=kb.get_main_keyboard(message.from_user.id))
    await state.clear()

async def cancel_mass_upload(callback: CallbackQuery, state: FSMContext):
    """Отмена массовой загрузки"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Массовая загрузка отменена",
        reply_markup=kb.get_admin_keyboard()
    )
    await callback.answer()
async def admin_manage_products(callback: CallbackQuery):
    """Меню управления товарами"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    # Получаем список всех товаров
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.*, c.name as category_name 
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.is_active = 1
        ORDER BY p.id DESC
        LIMIT 20
    ''')
    products = cursor.fetchall()
    conn.close()
    
    if not products:
        await callback.message.edit_text(
            "📦 Нет товаров для управления.\n\n"
            "Добавьте товары через меню '➕ Товар' или '📊 Массовая загрузка'",
            reply_markup=kb.get_admin_keyboard()
        )
        await callback.answer()
        return
    
    text = "<b>📦 УПРАВЛЕНИЕ ТОВАРАМИ</b>\n\n"
    text += "Выберите товар для редактирования:\n\n"
    
    builder = InlineKeyboardBuilder()
    
    for product in products:
        # Показываем название и цену
        text += f"🔹 <b>{product['name']}</b>\n"
        text += f"   💰 {product['price']} руб. | 📦 {product['stock']} шт.\n"
        text += f"   📁 {product['category_name']}\n\n"
        
        builder.add(InlineKeyboardButton(
            text=f"✏️ {product['name'][:30]}",
            callback_data=f"edit_product_{product['id']}"
        ))
    
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

async def edit_product_menu(callback: CallbackQuery, state: FSMContext):
    """Меню редактирования товара"""
    # Получаем ID товара из callback.data
    parts = callback.data.split("_")
    
    # Ищем число в частях
    product_id = None
    for part in parts:
        if part.isdigit():
            product_id = int(part)
            break
    
    if not product_id:
        await callback.answer("❌ Ошибка: неверный формат", show_alert=True)
        return
    
    product = db.get_product(product_id)
    
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return
    
    await state.update_data(product_id=product_id, product_name=product['name'])
    
    # Получаем категорию
    category = db.get_category(product['category_id'])
    category_name = category['name'] if category else "Не указана"
    
    text = f"<b>✏️ РЕДАКТИРОВАНИЕ ТОВАРА</b>\n\n"
    text += f"📦 <b>{product['name']}</b>\n\n"
    text += f"📝 Описание: {product['description'][:50]}...\n"
    text += f"💰 Цена: {product['price']} руб.\n"
    text += f"📊 Себестоимость: {product['cost_price']} руб.\n"
    text += f"📦 Остаток: {product['stock']} шт.\n"
    text += f"📁 Категория: {category_name}\n"
    text += f"📸 Фото: {'Есть' if product['image_id'] else 'Нет'}\n"
    text += f"🔄 Статус: {'Активен' if product['is_active'] else 'Скрыт'}\n\n"
    text += "Выберите поле для редактирования:"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📝 Название", callback_data=f"edit_field_name_{product_id}"))
    builder.row(InlineKeyboardButton(text="📄 Описание", callback_data=f"edit_field_description_{product_id}"))
    builder.row(InlineKeyboardButton(text="💰 Цена", callback_data=f"edit_field_price_{product_id}"))
    builder.row(InlineKeyboardButton(text="📊 Себестоимость", callback_data=f"edit_field_cost_{product_id}"))
    builder.row(InlineKeyboardButton(text="📦 Количество", callback_data=f"edit_field_stock_{product_id}"))
    builder.row(InlineKeyboardButton(text="📁 Категория", callback_data=f"edit_field_category_{product_id}"))
    builder.row(InlineKeyboardButton(text="📸 Фото", callback_data=f"edit_field_image_{product_id}"))
    builder.row(InlineKeyboardButton(text="🔄 Активность", callback_data=f"edit_field_active_{product_id}"))
    builder.row(InlineKeyboardButton(text="🗑 Удалить товар", callback_data=f"delete_product_{product_id}"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="admin_manage_products"))
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await state.set_state(EditProductStates.select_field)
    await callback.answer()

async def edit_product_field(callback: CallbackQuery, state: FSMContext):
    """Выбор поля для редактирования"""
    parts = callback.data.split("_")
    
    # field - это второй элемент (например: name, description и т.д.)
    # product_id - это третий элемент
    if len(parts) >= 3:
        field = parts[2]
        product_id = int(parts[3]) if parts[3].isdigit() else None
    else:
        await callback.answer("❌ Ошибка формата", show_alert=True)
        return
    
    if not product_id:
        await callback.answer("❌ Ошибка: неверный ID", show_alert=True)
        return
    
    await state.update_data(edit_field=field, product_id=product_id)
    
    field_names = {
        'name': 'название товара',
        'description': 'описание товара',
        'price': 'цену (число)',
        'cost': 'себестоимость (число)',
        'stock': 'количество (целое число)',
        'category': 'категорию (выберите из списка)',
        'image': 'фото (отправьте новое фото)',
        'active': 'активность товара'
    }
    
    if field == 'category':
        await state.set_state(EditProductStates.edit_category)
        await callback.message.edit_text(
            f"📁 Выберите новую категорию для товара:",
            reply_markup=kb.get_categories_keyboard()
        )
    elif field == 'image':
        await state.set_state(EditProductStates.edit_image)
        await callback.message.edit_text(
            f"📸 Отправьте новое фото для товара:\n\n"
            f"Или нажмите /skip чтобы оставить текущее",
            reply_markup=kb.get_cancel_keyboard()
        )
    elif field == 'active':
        product = db.get_product(product_id)
        new_status = 0 if product['is_active'] else 1
        db.update_product(product_id, is_active=new_status)
        
        status_text = "активирован" if new_status else "деактивирован"
        await callback.message.edit_text(
            f"✅ Товар {status_text}!\n\n"
            f"📦 {product['name']}\n"
            f"Статус: {'Активен' if new_status else 'Скрыт'}",
            reply_markup=kb.get_admin_keyboard()
        )
        await callback.answer()
        await state.clear()
        return
    else:
        state_map = {
            'name': EditProductStates.edit_name,
            'description': EditProductStates.edit_description,
            'price': EditProductStates.edit_price,
            'cost': EditProductStates.edit_cost_price,
            'stock': EditProductStates.edit_stock
        }
        await state.set_state(state_map[field])
        
        await callback.message.edit_text(
            f"✏️ Введите новое {field_names[field]}:\n\n"
            f"Или нажмите /cancel для отмены",
            reply_markup=kb.get_cancel_keyboard()
        )
    
    await callback.answer()

async def edit_product_name(message: Message, state: FSMContext):
    """Редактирование названия"""
    data = await state.get_data()
    product_id = data['product_id']
    new_name = message.text.strip()
    
    db.update_product(product_id, name=new_name)
    
    await message.answer(
        f"✅ Название изменено!\n\n"
        f"Новое название: {new_name}",
        reply_markup=kb.get_main_keyboard(message.from_user.id)
    )
    await state.clear()

async def edit_product_description(message: Message, state: FSMContext):
    """Редактирование описания"""
    data = await state.get_data()
    product_id = data['product_id']
    new_description = message.text.strip()
    
    db.update_product(product_id, description=new_description)
    
    await message.answer(
        f"✅ Описание изменено!",
        reply_markup=kb.get_main_keyboard(message.from_user.id)
    )
    await state.clear()

async def edit_product_price(message: Message, state: FSMContext):
    """Редактирование цены"""
    if not message.text.replace('.', '', 1).isdigit():
        await message.answer("⚠️ Введите число")
        return
    
    data = await state.get_data()
    product_id = data['product_id']
    new_price = float(message.text)
    
    db.update_product(product_id, price=new_price)
    
    await message.answer(
        f"✅ Цена изменена!\n\n"
        f"Новая цена: {new_price} руб.",
        reply_markup=kb.get_main_keyboard(message.from_user.id)
    )
    await state.clear()

async def edit_product_cost_price(message: Message, state: FSMContext):
    """Редактирование себестоимости"""
    if not message.text.replace('.', '', 1).isdigit():
        await message.answer("⚠️ Введите число")
        return
    
    data = await state.get_data()
    product_id = data['product_id']
    new_cost = float(message.text)
    
    db.update_product(product_id, cost_price=new_cost)
    
    await message.answer(
        f"✅ Себестоимость изменена!\n\n"
        f"Новая себестоимость: {new_cost} руб.",
        reply_markup=kb.get_main_keyboard(message.from_user.id)
    )
    await state.clear()

async def edit_product_stock(message: Message, state: FSMContext):
    """Редактирование количества"""
    if not message.text.isdigit():
        await message.answer("⚠️ Введите целое число")
        return
    
    data = await state.get_data()
    product_id = data['product_id']
    new_stock = int(message.text)
    
    db.update_product(product_id, stock=new_stock)
    
    # Если количество 0, деактивируем товар
    if new_stock <= 0:
        db.update_product(product_id, is_active=0)
        await message.answer(
            f"✅ Количество изменено!\n\n"
            f"Новое количество: {new_stock} шт.\n"
            f"⚠️ Товар деактивирован (закончился)",
            reply_markup=kb.get_main_keyboard(message.from_user.id)
        )
    else:
        await message.answer(
            f"✅ Количество изменено!\n\n"
            f"Новое количество: {new_stock} шт.",
            reply_markup=kb.get_main_keyboard(message.from_user.id)
        )
    await state.clear()

async def edit_product_category(callback: CallbackQuery, state: FSMContext):
    """Редактирование категории"""
    category_id = int(callback.data.split("_")[1])
    data = await state.get_data()
    product_id = data['product_id']
    
    db.update_product(product_id, category_id=category_id)
    
    category = db.get_category(category_id)
    
    await callback.message.edit_text(
        f"✅ Категория изменена!\n\n"
        f"Новая категория: {category['name']}",
        reply_markup=kb.get_admin_keyboard()
    )
    await state.clear()
    await callback.answer()

async def edit_product_image(message: Message, state: FSMContext, bot: Bot):
    """Редактирование фото"""
    if message.text and message.text == "/skip":
        await message.answer(
            "⏭️ Фото не изменено",
            reply_markup=kb.get_main_keyboard(message.from_user.id)
        )
        await state.clear()
        return
    
    if not message.photo:
        await message.answer("❌ Отправьте фото или нажмите /skip")
        return
    
    data = await state.get_data()
    product_id = data['product_id']
    photo_id = message.photo[-1].file_id
    
    db.update_product(product_id, image_id=photo_id)
    
    await message.answer(
        f"✅ Фото обновлено!",
        reply_markup=kb.get_main_keyboard(message.from_user.id)
    )
    await state.clear()
async def admin_manage_products(callback: CallbackQuery):
    """Меню управления товарами"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    # Получаем список всех товаров
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.*, c.name as category_name 
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.is_active = 1
        ORDER BY p.id DESC
        LIMIT 20
    ''')
    products = cursor.fetchall()
    conn.close()
    
    if not products:
        await callback.message.edit_text(
            "📦 Нет товаров для управления.\n\n"
            "Добавьте товары через меню '➕ Товар' или '📊 Массовая загрузка'",
            reply_markup=kb.get_admin_keyboard()
        )
        await callback.answer()
        return
    
    text = "<b>📦 УПРАВЛЕНИЕ ТОВАРАМИ</b>\n\n"
    text += "Выберите товар для редактирования:\n\n"
    
    builder = InlineKeyboardBuilder()
    
    for product in products:
        # Показываем название и цену
        text += f"🔹 <b>{product['name']}</b>\n"
        text += f"   💰 {product['price']} руб. | 📦 {product['stock']} шт.\n"
        text += f"   📁 {product['category_name']}\n\n"
        
        builder.add(InlineKeyboardButton(
            text=f"✏️ {product['name'][:30]}",
            callback_data=f"edit_product_{product['id']}"
        ))
    
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

async def edit_product_menu(callback: CallbackQuery, state: FSMContext):
    """Меню редактирования товара"""
    product_id = int(callback.data.split("_")[2])
    product = db.get_product(product_id)
    
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return
    
    await state.update_data(product_id=product_id, product_name=product['name'])
    
    # Получаем категорию
    category = db.get_category(product['category_id'])
    category_name = category['name'] if category else "Не указана"
    
    text = f"<b>✏️ РЕДАКТИРОВАНИЕ ТОВАРА</b>\n\n"
    text += f"📦 <b>{product['name']}</b>\n\n"
    text += f"📝 Описание: {product['description'][:50]}...\n"
    text += f"💰 Цена: {product['price']} руб.\n"
    text += f"📊 Себестоимость: {product['cost_price']} руб.\n"
    text += f"📦 Остаток: {product['stock']} шт.\n"
    text += f"📁 Категория: {category_name}\n"
    text += f"📸 Фото: {'Есть' if product['image_id'] else 'Нет'}\n"
    text += f"🔄 Статус: {'Активен' if product['is_active'] else 'Скрыт'}\n\n"
    text += "Выберите поле для редактирования:"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📝 Название", callback_data=f"edit_field_name_{product_id}"))
    builder.row(InlineKeyboardButton(text="📄 Описание", callback_data=f"edit_field_description_{product_id}"))
    builder.row(InlineKeyboardButton(text="💰 Цена", callback_data=f"edit_field_price_{product_id}"))
    builder.row(InlineKeyboardButton(text="📊 Себестоимость", callback_data=f"edit_field_cost_{product_id}"))
    builder.row(InlineKeyboardButton(text="📦 Количество", callback_data=f"edit_field_stock_{product_id}"))
    builder.row(InlineKeyboardButton(text="📁 Категория", callback_data=f"edit_field_category_{product_id}"))
    builder.row(InlineKeyboardButton(text="📸 Фото", callback_data=f"edit_field_image_{product_id}"))
    builder.row(InlineKeyboardButton(text="🔄 Активность", callback_data=f"edit_field_active_{product_id}"))
    builder.row(InlineKeyboardButton(text="🗑 Удалить товар", callback_data=f"delete_product_{product_id}"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="admin_manage_products"))
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await state.set_state(EditProductStates.select_field)
    await callback.answer()

async def edit_product_field(callback: CallbackQuery, state: FSMContext):
    """Выбор поля для редактирования"""
    field = callback.data.split("_")[2]
    product_id = int(callback.data.split("_")[3])
    
    await state.update_data(edit_field=field, product_id=product_id)
    
    field_names = {
        'name': 'название товара',
        'description': 'описание товара',
        'price': 'цену (число)',
        'cost': 'себестоимость (число)',
        'stock': 'количество (целое число)',
        'category': 'категорию (выберите из списка)',
        'image': 'фото (отправьте новое фото)',
        'active': 'активность товара'
    }
    
    if field == 'category':
        await state.set_state(EditProductStates.edit_category)
        await callback.message.edit_text(
            f"📁 Выберите новую категорию для товара:",
            reply_markup=kb.get_categories_keyboard()
        )
    elif field == 'image':
        await state.set_state(EditProductStates.edit_image)
        await callback.message.edit_text(
            f"📸 Отправьте новое фото для товара:\n\n"
            f"Или нажмите /skip чтобы оставить текущее",
            reply_markup=kb.get_cancel_keyboard()
        )
    elif field == 'active':
        product = db.get_product(product_id)
        new_status = 0 if product['is_active'] else 1
        db.update_product(product_id, is_active=new_status)
        
        status_text = "активирован" if new_status else "деактивирован"
        await callback.message.edit_text(
            f"✅ Товар {status_text}!\n\n"
            f"📦 {product['name']}\n"
            f"Статус: {'Активен' if new_status else 'Скрыт'}",
            reply_markup=kb.get_admin_keyboard()
        )
        await callback.answer()
        await state.clear()
        return
    else:
        state_map = {
            'name': EditProductStates.edit_name,
            'description': EditProductStates.edit_description,
            'price': EditProductStates.edit_price,
            'cost': EditProductStates.edit_cost_price,
            'stock': EditProductStates.edit_stock
        }
        await state.set_state(state_map[field])
        
        await callback.message.edit_text(
            f"✏️ Введите новое {field_names[field]}:\n\n"
            f"Или нажмите /cancel для отмены",
            reply_markup=kb.get_cancel_keyboard()
        )
    
    await callback.answer()

async def edit_product_name(message: Message, state: FSMContext):
    """Редактирование названия"""
    data = await state.get_data()
    product_id = data['product_id']
    new_name = message.text.strip()
    
    db.update_product(product_id, name=new_name)
    
    await message.answer(
        f"✅ Название изменено!\n\n"
        f"Новое название: {new_name}",
        reply_markup=kb.get_main_keyboard(message.from_user.id)
    )
    await state.clear()

async def edit_product_description(message: Message, state: FSMContext):
    """Редактирование описания"""
    data = await state.get_data()
    product_id = data['product_id']
    new_description = message.text.strip()
    
    db.update_product(product_id, description=new_description)
    
    await message.answer(
        f"✅ Описание изменено!",
        reply_markup=kb.get_main_keyboard(message.from_user.id)
    )
    await state.clear()

async def edit_product_price(message: Message, state: FSMContext):
    """Редактирование цены"""
    if not message.text.replace('.', '', 1).isdigit():
        await message.answer("⚠️ Введите число")
        return
    
    data = await state.get_data()
    product_id = data['product_id']
    new_price = float(message.text)
    
    db.update_product(product_id, price=new_price)
    
    await message.answer(
        f"✅ Цена изменена!\n\n"
        f"Новая цена: {new_price} руб.",
        reply_markup=kb.get_main_keyboard(message.from_user.id)
    )
    await state.clear()

async def edit_product_cost_price(message: Message, state: FSMContext):
    """Редактирование себестоимости"""
    if not message.text.replace('.', '', 1).isdigit():
        await message.answer("⚠️ Введите число")
        return
    
    data = await state.get_data()
    product_id = data['product_id']
    new_cost = float(message.text)
    
    db.update_product(product_id, cost_price=new_cost)
    
    await message.answer(
        f"✅ Себестоимость изменена!\n\n"
        f"Новая себестоимость: {new_cost} руб.",
        reply_markup=kb.get_main_keyboard(message.from_user.id)
    )
    await state.clear()

async def edit_product_stock(message: Message, state: FSMContext):
    """Редактирование количества"""
    if not message.text.isdigit():
        await message.answer("⚠️ Введите целое число")
        return
    
    data = await state.get_data()
    product_id = data['product_id']
    new_stock = int(message.text)
    
    db.update_product(product_id, stock=new_stock)
    
    # Если количество 0, деактивируем товар
    if new_stock <= 0:
        db.update_product(product_id, is_active=0)
        await message.answer(
            f"✅ Количество изменено!\n\n"
            f"Новое количество: {new_stock} шт.\n"
            f"⚠️ Товар деактивирован (закончился)",
            reply_markup=kb.get_main_keyboard(message.from_user.id)
        )
    else:
        await message.answer(
            f"✅ Количество изменено!\n\n"
            f"Новое количество: {new_stock} шт.",
            reply_markup=kb.get_main_keyboard(message.from_user.id)
        )
    await state.clear()

async def edit_product_category(callback: CallbackQuery, state: FSMContext):
    """Редактирование категории"""
    category_id = int(callback.data.split("_")[1])
    data = await state.get_data()
    product_id = data['product_id']
    
    db.update_product(product_id, category_id=category_id)
    
    category = db.get_category(category_id)
    
    await callback.message.edit_text(
        f"✅ Категория изменена!\n\n"
        f"Новая категория: {category['name']}",
        reply_markup=kb.get_admin_keyboard()
    )
    await state.clear()
    await callback.answer()

async def edit_product_image(message: Message, state: FSMContext, bot: Bot):
    """Редактирование фото"""
    if message.text and message.text == "/skip":
        await message.answer(
            "⏭️ Фото не изменено",
            reply_markup=kb.get_main_keyboard(message.from_user.id)
        )
        await state.clear()
        return
    
    if not message.photo:
        await message.answer("❌ Отправьте фото или нажмите /skip")
        return
    
    data = await state.get_data()
    product_id = data['product_id']
    photo_id = message.photo[-1].file_id
    
    db.update_product(product_id, image_id=photo_id)
    
    await message.answer(
        f"✅ Фото обновлено!",
        reply_markup=kb.get_main_keyboard(message.from_user.id)
    )
    await state.clear()
async def edit_product_skip_image(message: Message, state: FSMContext):
    """Пропуск изменения фото"""
    await message.answer(
        "⏭️ Фото не изменено",
        reply_markup=kb.get_main_keyboard(message.from_user.id)
    )
    await state.clear()

async def finish_upload_without_photos(callback: CallbackQuery, state: FSMContext):
    """Завершение загрузки без фото (только обновление)"""
    data = await state.get_data()
    existing_products = data.get('existing_products', [])
    new_products = data.get('new_products', [])
    
    if existing_products:
        await callback.message.edit_text("⏳ Обновляю существующие товары...")
        updated = db.update_existing_products(existing_products)
        
        result_text = f"✅ <b>ОБНОВЛЕНИЕ ТОВАРОВ</b>\n\n"
        result_text += f"🔄 Обновлено товаров: {updated}\n"
        result_text += f"➕ Количество добавлено к остаткам\n\n"
        
        if new_products:
            result_text += f"🆕 Новых товаров: {len(new_products)}\n"
            result_text += "⚠️ Фото для новых товаров не добавлены\n"
            result_text += "💡 Вы можете добавить фото позже через управление товарами"
        
        await callback.message.edit_text(result_text, parse_mode="HTML", reply_markup=kb.get_admin_keyboard())
    else:
        await callback.message.edit_text(
            "❌ Нет товаров для обработки",
            reply_markup=kb.get_admin_keyboard()
        )
    
    await state.clear()
    await callback.answer()

async def admin_delete_order(callback: CallbackQuery):
    """Удаление заказа (админ)"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    # Получаем ID заказа
    order_id = int(callback.data.split("_")[2])
    
    # Проверяем существование заказа
    order = db.get_order(order_id)
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    
    # Удаляем заказ
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM orders WHERE id = ?', (order_id,))
    conn.commit()
    conn.close()
    
    await callback.answer(f"✅ Заказ #{order_id} удален", show_alert=True)
    
    # Обновляем список заказов
    await admin_orders_manage_callback(callback)

async def admin_backup_db(callback: CallbackQuery):
    """Выгрузка базы данных"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    await callback.message.edit_text("⏳ Создаю резервную копию базы данных...")
    
    import os
    import shutil
    from datetime import datetime
    
    # Создаем временную копию БД
    backup_filename = f"vape_shop_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    temp_backup = os.path.join(os.path.dirname(__file__), backup_filename)
    
    try:
        # Копируем файл базы данных
        shutil.copy2(config.DB_NAME, temp_backup)
        
        # Отправляем файл
        with open(temp_backup, 'rb') as f:
            await callback.message.answer_document(
                BufferedInputFile(f.read(), filename=backup_filename),
                caption=f"📦 <b>Резервная копия базы данных</b>\n\n"
                        f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
                        f"📁 Файл: {backup_filename}\n"
                        f"💾 Размер: {os.path.getsize(temp_backup) / 1024:.2f} KB\n\n"
                        f"<i>Храните копии в надежном месте!</i>",
                parse_mode="HTML"
            )
        
        # Удаляем временный файл
        os.remove(temp_backup)
        
        # Возвращаемся в админ-панель
        await callback.message.answer(
            "🔧 Панель управления:",
            reply_markup=kb.get_admin_keyboard()
        )
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка при создании резервной копии: {str(e)}")
    
    await callback.answer()

async def admin_export_excel(callback: CallbackQuery):
    """Выгрузка всех данных в Excel"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    await callback.message.edit_text("⏳ Экспортирую данные в Excel...")
    
    import pandas as pd
    from datetime import datetime
    import io
    
    try:
        conn = db.get_db_connection()
        
        # Создаем Excel файл в памяти
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # 1. Таблица пользователей
            try:
                df_users = pd.read_sql_query("SELECT * FROM users", conn)
                if not df_users.empty:
                    df_users.to_excel(writer, sheet_name='Пользователи', index=False)
                    # Форматирование
                    worksheet = writer.sheets['Пользователи']
                    worksheet.column_dimensions['A'].width = 15
                    worksheet.column_dimensions['B'].width = 20
                    worksheet.column_dimensions['C'].width = 25
                    worksheet.column_dimensions['D'].width = 15
                    worksheet.column_dimensions['E'].width = 15
            except Exception as e:
                print(f"Ошибка экспорта пользователей: {e}")
            
            # 2. Таблица товаров
            try:
                df_products = pd.read_sql_query("SELECT * FROM products", conn)
                if not df_products.empty:
                    df_products.to_excel(writer, sheet_name='Товары', index=False)
                    worksheet = writer.sheets['Товары']
                    worksheet.column_dimensions['A'].width = 10
                    worksheet.column_dimensions['B'].width = 30
                    worksheet.column_dimensions['C'].width = 40
                    worksheet.column_dimensions['D'].width = 12
                    worksheet.column_dimensions['E'].width = 12
                    worksheet.column_dimensions['F'].width = 12
            except Exception as e:
                print(f"Ошибка экспорта товаров: {e}")
            
            # 3. Таблица заказов
            try:
                df_orders = pd.read_sql_query("SELECT * FROM orders", conn)
                if not df_orders.empty:
                    df_orders.to_excel(writer, sheet_name='Заказы', index=False)
                    worksheet = writer.sheets['Заказы']
                    worksheet.column_dimensions['A'].width = 10
                    worksheet.column_dimensions['B'].width = 12
                    worksheet.column_dimensions['C'].width = 40
                    worksheet.column_dimensions['D'].width = 12
                    worksheet.column_dimensions['E'].width = 12
            except Exception as e:
                print(f"Ошибка экспорта заказов: {e}")
            
            # 4. Таблица категорий
            try:
                df_categories = pd.read_sql_query("SELECT * FROM categories", conn)
                if not df_categories.empty:
                    df_categories.to_excel(writer, sheet_name='Категории', index=False)
            except Exception as e:
                print(f"Ошибка экспорта категорий: {e}")
            
            # 5. Статистика
            try:
                # Получаем общую статистику
                total_users = pd.read_sql_query("SELECT COUNT(*) as count FROM users", conn).iloc[0,0]
                total_orders = pd.read_sql_query("SELECT COUNT(*) as count FROM orders", conn).iloc[0,0]
                total_revenue = pd.read_sql_query("SELECT SUM(total_amount) as sum FROM orders", conn).iloc[0,0] or 0
                total_profit = pd.read_sql_query("SELECT SUM(total_amount - total_cost) as sum FROM orders", conn).iloc[0,0] or 0
                
                stats_data = {
                    'Показатель': ['Всего пользователей', 'Всего заказов', 'Общая выручка', 'Общая прибыль'],
                    'Значение': [total_users, total_orders, total_revenue, total_profit]
                }
                df_stats = pd.DataFrame(stats_data)
                df_stats.to_excel(writer, sheet_name='Статистика', index=False)
            except Exception as e:
                print(f"Ошибка экспорта статистики: {e}")
            
            # 6. Топ товаров
            try:
                df_top = pd.read_sql_query('''
                    SELECT p.name, COUNT(*) as sales, SUM(json_extract(items.value, '$.quantity')) as quantity
                    FROM orders o
                    CROSS JOIN json_each(o.items) AS items
                    JOIN products p ON json_extract(items.value, '$.name') = p.name
                    GROUP BY p.id
                    ORDER BY sales DESC
                    LIMIT 20
                ''', conn)
                if not df_top.empty:
                    df_top.to_excel(writer, sheet_name='Топ товаров', index=False)
            except Exception as e:
                print(f"Ошибка экспорта топ товаров: {e}")
        
        conn.close()
        output.seek(0)
        
        # Формируем имя файла
        filename = f"vape_shop_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        # Отправляем файл
        await callback.message.answer_document(
            BufferedInputFile(output.getvalue(), filename=filename),
            caption=f"📊 <b>Экспорт базы данных в Excel</b>\n\n"
                    f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
                    f"📁 Файл: {filename}\n\n"
                    f"<b>Содержимое:</b>\n"
                    f"• Пользователи\n"
                    f"• Товары\n"
                    f"• Заказы\n"
                    f"• Категории\n"
                    f"• Статистика\n"
                    f"• Топ товаров\n\n"
                    f"<i>Файл можно открыть в Excel или Google Sheets</i>",
            parse_mode="HTML"
        )
        
        # Возвращаемся в админ-панель
        await callback.message.answer(
            "🔧 Панель управления:",
            reply_markup=kb.get_admin_keyboard()
        )
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка экспорта: {str(e)}")
    
    await callback.answer()

async def admin_design_menu(callback: CallbackQuery):
    """Меню дизайна бота"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    shop_name = db.get_design_setting('shop_name')
    welcome_text = db.get_design_setting('welcome_text')
    primary_color = db.get_design_setting('primary_color')
    
    text = f"🎨 <b>ДИЗАЙН БОТА</b>\n\n"
    text += f"🏪 Название магазина: <b>{shop_name}</b>\n"
    text += f"📝 Приветствие: <i>{welcome_text[:50]}...</i>\n"
    text += f"🎨 Основной цвет: <code>{primary_color}</code>\n\n"
    text += "Выберите что настроить:"
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=kb.get_design_keyboard()
    )
    await callback.answer()

async def banner_list(callback: CallbackQuery):
    """Список баннеров"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    banners = db.get_all_banners()
    
    if not banners:
        await callback.message.answer("📋 Нет баннеров")
        await callback.answer()
        return
    
    text = "📋 <b>СПИСОК БАННЕРОВ</b>\n\n"
    builder = InlineKeyboardBuilder()
    
    for banner in banners:
        status = "✅" if banner.get('is_active', 0) else "❌"
        text += f"{status} <b>{banner['name']}</b>\n"
        text += f"   📅 {banner['created_at'][:16]}\n\n"
        
        if not banner.get('is_active', 0):
            builder.row(InlineKeyboardButton(
                text=f"🟢 Активировать {banner['name']}",
                callback_data=f"banner_activate_{banner['id']}"
            ))
        
        builder.row(InlineKeyboardButton(
            text=f"🗑 Удалить {banner['name']}",
            callback_data=f"banner_delete_{banner['id']}"
        ))
    
    builder.row(InlineKeyboardButton(text="➕ Добавить баннер", callback_data="banner_add"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="design_banners"))
    
    # Используем edit_text, а не answer
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

async def color_setting(callback: CallbackQuery, state: FSMContext):
    """Выбор цвета для изменения"""
    color_type = callback.data.replace("color_", "")
    await state.update_data(color_type=color_type)
    await state.set_state(DesignStates.edit_color)
    
    color_names = {
        'primary': 'основной',
        'secondary': 'вторичный',
        'accent': 'акцентный',
        'text': 'текста'
    }
    
    await callback.message.answer(
        f"🎨 Введите HEX код для <b>{color_names[color_type]}</b> цвета:\n\n"
        f"Пример: <code>#2ecc71</code> (зеленый)\n"
        f"<code>#3498db</code> (синий)\n"
        f"<code>#e74c3c</code> (красный)\n\n"
        f"Или отправьте название цвета на русском (красный, синий, зеленый и т.д.)",
        parse_mode="HTML",
        reply_markup=kb.get_cancel_keyboard()
    )
    await callback.answer()

async def save_color_setting(message: Message, state: FSMContext):
    """Сохранение цвета"""
    data = await state.get_data()
    color_type = data.get('color_type')
    
    # Конвертируем название цвета в HEX
    color_map = {
        'красный': '#e74c3c',
        'синий': '#3498db',
        'зеленый': '#2ecc71',
        'желтый': '#f1c40f',
        'оранжевый': '#f39c12',
        'фиолетовый': '#9b59b6',
        'розовый': '#e84393',
        'черный': '#000000',
        'белый': '#ffffff',
        'серый': '#95a5a6'
    }
    
    color = message.text.strip().lower()
    hex_color = color_map.get(color, color)
    
    # Проверяем формат HEX
    if not hex_color.startswith('#') or len(hex_color) != 7:
        await message.answer("❌ Неверный формат. Используйте HEX код (#RRGGBB) или название цвета")
        return
    
    setting_key = f"{color_type}_color"
    db.update_design_setting(setting_key, hex_color)
    
    await message.answer(
        f"✅ Цвет обновлен!\n\n"
        f"Новый цвет: <code>{hex_color}</code>\n"
        f"🎨 Теперь бот выглядит по-новому!",
        parse_mode="HTML",
        reply_markup=kb.get_admin_keyboard()
    )
    await state.clear()

async def design_welcome_menu(callback: CallbackQuery, state: FSMContext):
    """Редактирование приветственного текста"""
    await state.set_state(DesignStates.edit_text)
    current_text = db.get_design_setting('welcome_text')
    
    await callback.message.answer(
        f"📝 <b>РЕДАКТИРОВАНИЕ ПРИВЕТСТВИЯ</b>\n\n"
        f"Текущий текст:\n<i>{current_text}</i>\n\n"
        f"Введите новый текст приветствия:\n\n"
        f"<i>Можно использовать эмодзи и HTML теги</i>",
        parse_mode="HTML",
        reply_markup=kb.get_cancel_keyboard()
    )
    await callback.answer()

async def save_welcome_text(message: Message, state: FSMContext):
    """Сохранение приветственного текста"""
    new_text = message.text
    db.update_design_setting('welcome_text', new_text)
    
    await message.answer(
        f"✅ Приветственный текст обновлен!\n\n"
        f"Новый текст:\n<i>{new_text}</i>",
        parse_mode="HTML",
        reply_markup=kb.get_admin_keyboard()
    )
    await state.clear()

async def design_banners_menu(callback: CallbackQuery):
    """Меню баннеров"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    text = "🖼️ <b>УПРАВЛЕНИЕ БАННЕРОМ</b>\n\n"
    
    banner = db.get_active_banner()
    if banner:
        text += f"Активный баннер: <b>{banner['name']}</b>\n"
        text += f"Добавлен: {banner['created_at'][:16]}\n\n"
    else:
        text += "❌ Нет активного баннера\n\n"
    
    text += "Баннер будет показываться во всех сообщениях, кроме:\n"
    text += "• Каталог после выбора категории\n"
    text += "• Карточка товара"
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_banner_keyboard())
    await callback.answer()

async def banner_add_start(callback: CallbackQuery, state: FSMContext):
    """Добавление баннера"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    await state.set_state(DesignStates.add_banner)
    await callback.message.answer(
        "🖼️ <b>ДОБАВЛЕНИЕ БАННЕРА</b>\n\n"
        "1. Отправьте фото\n"
        "2. После отправки введите название",
        parse_mode="HTML"
    )
    await callback.answer()

async def banner_add_photo(message: Message, state: FSMContext):
    """Сохранение фото"""
    if not message.photo:
        await message.answer("❌ Отправьте фото")
        return
    
    await state.update_data(banner_photo=message.photo[-1].file_id)
    await message.answer("📝 Введите название баннера:")

async def banner_add_name(message: Message, state: FSMContext):
    """Сохранение баннера"""
    data = await state.get_data()
    photo_id = data.get('banner_photo')
    name = message.text.strip()
    
    if not photo_id:
        await message.answer("❌ Ошибка: фото не найдено")
        await state.clear()
        return
    
    if not name:
        await message.answer("❌ Введите название")
        return
    
    # Деактивируем старые баннеры и добавляем новый
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE banners SET is_active = 0')
    cursor.execute('''
        INSERT INTO banners (name, image_id, is_active, created_at)
        VALUES (?, ?, 1, ?)
    ''', (name, photo_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    
    await message.answer(f"✅ Баннер <b>{name}</b> добавлен и активирован!", parse_mode="HTML")
    await state.clear()

async def banner_activate(callback: CallbackQuery):
    """Активировать баннер"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    banner_id = int(callback.data.split("_")[2])
    db.set_active_banner(banner_id)
    
    await callback.answer("✅ Баннер активирован")
    await banner_list(callback)

async def banner_delete(callback: CallbackQuery):
    """Удалить баннер"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    banner_id = int(callback.data.split("_")[2])
    db.delete_banner(banner_id)
    
    await callback.answer("✅ Баннер удален")
    await banner_list(callback)

async def send_with_banner(bot: Bot, chat_id, text, **kwargs):
    """Отправляет сообщение с баннером"""
    banner = db.get_active_banner()
    
    if banner and db.get_design_setting('show_banner') == '1':
        await bot.send_photo(
            chat_id=chat_id,
            photo=banner['image_id'],
            caption=text,
            **kwargs
        )
    else:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            **kwargs
        )

async def cancel_handler(message: Message, state: FSMContext):
    """Отмена текущего действия"""
    current_state = await state.get_state()
    
    if current_state is None:
        # Если нет активного состояния, просто игнорируем
        return
    
    await state.clear()
    
    # Отправляем сообщение об отмене
    sent = await message.answer(
        "❌ Действие отменено", 
        reply_markup=kb.get_main_keyboard(message.from_user.id)
    )
    await db.save_message(message.from_user.id, sent.message_id)

async def safe_edit_message(message, text, reply_markup=None, parse_mode="HTML"):
    """Безопасное редактирование сообщения"""
    try:
        if reply_markup:
            await message.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        else:
            await message.edit_text(text, parse_mode=parse_mode)
        return True
    except Exception as e:
        if "message is not modified" in str(e):
            return False
        else:
            raise e
        
async def design_colors_menu(callback: CallbackQuery):
    """Меню выбора цветов"""
    text = "🎨 <b>НАСТРОЙКА ЦВЕТОВ</b>\n\n"
    text += "Выберите цвет для изменения:\n\n"
    text += f"🟢 Основной цвет: <code>{db.get_design_setting('primary_color')}</code>\n"
    text += f"🔵 Вторичный цвет: <code>{db.get_design_setting('secondary_color')}</code>\n"
    text += f"🟠 Акцентный цвет: <code>{db.get_design_setting('accent_color')}</code>\n"
    text += f"⚪ Цвет текста: <code>{db.get_design_setting('text_color')}</code>\n\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🟢 Основной", callback_data="color_primary"))
    builder.row(InlineKeyboardButton(text="🔵 Вторичный", callback_data="color_secondary"))
    builder.row(InlineKeyboardButton(text="🟠 Акцентный", callback_data="color_accent"))
    builder.row(InlineKeyboardButton(text="⚪ Цвет текста", callback_data="color_text"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_design"))
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

async def send_with_banner(bot, chat_id, text, section='welcome', **kwargs):
    """Отправляет сообщение с баннером для конкретного раздела"""
    show_global = db.get_design_setting('show_banner_global') == '1'
    
    if show_global:
        banner = db.get_banner_for_section(section)
        if banner:
            return await bot.send_photo(
                chat_id=chat_id,
                photo=banner['image_id'],
                caption=text,
                **kwargs
            )
    
    return await bot.send_message(
        chat_id=chat_id,
        text=text,
        **kwargs
    )

async def banner_edit(callback: CallbackQuery):
    """Редактирование баннера - выбор разделов для показа"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    banner_id = int(callback.data.split("_")[2])
    
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM banners WHERE id = ?', (banner_id,))
    banner = cursor.fetchone()
    conn.close()
    
    if not banner:
        await callback.answer("Баннер не найден", show_alert=True)
        return
    
    banner_dict = dict(banner)
    
    text = f"🖼️ <b>НАСТРОЙКИ БАННЕРА</b>\n\n"
    text += f"Название: <b>{banner_dict['name']}</b>\n\n"
    text += "<b>Показывать в разделах:</b>\n\n"
    
    # Список разделов с их настройками
    sections = [
        ('welcome', '🏠 Приветствие', banner_dict.get('show_on_welcome', 0)),
        ('catalog', '📁 Каталог', banner_dict.get('show_on_catalog', 0)),
        ('cart', '🛒 Корзина', banner_dict.get('show_on_cart', 0)),
        ('orders', '📦 Заказы', banner_dict.get('show_on_orders', 0)),
        ('profile', '👤 Профиль', banner_dict.get('show_on_profile', 0)),
        ('contest', '🎁 Конкурс', banner_dict.get('show_on_contest', 0)),
        ('support', '🆘 Поддержка', banner_dict.get('show_on_support', 0))
    ]
    
    builder = InlineKeyboardBuilder()
    
    for section_key, section_name, is_active in sections:
        status = "✅" if is_active else "❌"
        text += f"{status} {section_name}\n"
        builder.row(InlineKeyboardButton(
            text=f"{'🔴 Выключить' if is_active else '🟢 Включить'} в {section_name}",
            callback_data=f"banner_toggle_section_{banner_id}_{section_key}"
        ))
    
    text += f"\n<b>Статус:</b> {'🟢 Активен' if banner_dict.get('is_active', 0) else '🔴 Неактивен'}"
    
    builder.row(InlineKeyboardButton(
        text=f"{'🔴 Деактивировать' if banner_dict.get('is_active', 0) else '🟢 Активировать'} баннер",
        callback_data=f"banner_toggle_active_{banner_id}"
    ))
    builder.row(InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="banner_list"))
    
    try:
        if isinstance(callback.message, str):
            # Если это не реальный callback, а наш фейковый
            await callback.message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
        else:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception as e:
        if "message is not modified" in str(e):
            await callback.answer()
        else:
            raise e
    
    if not isinstance(callback.message, str):
        await callback.answer() 

async def banner_toggle_section(callback: CallbackQuery):
    """Переключение показа баннера в разделе"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    parts = callback.data.split("_")
    banner_id = int(parts[2])
    section = parts[3]
    
    # Сопоставление раздела с колонкой
    section_map = {
        'welcome': 'show_on_welcome',
        'catalog': 'show_on_catalog',
        'cart': 'show_on_cart',
        'orders': 'show_on_orders',
        'profile': 'show_on_profile',
        'contest': 'show_on_contest',
        'support': 'show_on_support'
    }
    
    column = section_map.get(section)
    if not column:
        await callback.answer("Ошибка", show_alert=True)
        return
    
    # Получаем текущее значение
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f'SELECT {column} FROM banners WHERE id = ?', (banner_id,))
    result = cursor.fetchone()
    
    if result:
        current = result[0] or 0
        new_value = 0 if current == 1 else 1
        cursor.execute(f'UPDATE banners SET {column} = ? WHERE id = ?', (new_value, banner_id))
        conn.commit()
    
    conn.close()
    
    await callback.answer("✅ Настройка сохранена")
    
    # Обновляем меню настроек
    await banner_settings(callback)

async def banner_toggle_active(callback: CallbackQuery):
    """Переключение активности баннера"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    banner_id = int(callback.data.split("_")[2])
    
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT is_active FROM banners WHERE id = ?', (banner_id,))
    result = cursor.fetchone()
    
    if result:
        current = result[0] or 0
        new_value = 0 if current == 1 else 1
        cursor.execute('UPDATE banners SET is_active = ? WHERE id = ?', (new_value, banner_id))
        conn.commit()
    
    conn.close()
    
    await callback.answer(f"✅ Баннер {'активирован' if new_value == 1 else 'деактивирован'}")
    
    # Обновляем меню настроек
    await banner_settings(callback)

async def banner_delete(callback: CallbackQuery):
    """Удаление баннера"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    banner_id = int(callback.data.split("_")[2])
    
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM banners WHERE id = ?', (banner_id,))
    conn.commit()
    conn.close()
    
    await callback.answer("✅ Баннер удален")
    
    # Обновляем список баннеров
    await banner_list(callback)

async def banner_global_settings(callback: CallbackQuery):
    """Глобальные настройки баннеров"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    show_global = db.get_design_setting('show_banner_global')
    if show_global is None:
        show_global = '1'
    
    text = "🌍 <b>ГЛОБАЛЬНЫЕ НАСТРОЙКИ БАННЕРОВ</b>\n\n"
    text += f"Показывать баннеры: {'✅ Включено' if show_global == '1' else '❌ Выключено'}\n\n"
    text += "Если отключить, баннеры не будут показываться нигде."
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="🔴 Выключить все" if show_global == '1' else "🟢 Включить все",
        callback_data="banner_global_toggle"
    ))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="design_banners"))
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

async def banner_global_toggle(callback: CallbackQuery):
    """Переключение глобального показа баннеров"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    current = db.get_design_setting('show_banner_global')
    if current is None:
        current = '1'
    
    new_value = '0' if current == '1' else '1'
    db.update_design_setting('show_banner_global', new_value)
    
    await callback.answer(f"✅ Глобальный показ баннеров {'включен' if new_value == '1' else 'выключен'}")
    
    # Обновляем текущее сообщение
    await banner_global_settings(callback)

async def banner_add_with_settings_start(callback: CallbackQuery, state: FSMContext):
    """Начало добавления баннера с настройками"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    await state.set_state(DesignStates.add_banner)
    await callback.message.answer(
        "🖼️ <b>ДОБАВЛЕНИЕ БАННЕРА</b>\n\n"
        "1. Отправьте фото для баннера\n"
        "2. После отправки введите название баннера\n"
        "3. Затем вы сможете настроить, где показывать баннер\n\n"
        "Баннер можно будет показывать в разных разделах бота:\n"
        "• 🏠 Приветствие\n"
        "• 📁 Каталог\n"
        "• 🛒 Корзина\n"
        "• 📦 Заказы\n"
        "• 👤 Профиль\n"
        "• 🎁 Конкурс\n"
        "• 🆘 Поддержка",
        parse_mode="HTML"
    )
    await callback.answer()

async def banner_add_photo(message: Message, state: FSMContext):
    """Обработка фото баннера"""
    if not message.photo:
        await message.answer("❌ Отправьте фото")
        return
    
    photo_id = message.photo[-1].file_id
    await state.update_data(banner_photo=photo_id)
    
    await message.answer(
        "📝 Отлично! Теперь введите название баннера:",
        reply_markup=kb.get_cancel_keyboard()
    )

async def banner_add_name_with_settings(message: Message, state: FSMContext):
    """Сохранение баннера с настройками"""
    data = await state.get_data()
    photo_id = data.get('banner_photo')
    name = message.text.strip()
    
    if not photo_id:
        await message.answer("❌ Ошибка: фото не найдено")
        await state.clear()
        return
    
    if not name:
        await message.answer("❌ Введите название баннера")
        return
    
    # Создаем баннер с настройками по умолчанию (только на приветствие)
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO banners (name, image_id, position, show_on_welcome, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (name, photo_id, 'top', 1, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    
    banner_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    await message.answer(
        f"✅ Баннер <b>{name}</b> добавлен!\n\n"
        f"Теперь настройте, где его показывать:",
        parse_mode="HTML"
    )
    
    # Создаем фейковый callback для редактирования
    class FakeCallback:
        def __init__(self, message, banner_id):
            self.message = message
            self.data = f"banner_edit_{banner_id}"
            self.from_user = message.from_user
    
    fake_callback = FakeCallback(message, banner_id)
    
    # Открываем меню настройки
    await banner_edit(fake_callback)
    await state.clear()

async def banner_settings(callback: CallbackQuery):
    """Настройки баннера"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    banner_id = int(callback.data.split("_")[2])
    
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM banners WHERE id = ?', (banner_id,))
    banner = cursor.fetchone()
    conn.close()
    
    if not banner:
        await callback.answer("Баннер не найден", show_alert=True)
        return
    
    banner_dict = dict(banner)
    
    text = f"🖼️ <b>НАСТРОЙКИ БАННЕРА</b>\n\n"
    text += f"Название: <b>{banner_dict['name']}</b>\n"
    text += f"Статус: {'🟢 Активен' if banner_dict.get('is_active', 0) else '🔴 Неактивен'}\n\n"
    text += "<b>Показывать в разделах:</b>\n\n"
    
    builder = InlineKeyboardBuilder()
    
    # Список разделов
    sections = [
        ('welcome', '🏠 Приветствие', banner_dict.get('show_on_welcome', 0)),
        ('catalog', '📁 Каталог', banner_dict.get('show_on_catalog', 0)),
        ('cart', '🛒 Корзина', banner_dict.get('show_on_cart', 0)),
        ('orders', '📦 Заказы', banner_dict.get('show_on_orders', 0)),
        ('profile', '👤 Профиль', banner_dict.get('show_on_profile', 0)),
        ('contest', '🎁 Конкурс', banner_dict.get('show_on_contest', 0)),
        ('support', '🆘 Поддержка', banner_dict.get('show_on_support', 0))
    ]
    
    for section_key, section_name, is_active in sections:
        status = "✅" if is_active else "❌"
        text += f"{status} {section_name}\n"
        
        # Кнопка для переключения раздела
        builder.row(InlineKeyboardButton(
            text=f"{'🔴 Выключить' if is_active else '🟢 Включить'} в разделе {section_name}",
            callback_data=f"banner_section_{banner_id}_{section_key}"
        ))
    
    # Кнопка для переключения активности баннера
    builder.row(InlineKeyboardButton(
        text=f"{'🔴 Деактивировать' if banner_dict.get('is_active', 0) else '🟢 Активировать'} баннер",
        callback_data=f"banner_active_{banner_id}"
    ))
    builder.row(InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="banner_list"))
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

async def design_shop_name(callback: CallbackQuery, state: FSMContext):
    """Изменение названия магазина"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    current = db.get_design_setting('shop_name')
    await state.set_state(DesignStates.edit_shop_name)
    
    await callback.message.edit_text(
        f"🏪 <b>НАЗВАНИЕ МАГАЗИНА</b>\n\n"
        f"Текущее:\n<b>{current}</b>\n\n"
        f"Введите новое название:",
        parse_mode="HTML",
        reply_markup=kb.get_cancel_keyboard_inline()
    )
    await callback.answer()

async def save_shop_name(message: Message, state: FSMContext):
    """Сохранение названия магазина"""
    new_name = message.text.strip()
    
    if not new_name:
        await message.answer("❌ Название не может быть пустым")
        return
    
    if len(new_name) > 50:
        await message.answer("❌ Название слишком длинное (максимум 50 символов)")
        return
    
    db.update_design_setting('shop_name', new_name)
    
    await message.answer(
        f"✅ Название магазина изменено!\n\n"
        f"Новое название:\n<b>{new_name}</b>",
        parse_mode="HTML",
        reply_markup=kb.get_main_keyboard(message.from_user.id)
    )
    await state.clear()

async def design_shop_name(callback: CallbackQuery, state: FSMContext):
    """Изменение названия магазина"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    current_name = db.get_design_setting('shop_name')
    await state.set_state(DesignStates.edit_shop_name)
    
    await callback.message.edit_text(
        f"🏪 <b>НАЗВАНИЕ МАГАЗИНА</b>\n\n"
        f"Текущее название:\n<i>{current_name}</i>\n\n"
        f"Введите новое название магазина:\n\n"
        f"<i>Можно использовать эмодзи и до 50 символов</i>",
        parse_mode="HTML",
        reply_markup=kb.get_cancel_keyboard_inline()
    )
    await callback.answer()

async def save_shop_name(message: Message, state: FSMContext):
    """Сохранение названия магазина"""
    new_name = message.text.strip()
    
    if not new_name:
        await message.answer("❌ Название не может быть пустым")
        return
    
    if len(new_name) > 50:
        await message.answer("❌ Название слишком длинное (максимум 50 символов)")
        return
    
    db.update_design_setting('shop_name', new_name)
    
    await message.answer(
        f"✅ Название магазина изменено!\n\n"
        f"Новое название:\n<b>{new_name}</b>",
        parse_mode="HTML",
        reply_markup=kb.get_main_keyboard(message.from_user.id)
    )
    await state.clear()

async def design_description(callback: CallbackQuery, state: FSMContext):
    """Изменение описания"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    current = db.get_design_setting('shop_description')
    await state.set_state(DesignStates.edit_description)
    
    await callback.message.edit_text(
        f"📄 <b>ОПИСАНИЕ МАГАЗИНА</b>\n\n"
        f"Текущее:\n<i>{current}</i>\n\n"
        f"Введите новое описание:",
        parse_mode="HTML",
        reply_markup=kb.get_cancel_keyboard_inline()
    )
    await callback.answer()

async def save_description(message: Message, state: FSMContext):
    """Сохранение описания магазина"""
    new_desc = message.text.strip()
    
    if not new_desc:
        await message.answer("❌ Описание не может быть пустым")
        return
    
    if len(new_desc) > 200:
        await message.answer("❌ Описание слишком длинное (максимум 200 символов)")
        return
    
    db.update_design_setting('shop_description', new_desc)
    
    await message.answer(
        f"✅ Описание магазина изменено!\n\n"
        f"Новое описание:\n<i>{new_desc}</i>",
        parse_mode="HTML",
        reply_markup=kb.get_main_keyboard(message.from_user.id)
    )
    await state.clear()

async def design_welcome_text(callback: CallbackQuery, state: FSMContext):
    """Изменение приветственного текста"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    current = db.get_design_setting('welcome_text')
    await state.set_state(DesignStates.edit_text)
    
    await callback.message.edit_text(
        f"📝 <b>ПРИВЕТСТВЕННЫЙ ТЕКСТ</b>\n\n"
        f"Текущий:\n<i>{current}</i>\n\n"
        f"Введите новый текст:",
        parse_mode="HTML",
        reply_markup=kb.get_cancel_keyboard_inline()
    )
    await callback.answer()

async def save_welcome_text(message: Message, state: FSMContext):
    """Сохранение приветственного текста"""
    new_text = message.text.strip()
    
    if not new_text:
        await message.answer("❌ Текст не может быть пустым")
        return
    
    db.update_design_setting('welcome_text', new_text)
    
    await message.answer(
        f"✅ Приветственный текст изменен!\n\n"
        f"Новый текст:\n<i>{new_text}</i>",
        parse_mode="HTML",
        reply_markup=kb.get_main_keyboard(message.from_user.id)
    )
    await state.clear()

async def banner_add_simple(callback: CallbackQuery, state: FSMContext):
    """Добавление баннера"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    await state.set_state(DesignStates.add_banner)
    await callback.message.answer(
        "🖼️ <b>ДОБАВЛЕНИЕ БАННЕРА</b>\n\n"
        "1. Отправьте фото\n"
        "2. После отправки введите название",
        parse_mode="HTML",
        reply_markup=kb.get_cancel_keyboard()
    )
    await callback.answer()

async def banner_list_simple(callback: CallbackQuery):
    """Список баннеров"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    banners = db.get_all_banners()
    
    if not banners:
        await callback.message.answer("📋 Нет баннеров")
        await callback.answer()
        return
    
    text = "📋 <b>СПИСОК БАННЕРОВ</b>\n\n"
    builder = InlineKeyboardBuilder()
    
    for banner in banners:
        b_dict = dict(banner)
        text += f"🖼️ <b>{b_dict['name']}</b>\n"
        text += f"   Статус: {'✅ Активен' if b_dict.get('is_active') else '❌ Неактивен'}\n"
        text += f"   Показ: "
        sections = []
        if b_dict.get('show_on_welcome'): sections.append("🏠 Приветствие")
        if b_dict.get('show_on_catalog'): sections.append("📁 Каталог")
        if b_dict.get('show_on_cart'): sections.append("🛒 Корзина")
        if b_dict.get('show_on_orders'): sections.append("📦 Заказы")
        if b_dict.get('show_on_profile'): sections.append("👤 Профиль")
        if b_dict.get('show_on_contest'): sections.append("🎁 Конкурс")
        if b_dict.get('show_on_support'): sections.append("🆘 Поддержка")
        text += ", ".join(sections) if sections else "Нигде\n"
        text += "\n\n"
        
        builder.row(
            InlineKeyboardButton(text=f"⚙️ Настроить {b_dict['name']}", callback_data=f"banner_config_{b_dict['id']}"),
            InlineKeyboardButton(text=f"🗑 Удалить", callback_data=f"banner_remove_{b_dict['id']}")
        )
    
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="design_banners"))
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

async def banner_config(callback: CallbackQuery):
    """Настройка баннера - выбор разделов"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    banner_id = int(callback.data.split("_")[2])
    
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM banners WHERE id = ?', (banner_id,))
    banner = cursor.fetchone()
    conn.close()
    
    if not banner:
        await callback.answer("Баннер не найден", show_alert=True)
        return
    
    b_dict = dict(banner)
    
    text = f"🖼️ <b>НАСТРОЙКА БАННЕРА</b>\n\n"
    text += f"Название: <b>{b_dict['name']}</b>\n"
    text += f"Статус: {'🟢 Активен' if b_dict.get('is_active') else '🔴 Неактивен'}\n\n"
    text += "<b>Показывать в разделах:</b>\n\n"
    
    builder = InlineKeyboardBuilder()
    
    # Кнопки для каждого раздела
    sections = [
        ('welcome', '🏠 Приветствие', b_dict.get('show_on_welcome', 0)),
        ('catalog', '📁 Каталог', b_dict.get('show_on_catalog', 0)),
        ('cart', '🛒 Корзина', b_dict.get('show_on_cart', 0)),
        ('orders', '📦 Заказы', b_dict.get('show_on_orders', 0)),
        ('profile', '👤 Профиль', b_dict.get('show_on_profile', 0)),
        ('contest', '🎁 Конкурс', b_dict.get('show_on_contest', 0)),
        ('support', '🆘 Поддержка', b_dict.get('show_on_support', 0))
    ]
    
    for section_key, section_name, is_active in sections:
        status = "✅" if is_active else "❌"
        text += f"{status} {section_name}\n"
        builder.row(InlineKeyboardButton(
            text=f"{'🔴 Выключить' if is_active else '🟢 Включить'} {section_name}",
            callback_data=f"banner_switch_{banner_id}_{section_key}"
        ))
    
    builder.row(InlineKeyboardButton(
        text=f"{'🔴 Деактивировать' if b_dict.get('is_active') else '🟢 Активировать'} баннер",
        callback_data=f"banner_active_{banner_id}"
    ))
    builder.row(InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="banner_list_simple"))
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

async def banner_switch(callback: CallbackQuery):
    """Включение/выключение раздела для баннера"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    parts = callback.data.split("_")
    banner_id = int(parts[2])
    section = parts[3]
    
    section_col = {
        'welcome': 'show_on_welcome',
        'catalog': 'show_on_catalog',
        'cart': 'show_on_cart',
        'orders': 'show_on_orders',
        'profile': 'show_on_profile',
        'contest': 'show_on_contest',
        'support': 'show_on_support'
    }.get(section)
    
    if not section_col:
        await callback.answer("Ошибка", show_alert=True)
        return
    
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f'SELECT {section_col} FROM banners WHERE id = ?', (banner_id,))
    result = cursor.fetchone()
    
    if result:
        new_val = 0 if result[0] else 1
        cursor.execute(f'UPDATE banners SET {section_col} = ? WHERE id = ?', (new_val, banner_id))
        conn.commit()
    
    conn.close()
    
    await callback.answer("✅ Настройка сохранена")
    await banner_config(callback)

async def banner_active(callback: CallbackQuery):
    """Активация/деактивация баннера"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    banner_id = int(callback.data.split("_")[2])
    
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT is_active FROM banners WHERE id = ?', (banner_id,))
    result = cursor.fetchone()
    
    if result:
        new_val = 0 if result[0] else 1
        cursor.execute('UPDATE banners SET is_active = ? WHERE id = ?', (new_val, banner_id))
        conn.commit()
    
    conn.close()
    
    await callback.answer("✅ Статус изменен")
    await banner_config(callback)

async def banner_remove(callback: CallbackQuery):
    """Удаление баннера"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    banner_id = int(callback.data.split("_")[2])
    
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM banners WHERE id = ?', (banner_id,))
    conn.commit()
    conn.close()
    
    await callback.answer("✅ Баннер удален")
    await banner_list_simple(callback)

async def save_banner_photo(message: Message, state: FSMContext):
    """Сохранение фото баннера"""
    if not message.photo:
        await message.answer("❌ Отправьте фото")
        return
    
    photo_id = message.photo[-1].file_id
    await state.update_data(banner_photo=photo_id)
    await message.answer("📝 Введите название баннера:")

async def save_banner_name(message: Message, state: FSMContext):
    """Сохранение баннера"""
    data = await state.get_data()
    photo_id = data.get('banner_photo')
    name = message.text.strip()
    
    if not photo_id:
        await message.answer("❌ Ошибка")
        await state.clear()
        return
    
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO banners (name, image_id, show_on_welcome, created_at)
        VALUES (?, ?, ?, ?)
    ''', (name, photo_id, 1, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    
    await message.answer(f"✅ Баннер '{name}' добавлен!\n\nТеперь настройте его в меню баннеров.")
    await state.clear()

async def send_with_banner(bot, chat_id, text, skip_banner=False, **kwargs):
    """Отправка сообщения с баннером (если нужно)"""
    if skip_banner:
        return await bot.send_message(chat_id, text, **kwargs)
    
    banner = db.get_active_banner()
    if banner:
        return await bot.send_photo(
            chat_id,
            photo=banner['image_id'],
            caption=text,
            **kwargs
        )
    else:
        return await bot.send_message(chat_id, text, **kwargs)
    
def get_cancel_keyboard_inline():
    """Инлайн клавиатура для отмены"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_design"))
    return builder.as_markup()
