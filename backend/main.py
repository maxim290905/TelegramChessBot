from flask import Flask, request, jsonify, session, render_template
from flask_socketio import SocketIO, emit, join_room, disconnect
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_migrate import Migrate
from backend.models import db, User, Game
from backend.elo import calculate_elo
from werkzeug.security import generate_password_hash, check_password_hash
import chess
import logging
import uuid
from collections import defaultdict
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv('SECRET_KEY', 'your_secret_key')
SQLALCHEMY_DATABASE_URI = os.getenv('SQLALCHEMY_DATABASE_URI', 'sqlite:///database.db')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:5000')

game_rooms = {}
games = {}

app = Flask(__name__,
            static_folder='static',
            template_folder='templates')

app.config['SECRET_KEY'] = SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
migrate = Migrate(app, db)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')
login_manager = LoginManager()
login_manager.init_app(app)

logging.basicConfig(level=logging.INFO)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.error(f'Unhandled exception: {e}', exc_info=True)
    return jsonify({'error': 'An unexpected error occurred.'}), 500

@app.errorhandler(404)
def page_not_found(e):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'error': 'Internal server error'}), 500

@app.route('/auth_token', methods=['POST'])
def auth_token():
    token = request.json.get('token')
    if not token:
        return jsonify({'error': 'No token provided'}), 400
    user = User.query.filter_by(auth_token=token).first()
    if not user:
        return jsonify({'error': 'Invalid token'}), 400
    login_user(user)
    user.revoke_auth_token()
    return jsonify({'message': 'Authenticated'}), 200

@app.route('/play')
def play():
    """
    Обрабатывает запрос на начало игры в шахматы и отображение соответствующего интерфейса.

    Эта функция отвечает за обработку запроса для начала игры в шахматы, включая проверку авторизации пользователя, 
    его участия в конкретной игре, а также отображение UI игры на основе того, является ли пользователь локальным 
    игроком или участвует в онлайн-игре. В случае ошибки возвращается сообщение об ошибке с соответствующим кодом.

    Аргументы:
        Нет.

    Возвращает:
        - Если пользователь является локальным игроком: отображение локального интерфейса игры.
        - Если пользователь участвует в онлайн-игре и все данные корректны: отображение интерфейса игры с данными о текущей игре.
        - В случае ошибки (отсутствие токена, неправильного токена, отсутствия игры, или если игрок не является участником игры): 
          возвращается JSON-ответ с описанием ошибки и соответствующим статусом.

    Ошибки:
        400 Bad Request: Если отсутствуют обязательные параметры запроса, такие как "game_id" или "token", или если токен неверный.
        403 Forbidden: Если пользователь не является участником указанной игры.
        404 Not Found: Если игра с указанным "game_id" не найдена.

    Примечания:
        - Параметр `username` можно получить из запроса или сессии. Если он не предоставлен, используется значение по умолчанию "Local Player".
        - Параметр `local` указывает, является ли пользователь локальным игроком (без подключения к онлайн-игре). Если параметр "local=true", показывается интерфейс для локальной игры.
        - Для проверки подлинности используется токен, переданный в параметре запроса `token`, который сверяется с базой данных для нахождения пользователя.
    """
    username = request.args.get('username', 'Local Player') 
    game_id = request.args.get('game_id')
    token = request.args.get('token')
    is_local = request.args.get('local') == 'true'

    if is_local:
        return render_template('chess_ui.html', local=True, username='Local Player')

    if not game_id or not token:
        return jsonify({'error': 'Missing game_id or token'}), 400

    user = User.query.filter_by(auth_token=token).first()
    if not user:
        return jsonify({'error': 'Invalid token'}), 400

    login_user(user)
    game = Game.query.get(game_id)
    if not game:
        return jsonify({'error': 'Game not found'}), 404

    if user.id not in [game.player_white_id, game.player_black_id]:
        return jsonify({'error': 'You are not part of this game'}), 403

    return render_template('chess_ui.html', game_id=game_id, username=user.username)


@app.route('/register', methods=['POST'])
def register():
    """
    Обрабатывает запрос на регистрацию нового пользователя.

    Эта функция принимает имя пользователя и пароль, проверяет их наличие и уникальность, 
    а затем создает нового пользователя в базе данных. В случае успешной регистрации возвращается
    сообщение об успешной регистрации. В случае ошибок (отсутствие данных или дублирование имени пользователя)
    возвращается сообщение с ошибкой и соответствующий код HTTP.

    Аргументы:
        Нет.

    Возвращает:
        - Если регистрация прошла успешно: JSON-ответ с сообщением об успешной регистрации и кодом статуса 200.
        - Если имя пользователя или пароль не указаны: JSON-ответ с сообщением об ошибке и кодом статуса 400.
        - Если имя пользователя уже существует: JSON-ответ с сообщением об ошибке и кодом статуса 400.

    Ошибки:
        400 Bad Request: Если не указаны имя пользователя или пароль, либо если имя пользователя уже существует.

    Примечания:
        - Пароль сохраняется в базе данных в зашифрованном виде с использованием метода "set_password".
        - После создания нового пользователя, изменения сохраняются в базе данных с помощью "db.session.commit".
    """
    username = request.form.get('username')
    password = request.form.get('password')
    if not username or not password:
        return jsonify({'message': 'Username and password are required.'}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({'message': 'Username already exists'}), 400
    user = User(username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return jsonify({'message': 'Registration successful'}), 200


@app.route('/login', methods=['POST'])
def login():
    """
    Обрабатывает запрос на вход пользователя (логин) в систему.

    Эта функция принимает имя пользователя и пароль, проверяет их наличие и корректность, 
    а затем выполняет вход пользователя в систему. Если данные правильные, пользователю 
    генерируется токен авторизации, который возвращается в ответе. В случае ошибки (неверные данные)
    возвращается сообщение об ошибке.

    Аргументы:
        Нет.

    Возвращает:
        - Если вход успешен (имя пользователя и пароль верные): JSON-ответ с сообщением о успешном входе и 
          токеном авторизации, а также кодом статуса 200.
        - Если имя пользователя или пароль не указаны: JSON-ответ с сообщением об ошибке и кодом статуса 400.
        - Если учетные данные неверны (неправильное имя пользователя или пароль): JSON-ответ с сообщением 
          об ошибке и кодом статуса 400.

    Ошибки:
        400 Bad Request: Если не указаны имя пользователя или пароль, либо если учетные данные неверны.

    Примечания:
        - Для проверки пароля используется метод `check_password`, который сравнивает введенный пароль с 
          сохраненным в базе данных.
        - Если вход успешен, токен авторизации генерируется с помощью метода "generate_auth_token".
    """
    username = request.form.get('username')
    password = request.form.get('password')
    if not username or not password:
        return jsonify({'message': 'Username and password are required.'}), 400
    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        login_user(user)
        token = user.generate_auth_token()
        return jsonify({'message': 'Login successful', 'auth_token': token}), 200
    else:
        return jsonify({'message': 'Invalid credentials'}), 400


@app.route('/logout')
@login_required
def logout():
    """
    Обрабатывает запрос на выход пользователя из системы.

    Эта функция выполняет выход текущего пользователя из системы, 
    удаляя его сеанс и, при необходимости, аннулируя токен авторизации.

    Аргументы:
        Нет.

    Возвращает:
        - Если выход успешен: JSON-ответ с сообщением о успешном выходе и кодом статуса 200.
        - Если возникла ошибка при выходе: JSON-ответ с сообщением об ошибке и кодом статуса 400.

    Ошибки:
        400: Если возникла ошибка при выполнении выхода.
        
    Примечания:
        - Используется декоратор @login_required для обеспечения доступа только авторизованным пользователям.
        - Метод logout_user() из Flask-Login выполняет выход пользователя.
        - Если используется токен авторизации, он должен быть аннулирован или удален здесь.
    """
    try:
        # Аннулируем токен авторизации, если используется
        if current_user.auth_token:
            current_user.revoke_auth_token()
            db.session.commit()
        
        # Выполняем выход пользователя
        logout_user()
        return jsonify({'message': 'Logged out successfully.'}), 200
    except Exception as e:
        # Логирование ошибки (опционально)
        app.logger.error(f"Logout failed: {e}")
        return jsonify({'message': 'An error occurred during logout.'}), 400

@app.route('/leaderboard')
def leaderboard():
    """
    Получает список лучших 10 пользователей по рейтингу Elo.

    Эта функция извлекает из базы данных 10 пользователей с наивысшими рейтингами Elo и возвращает их имена 
    и рейтинги в формате JSON. Рейтинг пользователей сортируется по убыванию, так что первым идет пользователь 
    с наивысшим рейтингом.

    Аргументы:
        Нет.

    Возвращает:
        - JSON-ответ, содержащий список из 10 пользователей с их именами и рейтингами Elo.
        - статус 200.

    Примечания:
        - Рейтинг Elo (параметр "elorating") сортируется в порядке убывания, так что на первом месте находится пользователь с самым высоким рейтингом.
    """
    users = User.query.order_by(User.elorating.desc()).limit(10).all()
    leaderboard = [{'username': user.username, 'elorating': user.elorating} for user in users]
    return jsonify(leaderboard), 200


@app.route('/start_game')
@login_required
def start_game():
    """
    Начинает новую игру или присоединяет пользователя к ожидающей игре.

    Эта функция ищет активную игру, которая ожидает второго игрока (is_waiting=True). Если такая игра найдена,
    текущий пользователь присоединяется к игре в качестве черного игрока (player_black_id). Если игры в ожидании нет,
    создается новая игра, где текущий пользователь становится белым игроком (player_white_id). В обоих случаях 
    возвращается информация о начале игры, включая идентификатор игры, цвет игрока и токен авторизации.

    Аргументы:
        Нет.

    Возвращает:
        - JSON-ответ с сообщением о подготовке игры, идентификатором игры, токеном авторизации и цветом игрока.
        - статус 200.

    Примечания:
        - Для времени игры устанавливается начальное значение в 10 минут (600 секунд) для обоих игроков.
        - Время последнего хода обновляется на текущий момент времени.
        - В случае создания новой игры, используется начальная позиция с помощью библиотеки "chess".
        - Генерируется токен авторизации для текущего пользователя, который может быть использован для аутентификации в будущем.
    """
    pending_game = Game.query.filter_by(is_active=True, is_waiting=True).first()
    if pending_game:
        pending_game.player_black_id = current_user.id
        pending_game.is_waiting = False
        pending_game.time_left_white = 600
        pending_game.time_left_black = 600
        pending_game.last_move_time = datetime.utcnow()
        db.session.commit()
        game_id = pending_game.id
        your_color = 'black'
    else:
        new_game = Game(
            player_white_id=current_user.id,
            is_waiting=True,
            fen=chess.Board().fen(),
            time_left_white=600,
            time_left_black=600,
            last_move_time=datetime.utcnow()  # Добавлено поле
        )
        db.session.add(new_game)
        db.session.commit()
        game_id = new_game.id
        your_color = 'white'

    token = current_user.generate_auth_token()

    return jsonify({
        'message': 'Game ready',
        'game_id': game_id,
        'auth_token': token,
        'your_color': your_color
    }), 200


@socketio.on('connect')
def handle_connect():
    """
    Обрабатывает подключение пользователя к игре через WebSocket.

    Эта функция проверяет наличие и корректность токена аутентификации и идентификатора игры, полученных
    через параметры запроса. Если данные корректны, устанавливается связь между пользователем и игрой, 
    а также сохраняется информация в сессии. В случае ошибки (отсутствие данных или неверный токен) 
    отправляется сообщение об ошибке и происходит отключение пользователя.

    Аргументы:
        Нет.

    Возвращает:
        - В случае успеха отправляется событие с состоянием подключения пользователя.
        - В случае ошибки отправляется сообщение об ошибке и происходит отключение.

    Примечания:
        - Используется библиотека "logging" для записи события подключения пользователя.
        - Информация о подключении сохраняется в сессии для дальнейшего использования.
    """
    token = request.args.get('token')
    game_id = request.args.get('game_id')
    if not token or not game_id:
        emit('error', {'message': 'Authentication token and game_id required.'})
        disconnect()
        return
    user = User.query.filter_by(auth_token=token).first()
    if not user:
        emit('error', {'message': 'Invalid authentication token.'})
        disconnect()
        return
    session['user_id'] = user.id
    session['game_id'] = game_id
    emit('status', {'message': f'User {user.username} connected to game {game_id}.'})
    logging.info(f'User {user.username} connected to game {game_id}.')


@socketio.on('join_game')
def handle_join_game(data):
    """
    Обрабатывает запрос пользователя на присоединение к игре.

    Эта функция проверяет наличие идентификатора игры (`game_id`) и аутентификацию пользователя, 
    а затем пытается присоединить пользователя к активной игре. Если пользователь является частью игры, 
    он присоединяется к соответствующей комнате WebSocket. После этого, если оба игрока присоединились, 
    начинается сама игра.

    Аргументы:
        data (dict): Данные запроса, которые должны содержать ключ `game_id`, идентифицирующий игру.

    Возвращает:
        - В случае ошибки отправляется событие `error` с соответствующим сообщением.
        - В случае успеха пользователю отправляется событие `status` о том, что он присоединился к игре.
        - Если оба игрока присоединились, отправляется событие `game_started` с информацией о начале игры.
    """
    game_id = data.get('game_id')
    if not game_id:
        emit('error', {'message': 'No game_id provided.'})
        return

    user_id = session.get('user_id')
    if not user_id:
        emit('error', {'message': 'User not authenticated.'})
        return

    user = db.session.get(User, user_id)
    if not user:
        emit('error', {'message': 'User not found.'})
        return

    game = db.session.get(Game, game_id)
    if not game or not game.is_active:
        emit('error', {'message': 'Invalid game.'})
        return

    if user.id not in [game.player_white_id, game.player_black_id]:
        emit('error', {'message': 'You are not part of this game.'})
        return

    room = str(game_id)
    join_room(room)
    if room not in game_rooms:
        game_rooms[room] = set()
    game_rooms[room].add(user.id)
    emit('status', {'message': f'Joined game {game_id}.'}, room=room)
    logging.info(f'User {user.username} joined game {game_id}. Total players: {len(game_rooms[room])}')

    if room not in games:
        games[room] = chess.Board()

    if len(game_rooms[room]) == 2:
        player_white = db.session.get(User, game.player_white_id)
        player_black = db.session.get(User, game.player_black_id)
        emit('game_info', {
            'player_white': {'username': player_white.username, 'elorating': player_white.elorating},
            'player_black': {'username': player_black.username, 'elorating': player_black.elorating}
        }, room=room)
        emit('game_started', {
            'message': 'Both players have joined. Let\'s start the game!',
            'current_turn': 'white',
            'time_left_white': game.time_left_white,
            'time_left_black': game.time_left_black,
            'fen': games[room].fen(),
            'player_white': {'username': player_white.username, 'elorating': player_white.elorating},
            'player_black': {'username': player_black.username, 'elorating': player_black.elorating}
        }, room=room)
        logging.info(f'Game {game_id} started.')


@socketio.on('move')
def handle_move(data):
    """
    Обрабатывает ход в игре и обновляет состояние игры, включая время, позицию и результат.

    Эта функция принимает ход пользователя, проверяет его корректность и применяет его к текущей позиции
    на шахматной доске. После выполнения хода обновляется время оставшееся у игроков, и если одно из
    условий окончания игры выполнено, отправляется сообщение о завершении игры. В противном случае,
    ход выполняется, и игра продолжается.

    Аргументы:
        data (dict): Данные запроса, содержащие информацию о ходе.
            - 'game_id' (str): Идентификатор игры.
            - 'move' (dict): Ход в формате { 'from': <start_square>, 'to': <end_square> }.

    Возвращает:
        - В случае ошибки отправляется "error" с соответствующим сообщением.
        - В случае успешного хода отправляется событие `move` с информацией о новом состоянии игры.
        - Если игра завершена (мат, ничья или по времени), отправляется событие `game_over` с результатом игры.
    """
    game_id = data.get('game_id')
    move = data.get('move')
    if not game_id or not move:
        emit('error', {'message': 'Missing game_id or move.'})
        return

    room = str(game_id)
    if room not in games:
        emit('error', {'message': 'Invalid game.'})
        return

    game = db.session.get(Game, game_id)
    if not game or not game.is_active:
        emit('error', {'message': 'Invalid game.'})
        return

    board = games[room]

    current_time = datetime.utcnow()
    elapsed = (current_time - game.last_move_time).total_seconds()
    game.last_move_time = current_time

    current_turn_color = 'white' if board.turn == chess.WHITE else 'black'
    if current_turn_color == 'white':
        game.time_left_white -= int(elapsed)
        if game.time_left_white <= 0:
            game.time_left_white = 0
            game.is_active = False
            game.result = 'black'
            db.session.commit()
            emit('move', {
                'move': move,
                'current_turn': 'none',
                'time_left_white': game.time_left_white,
                'time_left_black': game.time_left_black,
                'fen': board.fen()
            }, room=room, include_self=False)
            emit('game_over', {'result': 'Black wins on time'}, room=room)
            update_game_over(game, board)
            return
    else:
        game.time_left_black -= int(elapsed)
        if game.time_left_black <= 0:
            game.time_left_black = 0
            game.is_active = False
            game.result = 'white'
            db.session.commit()
            emit('move', {
                'move': move,
                'current_turn': 'none',
                'time_left_white': game.time_left_white,
                'time_left_black': game.time_left_black,
                'fen': board.fen()
            }, room=room, include_self=False)
            emit('game_over', {'result': 'White wins on time'}, room=room)
            update_game_over(game, board)
            return

    uci_move = move['from'] + move['to']
    try:
        chess_move = chess.Move.from_uci(uci_move)
    except ValueError:
        emit('error', {'message': 'Invalid move format.'})
        return

    if chess_move not in board.legal_moves:
        emit('error', {'message': 'Illegal move.'})
        return

    board.push(chess_move)
    game.fen = board.fen()
    db.session.commit()

    if board.is_game_over():
        if board.is_checkmate():
            winner = 'white' if board.turn == chess.BLACK else 'black'
            result_message = f'{winner.capitalize()} wins by checkmate.'
        elif board.is_stalemate():
            result_message = 'Game drawn by stalemate.'
        elif board.is_insufficient_material():
            result_message = 'Game drawn due to insufficient material.'
        elif board.is_seventyfive_moves():
            result_message = 'Game drawn by seventy-five moves rule.'
        elif board.is_fivefold_repetition():
            result_message = 'Game drawn by fivefold repetition.'
        else:
            result_message = 'Game over.'

        emit('move', {
            'move': move,
            'current_turn': 'none',
            'time_left_white': game.time_left_white,
            'time_left_black': game.time_left_black,
            'fen': board.fen()
        }, room=room, include_self=False)
        emit('game_over', {
            'result': result_message
        }, room=room)

        update_game_over(game, board)
    else:
        next_turn = 'black' if board.turn == chess.BLACK else 'white'
        db.session.commit()
        emit('move', {
            'move': move,
            'current_turn': next_turn,
            'time_left_white': game.time_left_white,
            'time_left_black': game.time_left_black,
            'fen': board.fen()
        }, room=room, include_self=False)


def update_game_over(game, board):
    """
    Обновляет результаты игры, а также рейтинги игроков, в зависимости от итогового состояния игры.

    Эта функция вызывается после завершения игры (победа, ничья или другой результат) и выполняет следующие действия:
    1. Обновляет рейтинги игроков в зависимости от результата игры.
    2. Обновляет статус игры в базе данных, помечая игру как завершенную.
    3. Логирует завершение игры с результатом.

    Аргументы:
        game (Game): Объект игры, содержащий информацию о текущем состоянии игры, игроках и результате.
        board (chess.Board): Объект шахматной доски, представляющий текущую позицию игры.

    Возвращает:
        None

    Пример:
        В случае, если игра завершена с матом:
        update_game_over(game, board)
        Логирует: "Game 123 ended with result: white"
        Обновляет рейтинги игроков: побеждает белый, проигрывает черный.

    Примечания:
        - Если игра завершилась матом, обновляются рейтинги победителя и проигравшего.
        - В случае, если результат игры был заранее установлен как победа одного из игроков или ничья, рейтинги также обновляются в соответствии с этим результатом.
        - Игра помечается как завершенная в базе данных, и статус игры изменяется на "is_active = False".
    Логирование:
        - Вся информация о завершении игры (с указанием идентификатора игры и ее результата) логируется для дальнейшего мониторинга.
    """
    if board.is_checkmate():
        winner = 'white' if board.turn == chess.BLACK else 'black'
        loser = 'black' if winner == 'white' else 'white'
        update_ratings_on_win(game, winner, loser)
    elif board.is_stalemate() or board.is_insufficient_material() or board.is_seventyfive_moves() or board.is_fivefold_repetition():
        update_ratings_on_draw(game)
    else:
        if game.result == 'white':
            update_ratings_on_win(game, 'white', 'black')
        elif game.result == 'black':
            update_ratings_on_win(game, 'black', 'white')
        elif game.result == 'draw':
            update_ratings_on_draw(game)

    game.is_active = False
    db.session.commit()
    logging.info(f'Game {game.id} ended with result: {game.result}')


def update_ratings_on_win(game, winner_color, loser_color):
    """
    Обновляет рейтинги игроков (ELO) после победы одного из участников игры.

    Эта функция обновляет ELO-рейтинги победителя и проигравшего, а также увеличивает количество побед
    и поражений каждого игрока в базе данных. Рейтинги вычисляются с использованием функции "calculate_elo()",
    и игра помечается с результатом победителя. После выполнения изменений данные сохраняются в базе.

    Аргументы:
        game (Game): Объект игры, содержащий информацию о игроках и результатах.
        winner_color (str): Цвет победителя, который может быть 'white' или 'black'.
        loser_color (str): Цвет проигравшего, который может быть 'black' или 'white'.

    Возвращает:
        None

    Примечания:
        - Функция использует цвет победителя ("winner_color") и проигравшего ("loser_color") для выбора
          соответствующих игроков и вычисления новых ELO-рейтингов.

    Пример:
        В случае, если победил игрок с белыми фигурами, функция обновит рейтинги следующим образом:
        update_ratings_on_win(game, 'white', 'black')
        - Рейтинги игроков обновятся в базе.
        - Количество побед белого игрока и поражений черного увеличится на 1.
        - Статус игры будет обновлен с результатом 'white'.
    """
    if winner_color == 'white':
        winner = User.query.get(game.player_white_id)
        loser = User.query.get(game.player_black_id)
    else:
        winner = User.query.get(game.player_black_id)
        loser = User.query.get(game.player_white_id)
    
    new_winner_elo, new_loser_elo = calculate_elo(winner.elorating, loser.elorating)
    
    winner.elorating = new_winner_elo
    loser.elorating = new_loser_elo

    winner.wins += 1
    loser.losses += 1

    game.result = winner_color
    db.session.commit()


def update_ratings_on_draw(game):
    """
    Обновляет рейтинги игроков (ELO) в случае ничьей.

    Эта функция обновляет ELO-рейтинги для обоих игроков после ничьей в игре. Рейтинги вычисляются
    с использованием функции "calculate_elo()", которая учитывает ничью как результат. Также результат игры
    устанавливается как 'draw' в объекте игры.

    Аргументы:
        game (Game): Объект игры, содержащий информацию о игроках и результате игры.

    Возвращает:
        None

    Пример:
        В случае ничьей между игроками:
        update_ratings_on_draw(game)
        - Рейтинги обоих игроков обновляются с учетом ничьей.
        - Результат игры устанавливается как 'draw'.
    """
    player_white = User.query.get(game.player_white_id)
    player_black = User.query.get(game.player_black_id)
    
    new_white_elo, new_black_elo = calculate_elo(player_white.elorating, player_black.elorating, draw=True)
    
    player_white.elorating = new_white_elo
    player_black.elorating = new_black_elo

    game.result = 'draw'
    db.session.commit()


@socketio.on('offer_draw')
def handle_offer_draw(data):
    """
    Обрабатывает предложение ничьей от одного из игроков в игре.

    Эта функция обрабатывает запрос на предложение ничьей от игрока. Если предложение отправляется от игрока,
    который участвует в игре, оно будет отправлено другому игроку. Если запрос некорректен (например, игрок не
    аутентифицирован или не является участником игры), будет отправлено сообщение об ошибке.

    Аргументы:
        data (dict): Данные, передаваемые с предложением ничьей. Ожидается, что в данных будет содержаться
                     ключ "game_id", который указывает на игру, в которой предлагается ничья.

    Возвращает:
        None

    Примечания:
        - Функция проверяет наличие аутентификационного токена пользователя, а также его участие в указанной игре.
        - Если игрок, отправивший запрос, является одним из участников игры, ему будет отправлено сообщение о предложении ничьей.
        - В случае ошибок (отсутствие "game_id", неаутентифицированный пользователь, неучастие в игре) будет отправлено сообщение об ошибке.

    """
    game_id = data.get('game_id')
    if not game_id:
        emit('error', {'message': 'No game_id provided.'})
        return

    user_id = session.get('user_id')
    if not user_id:
        emit('error', {'message': 'User not authenticated.'})
        return

    game = db.session.get(Game, game_id)
    if not game or not game.is_active:
        emit('error', {'message': 'Invalid game'})
        return

    if user_id == game.player_white_id:
        from_player = 'white'
    elif user_id == game.player_black_id:
        from_player = 'black'
    else:
        emit('error', {'message': 'You are not part of this game.'})
        return

    emit('draw_offer', {'from_player': from_player}, room=str(game_id), include_self=False)


@socketio.on('draw_response')
def handle_draw_response(data):
    """
    Обрабатывает ответ на предложение ничьей от одного из игроков в игре.

    Эта функция проверяет ответ игрока на предложение ничьей, отправленное другим игроком. Если игрок принимает ничью,
    игра завершится, результат будет установлен как ничья, и рейтинги игроков обновятся. Если игрок отклоняет предложение,
    это будет отправлено другому игроку.

    Аргументы:
        data (dict): Данные, передаваемые с ответом на предложение ничьей. Ожидается, что в данных будут содержаться:
                     - `game_id` (str): Идентификатор игры.
                     - `accept` (bool): Флаг, указывающий, принимает ли игрок предложение ничьей (`True`) или отклоняет его (`False`).

    Возвращает:
        None

    Примечания:
        - Если игрок принимает ничью, игра будет завершена, результат будет установлен как ничья, и рейтинги игроков обновятся.
        - Если игрок отклоняет предложение, отправляется уведомление другому игроку о том, что ничья отклонена.
    """
    game_id = data.get('game_id')
    accept = data.get('accept')

    # Проверка наличия обязательных параметров
    if not game_id or accept is None:
        emit('error', {'message': 'Missing game_id or accept flag.'})
        return

    game = db.session.get(Game, game_id)
    if not game or not game.is_active:
        emit('error', {'message': 'Invalid game'})
        return

    user_id = session.get('user_id')
    if not user_id:
        emit('error', {'message': 'User not authenticated.'})
        return

    # Обработка ответа на предложение ничьей
    if accept:
        game.is_active = False
        game.result = 'draw'
        
        player_white = db.session.get(User, game.player_white_id)
        player_black = db.session.get(User, game.player_black_id)
        new_white_elo, new_black_elo = calculate_elo(player_white.elorating, player_black.elorating, draw=True)
        player_white.elorating = new_white_elo
        player_black.elorating = new_black_elo
        
        db.session.commit()
        
        emit('game_over', {'result': 'draw'}, room=str(game_id))
    else:
        emit('draw_response', {'accept': False}, room=str(game_id))


@socketio.on('resign')
def handle_resign(data):
    """
    Обрабатывает процесс сдачи игроком в игре.

    Эта функция позволяет игроку сдаться в игре. В случае сдачи, игра завершается, и противник выигрывает. Рейтинг игрока,
    сдавшегося, обновляется, а противнику начисляется победа. Если пользователь не является участником игры или игра
    недействительна, отправляется ошибка.

    Аргументы:
        data (dict): Данные, передаваемые с запросом на сдачу. Ожидается, что в данных будут содержаться:
                     - `game_id` (str): Идентификатор игры, в которой игрок сдается.

    Возвращает:
        None
    """
    game_id = data.get('game_id')
    
    if not game_id:
        emit('error', {'message': 'No game_id provided.'})
        return

    game = db.session.get(Game, game_id)
    if not game or not game.is_active:
        emit('error', {'message': 'Invalid game'})
        return

    user_id = session.get('user_id')
    if not user_id:
        emit('error', {'message': 'User not authenticated.'})
        return

    player_white = db.session.get(User, game.player_white_id)
    player_black = db.session.get(User, game.player_black_id)
   
    if user_id == player_white.id:
        game.result = 'black'  
        player_black.wins += 1
        player_white.losses += 1
        new_black_elo, new_white_elo = calculate_elo(player_black.elorating, player_white.elorating)
        player_black.elorating = new_black_elo
        player_white.elorating = new_white_elo
    elif user_id == player_black.id:
        game.result = 'white' 
        player_white.wins += 1
        player_black.losses += 1
        new_white_elo, new_black_elo = calculate_elo(player_white.elorating, player_black.elorating)
        player_white.elorating = new_white_elo
        player_black.elorating = new_black_elo
    else:
        emit('error', {'message': 'You are not part of this game.'})
        return

    game.is_active = False
    db.session.commit()
    emit('game_over', {'result': game.result}, room=str(game_id))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True, port=5000)