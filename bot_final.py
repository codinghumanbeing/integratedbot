#!/usr/bin/env python
# -*- coding: utf-8 -*-
# bot_final.py — ROOSTOO MOCK API — SELL ALL + 24/7 TRADING
import requests
import hashlib
import hmac
import time

API_KEY = "Uf1MjnJxofjvkQPyrN1YKTEdERgsjGtBznDVh8hqmEG4gqjHvgc1FCI6EqGmKvuy"
SECRET = "5CL4KCVLEYyLLaSq2Jg7VCCu3QsWQYTcv1gQTMngnBG81YJ9VWopJBIwIqsaNjqR"
BASE_URL = "https://mock-api.roostoo.com"

# GLOBALS
bought_stocks = {}
next_sell_check = 0
next_buy_time = 0
stopgainloss = False
stock_index = 0


def get_server_time():
    r = requests.get(f"{BASE_URL}/api/v3/time")  # CORRECT PATH
    if r.status_code == 200:
        st = r.json()["serverTime"]
        print(f"[TIME] Server time: {st}")
        return int(st)
    print(f"[TIME] Failed, using local: {int(time.time() * 1000)}")
    return int(time.time() * 1000)


def sign(params):
    query = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
    return hmac.new(SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()


def get_balance():
    ts = get_server_time()
    params = {"timestamp": ts}
    signature = sign(params)
    headers = {"X-MBX-APIKEY": API_KEY}
    r = requests.get(
        f"{BASE_URL}/api/v3/account",
        params={**params, "signature": signature},  # MERGE DICT
        headers=headers
    )
    print(f"[BALANCE] {r.status_code} | {r.text[:200]}")
    return r


# === SELL ALL ===
def sell_all_at_once():
    print(f"\nSELL ALL — {time.strftime('%Y-%m-%d %H:%M:%S')} HKT")
    r = get_balance()
    if r.status_code != 200:
        print("Balance failed. Wallet empty or API down.")
        return

    balances = r.json().get("balances", [])
    print(f"Found {len(balances)} assets")
    sold = 0

    for b in balances:
        asset = b["asset"]
        free = float(b["free"])
        if free > 0.0001 and asset != "USDT":
            symbol = f"{asset}USDT"
            qty = round(free, 6)
            print(f"[SELL] {qty} {symbol}")

            ts = get_server_time()
            params = {
                "symbol": symbol,
                "side": "SELL",
                "type": "MARKET",
                "quantity": qty,
                "timestamp": ts
            }
            signature = sign(params)
            headers = {"X-MBX-APIKEY": API_KEY}
            r2 = requests.post(
                f"{BASE_URL}/api/v3/order",
                params={**params, "signature": signature},
                headers=headers
            )
            res = r2.json()
            status = res.get("status", "ERR")
            print(f"  → {status}")
            if status == "FILLED":
                sold += 1
            time.sleep(1)

    print(f"SELL ALL DONE — {sold} sold")
    print("-" * 60)


# === TRADING ===
def get_ticker():
    r = requests.get(f"{BASE_URL}/api/v3/ticker/24hr")
    data = r.json()
    rising = [d for d in data if float(d.get("priceChangePercent", 0)) >= 5.0]
    prices = [float(d["lastPrice"]) for d in rising]
    market = {d["symbol"]: d for d in data}
    print(f"[TICKER] {len(rising)} rising")
    return rising, prices, market


def place_order(symbol, side, qty):
    global bought_stocks
    qty = round(qty, 6)
    ts = get_server_time()
    params = {
        "symbol": symbol,
        "side": side,
        "type": "MARKET",
        "quantity": qty,
        "timestamp": ts
    }
    signature = sign(params)
    headers = {"X-MBX-APIKEY": API_KEY}
    r = requests.post(
        f"{BASE_URL}/api/v3/order",
        params={**params, "signature": signature},
        headers=headers
    )
    res = r.json()
    status = res.get("status")
    if status == "FILLED":
        filled = float(res.get("executedQty", qty))
        avg = float(res.get("cummulativeQuoteQty", 0)) / filled if filled else 0
        if side == "BUY":
            bought_stocks[symbol] = {"price": avg, "qty": filled}
            print(f"[BOUGHT] {symbol} @ {avg:.2f}")
        else:
            bought_stocks.pop(symbol, None)
            print(f"[SOLD] {symbol}")
    return res


# === MAIN ===
if __name__ == "__main__":
    print("BOT STARTED")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')} HKT")
    print("-" * 60)

    sell_all_at_once()

    print("TRADING LOOP STARTED")
    print("Buy: 15 min | Sell: 5 min | TP +3% | SL -1.5%")
    print("-" * 60)

    while True:
        now = time.time()

        if now >= next_sell_check and bought_stocks:
            print(f"\n[SELL CHECK] {time.strftime('%H:%M:%S')}")
            _, _, market = get_ticker()
            for symbol, pos in list(bought_stocks.items()):
                cur = float(market.get(symbol, {}).get("askPrice") or market.get(symbol, {}).get("lastPrice", 0))
                if cur == 0: continue
                pnl = (cur - pos["price"]) / pos["price"]
                if pnl >= 0.03:
                    place_order(symbol, "SELL", pos["qty"])
                    stopgainloss = True
                elif pnl <= -0.015:
                    place_order(symbol, "SELL", pos["qty"])
                    stopgainloss = True
            next_sell_check = now + 300

        if now >= next_buy_time or stopgainloss:
            print(f"\n[BUY CYCLE] {time.strftime('%H:%M:%S')}")
            rising, prices, _ = get_ticker()
            if rising and not stopgainloss:
                d = rising[stock_index % len(rising)]
                symbol = d["symbol"]
                price = float(d["lastPrice"])
                qty = max(0.000001, round(1000 / price, 6))
                place_order(symbol, "BUY", qty)
                stock_index += 1
            next_buy_time = now + 900
            stopgainloss = False

        time.sleep(10)