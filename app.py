from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit, send
import os
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

# Хранилище пользователей: { sid: nickname }
users = {}

# Хранилище сообщений (последние 100)
messages = []

@app.route('/')
def index():
    # Читаем HTML файл (можно вернуть как строку, но проще отдельным файлом)
    with open('index.html', 'r', encoding='utf-8') as f:
        return f.read()

@socketio.on('connect')
def handle_connect():
    print(f'Client connected: {request.sid}')
    # Отправить новому клиенту историю сообщений
    emit('chat_history', messages[-50:])

@socketio.on('set_nick')
def handle_set_nick(data):
    nick = data.get('nick', '').strip()
    if not nick:
        emit('nick_failed', {'reason': 'Ник не может быть пустым'})
        return
    if len(nick) > 24:
        nick = nick[:24]
    old_nick = users.get(request.sid)
    users[request.sid] = nick
    emit('nick_success', {'nick': nick})
    # Оповестить всех о новом пользователе, если он не был зарегистрирован ранее
    if not old_nick:
        broadcast_system_message(f'👤 {nick} присоединился к чату', namespace='/')
    else:
        broadcast_system_message(f'✏️ {old_nick} сменил ник на {nick}', namespace='/')

@socketio.on('send_message')
def handle_message(data):
    text = data.get('text', '').strip()
    if not text:
        return
    nick = users.get(request.sid)
    if not nick:
        emit('system', {'msg': 'Сначала установите никнейм через кнопку'})
        return
    msg_data = {
        'username': nick,
        'text': text,
        'timestamp': datetime.now().strftime('%H:%M:%S')
    }
    messages.append(msg_data)
    if len(messages) > 100:
        messages.pop(0)
    emit('new_message', msg_data, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    nick = users.pop(request.sid, None)
    if nick:
        broadcast_system_message(f'👋 {nick} покинул чат', namespace='/')

def broadcast_system_message(msg, namespace='/'):
    socketio.emit('system', {'msg': msg}, namespace=namespace)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
