import uuid
import requests
import logging
import json
import hmac
import hashlib

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from keep_alive import keep_alive

# === Токен бота ===
TOKEN = "8496640654:AAGIfAbZivdDPH1mbNSlENWHyXfDIgpJKaM"

# === LAVA (Business) ===
LAVA_SHOP_ID = "aabbaa06-325c-4b48-8d32-beccba983642"  # ID проекта (shopId)
LAVA_SECRET_KEY = "293e78a4d1743afadbfcfc2ff35bbc0a5db44981"  # Секретный ключ
LAVA_INVOICE_URL = "https://api.lava.ru/business/invoice/create"

# === Логирование ===
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# === Каталог Premium ===
PREMIUM_ITEMS = {
    "💎 3 месяца": {"name": "💎 3 месяца", "price": 1200},
    "🚀 6 месяцев": {"name": "🚀 6 месяцев", "price": 1500},
    "👑 12 месяцев": {"name": "👑 12 месяцев", "price": 2500},
}


# === Создание инвойса в LAVA ===
def create_lava_invoice(amount_rub: int, description: str, return_url: str) -> str | None:
    """
    Создаём счёт в LAVA и возвращаем ссылку на оплату.
    Документация:
    POST https://api.lava.ru/business/invoice/create
    Поля: sum, orderId, shopId, successUrl, failUrl, comment, ...
    Подпись: HMAC-SHA256(json_body, secret_key) в заголовке Signature
    """

    # Генерируем уникальный orderId
    order_id = str(uuid.uuid4())

    # Тело запроса
    payload = {
        "sum": float(f"{amount_rub:.2f}"),  # LAVA ждёт float
        "orderId": order_id,
        "shopId": LAVA_SHOP_ID,
        "successUrl": return_url,
        "failUrl": return_url,
        "comment": description,
        # "hookUrl": "...",  # если будешь делать вебхуки — сюда URL твоего обработчика
    }

    # Сериализация JSON строго в том виде, который подписываем
    json_body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    # Подпись HMAC-SHA256(JSON, secret_key)
    signature = hmac.new(
        LAVA_SECRET_KEY.encode("utf-8"),
        msg=json_body.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Signature": signature,
    }

    try:
        resp = requests.post(
            LAVA_INVOICE_URL,
            data=json_body.encode("utf-8"),  # data-raw JSON
            headers=headers,
            timeout=15,
        )

        if resp.status_code != 200:
            logging.error("LAVA error %s: %s", resp.status_code, resp.text)
            return None

        data = resp.json()
        # Ожидаем, что реальный URL счета лежит в data / invoice и т.п.
        invoice_data = data.get("data") or data.get("invoice") or data

        pay_url = None
        if isinstance(invoice_data, dict):
            # Пробуем несколько распространённых ключей
            for key in ("url", "URL", "payUrl", "payment_url", "paymentUrl"):
                if key in invoice_data and invoice_data[key]:
                    pay_url = invoice_data[key]
                    break

        if not pay_url:
            logging.error("Не удалось найти URL оплаты в ответе LAVA: %s", data)
            return None

        return pay_url

    except Exception as e:
        logging.exception("LAVA create_invoice exception: %s", e)
        return None


# === /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    context.user_data.clear()

    keyboard = [
        ["⭐️ Telegram Stars", "👑 Telegram Premium"],
        ["💬 Поддержка", "ℹ О сервисе"],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_html(
        f"🚀 <b>Добро пожаловать в PREM1UMSHOP!</b> {user.mention_html()}!\n\n"
        "🎯 <b>Покупай Telegram Stars и Telegram Premium по лучшим ценам!</b>\n\n"
        "<b>Выбери категорию:</b>",
        reply_markup=reply_markup,
    )


# === О сервисе и документы ===
async def show_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ <b>О сервисе PREM1UMSHOP</b>\n\n"
        "PREM1UMSHOP (@prem1umshop_star_bot) — сервис по продаже Telegram Stars "
        "и Telegram Premium.\n\n"
        "<b>Документы сервиса:</b>\n"
        "• Политика возврата денежных средств\n"
        "• Публичная оферта\n"
        "• Политика конфиденциальности\n\n"
        "Полные тексты документов доступны по ссылке:\n"
        "🔗 <a href='https://alexandro1141.github.io/policy-page/policy.html'>"
        "Открыть документы сервиса</a>\n\n"
        "<b>Реквизиты продавца:</b>\n"
        "Физическое лицо: Алекс Алексанян Гайкович\n"
        "ИНН: 502993268720\n"
        "Город: Мытищи\n"
        "Email: prem1umshoptelegram@mail.ru\n\n"
        "<b>Поддержка:</b> @PREM1UMSHOP"
    )

    reply_markup = ReplyKeyboardMarkup([["🔙 Назад"]], resize_keyboard=True)
    await update.message.reply_html(text, reply_markup=reply_markup)


# === Stars ===
async def show_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["category"] = "stars"

    stars_info = "⭐️ Telegram Stars\n\n🎉 Выбери вариант покупки:"
    keyboard = [["🎁 Купить себе", "🎀 Подарить другу"], ["🔙 Назад"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(stars_info, reply_markup=reply_markup)


# === Premium ===
async def show_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["category"] = "premium"

    premium_info = "👑 Telegram Premium\n\n🎉 Выбери вариант покупки:"
    keyboard = [["🎁 Купить себе", "🎀 Подарить другу"], ["🔙 Назад"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(premium_info, reply_markup=reply_markup)


# === Подарок другу: запрос юзернейма ===
async def handle_gift_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["gift_mode"] = True
    gift_info = (
        "🎀 <b>Подарок другу</b>\n\n"
        "Введите имя пользователя получателя:\n\n"
        "Например: <code>@username</code>"
    )
    keyboard = [["🔙 Назад"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_html(gift_info, reply_markup=reply_markup)


# === Соглашение ===
async def show_agreement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["agreement_shown"] = True

    agreement_text = (
        "📄 <b>Пользовательское соглашение PREM1UMSHOP</b>\n\n"
        "Перед оплатой ознакомьтесь с документами:\n"
        "• Публичная оферта\n"
        "• Политика возврата\n"
        "• Политика конфиденциальности\n\n"
        "🔗 <a href='https://alexandro1141.github.io/policy-page/policy.html'>"
        "Открыть соглашение и документы</a>\n\n"
        "Если вы согласны со всеми условиями, нажмите <b>«✅ Я согласен»</b> для продолжения."
    )

    keyboard = [["✅ Я согласен"], ["🔙 Назад"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_html(agreement_text, reply_markup=reply_markup)


# === Подтверждение согласия ===
async def handle_agreement_consent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["agreement_accepted"] = True

    if "pending_order" in context.user_data:
        order_data = context.user_data["pending_order"]
        if order_data["type"] == "stars":
            await process_stars_order(
                update, context, order_data["count"], bypass_agreement=True
            )
        elif order_data["type"] == "premium":
            await process_premium_order(
                update,
                context,
                order_data["name"],
                order_data["price"],
                bypass_agreement=True,
            )
        del context.user_data["pending_order"]
    else:
        await update.message.reply_text(
            "✅ Соглашение принято.\n💳 Оплата скоро будет доступна!"
        )


# === Выбор пакета Stars ===
async def show_stars_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stars_info = (
        "🎉 Для покупки звёзд выбери пакет или отправь своё количество "
        "(от 50 до 5000 ⭐️)"
    )
    if context.user_data.get("gift_mode") and context.user_data.get("gift_username"):
        stars_info = (
            f"🎁 Подарок для {context.user_data['gift_username']}\n\n" + stars_info
        )

    keyboard = [
        ["100 ⭐️ - 160Р", "150 ⭐️ - 240Р"],
        ["250 ⭐️ - 400Р", "500 ⭐️ - 800Р"],
        ["1000 ⭐️ - 1600Р", "2500 ⭐️ - 4000Р"],
        ["🔙 Назад"],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(stars_info, reply_markup=reply_markup)


# === Создание платежа Stars через LAVA ===
async def process_stars_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    stars_count: int,
    bypass_agreement: bool = False,
):
    price = int(stars_count * 1.6)

    if not bypass_agreement and not context.user_data.get("agreement_accepted"):
        context.user_data["pending_order"] = {"type": "stars", "count": stars_count}
        await show_agreement(update, context)
        return

    description = f"{stars_count} Telegram Stars для {update.effective_user.id}"
    return_url = "https://t.me/prem1umshop_star_bot"

    payment_url = create_lava_invoice(price, description, return_url)
    if not payment_url:
        await update.message.reply_text(
            "⚠️ Не удалось сформировать ссылку на оплату.\n"
            "Попробуйте ещё раз чуть позже или напишите в поддержку: @PREM1UMSHOP"
        )
        return

    msg = (
        "🎉 Отличный выбор!\n\n"
        f"Товар: {stars_count} Telegram Stars ⭐️\n"
        f"Цена: {price} ₽\n\n"
        "Нажми кнопку ниже, чтобы перейти к оплате."
    )

    pay_inline_kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("💳 ОПЛАТИТЬ", url=payment_url)]]
    )
    await update.message.reply_text(msg, reply_markup=pay_inline_kb)

    nav_kb = ReplyKeyboardMarkup(
        [["✅ Я оплатил", "❌ Отмена"]],
        resize_keyboard=True,
    )
    await update.message.reply_text(
        "После оплаты нажми «✅ Я оплатил» или «❌ Отмена».",
        reply_markup=nav_kb,
    )

    context.user_data["waiting_payment"] = True
    context.user_data["last_order"] = {
        "type": "stars",
        "stars_count": stars_count,
        "price": price,
        "payment_url": payment_url,
    }


# === Выбор тарифа Premium ===
async def show_premium_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    catalog_text = "👑 Telegram Premium:\n\n"
    for item in PREMIUM_ITEMS.values():
        catalog_text += f"• {item['name']}\n💰 Цена: {item['price']} руб.\n\n"

    if context.user_data.get("gift_mode") and context.user_data.get("gift_username"):
        catalog_text = (
            f"🎁 Подарок для {context.user_data['gift_username']}\n\n" + catalog_text
        )

    keyboard = [["💎 3 месяца", "🚀 6 месяцев"], ["👑 12 месяцев", "🔙 Назад"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(catalog_text, reply_markup=reply_markup)


# === Создание платежа Premium через LAVA ===
async def process_premium_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    name: str,
    price: int,
    bypass_agreement: bool = False,
):
    if not bypass_agreement and not context.user_data.get("agreement_accepted"):
        context.user_data["pending_order"] = {
            "type": "premium",
            "name": name,
            "price": price,
        }
        await show_agreement(update, context)
        return

    description = f"{name} Telegram Premium для {update.effective_user.id}"
    return_url = "https://t.me/prem1umshop_star_bot"

    payment_url = create_lava_invoice(price, description, return_url)
    if not payment_url:
        await update.message.reply_text(
            "⚠️ Не удалось сформировать ссылку на оплату.\n"
            "Попробуйте ещё раз чуть позже или напишите в поддержку: @PREM1UMSHOP"
        )
        return

    msg = (
        "🎉 Отличный выбор!\n\n"
        f"Товар: {name}\n"
        f"Цена: {price} ₽\n\n"
        "Нажми кнопку ниже, чтобы перейти к оплате."
    )

    pay_inline_kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("💳 ОПЛАТИТЬ", url=payment_url)]]
    )
    await update.message.reply_text(msg, reply_markup=pay_inline_kb)

    nav_kb = ReplyKeyboardMarkup(
        [["✅ Я оплатил", "❌ Отмена"]],
        resize_keyboard=True,
    )
    await update.message.reply_text(
        "После оплаты нажми «✅ Я оплатил» или «❌ Отмена».",
        reply_markup=nav_kb,
    )

    context.user_data["waiting_payment"] = True
    context.user_data["last_order"] = {
        "type": "premium",
        "name": name,
        "price": price,
        "payment_url": payment_url,
    }


# === Поддержка ===
async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    support_text = (
        "💬 Поддержка\n\n"
        "По всем вопросам: @PREM1UMSHOP\n"
        "Ответим в ближайшее время ⚡️"
    )
    reply_markup = ReplyKeyboardMarkup([["🔙 Назад"]], resize_keyboard=True)
    await update.message.reply_text(support_text, reply_markup=reply_markup)


# === Обработка всех сообщений ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    # Главное меню
    if user_text == "⭐️ Telegram Stars":
        await show_stars(update, context)
        return
    elif user_text == "👑 Telegram Premium":
        await show_premium(update, context)
        return
    elif user_text == "💬 Поддержка":
        await show_support(update, context)
        return
    elif user_text == "ℹ О сервисе":
        await show_about(update, context)
        return
    elif user_text == "🔙 Назад":
        await start(update, context)
        return

    # Стадия оплаты
    if user_text == "✅ Я оплатил":
        await update.message.reply_text(
            "✅ Спасибо! Если платёж прошёл, заказ будет обработан в ближайшее время.\n"
            "Если что-то пошло не так, напишите в поддержку: @PREM1UMSHOP"
        )
        context.user_data.pop("waiting_payment", None)
        context.user_data.pop("last_order", None)
        await start(update, context)
        return

    if user_text == "❌ Отмена":
        await update.message.reply_text("❌ Оплата отменена. Возвращаю в главное меню.")
        context.user_data.pop("waiting_payment", None)
        context.user_data.pop("last_order", None)
        await start(update, context)
        return

    # Ввод юзернейма для подарка
    if context.user_data.get("gift_mode") and not context.user_data.get(
        "gift_username"
    ):
        username = user_text.strip()
        if not username.startswith("@"):
            username = "@" + username

        context.user_data["gift_username"] = username

        # Определяем, что дарим — Stars или Premium
        if context.user_data.get("product_type") == "premium" or context.user_data.get(
            "category"
        ) == "premium":
            await show_premium_purchase(update, context)
        else:
            await show_stars_purchase(update, context)
        return

    # Выбор «купить себе / подарить другу»
    if user_text == "🎁 Купить себе":
        context.user_data["gift_mode"] = False
        context.user_data["gift_username"] = None
        if context.user_data.get("category") == "premium":
            await show_premium_purchase(update, context)
        else:
            await show_stars_purchase(update, context)
        return

    if user_text == "🎀 Подарить другу":
        if context.user_data.get("category") == "premium":
            context.user_data["product_type"] = "premium"
        else:
            context.user_data["product_type"] = "stars"
        await handle_gift_selection(update, context)
        return

    # Пакеты звёзд
    star_packages = {
        "100 ⭐️ - 160Р": 100,
        "150 ⭐️ - 240Р": 150,
        "250 ⭐️ - 400Р": 250,
        "500 ⭐️ - 800Р": 500,
        "1000 ⭐️ - 1600Р": 1000,
        "2500 ⭐️ - 4000Р": 2500,
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
    app.add_handler(
        MessageHandler(filters.Regex("^✅ Я согласен$"), handle_agreement_consent)
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 PREM1UMSHOP бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
