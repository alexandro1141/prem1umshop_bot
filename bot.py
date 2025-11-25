import logging

from telegram import Update, ReplyKeyboardMarkup

from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

from keep_alive import keep_alive



# === Токен бота ===

TOKEN = "8392743023:AAHjApwBpmoapx7NA3KW25iGmBITUvuOnDQ"



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



# === Команда /start ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    context.user_data.clear()



    keyboard = [

        ['⭐️ Telegram Stars', '👑 Telegram Premium'],

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



# === Проверка соглашения (Stars) ===

async def process_stars_order(update: Update, context: ContextTypes.DEFAULT_TYPE, stars_count: int, bypass_agreement=False):

    price = int(stars_count * 1.6)  # курс 1 звезда = 1.6 руб



    if not bypass_agreement and not context.user_data.get("agreement_accepted"):

        context.user_data["pending_order"] = {"type": "stars", "count": stars_count}

        await show_agreement(update, context)

        return



    msg = (

        f"🎉 Отличный выбор!\n\n"

        f"Товар: {stars_count} Telegram Stars ⭐️\n"

        f"Цена: {price} руб.\n\n"

        f"💳 Оплата скоро будет доступна!"

    )

    await update.message.reply_text(msg)



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



# === Проверка соглашения (Premium) ===

async def process_premium_order(update: Update, context: ContextTypes.DEFAULT_TYPE, name: str, price: int, bypass_agreement=False):

    if not bypass_agreement and not context.user_data.get("agreement_accepted"):

        # Запоминаем заказ и показываем соглашение

        context.user_data["pending_order"] = {"type": "premium", "name": name, "price": price}

        await show_agreement(update, context)

        return



    msg = (

        "🎉 Отличный выбор!\n\n"

        f"Товар: {name}\n"

        f"Цена: {price} руб.\n\n"

        "💳 Оплата скоро будет доступна!"

    )

    await update.message.reply_text(msg)



# === Поддержка ===

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):

    support_text = (

        "💬 Поддержка\n\n"

        "По всем вопросам: @PREM1UMSHOP\n"

        "Ответим в ближайшее время ⚡️"

    )

    reply_markup = ReplyKeyboardMarkup([['🔙 Назад']], resize_keyboard=True)

    await update.message.reply_text(support_text, reply_markup=reply_markup)



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
