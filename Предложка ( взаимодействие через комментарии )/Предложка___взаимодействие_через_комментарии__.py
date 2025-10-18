# -*- coding: utf-8 -*-
import telebot
import time
import uuid
from telebot import types

# === Настройки ===
TOKEN = "8446185357:AAFRVdLr-VmH0pR6Hd7c-0chXUINcvZSnDA"
MOD_CHAT_ID = -1003079770383  # id чата модерации
CHANNEL_USERNAME = "@asddfasfas"  # username канала (с @)

bot = telebot.TeleBot(TOKEN)

# === Хранилища ===
offers = {}  # offer_id -> { owner, text, type, photo/video, mode, anon_link(optional), created_time }
last_message_time = {}  # user_id -> timestamp (антиспам)
mod_messages = {}  # mod_message_id -> offer_id (чтобы знать, какое предложение связано с мод-сообщением)
edit_requests = {}  # instruction_message_id -> { offer_id, mod_msg_id, time }
MAX_TEXT_LENGTH = 500  # ограничение символов

# === Вспомогательные функции ===
def safe_html(text):
    return text.replace('<', '&lt;').replace('>', '&gt;')

def gen_offer_id():
    return uuid.uuid4().hex  # безопасный короткий UUID без дефисов

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

# === Команды ===
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Кого ищем? 🕵\nВведите сообщение ниже:")

# === Обработка предложений (текст, фото, видео) ===
@bot.message_handler(content_types=['text', 'photo', 'video'])
def handle_offer(message):
    # --- Если это ответ на служебное сообщение бота с просьбой редактировать —
    # обрабатываем как редактирование, а не как новое предложение

    if message.reply_to_message and message.reply_to_message.message_id in edit_requests:
        process_edit_reply_from_handle(message)
        return

    user_id = message.from_user.id
    now = time.time()

    # --- Игнорируем команды ---
    if message.text and message.text.startswith("/"):
        return

    # --- Проверка анонимного режима (ожидание ссылки) ---
    # В этой логике мы предполагаем, что we store interim offer for user until confirmation:
    # но теперь offers хранится по offer_id, поэтому нужно найти "последнее" незавершённое предложение этого user.
    # Чтобы не ломать логику, мы пометим ожидание anon_link следующей структурой: offers_waiting_by_user[user_id] = offer_id
    # Для простоты (и минимальных изменений) — найдем любое предложение от этого user с mode == 'anon' и без anon_link.

    # --- Антиспам ---
    if user_id in last_message_time and now - last_message_time[user_id] < 30:
        bot.send_message(message.chat.id, "⏳ Подожди немного перед следующей отправкой (30 сек).")
        return
    last_message_time[user_id] = now

    # --- Подготовка данных предложения ---
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

    # создаём уникальный offer_id и сохраняем
    offer_id = gen_offer_id()
    offers[offer_id] = data

    # --- Меню выбора режима (публично / анонимно) ---
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("😎 Отправить с юзернеймом", callback_data=f"mode_public_{offer_id}"),
        types.InlineKeyboardButton("🕶 Отправить анонимно", callback_data=f"mode_anon_{offer_id}")
    )
    bot.send_message(message.chat.id, "Выбери, как хочешь отправить сообщение:", reply_markup=markup)

# === Неподдерживаемые форматы ===
@bot.message_handler(content_types=[
    'audio', 'document', 'sticker', 'voice', 'animation', 'contact', 'poll', 'location'
])
def unsupported(message):
    bot.send_message(message.chat.id, "❌ Бот принимает только фото, видео и текст.")

# === Выбор режима (public/anon) ===
# === Выбор режима (public/anon) ===
@bot.callback_query_handler(func=lambda c: c.data.startswith("mode_"))
def choose_mode(call):
    try:
        _, mode, offer_id = call.data.split("_", 2)
        if offer_id not in offers:
            bot.answer_callback_query(call.id, "Ошибка: нет данных.")
            return

        offers[offer_id]["mode"] = mode

        # Удаляем предыдущее сообщение с выбором
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass

        # Сразу показываем подтверждение — без привязки к @AnonAskBot
        confirm_markup = types.InlineKeyboardMarkup()
        confirm_markup.add(
            types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{offer_id}"),
            types.InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_{offer_id}")
        )
        bot.send_message(call.message.chat.id, "Подтвердите отправку:", reply_markup=confirm_markup)
    except Exception as e:
        print("Ошибка в choose_mode:", e)

# === Возврат к выбору режима ===
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

# === Подтверждение / отмена отправки в модерацию ===
@bot.callback_query_handler(func=lambda c: c.data.startswith("confirm_") or c.data.startswith("cancel_"))
def confirm_or_cancel(call):
    try:
        action, offer_id = call.data.split("_", 1)
        if offer_id not in offers:
            bot.answer_callback_query(call.id, "Ошибка: нет данных.")
            return

        offer = offers[offer_id]

        # проверка, было ли уже подтверждение
        if offer.get("sent"):
            bot.answer_callback_query(call.id, "✅ Уже отправлено на модерацию.")
            return

        if action == "cancel":
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            return

        offer["sent"] = True  # помечаем как отправленное
        # удаляем кнопки, чтобы нельзя было повторно подтвердить
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except:
            pass

        # остальная логика публикации в чат модерации
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


# === Нажатие "Редактировать" ===
@bot.callback_query_handler(func=lambda c: c.data.startswith("edit_"))
def start_editing(call):
    try:
        _, offer_id = call.data.split("_", 1)
        if offer_id not in offers:
            bot.answer_callback_query(call.id, "Ошибка: нет данных для редактирования.")
            return
        bot.answer_callback_query(call.id)
        # отправляем служебное сообщение-инструкцию, на который модератор должен ответить
        instr = bot.send_message(
            call.message.chat.id,
            f"✏️ Введите новый текст для предложения OID {offer_id} ответом на это сообщение."
        )
        # сохраняем что за offer ожидает редактирования: ключ = instruction_message_id
        edit_requests[instr.message_id] = {"offer_id": offer_id, "mod_msg_id": call.message.message_id, "time": time.time()}
    except Exception as e:
        print("Ошибка в start_editing:", e)

# === Приём нового текста от модератора (когда он отвечает на служебное сообщение) ===
def process_edit_reply_from_handle(message):
    try:
        cleanup_edit_requests()
        instr_mid = message.reply_to_message.message_id
        if instr_mid not in edit_requests:
            # если вдруг нет такой записи — игнорируем (но это не должно случаться)
            return

        data = edit_requests.pop(instr_mid)
        offer_id = data["offer_id"]
        mod_msg_id = data["mod_msg_id"]

        if offer_id not in offers:
            bot.send_message(message.chat.id, "⚠️ Ошибка: предложение уже удалено.")
            # удаляем сообщение модератора и инструкцию, чтобы не засорять чат
            try:
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            try:
                bot.delete_message(message.chat.id, instr_mid)
            except:
                pass
            return

        # если пришло не текстовое сообщение — отменяем
        if not message.text or not message.text.strip():
            bot.send_message(message.chat.id, "❌ Пустой текст. Редактирование отменено.")
            # удалим сообщение-модератора и инструкцию
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
        offers[offer_id]["text"] = new_text  # обновляем данные

        # формируем новый текст для модерационного сообщения
        new_mod_text = (
            f"<b>Новое предложение ({'Анонимно' if offers[offer_id].get('mode') == 'anon' else 'С именем'})</b>\n\n"
            f"<b>OID:</b> <code>{offer_id}</code>\n"
            f"<b>Текст:</b>\n<code>{safe_html(new_text)}</code>"
        )

        # редактируем оригинальное сообщение в чате модерации (используем MOD_CHAT_ID и mod_msg_id)
        try:
            if offers[offer_id]["type"] in ["photo", "video"]:
                # для фото/видео меняем caption
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
            # если не получилось отредактировать — логируем, но продолжаем
            print("Ошибка при edit_message в модерации:", e)

        # удаляем сообщение модератора (его ответ) и инструкцию бота
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            bot.delete_message(message.chat.id, instr_mid)
        except:
            pass

        # опционально — можно отправить краткое уведомление, удаляемое через секунду (не добавляю, по твоему запросу можно потом)
    except Exception as e:
        print("Ошибка при обработке редактирования:", e)

# === Нажатия "Одобрить" / "Отклонить" в модерации ===
# === Нажатия "Одобрить" / "Отклонить" в модерации ===
@bot.callback_query_handler(func=lambda c: c.data.startswith("approve_") or c.data.startswith("reject_"))
def moderation_action(call):
    try:
        action, offer_id = call.data.split("_", 1)
        if offer_id not in offers:
            return
        offer = offers[offer_id]
        text = safe_html(offer["text"])
        # убираем кнопки с модерационного сообщения
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

        # === Формируем финальный текст для канала ===
        final_text = text

        # Если режим НЕ анонимный — добавляем юзернейм или ID
        if offer.get("mode") != "anon":
            user = bot.get_chat(offer["owner"])
            username = user.username
            if username:
                author_tag = f"\n\n👤 @{username}"
            else:
                # Если юзернейма нет — можно указать имя или просто ID (но лучше не светить ID)
                # По ТЗ — "указывался юзернейм", значит, если его нет — ничего не добавляем
                author_tag = ""
            final_text += author_tag

        post_text = final_text

        # === Публикация БЕЗ кнопки "Написать" ===
        if offer["type"] == "photo":
            bot.send_photo(CHANNEL_USERNAME, offer["photo"], caption=post_text, parse_mode="HTML")
        elif offer["type"] == "video":
            bot.send_video(CHANNEL_USERNAME, offer["video"], caption=post_text, parse_mode="HTML")
        else:
            bot.send_message(CHANNEL_USERNAME, post_text, parse_mode="HTML")

        bot.send_message(offer["owner"], "✅ Твоё сообщение опубликовано в канале!")

        # удаляем offer после публикации
        try:
            del offers[offer_id]
        except:
            pass
    except Exception as e:
        print("Ошибка при модерации:", e)

# === Запуск ===
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

    # Запускаем заглушку в отдельном потоке
    threading.Thread(target=keep_alive, daemon=True).start()

    bot.remove_webhook()
    bot.infinity_polling(skip_pending=True)

