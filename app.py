from flask import Flask, request
from flask_socketio import SocketIO, emit
from datetime import datetime
import os
import base64

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

users = {}
messages = []  # храним последние 100 сообщений (текст + изображения)

@app.route('/')
def index():
    with open('index.html', 'r', encoding='utf-8') as f:
        return f.read()

@socketio.on('connect')
def handle_connect():
    emit('chat_history', messages[-50:])

@socketio.on('set_nick')
def handle_set_nick(data):
    nick = data.get('nick', '').strip()
    if not nick:
        emit('nick_failed', {'reason': 'Ник не может быть пустым'})
        return
    users[request.sid] = nick
    emit('nick_success', {'nick': nick})

@socketio.on('send_message')
def handle_message(data):
    text = data.get('text', '').strip()
    image = data.get('image')  # base64 строка, если есть
    if not text and not image:
        return
    nick = users.get(request.sid)
    if not nick:
        emit('system', {'msg': 'Сначала установи никнейм'})
        return
    msg = {
        'username': nick,
        'text': text,
        'image': image,  # может быть None или base64
        'timestamp': datetime.now().strftime('%H:%M:%S')
    }
    messages.append(msg)
    if len(messages) > 100:
        messages.pop(0)
    emit('new_message', msg, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    nick = users.pop(request.sid, None)
    if nick:
        emit('system', {'msg': f'👋 {nick} покинул чат'}, broadcast=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
