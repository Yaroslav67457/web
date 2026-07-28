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
    msg = {
        "username": nick,
        "text": text,
        "image": image,
        "reply_to": reply_to,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }
    messages.append(msg)
    print(f"[CHAT] {msg['timestamp']} | {msg['username']}: {msg['text'][:50]}{' [image]' if image else ''}")
    try:
        await sio.emit("new_message", msg)
    except Exception as e:
        print(f"Broadcast error: {e}")
        await sio.emit("system", {"msg": "Не удалось отправить сообщение (превышен размер)"}, to=sid)


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
