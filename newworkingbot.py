#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Use updated API key and 15-min trading interval logic
import requests
import hashlib
import hmac
import time

API_KEY = "Uf1MjnJxofjvkQPyrN1YKTEdERgsjGtBznDVh8hqmEG4gqjHvgc1FCI6EqGmKvuy"
SECRET = "5CL4KCVLEYyLLaSq2Jg7VCCu3QsWQYTcv1gQTMngnBG81YJ9VWopJBIwIqsaNjqR"

BASE_URL = "https://mock-api.roostoo.com"

# -------------------
# Initialize globals
# -------------------
next_trade_time = int(time.time()) * 1000
stopgainloss = False
global_pricediff = 0
theorderid = None
ispending = False
buy_stocks = []
current_price = []
bought_stocks = {}    # Track: stock → {"price": X, "qty": Y}
stock_index = 0       # Rotate through buy_stocks
exchange_info = {}

def generate_signature(params):
    query_string = '&'.join(["{}={}".format(k, params[k])
                             for k in sorted(params.keys())])
    us = SECRET.encode('utf-8')
    m = hmac.new(us, query_string.encode('utf-8'), hashlib.sha256)
    return m.hexdigest()


# These functions remain unchanged as per instructions
def get_server_time():
    r = requests.get(
        BASE_URL + "/v3/serverTime",
    )
    print (r.status_code, r.text)
    return r.json()


def get_ex_info():
    global exchange_info
    r = requests.get(BASE_URL + "/v3/exchangeInfo")
    print(r.status_code, r.text)
    data = r.json()
    if "TradePairs" in data:
        exchange_info = data["TradePairs"]
    return data


def pending_count():
    payload = {
        "timestamp": int(time.time()) * 1000,
    }

    r = requests.get(
        BASE_URL + "/v3/pending_count",
        params=payload,
        headers={"RST-API-KEY": API_KEY,
                 "MSG-SIGNATURE": generate_signature(payload)}
    )
    print (r.status_code, r.text)
    return r.json()


# -------------------
# Modified below
# -------------------

def get_ticker(pair=None):
    global timestamp
    timestamp = int(time.time())
    payload = {"timestamp": timestamp}
    if pair:
        payload["pair"] = pair

    r = requests.get(BASE_URL + "/v3/ticker", params=payload)
    print (r.status_code, r.text)
    data = r.json()

    global buy_stocks
    global current_price
    buy_stocks = []
    current_price = []

    # Handle nested dictionary structure
    if "Data" in data and isinstance(data["Data"], dict):
        for pair_name, info in data["Data"].items():
            if info.get("Change", 0) >= 0.05:
                buy_stocks.append(pair_name)
                current_price.append(info["MinAsk"])

    return data


def get_balance():
    payload = {"timestamp": int(time.time()) * 1000}
    r = requests.get(
        BASE_URL + "/v3/balance",
        params=payload,
        headers={
            "RST-API-KEY": API_KEY,
            "MSG-SIGNATURE": generate_signature(payload)
        }
    )
    print (r.status_code, r.text)
    return r.json()


def place_order(stock, side, qty, price=None):
    global theorderid
    global next_trade_time
    global global_pricediff
    global stopgainloss
    if stock in exchange_info:
        amount_precision = exchange_info[stock].get("AmountPrecision", 0)
        qty = round(float(qty), amount_precision)
    else:
        qty = round(float(qty), 2)
    payload = {
        "timestamp": int(time.time()) * 1000,
        "pair": stock,
        "side": side,
        "quantity": qty,
    }

    if not price:
        payload['type'] = "MARKET"
    else:
        payload['type'] = "LIMIT"
        payload['price'] = price

    r = requests.post(
        BASE_URL + "/v3/place_order",
        data=payload,
        headers={
            "RST-API-KEY": API_KEY,
            "MSG-SIGNATURE": generate_signature(payload)
        }
    )

    print (r.status_code, r.text)
    try:
        stuff = r.json()
    except ValueError:
        print("⚠️ place_order(): Invalid JSON response:", r.text)

    if "OrderDetail" in stuff:
        theorderid = stuff["OrderDetail"].get("OrderID", None)
        newprice = stuff["OrderDetail"].get("Price", None)
        if side == "BUY" and stuff["OrderDetail"].get("Status") == "Filled":
                    if stock not in bought_stocks:
                        bought_stocks[stock] = {"price": newprice or price, "qty": qty}

        # Calculate price diff when possible
        if current_price and current_price[0] != 0 and newprice:
            global_pricediff = (newprice - current_price[0]) / current_price[0]
            if global_pricediff <= -0.015 or global_pricediff >= 0.03:
                stopgainloss = True

    # Next trade allowed after 15 minutes
    next_trade_time = int(time.time()) * 1000 + (15 * 60 * 1000)
    time.sleep(1)


def cancel_order():
    global theorderid
    if not theorderid:
        return

    payload = {
        "timestamp": int(time.time()) * 1000,
        "order_id": theorderid,
    }

    r = requests.post(
        BASE_URL + "/v3/cancel_order",
        data=payload,
        headers={
            "RST-API-KEY": API_KEY,
            "MSG-SIGNATURE": generate_signature(payload)
        }
    )
    print (r.status_code, r.text)


def query_order():
    global next_trade_time
    global ispending

    payload = {
        "timestamp": int(time.time()) * 1000,
        "order_id": theorderid,
    }

    r = requests.post(
        BASE_URL + "/v3/query_order",
        data=payload,
        headers={
            "RST-API-KEY": API_KEY,
            "MSG-SIGNATURE": generate_signature(payload)
        }
    )

    try:
        data = r.json()
    except ValueError:
        print("query_order(): Invalid JSON response:", r.text)
    if data.get("Status") == "Pending":
        next_trade_time = int(time.time()) * 1000 + 15 * 60 * 1000
        ispending = True
    else:
        ispending = False

    print (r.status_code, r.text)


# -------------------
# Trading logic loop
# -------------------
if __name__ == '__main__':
    while True:
        now = int(time.time()) * 1000

        # Main trading execution every 15 minutes or when stopgainloss flag set
        if (next_trade_time <= now) or stopgainloss:
            get_server_time()
            get_ex_info()
            ticker_data = get_ticker()
            get_balance()

            # === PROFIT-TAKING & STOP-LOSS SELL ===
            sold = False
            for stock, info in list(bought_stocks.items()):
                current_ask = None
                if "Data" in ticker_data and stock in ticker_data["Data"]:
                    current_ask = ticker_data["Data"][stock].get("MinAsk")

                if current_ask:
                    profit_pct = (current_ask - info["price"]) / info["price"]
                    if profit_pct >= 0.03 or profit_pct <= -0.015:
                        place_order(stock, "SELL", info["qty"])
                        del bought_stocks[stock]
                        stopgainloss = True
                        sold = True
                        break

            # === BUY NEXT STOCK (rotate) ===
            if not stopgainloss and not sold and buy_stocks:
                idx = stock_index % len(buy_stocks)
                stock = buy_stocks[idx]
                # Find matching price by index
                price = current_price[idx]
                qty = 1000 / price

                place_order(stock, "BUY", qty)
                stock_index += 1

                query_order()
                pending_count()
            else:
                pending_count()

            if not buy_stocks:
                stock_index = 0  # Reset rotation if no candidates

            stopgainloss = False  # Reset flag after action

        # Cancel if loss threshold triggered
        if global_pricediff <= -0.015 and ispending:
            cancel_order()

        # Sleep check interval (10 seconds)
        time.sleep(10)