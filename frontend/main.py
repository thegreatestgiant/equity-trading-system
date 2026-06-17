import streamlit as st

from api_client import (
    get_positions,
    get_trade_by_id,
    get_trade_by_symbol,
    get_trades,
    login,
    logout,
    submit_trade,
    register,
    add_account_to_user,
    update_user_account,
    update_trade,
)

if "username" not in st.session_state:
    st.session_state.username = None

st.title("Equity Trading System")

if st.session_state.username is None:
    page = st.sidebar.selectbox("Page", ["Login", "Register"])

    if page == "Login":
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        if st.button("Login"):
            result = login(username, password)
            if result["status"] == "success":
                st.session_state.username = username
                st.success("Logged in")
                st.rerun()
            else:
                st.error(result.get("message", "Login failed"))

    elif page == "Register":
        username = st.text_input("New Username")
        password = st.text_input("New Password", type="password")

        if st.button("Register"):
            result = register(username, password)
            if result["status"] == "success":
                st.success(f"Account created for {result['username']}. You can now log in.")
            else:
                st.error(result["message"])

else:
    st.sidebar.write(f"Logged in as: {st.session_state.username}")

    if st.sidebar.button("Logout"):
        logout()
        st.session_state.username = None
        st.rerun()

    page_options = {
        "GET /positions": "All Positions",
        "GET /positions/{symbol}": "Position by Symbol",
        "GET /trades": "All Trades",
        "GET /trades/{trade_id}": "Trade by ID",
        "GET /trades/{symbol}": "Trade by Symbol",
        "POST /trade": "Enter Trade",
        "POST /users/accounts/{account_id}": "Add Account",
        "PUT /users/accounts/{account_id}": "Update Account",
        "PUT /trades/{trade_id}": "Update Trade",
    }

    st.sidebar.markdown("**Pages**")
    selected_label = st.sidebar.radio(
        "Page", list(page_options.keys()), label_visibility="collapsed"
    )
    page = page_options[selected_label]

    if page == "Enter Trade":
        st.header("POST /trade")

        account_id = st.text_input("Account ID")
        symbol = st.text_input("Symbol")
        side = st.selectbox("Side", ["BUY", "SELL"])
        quantity = st.number_input("Quantity", min_value=1)
        price = st.number_input("Price", min_value=0.01)

        if st.button("Submit Trade"):
            trade = {
                "username": st.session_state.username,
                "account_id": account_id,
                "symbol": symbol.upper(),
                "side": side,
                "quantity": quantity,
                "price": price,
            }

            result = submit_trade(trade)
            st.json(result)

    elif page == "All Positions":
        st.header("GET /positions")

        if st.button("Load Positions"):
            result = get_positions()
            st.table(result)

    elif page == "Position by Symbol":
        st.header("GET /positions/{symbol}")

        symbol = st.text_input("Symbol", "AAPL")

        if st.button("Load Position"):
            result = get_positions(symbol)
            st.json(result)

    elif page == "All Trades":
        st.header("GET /trades")

        if st.button("Load Trades"):
            result = get_trades()
            st.table(result)


    elif page == "Trade by ID":

        st.header("GET /trades/{trade_id}")

        trade_id = st.text_input("Trade ID", "T001")

        if st.button("Load Trade"):
            result = get_trade_by_id(trade_id)

            st.json(result)

    elif page == "Trade by Symbol":
        st.header("GET /trades/{symbol}")

        trade_id = st.text_input("Symbol", "")

        if st.button("Load Trades"):
            result = get_trade_by_symbol(trade_id)
            st.json(result)



    elif page == "Add Account":
        st.header("POST /users/accounts/{account_id}")

        account_id = st.text_input("Account ID")

        if st.button("Add Account"):
            result = add_account_to_user(account_id)
            st.json(result)

    elif page == "Update Account":
        st.header("PUT /users/accounts/{account_id}")

        account_id = st.text_input("Account ID")
        can_short = st.checkbox("Can Short")

        if st.button("Update Account"):
            data = {
                "username": st.session_state.username,
                "can_short": can_short,
            }

            result = update_user_account(account_id, data)
            st.json(result)

    elif page == "Update Trade":
        st.header("PUT /trades/{trade_id}")

        trade_id = st.text_input("Trade ID")
        symbol = st.text_input("New Symbol")
        side = st.selectbox("New Side", ["BUY", "SELL"])
        quantity = st.number_input("New Quantity", min_value=1)
        price = st.number_input("New Price", min_value=0.01)

        if st.button("Update Trade"):
            data = {
                "symbol": symbol.upper(),
                "side": side,
                "quantity": quantity,
                "price": price,
            }

            result = update_trade(trade_id, data)
            st.json(result)