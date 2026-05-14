import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "supersecretkey123")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///bank.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False