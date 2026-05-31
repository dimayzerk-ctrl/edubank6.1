from flask import Flask, render_template, redirect, url_for, flash, request
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from sqlalchemy import select
from math import ceil
from datetime import datetime
from config import Config
from models import db, User, Transaction, SavingsAccount, Subscription, PendingTransaction
from forms import (
    RegisterForm,
    LoginForm,
    TransferForm,
    SavingsForm,
    PaymentForm,
    SubscriptionForm
)

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ── ИЗЮМИНКА: Atomic Payment Buffering ────────────────────────────────────
# Шаг 1: создаём PendingTransaction HELD — "бронируем" деньги
# Шаг 2: Pessimistic Lock (with_for_update) — блокируем строку пользователя
#         Если два запроса придут одновременно — второй ждёт первого.
#         Это решает Race Condition: баланс не уйдёт в минус.
# Шаг 3: повторная проверка баланса внутри блокировки (TOCTOU-защита)
# Шаг 4: Round-up для ВСЕХ платежей — ceil(99.99) - 99.99 = 0.01 ₽ в копилку
# Шаг 5: HELD → COMPLETED или REJECTED
def atomic_payment(user_id, amount, category):
    round_up = 0.0

    # Шаг 1: буфер
    pending = PendingTransaction(
        user_id=user_id,
        amount=amount,
        category=category,
        status='HELD',
        type='PAYMENT'
    )
    db.session.add(pending)
    db.session.flush()

    # Шаг 2: Pessimistic Lock
    user = db.session.execute(
        select(User).where(User.id == user_id).with_for_update()
    ).scalar_one()

    # Шаг 3: проверка баланса
    if user.balance < amount:
        pending.status = 'REJECTED'
        pending.completed_at = datetime.utcnow()
        db.session.commit()
        return False, 'Недостаточно средств', 0.0

    # Шаг 4: Round-up для ВСЕХ платежей
    # ceil(150.50) = 151, round_up = 0.50 ₽ идёт в накопления
    round_up = round(ceil(amount) - amount, 2)
    if round_up > 0 and user.balance >= (amount + round_up):
        pass  # хватает — берём с округлением
    else:
        round_up = 0.0  # не хватает на копейки — берём без округления

    total = amount + round_up
    user.balance = round(user.balance - total, 2)

    if round_up > 0:
        savings = SavingsAccount.query.filter_by(user_id=user_id).first()
        if savings:
            savings.balance = round(savings.balance + round_up, 2)

    desc = f'Оплата: {category}'
    if round_up > 0:
        desc += f' (+{round_up} ₽ → копилка)'

    transaction = Transaction(
        sender_id=user_id,
        receiver_id=user_id,
        amount=amount,
        round_up_amount=round_up,
        description=desc,
        type='ROUNDUP_PAYMENT' if round_up > 0 else 'PAYMENT'  # ROUNDUP если были копейки
    )
    db.session.add(transaction)

    pending.status = 'COMPLETED'
    pending.round_up_amount = round_up
    pending.completed_at = datetime.utcnow()
    db.session.commit()

    msg = 'Платёж выполнен'
    if round_up > 0:
        msg += f'. {round_up} ₽ округлено и отложено в накопления 🎉'
    return True, msg, round_up


@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data).first():
            flash('Этот email уже зарегистрирован')
            return redirect(url_for('register'))
        if User.query.filter_by(username=form.username.data).first():
            flash('Это имя пользователя уже занято')
            return redirect(url_for('register'))
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.flush()
        savings = SavingsAccount(user_id=user.id, balance=0)
        db.session.add(savings)
        db.session.commit()
        subscription = Subscription(user_id=user.id, active=False)
        db.session.add(subscription)
        db.session.commit()
        flash('Регистрация прошла успешно! Войдите в систему.')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Неверный email или пароль')
    return render_template('login.html', form=form)


@app.route('/dashboard')
@login_required
def dashboard():
    savings = SavingsAccount.query.filter_by(user_id=current_user.id).first()
    if not savings:
        savings = SavingsAccount(user_id=current_user.id, balance=0.0)
        db.session.add(savings)
        db.session.commit()
    return render_template('dashboard.html', savings=savings)


@app.route('/transfer', methods=['GET', 'POST'])
@login_required
def transfer():
    form = TransferForm()

    subscription = Subscription.query.filter_by(
        user_id=current_user.id
    ).first()

    commission_percent = 1 if subscription.active else 3

    if form.validate_on_submit():
        recipient = User.query.filter_by(
            username=form.recipient.data
        ).first()

        amount = float(form.amount.data)

        commission = amount * commission_percent / 100
        total = amount + commission

        if not recipient:
            flash('Получатель не найден')
            return redirect(url_for('transfer'))

        if current_user.balance < total:
            flash('Недостаточно средств')
            return redirect(url_for('transfer'))

        current_user.balance -= total
        recipient.balance += amount

        transaction = Transaction(
            sender_id=current_user.id,
            receiver_id=recipient.id,
            amount=amount,
            description=f'Перевод ({commission_percent}% комиссия)'
        )

        db.session.add(transaction)
        db.session.commit()

        flash(
            f'Перевод выполнен. Комиссия: {commission:.2f}₽'
        )

        return redirect(url_for('dashboard'))

    return render_template(
        'transfer.html',
        form=form,
        commission_percent=commission_percent
    )


@app.route('/savings', methods=['GET', 'POST'])
@login_required
def savings():
    form = SavingsForm()
    savings = SavingsAccount.query.filter_by(user_id=current_user.id).first()
    if not savings:
        savings = SavingsAccount(user_id=current_user.id, balance=0.0)
        db.session.add(savings)
        db.session.commit()
    if form.validate_on_submit():
        amount = float(form.amount.data)
        user = db.session.execute(
            select(User).where(User.id == current_user.id).with_for_update()
        ).scalar_one()
        if form.action.data == 'deposit':
            if user.balance >= amount:
                user.balance = round(user.balance - amount, 2)
                savings.balance = round(savings.balance + amount, 2)
                flash('Средства переведены в накопления')
            else:
                flash('Недостаточно средств')
        elif form.action.data == 'withdraw':
            if savings.balance >= amount:
                savings.balance = round(savings.balance - amount, 2)
                user.balance = round(user.balance + amount, 2)
                flash('Средства выведены с накоплений')
            else:
                flash('Недостаточно накоплений')
        db.session.commit()
        return redirect(url_for('savings'))
    return render_template('savings.html', form=form, savings=savings)


@app.route('/payments', methods=['GET', 'POST'])
@login_required
def payments():
    form = PaymentForm()

    subscription = Subscription.query.filter_by(
        user_id=current_user.id
    ).first()

    if subscription.active:
        game_commission = 3
    else:
        game_commission = 5

    if form.validate_on_submit():
        amount = float(form.amount.data)

        commission_percent = 0

        if form.category.data == 'Игры':
            commission_percent = game_commission

        commission = amount * commission_percent / 100
        total = amount + commission

        if current_user.balance < total:
            flash('Недостаточно средств')
            return redirect(url_for('payments'))

        current_user.balance -= total

        transaction = Transaction(
            sender_id=current_user.id,
            receiver_id=current_user.id,
            amount=amount,
            description=f'Оплата: {form.category.data}'
        )

        db.session.add(transaction)
        db.session.commit()

        flash(
            f'Платёж выполнен. Комиссия: {commission:.2f}₽'
        )

        return redirect(url_for('payments'))

    return render_template(
        'payments.html',
        form=form,
        game_commission=game_commission
    )


@app.route('/history')
@login_required
def history():
    transactions = Transaction.query.filter(
        (Transaction.sender_id == current_user.id) |
        (Transaction.receiver_id == current_user.id)
    ).order_by(Transaction.timestamp.desc()).all()
    pending = PendingTransaction.query.filter_by(
        user_id=current_user.id
    ).order_by(PendingTransaction.created_at.desc()).limit(10).all()
    return render_template('history.html', transactions=transactions, pending=pending)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
