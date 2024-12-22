import os
import sqlite3
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit

DB_NAME = 'users.db'

app = Flask(__name__)
app.config['SECRET_KEY'] = 'any-secret-key'  # нужен для SocketIO
CORS(app)

# Инициализируем SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

def init_db():
    """Создаём таблицы users и messages, если их ещё нет."""
    if not os.path.exists(DB_NAME):
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute('''
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT UNIQUE NOT NULL,
                    country TEXT,
                    city TEXT,
                    role TEXT,
                    language TEXT,
                    password TEXT,
                    latitude REAL,
                    longitude REAL
                )
            ''')
            c.execute('''
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender TEXT NOT NULL,
                    receiver TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

init_db()

# ---------- Эндпоинты для REST (регистрация / вход / получение списка пользователей) ----------

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    phone = data.get('phone')
    country = data.get('country')
    city = data.get('city')
    role = data.get('role')
    language = data.get('language')
    password = data.get('password')
    latitude = data.get('latitude')
    longitude = data.get('longitude')

    if not phone or not password:
        return jsonify({'error': 'Не все обязательные поля заполнены'}), 400

    try:
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO users (phone, country, city, role, language, password, latitude, longitude)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (phone, country, city, role, language, password, latitude, longitude))
            conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Пользователь с таким телефоном уже существует'}), 400

    return jsonify({'message': 'Пользователь успешно зарегистрирован!'}), 201


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    phone = data.get('phone')
    password = data.get('password')

    if not phone or not password:
        return jsonify({'error': 'Не все поля заполнены'}), 400

    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('SELECT phone, role FROM users WHERE phone=? AND password=?', (phone, password))
        row = c.fetchone()

    if row:
        # Получаем переписку пользователя
        c.execute('''
            SELECT sender, receiver, message, timestamp 
            FROM messages 
            WHERE sender=? OR receiver=?
            ORDER BY timestamp ASC
        ''', (phone, phone))
        messages = c.fetchall()
        messages_list = [
            {
                'sender': m[0],
                'receiver': m[1],
                'message': m[2],
                'timestamp': m[3]
            } for m in messages
        ]

        return jsonify({
            'message': 'Успешный вход',
            'user': {
                'phone': row[0],
                'role': row[1]
            },
            'messages': messages_list
        }), 200
    else:
        return jsonify({'error': 'Неверный логин или пароль'}), 401


@app.route('/users', methods=['GET'])
def get_users():
    """
    GET /users?role=Работодатель  -> список пользователей, у которых role='Работодатель'
    GET /users?role=Работник      -> список пользователей, у которых role='Работник'
    """
    role = request.args.get('role')
    if not role:
        return jsonify({'error': 'Параметр role не указан'}), 400

    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('SELECT phone, role FROM users WHERE role=?', (role,))
        rows = c.fetchall()

    result = []
    for r in rows:
        result.append({'phone': r[0], 'role': r[1]})

    return jsonify({'users': result}), 200


# ---------- Реалтайм-чат через SocketIO ----------

@socketio.on('connect')
def handle_connect():
    print("Клиент подключён к SocketIO")

@socketio.on('disconnect')
def handle_disconnect():
    print("Клиент отключился от SocketIO")

@socketio.on('send_message')
def handle_send_message(data):
    """
    data — словарь, например:
    {
      'sender': '111111',
      'receiver': '222222',
      'message': 'Привет!'
    }
    """
    sender = data.get('sender')
    receiver = data.get('receiver')
    message = data.get('message')

    if not sender or not receiver or not message:
        return emit('error', {'error': 'Некорректные данные'}), 400

    # Сохраняем сообщение в базу данных
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO messages (sender, receiver, message)
            VALUES (?, ?, ?)
        ''', (sender, receiver, message))
        conn.commit()

    # Рассылаем событие 'new_message' всем, кто подписан (broadcast=True)
    emit('new_message', data, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)

