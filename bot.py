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

# Проверка ключей
if not TOKEN or not LAVA_SECRET_KEY:
    print("❌ ОШИБКА: Не найдены ключи в файле .env!")
    exit()

LAVA_INVOICE_URL = "https://api.lava.ru/business/invoice/create"
LAVA_HOOK_URL = "http://95.181.224.199:8080/lava-webhook"

# === ФАЙЛ С ПОЛЬЗОВАТЕЛЯМИ (БАЗА ДАННЫХ) ===
USERS_FILE = "users.txt"

def save_user(chat_id):
    """Сохраняет ID пользователя в файл, если его там нет"""
    chat_id = str(chat_id)
    users = set()
    
    # Создаем файл, если нет
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

# === Глобальное приложение Telegram и память заказов ===
tg_app: Application | None = None
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


# === /start (ВХОД И СОХРАНЕНИЕ ЮЗЕРА) ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # СОХРАНЯЕМ ПОЛЬЗОВАТЕЛЯ В БАЗУ
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
    # 1. Проверка админа
    if str(update.effective_user.id) != str(ADMIN_CHAT_ID):
        return

    # 2. Проверяем, ответил ли админ на сообщение с фото
    reply = update.message.reply_to_message
    
    # Получаем текст из команды (всё что после /post)
    caption_text = " ".join(context.args)

    if not os.path.exists(USERS_FILE):
        await update.message.reply_text("📁 База пуста.")
        return

    with open(USERS_FILE, "r") as f:
        chat_ids = f.read().splitlines()

    await update.message.reply_text(f"🚀 Рассылка на {len(chat_ids)} пользователей...")
    
    count = 0
    # 3. ЛОГИКА РАССЫЛКИ
    if reply and reply.photo:
        # Если ответили на фото - шлем фото
        photo_id = reply.photo[-1].file_id # Берем самое лучшее качество
        for chat_id in chat_ids:
            try:
                await context.bot.send_photo(chat_id=chat_id, photo=photo_id, caption=caption_text, parse_mode="HTML")
                count += 1
                await asyncio.sleep(0.05) # Небольшая пауза чтобы телеграм не забанил за спам
            except Exception:
                pass
    else:
        # Если просто текст (без ответа на фото)
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


# === ОСТАЛЬНЫЕ ФУНКЦИИ (Сокращены для удобства, логика та же) ===
async def show_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "ℹ️ <b>О сервисе PREM1UMSHOP</b>\n\nДокументы и поддержка: @PREM1UMSHOP"
    reply_markup = ReplyKeyboardMarkup([["🔙 Назад"]], resize_keyboard=True)
    await update.message.reply_html(text, reply_markup=reply_markup)

async def show_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["category"] = "stars"
    await send_photo_message(update, IMG_BUY_GIFT, "⭐️ Stars: Выбери вариант:", ReplyKeyboardMarkup([["🎁 Купить себе", "🎀 Подарить другу"], ["🔙 Назад"]], resize_keyboard=True))

async def show_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["category"] = "premium"
    await send_photo_message(update, IMG_BUY_GIFT, "👑 Premium: Выбери вариант:", ReplyKeyboardMarkup([["🎁 Купить себе", "🎀 Подарить другу"], ["🔙 Назад"]], resize_keyboard=True))

async def handle_gift_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["gift_mode"] = True
    await update.message.reply_html("Введи @username друга:", reply_markup=ReplyKeyboardMarkup([["🔙 Назад"]], resize_keyboard=True))

async def show_agreement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["agreement_shown"] = True
    await send_photo_message(update, IMG_AGREEMENT, "📄 Примите соглашение:", ReplyKeyboardMarkup([["✅ Я согласен"], ["🔙 Назад"]], resize_keyboard=True))

async def handle_agreement_consent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["agreement_accepted"] = True
    if "pending_order" in context.user_data:
        d = context.user_data["pending_order"]
        if d["type"] == "stars": await process_stars_order(update, context, d["count"], True)
        elif d["type"] == "premium": await process_premium_order(update, context, d["name"], d["price"], True)
        del context.user_data["pending_order"]
    else:
        await update.message.reply_text("✅ Соглашение принято.")

async def show_stars_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_photo_message(update, IMG_STARS_AMOUNT, "Выбери количество звёзд:", ReplyKeyboardMarkup([["100 ⭐️ - 160Р", "150 ⭐️ - 240Р"], ["250 ⭐️ - 400Р", "500 ⭐️ - 800Р"], ["🔙 Назад"]], resize_keyboard=True), parse_mode=None)

async def process_stars_order(update: Update, context: ContextTypes.DEFAULT_TYPE, count: int, bypass_agreement=False):
    if not bypass_agreement and not context.user_data.get("agreement_accepted"):
        context.user_data["pending_order"] = {"type": "stars", "count": count}
        await show_agreement(update, context)
        return
    price = int(count * 1.6)
    order_id = str(uuid.uuid4())
    user = update.effective_user
    ORDERS[order_id] = {"type": "stars", "buyer_id": user.id, "buyer_username": user.username, "gift_to": context.user_data.get("gift_username"), "stars_count": count, "price": price, "premium_name": None}
    
    url = create_lava_invoice(price, f"Stars {count}", "https://t.me/prem1umshopbot", order_id)
    if url:
        await send_photo_message(update, IMG_PAYMENT, f"К оплате: {price}₽", InlineKeyboardMarkup([[InlineKeyboardButton("💳 ОПЛАТИТЬ", url=url)]]))
        await update.message.reply_text("После оплаты нажми:", reply_markup=ReplyKeyboardMarkup([["✅ Я оплатил", "❌ Отмена"]], resize_keyboard=True))

async def show_premium_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = []
    row = []
    for i, item in enumerate(PREMIUM_ITEMS.values()):
        row.append(item['name'])
        if (i+1) % 2 == 0: kb.append(row); row = []
    if row: kb.append(row)
    kb.append(["🔙 Назад"])
    await update.message.reply_text("Выбери тариф:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def process_premium_order(update: Update, context: ContextTypes.DEFAULT_TYPE, name: str, price: int, bypass_agreement=False):
    if not bypass_agreement and not context.user_data.get("agreement_accepted"):
        context.user_data["pending_order"] = {"type": "premium", "name": name, "price": price}
        await show_agreement(update, context)
        return
    order_id = str(uuid.uuid4())
    user = update.effective_user
    ORDERS[order_id] = {"type": "premium", "buyer_id": user.id, "buyer_username": user.username, "gift_to": context.user_data.get("gift_username"), "premium_name": name, "price": price, "stars_count": None}

    url = create_lava_invoice(price, f"Premium {name}", "https://t.me/prem1umshopbot", order_id)
    if url:
        await send_photo_message(update, IMG_PAYMENT, f"К оплате: {price}₽", InlineKeyboardMarkup([[InlineKeyboardButton("💳 ОПЛАТИТЬ", url=url)]]))
        await update.message.reply_text("После оплаты нажми:", reply_markup=ReplyKeyboardMarkup([["✅ Я оплатил", "❌ Отмена"]], resize_keyboard=True))

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💬 Поддержка: @PREM1UMSHOP", reply_markup=ReplyKeyboardMarkup([["🔙 Назад"]], resize_keyboard=True))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "⭐️ Telegram Stars": await show_stars(update, context)
    elif text == "👑 Telegram Premium": await show_premium(update, context)
    elif text == "💬 Поддержка": await show_support(update, context)
    elif text == "ℹ О сервисе": await show_about(update, context)
    elif text == "🔙 Назад" or text == "❌ Отмена": await start(update, context)
    elif text == "✅ Я оплатил": 
        await update.message.reply_text("✅ Проверяем оплату... Ждите уведомления!")
        await start(update, context)
    elif text == "🎁 Купить себе":
        context.user_data["gift_mode"] = False
        if context.user_data.get("category") == "premium": await show_premium_purchase(update, context)
        else: await show_stars_purchase(update, context)
    elif text == "🎀 Подарить другу":
        context.user_data["product_type"] = context.user_data.get("category", "stars")
        await handle_gift_selection(update, context)
    elif context.user_data.get("gift_mode") and not context.user_data.get("gift_username"):
        context.user_data["gift_username"] = text
        if context.user_data.get("product_type") == "premium": await show_premium_purchase(update, context)
        else: await show_stars_purchase(update, context)
    elif text in PREMIUM_ITEMS: await process_premium_order(update, context, PREMIUM_ITEMS[text]["name"], PREMIUM_ITEMS[text]["price"])
    else:
        # Пакеты звезд
        pkgs = {"100 ⭐️ - 160Р": 100, "150 ⭐️ - 240Р": 150, "250 ⭐️ - 400Р": 250, "500 ⭐️ - 800Р": 500}
        if text in pkgs: await process_stars_order(update, context, pkgs[text])
        else:
            try:
                c = int(text)
                if 50 <= c <= 5000: await process_stars_order(update, context, c)
                else: await update.message.reply_text("От 50 до 5000!")
            except:
                await update.message.reply_text("Используй меню.")

def main():
    global tg_app
    threading.Thread(target=run_flask, daemon=True).start()
    tg_app = Application.builder().token(TOKEN).build()
    
    tg_app.add_handler(CommandHandler("start", start))
    tg_app.add_handler(CommandHandler("post", broadcast_post)) # <--- НОВАЯ КОМАНДА
    
    tg_app.add_handler(MessageHandler(filters.Regex("^✅ Я согласен$"), handle_agreement_consent))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

if __name__ == "__main__":
    print("🤖 Бот запущен...")
    tg_app.run_polling()
    main()
