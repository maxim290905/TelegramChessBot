// static/js/script.js

let socket = null;

const urlParams = new URLSearchParams(window.location.search);
const gameId = urlParams.get('game_id');
const authToken = urlParams.get('token');
const isLocalParam = urlParams.get('local') === 'true';
const localGame = isLocalParam;

console.log("Username from backend:", username);
console.log("Is local game:", localGame);

const statusElement = document.getElementById('status');
const playerWhiteElement = document.getElementById('player-white');
const playerBlackElement = document.getElementById('player-black');
const eloWhiteElement = document.getElementById('elo-white');
const eloBlackElement = document.getElementById('elo-black');
const currentTurnElement = document.getElementById('current-turn');
const timerWhiteElement = document.getElementById('timer-white');
const timerBlackElement = document.getElementById('timer-black');
const resignButton = document.getElementById('resign-btn');
const offerDrawButton = document.getElementById('offer-draw-btn');

let gameStarted = false;
let myColor = null; // 'white' or 'black'
let chessGame = new Chess();
let board = null;
let timeLeftWhite = 600;
let timeLeftBlack = 600;
let timerInterval = null;
let isGameOver = false;
let currentPlayerLocal = 'white';

function formatTime(seconds) {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}:${remainingSeconds < 10 ? '0' + remainingSeconds : remainingSeconds}`;
}

function updateTimerDisplay() {
    timerWhiteElement.textContent = `White Time Left: ${formatTime(timeLeftWhite)}`;
    timerBlackElement.textContent = `Black Time Left: ${formatTime(timeLeftBlack)}`;
}

function updateEloDisplay(eloWhite, eloBlack) {
    eloWhiteElement.textContent = `White ELO: ${eloWhite}`;
    eloBlackElement.textContent = `Black ELO: ${eloBlack}`;
}

function startTimer() {
    /**
 * Запускает таймер игры и обновляет оставшееся время для каждого игрока.
 * 
 * Эта функция управляет обратным отсчетом времени для обоих игроков в шахматной игре. Она обрабатывает как локальные,
 * так и онлайн-игры отдельно, проверяя, чей сейчас ход, и уменьшая оставшееся время для активного игрока.
 * Если у игрока заканчивается время, игра завершается, и победитель определяется. Функция также обновляет отображение
 * времени и отправляет обновленные данные на сервер для онлайн-игры.
 * 
 * Таймер останавливается, если игра завершена или если игра еще не началась. Таймер обновляется каждую секунду и
 * автоматически останавливается, когда у игрока заканчивается время.
 * 
 * Поведение таймера зависит от того, играется ли игра локально или онлайн:
 * - **Локальная игра**: Таймер отсчитывает время для каждого игрока локально. Обновления по сети не отправляются.
 * - **Онлайн-игра**: Таймер отсчитывает время для текущего игрока и отправляет обновленное время на сервер через событие сокета.
 * 
 * Возвращает:
 *   Функция не возвращает значения. Она изменяет состояние игры, обновляет отображение и отправляет
 *   сообщения через сокет для онлайн-игры.
 */
    if (timerInterval) clearInterval(timerInterval);
    timerInterval = setInterval(() => {
        if (!gameStarted || isGameOver) {
            clearInterval(timerInterval);
            return;
        }

        if (localGame) {
            if (chessGame.turn() === 'w') {
                if (timeLeftWhite > 0) {
                    timeLeftWhite--;
                    updateTimerDisplay();
                } else {
                    clearInterval(timerInterval);
                    statusElement.textContent = "Белые проиграли по времени. Черные победили!";
                    gameOver('black');
                }
            } else {
                if (timeLeftBlack > 0) {
                    timeLeftBlack--;
                    updateTimerDisplay();
                } else {
                    clearInterval(timerInterval);
                    statusElement.textContent = "Черные проиграли по времени. Белые победили!";
                    gameOver('white');
                }
            }
        } else {
            const currentColor = chessGame.turn() === 'w' ? 'white' : 'black';
            if (currentColor === 'white') {
                if (timeLeftWhite > 0) {
                    timeLeftWhite--;
                    updateTimerDisplay();
                    socket.emit('update_time', { game_id: gameId, color: 'white', time_left: timeLeftWhite });
                } else {
                    clearInterval(timerInterval);
                    statusElement.textContent = "Белые проиграли по времени. Черные победили!";
                    gameOver('black');
                }
            } else {
                if (timeLeftBlack > 0) {
                    timeLeftBlack--;
                    updateTimerDisplay();
                    socket.emit('update_time', { game_id: gameId, color: 'black', time_left: timeLeftBlack });
                } else {
                    clearInterval(timerInterval);
                    statusElement.textContent = "Черные проиграли по времени. Белые победили!";
                    gameOver('white');
                }
            }
        }
    }, 1000);
}

function gameOver(winnerColor) {
    /**
 * Завершается игра и определяется победитель.
 * 
 * Эта функция вызывается, когда игра заканчивается, и она выполняет несколько задач:
 * - Обновляет флаг `isGameOver`, чтобы указать, что игра завершена.
 * - Уничтожает объект доски, что позволяет освободить ресурсы и подготовиться к следующей игре.
 * - В случае локальной игры выводится сообщение о победе на экране.
 * - В случае онлайн-игры отправляется событие на сервер с результатом игры, а также выводится сообщение о победителе.
 * 
 * Если игра завершена, эта функция также обновляет статус игры, используя цвет победителя, который был передан в параметре `winnerColor`.
 * 
 * Примечания:
 * - В случае локальной игры обновляется только отображение на экране, без отправки данных на сервер.
 * - В случае онлайн-игры информация о завершении игры отправляется на сервер через сокет, и отображается сообщение о победе.
 * 
 * Аргументы:
 *   - `winnerColor` (string): Цвет победителя, который может быть `'white'` или `'black'`. Используется для определения,
 *     кто победил в игре и какого цвета игрок.
 */
    isGameOver = true;
    board.destroy();
    if (localGame) {
        statusElement.textContent = `Game over: ${capitalizeFirstLetter(winnerColor)} wins.`;
    } else {
        socket.emit('game_over', { game_id: gameId, result: `${winnerColor} wins on time` });
        statusElement.textContent = `Game over: ${capitalizeFirstLetter(winnerColor)} wins.`;
    }
}

function capitalizeFirstLetter(string) {
    return string.charAt(0).toUpperCase() + string.slice(1);
}

function initializeLocalBoard() {
    /**
 * Инициализирует локальную шахматную доску с начальной позицией и настройками.
 * 
 * Эта функция создает и настраивает шахматную доску с помощью библиотеки Chessboard.js. 
 * Она задает начальную позицию фигур, настраивает поведение при перетаскивании фигур, 
 * а также устанавливает тему для изображений фигур.
 * После инициализации доски также обновляется отображение рейтинга ELO для обоих игроков.
 */
    console.log("Initializing local board...");
    board = Chessboard('chess-board', {
        position: 'start',
        draggable: true,
        orientation: 'white',
        onDragStart: onDragStartLocal,
        onDrop: onDropLocal,
        onSnapEnd: onSnapEndLocal,
        pieceTheme: 'https://chessboardjs.com/img/chesspieces/alpha/{piece}.png'
    });
    updateEloDisplay(1500, 1500);
    console.log("Local board initialized.");
}

function onDragStartLocal(source, piece, position, orientation) {
    if (!gameStarted || isGameOver) return false;
    // Разрешаем ходить только, если это ход белых и фигура белая
    if (chessGame.turn() === 'w' && piece.search(/^w/) === -1) {
      return false;
    }
    if (chessGame.turn() === 'b' && piece.search(/^b/) === -1) {
      return false;
    }
  }

/**
 * Обрабатывает событие перемещения фигуры на локальной доске.
 * 
 * Эта функция вызывается при перетаскивании фигуры на новую клетку на локальной шахматной доске. 
 * Она пытается выполнить ход в объекте игры (`chessGame`) и, если ход является допустимым, обновляет 
 * положение фигур на доске, изменяет текущее состояние игры и запускает таймер.
 * Если ход недопустим, фигура возвращается на исходную клетку.
 * 
 * Примечания:
 * - Функция автоматически выполняет превращение пешки в ферзя (promotion: 'q') при необходимости.
 * - После выполнения хода обновляется состояние доски и отображается информация о текущем ходе.
 * - Таймер игры перезапускается с каждым ходом, а также обновляется информация о текущем ходе.
 * 
 * Параметры:
 *   - "source" (string): Исходная клетка, с которой была перемещена фигура
 *   - "target" (string): Целевая клетка, на которую фигура была перемещена
 * 
 * Возвращаемое значение:
 *   - Возвращает строку 'snapback', если ход недопустим, и фигура должна вернуться на исходную позицию.
 *   - Ничего не возвращает в случае успешного выполнения хода.
 */
function onDropLocal(source, target) {
    const move = chessGame.move({
        from: source,
        to: target,
        promotion: 'q'
    });
    if (move === null) return 'snapback';
    board.position(chessGame.fen());
    currentTurnElement.textContent = `Current Turn: ${capitalizeFirstLetter(chessGame.turn() === 'w' ? 'white' : 'black')}`;
    statusElement.textContent = "Move made. Your turn again.";
    switchOrientationLocal();
    startTimer();
}


function onSnapEndLocal() {
    board.position(chessGame.fen());
}

function switchOrientationLocal() {
    currentPlayerLocal = (chessGame.turn() === 'w') ? 'white' : 'black';
    board.orientation(currentPlayerLocal);
    console.log(`Switched board orientation to ${currentPlayerLocal}`);
}

if (localGame) {
    console.log("Initializing local game...");
    statusElement.textContent = 'Local game started. You play both sides.';
    initializeLocalBoard();
    gameStarted = true;
    currentTurnElement.textContent = `Current Turn: White`;
    timeLeftWhite = 600;
    timeLeftBlack = 600;
    updateTimerDisplay();
    playerWhiteElement.textContent = "White: Local Player (You)";
    playerBlackElement.textContent = "Black: Local Player (You)";
    startTimer();
} else {
    if (!gameId || !authToken) {
        statusElement.textContent = 'Missing game_id or token.';
        throw new Error('Missing game_id or token.');
    }

    socket = io({
        query: {
            token: authToken,
            game_id: gameId
        }
    });

    socket.on('connect', () => {
        console.log('Connected to server');
        socket.emit('join_game', { 'game_id': gameId });
        statusElement.textContent = 'Connected. Waiting for both players to join...';
    });

    let playerWhite = null;
    let playerBlack = null;

    socket.on('status', (data) => {
        console.log(data.message);
        statusElement.textContent = data.message;
    });

    socket.on('game_info', (data) => {
        playerWhite = data.player_white;
        playerBlack = data.player_black;
        
        playerWhiteElement.textContent = `White: ${playerWhite.username}`;
        playerBlackElement.textContent = `Black: ${playerBlack.username}`;
        eloWhiteElement.textContent = `White ELO: ${playerWhite.elorating}`;
        eloBlackElement.textContent = `Black ELO: ${playerBlack.elorating}`;
      
        // Определяем цвет игрока
        if (playerWhite.username === username) {
          myColor = 'white';
          playerWhiteElement.textContent += ' (You)';
        } else if (playerBlack.username === username) {
          myColor = 'black';
          playerBlackElement.textContent += ' (You)';
        } else {
          console.error('Cannot determine player color. Check username matching.');
        }
      });
    socket.on('game_started', (data) => {
        statusElement.textContent = "Game started! You can make your move.";
        gameStarted = true;
        currentTurnElement.textContent = `Current Turn: ${capitalizeFirstLetter(data.current_turn)}`;
        timeLeftWhite = data.time_left_white;
        timeLeftBlack = data.time_left_black;
        updateTimerDisplay();
        chessGame.load(data.fen);
        initializeOnlineBoard(data.fen);
        updateEloDisplay(data.player_white.elorating, data.player_black.elorating);
        startTimer();
    });

    socket.on('move', (data) => {
        chessGame.load(data.fen);
        board.position(data.fen);
        statusElement.textContent = "Opponent moved. Your turn!";
        currentTurnElement.textContent = `Current Turn: ${capitalizeFirstLetter(data.current_turn)}`;
        timeLeftWhite = data.time_left_white;
        timeLeftBlack = data.time_left_black;
        updateTimerDisplay();
        startTimer();
    });

    socket.on('game_over', (data) => {
        statusElement.textContent = `Game over: ${data.result}`;
        gameStarted = false;
        isGameOver = true;
        clearInterval(timerInterval);
        board.destroy();
    });

    socket.on('draw_offer', (data) => {
        const accept = confirm(`${data.from_player} has offered a draw. Do you accept?`);
        socket.emit('draw_response', { 'game_id': gameId, 'accept': accept });
    });

    socket.on('draw_response', (data) => {
        if (data.accept) {
            statusElement.textContent = 'Draw accepted.';
            gameOver('draw');
        } else {
            statusElement.textContent = 'Draw declined.';
        }
    });

    socket.on('resign', (data) => {
        statusElement.textContent = `${data.player} has resigned. You win!`;
        gameStarted = false;
        isGameOver = true;
        clearInterval(timerInterval);
        board.destroy();
    });

    socket.on('error', (data) => {
        statusElement.textContent = `Error: ${data.message}`;
    });

    function determineMyColor(player_white, player_black) {
        if (player_white.username === username) {
            return 'white';
        } else if (player_black.username === username) {
            return 'black';
        }
        return null;
    }

    function highlightYou(playerWhiteName, playerBlackName) {
        if (playerWhiteName === username) {
            playerWhiteElement.textContent += ' (You)';
        }
        if (playerBlackName === username) {
            playerBlackElement.textContent += ' (You)';
        }
    }

    function initializeOnlineBoard(fen) {
        console.log("Initializing online board with FEN:", fen);
        board = Chessboard('chess-board', {
            position: fen,
            draggable: true,
            orientation: myColor, // Используем определенный цвет игрока
            onDragStart: onDragStartOnline,
            onDrop: onDropOnline,
            onSnapEnd: onSnapEndOnline,
            pieceTheme: 'https://chessboardjs.com/img/chesspieces/alpha/{piece}.png'
        });
    }

    function onDragStartOnline(source, piece, position, orientation) {
        if (!gameStarted || isGameOver) return false;
        if ((myColor === 'white' && piece.search(/^w/) === -1) ||
            (myColor === 'black' && piece.search(/^b/) === -1)) {
            return false;
        }
        if ((myColor === 'white' && chessGame.turn() !== 'w') ||
            (myColor === 'black' && chessGame.turn() !== 'b')) {
            return false;
        }
    }

    function onDropOnline(source, target) {
        const move = chessGame.move({
            from: source,
            to: target,
            promotion: 'q'
        });
        if (move === null) return 'snapback';
        board.position(chessGame.fen());
        statusElement.textContent = "Move sent. Waiting for opponent...";
        currentTurnElement.textContent = `Current Turn: ${capitalizeFirstLetter(chessGame.turn() === 'w' ? 'white' : 'black')}`;
        startTimer();
        if (socket) {
            socket.emit('move', { 
                'game_id': gameId, 
                'move': { 'from': source, 'to': target } 
            });
        }
    }

    function onSnapEndOnline() {
        board.position(chessGame.fen());
    }
}

resignButton.addEventListener('click', () => {
    if (!gameStarted || isGameOver) return;
    if (confirm('Are you sure you want to resign?')) {
        if (localGame) {
            statusElement.textContent = 'You have resigned. Game over.';
            isGameOver = true;
            clearInterval(timerInterval);
            board.destroy();
        } else {
            if (socket) socket.emit('resign', { 'game_id': gameId });
            statusElement.textContent = 'You have resigned. You lose.';
            gameStarted = false;
            isGameOver = true;
            clearInterval(timerInterval);
            board.destroy();
        }
    }
});

offerDrawButton.addEventListener('click', () => {
    if (!gameStarted || isGameOver) return;
    if (confirm('Do you want to offer a draw?')) {
        if (localGame) {
            statusElement.textContent = 'Game ended in a draw.';
            isGameOver = true;
            clearInterval(timerInterval);
            board.destroy();
        } else {
            if (socket) socket.emit('offer_draw', { 'game_id': gameId });
            statusElement.textContent = 'Draw offer sent. Waiting for opponent\'s response.';
        }
    }
});

updateTimerDisplay();