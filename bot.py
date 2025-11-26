import logging
import uuid
import requests

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from keep_alive import keep_alive

# === Токен бота ===
TOKEN = "8392743023:AAHjApwBpmoapx7NA3KW25iGmBITUvuOnDQ"

# === Данные ЮKassa (ТЕСТОВЫЙ режим) ===
YOOKASSA_SHOP_ID = "1115508896"
YOOKASSA_SECRET_KEY = "test_gDWtGRLQJ8kDWwo4Zy3eJ8L2w3ysuccHcPqpPDOyorxw"
YOOKASSA_API_URL = "https://api.yookassa.ru/v3/payments"

# === Логирование ===
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# === Каталог Premium (глобально, чтобы использовать в нескольких местах) ===
PREMIUM_ITEMS = {
    "💎 3 месяца": {"name": "💎 3 месяца", "price": 1200},
    "🚀 6 месяцев": {"name": "🚀 6 месяцев", "price": 1500},
    "👑 12 месяцев": {"name": "👑 12 месяцев", "price": 2500},
}


# === Вспомогательная функция: создать платёж в ЮKassa ===
def create_payment(amount_rub: int, description: str, return_url: str = "https://t.me/prem1umshop_star_bot"):
    """
    Создаём платёж в ЮKassa и возвращаем JSON-ответ.
    amount_rub — сумма в рублях (int).
    """
    headers = {
        "Idempotence-Key": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }

    payload = {
        "amount": {
            "value": f"{amount_rub:.2f}",
            "currency": "RUB"
        },
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": return_url
        },
        "description": description
    }

    try:
        resp = requests.post(
            YOOKASSA_API_URL,
            auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
            json=payload,
            headers=headers,
            timeout=15
        )
        data = resp.json()
        if resp.status_code not in (200, 201):
            logging.error("YooKassa error %s: %s", resp.status_code, data)
            return None
        return data
    except Exception as e:
        logging.exception("YooKassa request failed: %s", e)
        return None


# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    context.user_data.clear()

    keyboard = [
        ['⭐️ Telegram Stars', '👑 Telegram Premium'],
        ['ℹ️ О сервисе', '📄 Документы'],
        ['💬 Поддержка']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_html(
        f"🚀 <b>Добро пожаловать в PREM1UMSHOP!</b> {user.mention_html()}!\n\n"
        "🎯 <b>Покупай Telegram Stars и Telegram Premium по лучшим ценам!</b>\n\n"
        "<b>Выбери категорию:</b>",
        reply_markup=reply_markup
    )

# === Telegram Stars ===
async def show_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data['category'] = 'stars'

    stars_info = "⭐️ Telegram Stars\n\n🎉 Выбери вариант покупки:"
    keyboard = [['🎁 Купить себе', '🎀 Подарить другу'], ['🔙 Назад']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(stars_info, reply_markup=reply_markup)

# === Telegram Premium ===
async def show_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data['category'] = 'premium'

    premium_info = "👑 Telegram Premium\n\n🎉 Выбери вариант покупки:"
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

# === Показ соглашения ===
async def show_agreement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["agreement_shown"] = True

    agreement_text = (
        "📄 <b>Пользовательское соглашение PREM1UMSHOP</b>\n\n"
        "Перед оплатой ознакомьтесь с документами:\n"
        "• Публичная оферта\n"
        "• Политика возврата\n"
        "• Политика конфиденциальности\n\n"
        "🔗 <a href='https://alexandro1141.github.io/policy-page/policy.html'>Открыть соглашение</a>\n\n"
        "Если вы согласны со всеми условиями, нажмите <b>«✅ Я согласен»</b> для продолжения."
    )

    keyboard = [['✅ Я согласен'], ['🔙 Назад']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_html(agreement_text, reply_markup=reply_markup)

# === Подтверждение согласия ===
async def handle_agreement_consent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["agreement_accepted"] = True

    if "pending_order" in context.user_data:
        order_data = context.user_data["pending_order"]
        if order_data["type"] == "stars":
            await process_stars_order(update, context, order_data["count"], bypass_agreement=True)
        elif order_data["type"] == "premium":
            await process_premium_order(update, context, order_data["name"], order_data["price"], bypass_agreement=True)
        del context.user_data["pending_order"]
    else:
        await update.message.reply_text("✅ Соглашение принято.\n💳 Оплата скоро будет доступна!")

# === Покупка Stars ===
async def show_stars_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stars_info = "🎉 Для покупки звёзд выбери пакет или отправь своё количество (от 50 до 5000 ⭐️)"
    if context.user_data.get('gift_mode') and context.user_data.get('gift_username'):
        stars_info = f"🎁 Подарок для {context.user_data['gift_username']}\n\n" + stars_info

    keyboard = [
        ['100 ⭐️ - 160Р', '150 ⭐️ - 240Р'],
        ['250 ⭐️ - 400Р', '500 ⭐️ - 800Р'],
        ['1000 ⭐️ - 1600Р', '2500 ⭐️ - 4000Р'],
        ['🔙 Назад']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(stars_info, reply_markup=reply_markup)

# === Проверка соглашения (Stars) + создание платежа ===
async def process_stars_order(update: Update, context: ContextTypes.DEFAULT_TYPE, stars_count: int, bypass_agreement=False):
    price = int(stars_count * 1.6)  # курс 1 звезда = 1.6 руб

    if not bypass_agreement and not context.user_data.get("agreement_accepted"):
        context.user_data["pending_order"] = {"type": "stars", "count": stars_count}
        await show_agreement(update, context)
        return

    description = f"{stars_count} Telegram Stars для пользователя {update.effective_user.id}"
    payment = create_payment(price, description)

    if not payment or "confirmation" not in payment:
        await update.message.reply_text(
            "⚠ Сейчас оплата временно недоступна. Попробуйте позже или напишите в поддержку: @PREM1UMSHOP"
        )
        return

    pay_url = payment["confirmation"]["confirmation_url"]

    msg = (
        f"🎉 Отличный выбор!\n\n"
        f"Товар: {stars_count} Telegram Stars ⭐️\n"
        f"Цена: {price} руб.\n\n"
        f"🔗 <b>Ссылка на оплату (ЮKassa):</b>\n{pay_url}\n\n"
        "После успешной оплаты мы обработаем ваш заказ в ближайшее время."
    )
    await update.message.reply_html(msg)

# === Покупка Premium (каталог и выбор) ===
async def show_premium_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    catalog_text = "👑 Telegram Premium:\n\n"
    for item in PREMIUM_ITEMS.values():
        catalog_text += f"• {item['name']}\n💰 Цена: {item['price']} руб.\n\n"

    if context.user_data.get('gift_mode') and context.user_data.get('gift_username'):
        catalog_text = f"🎁 Подарок для {context.user_data['gift_username']}\n\n" + catalog_text

    keyboard = [['💎 3 месяца', '🚀 6 месяцев'], ['👑 12 месяцев', '🔙 Назад']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(catalog_text, reply_markup=reply_markup)

# === Проверка соглашения (Premium) + создание платежа ===
async def process_premium_order(update: Update, context: ContextTypes.DEFAULT_TYPE, name: str, price: int, bypass_agreement=False):
    if not bypass_agreement and not context.user_data.get("agreement_accepted"):
        context.user_data["pending_order"] = {"type": "premium", "name": name, "price": price}
        await show_agreement(update, context)
        return

    description = f"{name} Telegram Premium для пользователя {update.effective_user.id}"
    payment = create_payment(price, description)

    if not payment or "confirmation" not in payment:
        await update.message.reply_text(
            "⚠ Сейчас оплата временно недоступна. Попробуйте позже или напишите в поддержку: @PREM1UMSHOP"
        )
        return

    pay_url = payment["confirmation"]["confirmation_url"]

    msg = (
        "🎉 Отличный выбор!\n\n"
        f"Товар: {name}\n"
        f"Цена: {price} руб.\n\n"
        f"🔗 <b>Ссылка на оплату (ЮKassa):</b>\n{pay_url}\n\n"
        "После успешной оплаты мы обработаем ваш заказ в ближайшее время."
    )
    await update.message.reply_html(msg)

# === Поддержка ===
async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    support_text = (
        "💬 Поддержка\n\n"
        "По всем вопросам: @PREM1UMSHOP\n"
        "Ответим в ближайшее время ⚡️"
    )
    reply_markup = ReplyKeyboardMarkup([['🔙 Назад']], resize_keyboard=True)
    await update.message.reply_text(support_text, reply_markup=reply_markup)

# === О сервисе ===
async def show_service_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ <b>О сервисе PREM1UMSHOP</b>\n\n"
        "Мы продаём цифровые товары:\n"
        "• Telegram Stars\n"
        "• Telegram Premium (3–12 месяцев)\n\n"
        "После оплаты заказ обрабатывается в течение 5–120 минут.\n"
        "В исключительных случаях срок может быть увеличен до 48 часов.\n\n"
        "📍 <b>Продавец:</b>\n"
        "Физическое лицо — самозанятый РФ (НПД)\n"
        "ФИО: Алекс Алексанян Гайкович\n"
        "ИНН: <b>502993268720</b>\n"
        "Город: <b>Мытищи</b>\n\n"
        "💳 Оплата обрабатывается через платёжный сервис ЮKassa.\n"
        "Данные банковской карты передаются по защищённым каналам.\n\n"
        "По всем вопросам: @PREM1UMSHOP\n"
        "Email: prem1umshoptelegram@mail.ru"
    )
    reply_markup = ReplyKeyboardMarkup([
        ['⭐️ Telegram Stars', '👑 Telegram Premium'],
        ['ℹ️ О сервисе', '📄 Документы'],
        ['💬 Поддержка']
    ], resize_keyboard=True)
    await update.message.reply_html(text, reply_markup=reply_markup)

# === Документы ===
async def show_documents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📄 <b>Документы сервиса PREM1UMSHOP</b>\n\n"
        "Выберите документ, чтобы ознакомиться:\n"
        "• 📘 Публичная оферта\n"
        "• 📗 Политика возврата денежных средств\n"
        "• 🔐 Политика конфиденциальности"
    )
    keyboard = [
        ['📘 Публичная оферта'],
        ['📗 Политика возврата'],
        ['🔐 Политика конфиденциальности'],
        ['🔙 Назад']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_html(text, reply_markup=reply_markup)

# === Публичная оферта ===
async def show_offer_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📘 <b>Публичная оферта</b>\n\n"
        "Настоящий документ является публичной офертой физического лица\n"
        "Алекса Алексаняна Гайковича (ИНН: 502993268720, статус — самозанятый РФ),\n"
        "далее — «Продавец», заключить договор купли-продажи цифровых товаров\n"
        "с любым лицом, осуществившим оплату через Telegram-бот PREM1UMSHOP (@prem1umshop_star_bot).\n\n"
        "<b>1. Предмет договора</b>\n"
        "Продавец осуществляет продажу цифровых товаров:\n"
        "• Telegram Stars\n"
        "• Telegram Premium\n\n"
        "<b>2. Порядок оплаты</b>\n"
        "Оплата производится безналичным способом через платёжный сервис ЮKassa.\n"
        "Момент успешной оплаты является моментом акцепта настоящей оферты.\n\n"
        "<b>3. Оказание услуги</b>\n"
        "Цифровой товар предоставляется на указанный пользователем Telegram-аккаунт\n"
        "в срок от 5 минут до 48 часов с момента оплаты.\n\n"
        "<b>4. Права и обязанности сторон</b>\n"
        "Продавец обязуется предоставить оплаченный товар в заявленный срок.\n"
        "Покупатель обязуется указать корректные данные для получения товара.\n\n"
        "<b>5. Возврат средств</b>\n"
        "Условия возврата денежных средств определяются «Политикой возврата денежных средств».\n\n"
        "<b>6. Контакты</b>\n"
        "Поддержка: @PREM1UMSHOP\n"
        "Email: prem1umshoptelegram@mail.ru"
    )
    await update.message.reply_html(text)

# === Политика возврата ===
async def show_refund_policy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📗 <b>Политика возврата денежных средств</b>\n\n"
        "Возврат денежных средств возможен в следующих случаях:\n"
        "• оплаченный товар не был предоставлен в течение 48 часов по вине магазина;\n"
        "• цифровой товар не может быть предоставлен по техническим причинам со стороны Продавца.\n\n"
        "Возврат средств НЕ осуществляется, если:\n"
        "• покупатель указал неверный ник/Telegram-аккаунт;\n"
        "• товар был успешно предоставлен (звёзды зачислены / Premium активирован);\n"
        "• покупатель передумал после получения товара.\n\n"
        "Срок рассмотрения обращения на возврат — до 72 часов.\n"
        "В случае одобрения возврат производится на тот же способ оплаты,\n"
        "который использовался при покупке, либо по согласованию — на внутренний баланс.\n\n"
        "Поддержка по вопросам возврата: @PREM1UMSHOP"
    )
    await update.message.reply_html(text)

# === Политика конфиденциальности ===
async def show_privacy_policy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🔐 <b>Политика конфиденциальности</b>\n\n"
        "Telegram-бот PREM1UMSHOP обрабатывает следующие данные:\n"
        "• Telegram ID пользователя;\n"
        "• username и отображаемое имя;\n"
        "• информацию о заказах и платежах (без реквизитов банковской карты).\n\n"
        "Данные используются исключительно для оформления и выполнения заказов,\n"
        "а также для решения вопросов поддержки.\n\n"
        "Данные не передаются третьим лицам, за исключением случаев,\n"
        "предусмотренных законодательством РФ и необходимых для обработки платежей.\n\n"
        "Пользователь может запросить удаление своих данных, обратившись в поддержку: @PREM1UMSHOP"
    )
    await update.message.reply_html(text)

# === Обработка сообщений ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    if user_text == '⭐️ Telegram Stars':
        await show_stars(update, context)
        return
    elif user_text == '👑 Telegram Premium':
        await show_premium(update, context)
        return
    elif user_text == '💬 Поддержка':
        await show_support(update, context)
        return
    elif user_text == 'ℹ️ О сервисе':
        await show_service_info(update, context)
        return
    elif user_text == '📄 Документы':
        await show_documents(update, context)
        return
    elif user_text == '📘 Публичная оферта':
        await show_offer_doc(update, context)
        return
    elif user_text == '📗 Политика возврата':
        await show_refund_policy(update, context)
        return
    elif user_text == '🔐 Политика конфиденциальности':
        await show_privacy_policy(update, context)
        return
    elif user_text == '🔙 Назад':
        await start(update, context)
        return

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

    # Ввод @username для подарка
    if context.user_data.get('gift_mode') and not context.user_data.get('gift_username'):
        username = user_text.strip()

        if not username.startswith('@') or ' ' in username:
            await update.message.reply_text("❌ Введите ник в формате @username, без пробелов.")
            return

        context.user_data['gift_username'] = username

        if context.user_data.get('product_type') == 'premium':
            await show_premium_purchase(update, context)
        else:
            await show_stars_purchase(update, context)
        return

    # Пакеты звёзд
    star_packages = {
        '100 ⭐️ - 160Р': 100,
        '150 ⭐️ - 240Р': 150,
        '250 ⭐️ - 400Р': 250,
        '500 ⭐️ - 800Р': 500,
        '1000 ⭐️ - 1600Р': 1000,
        '2500 ⭐️ - 4000Р': 2500
    }
    if user_text in star_packages:
        await process_stars_order(update, context, star_packages[user_text])
        return

    # Пакеты Premium
    if user_text in PREMIUM_ITEMS:
        item = PREMIUM_ITEMS[user_text]
        await process_premium_order(update, context, item["name"], item["price"])
        return

    # Пользователь ввёл число — кастомное количество Stars
    try:
        stars_count = int(user_text)
        if stars_count < 50:
            await update.message.reply_text("❌ Минимум 50 звёзд.")
        elif stars_count > 5000:
            await update.message.reply_text("❌ Максимум 5000 звёзд.")
        else:
            await process_stars_order(update, context, stars_count)
    except ValueError:
        await update.message.reply_text("Используй кнопки ниже для навигации!")

# === Запуск ===
def main():
    keep_alive()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex('^✅ Я согласен$'), handle_agreement_consent))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 PREM1UMSHOP бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
