from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import ADMIN_IDS
import database as db

# --- РЕПЛАЙ КЛАВИАТУРЫ ---

def get_main_keyboard(user_id=None):
    kb = [
        [KeyboardButton(text="🛍 Каталог")],
        [KeyboardButton(text="📦 Мои заказы")],
        [KeyboardButton(text="🎁 Конкурс"), KeyboardButton(text="🆘 Поддержка")],
        [KeyboardButton(text="🛒 Корзина"), KeyboardButton(text="👤 Профиль")]
    ]
    if user_id and user_id in ADMIN_IDS:
        kb.append([KeyboardButton(text="🏆 Рейтинг"), KeyboardButton(text="🔧 Админ панель")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, persistent=True)

def get_cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
        persistent=True
    )

def get_cancel_keyboard_inline():
    """Инлайн клавиатура для отмены"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_contest_creation"))
    return builder.as_markup()

# --- ИНЛАЙН КЛАВИАТУРЫ ---

def get_admin_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Товар", callback_data="admin_add_product"),
                InlineKeyboardButton(text="⏰ Предзаказ", callback_data="admin_add_preorder"))
    builder.row(InlineKeyboardButton(text="📊 Массовая загрузка", callback_data="admin_mass_upload"))
    builder.row(InlineKeyboardButton(text="✏️ Управление товарами", callback_data="admin_manage_products"))
    builder.row(InlineKeyboardButton(text="📁 Управление категориями", callback_data="admin_categories"))
    builder.row(InlineKeyboardButton(text="🎨 Дизайн бота", callback_data="admin_design"))
    
    # ДОБАВЛЕНА КНОПКА КОНКУРСОВ ТУТ:
    builder.row(InlineKeyboardButton(text="🎁 Конкурсы", callback_data="admin_contests")) 
    
    builder.row(InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
                InlineKeyboardButton(text="💰 Прибыль", callback_data="admin_profit"))
    builder.row(InlineKeyboardButton(text="📉 Сброс прибыли + Отчет .txt", callback_data="admin_confirm_reset"))
    builder.row(InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"),
                InlineKeyboardButton(text="📦 Управление заказами", callback_data="admin_orders"))
    builder.row(InlineKeyboardButton(text="💾 Выгрузить БД", callback_data="admin_backup_db"),
                InlineKeyboardButton(text="📊 Экспорт в Excel", callback_data="admin_export_excel"))

    return builder.as_markup()

def get_category_admin_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Добавить категорию", callback_data="admin_add_category"))
    builder.row(InlineKeyboardButton(text="📝 Редактировать категории", callback_data="admin_edit_categories"))
    builder.row(InlineKeyboardButton(text="🗑 Удалить категорию", callback_data="admin_delete_category"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    return builder.as_markup()

def get_categories_keyboard():
    """Клавиатура с категориями"""
    builder = InlineKeyboardBuilder()
    categories = db.get_all_categories(include_inactive=False)
    for cat in categories:
        builder.row(InlineKeyboardButton(
            text=f"{cat['emoji']} {cat['name']}", 
            callback_data=f"cat_{cat['id']}"
        ))
    builder.row(InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_main_menu"))
    return builder.as_markup()

def get_categories_edit_keyboard():
    builder = InlineKeyboardBuilder()
    categories = db.get_all_categories(include_inactive=True)
    for cat in categories:
        status = "✅" if cat['is_active'] else "❌"
        builder.row(InlineKeyboardButton(text=f"{status} {cat['emoji']} {cat['name']}", callback_data=f"edit_cat_{cat['id']}"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_categories"))
    return builder.as_markup()

def get_category_action_keyboard(category_id):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"cat_rename_{category_id}"))
    builder.row(InlineKeyboardButton(text="😊 Изменить эмодзи", callback_data=f"cat_change_emoji_{category_id}"))
    builder.row(InlineKeyboardButton(text="🔢 Изменить порядок", callback_data=f"cat_change_sort_{category_id}"))
    builder.row(InlineKeyboardButton(text="🔄 Вкл/Выкл", callback_data=f"cat_toggle_{category_id}"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_edit_categories"))
    return builder.as_markup()

def get_categories_delete_keyboard():
    builder = InlineKeyboardBuilder()
    categories = db.get_all_categories(include_inactive=True)
    for cat in categories:
        products_count = len(db.get_products_by_category_id(cat['id']))
        delete_text = f"🗑 {cat['emoji']} {cat['name']}"
        if products_count > 0:
            delete_text += f" ({products_count} товаров) - нельзя удалить"
            builder.row(InlineKeyboardButton(text=delete_text, callback_data=f"no_delete_{cat['id']}"))
        else:
            builder.row(InlineKeyboardButton(text=delete_text, callback_data=f"confirm_delete_cat_{cat['id']}"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_categories"))
    return builder.as_markup()

def get_confirm_delete_keyboard(category_id):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_cat_{category_id}"),
        InlineKeyboardButton(text="❌ Нет, отмена", callback_data="admin_delete_category")
    )
    return builder.as_markup()

def get_product_keyboard(product_id, is_admin=False):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🛒 В корзину", callback_data=f"buy_{product_id}"))
    if is_admin:
        builder.row(InlineKeyboardButton(text="🗑 Удалить товар", callback_data=f"delete_{product_id}"))
    return builder.as_markup()

def get_confirm_reset_kb():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, сбросить", callback_data="admin_do_reset"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="admin_profit")
    )
    return builder.as_markup()

def get_cart_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💳 Оформить заказ", callback_data="checkout"))
    builder.row(InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="clear_cart"))
    return builder.as_markup()

def get_confirm_keyboard():
    """Клавиатура подтверждения заказа (Inline)"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_order"),
        InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order")
    )
    return builder.as_markup()

def get_payment_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💵 Наличные при получении", callback_data="payment_cash"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_order"))
    return builder.as_markup()

def get_payment_confirmation_keyboard():
    """Клавиатура подтверждения оплаты (Inline)"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Я оплатил", callback_data="confirm_payment"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_order"))
    return builder.as_markup()

# ============= НОВЫЕ ФУНКЦИИ ДЛЯ КОНКУРСОВ =============

def get_contests_admin_keyboard():
    """Клавиатура управления конкурсами"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎯 Создать конкурс", callback_data="admin_create_contest"))
    builder.row(InlineKeyboardButton(text="📋 Активные конкурсы", callback_data="admin_active_contests"))
    builder.row(InlineKeyboardButton(text="🏆 Завершенные конкурсы", callback_data="admin_finished_contests"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад в админку", callback_data="back_to_admin_panel"))  # Изменено
    return builder.as_markup()

def get_contest_criteria_keyboard():
    """Клавиатура выбора критериев конкурса"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 Автоматическое участие всех", callback_data="contest_criteria_auto"))
    builder.row(InlineKeyboardButton(text="📦 По количеству покупок", callback_data="contest_criteria_orders"))
    builder.row(InlineKeyboardButton(text="💰 По сумме покупок", callback_data="contest_criteria_spent"))
    builder.row(InlineKeyboardButton(text="👍 Ручное участие (кнопка)", callback_data="contest_criteria_manual"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_contest_creation"))
    return builder.as_markup()

def get_contest_details_keyboard(contest_id):
    """Клавиатура для управления конкретным конкурсом"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="👥 Участники", callback_data=f"contest_participants_{contest_id}"))
    builder.row(InlineKeyboardButton(text="🏆 Выбрать победителей", callback_data=f"contest_select_winners_{contest_id}"))
    builder.row(InlineKeyboardButton(text="❌ Завершить конкурс", callback_data=f"contest_end_{contest_id}"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="back_to_active_contests"))  # Изменено
    return builder.as_markup()

def get_participate_keyboard(contest_id):
    """Кнопка участия в конкурсе"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎁 Участвовать в конкурсе!", callback_data=f"participate_contest_{contest_id}"))
    return builder.as_markup()

def get_contest_info_keyboard(contest_id):
    """Клавиатура с информацией о конкурсе"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✨ Участвовать", callback_data=f"participate_contest_{contest_id}"))
    builder.row(InlineKeyboardButton(text="🏆 Победители", callback_data=f"contest_winners_{contest_id}"))
    return builder.as_markup()

def get_contest_winners_keyboard(contest_id):
    """Клавиатура для просмотра победителей"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏆 Победители", callback_data=f"contest_winners_{contest_id}"))
    return builder.as_markup()

def get_color_keyboard():
    """Клавиатура выбора цвета"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🟢 Основной", callback_data="color_primary"),
        InlineKeyboardButton(text="🔵 Вторичный", callback_data="color_secondary")
    )
    builder.row(
        InlineKeyboardButton(text="🟠 Акцентный", callback_data="color_accent"),
        InlineKeyboardButton(text="⚪ Текст", callback_data="color_text")
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="design_colors"))
    return builder.as_markup()

def get_banner_keyboard():
    """Клавиатура управления баннерами"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Добавить баннер", callback_data="banner_add"))
    builder.row(InlineKeyboardButton(text="📋 Список баннеров", callback_data="banner_list"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_design"))
    return builder.as_markup()

def get_design_keyboard():
    """Клавиатура управления дизайном"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎨 Цвета", callback_data="design_colors"))
    builder.row(InlineKeyboardButton(text="📝 Приветственный текст", callback_data="design_welcome"))
    builder.row(InlineKeyboardButton(text="🏪 Название магазина", callback_data="design_shop_name"))
    builder.row(InlineKeyboardButton(text="📄 Описание магазина", callback_data="design_description"))
    builder.row(InlineKeyboardButton(text="🖼️ Баннер", callback_data="design_banners"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    return builder.as_markup()
