from redis.asyncio import ConnectionPool, Redis
from app.core.config import redis_host, redis_port_number, computed_max_connections

pool = ConnectionPool(
    host=redis_host,
    port=redis_port_number,
    db=0,
    max_connections=computed_max_connections,
)

redis_client = Redis(connection_pool=pool)

# Redis hash names keyed by domain object
USERS_KEY = "users"
ACCOUNTS_KEY = "accounts"
POSITIONS_KEY = "positions"
USERNAMES_KEY = "username"
MARKET_PRICES_KEY = "market_prices"
