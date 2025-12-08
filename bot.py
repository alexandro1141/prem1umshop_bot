import uuid
import requests
import logging
import json
import hmac
import hashlib
import threading
import os
import asyncio
from dotenv import load_dotenv

from flask import Flask, request

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

# === ЗАГРУЗКА ПЕРЕМЕННЫХ ИЗ ФАЙЛА .env ===
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
LAVA_SHOP_ID = os.getenv("LAVA_SHOP_ID")
LAVA_SECRET_KEY = os.getenv("LAVA_SECRET_KEY")
LAVA_WEBHOOK_SECRET = os.getenv("LAVA_WEBHOOK_SECRET")
ADMIN_CHAT_ID = os.getenv("ADMIN_ID")

# === ПРОВЕРКА КЛЮЧЕЙ ===
if not TOKEN or not LAVA_SECRET_KEY:
    print("❌ ОШИБКА: Не найдены ключи в файле .env!")
    print("Убедитесь, что вы создали файл .env и заполнили его.")
    exit()

LAVA_INVOICE_URL = "https://api.lava.ru/business/invoice/create"
LAVA_HOOK_URL = "http://95.181.224.199:8080/lava-webhook"

# === ФАЙЛ С ПОЛЬЗОВАТЕЛЯМИ (БАЗА ДАННЫХ) ===
USERS_FILE = "users.txt"

def save_user(chat_id):
    """Сохраняет ID пользователя в файл, если его там нет"""
    chat_id = str(chat_id)
    users = set()
    
    if not os.path.exists(USERS_FILE):
        open(USERS_FILE, 'w').close()
        
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            users = set(f.read().splitlines())
    
    if chat_id not in users:
        with open(USERS_FILE, "a") as f:
            f.write(chat_id + "\n")

# === НАСТРОЙКИ КАРТИНОК ===
IMG_DIR = "images"
IMG_MAIN_MENU = os.path.join(IMG_DIR, "ПлашкаБотПШ 1.png")
IMG_BUY_GIFT = os.path.join(IMG_DIR, "ПлашкаБотПШ 2.png")
IMG_STARS_AMOUNT = os.path.join(IMG_DIR, "ПлашкаБотПШ 3.png")
IMG_AGREEMENT = os.path.join(IMG_DIR, "ПлашкаБотПШ 4.png")
IMG_PAYMENT = os.path.join(IMG_DIR, "ПлашкаБотПШ 5.png")

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

# === Память заказов ===
ORDERS: dict[str, dict] = {}


# === LAVA API ===
def create_lava_invoice(amount_rub: int, description: str, return_url: str, order_id: str) -> str | None:
    payload = {
        "sum": float(f"{amount_rub:.2f}"),
        "orderId": order_id,
        "shopId": LAVA_SHOP_ID,
        "successUrl": return_url,
        "failUrl": return_url,
        "hookUrl": LAVA_HOOK_URL,
        "comment": description,
    }

    json_body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    signature = hmac.new(
        LAVA_SECRET_KEY.encode("utf-8"),
        msg=json_body.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    headers = {"Accept": "application/json", "Content-Type": "application/json", "Signature": signature}

    try:
        resp = requests.post(LAVA_INVOICE_URL, data=json_body.encode("utf-8"), headers=headers, timeout=15)
        if resp.status_code != 200:
            logging.error("LAVA error %s: %s", resp.status_code, resp.text)
            return None
        data = resp.json()
        invoice_data = data.get("data") or data.get("invoice") or data
        pay_url = None
        if isinstance(invoice_data, dict):
            for key in ("url", "URL", "payUrl", "payment_url", "paymentUrl"):
                if key in invoice_data and invoice_data[key]:
                    pay_url = invoice_data[key]
                    break
        return pay_url
    except Exception as e:
        logging.exception("LAVA create_invoice exception: %s", e)
        return None


# === Flask Webhook ===
flask_app = Flask(__name__)

@flask_app.route("/lava-webhook", methods=["POST"])
def lava_webhook():
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        return {"ok": False}, 400

    order_id = str(data.get("orderId") or data.get("order_id") or "").strip()
    status = str(data.get("status") or data.get("payment_status") or "").lower()
    
    success_statuses = {"success", "done", "paid", "completed", "succeeded"}
    is_success = status in success_statuses or bool(data.get("pay_time"))

    if not is_success:
        return {"ok": True}

    order = ORDERS.get(order_id)
    
    # Формируем сообщение админу
    text = f"💸 <b>ОПЛАТА LAVA</b>\nOrder: {order_id}\nStatus: {status}\n"
    if order:
        username = order.get("buyer_username")
        buyer_mention = f"@{username}" if username else f"id {order['buyer_id']}"
        gift_to = order.get("gift_to") or "самому себе"
        
        text += f"👤 <b>Кто купил:</b> {buyer_mention}\n"
        text += f"🎁 <b>Кому:</b> {gift_to}\n"
        
        if order['type'] == 'stars':
            text += f"⭐ Stars: {order['stars_count']}\n💰 {order['price']} RUB"
        else:
            text += f"👑 Premium: {order['premium_name']}\n💰 {order['price']} RUB"
            
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": ADMIN_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception:
        pass
        
    return {"ok": True}

def run_flask():
    flask_app.run(host="0.0.0.0", port=8080)


# === ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ФОТО ===
async def send_photo_message(update: Update, image_path: str, caption: str, reply_markup, parse_mode="HTML"):
    try:
        with open(image_path, 'rb') as photo_file:
            await update.message.reply_photo(photo=photo_file, caption=caption, parse_mode=parse_mode, reply_markup=reply_markup)
    except FileNotFoundError:
        if parse_mode == "HTML":
            await update.message.reply_html(caption, reply_markup=reply_markup)
        else:
            await update.message.reply_text(caption, reply_markup=reply_markup)


# === /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id)
    context.user_data.clear()

    keyboard = [
        ["⭐️ Telegram Stars", "👑 Telegram Premium"],
        ["💬 Поддержка", "ℹ О сервисе"],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    text = (
        f"🚀 <b>Добро пожаловать в PREM1UMSHOP!</b> {user.mention_html()}!\n\n"
        "🎯 <b>Покупай Telegram Stars и Telegram Premium по лучшим ценам!</b>\n\n"
        "<b>Выбери категорию:</b>"
    )
    
    await send_photo_message(update, IMG_MAIN_MENU, text, reply_markup)


# === РАССЫЛКА С ФОТО (КОМАНДА /post) ===
async def broadcast_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_CHAT_ID):
        return

    reply = update.message.reply_to_message
    caption_text = " ".join(context.args)

    if not os.path.exists(USERS_FILE):
        await update.message.reply_text("📁 База пуста.")
        return

    with open(USERS_FILE, "r") as f:
        chat_ids = f.read().splitlines()

    await update.message.reply_text(f"🚀 Рассылка на {len(chat_ids)} пользователей...")
    
    count = 0
    if reply and reply.photo:
        photo_id = reply.photo[-1].file_id
        for chat_id in chat_ids:
            try:
                await context.bot.send_photo(chat_id=chat_id, photo=photo_id, caption=caption_text, parse_mode="HTML")
                count += 1
                await asyncio.sleep(0.05)
            except Exception:
                pass
    else:
        if not caption_text:
            await update.message.reply_text("❗ Сделай Reply на фото с командой /post Текст\nИли просто /post Текст")
            return
            
        for chat_id in chat_ids:
            try:
                await context.bot.send_message(chat_id=chat_id, text=caption_text, parse_mode="HTML")
                count += 1
                await asyncio.sleep(0.05)
            except Exception:
                pass

    await update.message.reply_text(f"✅ Успешно отправлено: {count}")


# === О сервисе и документы (ПОЛНЫЙ ТЕКСТ) ===
async def show_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ <b>О сервисе PREM1UMSHOP</b>\n\n"
        "PREM1UMSHOP (@prem1umshopbot) — сервис по продаже Telegram Stars "
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
    
    await send_photo_message(update, IMG_BUY_GIFT, stars_info, reply_markup, parse_mode="HTML")

# === Premium ===
async def show_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["category"] = "premium"

    premium_info = "👑 Telegram Premium\n\n🎉 Выбери вариант покупки:"
    keyboard = [["🎁 Купить себе", "🎀 Подарить другу"], ["🔙 Назад"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await send_photo_message(update, IMG_BUY_GIFT, premium_info, reply_markup, parse_mode="HTML")

# === Подарок другу ===
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

# === Соглашение (ПОЛНЫЙ ТЕКСТ) ===
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
    
    await send_photo_message(update, IMG_AGREEMENT, agreement_text, reply_markup)

# === Согласие ===
async def handle_agreement_consent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["agreement_accepted"] = True
    if "pending_order" in context.user_data:
        d = context.user_data["pending_order"]
        if d["type"] == "stars": await process_stars_order(update, context, d["count"], True)
        elif d["type"] == "premium": await process_premium_order(update, context, d["name"], d["price"], True)
        del context.user_data["pending_order"]
    else:
        await update.message.reply_text("✅ Соглашение принято.\n💳 Оплата скоро будет доступна!")

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
    await send_photo_message(update, IMG_STARS_AMOUNT, stars_info, reply_markup, parse_mode=None)

# === Процесс оплаты Stars ===
async def process_stars_order(update: Update, context: ContextTypes.DEFAULT_TYPE, count: int, bypass_agreement=False):
    if not bypass_agreement and not context.user_data.get("agreement_accepted"):
        context.user_data["pending_order"] = {"type": "stars", "count": count}
        await show_agreement(update, context)
        return
    price = int(count * 1.6)
    order_id = str(uuid.uuid4())
    user = update.effective_user
    
    gift_username = context.user_data.get("gift_username")
    is_gift = bool(context.user_data.get("gift_mode") and gift_username)

    ORDERS[order_id] = {
        "type": "stars",
        "buyer_id": user.id,
        "buyer_username": user.username,
        "buyer_fullname": user.full_name,
        "gift_to": gift_username if is_gift else None,
        "stars_count": count,
        "price": price,
    }
    
    url = create_lava_invoice(price, f"Stars {count} (ID {user.id})", "https://t.me/prem1umshopbot", order_id)
    if not url:
        await update.message.reply_text("⚠️ Ошибка создания счета.")
        return

    msg = (
        "🎉 Отличный выбор!\n\n"
        f"Товар: {count} Telegram Stars ⭐️\n"
        f"Цена: {price} ₽\n\n"
        "Нажми кнопку ниже, чтобы перейти к оплате."
    )
    
    await send_photo_message(update, IMG_PAYMENT, msg, InlineKeyboardMarkup([[InlineKeyboardButton("💳 ОПЛАТИТЬ", url=url)]]))
    await update.message.reply_text("После оплаты нажми:", reply_markup=ReplyKeyboardMarkup([["✅ Я оплатил", "❌ Отмена"]], resize_keyboard=True))

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

# === Процесс оплаты Premium ===
async def process_premium_order(update: Update, context: ContextTypes.DEFAULT_TYPE, name: str, price: int, bypass_agreement=False):
    if not bypass_agreement and not context.user_data.get("agreement_accepted"):
        context.user_data["pending_order"] = {"type": "premium", "name": name, "price": price}
        await show_agreement(update, context)
        return
    order_id = str(uuid.uuid4())
    user = update.effective_user
    
    gift_username = context.user_data.get("gift_username")
    is_gift = bool(context.user_data.get("gift_mode") and gift_username)

    ORDERS[order_id] = {
        "type": "premium",
        "buyer_id": user.id,
        "buyer_username": user.username,
        "buyer_fullname": user.full_name,
        "gift_to": gift_username if is_gift else None,
        "premium_name": name,
        "price": price,
    }

    url = create_lava_invoice(price, f"Premium {name} (ID {user.id})", "https://t.me/prem1umshopbot", order_id)
    if not url:
        await update.message.reply_text("⚠️ Ошибка создания счета.")
        return

    msg = (
        "🎉 Отличный выбор!\n\n"
        f"Товар: {name}\n"
        f"Цена: {price} ₽\n\n"
        "Нажми кнопку ниже, чтобы перейти к оплате."
    )

    await send_photo_message(update, IMG_PAYMENT, msg, InlineKeyboardMarkup([[InlineKeyboardButton("💳 ОПЛАТИТЬ", url=url)]]))
    await update.message.reply_text("После оплаты нажми:", reply_markup=ReplyKeyboardMarkup([["✅ Я оплатил", "❌ Отмена"]], resize_keyboard=True))

# === Поддержка (ПОЛНЫЙ ТЕКСТ) ===
async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    support_text = (
        "💬 Поддержка\n\n"
        "По всем вопросам: @PREM1UMSHOP\n"
        "Ответим в ближайшее время ⚡️"
    )
    reply_markup = ReplyKeyboardMarkup([["🔙 Назад"]], resize_keyboard=True)
    await update.message.reply_text(support_text, reply_markup=reply_markup)

# === ОБРАБОТЧИК СООБЩЕНИЙ ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "⭐️ Telegram Stars": await show_stars(update, context)
    elif text == "👑 Telegram Premium": await show_premium(update, context)
    elif text == "💬 Поддержка": await show_support(update, context)
    elif text == "ℹ О сервисе": await show_about(update, context)
    elif text == "🔙 Назад" or text == "❌ Отмена": await start(update, context)
    elif text == "✅ Я оплатил": 
        await update.message.reply_text("✅ Спасибо! Если платёж прошёл, заказ будет обработан в ближайшее время.\nЕсли что-то пошло не так, напишите в поддержку: @PREM1UMSHOP")
        await start(update, context)
    elif text == "🎁 Купить себе":
        context.user_data["gift_mode"] = False
        context.user_data["gift_username"] = None
        if context.user_data.get("category") == "premium": await show_premium_purchase(update, context)
        else: await show_stars_purchase(update, context)
    elif text == "🎀 Подарить другу":
        context.user_data["product_type"] = context.user_data.get("category", "stars")
        await handle_gift_selection(update, context)
    elif context.user_data.get("gift_mode") and not context.user_data.get("gift_username"):
        u = text.strip()
        if not u.startswith("@"): u = "@" + u
        context.user_data["gift_username"] = u
        if context.user_data.get("product_type") == "premium" or context.user_data.get("category") == "premium": await show_premium_purchase(update, context)
        else: await show_stars_purchase(update, context)
    elif text in PREMIUM_ITEMS: 
        item = PREMIUM_ITEMS[text]
        await process_premium_order(update, context, item["name"], item["price"])
    else:
        # Пакеты звезд
        pkgs = {"100 ⭐️ - 160Р": 100, "150 ⭐️ - 240Р": 150, "250 ⭐️ - 400Р": 250, "500 ⭐️ - 800Р": 500, "1000 ⭐️ - 1600Р": 1000, "2500 ⭐️ - 4000Р": 2500}
        if text in pkgs: await process_stars_order(update, context, pkgs[text])
        else:
            try:
                c = int(text)
                if 50 <= c <= 5000: await process_stars_order(update, context, c)
                else: await update.message.reply_text("❌ Минимум 50, Максимум 5000.")
            except:
                await update.message.reply_text("Используй кнопки ниже!")

# === ГЛАВНАЯ ФУНКЦИЯ ===
def main():
    threading.Thread(target=run_flask, daemon=True).start()

    # СОЗДАЕМ И ЗАПУСКАЕМ ВНУТРИ main(), ЧТОБЫ НЕ БЫЛО ОШИБОК С NoneType
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("post", broadcast_post)) 
    
    application.add_handler(MessageHandler(filters.Regex("^✅ Я согласен$"), handle_agreement_consent))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Бот запущен (ВСЕ ФУНКЦИИ ВОССТАНОВЛЕНЫ)...")
    application.run_polling()

if __name__ == "__main__":
    main()
