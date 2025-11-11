#!/usr/bin/env python
# -*- coding: utf-8 -*-
# bot_final.py — SELL ALL FIRST → THEN 24/7 TRADING
# EC2 SESSION MANAGER READY
import requests
import hashlib
import hmac
import time

# === FIXED: Correct API base path ===
API_KEY = "Uf1MjnJxofjvkQPyrN1YKTEdERgsjGtBznDVh8hqmEG4gqjHvgc1FCI6EqGmKvuy"
SECRET = "5CL4KCVLEYyLLaSq2Jg7VCCu3QsWQYTcv1gQTMngnBG81YJ9VWopJBIwIqsaNjqR"
BASE_URL = "https://mock-api.roostoo.com/api"  # ← FIXED: /api not /v3

# GLOBALS
bought_stocks = {}
next_sell_check = 0
next_buy_time = 0
stopgainloss = False
stock_index = 0


def get_server_time():
    """Correct endpoint: /api/servertime"""
    for _ in range(3):
        try:
            r = requests.get(f"{BASE_URL}/servertime")
            if r.status_code == 200:
                st = r.json().get("serverTime")
                if st:
                    print(f"[SERVER TIME] {st}")
                    return int(st)
        except:
            pass
        time.sleep(1)
    print("[WARNING] Using local time")
    return int(time.time() * 1000)


def sign(params):
    query = '&'.join(f"{k}={params[k]}" for k in sorted(params))
    return hmac.new(SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()


def get_balance():
    ts = get_server_time()
    payload = {"timestamp": ts}
    r = requests.post(
        f"{BASE_URL}/balance",
        data=payload,
        headers={"RST-API-KEY": API_KEY, "MSG-SIGNATURE": sign(payload)}
    )
    print(f"[BALANCE] {r.status_code} | {r.text[:200]}")
    return r


# === SELL ALL ===
def sell_all_at_once():
    print(f"\nSELL ALL — {time.strftime('%Y-%m-%d %H:%M:%S')} HKT")
    
    r = None
    for i in range(3):
        r = get_balance()
        if r.status_code == 200:
            break
        print(f"[RETRY] Balance {i+1}/3...")
        time.sleep(2)
    if not r or r.status_code != 200:
        print(f"ERROR: Balance failed: {r.text if r else 'No response'}")
        return
    
    wallet = r.json().get("Wallet", {})
    print(f"[WALLET] {list(wallet.keys())}")
    
    sold = 0
    for asset, info in wallet.items():
        free = info.get("Free", 0) or info.get("free", 0)
        if free > 0.0001 and asset != "USD":
            pair = f"{asset}/USD"
            qty = round(free, 6)
            print(f"[SELL] {qty} {pair}")
            
            p = {
                "timestamp": get_server_time(),
                "pair": pair,
                "side": "SELL",
                "quantity": qty,
                "type": "MARKET"
            }
            r2 = requests.post(
                f"{BASE_URL}/place_order",
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
    
    print(f"SELL ALL DONE — {sold} assets sold")
    print("-" * 60)


# === TRADING ===
def get_ticker():
    r = requests.get(f"{BASE_URL}/ticker", params={"timestamp": int(time.time() * 1000)})
    data = r.json().get("Data", {})
    rising = [p for p, d in data.items() if d.get("Change", 0) >= 0.05]
    prices = [d["LastPrice"] for p, d in data.items() if p in rising]
    print(f"[TICKER] {len(rising)} rising")
    return rising, prices, data


def place_order(pair, side, qty):
    global bought_stocks
    qty = round(qty, 1)
    p = {
        "timestamp": get_server_time(),
        "pair": pair,
        "side": side,
        "quantity": qty,
        "type": "MARKET"
    }
    r = requests.post(
        f"{BASE_URL}/place_order",
        data=p,
        headers={"RST-API-KEY": API_KEY, "MSG-SIGNATURE": sign(p)}
    )
    od = r.json().get("OrderDetail", {})
    if od.get("Status") == "FILLED":
        price = float(od["FilledAverPrice"])
        if side == "BUY":
            bought_stocks[pair] = {"price": price, "qty": qty}
            print(f"[BOUGHT] {pair} @ {price:.2f}")
        else:
            bought_stocks.pop(pair, None)
            print(f"[SOLD] {pair}")
    return r


# === MAIN ===
if __name__ == "__main__":
    print("BOT STARTED")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')} HKT")
    print("-" * 60)

    sell_all_at_once()

    print("TRADING LOOP STARTED")
    print("Buy: 15 min | Sell Check: 5 min | TP +3% | SL -1.5%")
    print("-" * 60)

    while True:
        now = time.time()

        # SELL CHECK
        if now >= next_sell_check and bought_stocks:
            print(f"\n[SELL CHECK] {time.strftime('%H:%M:%S')}")
            rising, prices, market = get_ticker()
            for pair, pos in list(bought_stocks.items()):
                cur = market.get(pair, {}).get("AskPrice") or market.get(pair, {}).get("LastPrice")
                if not cur: continue
                pnl = (cur - pos["price"]) / pos["price"]
                if pnl >= 0.03:
                    place_order(pair, "SELL", pos["qty"])
                    stopgainloss = True
                elif pnl <= -0.015:
                    place_order(pair, "SELL", pos["qty"])
                    stopgainloss = True
            next_sell_check = now + 300

        # BUY
        if now >= next_buy_time or stopgainloss:
            print(f"\n[BUY CYCLE] {time.strftime('%H:%M:%S')}")
            rising, prices, market = get_ticker()
            if rising and not stopgainloss:
                idx = stock_index % len(rising)
                pair = rising[idx]
                price = prices[idx]
                qty = max(0.1, round(1000 / price, 1))
                place_order(pair, "BUY", qty)
                stock_index += 1
            next_buy_time = now + 900
            stopgainloss = False

        time.sleep(10)