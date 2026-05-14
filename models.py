from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    balance = db.Column(db.Float, default=1000.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    amount = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    description = db.Column(db.String(255))
    # Тип транзакции: PAYMENT, ROUNDUP_PAYMENT, TRANSFER, SAVINGS
    type = db.Column(db.String(32), default='PAYMENT')
    # Сумма округления (для ROUNDUP_PAYMENT)
    round_up_amount = db.Column(db.Float, default=0.0)

class SavingsAccount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    balance = db.Column(db.Float, default=0.0)

# ── ИЗЮМИНКА: Промежуточный буфер транзакций ──────────────────────────────
# Реализует Atomic Payment Buffering (APB):
# Транзакция сначала попадает сюда со статусом HELD,
# проходит проверку баланса и только потом применяется (COMPLETED)
# или отклоняется (REJECTED). Это гарантирует ACID-свойства даже при
# одновременных запросах (Race Condition защита).
class PendingTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    round_up_amount = db.Column(db.Float, default=0.0)
    category = db.Column(db.String(100))
    # Статусы: HELD → COMPLETED | REJECTED
    status = db.Column(db.String(16), default='HELD')
    type = db.Column(db.String(32), default='PAYMENT')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
