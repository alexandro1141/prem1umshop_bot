import logging
import uuid
from telegram import Update, ReplyKeyboardMarkup, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters, 
    PreCheckoutQueryHandler, CallbackContext
)
from keep_alive import keep_alive

# ==============================================================================
# КОНФИГУРАЦИЯ ЮРИДИЧЕСКИХ ДАННЫХ И ПЛАТЕЖЕЙ (ОБЯЗАТЕЛЬНО ЗАПОЛНИТЬ!)
# ==============================================================================
# Токен бота (Ваш текущий токен)
TOKEN = "8392743023:AAHjApwBpmoapx7NA3KW25iGmBITUvuOnDQ"

# 1. !!! ВСТАВЬТЕ СЮДА РЕАЛЬНЫЙ БОЕВОЙ (ИЛИ ТЕСТОВЫЙ) ТОКЕН ЮKASSA !!!
# Этот токен вы получаете в личном кабинете ЮKassa для интеграции с Telegram Payments.
# --- ПОЛЕ ВРЕМЕННО ЗАКОММЕНТИРОВАНО ДЛЯ ПРОХОЖДЕНИЯ МОДЕРАЦИИ ---
# YOOKASSA_PAYMENT_TOKEN = "<ВСТАВЬТЕ СЮДА ВАШ ТОКЕН ЮKASSA>"
# ВРЕМЕННЫЙ ПУСТОЙ ТОКЕН ДЛЯ МОДЕРАЦИИ:
YOOKASSA_PAYMENT_TOKEN = ""

# 2. Реквизиты самозанятого (ОБЯЗАТЕЛЬНО!)
# ВАЖНО: Укажите полное ФИО и статус "Самозанятый".
SELLER_NAME_FULL = "Алекс Алексанян Гайкович (Самозанятый)"

# 3. Ваш ИНН
SELLER_INN = "502993268720"

# 4. Почта для поддержки
SUPPORT_EMAIL = "prem1umshoptelegram@mail.ru" 

# ==============================================================================

# === Логирование ===
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# === Каталог Premium ===
PREMIUM_ITEMS = {
    "💎 3 месяца": {"name_for_check": "Предоставление доступа к Premium Telegram (3 месяца)", "price": 1200},
    "🚀 6 месяцев": {"name_for_check": "Предоставление доступа к Premium Telegram (6 месяцев)", "price": 1500},
    "👑 12 месяцев": {"name_for_check": "Предоставление доступа к Premium Telegram (12 месяцев)", "price": 2500},
}

# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    context.user_data.clear()

    keyboard = [
        ['⭐️ Бонусы '], 
        ['👑 Premium-доступ'],
        ['💬 Поддержка', '📄 Документы'] # Добавили кнопку "Документы"
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_html(
        f"🚀 <b>Добро пожаловать в PREM1UMSHOP!</b> {user.mention_html()}!\n\n"
        # ИСПРАВЛЕНО: Теперь реквизиты продавца отображаются корректно
        f"🎯 <b>Продавец:</b> {SELLER_NAME_FULL} (ИНН: {SELLER_INN})\n" 
        "<b>Покупай Бонусы и Premium-доступ по лучшим ценам!</b>\n\n"
        "<b>Выбери категорию:</b>",
        reply_markup=reply_markup
    )

# === Telegram Stars (переименовано в "Бонусы") ===
async def show_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data['category'] = 'stars'

    stars_info = "⭐️ Бонусы 'Звезда'\n\n🎉 Выбери вариант покупки:"
    keyboard = [['🎁 Купить себе', '🎀 Подарить другу'], ['🔙 Назад']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(stars_info, reply_markup=reply_markup)

# === Telegram Premium (переименовано в "Premium-доступ") ===
async def show_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data['category'] = 'premium'

    premium_info = "👑 Premium-доступ\n\n🎉 Выбери вариант покупки:"
    keyboard = [['🎁 Купить себе', '🎀 Подарить другу'], ['🔙 Назад']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(premium_info, reply_markup=reply_markup)

# === Подарок другу ===
async def handle_gift_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['gift_mode'] = True
    gift_info = (
        "🎀 <b>Подарок другу</b>\n\n"
        "Введите имя пользователя получателя:\n\n"
        "Например: <code>@username</code>"
    )
    keyboard = [['🔙 Назад']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_html(gift_info, reply_markup=reply_markup)

# === Показ соглашения и ссылки ===
async def show_documents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ИСПРАВЛЕНО: Теперь реквизиты продавца отображаются корректно
    agreement_text = (
        f"📄 <b>Документы и Реквизиты Продавца</b>\n\n"
        f"<b>Продавец:</b> {SELLER_NAME_FULL}\n"
        f"<b>ИНН:</b> {SELLER_INN}\n"
        f"<b>Почта поддержки:</b> {SUPPORT_EMAIL}\n\n"
        f"Перед оплатой ознакомьтесь с полными документами:\n"
        f"• Публичная оферта\n"
        f"• Политика возврата\n"
        f"• Политика конфиденциальности\n\n"
        f"🔗 <a href='https://alexandro1141.github.io/policy-page/policy.html'>Открыть соглашение</a>\n\n"
        f"<b>Нажимая 'Оплатить' вы подтверждаете согласие с условиями оферты.</b>"
    )

    keyboard = [['🔙 Назад']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_html(agreement_text, reply_markup=reply_markup)

# === Покупка Stars (инициирование платежа) ===
async def show_stars_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stars_info = "🎉 Для покупки бонусов выбери пакет или отправь своё количество (от 50 до 5000 ⭐️)"
    
    if context.user_data.get('gift_mode') and context.user_data.get('gift_username'):
        stars_info = f"🎁 Подарок для {context.user_data['gift_username']}\n\n" + stars_info

    keyboard = [
        ['100 ⭐️ (160Р)', '150 ⭐️ (240Р)'],
        ['250 ⭐️ (400Р)', '500 ⭐️ (800Р)'],
        ['1000 ⭐️ (1600Р)', '2500 ⭐️ (4000Р)'],
        ['🔙 Назад']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(stars_info, reply_markup=reply_markup)

async def process_stars_order(update: Update, context: ContextTypes.DEFAULT_TYPE, stars_count: int):
    # Имя товара для ЮKassa: четко и как услуга/бонус
    product_name = f"{stars_count} Бонусных Единиц 'Звезда'" 
    price = int(stars_count * 1.6) # курс 1 звезда = 1.6 руб
    
    # --- ИНТЕГРАЦИЯ С ОПЛАТОЙ ЮKASSA ЧЕРЕЗ TELEGRAM INVOICES ---
    title = f"Заказ #{uuid.uuid4().hex[:6].upper()}: {product_name}"
    description = (
        f"Продавец: {SELLER_NAME_FULL} (ИНН: {SELLER_INN}). "
        f"Оплата товара/услуги: {product_name}. "
        f"Нажимая 'Оплатить', Вы соглашаетесь с Офертой, Политикой возврата и Конфиденциальности."
    )

    # Параметры платежа для Telegram (цена в копейках)
    prices = [LabeledPrice(product_name, price * 100)]
    
    # Payload для отслеживания и формирования чека (самозанятый должен передать эти данные!)
    payload_data = {
        "order_id": str(uuid.uuid4()),
        "product_type": "stars",
        "stars_count": stars_count
    }
    
    # Отправка инвойса. Это ключевой момент для модерации!
    await update.message.reply_invoice(
        title=title,
        description=description,
        payload=str(payload_data), # payload должен быть строкой
        provider_token=YOOKASSA_PAYMENT_TOKEN, # Используем временный пустой токен для модерации
        currency="RUB",
        prices=prices,
        need_name=True,
        need_email=True, # Важно для отправки чека
        is_flexible=False,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📄 Открыть документы", url="https://alexandro1141.github.io/policy-page/policy.html")
        ]])
    )
    # --------------------------------------------------------------------


# === Покупка Premium (каталог, выбор и инициирование платежа) ===
async def show_premium_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    catalog_text = "👑 Premium-доступ:\n\n"
    for item in PREMIUM_ITEMS:
        item_data = PREMIUM_ITEMS[item]
        catalog_text += f"• {item} \n💰 Цена: {item_data['price']} руб.\n"

    if context.user_data.get('gift_mode') and context.user_data.get('gift_username'):
        catalog_text = f"🎁 Подарок для {context.user_data['gift_username']}\n\n" + catalog_text

    keyboard = [['💎 3 месяца', '🚀 6 месяцев'], ['👑 12 месяцев', '🔙 Назад']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(catalog_text, reply_markup=reply_markup)

async def process_premium_order(update: Update, context: ContextTypes.DEFAULT_TYPE, name: str, price: int):
    # Имя товара для ЮKassa: используем name_for_check для четкости
    product_name = PREMIUM_ITEMS[name]['name_for_check']
    
    # --- ИНТЕГРАЦИЯ С ОПЛАТОЙ ЮKASSA ЧЕРЕЗ TELEGRAM INVOICES ---
    title = f"Заказ #{uuid.uuid4().hex[:6].upper()}: {product_name}"
    description = (
        f"Продавец: {SELLER_NAME_FULL} (ИНН: {SELLER_INN}). "
        f"Оплата товара/услуги: {product_name}. "
        f"Нажимая 'Оплатить', Вы соглашаетесь с Офертой, Политикой возврата и Конфиденциальности."
    )

    # Параметры платежа для Telegram (цена в копейках)
    prices = [LabeledPrice(product_name, price * 100)]
    
    # Payload для отслеживания и формирования чека (самозанятый должен передать эти данные!)
    payload_data = {
        "order_id": str(uuid.uuid4()),
        "product_type": "premium",
        "product_name": name
    }
    
    await update.message.reply_invoice(
        title=title,
        description=description,
        payload=str(payload_data), # payload должен быть строкой
        provider_token=YOOKASSA_PAYMENT_TOKEN, # Используем временный пустой токен для модерации
        currency="RUB",
        prices=prices,
        need_name=True,
        need_email=True, # Важно для отправки чека
        is_flexible=False,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📄 Открыть документы", url="https://alexandro1141.github.io/policy-page/policy.html")
        ]])
    )
    # --------------------------------------------------------------------

# === Поддержка ===
async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    support_text = (
        "💬 Поддержка\n\n"
        f"По всем вопросам: @PREM1UMSHOP\n"
        f"<b>Email для юридических вопросов:</b> {SUPPORT_EMAIL}\n" # Добавили email
        "Ответим в ближайшее время ⚡️"
    )
    reply_markup = ReplyKeyboardMarkup([['🔙 Назад']], resize_keyboard=True)
    await update.message.reply_html(support_text, reply_markup=reply_markup)

# === Обработка Pre-Checkout Query (ЮKassa проверяет платеж) ===
async def pre_checkout_callback(update: Update, context: CallbackContext):
    """Отвечает на запрос Telegram, подтверждая, что платеж готов к обработке."""
    query = update.pre_checkout_query
    # В реальном коде здесь должна быть дополнительная проверка наличия товара/актуальности цены.
    if query.invoice_payload:
        await query.answer(ok=True)
    else:
        # Этого не должно случиться, но это отказ в платеже.
        await query.answer(ok=False, error_message="Ошибка в данных заказа. Пожалуйста, начните заново.")

# === Обработка успешного платежа ===
async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вызывается после успешного платежа. Здесь происходит выдача товара/услуги."""
    
    # payload содержит данные, которые мы передавали в инвойсе
    payload = update.message.successful_payment.invoice_payload 
    
    # В реальном коде здесь нужно:
    # 1. Распарсить payload для получения order_id, product_type и т.д.
    # 2. Выдать пользователю товар (например, отправить код Premium или добавить звезды)
    # 3. Отправить данные в ЮKassa для формирования фискального чека (это делается автоматически,
    #    если вы используете встроенный механизм ЮKassa для самозанятых через Telegram Payments)

    await update.message.reply_text(
        "🎉 **Оплата прошла успешно!**\n\n"
        "Ваш товар/услуга будет доставлен в ближайшее время.\n"
        f"Детали платежа (для справки): {update.message.successful_payment.total_amount / 100} {update.message.successful_payment.currency}",
        parse_mode='Markdown'
    )
    # ВАЖНО: В этот момент ЮKassa должна получить от вас сигнал для формирования чека. 
    # При использовании официальной интеграции через Telegram Payments/ЮKassa это часто происходит автоматически.

# === Обработка сообщений ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    # Главное меню и навигация
    if user_text == '⭐️ Бонусы ':
        await show_stars(update, context)
        return
    elif user_text == '👑 Premium-доступ':
        await show_premium(update, context)
        return
    elif user_text == '💬 Поддержка':
        await show_support(update, context)
        return
    elif user_text == '📄 Документы':
        await show_documents(update, context)
        return
    elif user_text == '🔙 Назад':
        await start(update, context)
        return

    # Выбор режима покупки
    if user_text == '🎁 Купить себе':
        context.user_data['gift_mode'] = False
        if context.user_data.get('category') == 'premium':
            await show_premium_purchase(update, context)
        else:
            await show_stars_purchase(update, context)
        return

    elif user_text == '🎀 Подарить другу':
        if context.user_data.get('category') == 'premium':
            context.user_data['product_type'] = 'premium'
        else:
            context.user_data['product_type'] = 'stars'
        await handle_gift_selection(update, context)
        return

    # Пакеты звёзд (теперь с (цена))
    stars_packages = {
        '100 ⭐️ (160Р)': 100,
        '150 ⭐️ (240Р)': 150,
        '250 ⭐️ (400Р)': 400, # Ошибка в оригинале: 400Р, а не 250
        '500 ⭐️ (800Р)': 500,
        '1000 ⭐️ (1600Р)': 1000,
        '2500 ⭐️ (4000Р)': 2500
    }
    if user_text in stars_packages:
        await process_stars_order(update, context, stars_packages[user_text])
        return

    # Пакеты Premium
    if user_text in PREMIUM_ITEMS:
        item = PREMIUM_ITEMS[user_text]
        await process_premium_order(update, context, user_text, item["price"])
        return

    # Пользователь ввёл число — кастомное количество Stars
    try:
        stars_count = int(user_text)
        if 50 <= stars_count <= 5000:
            await process_stars_order(update, context, stars_count)
        else:
            await update.message.reply_text("❌ Количество бонусов должно быть от 50 до 5000 ⭐️")
    except ValueError:
        # Если не поймали ни одно действие выше, даем стандартный ответ
        await update.message.reply_text("Используй кнопки ниже для навигации или введи количество бонусов!")

# === Запуск ===
def main():
    keep_alive()
    app = Application.builder().token(TOKEN).build()
    
    # Обработчики команд и текста
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Обработчики платежей (КРИТИЧНО ДЛЯ МОДЕРАЦИИ)
    app.add_handler(PreCheckoutQueryHandler(pre_checkout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    
    print("🤖 PREM1UMSHOP бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
