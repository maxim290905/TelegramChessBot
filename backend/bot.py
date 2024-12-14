import os
import uuid
import requests
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
from backend.models import db, User
from backend.main import app

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:5000')
FRONTEND_URL = os.getenv('FRONTEND_URL')

if not BOT_TOKEN or not FRONTEND_URL:
    raise ValueError("BOT_TOKEN and FRONTEND_URL must be set in the .env file.")

REGISTER_USERNAME, REGISTER_PASSWORD = range(2)
LOGIN_USERNAME, LOGIN_PASSWORD = range(2, 4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает команду /start и отправляет приветственное сообщение.

    Эта функция вызывается при использовании команды /start пользователем в чате с ботом.
    Она отправляет приветственное сообщение с инструкциями по использованию бота, включая команды
    для регистрации, входа в аккаунт, начала игры и игры локально.

    Аргументы:
        update (Update): Объект обновления, содержащий информацию о сообщении и отправителе.
        context (ContextTypes.DEFAULT_TYPE): Контекст команды, содержащий информацию о контексте
                                             и состояниях для обработки команд.
    """
    await update.message.reply_text(
        "Welcome to Chess Bot!\n"
        "Use /register to create an account or /login to log in.\n"
        "Use /startgame to play online or /playlocal to play locally."
    )

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Enter your desired username:")
    return REGISTER_USERNAME

async def register_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['username'] = update.message.text
    await update.message.reply_text("Enter your desired password:")
    return REGISTER_PASSWORD

async def register_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает процесс регистрации пользователя с паролем.

    Эта функция вызывается после того, как пользователь вводит пароль для завершения регистрации.
    Пароль передается в запрос к серверу, где он сохраняется вместе с ранее введенным именем пользователя.
    В случае успешной регистрации отправляется подтверждающее сообщение, в случае ошибки — сообщение об ошибке.

    Аргументы:
        update (Update): Объект обновления, содержащий информацию о сообщении и отправителе, в данном случае о пароле пользователя.
        context (ContextTypes.DEFAULT_TYPE): Контекст команды, содержащий данные, введенные пользователем, и другую информацию о процессе регистрации.

    Возвращает:
        ConversationHandler.END: Завершается текущий процесс разговора (conversation), переходя к окончанию регистрации.
    """
    username = context.user_data['username']
    password = update.message.text
    response = requests.post(f'{BASE_URL}/register', data={'username': username, 'password': password})

    if response.status_code == 200:
        await update.message.reply_text("Registration successful! You can now /login.")
    else:
        await update.message.reply_text(f"Registration failed: {response.json().get('message', 'Unknown error')}.")
    return ConversationHandler.END

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Enter your username:")
    return LOGIN_USERNAME

async def login_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['username'] = update.message.text
    await update.message.reply_text("Enter your password:")
    return LOGIN_PASSWORD

async def login_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает процесс входа пользователя с использованием пароля.

    Эта функция вызывается, когда пользователь вводит свой пароль для входа в систему. 
    Функция отправляет POST-запрос на сервер с данными о пользователе и пароле, и в случае успешной авторизации 
    сервер возвращает ответ с аутентификационным токеном, который сохраняется в контексте пользователя. 
    В случае ошибки возвращается сообщение об ошибке.

    Аргументы:
        update (Update): Объект обновления, содержащий информацию о сообщении, в частности, о пароле пользователя.
        context (ContextTypes.DEFAULT_TYPE): Контекст команды, содержащий данные, такие как имя пользователя, 
                                              которое хранится в `context.user_data['username']`.

    Возвращает:
        ConversationHandler.END: Завершается текущее состояние в обработчике беседы.

    Примечания:
        - В случае успешного входа сервер возвращает токен аутентификации, который сохраняется в `context.user_data['auth_token']`.
        - В случае ошибки, например, неверного пароля или отсутствующего пользователя, сервер вернет сообщение об ошибке, которое будет отправлено пользователю.
    """
    username = context.user_data['username']
    password = update.message.text
    session = requests.Session()
    response = session.post(f'{BASE_URL}/login', data={'username': username, 'password': password})

    if response.status_code == 200:
        auth_token = response.json().get('auth_token')
        context.user_data['auth_token'] = auth_token
        context.user_data['session'] = session
        context.user_data['username'] = username
        await update.message.reply_text(
            "Login successful! Use /startgame to play online or /playlocal to play locally."
        )
    else:
        error_message = response.json().get('message', 'Unknown error.')
        await update.message.reply_text(f"Login failed: {error_message}")
    return ConversationHandler.END


async def logout(update, context):
    """Handles user logout."""
    session = context.user_data.get('session')
    if session:
        response = session.get(f'{BASE_URL}/logout')  # Ensure this is the call being made
        if response.status_code == 200:
            context.user_data.clear()
            await update.message.reply_text("You have been logged out.")
        else:
            await update.message.reply_text("Logout failed.")
    else:
        await update.message.reply_text("You are not logged in.")

async def startgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает команду для начала новой игры.

    Эта функция инициирует создание новой игры на сервере, если пользователь авторизован. Если пользователь 
    не авторизован, он получает сообщение о необходимости войти в систему. В случае успешного создания игры, 
    пользователю отправляется сообщение с ссылкой на игровую страницу через мини-приложение.

    Аргументы:
        update (Update): Объект обновления, содержащий информацию о сообщении от пользователя, которое вызвало команду.
        context (ContextTypes.DEFAULT_TYPE): Контекст команды, содержащий данные пользователя, включая сессию.

    Возвращает:
        None: Функция отправляет сообщение пользователю и не возвращает значений.

    Примечания:
        - Если пользователь не авторизован (нет сессии), ему будет предложено сначала войти в систему.
        - При успешном старте игры пользователю отправляется кнопка с ссылкой на страницу игры в мини-приложении.
    
    Ошибки:
        - Если пользователь не авторизован, отправляется сообщение с просьбой войти в систему.
        - Если при создании игры произошла ошибка, пользователю отправляется сообщение об ошибке.
    """
    session = context.user_data.get('session')
    
    if not session:
        await update.message.reply_text("You need to /login first.")
        return
    response = session.get(f'{BASE_URL}/start_game')
    
    if response.status_code == 200:
        data = response.json()
        game_id = data['game_id']
        username = context.user_data.get('username')
        
        with app.app_context():
            user = User.query.filter_by(username=username).first()
            if not user:
                await update.message.reply_text("User not found.")
                return
            token = user.generate_auth_token()

        play_url = f'{FRONTEND_URL}/play?game_id={game_id}&token={token}&local=false'
        web_app = WebAppInfo(url=play_url)
        
        await update.message.reply_text(
            "Game created! Use the MiniApp below to start playing:",
            reply_markup=InlineKeyboardMarkup.from_button(InlineKeyboardButton("Open Game", web_app=web_app))
        )
    else:
        await update.message.reply_text("Error starting game.")


async def playlocal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game_id = str(uuid.uuid4())
    play_url = f'{FRONTEND_URL}/play?game_id={game_id}&local=true'
    web_app = WebAppInfo(url=play_url)
    await update.message.reply_text(
        "Starting a local game! Use the MiniApp below to play:",
        reply_markup=InlineKeyboardMarkup.from_button(InlineKeyboardButton("Open Local Game", web_app=web_app))
    )

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает команду для получения таблицы лидеров.

    Эта функция запрашивает данные о текущей таблице лидеров с сервера и отправляет пользователю отформатированный список 
    игроков с их рейтингами ELO.

    Аргументы:
        update (Update): Объект обновления, содержащий информацию о сообщении от пользователя, которое вызвало команду.
        context (ContextTypes.DEFAULT_TYPE): Контекст команды, содержащий данные пользователя и другие параметры.

    Возвращает:
        None
        
    Ошибки:
        - Если запрос к серверу завершился с ошибкой, пользователю будет отправлено сообщение об ошибке.
    """
    response = requests.get(f'{BASE_URL}/leaderboard')
    
    if response.status_code == 200:
        data = response.json()
        leaderboard_text = "Leaderboard:\n"
        
        for idx, user in enumerate(data, start=1):
            leaderboard_text += f"{idx}. {user['username']} - ELO: {int(user['elorating'])}\n"
        
        await update.message.reply_text(leaderboard_text)
    else:
        await update.message.reply_text("Error fetching leaderboard.")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    register_conv = ConversationHandler(
        entry_points=[CommandHandler('register', register)],
        states={
            REGISTER_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_username)],
            REGISTER_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_password)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    login_conv = ConversationHandler(
        entry_points=[CommandHandler('login', login)],
        states={
            LOGIN_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_username)],
            LOGIN_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_password)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('leaderboard', leaderboard))
    application.add_handler(CommandHandler('logout', logout))
    application.add_handler(CommandHandler('startgame', startgame))
    application.add_handler(CommandHandler('playlocal', playlocal))
    application.add_handler(register_conv)
    application.add_handler(login_conv)

    application.run_polling()

if __name__ == '__main__':
    main()