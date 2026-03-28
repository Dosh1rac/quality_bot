from aiogram.fsm.state import StatesGroup, State

class AddProductStates(StatesGroup):
    name = State()
    description = State()
    price = State()
    cost_price = State()
    stock = State()
    category = State()
    image = State()

class AddPreorderStates(StatesGroup):
    name = State()
    description = State()
    price = State()
    cost_price = State()
    category = State()
    image = State()

class BroadcastStates(StatesGroup):
    text = State()

class CheckoutStates(StatesGroup):
    payment = State()
    wait_payment = State()
    confirm = State()

class CategoryStates(StatesGroup):
    add_code = State()
    add_name = State()
    add_emoji = State()
    add_sort = State()
    edit_name = State()
    edit_emoji = State()
    edit_sort = State()

class ContestStates(StatesGroup):
    name = State()
    description = State()
    prize = State()
    winners_count = State()
    start_date = State()
    end_date = State()
    criteria = State()
    criteria_value = State()

class MassUploadStates(StatesGroup):
    file = State()
    category = State()
    confirm = State()
    waiting_photos = State()

class EditProductStates(StatesGroup):
    select_field = State()
    edit_name = State()
    edit_description = State()
    edit_price = State()
    edit_cost_price = State()
    edit_stock = State()
    edit_category = State()
    edit_image = State()

class DesignStates(StatesGroup):
    edit_color = State()
    edit_text = State()
    edit_shop_name = State()
    edit_description = State()
    add_banner = State()