import asyncio
import logging
import sqlite3
import random
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# ==========================================
# НАСТРОЙКИ
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN")

DB_NAME = "finance.db"


# Словари с фиксированными тратами
TRANSPORT_ITEMS = {"Автобус": 65.0, "Метро Дима": 65.0, "Метро Вика": 95.0, "Такси": None, "Другое (транспорт)": None}
CAFE_ITEMS = {"Кофе Вика": 240.0, "Другое (кафе)": None}
APARTMENT_ITEMS = {"Квартира": 26000.0, "К/У": None}
CONNECTION_ITEMS = {"Мобильная связь": None, "Билайн 100": 100.0, "Интернет домашний": 500.0, "Прочее (связь)": None}

# Маппинг для красивой статистики (чтобы кучу мелких трат объединить в одну категорию)
CATEGORY_GROUPS = {
    "Автобус": "Транспорт", "Метро Дима": "Транспорт", "Метро Вика": "Транспорт", "Такси": "Транспорт", "Другое (транспорт)": "Транспорт",
    "Кофе Вика": "Кафе/Рестораны", "Другое (кафе)": "Кафе/Рестораны",
    "Квартира": "Квартира", "К/У": "Квартира",
    "Мобильная связь": "Связь", "Билайн 100": "Связь", "Интернет домашний": "Связь", "Прочее (связь)": "Связь"
}

# ==========================================
# БАЗА ДАННЫХ
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            amount REAL,
            category TEXT,
            date TEXT
        )
    ''')
    conn.commit()
    conn.close()

def add_record(record_type, amount, category):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    date = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute("INSERT INTO records (type, amount, category, date) VALUES (?, ?, ?, ?)",
                   (record_type, amount, category, date))
    conn.commit()
    conn.close()

def get_balance():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(amount) FROM records WHERE type='income'")
    income = cursor.fetchone()[0] or 0.0
    cursor.execute("SELECT SUM(amount) FROM records WHERE type='expense'")
    expense = cursor.fetchone()[0] or 0.0
    cursor.execute("SELECT SUM(amount) FROM records WHERE type='savings_in'")
    savings_in = cursor.fetchone()[0] or 0.0
    cursor.execute("SELECT SUM(amount) FROM records WHERE type='savings_out'")
    savings_out = cursor.fetchone()[0] or 0.0
    conn.close()
    
    savings = savings_in - savings_out
    balance = income - expense - savings
    return income, expense, savings, balance

def get_stats():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(amount) FROM records WHERE type='income'")
    total_income = cursor.fetchone()[0] or 0.0
    cursor.execute("SELECT SUM(amount) FROM records WHERE type='expense'")
    total_expense = cursor.fetchone()[0] or 0.0
    cursor.execute("SELECT category, SUM(amount) FROM records WHERE type='expense' GROUP BY category")
    all_expenses = cursor.fetchall()
    conn.close()
    return total_income, total_expense, all_expenses

# ==========================================
# ШУТКИ И МАТЫ
# ==========================================
def get_funny_phrase(action):
    if action == "expense":
        return random.choice([
            "Охереть, опять траты. Ну ладно, записал.",
            "Деньги улетают, как Афина за мячиком. Записал.",
            "Дима, Вика, вы там не охуели так тратить? Ладно, записал.",
            "Кошелек плачет, но я записал.",
            "Куда катимся... Записал расход."
        ])
    elif action == "income":
        return random.choice([
            "О, бабки пришли! Красавчики!",
            "Денюжка капает, можно и Афине корм хороший купить!",
            "Молодцы! Так держать!",
            "Наконец-то! Я уже думал, вы всё проедите."
        ])
    elif action == "savings_in":
        return "Отложили? Ну хоть что-то. Копите на будку для Афины."
    elif action == "savings_out":
        return "БЛЯДЬ! Вы что творите?! Достаете из копилки! Надеюсь, это что-то важное."
    return ""

# ==========================================
# СОСТОЯНИЯ (FSM)
# ==========================================
class FinanceStates(StatesGroup):
    waiting_income = State()
    waiting_custom_expense = State()
    waiting_savings_in = State()
    waiting_savings_out = State()

# ==========================================
# БОТ И КЛАВИАТУРЫ
# ==========================================
router = Router()

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💸 Добавить приход"), KeyboardButton(text="🛒 Добавить расход")],
            [KeyboardButton(text="🐷 В копилку"), KeyboardButton(text="🚨 Взять из копилки")],
            [KeyboardButton(text="💳 Мой баланс"), KeyboardButton(text="📊 Статистика")]
        ],
        resize_keyboard=True
    )

def get_expense_categories():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚌 Транспорт", callback_data="cat_transport"), InlineKeyboardButton(text="☕ Кафе/Рестораны", callback_data="cat_cafe")],
        [InlineKeyboardButton(text="🛒 Продукты", callback_data="cat_products"), InlineKeyboardButton(text="🏠 Квартира", callback_data="cat_apartment")],
        [InlineKeyboardButton(text="🐶 Афина", callback_data="cat_afina"), InlineKeyboardButton(text="👕 Одежда и обувь", callback_data="cat_clothes")],
        [InlineKeyboardButton(text="💄 Косметика", callback_data="cat_cosmetics"), InlineKeyboardButton(text="📱 Связь", callback_data="cat_connection")],
        [InlineKeyboardButton(text="🎮 Хобби", callback_data="cat_hobby"), InlineKeyboardButton(text="🏥 Здоровье", callback_data="cat_health")],
        [InlineKeyboardButton(text="📈 Инвестиции", callback_data="cat_invest"), InlineKeyboardButton(text="📦 Другое", callback_data="cat_other")]
    ])

def get_sub_menu(items, prefix):
    buttons = []
    for name, amount in items.items():
        btn_text = f"{name} ({amount}₽)" if amount else name
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"{prefix}_{name}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_categories")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ==========================================
# ХЕНДЛЕРЫ
# ==========================================
@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        f"Привет, Дима и Вика! 🚀\n"
        f"Я ваш семейный финансовый бро. Помогу не спустить всё на ветер и накопить на мечту (и на корм Афине 🐶).\n\n"
        "Выбирайте действие:",
        reply_markup=get_main_keyboard()
    )

@router.message(F.text == "💳 Мой баланс")
async def show_balance(message: Message):
    income, expense, savings, balance = get_balance()
    text = f"📊 <b>Текущая ситуация:</b>\n\n"
    text += f"Свободные деньги: <b>{balance:.2f} руб.</b> 💵\n"
    text += f"В копилке: <b>{savings:.2f} руб.</b> 🐷\n\n"
    text += f"<i>Общий капитал:</i> <b>{balance + savings:.2f} руб.</b> 🏦"
    await message.answer(text, parse_mode="HTML")

@router.message(F.text == "📊 Статистика")
async def show_stats(message: Message):
    total_income, total_expense, all_expenses = get_stats()
    _, _, savings, balance = get_balance()
    
    # Группируем расходы по крупным категориям
    grouped = {}
    for cat, amount in all_expenses:
        parent_cat = CATEGORY_GROUPS.get(cat, cat)
        grouped[parent_cat] = grouped.get(parent_cat, 0.0) + amount
    
    # Сортируем от большего к меньшему
    sorted_grouped = sorted(grouped.items(), key=lambda x: x[1], reverse=True)
    
    comments = []
    if total_income == 0:
        comments.append("🤔 Пока пусто. Идите зарабатывать!")
    else:
        ratio = total_expense / total_income
        if ratio > 0.9: comments.append("🚨 <b>ПОЖАР!</b> Вы всё проебли! Остановитесь!")
        elif ratio > 0.7: comments.append("💀 Вы спустили больше 70%. Дима, Вика, заканчивайте с доставками!")
        elif ratio < 0.5: comments.append("👑 <b>Вы финансовые гении!</b> Тратите меньше половины.")
            
    if savings > 0: comments.append("🔥 В копилке есть деньги. Афина гордится вами!")

    text = f"📈 <b>Заработано:</b> {total_income:.2f} руб.\n"
    text += f"📉 <b>Потрачено:</b> {total_expense:.2f} руб.\n"
    text += f"🐷 <b>В копилке:</b> {savings:.2f} руб.\n"
    text += f"💵 <b>На руках:</b> {balance:.2f} руб.\n\n"
    
    if sorted_grouped:
        text += "<b>Расходы по категориям:</b>\n"
        for cat, amount in sorted_grouped:
            text += f"▪️ {cat}: {amount:.2f} руб.\n"
        text += "\n"
        
    text += f"<i>Совет:</i> {' '.join(comments)}"
    await message.answer(text, parse_mode="HTML")

# --- ПРИХОД ---
@router.message(F.text == "💸 Добавить приход")
async def start_income(message: Message, state: FSMContext):
    await state.set_state(FinanceStates.waiting_income)
    await message.answer("💸 Откуда прилетело и сколько?\nПример: <code>5000 Фриланс</code>", parse_mode="HTML")

@router.message(FinanceStates.waiting_income)
async def process_income(message: Message, state: FSMContext):
    try:
        parts = message.text.split(maxsplit=1)
        amount = float(parts[0])
        category = parts[1] if len(parts) > 1 else "Без категории"
        
        add_record("income", amount, category)
        await state.clear()
        phrase = get_funny_phrase("income")
        
        await message.answer(f"🎉 <b>+{amount:.2f} руб.</b> ({category}).\n{phrase}", parse_mode="HTML", reply_markup=get_main_keyboard())
        
        for admin_id in ADMIN_IDS:
            if admin_id != message.from_user.id:
                try:
                    await message.bot.send_message(admin_id, f"🔔 <b>ОПОВЕЩЕНИЕ:</b> {message.from_user.first_name} добавил(а) приход!\nСумма: <b>{amount:.2f} руб.</b> ({category})", parse_mode="HTML")
                except: pass
                
    except ValueError:
        await message.answer("❌ Ошибка! Напиши сначала цифру.\nПример: 5000 Аванс")

# --- РАСХОД (МЕНЮ) ---
@router.message(F.text == "🛒 Добавить расход")
async def start_expense(message: Message):
    await message.answer("Выбери категорию расходов:", reply_markup=get_expense_categories())

@router.callback_query(F.data == "back_to_categories")
async def back_to_cats(callback: CallbackQuery):
    await callback.message.edit_text("Выбери категорию расходов:", reply_markup=get_expense_categories())

# --- ОБРАБОТКА КАТЕГОРИЙ ---
@router.callback_query(F.data.startswith("cat_"))
async def handle_category(callback: CallbackQuery, state: FSMContext):
    cat = callback.data.split("_")[1]
    
    if cat == "transport": await callback.message.edit_text("Транспорт:", reply_markup=get_sub_menu(TRANSPORT_ITEMS, "trn"))
    elif cat == "cafe": await callback.message.edit_text("Кафе/Рестораны:", reply_markup=get_sub_menu(CAFE_ITEMS, "caf"))
    elif cat == "apartment": await callback.message.edit_text("Квартира:", reply_markup=get_sub_menu(APARTMENT_ITEMS, "apt"))
    elif cat == "connection": await callback.message.edit_text("Связь:", reply_markup=get_sub_menu(CONNECTION_ITEMS, "con"))
    else:
        cat_names = {
            "products": "Продукты", "afina": "Афина", "clothes": "Одежда и обувь",
            "cosmetics": "Косметика", "hobby": "Хобби и развлечения", 
            "health": "Здоровье", "invest": "Инвестиции", "other": "Другое"
        }
        cat_name = cat_names.get(cat, "Расход")
        await state.update_data(category_name=cat_name)
        await state.set_state(FinanceStates.waiting_custom_expense)
        await callback.message.edit_text(f"Введи сумму для категории <b>{cat_name}</b>:", parse_mode="HTML")
    await callback.answer()

# --- ОБРАБОТКА ПОДКАТЕГОРИЙ (КНОПКИ) ---
@router.callback_query(F.data.startswith("trn_") | F.data.startswith("caf_") | F.data.startswith("apt_") | F.data.startswith("con_"))
async def handle_sub_items(callback: CallbackQuery, state: FSMContext):
    data = callback.data.split("_", 1)
    prefix, item_name = data[0], data[1]
    
    dict_map = {"trn": TRANSPORT_ITEMS, "caf": CAFE_ITEMS, "apt": APARTMENT_ITEMS, "con": CONNECTION_ITEMS}
    amount = dict_map[prefix].get(item_name)
    
    if amount is not None:
        add_record("expense", amount, item_name)
        phrase = get_funny_phrase("expense")
        
        _, _, _, balance = get_balance()
        await callback.message.edit_text(f"✅ Записано: <b>{item_name}</b> на {amount} руб.\n{phrase}\n\n💵 <b>Текущий баланс:</b> {balance:.2f} руб.", parse_mode="HTML")
        await state.clear()
    else:
        await state.update_data(category_name=item_name)
        await state.set_state(FinanceStates.waiting_custom_expense)
        await callback.message.edit_text(f"Введи сумму для <b>{item_name}</b>:", parse_mode="HTML")
    await callback.answer()

# --- ВВОД ПРОИЗВОЛЬНОЙ СУММЫ РАСХОДА ---
@router.message(FinanceStates.waiting_custom_expense)
async def process_custom_expense(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
        data = await state.get_data()
        category = data.get("category_name", "Прочее")
        
        add_record("expense", amount, category)
        phrase = get_funny_phrase("expense")
        _, _, _, balance = get_balance()
        
        await state.clear()
        await message.answer(f"✅ Записано: <b>{category}</b> на {amount:.2f} руб.\n{phrase}\n\n💵 <b>Текущий баланс:</b> {balance:.2f} руб.", parse_mode="HTML", reply_markup=get_main_keyboard())
    except ValueError:
        await message.answer("❌ Напиши просто цифру. Например: 450")

# --- КОПИЛКА ---
@router.message(F.text == "🐷 В копилку")
async def start_savings_in(message: Message, state: FSMContext):
    _, _, savings, _ = get_balance()
    await state.set_state(FinanceStates.waiting_savings_in)
    await message.answer(f"🐷 Сейчас в копилке: <b>{savings:.2f} руб.</b>\nСколько откладываем? (просто цифру)", parse_mode="HTML")

@router.message(FinanceStates.waiting_savings_in)
async def process_savings_in(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
        add_record("savings_in", amount, "Копилка")
        await state.clear()
        phrase = get_funny_phrase("savings_in")
        _, _, savings, _ = get_balance()
        await message.answer(f"✨ <b>{amount:.2f} руб.</b> в копилке.\n{phrase}\n🐷 Всего в копилке: {savings:.2f} руб.", parse_mode="HTML", reply_markup=get_main_keyboard())
    except ValueError:
        await message.answer("❌ Ошибка! Введи цифру.")

@router.message(F.text == "🚨 Взять из копилки")
async def start_savings_out(message: Message, state: FSMContext):
    _, _, savings, _ = get_balance()
    await state.set_state(FinanceStates.waiting_savings_out)
    await message.answer(f"🚨 ЧЕРНЫЙ ДЕНЬ? Сейчас в копилке: <b>{savings:.2f} руб.</b>\nСколько достаем?", parse_mode="HTML")

@router.message(FinanceStates.waiting_savings_out)
async def process_savings_out(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
        _, _, savings, _ = get_balance()
        
        if amount > savings:
            await message.answer(f"💀 Вы чё, обкурились? В копилке всего {savings:.2f} руб.!")
            return
            
        add_record("savings_out", amount, "Из копилки")
        await state.clear()
        phrase = get_funny_phrase("savings_out")
        
        _, _, new_savings, new_balance = get_balance()
        
        await message.answer(
            f"💀 <b>-{amount:.2f} руб.</b> из копилки.\n{phrase}\n\n"
            f"💵 <b>Свободные деньги (баланс):</b> {new_balance:.2f} руб.\n"
            f"🐷 <b>Остаток в копилке:</b> {new_savings:.2f} руб.", 
            parse_mode="HTML", reply_markup=get_main_keyboard()
        )
    except ValueError:
        await message.answer("❌ Ошибка! Введи цифру.")

# ==========================================
# ЗАПУСК
# ==========================================
async def main():
    init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    print("Финансовый бот для Димы и Вики запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен.")
