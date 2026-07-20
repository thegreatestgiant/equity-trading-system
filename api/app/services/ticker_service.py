from app.core.redis import redis_client, MARKET_PRICES_KEY

valid_tickers = set()


async def load_sp500():
    ticker_keys = await redis_client.hkeys(MARKET_PRICES_KEY)
    return {
        ticker.decode() if isinstance(ticker, bytes) else ticker
        for ticker in ticker_keys
    }
