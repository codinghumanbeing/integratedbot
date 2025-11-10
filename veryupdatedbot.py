#!/usr/bin/env python
# -*- coding: utf-8 -*-
# FINAL FIXED: Buys recorded, sells work, sell check immediate
import requests
import hashlib
import hmac
import time
import random

API_KEY = "Uf1MjnJxofjvkQPyrN1YKTEdERgsjGtBznDVh8hqmEG4gqjHvgc1FCI6EqGmKvuy"
SECRET = "5CL4KCVLEYyLLaSq2Jg7VCCu3QsWQYTcv1gQTMngnBG81YJ9VWopJBIwIqsaNjqR"

BASE_URL = "https://mock-api.roostoo.com"

# -------------------
# Initialize globals
# -------------------
next_trade_time = int(time.time()) * 1000
next_sell_check_time = int(time.time()) * 1000 - 30000  # Force immediate first sell check
stopgainloss = False
global_pricediff = 0
theorderid = None
ispending = False
buy_stocks = []
current_price = []
bought_stocks = {}    # stock → {"price": X, "qty": Y, "time": Z}
stock_index = 0
exchange_info = {}
order_info = {}       # orderid → {"stock":, "side":, "qty":, "price":}
expected_buy_price = 0


def generate_signature(params):
    query_string = '&'.join([f"{k}={params[k]}" for k in sorted(params.keys())])
    m = hmac.new(SECRET.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256)
    return m.hexdigest()


def get_server_time():
    r = requests.get(BASE_URL + "/v3/serverTime")
    print(f"[DEBUG] get_server_time: {r.status_code} {r.text}")
    return r.json()


def get_ex_info():
    global exchange_info
    r = requests.get(BASE_URL + "/v3/exchangeInfo")
    print(f"[DEBUG] get_ex_info: {r.status_code} {r.text}")
    data = r.json()
    if "TradePairs" in data:
        exchange_info = data["TradePairs"]
    return data


def pending_count():
    payload = {"timestamp": int(time.time()) * 1000}
    r = requests.get(
        BASE_URL + "/v3/pending_count",
        params=payload,
        headers={"RST-API-KEY": API_KEY, "MSG-SIGNATURE": generate_signature(payload)}
    )
    print(f"[DEBUG] pending_count: {r.status_code} {r.text}")
    return r.json()


def handle_filled(orderid, data):
    global global_pricediff, stopgainloss, bought_stocks, order_info
    if orderid not in order_info:
        return

    info = order_info[orderid]
    stock = info["stock"]
    side = info["side"]
    qty = info["qty"]
    placed_price = info["price"]

    status = data.get("Status")
    if not status and "OrderDetail" in data:
        status = data["OrderDetail"].get("Status")

    if status != "Filled":
        return

    filled_price = None
    if "OrderDetail" in data:
        filled_price = data["OrderDetail"].get("FilledAverPrice")
    if not filled_price:
        filled_price = data.get("Price")
    if not filled_price and "OrderDetail" in data:
        filled_price = data["OrderDetail"].get("Price")
    if not filled_price:
        filled_price = placed_price

    filled_price = float(filled_price)

    print(f"[FILLED] Order {orderid} | {side} {qty} {stock} @ {filled_price:.6f}")

    if side == "BUY":
        bought_stocks[stock] = {
            "price": filled_price,
            "qty": qty,
            "time": int(time.time())
        }
        if expected_buy_price != 0:
            global_pricediff = (filled_price - expected_buy_price) / expected_buy_price
            print(f"[PRICEDIFF] Expected: {expected_buy_price:.6f} | Filled: {filled_price:.6f} | Diff: {global_pricediff:.4%}")
            if global_pricediff <= -0.015 or global_pricediff >= 0.03:
                stopgainloss = True
    elif side == "SELL":
        if stock in bought_stocks:
            del bought_stocks[stock]
            print(f"[SOLD] Removed {stock} from holdings")

    del order_info[orderid]


def get_ticker(pair=None):
    global buy_stocks, current_price
    timestamp = int(time.time())
    payload = {"timestamp": timestamp}
    if pair:
        payload["pair"] = pair

    r = requests.get(BASE_URL + "/v3/ticker", params=payload)
    print(f"[DEBUG] get_ticker: {r.status_code} {r.text}")
    data = r.json()

    buy_stocks = []
    current_price = []

    if "Data" in data and isinstance(data["Data"], dict):
        for pair_name, info in data["Data"].items():
            change = info.get("Change", 0)
            if change >= 0.05:
                buy_stocks.append(pair_name)
                current_price.append(info["LastPrice"])

    print(f"[TICKER] Found {len(buy_stocks)} rising stocks: {buy_stocks}")
    return data


def get_balance():
    payload = {"timestamp": int(time.time()) * 1000}
    r = requests.get(
        BASE_URL + "/v3/balance",
        params=payload,
        headers={"RST-API-KEY": API_KEY, "MSG-SIGNATURE": generate_signature(payload)}
    )
    print(f"[DEBUG] get_balance: {r.status_code} {r.text}")
    return r.json()


def place_order(stock, side, qty, price=None):
    global theorderid, ispending
    if stock in exchange_info:
        amount_precision = exchange_info[stock].get("AmountPrecision", 2)
    else:
        amount_precision = 2
    qty = round(float(qty), amount_precision)

    payload = {
        "timestamp": int(time.time()) * 1000,
        "pair": stock,
        "side": side,
        "quantity": qty,
    }

    if not price:
        payload['type'] = "MARKET"
        print(f"[ORDER] Placing MARKET {side} {qty} {stock}")
    else:
        payload['type'] = "LIMIT"
        payload['price'] = price
        print(f"[ORDER] Placing LIMIT {side} {qty} {stock} @ {price}")

    r = requests.post(
        BASE_URL + "/v3/place_order",
        data=payload,
        headers={"RST-API-KEY": API_KEY, "MSG-SIGNATURE": generate_signature(payload)}
    )

    print(f"[RESPONSE] place_order: {r.status_code} {r.text}")
    try:
        stuff = r.json()
    except ValueError:
        print("place_order(): Invalid JSON response:", r.text)
        return

    if "OrderDetail" not in stuff:
        print(f"[ERROR] No OrderDetail in response")
        return

    order_detail = stuff["OrderDetail"]
    theorderid = order_detail.get("OrderID")
    status = order_detail.get("Status", "Unknown")

    if not theorderid:
        print(f"[ERROR] No OrderID returned")
        return

    # RECORD ORDER FIRST
    order_info[theorderid] = {
        "stock": stock,
        "side": side,
        "qty": qty,
        "price": price
    }

    # HANDLE FILL IMMEDIATELY
    handle_filled(theorderid, stuff)

    # ONLY SET PENDING IF NOT FILLED
    if status == "Filled":
        avg_price = order_detail.get("FilledAverPrice", "N/A")
        print(f"[INSTANT FILL] Order {theorderid} filled @ {avg_price}")
        ispending = False
    else:
        print(f"[PENDING] Order {theorderid} is {status} - will query later")
        ispending = True

    time.sleep(1)


def cancel_order():
    global theorderid
    if not theorderid:
        return

    payload = {"timestamp": int(time.time()) * 1000, "order_id": theorderid}
    r = requests.post(
        BASE_URL + "/v3/cancel_order",
        data=payload,
        headers={"RST-API-KEY": API_KEY, "MSG-SIGNATURE": generate_signature(payload)}
    )
    print(f"[CANCEL] {r.status_code} {r.text}")


def query_order():
    global theorderid, ispending
    if not theorderid:
        return

    payload = {"timestamp": int(time.time()) * 1000, "order_id": theorderid}
    r = requests.post(
        BASE_URL + "/v3/query_order",
        data=payload,
        headers={"RST-API-KEY": API_KEY, "MSG-SIGNATURE": generate_signature(payload)}
    )

    try:
        data = r.json()
    except ValueError:
        print("query_order(): Invalid JSON:", r.text)
        return

    status = data.get("Status", "Unknown")
    print(f"[QUERY] Order {theorderid}: {status}")
    handle_filled(theorderid, data)
    ispending = (status == "Pending")


# -------------------
# MAIN TRADING LOOP
# -------------------
if __name__ == '__main__':
    print("TRADING BOT STARTED - FULLY FIXED - Debug ON")
    print(f"Current time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} HKT")

    while True:
        now = int(time.time()) * 1000
        sold_any = False

        print(f"[LOOP] {time.strftime('%H:%M:%S')} | Holdings:{len(bought_stocks)} | SellReady:{next_sell_check_time <= now}")

        # Handle pending orders
        if ispending:
            query_order()

        # SELL CHECK: Every 30 seconds — ALWAYS RUN
        if next_sell_check_time <= now:
            print(f"\n[SELL CHECK] @ {time.strftime('%H:%M:%S')} | Holdings: {len(bought_stocks)}")

            if bought_stocks:
                ticker_data = get_ticker()

                # Optional: Simulate price movement (±2%) — COMMENT OUT FOR REAL API
                if "Data" in ticker_data:
                    for p in ticker_data["Data"]:
                        old = ticker_data["Data"][p]["LastPrice"]
                        change = random.uniform(-0.02, 0.02)
                        new = round(old * (1 + change), 6)
                        ticker_data["Data"][p]["LastPrice"] = new
                        ticker_data["Data"][p]["AskPrice"] = round(new * 1.001, 6)

                for stock, info in list(bought_stocks.items()):
                    buy_price = info["price"]
                    qty = info["qty"]

                    cur = None
                    if "Data" in ticker_data and stock in ticker_data["Data"]:
                        cur = ticker_data["Data"][stock].get("AskPrice") or ticker_data["Data"][stock].get("LastPrice")

                    if not cur:
                        print(f"  [SKIP] {stock} – no price")
                        continue

                    profit_pct = (cur - buy_price) / buy_price
                    print(f"  [CHECK] {stock}")
                    print(f"      Buy: {buy_price:.6f} | Now: {cur:.6f} | P/L: {profit_pct:+.4%}")

                    if profit_pct >= 0.03:
                        print(f"      SELLING (Take-Profit +3%)")
                        place_order(stock, "SELL", qty)
                        sold_any = True
                    elif profit_pct <= -0.015:
                        print(f"      SELLING (Stop-Loss -1.5%)")
                        place_order(stock, "SELL", qty)
                        sold_any = True
                    else:
                        print(f"      HOLDING (P/L {profit_pct:+.4%})")
            else:
                print("  [INFO] No holdings – nothing to check")

            next_sell_check_time = now + (30 * 1000)
            if sold_any:
                stopgainloss = True

        # BUY CYCLE: Every 15 minutes OR after sell
        if (next_trade_time <= now) or stopgainloss:
            print(f"\n[BUY CYCLE] @ {time.strftime('%H:%M:%S')}")
            get_server_time()
            get_ex_info()
            ticker_data = get_ticker()
            get_balance()

            if not stopgainloss and buy_stocks and not sold_any:
                idx = stock_index % len(buy_stocks)
                stock = buy_stocks[idx]
                price = current_price[idx]
                expected_buy_price = price
                qty = round(1000 / price, 6)

                print(f"[BUY] Selecting {stock} @ {price:.6f} | Qty: {qty}")
                place_order(stock, "BUY", qty)
                stock_index += 1
            else:
                reason = []
                if stopgainloss: reason.append("stopgainloss")
                if not buy_stocks: reason.append("no candidates")
                if sold_any: reason.append("just sold")
                print(f"[BUY] Skipped – {', '.join(reason)}")

            pending_count()
            if not buy_stocks:
                stock_index = 0

            next_trade_time = int(time.time()) * 1000 + (15 * 60 * 1000)
            stopgainloss = False

        # Final pending + bad fill cancel
        if ispending:
            query_order()

        if global_pricediff <= -0.015 and ispending:
            print(f"[CANCEL] Buy filled too low ({global_pricediff:.4%})")
            cancel_order()

        pending_count()
        time.sleep(10)