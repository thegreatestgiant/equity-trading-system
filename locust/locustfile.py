from locust import HttpUser, task, between
import uuid
import random


class EquityTradingUser(HttpUser):
    # Simulates a user waiting 1 to 3 seconds between actions

    wait_time = between(1, 3)
    TICKERS = [
        "AAPL",
        "MSFT",
        "AMZN",
        "GOOG",
        "META",
        "NVDA",
        "JPM",
        "XOM",
        "WMT",
        "PG",
        "KO",
        "PEP",
        "JNJ",
        "V",
        "MA",
    ]

    def on_start(self):
        self.account_ids = []
        # create unique user
        username = f"user_{uuid.uuid4().hex[:8]}"

        for _ in range(3):
            response = self.client.post(
                "/register",
                json={
                    "username": username,
                    "password": "password123",
                },
            )

            if response.status_code == 200:
                break
        else:
            raise Exception("Failed to register after 3 attempts")

        response = self.client.post(
            "/users/account",
            params={"account_name": "Trading", "can_short": True},
        )

        if response.status_code == 200:
            self.account_ids.append(response.json()["account_id"])

        response = self.client.post(
            "/users/account",
            params={"account_name": "Econ", "can_short": True},
        )

        if response.status_code == 200:
            self.account_ids.append(response.json()["account_id"])

        response = self.client.post(
            "/users/account",
            params={"account_name": "Retirement", "can_short": True},
        )

        if response.status_code == 200:
            self.account_ids.append(response.json()["account_id"])

        if len(self.account_ids) != 3:
            raise Exception("Failed to create accounts")

    @task(13)
    def create_trade(self):

        if not self.account_ids:
            return

        account_id = random.choice(self.account_ids)
        ticker = random.choice(self.TICKERS)
        direction = random.choice(["Buy", "Sell"])

        self.client.post(
            "/trade",
            json=[
                {
                    "account_id": account_id,
                    "direction": direction,
                    "ticker": ticker,
                    "quantity": random.randint(1, 500),
                    "price": "200.50",
                }
            ],
        )

    @task(12)
    def create_batchtrade(self):

        if not self.account_ids:
            return

        random_integer = random.randint(1, 10)

        batch_trades = []

        for i in range(random_integer):
            account_id = random.choice(self.account_ids)
            ticker = random.choice(self.TICKERS)
            direction = random.choice(["Buy", "Sell"])
            batch_trades.append(
                {
                    "account_id": account_id,
                    "direction": direction,
                    "ticker": ticker,
                    "quantity": random.randint(1, 500),
                    "price": "200.50",
                }
            )
        self.client.post("/trade", json=batch_trades)

    @task(5)
    def get_positions(self):
        self.client.get("/positions")

    @task(2)
    def get_trades(self):
        self.client.get("/trades")

    @task(1)
    def check_health(self):
        self.client.get("/probe")
