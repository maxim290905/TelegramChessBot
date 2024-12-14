# models.py

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import chess
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    elorating = db.Column(db.Integer, default=1000)
    wins = db.Column(db.Integer, default=0)
    losses = db.Column(db.Integer, default=0)
    auth_token = db.Column(db.String(36), unique=True, nullable=True)
    
    # Другие поля и методы

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

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_white_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    player_black_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fen = db.Column(db.String, nullable=False, default=chess.Board().fen())
    is_active = db.Column(db.Boolean, default=True)
    is_waiting = db.Column(db.Boolean, default=True)
    time_left_white = db.Column(db.Integer, default=600)  # 10 минут в секундах
    time_left_black = db.Column(db.Integer, default=600)  # 10 минут в секундах
    last_move_time = db.Column(db.DateTime, default=datetime.utcnow)  # Добавлено поле
    result = db.Column(db.String, nullable=True)
    
    # Определение отношений
    player_white = db.relationship('User', foreign_keys=[player_white_id], backref='white_games')
    player_black = db.relationship('User', foreign_keys=[player_black_id], backref='black_games')