# chessbot_test.py

#=========================================  models.py  ===============================================

from telegram import InlineKeyboardMarkup
from telegram.ext import ConversationHandler
from backend.main import BASE_URL, app as flask_app, db, leaderboard, socketio, update_ratings_on_win, update_ratings_on_draw
import json
import chess
from flask_socketio import SocketIOTestClient

import pytest
from flask import Flask, session
from backend.models import db, User, Game
from werkzeug.security import check_password_hash
import uuid
from datetime import datetime, timedelta

from backend.main import app as flask_app, db, socketio, update_ratings_on_win, update_ratings_on_draw
import json
import chess
from flask_socketio import SocketIOTestClient

import pytest
from flask import session
from backend.models import User, Game
from werkzeug.security import check_password_hash
import uuid
from datetime import datetime

from backend.bot import FRONTEND_URL, LOGIN_PASSWORD, LOGIN_USERNAME, REGISTER_PASSWORD, REGISTER_USERNAME, cancel, login, login_password, login_username, logout, playlocal, register, register_password, register_username, start

@pytest.fixture
def app():
    """Create and configure a new app instance for each test."""
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'  # Use in-memory database for testing
    flask_app.config['TESTING'] = True
    flask_app.config['SECRET_KEY'] = 'testsecretkey'
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    flask_app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF protection in testing
    flask_app.config['LOGIN_DISABLED'] = False

    db.init_app(flask_app)
    socketio.init_app(flask_app)  # Add this line to initialize SocketIO with the test app

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def test_client(app):
    """A test client for the app."""
    return app.test_client()

@pytest.fixture
def client(test_client):
    """An alias test client for the app."""
    return test_client

@pytest.fixture
def runner(app):
    """A test runner for the app's Click commands."""
    return app.test_cli_runner()

def login_test_user(test_client, username, password):
    response = test_client.post('/login', data={
        'username': username,
        'password': password
    })
    return response

def test_set_password(app):
    """Test that the password is hashed and set correctly."""
    with app.app_context():
        user = User(username='testuser')
        user.set_password('testpassword')
        assert user.password_hash is not None
        assert user.password_hash != 'testpassword'
        assert check_password_hash(user.password_hash, 'testpassword')

def test_check_password(app):
    """Test that password checking works correctly."""
    with app.app_context():
        user = User(username='testuser')
        user.set_password('testpassword')
        assert user.check_password('testpassword') is True
        assert user.check_password('wrongpassword') is False

def test_generate_auth_token(app):
    """Test that generating an auth token works correctly."""
    with app.app_context():
        user = User(username='testuser')
        user.set_password('testpassword')  # Set the password
        db.session.add(user)
        db.session.commit()
        token = user.generate_auth_token()
        assert user.auth_token == token
        # Validate that the token is a valid UUID
        try:
            uuid_obj = uuid.UUID(token, version=4)
        except ValueError:
            assert False, "The auth token is not a valid UUID."

def test_revoke_auth_token(app):
    """Test that revoking the auth token works correctly."""
    with app.app_context():
        user = User(username='testuser')
        user.set_password('testpassword')  # Set the password
        db.session.add(user)
        db.session.commit()
        user.generate_auth_token()
        assert user.auth_token is not None
        user.revoke_auth_token()
        assert user.auth_token is None

#=========================================  main.py  ===============================================

def test_register(test_client):
    response = test_client.post('/register', data={
        'username': 'testuser',
        'password': 'testpass'
    })
    data = json.loads(response.data)
    assert response.status_code == 200
    assert data['message'] == 'Registration successful'

    # Attempt to register the same user again
    response = test_client.post('/register', data={
        'username': 'testuser',
        'password': 'testpass'
    })
    data = json.loads(response.data)
    assert response.status_code == 400
    assert data['message'] == 'Username already exists'

def test_login(test_client):
    # First, register a user
    test_client.post('/register', data={
        'username': 'testuser',
        'password': 'testpass'
    })

    # Now, try to login
    response = test_client.post('/login', data={
        'username': 'testuser',
        'password': 'testpass'
    })
    data = json.loads(response.data)
    assert response.status_code == 200
    assert data['message'] == 'Login successful'
    assert 'auth_token' in data

    # Try to login with invalid credentials
    response = test_client.post('/login', data={
        'username': 'testuser',
        'password': 'wrongpass'
    })
    data = json.loads(response.data)
    assert response.status_code == 400
    assert data['message'] == 'Invalid credentials'

def test_auth_token(test_client):
    # Register and get auth_token
    response = test_client.post('/register', data={
        'username': 'testuser2',
        'password': 'testpass'
    })
    response = test_client.post('/login', data={
        'username': 'testuser2',
        'password': 'testpass'
    })
    data = json.loads(response.data)
    assert 'auth_token' in data  # Ensure auth_token is in response
    token = data['auth_token']

    # Use auth_token to authenticate
    response = test_client.post('/auth_token', json={
        'token': token
    })
    data = json.loads(response.data)
    assert response.status_code == 200
    assert data['message'] == 'Authenticated'

    # Try with invalid token
    response = test_client.post('/auth_token', json={
        'token': 'invalidtoken'
    })
    data = json.loads(response.data)
    assert response.status_code == 400
    assert data['error'] == 'Invalid token'

def test_logout(test_client):
    # Register and login
    test_client.post('/register', data={
        'username': 'testuser3',
        'password': 'testpass'
    })
    login_response = login_test_user(test_client, 'testuser3', 'testpass')
    # Since the login_test_user function returns response, we need to extract data
    data = json.loads(login_response.data)
    assert 'auth_token' in data  # Ensure auth_token is in response
    # Now call /logout
    response = test_client.get('/logout')
    data = json.loads(response.data)
    assert response.status_code == 200
    assert data['message'] == 'Logged out successfully'

def test_leaderboard(test_client, app):
    with app.app_context():
        # Create some users with various elo ratings
        user1 = User(username='user1', elorating=1500)
        user1.set_password('password1')  # Set password
        user2 = User(username='user2', elorating=1600)
        user2.set_password('password2')  # Set password
        user3 = User(username='user3', elorating=1700)
        user3.set_password('password3')  # Set password
        db.session.add_all([user1, user2, user3])
        db.session.commit()

    response = test_client.get('/leaderboard')
    data = json.loads(response.data)
    assert response.status_code == 200
    assert len(data) == 3
    assert data[0]['username'] == 'user3'
    assert data[0]['elorating'] == 1700
    assert data[1]['username'] == 'user2'
    assert data[1]['elorating'] == 1600
    assert data[2]['username'] == 'user1'
    assert data[2]['elorating'] == 1500

def test_start_game(test_client):
    # Register and login
    test_client.post('/register', data={
        'username': 'player1',
        'password': 'password1'
    })
    login_response = login_test_user(test_client, 'player1', 'password1')
    login_data = json.loads(login_response.data)
    assert 'auth_token' in login_data  # Ensure auth_token is in response
    auth_token = login_data['auth_token']

    # Simulate being logged in by setting session
    with test_client.session_transaction() as sess:
        user = User.query.filter_by(username='player1').first()
        sess['_user_id'] = str(user.id)
        sess['user_id'] = user.id

    # Now call start_game
    response = test_client.get('/start_game')
    data = json.loads(response.data)
    assert response.status_code == 200
    assert data['message'] == 'Game ready'
    assert 'game_id' in data
    assert 'auth_token' in data
    assert 'your_color' in data

def test_play_local(test_client):
    response = test_client.get('/play?local=true')
    assert response.status_code == 200
    assert b'Local Player' in response.data

def test_update_ratings_on_win(app):
    with app.app_context():
        # Create two users
        player_white = User(username='winner', elorating=1500, wins=0, losses=0)
        player_white.set_password('pass')  # Set password
        player_black = User(username='loser', elorating=1500, wins=0, losses=0)
        player_black.set_password('pass')  # Set password
        db.session.add_all([player_white, player_black])
        db.session.commit()

        # Create a game
        game = Game(
            player_white_id=player_white.id,
            player_black_id=player_black.id,
            is_active=True,
            fen=chess.Board().fen(),
            time_left_white=600,
            time_left_black=600,
            last_move_time=datetime.utcnow()
        )
        db.session.add(game)
        db.session.commit()

        # Simulate a win for white
        update_ratings_on_win(game, 'white', 'black')
        db.session.refresh(player_white)
        db.session.refresh(player_black)
        assert player_white.elorating > 1500
        assert player_black.elorating < 1500
        assert player_white.wins == 1
        assert player_black.losses == 1
        assert game.result == 'white'

def test_update_ratings_on_draw(app):
    with app.app_context():
        # Create two users
        player_white = User(username='player1', elorating=1500)
        player_white.set_password('pass')  # Set password
        player_black = User(username='player2', elorating=1500)
        player_black.set_password('pass')  # Set password
        db.session.add_all([player_white, player_black])
        db.session.commit()

        # Create a game
        game = Game(
            player_white_id=player_white.id,
            player_black_id=player_black.id,
            is_active=True,
            fen=chess.Board().fen(),
            time_left_white=600,
            time_left_black=600,
            last_move_time=datetime.utcnow()
        )
        db.session.add(game)
        db.session.commit()

        # Simulate a draw
        update_ratings_on_draw(game)
        db.session.refresh(player_white)
        db.session.refresh(player_black)
        assert player_white.elorating == 1500  # Assuming no change on draw with equal ratings
        assert player_black.elorating == 1500
        assert game.result == 'draw'

def test_error_handlers(test_client):
    # Test 404 error handler
    response = test_client.get('/nonexistent_route')
    data = json.loads(response.data)
    assert response.status_code == 404
    assert data['error'] == 'Not found'

    # Test 500 error handler by causing an exception
    original_route = flask_app.view_functions['play']

    def error_route():
        raise Exception('Test exception')

    flask_app.view_functions['play'] = error_route
    response = test_client.get('/play')
    data = json.loads(response.data)
    assert response.status_code == 500
    assert data['error'] == 'An unexpected error occurred.'
    flask_app.view_functions['play'] = original_route  # Restore original route

#=========================================  bot.py  ===============================================

import pytest
from unittest.mock import MagicMock, patch

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from backend.bot import (
    start, register, register_username, register_password, login,
    login_username, login_password, logout, playlocal, leaderboard, cancel
)
from telegram import InlineKeyboardMarkup
from telegram.ext import ConversationHandler
import uuid

@pytest.mark.asyncio
async def test_start():
    """Test the /start command handler."""
    # Mock update and context
    update = MagicMock()
    update.message.reply_text = AsyncMock()  # Use AsyncMock for async methods
    context = MagicMock()

    # Call the handler
    await start(update, context)

    # Assert that reply_text was called with the expected message
    update.message.reply_text.assert_called_once_with(
        "Welcome to Chess Bot!\n"
        "Use /register to create an account or /login to log in.\n"
        "Use /startgame to play online or /playlocal to play locally."
    )

@pytest.mark.asyncio
async def test_register():
    """Test the /register command handler."""
    update = MagicMock()
    update.message.reply_text = AsyncMock()  # Use AsyncMock
    context = MagicMock()

    result = await register(update, context)

    update.message.reply_text.assert_called_once_with("Enter your desired username:")
    assert result == REGISTER_USERNAME

@pytest.mark.asyncio
async def test_register_username():
    """Test the register_username handler."""
    update = MagicMock()
    update.message.text = 'testuser'
    update.message.reply_text = AsyncMock()  # Use AsyncMock
    context = MagicMock()
    context.user_data = {}

    result = await register_username(update, context)

    assert context.user_data['username'] == 'testuser'
    update.message.reply_text.assert_called_once_with("Enter your desired password:")
    assert result == REGISTER_PASSWORD

@pytest.mark.asyncio
async def test_register_password_success():
    """Test the register_password handler on successful registration."""
    with patch('requests.post') as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'message': 'Registration successful'}
        mock_post.return_value = mock_response

        update = MagicMock()
        update.message.text = 'testpassword'
        update.message.reply_text = AsyncMock()  # Use AsyncMock
        context = MagicMock()
        context.user_data = {'username': 'testuser'}

        result = await register_password(update, context)

        mock_post.assert_called_with(
            f'{BASE_URL}/register',
            data={'username': 'testuser', 'password': 'testpassword'}
        )

        update.message.reply_text.assert_called_once_with("Registration successful! You can now /login.")
        assert result == ConversationHandler.END

@pytest.mark.asyncio
async def test_register_password_failure():
    """Test the register_password handler on failed registration."""
    with patch('requests.post') as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {'message': 'Username already exists'}
        mock_post.return_value = mock_response

        update = MagicMock()
        update.message.text = 'testpassword'
        update.message.reply_text = AsyncMock()  # Use AsyncMock
        context = MagicMock()
        context.user_data = {'username': 'testuser'}

        result = await register_password(update, context)

        mock_post.assert_called_with(
            f'{BASE_URL}/register',
            data={'username': 'testuser', 'password': 'testpassword'}
        )

        update.message.reply_text.assert_called_once_with(
            "Registration failed: Username already exists."
        )
        assert result == ConversationHandler.END

@pytest.mark.asyncio
async def test_login():
    """Test the /login command handler."""
    update = MagicMock()
    update.message.reply_text = AsyncMock()  # Use AsyncMock
    context = MagicMock()

    result = await login(update, context)

    update.message.reply_text.assert_called_once_with("Enter your username:")
    assert result == LOGIN_USERNAME

@pytest.mark.asyncio
async def test_login_username():
    """Test the login_username handler."""
    update = MagicMock()
    update.message.text = 'testuser'
    update.message.reply_text = AsyncMock()  # Use AsyncMock
    context = MagicMock()
    context.user_data = {}

    result = await login_username(update, context)

    assert context.user_data['username'] == 'testuser'
    update.message.reply_text.assert_called_once_with("Enter your password:")
    assert result == LOGIN_PASSWORD

@pytest.mark.asyncio
async def test_login_password_success():
    """Test the login_password handler on successful login."""
    with patch('requests.Session') as mock_session_class:
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'auth_token': 'test_token'}
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        update = MagicMock()
        update.message.text = 'testpassword'
        update.message.reply_text = AsyncMock()  # Use AsyncMock
        context = MagicMock()
        context.user_data = {'username': 'testuser'}

        result = await login_password(update, context)

        mock_session.post.assert_called_with(
            f'{BASE_URL}/login',
            data={'username': 'testuser', 'password': 'testpassword'}
        )

        update.message.reply_text.assert_called_once_with(
            "Login successful! Use /startgame to play online or /playlocal to play locally."
        )
        assert context.user_data['auth_token'] == 'test_token'
        assert context.user_data['session'] == mock_session
        assert context.user_data['username'] == 'testuser'
        assert result == ConversationHandler.END

@pytest.mark.asyncio
async def test_login_password_failure():
    """Test the login_password handler on failed login."""
    with patch('requests.Session') as mock_session_class:
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {'message': 'Invalid credentials'}
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        update = MagicMock()
        update.message.text = 'wrongpassword'
        update.message.reply_text = AsyncMock()  # Use AsyncMock
        context = MagicMock()
        context.user_data = {'username': 'testuser'}

        result = await login_password(update, context)

        mock_session.post.assert_called_with(
            f'{BASE_URL}/login',
            data={'username': 'testuser', 'password': 'wrongpassword'}
        )

        update.message.reply_text.assert_called_once_with(
            "Login failed: Invalid credentials"
        )
        assert result == ConversationHandler.END

@pytest.mark.asyncio
async def test_logout_logged_in():
    """Test the /logout command when user is logged in."""
    with patch('requests.Session') as mock_session_class:
        mock_session = MagicMock()
        mock_session.get.return_value = MagicMock(status_code=200)
        mock_session_class.return_value = mock_session

        update = MagicMock()
        update.message.reply_text = AsyncMock()  # Use AsyncMock
        context = MagicMock()
        context.user_data = MagicMock()  # Используйте MagicMock вместо {}
        context.user_data.clear = MagicMock()  # Отслеживайте вызов clear()

        await logout(update, context)

        mock_session.get(f'{BASE_URL}/logout')
        context.user_data.clear.assert_called_once()  # Проверка вызова clear
        update.message.reply_text.assert_called_once_with("You have been logged out.")

@pytest.mark.asyncio
async def test_logout_not_logged_in():
    """Test the /logout command when user is not logged in."""
    update = MagicMock()
    update.message.reply_text = AsyncMock()  # Use AsyncMock
    context = MagicMock()
    context.user_data = {}

    await logout(update, context)

    update.message.reply_text.assert_called_once_with("You are not logged in.")

@pytest.mark.asyncio
async def test_playlocal():
    """Test the /playlocal command handler."""
    update = MagicMock()
    update.message.reply_text = AsyncMock()  # Use AsyncMock
    context = MagicMock()

    with patch('uuid.uuid4', return_value=uuid.UUID('12345678-1234-5678-1234-567812345678')):
        await playlocal(update, context)

    expected_url = f'{FRONTEND_URL}/play?game_id=12345678-1234-5678-1234-567812345678&local=true'
    update.message.reply_text.assert_called_once()
    args, kwargs = update.message.reply_text.call_args
    assert "Starting a local game! Use the MiniApp below to play:" in args[0]
    assert isinstance(kwargs['reply_markup'], InlineKeyboardMarkup)

@pytest.mark.asyncio
async def test_leaderboard_success():
    """Test the /leaderboard command handler on success."""
    with patch('requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {'username': 'user1', 'elorating': 1700},
            {'username': 'user2', 'elorating': 1600},
            {'username': 'user3', 'elorating': 1500}
        ]
        mock_get.return_value = mock_response

        update = MagicMock()
        update.message.reply_text = AsyncMock()  # Use AsyncMock
        context = MagicMock()

        await leaderboard(update, context)

        expected_text = "Leaderboard:\n"
        expected_text += "1. user1 - ELO: 1700\n"
        expected_text += "2. user2 - ELO: 1600\n"
        expected_text += "3. user3 - ELO: 1500\n"

        update.message.reply_text.assert_called_once_with(expected_text)

@pytest.mark.asyncio
async def test_leaderboard_failure():
    """Test the /leaderboard command handler on failure."""
    with patch('requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        update = MagicMock()
        update.message.reply_text = AsyncMock()  # Use AsyncMock
        context = MagicMock()

        await leaderboard(update, context)

        update.message.reply_text.assert_called_once_with("Error fetching leaderboard.")

@pytest.mark.asyncio
async def test_cancel():
    """Test the /cancel command handler."""
    update = MagicMock()
    update.message.reply_text = AsyncMock()  # Use AsyncMock
    context = MagicMock()

    result = await cancel(update, context)

    update.message.reply_text.assert_called_once_with("Operation cancelled.")
    assert result == ConversationHandler.END

#=========================================  elo.py  ===============================================

from backend.elo import calculate_elo

def test_winner_elo_increase():
    # Увеличение рейтинга ELO победителя
    winner_elo, loser_elo = calculate_elo(1600, 1400)
    assert winner_elo > 1600, "Рейтинг ELO победителя должен увеличиться"
    assert loser_elo < 1400, "Рейтинг ELO проигравшего должен уменьшиться"

def test_loser_elo_decrease():
    # Уменьшение рейтинга ELO проигравшего
    winner_elo, loser_elo = calculate_elo(1600, 1400)
    assert loser_elo < 1400, "Рейтинг ELO проигравшего должен уменьшиться"

def test_draw_scenario():
    # Сценарий ничьей
    winner_elo, loser_elo = calculate_elo(1600, 1600, draw=True)
    assert winner_elo == 1600 and loser_elo == 1600, "Рейтинги ELO должны остаться неизменными при ничьей"

def test_equal_elo():
    # Одинаковые рейтинги ELO
    winner_elo, loser_elo = calculate_elo(1500, 1500)
    assert winner_elo > 1500, "Рейтинг ELO победителя должен увеличиться"
    assert loser_elo < 1500, "Рейтинг ELO проигравшего должен уменьшиться"

def test_high_k_factor():
    # Высокий коэффициент K
    winner_elo, loser_elo = calculate_elo(2000, 1000, k=100)
    assert winner_elo > 2000, "Рейтинг ELO победителя должен значительно увеличиться с высоким K"
    assert loser_elo < 1000, "Рейтинг ELO проигравшего должен значительно уменьшиться с высоким K"

def test_low_k_factor():
    # Низкий коэффициент K
    winner_elo, loser_elo = calculate_elo(2000, 1000, k=10)
    assert winner_elo - 2000 < 10, "Рейтинг ELO победителя должен немного увеличиться с низким K"
    assert 1000 - loser_elo < 10, "Рейтинг ELO проигравшего должен немного уменьшиться с низким K"

if __name__ == "__main__":
    pytest.main()