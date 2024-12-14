from flask import Flask, request, jsonify, session, render_template
from flask_socketio import SocketIO, emit, join_room, disconnect
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_migrate import Migrate
from models import db, User, Game
from elo import calculate_elo
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
    username = request.args.get('username', 'Local Player')  # Или получайте username из сессии или другого источника
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

    return render_template('chess_ui.html', game_id=game_id, username=username)

@app.route('/register', methods=['POST'])
def register():
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
    logout_user()
    return jsonify({'message': 'Logged out successfully'}), 200

@app.route('/leaderboard')
def leaderboard():
    users = User.query.order_by(User.elorating.desc()).limit(10).all()
    leaderboard = [{'username': user.username, 'elorating': user.elorating} for user in users]
    return jsonify(leaderboard), 200

@app.route('/start_game')
@login_required
def start_game():
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
    player_white = User.query.get(game.player_white_id)
    player_black = User.query.get(game.player_black_id)
    new_white_elo, new_black_elo = calculate_elo(player_white.elorating, player_black.elorating, draw=True)
    player_white.elorating = new_white_elo
    player_black.elorating = new_black_elo
    game.result = 'draw'
    db.session.commit()

@socketio.on('offer_draw')
def handle_offer_draw(data):
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
    game_id = data.get('game_id')
    accept = data.get('accept')
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