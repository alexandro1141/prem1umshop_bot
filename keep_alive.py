from flask import Flask, request
from threading import Thread
import telegram

app = Flask('')
bot = telegram.Bot(token="8392743023:AAHjApwBpmoapx7NA3KW25iGmBITUvuOnDQ")

# 🔹 Твой Telegram ID (чтобы бот присылал уведомления лично тебе)
ADMIN_ID = 1041184050  # ← поменяй на свой ID (узнай в @userinfobot)

@app.route('/')
def home():
    return "✅ PREM1UMSHOP сервер активен!"

@app.route('/cloudtips_result', methods=['POST'])
def cloudtips_result():
    data = request.json
    amount = data.get("amount")
    comment = data.get("comment", "—")
    payer = data.get("payer_name", "Неизвестно")

    msg = (
        f"💸 <b>Новый платёж!</b>\n\n"
        f"👤 Плательщик: {payer}\n"
        f"💰 Сумма: {amount}₽\n"
        f"📝 Комментарий: {comment}"
    )
    bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode="HTML")
    return "OK", 200

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()
