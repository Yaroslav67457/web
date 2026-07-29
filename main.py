from flask import Flask, render_template, send_file
from asgiref.wsgi import WsgiToAsgi
from collections import deque
from datetime import datetime
import socketio
import os

app = Flask(__name__)
app.config["SECRET_KEY"] = "secret!"

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    max_http_buffer_size=10 * 1024 * 1024,  # 10 MB
)

asgi_app = socketio.ASGIApp(sio, other_asgi_app=WsgiToAsgi(app))

users = {}
messages = deque(maxlen=100)  # храним последние 100 сообщений
message_id_counter = 0
MAX_NICK_LENGTH = 24
MAX_TEXT_LENGTH = 4000
MAX_IMAGE_LENGTH = 10 * 1024 * 1024


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/favicon.ico")
def favicon():
    return send_file("favicon.ico", mimetype="image/x-icon", max_age=86400)


@app.route("/msg.ico")
def message_icon():
    return send_file("msg.ico", mimetype="image/x-icon", max_age=86400)


@sio.event
async def connect(sid, environ):
    await sio.emit("chat_history", list(messages)[-50:], to=sid)


@sio.on("set_nick")
async def handle_set_nick(sid, data):
    if not isinstance(data, dict):
        return
    nick = data.get("nick", "")
    if not isinstance(nick, str):
        return
    nick = nick.strip()
    if not nick or len(nick) > MAX_NICK_LENGTH:
        await sio.emit("nick_failed", {"reason": "Ник не может быть пустым"}, to=sid)
        return
    old_nick = users.get(sid)
    # Проверка: ник уже занят другим пользователем?
    for other_sid, existing_nick in users.items():
        if other_sid != sid and existing_nick.lower() == nick.lower():
            await sio.emit("nick_failed", {"reason": f"Ник «{nick}» уже занят"}, to=sid)
            return
    users[sid] = nick
    await sio.emit("nick_success", {"nick": nick}, to=sid)
    if old_nick is None:
        await sio.emit(
            "system",
            {"msg": f"👋 {nick} присоединился к чату"},
            skip_sid=sid,
        )
    elif old_nick != nick:
        await sio.emit(
            "system",
            {"msg": f"✏️ {old_nick} сменил ник на {nick}"},
            skip_sid=sid,
        )


@sio.on("send_message")
async def handle_message(sid, data):
    if not isinstance(data, dict):
        return
    text = data.get("text", "")
    image = data.get("image")  # base64 строка, может быть None
    reply_to = data.get("reply_to")  # {username, text, timestamp} или None
    if not isinstance(text, str) or not isinstance(image, (str, type(None))):
        return
    if reply_to is not None and not isinstance(reply_to, dict):
        return
    text = text.strip()
    if len(text) > MAX_TEXT_LENGTH or len(image or "") > MAX_IMAGE_LENGTH:
        await sio.emit("system", {"msg": "Сообщение или изображение слишком большое"}, to=sid)
        return
    if not text and not image:
        return
    nick = users.get(sid)
    if not nick:
        await sio.emit("system", {"msg": "Сначала установи никнейм"}, to=sid)
        return
    global message_id_counter
    message_id_counter += 1
    msg = {
        "id": message_id_counter,
        "username": nick,
        "text": text,
        "image": image,
        "reply_to": reply_to,
        "edited": False,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }
    messages.append(msg)
    print(f"[CHAT] {msg['timestamp']} | {msg['username']}: {msg['text'][:50]}{' [image]' if image else ''}")
    try:
        await sio.emit("new_message", msg)
    except Exception as e:
        print(f"Broadcast error: {e}")
        await sio.emit("system", {"msg": "Не удалось отправить сообщение (превышен размер)"}, to=sid)


@sio.on("edit_message")
async def handle_edit_message(sid, data):
    if not isinstance(data, dict):
        return
    msg_id = data.get("id")
    new_text = data.get("text", "")
    if not isinstance(msg_id, int) or not isinstance(new_text, str):
        return
    new_text = new_text.strip()
    if not new_text or len(new_text) > MAX_TEXT_LENGTH:
        await sio.emit("system", {"msg": "Текст сообщения не может быть пустым"}, to=sid)
        return
    nick = users.get(sid)
    if not nick:
        return
    for msg in messages:
        if msg.get("id") == msg_id:
            if msg.get("username") != nick:
                await sio.emit("system", {"msg": "Нельзя редактировать чужие сообщения"}, to=sid)
                return
            old_text = msg["text"]
            msg["text"] = new_text
            msg["edited"] = True
            msg["timestamp"] = datetime.now().strftime("%H:%M:%S")
            print(f"[EDIT] {msg['username']}: «{old_text[:50]}» → «{new_text[:50]}»")
            await sio.emit("message_edited", {"id": msg_id, "text": new_text, "timestamp": msg["timestamp"]})
            return
    await sio.emit("system", {"msg": "Сообщение не найдено"}, to=sid)


@sio.on("whisper_message")
async def handle_whisper(sid, data):
    if not isinstance(data, dict):
        return
    target_nick = data.get("target_nick", "")
    text = data.get("text", "")
    image = data.get("image")
    reply_to = data.get("reply_to")
    if not isinstance(target_nick, str) or not isinstance(text, str) or not isinstance(image, (str, type(None))):
        return
    if reply_to is not None and not isinstance(reply_to, dict):
        return
    text = text.strip()
    if not text and not image:
        return
    if len(text) > MAX_TEXT_LENGTH or len(image or "") > MAX_IMAGE_LENGTH:
        await sio.emit("system", {"msg": "Сообщение слишком большое"}, to=sid)
        return
    nick = users.get(sid)
    if not nick:
        return
    target_sid = None
    for other_sid, other_nick in users.items():
        if other_nick.lower() == target_nick.lower():
            target_sid = other_sid
            break
    if not target_sid or target_sid == sid:
        await sio.emit("system", {"msg": f"Пользователь «{target_nick}» не найден"}, to=sid)
        return
    msg = {
        "from": nick,
        "to": target_nick,
        "text": text,
        "image": image,
        "reply_to": reply_to,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }
    print(f"[WHISPER] {msg['from']} → {msg['to']}: {msg['text'][:50]}{' [image]' if image else ''}")
    await sio.emit("new_whisper", msg, to=sid)
    await sio.emit("new_whisper", msg, to=target_sid)


@sio.event
async def disconnect(sid):
    nick = users.pop(sid, None)
    if nick:
        await sio.emit("system", {"msg": f"👋 {nick} покинул чат"})


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run(
        asgi_app,
        host="0.0.0.0",
        port=port,
        timeout_graceful_shutdown=10,
    )
