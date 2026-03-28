import asyncio
import logging
import json
from datetime import datetime, timedelta
from aiogram import F, types, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder  # <-- ДОБАВЬТЕ ЭТУ СТРОКУ
from aiogram.fsm.context import FSMContext

import config
import database as db
import keyboards as kb
from states import ContestStates

# ==========================================
#         ФУНКЦИИ ДЛЯ КОНКУРСОВ
# ==========================================

async def admin_contests_menu(callback: CallbackQuery):
    """Меню управления конкурсами"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    await callback.message.edit_text(
        "<b>🎁 УПРАВЛЕНИЕ КОНКУРСАМИ</b>\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=kb.get_contests_admin_keyboard()
    )
    await callback.answer()

async def admin_create_contest_start(callback: CallbackQuery, state: FSMContext):
    """Начало создания конкурса"""
    await state.set_state(ContestStates.name)
    await callback.message.edit_text(
        "<b>🎯 СОЗДАНИЕ КОНКУРСА</b>\n\n"
        "Введите название конкурса:",
        parse_mode="HTML",
        reply_markup=kb.get_cancel_keyboard_inline()
    )
    await callback.answer()

async def create_contest_name(message: Message, state: FSMContext):
    """Получение названия конкурса"""
    await state.update_data(name=message.text)
    await state.set_state(ContestStates.description)
    await message.answer(
        "📝 Введите описание конкурса:\n\n"
        "Опишите условия, приз и другие детали:",
        reply_markup=kb.get_cancel_keyboard()
    )

async def create_contest_description(message: Message, state: FSMContext):
    """Получение описания конкурса"""
    await state.update_data(description=message.text)
    await state.set_state(ContestStates.prize)
    await message.answer(
        "🎁 Введите описание приза:\n\n"
        "Например: Одноразовый вейп на 5000 тяг",
        reply_markup=kb.get_cancel_keyboard()
    )

async def create_contest_prize(message: Message, state: FSMContext):
    """Получение приза"""
    await state.update_data(prize=message.text)
    await state.set_state(ContestStates.winners_count)
    await message.answer(
        "🏆 Введите количество победителей (число):\n\n"
        "Сколько человек получат приз?",
        reply_markup=kb.get_cancel_keyboard()
    )

async def create_contest_winners_count(message: Message, state: FSMContext):
    """Получение количества победителей"""
    if not message.text.isdigit():
        await message.answer("⚠️ Введите число (количество победителей):")
        return
    
    await state.update_data(winners_count=int(message.text))
    await state.set_state(ContestStates.start_date)
    
    # Показываем клавиатуру с выбором даты
    keyboard = get_date_keyboard()
    await message.answer(
        "📅 Выберите дату начала конкурса:",
        reply_markup=keyboard
    )

async def create_contest_start_date(callback: CallbackQuery, state: FSMContext):
    """Выбор даты начала"""
    date_str = callback.data.split("_")[1]
    await state.update_data(start_date=date_str)
    await state.set_state(ContestStates.end_date)
    
    keyboard = get_date_keyboard()
    await callback.message.edit_text(
        "📅 Выберите дату окончания конкурса:",
        reply_markup=keyboard
    )
    await callback.answer()

async def create_contest_end_date(callback: CallbackQuery, state: FSMContext):
    """Выбор даты окончания"""
    date_str = callback.data.split("_")[1]
    await state.update_data(end_date=date_str)
    await state.set_state(ContestStates.criteria)
    
    await callback.message.edit_text(
        "<b>🎯 ВЫБЕРИТЕ КРИТЕРИЙ УЧАСТИЯ</b>\n\n"
        "Как будут определяться участники конкурса?",
        parse_mode="HTML",
        reply_markup=kb.get_contest_criteria_keyboard()
    )
    await callback.answer()

async def create_contest_criteria(callback: CallbackQuery, state: FSMContext):
    """Выбор критерия участия"""
    criteria = callback.data.replace("contest_criteria_", "")
    await state.update_data(criteria_type=criteria)
    
    data = await state.get_data()
    
    if criteria in ['min_orders', 'min_spent']:
        # Запрашиваем значение критерия
        criteria_text = "количества заказов" if criteria == 'min_orders' else "суммы покупок"
        await state.set_state(ContestStates.criteria_value)
        await callback.message.edit_text(
            f"📊 Введите минимальное {criteria_text} для участия:\n\n"
            f"Например: {5 if criteria == 'min_orders' else 1000}",
            reply_markup=kb.get_cancel_keyboard_inline()
        )
    else:
        # Создаем конкурс сразу
        await save_contest(callback, state, data)
    
    await callback.answer()

async def create_contest_criteria_value(message: Message, state: FSMContext):
    """Получение значения критерия"""
    if not message.text.replace('.', '', 1).isdigit():
        await message.answer("⚠️ Введите число:", reply_markup=kb.get_cancel_keyboard())
        return
    
    await state.update_data(criteria_value=message.text)
    data = await state.get_data()
    await save_contest(message, state, data)

async def save_contest(event, state: FSMContext, data):
    """Сохраняет конкурс в базу данных"""
    contest_id = db.create_contest(
        name=data['name'],
        description=data['description'],
        start_date=data['start_date'] + " 00:00:00",
        end_date=data['end_date'] + " 23:59:59",
        criteria_type=data['criteria_type'],
        criteria_value=data.get('criteria_value', '0'),
        prize=data['prize'],
        winners_count=data['winners_count']
    )
    
    await state.clear()
    
    # Отправляем сообщение о создании конкурса
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(
            f"✅ Конкурс успешно создан!\n\n"
            f"Название: {data['name']}\n"
            f"Приз: {data['prize']}\n"
            f"Даты: с {data['start_date']} по {data['end_date']}",
            reply_markup=kb.get_contests_admin_keyboard()
        )
    else:
        await event.answer(
            f"✅ Конкурс успешно создан!\n\n"
            f"Название: {data['name']}\n"
            f"Приз: {data['prize']}",
            reply_markup=kb.get_main_keyboard(event.from_user.id)
        )

async def show_active_contests(callback: CallbackQuery):
    """Показывает активные конкурсы"""
    contests = db.get_all_contests(include_inactive=False)
    
    if not contests:
        # Создаем клавиатуру с кнопкой назад
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="admin_contests"))
        
        await callback.message.edit_text(
            "📭 Нет активных конкурсов.\n\n"
            "Создайте новый конкурс через меню управления.",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
        await callback.answer()
        return
    
    text = "<b>🎁 АКТИВНЫЕ КОНКУРСЫ</b>\n\n"
    builder = InlineKeyboardBuilder()
    
    for contest in contests:
        participants_count = len(db.get_contest_participants(contest['id']))
        text += f"📌 <b>{contest['name']}</b>\n"
        text += f"Приз: {contest['prize']}\n"
        text += f"Участников: {participants_count}\n"
        text += f"До: {contest['end_date'][:10]}\n\n"
        
        builder.add(InlineKeyboardButton(
            text=f"📋 Подробнее",
            callback_data=f"contest_details_{contest['id']}"
        ))
        builder.add(InlineKeyboardButton(
            text=f"🏆 Выбрать победителей",
            callback_data=f"contest_select_winners_{contest['id']}"
        ))
        builder.add(InlineKeyboardButton(
            text=f"❌ Завершить",
            callback_data=f"contest_end_{contest['id']}"
        ))
    
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="admin_contests"))
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

async def show_finished_contests(callback: CallbackQuery):
    """Показывает завершенные конкурсы"""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM contests WHERE end_date < datetime('now') OR is_active = 0 ORDER BY end_date DESC")
    contests = cursor.fetchall()
    conn.close()
    
    if not contests:
        # Создаем клавиатуру с кнопкой назад
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="admin_contests"))
        
        await callback.message.edit_text(
            "📭 Нет завершенных конкурсов.",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
        await callback.answer()
        return
    
    text = "<b>🏆 ЗАВЕРШЕННЫЕ КОНКУРСЫ</b>\n\n"
    builder = InlineKeyboardBuilder()
    
    for contest in contests:
        participants_count = len(db.get_contest_participants(contest['id']))
        winners = json.loads(contest['winners']) if contest['winners'] else []
        
        text += f"📌 <b>{contest['name']}</b>\n"
        text += f"Приз: {contest['prize']}\n"
        text += f"Участников: {participants_count}\n"
        
        if winners:
            text += f"🏆 Победители: {', '.join([w['full_name'] for w in winners])}\n"
        
        text += f"Дата: {contest['end_date'][:10]}\n\n"
        
        builder.add(InlineKeyboardButton(
            text=f"📋 Подробнее",
            callback_data=f"contest_details_{contest['id']}"
        ))
    
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="admin_contests"))
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

async def contest_details(callback: CallbackQuery):
    """Детали конкурса"""
    contest_id = int(callback.data.split("_")[2])
    contest = db.get_contest(contest_id)
    
    if not contest:
        await callback.answer("Конкурс не найден", show_alert=True)
        return
    
    participants = db.get_contest_participants(contest_id)
    winners = json.loads(contest['winners']) if contest['winners'] else []
    
    criteria_text = {
        'auto_participate': '🔄 Автоматическое (все пользователи)',
        'min_orders': f'📦 Минимум {contest["criteria_value"]} заказов',
        'min_spent': f'💰 Минимум {contest["criteria_value"]} руб.',
        'manual': '👍 Ручное участие'
    }.get(contest['criteria_type'], contest['criteria_type'])
    
    text = (
        f"<b>📋 ИНФОРМАЦИЯ О КОНКУРСЕ</b>\n\n"
        f"📌 Название: <b>{contest['name']}</b>\n"
        f"🎁 Приз: {contest['prize']}\n"
        f"📅 Дата начала: {contest['start_date'][:10]}\n"
        f"📅 Дата окончания: {contest['end_date'][:10]}\n"
        f"🎯 Критерий: {criteria_text}\n"
        f"👥 Участников: {len(participants)}\n"
        f"🏆 Победителей: {contest['winners_count']}\n\n"
    )
    
    if winners:
        text += "<b>🏆 ПОБЕДИТЕЛИ:</b>\n"
        for i, winner in enumerate(winners, 1):
            text += f"{i}. {winner['full_name']} (@{winner['username']})\n"
    
    # Создаем клавиатуру с кнопкой назад
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="👥 Участники", callback_data=f"contest_participants_{contest_id}"))
    builder.row(InlineKeyboardButton(text="🏆 Выбрать победителей", callback_data=f"contest_select_winners_{contest_id}"))
    builder.row(InlineKeyboardButton(text="❌ Завершить конкурс", callback_data=f"contest_end_{contest_id}"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="admin_active_contests"))
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

async def contest_participants(callback: CallbackQuery):
    """Показывает участников конкурса"""
    contest_id = int(callback.data.split("_")[2])
    participants = db.get_contest_participants(contest_id)
    
    if not participants:
        await callback.answer("Нет участников", show_alert=True)
        return
    
    text = "<b>👥 УЧАСТНИКИ КОНКУРСА</b>\n\n"
    
    for i, p in enumerate(participants[:20], 1):
        winner_mark = "🏆 " if p['is_winner'] else ""
        text += f"{i}. {winner_mark}{p['full_name']} (@{p['username'] or 'нет юзернейма'})\n"
        text += f"   📦 Заказов: {p['total_spent'] if 'total_spent' in p else '?'}\n"
    
    if len(participants) > 20:
        text += f"\n... и еще {len(participants) - 20} участников"
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_contest_details_keyboard(contest_id))
    await callback.answer()

async def contest_select_winners(callback: CallbackQuery, bot: Bot):
    """Выбирает победителей конкурса"""
    contest_id = int(callback.data.split("_")[3])
    contest = db.get_contest(contest_id)
    
    if not contest:
        await callback.answer("Конкурс не найден", show_alert=True)
        return
    
    participants = db.get_contest_participants(contest_id)
    
    if len(participants) < contest['winners_count']:
        await callback.answer(f"Недостаточно участников! Нужно минимум {contest['winners_count']}", show_alert=True)
        return
    
    winners = db.select_winners(contest_id)
    
    # Отправляем уведомления победителям
    for winner in winners:
        try:
            await bot.send_message(
                winner['user_id'],
                f"🎉 <b>ПОЗДРАВЛЯЕМ! ВЫ ВЫИГРАЛИ КОНКУРС!</b>\n\n"
                f"Конкурс: {contest['name']}\n"
                f"Приз: {contest['prize']}\n\n"
                f"Для получения приза свяжитесь с менеджером: {config.SUPPORT_LINK}",
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"Ошибка отправки уведомления победителю {winner['user_id']}: {e}")
    
    # Формируем текст для администратора
    winners_text = "\n".join([f"{i}. {w['full_name']} (@{w['username']})" for i, w in enumerate(winners, 1)])
    
    await callback.message.edit_text(
        f"✅ Победители выбраны!\n\n"
        f"<b>🏆 ПОБЕДИТЕЛИ:</b>\n{winners_text}\n\n"
        f"Уведомления отправлены победителям.",
        parse_mode="HTML",
        reply_markup=kb.get_contest_details_keyboard(contest_id)
    )
    await callback.answer()

async def contest_end(callback: CallbackQuery):
    """Завершает конкурс"""
    contest_id = int(callback.data.split("_")[2])
    db.update_contest(contest_id, is_active=0)
    
    await callback.message.edit_text(
        "✅ Конкурс завершен!",
        reply_markup=kb.get_contests_admin_keyboard()
    )
    await callback.answer()

async def participate_contest(callback: CallbackQuery):
    """Участие в конкурсе"""
    contest_id = int(callback.data.split("_")[2])
    contest = db.get_contest(contest_id)
    user_id = callback.from_user.id
    
    if not contest:
        await callback.answer("Конкурс не найден", show_alert=True)
        return
    
    # Проверяем, активен ли конкурс
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if contest['end_date'] < now:
        await callback.answer("Конкурс уже завершен!", show_alert=True)
        return
    
    # Проверяем, участвует ли уже
    if db.is_user_participating(contest_id, user_id):
        await callback.answer("Вы уже участвуете в конкурсе!", show_alert=True)
        return
    
    # Проверяем критерии
    if not db.check_contest_criteria(contest, user_id):
        if contest['criteria_type'] == 'min_orders':
            await callback.answer(f"❌ Нужно сделать минимум {contest['criteria_value']} заказов!", show_alert=True)
        elif contest['criteria_type'] == 'min_spent':
            await callback.answer(f"❌ Нужно купить минимум на {contest['criteria_value']} руб!", show_alert=True)
        else:
            await callback.answer("❌ Вы не подходите под условия конкурса!", show_alert=True)
        return
    
    # Добавляем участника
    db.add_contest_participant(contest_id, user_id)
    await callback.answer("✅ Вы успешно участвуете в конкурсе!", show_alert=True)
    
    # Обновляем сообщение с информацией о конкурсе
    await callback.message.edit_reply_markup(reply_markup=None)

async def show_contest_info(message: Message):
    """Показывает информацию о текущем конкурсе"""
    contest = db.get_active_contest()
    
    if not contest:
        await message.answer(
            "🎁 В данный момент нет активных конкурсов.\n"
            "Следите за новостями!",
            reply_markup=kb.get_main_keyboard(message.from_user.id)
        )
        return
    
    now = datetime.now()
    end_date = datetime.strptime(contest['end_date'], "%Y-%m-%d %H:%M:%S")
    days_left = (end_date - now).days
    
    criteria_text = {
        'auto_participate': 'Все пользователи автоматически участвуют!',
        'min_orders': f'Нужно сделать минимум {contest["criteria_value"]} заказов',
        'min_spent': f'Нужно купить минимум на {contest["criteria_value"]} руб.',
        'manual': 'Нажми кнопку "Участвовать"'
    }.get(contest['criteria_type'], 'Уточняйте условия')
    
    text = (
        f"<b>🎁 АКТИВНЫЙ КОНКУРС</b>\n\n"
        f"<b>{contest['name']}</b>\n\n"
        f"{contest['description']}\n\n"
        f"🎁 <b>ПРИЗ:</b> {contest['prize']}\n"
        f"📅 <b>ДО ОКОНЧАНИЯ:</b> {days_left} дней\n"
        f"🎯 <b>УСЛОВИЯ:</b> {criteria_text}\n"
        f"🏆 <b>ПОБЕДИТЕЛЕЙ:</b> {contest['winners_count']}\n\n"
        f"Удачи!"
    )
    
    # Показываем кнопку участия только для ручного режима
    if contest['criteria_type'] == 'manual':
        reply_markup = kb.get_participate_keyboard(contest['id'])
    else:
        reply_markup = None
    
    await message.answer(text, parse_mode="HTML", reply_markup=reply_markup)

async def show_contest_winners(callback: CallbackQuery):
    """Показывает победителей конкурса"""
    contest_id = int(callback.data.split("_")[2])
    contest = db.get_contest(contest_id)
    
    if not contest:
        await callback.answer("Конкурс не найден", show_alert=True)
        return
    
    winners = json.loads(contest['winners']) if contest['winners'] else []
    
    if not winners:
        await callback.answer("Победители еще не выбраны!", show_alert=True)
        return
    
    text = f"<b>🏆 ПОБЕДИТЕЛИ КОНКУРСА</b>\n\n"
    text += f"<b>{contest['name']}</b>\n\n"
    
    for i, winner in enumerate(winners, 1):
        text += f"{i}. {winner['full_name']}\n"
    
    text += f"\n🎁 Приз: {contest['prize']}"
    
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

# Вспомогательная функция для создания клавиатуры с датами
def get_date_keyboard():
    """Создает клавиатуру с выбором даты"""
    builder = InlineKeyboardBuilder()
    
    # Следующие 7 дней
    for i in range(1, 8):
        date = (datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d")
        builder.add(InlineKeyboardButton(
            text=f"{i} день" if i == 1 else f"{i} дней",
            callback_data=f"date_{date}"
        ))
    
    builder.adjust(3)
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_contest_creation"))
    
    return builder.as_markup()

# ... все остальные функции выше ...

async def back_to_contests_menu(callback: CallbackQuery):
    """Возврат в главное меню конкурсов"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    await callback.message.edit_text(
        "<b>🎁 УПРАВЛЕНИЕ КОНКУРСАМИ</b>\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=kb.get_contests_admin_keyboard()
    )
    await callback.answer()

async def back_to_active_contests(callback: CallbackQuery):
    """Возврат к списку активных конкурсов"""
    await show_active_contests(callback)

async def back_to_finished_contests(callback: CallbackQuery):
    """Возврат к списку завершенных конкурсов"""
    await show_finished_contests(callback)

async def back_to_admin_panel(callback: CallbackQuery):
    """Возврат в админ панель"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("У вас нет прав", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🔧 Панель управления:",
        reply_markup=kb.get_admin_keyboard()
    )
    await callback.answer()

# Вспомогательная функция для создания клавиатуры с датами
def get_date_keyboard():
    """Создает клавиатуру с выбором даты"""
    builder = InlineKeyboardBuilder()
    
    # Следующие 7 дней
    for i in range(1, 8):
        date = (datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d")
        builder.add(InlineKeyboardButton(
            text=f"{i} день" if i == 1 else f"{i} дней",
            callback_data=f"date_{date}"
        ))
    
    builder.adjust(3)
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_contest_creation"))
    
    return builder.as_markup()