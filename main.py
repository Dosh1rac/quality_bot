import asyncio
import logging

# Оставляем только этот импорт для прокси
from aiohttp_socks import ProxyConnector
from aiogram.filters import Command, StateFilter
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram import Bot, Dispatcher, F
import config
import database as db
import handlers
import contest_handlers
import auto_tasks
from states import (
    AddProductStates,
    AddPreorderStates,
    BroadcastStates,
    CheckoutStates,
    CategoryStates,
    ContestStates,
    MassUploadStates,
    EditProductStates,
    DesignStates
)

async def main():
    logging.basicConfig(level=logging.INFO)
    db.init_db()
    db.init_settings()
    total_users = db.get_total_users()
    print(f"📊 В базе данных {total_users} пользователей")

    # --- НАСТРОЙКА ПРОКСИ ---
    session = AiohttpSession(proxy="socks5://127.0.0.1:1080")
    bot = Bot(token=config.BOT_TOKEN, session=session)
    dp = Dispatcher()

    # 1. Базовые команды
    dp.message.register(handlers.start_command, Command("start"), StateFilter(None))
    dp.message.register(handlers.cancel_handler, F.text == "❌ Отмена")
    dp.callback_query.register(handlers.cancel_action_handler, F.data == "cancel_action")

    # 2. Текстовые кнопки меню
    dp.message.register(handlers.catalog_text_btn, F.text == "🛍 Каталог", StateFilter(None))
    dp.message.register(handlers.cart_text_btn, F.text == "🛒 Корзина", StateFilter(None))
    dp.message.register(handlers.profile_text_btn, F.text == "👤 Профиль", StateFilter(None))
    dp.message.register(handlers.my_orders_text_btn, F.text == "📦 Мои заказы", StateFilter(None))
    dp.message.register(handlers.rating_text_btn, F.text == "🏆 Рейтинг", StateFilter(None))
    dp.message.register(contest_handlers.show_contest_info, F.text == "🎁 Конкурс")
    dp.message.register(handlers.support_text_btn, F.text == "🆘 Поддержка", StateFilter(None))
    dp.message.register(handlers.admin_text_btn, F.text == "🔧 Админ панель", StateFilter(None))

    # 3. Корзина и заказы
    dp.callback_query.register(handlers.add_to_cart_callback, F.data.startswith("buy_"))
    dp.callback_query.register(handlers.clear_cart_callback, F.data == "clear_cart")
    dp.callback_query.register(handlers.checkout_start, F.data == "checkout")
    dp.callback_query.register(handlers.checkout_payment, F.data.startswith("payment_"), CheckoutStates.payment)
    dp.callback_query.register(handlers.checkout_confirm_payment, F.data == "confirm_payment", CheckoutStates.wait_payment)
    dp.callback_query.register(handlers.checkout_confirm, F.data.in_(["confirm_order", "cancel_order"]), CheckoutStates.confirm)
    dp.callback_query.register(handlers.remove_from_cart_callback, F.data.startswith("remove_"))

    # 4. Админ-панель
    dp.callback_query.register(handlers.admin_stats_callback, F.data == "admin_stats")
    dp.callback_query.register(handlers.admin_profit_stats, F.data == "admin_profit")
    dp.callback_query.register(handlers.admin_orders_manage_callback, F.data == "admin_orders")
    dp.callback_query.register(handlers.admin_order_details, F.data.startswith("manage_order_"))
    dp.callback_query.register(handlers.admin_set_order_status, F.data.startswith("set_status_"))
    dp.callback_query.register(handlers.delete_product_callback, F.data.regexp(r'^delete_\d+$'))
    dp.callback_query.register(handlers.admin_confirm_reset, F.data == "admin_confirm_reset")
    dp.callback_query.register(handlers.admin_do_reset, F.data == "admin_do_reset")
    dp.callback_query.register(handlers.admin_back, F.data == "admin_back")

    dp.callback_query.register(contest_handlers.admin_contests_menu, F.data == "admin_contests")
    dp.callback_query.register(contest_handlers.admin_create_contest_start, F.data == "admin_create_contest")
    dp.callback_query.register(contest_handlers.show_active_contests, F.data == "admin_active_contests")
    dp.callback_query.register(contest_handlers.show_finished_contests, F.data == "admin_finished_contests")
    # 5. Рассылка
    dp.callback_query.register(handlers.admin_broadcast_start, F.data == "admin_broadcast")
    dp.message.register(handlers.admin_broadcast_send, BroadcastStates.text)

    # 6. Управление категориями
    dp.callback_query.register(handlers.admin_categories_menu, F.data == "admin_categories")
    dp.callback_query.register(handlers.admin_add_category_start, F.data == "admin_add_category")
    dp.callback_query.register(handlers.admin_edit_categories, F.data == "admin_edit_categories")
    dp.callback_query.register(handlers.admin_delete_category_menu, F.data == "admin_delete_category")
    dp.callback_query.register(handlers.admin_edit_category_select, F.data.startswith("edit_cat_"))
    dp.callback_query.register(handlers.admin_category_rename, F.data.startswith("cat_rename_"))
    dp.callback_query.register(handlers.admin_category_change_emoji, F.data.startswith("cat_change_emoji_"))
    dp.callback_query.register(handlers.admin_category_change_sort, F.data.startswith("cat_change_sort_"))
    dp.callback_query.register(handlers.admin_category_toggle, F.data.startswith("cat_toggle_"))
    dp.callback_query.register(handlers.admin_category_confirm_delete, F.data.startswith("confirm_delete_cat_"))
    dp.callback_query.register(handlers.admin_category_delete, F.data.regexp(r'^delete_cat_\d+$'))
    dp.callback_query.register(handlers.admin_no_delete, F.data.startswith("no_delete_"))

    # 7. Добавление товара
    dp.callback_query.register(handlers.admin_add_product_start, F.data == "admin_add_product")
    dp.message.register(handlers.add_product_name, AddProductStates.name)
    dp.message.register(handlers.add_product_description, AddProductStates.description)
    dp.message.register(handlers.add_product_price, AddProductStates.price)
    dp.message.register(handlers.add_product_cost_price, AddProductStates.cost_price)
    dp.message.register(handlers.add_product_stock, AddProductStates.stock)
    dp.callback_query.register(handlers.add_product_category, F.data.startswith("cat_"), AddProductStates.category)
    dp.message.register(handlers.add_product_image, AddProductStates.image, F.photo)
    
    # 8. Добавление предзаказа
    dp.callback_query.register(handlers.admin_add_preorder_start, F.data == "admin_add_preorder")
    db.init_db()
    db.init_settings()
    total_users = db.get_total_users()
    print(f"📊 В базе данных {total_users} пользователей")
    
    dp.message.register(handlers.add_preorder_name, AddPreorderStates.name)
    dp.message.register(handlers.add_preorder_description, AddPreorderStates.description)
    dp.message.register(handlers.add_preorder_price, AddPreorderStates.price)
    dp.message.register(handlers.add_preorder_cost_price, AddPreorderStates.cost_price)
    dp.callback_query.register(handlers.add_preorder_category, F.data.startswith("cat_"), AddPreorderStates.category)
    dp.message.register(handlers.add_preorder_image, AddPreorderStates.image, F.photo)
    
    # 9. Просмотр категорий и товаров
    dp.callback_query.register(handlers.show_category_products, F.data.startswith("cat_"), StateFilter(None))
    dp.callback_query.register(handlers.view_product, F.data.startswith("view_product_"))
    dp.callback_query.register(handlers.back_to_products, F.data.startswith("back_to_products_"))
    dp.callback_query.register(handlers.back_to_categories, F.data == "back_to_categories")
    dp.callback_query.register(handlers.back_to_main_menu, F.data == "back_to_main_menu")

    # 10. Состояния для категорий
    dp.message.register(handlers.add_category_code, CategoryStates.add_code)
    dp.message.register(handlers.add_category_name, CategoryStates.add_name)
    dp.message.register(handlers.add_category_emoji, CategoryStates.add_emoji)
    dp.message.register(handlers.add_category_sort, CategoryStates.add_sort)
    dp.message.register(handlers.admin_category_rename_save, CategoryStates.edit_name)
    dp.message.register(handlers.admin_category_emoji_save, CategoryStates.edit_emoji)
    dp.message.register(handlers.admin_category_sort_save, CategoryStates.edit_sort)

    # 11. Управление конкурсами
    dp.callback_query.register(contest_handlers.admin_contests_menu, F.data == "admin_contests")
    dp.callback_query.register(contest_handlers.admin_create_contest_start, F.data == "admin_create_contest")
    dp.callback_query.register(contest_handlers.show_active_contests, F.data == "admin_active_contests")
    dp.callback_query.register(contest_handlers.show_finished_contests, F.data == "admin_finished_contests")
    dp.callback_query.register(contest_handlers.contest_details, F.data.startswith("contest_details_"))
    dp.callback_query.register(contest_handlers.contest_participants, F.data.startswith("contest_participants_"))
    dp.callback_query.register(contest_handlers.contest_select_winners, F.data.startswith("contest_select_winners_"))
    dp.callback_query.register(contest_handlers.contest_end, F.data.startswith("contest_end_"))
    dp.callback_query.register(contest_handlers.participate_contest, F.data.startswith("participate_contest_"))
    dp.callback_query.register(contest_handlers.show_contest_winners, F.data.startswith("contest_winners_"))
    dp.callback_query.register(contest_handlers.back_to_contests_menu, F.data == "admin_contests")
    dp.callback_query.register(contest_handlers.back_to_active_contests, F.data == "back_to_active_contests")
    dp.callback_query.register(contest_handlers.back_to_admin_panel, F.data == "back_to_admin_panel")
    
    # Обработчики для создания конкурса
    dp.message.register(contest_handlers.create_contest_name, ContestStates.name)
    dp.message.register(contest_handlers.create_contest_description, ContestStates.description)
    dp.message.register(contest_handlers.create_contest_prize, ContestStates.prize)
    dp.message.register(contest_handlers.create_contest_winners_count, ContestStates.winners_count)
    dp.callback_query.register(contest_handlers.create_contest_start_date, F.data.startswith("date_"), ContestStates.start_date)
    dp.callback_query.register(contest_handlers.create_contest_end_date, F.data.startswith("date_"), ContestStates.end_date)
    dp.callback_query.register(contest_handlers.create_contest_criteria, F.data.startswith("contest_criteria_"), ContestStates.criteria)
    dp.message.register(contest_handlers.create_contest_criteria_value, ContestStates.criteria_value)
    
    # Отмена создания конкурса
    dp.callback_query.register(handlers.cancel_action_callback, F.data == "cancel_contest_creation")

    # 12. Массовая загрузка товаров
    dp.callback_query.register(handlers.admin_mass_upload_start, F.data == "admin_mass_upload")
    dp.message.register(handlers.process_products_file, MassUploadStates.file, F.document)
    dp.callback_query.register(handlers.process_mass_upload_category, F.data.startswith("cat_"), MassUploadStates.category)
    dp.callback_query.register(handlers.skip_photo, F.data == "skip_photo", MassUploadStates.waiting_photos)
    dp.callback_query.register(handlers.cancel_mass_upload, F.data == "cancel_mass_upload", MassUploadStates.waiting_photos)
    dp.callback_query.register(handlers.finish_upload, F.data == "finish_upload", MassUploadStates.waiting_photos)
    dp.message.register(handlers.handle_product_photo, MassUploadStates.waiting_photos, F.photo)

    # 13. Управление товарами (редактирование)
    dp.callback_query.register(handlers.admin_manage_products, F.data == "admin_manage_products")
    dp.callback_query.register(handlers.edit_product_menu, F.data.startswith("edit_product_"))
    dp.callback_query.register(handlers.edit_product_field, F.data.startswith("edit_field_"))
    dp.callback_query.register(handlers.edit_product_category, F.data.startswith("cat_"), EditProductStates.edit_category)
    dp.message.register(handlers.edit_product_image, EditProductStates.edit_image, F.photo)
    dp.message.register(handlers.edit_product_name, EditProductStates.edit_name)
    dp.message.register(handlers.edit_product_description, EditProductStates.edit_description)
    dp.message.register(handlers.edit_product_price, EditProductStates.edit_price)
    dp.message.register(handlers.edit_product_cost_price, EditProductStates.edit_cost_price)
    dp.message.register(handlers.edit_product_stock, EditProductStates.edit_stock)
# Удаление товара (замени старую регистрацию delete, если она была)
    dp.callback_query.register(handlers.delete_product_callback, F.data.startswith("delete_"))
    
    # Универсальная отмена для всех callback-кнопок "Отмена"
    dp.callback_query.register(handlers.cancel_action_callback, F.data == "cancel_action")


    # 14. Обновление количества товара (из карточки)
    dp.callback_query.register(handlers.admin_update_stock_start, F.data.startswith("update_stock_"))
    dp.message.register(handlers.admin_update_stock, F.text, StateFilter("waiting_stock"))

  # Баннеры
    dp.callback_query.register(handlers.design_banners_menu, F.data == "design_banners")
    dp.callback_query.register(handlers.banner_add_start, F.data == "banner_add")
    dp.callback_query.register(handlers.banner_list, F.data == "banner_list")
    dp.callback_query.register(handlers.banner_activate, F.data.startswith("banner_activate_"))
    dp.callback_query.register(handlers.banner_delete, F.data.startswith("banner_delete_"))
    
    dp.message.register(handlers.banner_add_photo, DesignStates.add_banner, F.photo)
    dp.message.register(handlers.banner_add_name, DesignStates.add_banner)

        # Дизайн бота
    dp.callback_query.register(handlers.admin_design_menu, F.data == "admin_design")
    dp.callback_query.register(handlers.design_colors_menu, F.data == "design_colors")
    dp.callback_query.register(handlers.design_welcome_text, F.data == "design_welcome")
    dp.callback_query.register(handlers.design_shop_name, F.data == "design_shop_name")
    dp.callback_query.register(handlers.design_description, F.data == "design_description")
    dp.callback_query.register(handlers.color_setting, F.data.startswith("color_"))
    
    dp.message.register(handlers.save_color_setting, DesignStates.edit_color)
    dp.message.register(handlers.save_welcome_text, DesignStates.edit_text)
    dp.message.register(handlers.save_shop_name, DesignStates.edit_shop_name)
    dp.message.register(handlers.save_description, DesignStates.edit_description)

    # 17. Выгрузка базы данных и экспорт
    dp.callback_query.register(handlers.admin_backup_db, F.data == "admin_backup_db")
    dp.callback_query.register(handlers.admin_export_excel, F.data == "admin_export_excel")

# Запуск фоновых задач
    asyncio.create_task(auto_tasks.auto_backup_task(bot))
    asyncio.create_task(auto_tasks.auto_report_task(bot))
    asyncio.create_task(auto_tasks.auto_finish_contests_task(bot))
    asyncio.create_task(auto_tasks.auto_check_stock_task(bot))

    print("🤖 Бот запущен и слушает сообщения...")

    try:
        # Важно: запускаем процесс получения обновлений
        await dp.start_polling(bot)
    finally:
        # Корректно закрываем сессию (важно для aiohttp)
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n❌ Бот остановлен")
