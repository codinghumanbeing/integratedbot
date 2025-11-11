#!/usr/bin/env python
# -*- coding: utf-8 -*-
# bot_final.py — SELL ALL FIRST → THEN 24/7 TRADING
# EC2 SESSION MANAGER READY
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
    r = requests.get(BASE_URL + "/v3/serverTime")
    if r.status_code == 200:
        return r.json().get("serverTime")
    return int(time.time() * 1000)

def get_balance():
    payload = {"timestamp": get_server_time() or int(time.time() * 1000)}
    r = requests.get(
        BASE_URL + "/v3/balance",
        params=payload,
        headers={"RST-API-KEY": API_KEY, "MSG-SIGNATURE": sign(payload)}
    )
    return r.json()

def sign(params):
    query = '&'.join([f"{k}={params[k]}" for k in sorted(params)])
    return hmac.new(SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()


# === 1. SELL ALL HOLDINGS (RUN ONCE) ===
def sell_all_at_once():
    print(f"\nSELL ALL HOLDINGS — {time.strftime('%Y-%m-%d %H:%M:%S')} HKT")
    
    # Get balance using the same payload structure
    payload = {"timestamp": int(time.time() * 1000)}
    r = requests.get(
        BASE_URL + "/v3/balance",
        params=payload,
        headers={"RST-API-KEY": API_KEY, "MSG-SIGNATURE": sign(payload)}
    )
    data = r.json().get("Wallet", {})   # <-- CHANGED: "Wallet" instead of "SpotWallet"
    
    sold = 0
    for asset, info in data.items():
        free = info.get("Free", 0)       # <-- CHANGED: "Free" (capital F)
        if free > 0 and asset != "USD":
            pair = f"{asset}/USD"
            qty = round(free, 6)
            print(f"[SELL] {qty} {pair}")
            
            p = {
                "timestamp": int(time.time() * 1000),
                "pair": pair,
                "side": "SELL",
                "quantity": qty,
                "type": "MARKET"
            }
            r2 = requests.post(
                BASE_URL + "/v3/place_order",
                data=p,
                headers={"RST-API-KEY": API_KEY, "MSG-SIGNATURE": sign(p)}
            )
            res = r2.json().get("OrderDetail", {})
            status = res.get("Status", "ERROR")
            price = res.get("FilledAverPrice", "N/A")
            print(f"  → {status} @ {price}")
            if status == "FILLED":
                sold += 1
            time.sleep(1)
    
    print(f"SELL ALL COMPLETE — {sold} assets sold\n")
    print("-" * 60)


# === 2. TRADING FUNCTIONS ===
def get_ticker():
    r = requests.get(BASE_URL + "/v3/ticker", params={"timestamp": int(time.time())})
    print(f"[DEBUG] ticker: {r.status_code}")
    data = r.json().get("Data", {})
    rising = [p for p, d in data.items() if d.get("Change", 0) >= 0.05]
    prices = [data[p]["LastPrice"] for p in rising]
    print(f"[TICKER] Found {len(rising)} rising: {rising}")
    return rising, prices, data


def place_order(pair, side, qty):
    global bought_stocks
    qty = round(qty, 1)
    payload = {
        "timestamp": int(time.time() * 1000),
        "pair": pair,
        "side": side,
        "quantity": qty,
        "type": "MARKET"
    }
    print(f"[ORDER] {side} {qty} {pair}")
    r = requests.post(
        BASE_URL + "/v3/place_order",
        data=payload,
        headers={"RST-API-KEY": API_KEY, "MSG-SIGNATURE": sign(payload)}
    )
    print(f"[RESPONSE] {r.text[:200]}")
    res = r.json()
    od = res.get("OrderDetail", {})
    if od.get("Status") == "FILLED":
        price = float(od["FilledAverPrice"])
        if side == "BUY":
            bought_stocks[pair] = {"price": price, "qty": qty}
            print(f"[BOUGHT] {pair} @ {price:.6f} | Holdings: {len(bought_stocks)}")
        else:
            bought_stocks.pop(pair, None)
            print(f"[SOLD] {pair} | Holdings: {len(bought_stocks)}")
    return res


# === MAIN: SELL ALL → THEN TRADE FOREVER ===
if __name__ == "__main__":
    print("BOT STARTED — EC2 SESSION MANAGER")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')} HKT")
    print("Step 1: Sell all holdings")
    print("Step 2: Start 15-min buy / 5-min sell trading")
    print("-" * 60)

    # === RUN SELL ALL ONCE ===
    sell_all_at_once()

    # === START TRADING LOOP ===
    print("TRADING LOOP STARTED")
    print("Buy: every 15 min | Sell Check: every 5 min | TP: +3% | SL: -1.5%")
    print("-" * 60)

    while True:
        now = time.time()

        # SELL CHECK
        if now >= next_sell_check and bought_stocks:
            print(f"\n[SELL CHECK] @ {time.strftime('%H:%M:%S')}")
            rising, prices, market = get_ticker()
            for pair, pos in list(bought_stocks.items()):
                cur = market[pair].get("AskPrice") or market[pair]["LastPrice"]
                pnl = (cur - pos["price"]) / pos["price"]
                print(f"  [P/L] {pair}: {pnl:+.2%}")
                if pnl >= 0.03:
                    print(f"  TAKE PROFIT +3%")
                    place_order(pair, "SELL", pos["qty"])
                    stopgainloss = True
                elif pnl <= -0.015:
                    print(f"  STOP-LOSS -1.5%")
                    place_order(pair, "SELL", pos["qty"])
                    stopgainloss = True
            next_sell_check = now + 300

        # BUY CYCLE
        if now >= next_buy_time or stopgainloss:
            print(f"\n[BUY CYCLE] @ {time.strftime('%H:%M:%S')}")
            rising, prices, market = get_ticker()
            if rising and not stopgainloss:
                pair = rising[stock_index % len(rising)]
                price = prices[stock_index % len(rising)]
                qty = round(1000 / price, 1)
                print(f"[BUY] Selecting {pair} @ {price:.6f} → Qty: {qty}")
                place_order(pair, "BUY", qty)
                stock_index += 1
            next_buy_time = now + 900
            stopgainloss = False

        time.sleep(10)