import sqlite3
import bcrypt

DB_PATH = "users.db"


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL
        )
        """
    )
    return conn


def get_positions(symbol=None):
    if symbol:
        return {
            "symbol": symbol.upper(),
            "quantity": 100,
            "avg_price": 200.00,
            "market_price": 225.00,
        }

    return [
        {"symbol": "AAPL", "quantity": 100, "avg_price": 200.00},
        {"symbol": "TSLA", "quantity": -50, "avg_price": 320.00},
    ]


def get_trade_by_id(trade_id):
    return {
        "trade_id": trade_id,
        "symbol": "AAPL",
        "side": "BUY",
        "quantity": 100,
        "price": 200.00,
    }

def get_trade_by_symbol(trade_id):
    return {
        "trade_id": trade_id,
        "symbol": "AAPL",
        "side": "BUY",
        "quantity": 100,
        "price": 200.00,
    }



def get_trades():
    return [
        {"trade_id": "T001", "symbol": "AAPL", "side": "BUY", "quantity": 100, "price": 200.00},
        {"trade_id": "T002", "symbol": "TSLA", "side": "SELL", "quantity": 50, "price": 320.00},
    ]


def login(username, password):
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()

        if row is None:
            return {"status": "error", "message": "Invalid username or password"}

        stored_hash = row[0].encode("utf-8")

        if bcrypt.checkpw(password.encode("utf-8"), stored_hash):
            return {"status": "success"}
        else:
            return {"status": "error", "message": "Invalid username or password"}
    finally:
        conn.close()


def logout():
    return {
        "status": "success",
    }


def submit_trade(trade):
    return {
        "status": "accepted",
        "trade_id": "T999",
        "trade": trade,
    }


def register(username, password):
    if not username or not password:
        return {"status": "error", "message": "Username and password are required"}

    conn = _get_db()
    try:
        existing = conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone()

        if existing is not None:
            return {"status": "error", "message": "Username already exists"}

        password_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash),
        )
        conn.commit()

        return {"status": "success", "username": username}
    finally:
        conn.close()


def add_account_to_user(account_id):
    return {
        "status": "success",
        "account_id": account_id,
    }


def update_user_account(account_id, data):
    return {
        "status": "success",
        "account_id": account_id,
        "updated": data,
    }


def update_trade(trade_id, data):
    return {
        "status": "success",
        "trade_id": trade_id,
        "updated": data,
    }