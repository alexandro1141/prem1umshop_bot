import uuid
import requests
import logging
import json
import hmac
import hashlib
import threading
import os
import asyncio
from datetime import datetime, timedelta
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

# === КУРС ВАЛЮТ ===
STARS_PRICE = 1.6
TON_PRICE = 160

# === ПРОВЕРКА КЛЮЧЕЙ ===
if not TOKEN or not LAVA_SECRET_KEY:
    print("❌ ОШИБКА: Не найдены ключи в файле .env!")
    exit()

LAVA_INVOICE_URL = "https://api.lava.ru/business/invoice/create"
LAVA_HOOK_URL = "http://95.181.224.199:8080/lava-webhook"

# === ФАЙЛЫ ДАННЫХ ===
USERS_FILE = "users.txt"       # Для рассылки (все, кто когда-либо заходил)
STATS_FILE = "stats.json"      # Для статистики (кто когда был активен)
STATUS_FILE = "status.txt"     # Режим сна

# === ФУНКЦИИ ===

# 1. Сохранение юзера для рассылки
def save_user(chat_id):
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

# 2. Запись активности для статистики
def record_activity(user_id):
    user_id = str(user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    
    data = {}
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            data = {}

    # Если сегодняшней даты нет - создаем
    if today not in data:
        data[today] = []

    # Если юзера нет в списке за сегодня - добавляем
    if user_id not in data[today]:
        data[today].append(user_id)
        
        # Сохраняем обратно в файл
        with open(STATS_FILE, "w") as f:
            json.dump(data, f)

# 3. Подсчет статистики
def get_stats():
    if not os.path.exists(STATS_FILE):
        return 0, 0, 0
    
    try:
        with open(STATS_FILE, "r") as f:
            data = json.load(f)
    except Exception:
        return 0, 0, 0

    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # За сегодня
    users_today = len(data.get(today_str, []))

    # За 7 дней
    users_week_set = set()
    for i in range(7):
        date_check = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        if date_check in data:
            users_week_set.update(data[date_check])
    
    # За 30 дней
    users_month_set = set()
    for i in range(30):
        date_check = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        if date_check in data:
            users_month_set.update(data[date_check])

    return users_today, len(users_week_set), len(users_month_set)


# Проверка режима сна
def is_sleeping():
    if not os.path.exists(STATUS_FILE): return False
    with open(STATUS_FILE, "r") as f: return f.read().strip() == "SLEEP"

def set_status(mode):
    with open(STATUS_FILE, "w") as f: f.write(mode)

# === НАСТРОЙКИ КАРТИНОК ===
IMG_DIR = "images"
IMG_MAIN_MENU = os.path.join(IMG_DIR, "ПлашкаБотПШ 1.png")
IMG_BUY_GIFT = os.path.join(IMG_DIR, "ПлашкаБотПШ 2.png")
IMG_STARS_AMOUNT = os.path.join(IMG_DIR, "ПлашкаБотПШ 3.png")
IMG_AGREEMENT = os.path.join(IMG_DIR, "ПлашкаБотПШ 4.png")
IMG_PAYMENT = os.path.join(IMG_DIR, "ПлашкаБотПШ 5.png")
IMG_TON_AMOUNT = os.path.join(IMG_DIR, "ПлашкаБотПШ 6.png")

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
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
    signature = hmac.new(LAVA_SECRET_KEY.encode("utf-8"), msg=json_body.encode("utf-8"), digestmod=hashlib.sha256).hexdigest()
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
        logging.exception("LAVA exception: %s", e)
        return None

# === FLASK WEBHOOK ===
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

    if not is_success: return {"ok": True}

    order = ORDERS.get(order_id)
    
    # УВЕДОМЛЕНИЕ АДМИНУ
    admin_text = f"💸 <b>ОПЛАТА LAVA</b>\nOrder: {order_id}\nStatus: {status}\n"
    if order:
        username = order.get("buyer_username")
        buyer_mention = f"@{username}" if username else f"id {order['buyer_id']}"
        gift_to = order.get("gift_to") or "самому себе"
        admin_text += f"👤 <b>Кто:</b> {buyer_mention}\n🎁 <b>Кому:</b> {gift_to}\n"
        if order['type'] == 'stars': admin_text += f"⭐ Stars: {order['amount']}\n💰 {order['price']} RUB"
        elif order['type'] == 'funds': admin_text += f"💎 TON: {order['amount']} TON\n💰 {order['price']} RUB"
            
    try: requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": ADMIN_CHAT_ID, "text": admin_text, "parse_mode": "HTML"}, timeout=10)
    except Exception: pass
        
    # УВЕДОМЛЕНИЕ ПОКУПАТЕЛЮ
    if order and order.get('buyer_id'):
        if is_sleeping():
            user_text = ("✅ <b>Оплата прошла успешно!</b>\n\nСпасибо за покупку в PREM1UMSHOP.\n\n😴 <b>Внимание: Ночной режим</b>\n"
                         "Ваш заказ принят. Средства поступят вам <b>утром, примерно в 11:00 по МСК</b>.")
        else:
            user_text = ("✅ <b>Оплата прошла успешно!</b>\n\nСпасибо за покупку в PREM1UMSHOP.\n"
                         "⏳ <b>Срок зачисления:</b> Обычно в течение <b>5 минут</b>.\n<i>(В редких случаях до 1 часа).</i>")
        
        menu = {"keyboard": [[{"text": "⭐️ Telegram Stars"}, {"text": "💎 TON (Telegram)"}], [{"text": "💬 Поддержка"}, {"text": "ℹ О сервисе"}]], "resize_keyboard": True}
        try: requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": order['buyer_id'], "text": user_text, "parse_mode": "HTML", "reply_markup": menu}, timeout=10)
        except Exception: pass

    return {"ok": True}

def run_flask():
    flask_app.run(host="0.0.0.0", port=8080)

# === ПОМОЩНИК ФОТО ===
async def send_photo_message(update: Update, image_path: str, caption: str, reply_markup, parse_mode="HTML"):
    try:
        with open(image_path, 'rb') as photo_file:
            await update.message.reply_photo(photo=photo_file, caption=caption, parse_mode=parse_mode, reply_markup=reply_markup)
    except FileNotFoundError:
        if parse_mode == "HTML": await update.message.reply_html(caption, reply_markup=reply_markup)
        else: await update.message.reply_text(caption, reply_markup=reply_markup)

# === /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id)
    record_activity(user.id) # Пишем активность
    context.user_data.clear()

    keyboard = [["⭐️ Telegram Stars", "💎 TON (Telegram)"], ["💬 Поддержка", "ℹ О сервисе"]]
    text = f"🚀 <b>Добро пожаловать в PREM1UMSHOP!</b> {user.mention_html()}!\n\n🎯 <b>Покупай Telegram Stars и TON (Telegram) по лучшим ценам!</b>\n\n<b>Выбери категорию:</b>"
    await send_photo_message(update, IMG_MAIN_MENU, text, ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

# === КОМАНДА СТАТИСТИКИ (/stats) ===
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Только для админа
    if str(update.effective_user.id) != str(ADMIN_CHAT_ID):
        return

    today, week, month = get_stats()
    
    # Считаем всего пользователей в базе
    total_users = 0
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            total_users = len(f.read().splitlines())

    text = (
        "📊 <b>Статистика активности пользователей</b>\n\n"
        f"🟢 <b>За сегодня:</b> {today} чел.\n"
        f"🟡 <b>За 7 дней:</b> {week} чел. (уникальных)\n"
        f"🔴 <b>За 30 дней:</b> {month} чел. (уникальных)\n\n"
        f"📁 <b>Всего в базе (за всё время):</b> {total_users} чел."
    )
    await update.message.reply_html(text)

# === КОМАНДЫ АДМИНА ===
async def sleep_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_CHAT_ID): return
    set_status("SLEEP")
    await update.message.reply_text("😴 <b>Ночной режим ВКЛЮЧЕН.</b>")

async def wake_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_CHAT_ID): return
    set_status("ACTIVE")
    await update.message.reply_text("☀️ <b>Дневной режим ВКЛЮЧЕН.</b>")

async def broadcast_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_CHAT_ID): return
    reply = update.message.reply_to_message
    caption_text = " ".join(context.args)
    if not os.path.exists(USERS_FILE):
        await update.message.reply_text("📁 База пуста.")
        return
    with open(USERS_FILE, "r") as f: chat_ids = f.read().splitlines()
    await update.message.reply_text(f"🚀 Рассылка на {len(chat_ids)} пользователей...")
    count = 0
    if reply and reply.photo:
        photo_id = reply.photo[-1].file_id
        for chat_id in chat_ids:
            try:
                await context.bot.send_photo(chat_id=chat_id, photo=photo_id, caption=caption_text, parse_mode="HTML")
                count += 1
                await asyncio.sleep(0.05)
            except Exception: pass
    else:
        if not caption_text:
            await update.message.reply_text("❗ Сделай Reply на фото с текстом")
            return
        for chat_id in chat_ids:
            try:
                await context.bot.send_message(chat_id=chat_id, text=caption_text, parse_mode="HTML")
                count += 1
                await asyncio.sleep(0.05)
            except Exception: pass
    await update.message.reply_text(f"✅ Успешно отправлено: {count}")

# === МЕНЮ И ЛОГИКА ===
async def show_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = ("ℹ️ <b>О сервисе PREM1UMSHOP</b>\n\nСервис по продаже Telegram Stars и TON.\n\n"
            "<b>Документы:</b> <a href='https://alexandro1141.github.io/policy-page/policy.html'>Открыть</a>\n"
            "<b>Поддержка:</b> @PREM1UMSHOP")
    await update.message.reply_html(text, reply_markup=ReplyKeyboardMarkup([["🔙 Назад"]], resize_keyboard=True))

async def show_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear(); context.user_data["category"] = "stars"
    await send_photo_message(update, IMG_BUY_GIFT, "⭐️ Telegram Stars\n\n🎉 Выбери вариант покупки:", ReplyKeyboardMarkup([["🎁 Купить себе", "🎀 Подарить другу"], ["🔙 Назад"]], resize_keyboard=True))

async def show_funds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear(); context.user_data["category"] = "funds"
    await send_photo_message(update, IMG_BUY_GIFT, "💎 <b>TON (Telegram)</b>\n\n⚠️ Только для покупок подарков внутри Telegram.\n\n🎉 Выбери вариант:", ReplyKeyboardMarkup([["🎁 Купить себе", "🎀 Подарить другу"], ["🔙 Назад"]], resize_keyboard=True))

async def handle_gift_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["gift_mode"] = True
    await update.message.reply_html("🎀 <b>Подарок другу</b>\nВведите @username:", reply_markup=ReplyKeyboardMarkup([["🔙 Назад"]], resize_keyboard=True))

async def show_agreement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["agreement_shown"] = True
    await send_photo_message(update, IMG_AGREEMENT, "📄 <b>Соглашение</b>\n\n<a href='https://alexandro1141.github.io/policy-page/policy.html'>Открыть документы</a>\n\nНажмите <b>«✅ Я согласен»</b>.", ReplyKeyboardMarkup([["✅ Я согласен"], ["🔙 Назад"]], resize_keyboard=True))

async def handle_agreement_consent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    record_activity(update.effective_user.id) # Пишем активность
    context.user_data["agreement_accepted"] = True
    if "pending_order" in context.user_data:
        d = context.user_data["pending_order"]
        if d["type"] == "stars": await process_stars_order(update, context, d["count"], True)
        elif d["type"] == "funds": await process_funds_order(update, context, d["count"], True)
        del context.user_data["pending_order"]
    else:
        await update.message.reply_text("✅ Соглашение принято.")

async def show_stars_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = "🎉 Выбери пакет Stars:"
    if context.user_data.get("gift_mode"): info = f"🎁 Подарок для {context.user_data.get('gift_username')}\n\n" + info
    kb = [["100 ⭐️ - 160Р", "150 ⭐️ - 240Р"], ["250 ⭐️ - 400Р", "500 ⭐️ - 800Р"], ["1000 ⭐️ - 1600Р", "2500 ⭐️ - 4000Р"], ["🔙 Назад"]]
    await send_photo_message(update, IMG_STARS_AMOUNT, info, ReplyKeyboardMarkup(kb, resize_keyboard=True), parse_mode=None)

async def show_funds_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = "💎 <b>Введите количество TON</b> (целое, 1-50):"
    if context.user_data.get("gift_mode"): info = f"🎁 Подарок для {context.user_data.get('gift_username')}\n\n" + info
    await send_photo_message(update, IMG_TON_AMOUNT, info, ReplyKeyboardMarkup([["🔙 Назад"]], resize_keyboard=True))

async def process_stars_order(update: Update, context: ContextTypes.DEFAULT_TYPE, count: int, bypass_agreement=False):
    if not bypass_agreement and not context.user_data.get("agreement_accepted"):
        context.user_data["pending_order"] = {"type": "stars", "count": count}
        await show_agreement(update, context)
        return
    price = int(count * STARS_PRICE)
    order_id = str(uuid.uuid4())
    user = update.effective_user
    gift = context.user_data.get("gift_username") if context.user_data.get("gift_mode") else None
    ORDERS[order_id] = {"type": "stars", "buyer_id": user.id, "buyer_username": user.username, "gift_to": gift, "amount": count, "price": price}
    url = create_lava_invoice(price, f"Stars {count}", "https://t.me/prem1umshopbot", order_id)
    if not url:
        await update.message.reply_text("⚠️ Ошибка LAVA.")
        return
    
    msg_suffix = "😴 <b>Ночной режим:</b> Выдача утром (11:00 МСК)." if is_sleeping() else "ℹ️ <b>Инфо:</b> Как только оплата пройдет, бот пришлёт уведомление."
    msg = f"🎉 <b>Заказ Stars</b>\nТовар: {count} ⭐️\nЦена: {price} ₽\n\n{msg_suffix}"
    await send_photo_message(update, IMG_PAYMENT, msg, InlineKeyboardMarkup([[InlineKeyboardButton("💳 ОПЛАТИТЬ", url=url)]]))
    await update.message.reply_text("Если передумали:", reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True))

async def process_funds_order(update: Update, context: ContextTypes.DEFAULT_TYPE, count: int, bypass_agreement=False):
    if not (1 <= count <= 50):
        await update.message.reply_text("❌ TON: от 1 до 50.")
        return
    if not bypass_agreement and not context.user_data.get("agreement_accepted"):
        context.user_data["pending_order"] = {"type": "funds", "count": count}
        await show_agreement(update, context)
        return
    price = int(count * TON_PRICE)
    order_id = str(uuid.uuid4())
    user = update.effective_user
    gift = context.user_data.get("gift_username") if context.user_data.get("gift_mode") else None
    ORDERS[order_id] = {"type": "funds", "buyer_id": user.id, "buyer_username": user.username, "gift_to": gift, "amount": count, "price": price}
    url = create_lava_invoice(price, f"Funds {count} TON", "https://t.me/prem1umshopbot", order_id)
    if not url:
        await update.message.reply_text("⚠️ Ошибка LAVA.")
        return

    msg_suffix = "😴 <b>Ночной режим:</b> Выдача утром (11:00 МСК)." if is_sleeping() else "ℹ️ <b>Инфо:</b> Как только оплата пройдет, бот пришлёт уведомление."
    msg = f"💎 <b>Заказ TON</b>\nТовар: {count} TON\nЦена: {price} ₽\n\n{msg_suffix}"
    await send_photo_message(update, IMG_PAYMENT, msg, InlineKeyboardMarkup([[InlineKeyboardButton("💳 ОПЛАТИТЬ", url=url)]]))
    await update.message.reply_text("Если передумали:", reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True))

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💬 Поддержка: @PREM1UMSHOP", reply_markup=ReplyKeyboardMarkup([["🔙 Назад"]], resize_keyboard=True))

# === ОБРАБОТЧИК ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    record_activity(user.id) # Пишем активность при любом сообщении
    
    text = update.message.text
    if text == "⭐️ Telegram Stars": await show_stars(update, context)
    elif text == "💎 TON (Telegram)": await show_funds(update, context)
    elif text == "💬 Поддержка": await show_support(update, context)
    elif text == "ℹ О сервисе": await show_about(update, context)
    elif text == "🔙 Назад" or text == "❌ Отмена": await start(update, context)
    elif text == "🎁 Купить себе":
        context.user_data["gift_mode"] = False
        if context.user_data.get("category") == "funds": await show_funds_purchase(update, context)
        else: await show_stars_purchase(update, context)
    elif text == "🎀 Подарить другу":
        context.user_data["product_type"] = context.user_data.get("category", "stars")
        await handle_gift_selection(update, context)
    elif context.user_data.get("gift_mode") and not context.user_data.get("gift_username"):
        u = text.strip(); u = "@" + u if not u.startswith("@") else u
        context.user_data["gift_username"] = u
        if context.user_data.get("product_type") == "funds" or context.user_data.get("category") == "funds": await show_funds_purchase(update, context)
        else: await show_stars_purchase(update, context)
        
    pkgs = {"100 ⭐️ - 160Р": 100, "150 ⭐️ - 240Р": 150, "250 ⭐️ - 400Р": 250, "500 ⭐️ - 800Р": 500, "1000 ⭐️ - 1600Р": 1000, "2500 ⭐️ - 4000Р": 2500}
    if text in pkgs: await process_stars_order(update, context, pkgs[text]); return
        
    try:
        count = int(text)
        if context.user_data.get("category") == "funds" or context.user_data.get("product_type") == "funds": await process_funds_order(update, context, count)
        else:
            if 50 <= count <= 5000: await process_stars_order(update, context, count)
            else: await update.message.reply_text("❌ Stars: 50-5000.")
    except ValueError: await update.message.reply_text("❗ Используйте меню.")

# === MAIN ===
def main():
    threading.Thread(target=run_flask, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("post", broadcast_post))
    app.add_handler(CommandHandler("sleep", sleep_command))
    app.add_handler(CommandHandler("wake", wake_command))
    app.add_handler(CommandHandler("stats", stats_command)) # Новая команда
    
    app.add_handler(MessageHandler(filters.Regex("^✅ Я согласен$"), handle_agreement_consent))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 Бот запущен (STATS + TON + SLEEP)...")
    app.run_polling()

if __name__ == "__main__":
    main()
