import telebot
import time
import uuid
from telebot import types

# Токен и айдишники чата
TOKEN = #сюда вводить токен бота
MOD_CHAT_ID = # id чата модерации
CHANNEL_USERNAME = # username канала (с @)

bot = telebot.TeleBot(TOKEN)

# дальше не трогать!!
offers = {}  
last_message_time = {}  
mod_messages = {}  
edit_requests = {} 
MAX_TEXT_LENGTH = 500 


def safe_html(text):
    return text.replace('<', '&lt;').replace('>', '&gt;')

def gen_offer_id():
    return uuid.uuid4().hex 

def cleanup_edit_requests():
    now = time.time()
    expired = [mid for mid, d in edit_requests.items() if now - d["time"] > 600]
    for mid in expired:
        try:
            del edit_requests[mid]
        except KeyError:
            pass

def call_buttons(offer_id):
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{offer_id}"),
        types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{offer_id}"),
        types.InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_{offer_id}")
    )
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Кого ищем? 🕵\nВведите сообщение ниже:")

@bot.message_handler(content_types=['text', 'photo', 'video'])
def handle_offer(message):

    if message.reply_to_message and message.reply_to_message.message_id in edit_requests:
        process_edit_reply_from_handle(message)
        return

    user_id = message.from_user.id
    now = time.time()

    if message.text and message.text.startswith("/"):
        return

    if user_id in last_message_time and now - last_message_time[user_id] < 30:
        bot.send_message(message.chat.id, "⏳ Подожди немного перед следующей отправкой (30 сек).")
        return
    last_message_time[user_id] = now

    data = {"text": "", "type": None, "mode": None, "owner": user_id, "created_time": now}

    if message.content_type == "photo":
        data["type"] = "photo"
        data["photo"] = message.photo[-1].file_id
        data["text"] = (message.caption or "").strip()
        if not data["text"]:
            bot.send_message(message.chat.id, "📸 Добавь подпись к фото, иначе модераторы не поймут, что это.")
            return
        if len(data["text"]) > MAX_TEXT_LENGTH:
            bot.send_message(message.chat.id, f"❌ Слишком много символов! Максимум {MAX_TEXT_LENGTH}.")
            return
    elif message.content_type == "video":
        data["type"] = "video"
        data["video"] = message.video.file_id
        data["text"] = (message.caption or "").strip()
        if not data["text"]:
            bot.send_message(message.chat.id, "🎬 Добавь подпись к видео, иначе модераторы не поймут смысл.")
            return
        if len(data["text"]) > MAX_TEXT_LENGTH:
            bot.send_message(message.chat.id, f"❌ Слишком много символов! Максимум {MAX_TEXT_LENGTH}.")
            return
    elif message.content_type == "text":
        data["type"] = "text"
        data["text"] = message.text.strip()
        if not data["text"]:
            bot.send_message(message.chat.id, "❌ Пустое сообщение. Напиши хоть что-то 🙂")
            return
        if len(data["text"]) > MAX_TEXT_LENGTH:
            bot.send_message(message.chat.id, f"❌ Слишком много символов! Максимум {MAX_TEXT_LENGTH}.")
            return
    else:
        bot.send_message(message.chat.id, "❌ Бот принимает только фото, видео и текст.")
        return

    offer_id = gen_offer_id()
    offers[offer_id] = data

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("😎 Отправить с юзернеймом", callback_data=f"mode_public_{offer_id}"),
        types.InlineKeyboardButton("🕶 Отправить анонимно", callback_data=f"mode_anon_{offer_id}")
    )
    bot.send_message(message.chat.id, "Выбери, как хочешь отправить сообщение:", reply_markup=markup)

@bot.message_handler(content_types=[
    'audio', 'document', 'sticker', 'voice', 'animation', 'contact', 'poll', 'location'
])
def unsupported(message):
    bot.send_message(message.chat.id, "❌ Бот принимает только фото, видео и текст.")

@bot.callback_query_handler(func=lambda c: c.data.startswith("mode_"))
def choose_mode(call):
    try:
        _, mode, offer_id = call.data.split("_", 2)
        if offer_id not in offers:
            bot.answer_callback_query(call.id, "Ошибка: нет данных.")
            return

        offers[offer_id]["mode"] = mode

        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass

        confirm_markup = types.InlineKeyboardMarkup()
        confirm_markup.add(
            types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{offer_id}"),
            types.InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_{offer_id}")
        )
        bot.send_message(call.message.chat.id, "Подтвердите отправку:", reply_markup=confirm_markup)
    except Exception as e:
        print("Ошибка в choose_mode:", e)

@bot.callback_query_handler(func=lambda c: c.data.startswith("back_"))
def go_back(call):
    try:
        _, offer_id = call.data.split("_", 1)
        if offer_id not in offers:
            bot.answer_callback_query(call.id, "Ошибка: нет данных.")
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("😎 Отправить с именем", callback_data=f"mode_public_{offer_id}"),
            types.InlineKeyboardButton("🕶 Отправить анонимно", callback_data=f"mode_anon_{offer_id}")
        )
        bot.edit_message_text(
            "Выбери, как хочешь отправить сообщение:",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup
        )
    except Exception as e:
        print("Ошибка при возврате назад:", e)

@bot.callback_query_handler(func=lambda c: c.data.startswith("confirm_") or c.data.startswith("cancel_"))
def confirm_or_cancel(call):
    try:
        action, offer_id = call.data.split("_", 1)
        if offer_id not in offers:
            bot.answer_callback_query(call.id, "Ошибка: нет данных.")
            return

        offer = offers[offer_id]

        if offer.get("sent"):
            bot.answer_callback_query(call.id, "✅ Уже отправлено на модерацию.")
            return

        if action == "cancel":
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            return

        offer["sent"] = True 
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except:
            pass

        mode = offer["mode"]
        mod_text = (
            f"<b>Новое предложение ({'Анонимно' if mode == 'anon' else 'С именем'})</b>\n\n"
            f"<b>OID:</b> <code>{offer_id}</code>\n"
            f"<b>Текст:</b>\n<code>{safe_html(offer['text'])}</code>"
        )
        markup = call_buttons(offer_id)

        if offer["type"] == "photo":
            msg = bot.send_photo(MOD_CHAT_ID, offer["photo"], caption=mod_text, parse_mode="HTML", reply_markup=markup)
        elif offer["type"] == "video":
            msg = bot.send_video(MOD_CHAT_ID, offer["video"], caption=mod_text, parse_mode="HTML", reply_markup=markup)
        else:
            msg = bot.send_message(MOD_CHAT_ID, mod_text, parse_mode="HTML", reply_markup=markup)

        mod_messages[msg.message_id] = offer_id
        bot.send_message(offer["owner"], "✅ Твоё предложение отправлено на модерацию!")
        bot.answer_callback_query(call.id)
    except Exception as e:
        print("Ошибка в confirm_or_cancel:", e)


@bot.callback_query_handler(func=lambda c: c.data.startswith("edit_"))
def start_editing(call):
    try:
        _, offer_id = call.data.split("_", 1)
        if offer_id not in offers:
            bot.answer_callback_query(call.id, "Ошибка: нет данных для редактирования.")
            return
        bot.answer_callback_query(call.id)
        instr = bot.send_message(
            call.message.chat.id,
            f"✏️ Введите новый текст для предложения OID {offer_id} ответом на это сообщение."
        )
        edit_requests[instr.message_id] = {"offer_id": offer_id, "mod_msg_id": call.message.message_id, "time": time.time()}
    except Exception as e:
        print("Ошибка в start_editing:", e)

def process_edit_reply_from_handle(message):
    try:
        cleanup_edit_requests()
        instr_mid = message.reply_to_message.message_id
        if instr_mid not in edit_requests:
            return

        data = edit_requests.pop(instr_mid)
        offer_id = data["offer_id"]
        mod_msg_id = data["mod_msg_id"]

        if offer_id not in offers:
            bot.send_message(message.chat.id, "⚠️ Ошибка: предложение уже удалено.")
            try:
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            try:
                bot.delete_message(message.chat.id, instr_mid)
            except:
                pass
            return

        if not message.text or not message.text.strip():
            bot.send_message(message.chat.id, "❌ Пустой текст. Редактирование отменено.")
            try:
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            try:
                bot.delete_message(message.chat.id, instr_mid)
            except:
                pass
            return

        new_text = message.text.strip()
        offers[offer_id]["text"] = new_text  

        new_mod_text = (
            f"<b>Новое предложение ({'Анонимно' if offers[offer_id].get('mode') == 'anon' else 'С именем'})</b>\n\n"
            f"<b>OID:</b> <code>{offer_id}</code>\n"
            f"<b>Текст:</b>\n<code>{safe_html(new_text)}</code>"
        )

        try:
            if offers[offer_id]["type"] in ["photo", "video"]:
                bot.edit_message_caption(
                    chat_id=MOD_CHAT_ID,
                    message_id=mod_msg_id,
                    caption=new_mod_text,
                    parse_mode="HTML",
                    reply_markup=call_buttons(offer_id)
                )
            else:
                bot.edit_message_text(
                    new_mod_text,
                    chat_id=MOD_CHAT_ID,
                    message_id=mod_msg_id,
                    parse_mode="HTML",
                    reply_markup=call_buttons(offer_id)
                )
        except Exception as e:
            print("Ошибка при edit_message в модерации:", e)

        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            bot.delete_message(message.chat.id, instr_mid)
        except:
            pass

    except Exception as e:
        print("Ошибка при обработке редактирования:", e)

@bot.callback_query_handler(func=lambda c: c.data.startswith("approve_") or c.data.startswith("reject_"))
def moderation_action(call):
    try:
        action, offer_id = call.data.split("_", 1)
        if offer_id not in offers:
            return
        offer = offers[offer_id]
        text = safe_html(offer["text"])
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except:
            pass

        if action == "reject":
            bot.send_message(offer["owner"], "❌ Твоё сообщение отклонено модератором.")
            try:
                del offers[offer_id]
            except:
                pass
            return

        final_text = text

        if offer.get("mode") != "anon":
            user = bot.get_chat(offer["owner"])
            username = user.username
            if username:
                author_tag = f"\n\n👤 @{username}"
            else:
                author_tag = ""
            final_text += author_tag

        post_text = final_text

        if offer["type"] == "photo":
            bot.send_photo(CHANNEL_USERNAME, offer["photo"], caption=post_text, parse_mode="HTML")
        elif offer["type"] == "video":
            bot.send_video(CHANNEL_USERNAME, offer["video"], caption=post_text, parse_mode="HTML")
        else:
            bot.send_message(CHANNEL_USERNAME, post_text, parse_mode="HTML")

        bot.send_message(offer["owner"], "✅ Твоё сообщение опубликовано в канале!")

        try:
            del offers[offer_id]
        except:
            pass
    except Exception as e:
        print("Ошибка при модерации:", e)

if __name__ == "__main__":
    print("✅ Бот запущен")

    import threading
    import http.server
    import socketserver

    def keep_alive():
        PORT = 10000
        handler = http.server.SimpleHTTPRequestHandler
        with socketserver.TCPServer(("", PORT), handler) as httpd:
            print("⚡ Сервер-заглушка запущен на порту", PORT)
            httpd.serve_forever()

    threading.Thread(target=keep_alive, daemon=True).start()

    bot.remove_webhook()
    bot.infinity_polling(skip_pending=True)

