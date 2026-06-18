-- just some schema to start things off... the rest is not really finalized

CREATE TYPE trade_direction AS ENUM ('Buy', 'Sell');

CREATE TABLE trade (
    trade_id UUID PRIMARY KEY,
    account_id UUID,
    user_id UUID,
    direction trade_direction,
    symbol_ticker VARCHAR(4),
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    quantity INT,
    price NUMERIC,
    other_account UUID
);

CREATE TABLE positions (
    position_id INT PRIMARY KEY,
    account_id UUID,
    symbol_ticker VARCHAR(4),
    quantity INT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

