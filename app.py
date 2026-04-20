from flask import Flask
from flask_socketio import SocketIO, emit
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

users = {}
messages = []

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
    # Не спамим системой о подключении, чтобы не бесило

@socketio.on('send_message')
def handle_message(data):
    text = data.get('text', '').strip()
    if not text:
        return
    nick = users.get(request.sid)
    if not nick:
        emit('system', {'msg': 'Сначала установи никнейм'})
        return
    msg = {
        'username': nick,
        'text': text,
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
    socketio.run(app, host='0.0.0.0', port=port)
