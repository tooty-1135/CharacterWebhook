import aiomysql
import os

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER", "your_user"),
    "password": os.getenv("MYSQL_PASSWORD", "your_password"),
    "db": os.getenv("MYSQL_DATABASE", "your_db"),
    "autocommit": True,
    "minsize": 1,
    "maxsize": 5,
}

pool = None

async def init_db():
    global pool
    if pool is None:
        pool = await aiomysql.create_pool(**MYSQL_CONFIG)

async def get_conn():
    global pool
    if pool is None:
        await init_db()
    return pool
