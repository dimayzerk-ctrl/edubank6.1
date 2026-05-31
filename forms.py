from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    PasswordField,
    SubmitField,
    DecimalField,
    SelectField
)
from wtforms.validators import DataRequired, Email, EqualTo, Length, NumberRange


class RegisterForm(FlaskForm):
    username = StringField(
        'Имя пользователя',
        validators=[DataRequired(), Length(min=3, max=20)]
    )
    email = StringField(
        'Email',
        validators=[DataRequired(), Email()]
    )
    password = PasswordField(
        'Пароль',
        validators=[DataRequired(), Length(min=6)]
    )
    confirm_password = PasswordField(
        'Подтвердите пароль',
        validators=[DataRequired(), EqualTo('password')]
    )
    submit = SubmitField('Зарегистрироваться')


class LoginForm(FlaskForm):
    email = StringField(
        'Email',
        validators=[DataRequired(), Email()]
    )
    password = PasswordField(
        'Пароль',
        validators=[DataRequired()]
    )
    submit = SubmitField('Войти')


class TransferForm(FlaskForm):
    recipient = StringField(
        'Имя получателя',
        validators=[DataRequired()]
    )
    amount = DecimalField(
        'Сумма',
        places=2,
        validators=[DataRequired(), NumberRange(min=0.01, message='Сумма должна быть больше 0')]
    )
    description = StringField(
        'Описание',
        validators=[Length(max=200)]
    )
    submit = SubmitField('Перевести')


class SavingsForm(FlaskForm):
    amount = DecimalField(
        'Сумма',
        places=2,
        validators=[DataRequired(), NumberRange(min=0.01, message='Сумма должна быть больше 0')]
    )
    action = SelectField(
        'Действие',
        choices=[
            ('deposit', 'Пополнить'),
            ('withdraw', 'Вывести')
        ],
        validators=[DataRequired()]
    )
    submit = SubmitField('Подтвердить')


class PaymentForm(FlaskForm):
    category = SelectField(
        'Категория',
        choices=[
            ('Мобильная связь', 'Мобильная связь'),
            ('Интернет', 'Интернет'),
            ('ЖКХ', 'ЖКХ'),
            ('Игры', 'Игры'),
            ('Подписки', 'Подписки')
        ],
        validators=[DataRequired()]
    )
    amount = DecimalField(
        'Сумма',
        places=2,
        validators=[DataRequired(), NumberRange(min=0.01, message='Сумма должна быть больше 0')]
    )
    submit = SubmitField('Оплатить')
    
class SubscriptionForm(FlaskForm):
    submit = SubmitField('Оформить подписку за 150₽')
