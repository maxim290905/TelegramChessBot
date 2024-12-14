<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Документация по Коду</title>
<style>
    body {
        font-family: Arial, sans-serif;
        line-height: 1.6;
        margin: 0;
        padding: 0;
        color: #333;
    }
    header, nav, section, footer {
        padding: 20px;
    }
    header {
        background: #f4f4f4;
    }
    nav {
        background: #333;
        color: #fff;
    }
    nav a {
        color: #fff;
        display: inline-block;
        margin-right: 10px;
        text-decoration: none;
        font-weight: bold;
    }
    nav a:hover {
        text-decoration: underline;
    }
    section h2 {
        border-bottom: 2px solid #333;
        padding-bottom: 10px;
    }
    code, pre {
        background: #f0f0f0;
        padding: 10px;
        display: block;
        white-space: pre-wrap;
        overflow-x: auto;
    }
    .code-block {
        margin-bottom: 20px;
    }
    .docstring {
        background: #eaf7ff;
        padding: 10px;
        margin-bottom: 10px;
    }
    h3 {
        margin-top: 40px;
    }
    h4 {
        margin-top: 30px;
    }
    footer {
        background: #f4f4f4;
        text-align: center;
        font-size: 0.9em;
        margin-top: 40px;
    }
    .table-of-contents {
        margin-bottom: 20px;
    }
    .table-of-contents ul {
        list-style: none;
        padding-left: 0;
    }
    .table-of-contents ul li {
        margin-bottom: 5px;
    }
</style>
</head>
<body>

<header>
    <h1>Документация по Проекту (Telegram-бот шахмат + Flask + Socket.IO)</h1>
    <p>Данная документация описывает функциональность, структуру и назначение кода, включающего в себя модели данных, бекенд 
    (Flask-приложение, Socket.IO), а также Telegram-бот.</p>
</header>

<nav>
    <a href="#models">Модели (models.py)</a>
    <a href="#bot">Telegram Бот (bot.py)</a>
    <a href="#main">Flask и Socket.IO Сервер (main.py)</a>
    <a href="#frontend">Фронтенд (chess_ui.html и static/js/script.js)</a>
</nav>

<section class="table-of-contents">
    <h2>Содержание</h2>
    <ul>
        <li><a href="#models">1. models.py</a>
            <ul>
                <li><a href="#models-user">Класс User</a></li>
                <li><a href="#models-game">Класс Game</a></li>
            </ul>
        </li>
        <li><a href="#bot">2. bot.py</a>
            <ul>
                <li><a href="#bot-general">Общие Настройки</a></li>
                <li><a href="#bot-commands">Команды Бота</a></li>
            </ul>
        </li>
        <li><a href="#main">3. main.py (Flask Приложение и Socket.IO)</a>
            <ul>
                <li><a href="#main-setup">Настройка Приложения</a></li>
                <li><a href="#main-routes">Маршруты Flask</a></li>
                <li><a href="#main-socket">События Socket.IO</a></li>
                <li><a href="#main-helper">Вспомогательные Функции</a></li>
            </ul>
        </li>
        <li><a href="#frontend">4. Фронтенд (templates/chess_ui.html и script.js)</a></li>
    </ul>
</section>

<section id="models">
    <h2>1. models.py</h2>

    <div class="docstring">
        <p><strong>Описание:</strong> Файл <code>models.py</code> содержит определение ORM-моделей для базы данных, 
        используемой приложением. Используется SQLAlchemy для взаимодействия с базой данных и Flask-Login для 
        аутентификации пользователей.</p>
    </div>

    <h3 id="models-user">Класс User</h3>

    <div class="code-block">
<pre><code>class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    elorating = db.Column(db.Integer, default=1000)
    wins = db.Column(db.Integer, default=0)
    losses = db.Column(db.Integer, default=0)
    auth_token = db.Column(db.String(36), unique=True, nullable=True)

    def set_password(self, password):
        """Устанавливает хешированный пароль."""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Проверяет, совпадает ли введённый пароль с хешированным."""
        return check_password_hash(self.password_hash, password)
    
    def generate_auth_token(self):
        """Генерирует уникальный аутентификационный токен."""
        import uuid
        self.auth_token = str(uuid.uuid4())
        db.session.commit()
        return self.auth_token
    
    def revoke_auth_token(self):
        """Аннулирует текущий аутентификационный токен."""
        self.auth_token = None
        db.session.commit()
</code></pre>
    </div>
    <p><strong>Назначение:</strong> Модель <code>User</code> хранит данные о пользователях, такие как имя пользователя, 
    пароль (в хешированном виде), рейтинг ELO, количество побед и поражений, а также токен аутентификации. 
    Методы класса позволяют устанавливать и проверять пароль, управлять токеном аутентификации.</p>

    <h3 id="models-game">Класс Game</h3>
    <div class="code-block">
<pre><code>class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_white_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    player_black_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fen = db.Column(db.String, nullable=False, default=chess.Board().fen())
    is_active = db.Column(db.Boolean, default=True)
    is_waiting = db.Column(db.Boolean, default=True)
    time_left_white = db.Column(db.Integer, default=600)
    time_left_black = db.Column(db.Integer, default=600)
    last_move_time = db.Column(db.DateTime, default=datetime.utcnow)
    result = db.Column(db.String, nullable=True)

    player_white = db.relationship('User', foreign_keys=[player_white_id], backref='white_games')
    player_black = db.relationship('User', foreign_keys=[player_black_id], backref='black_games')
</code></pre>
    </div>
    <p><strong>Назначение:</strong> Модель <code>Game</code> хранит данные о конкретной шахматной игре, включая игроков, 
    текущее состояние доски (FEN), время, оставшееся для каждого игрока, статус игры (активна, в ожидании второго игрока, 
    результат). Она связывает два экземпляра <code>User</code> как белого и черного игрока.</p>
</section>

<section id="bot">
    <h2>2. bot.py — Telegram Бот</h2>
    <div class="docstring">
        <p><strong>Описание:</strong> Файл <code>bot.py</code> описывает функционал Telegram-бота. Он взаимодействует 
        с бекендом по HTTP, отправляя запросы на маршруты Flask-приложения, чтобы выполнять регистрацию, логин, запуск игр, 
        просмотр таблицы лидеров и т.д.</p>
    </div>

    <h3 id="bot-general">Общие Настройки</h3>
    <div class="code-block">
<pre><code># Загрузка токена бота и URL
BOT_TOKEN = os.getenv('BOT_TOKEN')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:5000')
FRONTEND_URL = os.getenv('FRONTEND_URL')
</code></pre>
    </div>
    <p>Бот инициализируется с помощью токена, загружаемого из переменных окружения. Устанавливаются базовые URL для бекенда и фронтенда.</p>

    <h3 id="bot-commands">Основные Команды</h3>

    <ul>
        <li><strong>/start</strong>: Отправляет приветственное сообщение.</li>
        <li><strong>/register</strong>: Запускает диалог регистрации пользователя (имя, пароль) и отправляет запрос на бекенд.</li>
        <li><strong>/login</strong>: Запускает диалог входа: имя пользователя, пароль, проверка на бекенде.</li>
        <li><strong>/logout</strong>: Выход пользователя из системы.</li>
        <li><strong>/startgame</strong>: Запуск онлайн-игры; бот получает game_id и отправляет ссылку для мини-приложения игры.</li>
        <li><strong>/playlocal</strong>: Запуск локальной игры.</li>
        <li><strong>/leaderboard</strong>: Отображение таблицы лидеров.</li>
        <li><strong>/cancel</strong>: Отмена текущего процесса диалога.</li>
    </ul>

    <div class="code-block">
<pre><code>async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет приветственное сообщение и инструкции."""

async def register(...):
    """Начинает процесс регистрации: запрашивает имя пользователя."""

async def register_username(...):
    """Сохраняет введенное имя и запрашивает пароль."""

async def register_password(...):
    """Передает имя и пароль на бекенд для регистрации, возвращает результат."""

async def login(...):
    """Начинает процесс логина: запрашивает имя пользователя."""

async def login_username(...):
    """Сохраняет имя и запрашивает пароль."""

async def login_password(...):
    """Отправляет данные на бекенд, получает токен и сохраняет в контексте."""

async def logout(...):
    """Выход из системы, очистка контекста пользователя."""

async def startgame(...):
    """Создает или присоединяется к онлайн-игре и отправляет ссылку на фронтенд."""

async def playlocal(...):
    """Запускает локальную игру (без авторизации)."""

async def leaderboard(...):
    """Отображает таблицу лидеров."""

async def cancel(...):
    """Отменяет текущий процесс (регистрация или логин)."""
</code></pre>
    </div>
</section>

<section id="main">
    <h2>3. main.py — Flask Приложение и Socket.IO</h2>
    <div class="docstring">
        <p><strong>Описание:</strong> Файл <code>main.py</code> — это backend-сервер, написанный на Flask. 
        Он обрабатывает HTTP-запросы (регистрация, логин, запуск игры, leaderboard) и управляет состоянием игр. 
        Socket.IO предоставляет веб-сокеты для реального времени: обновление доски, предложение ничьей, сдача.</p>
    </div>

    <h3 id="main-setup">Настройка Приложения</h3>
    <p>Загрузка переменных окружения, инициализация Flask-приложения, базы данных, Socket.IO, аутентификация Flask-Login.</p>

    <h3 id="main-routes">Маршруты Flask</h3>
    <ul>
        <li><code>/auth_token</code>: Аутентификация по токену.</li>
        <li><code>/play</code>: Отображает игру (локально или онлайн).</li>
        <li><code>/register</code>: Регистрация пользователя.</li>
        <li><code>/login</code>: Вход пользователя.</li>
        <li><code>/logout</code>: Выход пользователя.</li>
        <li><code>/leaderboard</code>: Таблица лидеров.</li>
        <li><code>/start_game</code>: Начало новой игры или присоединение к ожидающей.</li>
    </ul>

    <h3 id="main-socket">События Socket.IO</h3>
    <ul>
        <li><strong>connect</strong>: Подключение к сокету, проверка токена и game_id.</li>
        <li><strong>join_game</strong>: Присоединение к конкретной игре.</li>
        <li><strong>move</strong>: Обработка хода игрока, обновление позиции и времени.</li>
        <li><strong>offer_draw</strong>: Предложение ничьей.</li>
        <li><strong>draw_response</strong>: Ответ на предложение ничьей.</li>
        <li><strong>resign</strong>: Сдача игрока.</li>
    </ul>

    <h3 id="main-helper">Вспомогательные Функции</h3>
    <p><code>update_game_over</code>: Обновление результата игры и рейтингов, логирование события.</p>
    <p><code>update_ratings_on_win</code>, <code>update_ratings_on_draw</code>: Пересчет ELO рейтингов при завершении игры.</p>

</section>

<section id="frontend">
    <h2>4. Фронтенд (templates/chess_ui.html и static/js/script.js)</h2>
    <div class="docstring">
        <p><strong>Описание:</strong> Frontend — это страница, отображающая шахматную доску, таймер, информацию об игроках, 
        рейтинги и кнопки управлением (сдача, предложение ничьей). Используются <code>chessboard.js</code> и 
        <code>chess.js</code> для отображения и логики. Socket.IO для реального времени.</p>
    </div>
    <h3>Основной Функционал</h3>
    <ul>
        <li>Отображение шахматной доски.</li>
        <li>Обновление позиции в реальном времени при получении событий от сервера.</li>
        <li>Обработка локальных и онлайн-игр (localGame vs online).</li>
        <li>Таймер для каждого игрока.</li>
        <li>Сдача, предложение ничьей через кнопки.</li>
    </ul>

    <h3>Ключевые функции в script.js</h3>
    <ul>
        <li><code>initializeLocalBoard()</code>: Инициализация доски для локальной игры.</li>
        <li><code>onDropLocal()</code>: Обработка хода для локальной игры.</li>
        <li><code>initializeOnlineBoard()</code>: Инициализация доски для онлайн-игры, подключение к серверу, подписка на события.</li>
        <li><code>onDropOnline()</code>: Обработка хода и отправка данных на сервер для онлайн-игры.</li>
        <li><code>startTimer()</code>: Запуск таймера и обратный отсчет для игроков.</li>
        <li><code>gameOver()</code>: Обработка завершения игры, остановка таймера, обновление статуса.</li>
    </ul>
</section>

<footer>
    <p>© 2024 Документация по Проекту «Шахматы с Телеграм-ботом и Flask Backend»</p>
</footer>

</body>
</html>
