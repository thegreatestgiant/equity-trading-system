import streamlit as st


from api_client import (
   login,
   register,
   logout,
   get_all_positions,
   get_positions_by_account,
   get_positions_by_ticker,
   get_positions_by_account_and_ticker,
   submit_trades,
   get_trades,
   get_trades_by_account,
   get_trades_by_ticker,
   get_trades_by_account_and_ticker,
   get_trade_by_id,
   add_account_to_user,
   create_account,
   get_user_accounts,
   update_user_account,
   update_trade,
)


st.set_page_config(page_title="Equity Trading System", page_icon="📈", layout="wide")


st.markdown(
   """
   <style>
   :root {
       --eq-blue-50:  #eef6ff;
       --eq-blue-100: #dbeeff;
       --eq-blue-200: #b9deff;
       --eq-blue-400: #5aa9ea;
       --eq-blue-500: #2f86d6;
       --eq-blue-700: #1c5e9e;
   }


   .stApp {
       background-color: var(--eq-blue-50);
   }


   /* Sidebar */
   section[data-testid="stSidebar"] {
       background: linear-gradient(180deg, var(--eq-blue-700) 0%, var(--eq-blue-500) 100%);
   }
   section[data-testid="stSidebar"] * {
       color: #ffffff !important;
   }
   section[data-testid="stSidebar"] .stRadio [data-baseweb="radio"] {
       background-color: rgba(255, 255, 255, 0.08);
       border-radius: 8px;
       padding: 6px 10px;
       margin-bottom: 4px;
   }
   section[data-testid="stSidebar"] .stRadio [data-baseweb="radio"]:hover {
       background-color: rgba(255, 255, 255, 0.18);
   }
   section[data-testid="stSidebar"] .stButton button {
       background-color: rgba(255, 255, 255, 0.12);
       color: #ffffff;
       border: 1px solid rgba(255, 255, 255, 0.35);
       border-radius: 8px;
   }
   section[data-testid="stSidebar"] .stButton button:hover {
       background-color: rgba(255, 255, 255, 0.25);
       border-color: #ffffff;
   }
   section[data-testid="stSidebar"] hr {
       border-color: rgba(255, 255, 255, 0.25);
   }


   /* Main content headers */
   h1, h2, h3 {
       color: var(--eq-blue-700);
   }


   /* Primary buttons in main content */
   .stButton button[kind="primary"] {
       background-color: var(--eq-blue-500);
       border-color: var(--eq-blue-500);
   }
   .stButton button[kind="primary"]:hover {
       background-color: var(--eq-blue-700);
       border-color: var(--eq-blue-700);
   }


   /* Cards (st.container(border=True)) */
   div[data-testid="stVerticalBlockBorderWrapper"] {
       border-color: var(--eq-blue-200) !important;
       background-color: #ffffff;
       border-radius: 10px;
   }
   </style>
   """,
   unsafe_allow_html=True,
)


if "username" not in st.session_state:
   st.session_state.username = None


#if "username" not in st.session_state:
#    st.session_state.username = "dev_bypass"  # TODO: remove this before going live, allows to see the main page without logging in


st.title("📈 Equity Trading System")


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
   st.sidebar.markdown(f"👤 **{st.session_state.username}**")
   st.sidebar.divider()


   if st.sidebar.button("🚪 Log Out"):
       logout()
       st.session_state.username = None
       st.rerun()


   page_options = {
       "🏦 My Accounts": "My Accounts",
       "📊 All Positions": "All Positions",
       "📊 Positions by Account": "Positions by Account",
       "📊 Positions by Ticker": "Positions by Ticker",
       "📊 Positions by Account & Ticker": "Positions by Account and Ticker",
       "📜 Trade History": "All Trades",
       "📜 Trade History by Account": "Trades by Account",
       "📜 Trade History by Ticker": "Trades by Ticker",
       "📜 Trade History by Account & Ticker": "Trades by Account and Ticker",
       "🔍 Look Up Trade by ID": "Trade by ID",
       "💸 Book a Trade": "Enter Trade",
       "➕ Open New Account": "Create Account",
       "✏️ Edit Account Settings": "Update Account",
       "✏️ Edit Trade": "Update Trade",
   }


   st.sidebar.markdown("**Navigate**")
   selected_label = st.sidebar.radio(
       "Page", list(page_options.keys()), label_visibility="collapsed"
   )
   page = page_options[selected_label]


   # Lets other pages send the user to "Positions by Account" with a
   # specific account already filled in, e.g. from a My Accounts link.
   if "jump_to_account" in st.session_state:
       page = "Positions by Account"


   if page == "Enter Trade":
       st.header("💸 Book a Trade")
       st.caption("POST /trade")


       # Initialize trade queue and review mode in session state
       if "trade_queue" not in st.session_state:
           st.session_state.trade_queue = []
       if "reviewing" not in st.session_state:
           st.session_state.reviewing = False


       # ── REVIEW & SUBMIT PAGE ──────────────────────────────────────────
       if st.session_state.reviewing:
           st.subheader("Review Trades")


           for i, trade in enumerate(st.session_state.trade_queue):
               with st.container(border=True):
                   cols = st.columns([3, 2, 2, 2, 1])
                   cols[0].write(f"**{trade['ticker']}**  —  {trade['account_id']}")
                   cols[1].write(trade["direction"])
                   cols[2].write(f"Qty: {trade['quantity']}")
                   cols[3].write(f"${trade['price']}")
                   if cols[4].button("✕", key=f"remove_{i}"):
                       st.session_state.trade_queue.pop(i)
                       st.rerun()


           st.divider()
           col_back, col_submit = st.columns([1, 1])


           if col_back.button("← Back"):
               st.session_state.reviewing = False
               st.rerun()


           if col_submit.button("Submit All", type="primary"):
               # Attach user_id to each trade and send as a single array
               payload = [
                   {**trade, "user_id": st.session_state.username}
                   for trade in st.session_state.trade_queue
               ]


               result = submit_trades(payload)


               if result["status"] == "success":
                   st.success(f"All {len(payload)} trades submitted successfully.")
                   st.json(result["data"])
                   st.session_state.trade_queue = []
                   st.session_state.reviewing = False
               else:
                   st.error(f"Submission failed: {result['message']}")


       # ── TRADE BUILDER ─────────────────────────────────────────────────
       else:
           # Show queued trades so far
           if st.session_state.trade_queue:
               st.subheader("Queued Trades")
               for i, trade in enumerate(st.session_state.trade_queue):
                   with st.container(border=True):
                       cols = st.columns([3, 2, 2, 2, 1])
                       cols[0].write(f"**{trade['ticker']}**  —  {trade['account_id']}")
                       cols[1].write(trade["direction"])
                       cols[2].write(f"Qty: {trade['quantity']}")
                       cols[3].write(f"${trade['price']}")
                       if cols[4].button("✕", key=f"q_remove_{i}"):
                           st.session_state.trade_queue.pop(i)
                           st.rerun()
               st.divider()


           # Add a new trade form
           st.subheader("Add Trade")
           account_id = st.text_input("Account ID")
           ticker = st.text_input("Ticker")
           direction = st.selectbox("Direction", ["Buy", "Sell"])
           quantity = st.number_input("Quantity", min_value=1, step=1)
           price = st.number_input("Price", min_value=0.01)
           other_account = st.text_input("Other Account (optional)")


           def _build_trade():
               return {
                   "account_id": account_id,
                   "ticker": ticker.upper(),
                   "direction": direction,
                   "quantity": int(quantity),
                   "price": str(price),  # backend expects price as a string
                   "other_account": other_account or None,
               }


           col_add, col_review = st.columns([1, 1])


           if col_add.button("＋ Add Trade"):
               if not account_id or not ticker:
                   st.error("Account ID and Ticker are required.")
               else:
                   st.session_state.trade_queue.append(_build_trade())
                   st.session_state.last_added_trade = _build_trade()
                   st.rerun()


           if col_review.button(
               "Review & Submit →",
               type="primary",
               disabled=len(st.session_state.trade_queue) == 0 and (not account_id or not ticker),
           ):
               # If the current form holds a trade that hasn't already
               # been added to the queue (via "+ Add Trade"), add it now.
               current = _build_trade() if (account_id and ticker) else None
               if current is not None and current != st.session_state.get("last_added_trade"):
                   st.session_state.trade_queue.append(current)
               st.session_state.reviewing = True
               st.rerun()


   elif page == "My Accounts":
       st.header("🏦 My Accounts")


       if st.button("Refresh"):
           st.session_state.pop("accounts_cache", None)


       if "accounts_cache" not in st.session_state:
           result = get_user_accounts()
           if result["status"] == "success":
               st.session_state.accounts_cache = result["data"]
           else:
               st.session_state.accounts_cache = []
               st.error(result["message"])


       accounts = st.session_state.accounts_cache


       if not accounts:
           st.info("You don't have any accounts yet. Create one to get started.")
       else:
           for account in accounts:
               account_id = account["account_id"]
               name = account.get("name") or "(unnamed account)"
               with st.container(border=True):
                   cols = st.columns([3, 1])
                   cols[0].write(f"**{name}**")
                   cols[0].caption(f"`{account_id}`")
                   if cols[1].button("View Positions →", key=f"acct_{account_id}"):
                       st.session_state.jump_to_account = account_id
                       st.rerun()


   elif page == "All Positions":
       st.header("📊 All Positions")
       st.caption("GET /positions")


       if st.button("Load Positions"):
           result = get_all_positions()
           if result["status"] == "success":
               st.json(result["data"])
           else:
               st.error(result["message"])


   elif page == "Positions by Account":
       st.header("📊 Positions by Account")
       st.caption("GET /positions/accounts/{account_id}")


       prefilled = st.session_state.pop("jump_to_account", "")
       account_id = st.text_input("Account ID", value=prefilled)


       if st.button("Load Positions"):
           result = get_positions_by_account(account_id)
           if result["status"] == "success":
               st.json(result["data"])
           else:
               st.error(result["message"])


   elif page == "Positions by Ticker":
       st.header("📊 Positions by Ticker")
       st.caption("GET /positions/ticker/{ticker}")


       ticker = st.text_input("Ticker", "AAPL")


       if st.button("Load Positions"):
           result = get_positions_by_ticker(ticker.upper())
           if result["status"] == "success":
               st.json(result["data"])
           else:
               st.error(result["message"])


   elif page == "Positions by Account and Ticker":
       st.header("📊 Positions by Account & Ticker")
       st.caption("GET /positions/accounts/{account_id}/ticker/{ticker}")


       account_id = st.text_input("Account ID")
       ticker = st.text_input("Ticker", "AAPL")


       if st.button("Load Position"):
           result = get_positions_by_account_and_ticker(account_id, ticker.upper())
           if result["status"] == "success":
               st.json(result["data"])
           else:
               st.error(result["message"])


   elif page == "All Trades":
       st.header("📜 Trade History")
       st.caption("GET /trades")


       if st.button("Load Trades"):
           result = get_trades()
           if result["status"] == "success":
               if result["data"]:
                   st.table(result["data"])
               else:
                   st.info("No trades found.")
           else:
               st.error(result["message"])


   elif page == "Trades by Account":
       st.header("📜 Trade History by Account")
       st.caption("GET /trades/account/{account_id}")


       account_id = st.text_input("Account ID")


       if st.button("Load Trades"):
           result = get_trades_by_account(account_id)
           if result["status"] == "success":
               if result["data"]:
                   st.table(result["data"])
               else:
                   st.info("No trades found.")
           else:
               st.error(result["message"])


   elif page == "Trades by Ticker":
       st.header("📜 Trade History by Ticker")
       st.caption("GET /trades/ticker/{ticker}")


       ticker = st.text_input("Ticker", "AAPL")


       if st.button("Load Trades"):
           result = get_trades_by_ticker(ticker.upper())
           if result["status"] == "success":
               if result["data"]:
                   st.table(result["data"])
               else:
                   st.info("No trades found.")
           else:
               st.error(result["message"])


   elif page == "Trades by Account and Ticker":
       st.header("📜 Trade History by Account & Ticker")
       st.caption("GET /trades/account/{account_id}/ticker.{ticker}")


       account_id = st.text_input("Account ID")
       ticker = st.text_input("Ticker", "AAPL")


       if st.button("Load Trades"):
           result = get_trades_by_account_and_ticker(account_id, ticker.upper())
           if result["status"] == "success":
               if result["data"]:
                   st.table(result["data"])
               else:
                   st.info("No trades found.")
           else:
               st.error(result["message"])


   elif page == "Trade by ID":
       st.header("🔍 Look Up Trade by ID")
       st.caption("GET /trades/{trade_id}")


       trade_id = st.text_input("Trade ID")


       if st.button("Load Trade"):
           result = get_trade_by_id(trade_id)
           if result["status"] == "success":
               st.json(result["data"])
           else:
               st.error(result["message"])


   elif page == "Create Account":
       st.header("➕ Open a New Account")
       st.caption("POST /users/account")


       name = st.text_input("Account Name", placeholder="e.g. Retirement, Trading")
       can_short = st.checkbox("Can Short")


       if st.button("Create Account"):
           result = create_account(name, can_short)
           if result["status"] == "success":
               account_id = result.get("account_id")
               display_name = result.get("name") or name or "(unnamed account)"
               if account_id:
                   st.success(f"Account **{display_name}** created — ID: `{account_id}`")
                   st.session_state.pop("accounts_cache", None)  # refresh My Accounts
               else:
                   st.success("Account created.")
                   st.warning(
                       "The backend didn't return the new account's ID. "
                       "Check 'My Accounts' to find it."
                   )
           else:
               st.error(result["message"])


   elif page == "Update Account":
       st.header("✏️ Edit Account Settings")
       st.caption("PUT /users/accounts/{account_id}")
       st.caption("This endpoint doesn't exist in the backend yet -- showing mock data.")


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
       st.header("✏️ Edit Trade")
       st.caption("PUT /trades/{trade_id}")
       st.caption("This endpoint doesn't exist in the backend yet -- showing mock data.")


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
