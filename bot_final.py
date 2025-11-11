#!/usr/bin/env python
# -*- coding: utf-8 -*-
# bot_final.py — SELL ALL → 24/7 TRADING (EXACT ROOSTOO DEMO)
import requests
import hashlib
import hmac
import time

API_KEY = "Uf1MjnJxofjvkQPyrN1YKTEdERgsjGtBznDVh8hqmEG4gqjHvgc1FCI6EqGmKvuy"
SECRET = "5CL4KCVLEYyLLaSq2Jg7VCCu3QsWQYTcv1gQTMngnBG81YJ9VWopJBIwIqsaNjqR"
BASE_URL = "https://mock-api.roostoo.com"  # Demo exact

# GLOBALS
bought_stocks = {}
next_sell_check = 0
next_buy_time = 0
stopgainloss = False
stock_index = 0


def get_server_time():
    r = requests.get(BASE_URL + "/v3/serverTime")  # Demo exact (capital T)
    print(f"[TIME] Status: {r.status_code} | {r.text[:100]}")
    if r.status_code == 200:
        return r.json().get("serverTime")
    return int(time.time() * 1000)


def sign(params):
    query = '&'.join([f"{k}={params[k]}" for k in sorted(params)])  # Demo exact
    sig = hmac.new(SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    print(f"[SIGN] {query[:50]}... → {sig[:8]}...")
    return sig


def get_balance():
    ts = get_server_time()
    payload = {"timestamp": ts}
    headers = {
        "RST-API-KEY": API_KEY,       # FIXED: Demo header
        "MSG-SIGNATURE": sign(payload) # FIXED: Demo signature
    }
    r = requests.get(BASE_URL + "/v3/balance", params=payload, headers=headers)  # Demo exact
    print(f"[BALANCE] Status: {r.status_code} | {r.text[:200]}")
    return r


def get_ticker():
    ts = int(time.time() * 1000)
    payload = {"timestamp": ts}
    headers = {"RST-API-KEY": API_KEY, "MSG-SIGNATURE": sign(payload)}
    r = requests.get(BASE_URL + "/v3/ticker", params=payload, headers=headers)  # Demo style for private?
    print(f"[TICKER] Status: {r.status_code} | {r.text[:100]}")
    if r.status_code != 200:
        return [], [], {}
    data = r.json().get("Data", {})  # Demo exact
    rising = [p for p, d in data.items() if float(d.get("Change", 0)) >= 5.0]  # "Change" field
    prices = [float(data[p]["LastPrice"]) for p in rising]
    market = data
    print(f"[TICKER] {len(rising)} rising: {rising[:3]}...")
    return rising, prices, market


def place_order(pair, side, qty):
    global bought_stocks
    ts = get_server_time()
    payload = {
        "timestamp": ts,
        "pair": pair,
        "side": side,
        "quantity": str(round(qty, 6)),  # String for precision
        "type": "MARKET"
    }
    headers = {
        "RST-API-KEY": API_KEY,
        "MSG-SIGNATURE": sign(payload)
    }
    r = requests.post(BASE_URL + "/v3/place_order", data=payload, headers=headers)  # Demo exact (data=)
    print(f"[ORDER {side}] {qty} {pair} | Status: {r.status_code} | {r.text[:200]}")
    try:
        res = r.json()
        od = res.get("OrderDetail", {})
        status = od.get("Status", "ERROR")
        if status == "FILLED":
            price = float(od.get("FilledAverPrice", 0))
            if side == "BUY":
                bought_stocks[pair] = {"price": price, "qty": qty}
                print(f"[BOUGHT] {pair} @ {price:.4f} | Holdings: {len(bought_stocks)}")
            else:
                bought_stocks.pop(pair, None)
                print(f"[SOLD] {pair} | Holdings: {len(bought_stocks)}")
            return True
    except:
        pass
    print(f"[ORDER FAIL] {pair}")
    return False


# === SELL ALL (ONCE) ===
def sell_all_at_once():
    print(f"\nSELL ALL — {time.strftime('%Y-%m-%d %H:%M:%S')} HKT")
    r = get_balance()
    if r.status_code != 200:
        print("ERROR: Balance failed (check keys/network).")
        return
    wallet = r.json().get("Wallet", {})  # Demo exact
    to_sell = []
    for asset, info in wallet.items():
        free = float(info.get("Free", 0))  # Capital F per demo
        if free > 0.0001 and asset != "USD":
            to_sell.append((asset, free))
    print(f"[BALANCE] {len(to_sell)} assets to sell: {[a for a, _ in to_sell[:5]]}...")
    sold = 0
    for asset, free in to_sell:
        pair = f"{asset}USD"  # Demo format
        qty = round(free, 6)
        print(f"[SELL] {qty} {pair}")
        if place_order(pair, "SELL", qty):
            sold += 1
        time.sleep(1)  # Rate limit
    print(f"SELL ALL COMPLETE — {sold}/{len(to_sell)} sold")
    print("-" * 60)


# === MAIN ===
if __name__ == "__main__":
    print("BOT STARTED — ROOSTOO COMPETITION")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')} HKT")
    print("1. Sell all (once)")
    print("2. Trade: Buy rising every 15m, sell check 5m (TP+3%, SL-1.5%)")
    print("-" * 60)
    sell_all_at_once()
    print("TRADING STARTED")
    print("-" * 60)
    while True:
        now = time.time()
        # SELL CHECK
        if now >= next_sell_check and bought_stocks:
            print(f"\n[SELL CHECK] {time.strftime('%H:%M:%S')}")
            _, _, market = get_ticker()
            for pair, pos in list(bought_stocks.items()):
                d = market.get(pair, {})
                cur = float(d.get("AskPrice") or d.get("LastPrice", 0))
                if cur == 0: continue
                pnl = (cur - pos["price"]) / pos["price"]
                print(f"  [P/L] {pair}: {pnl:+.2%}")
                if pnl >= 0.03:
                    print("  TP +3%")
                    place_order(pair, "SELL", pos["qty"])
                    stopgainloss = True
                elif pnl <= -0.015:
                    print("  SL -1.5%")
                    place_order(pair, "SELL", pos["qty"])
                    stopgainloss = True
            next_sell_check = now + 300
        # BUY
        if now >= next_buy_time or stopgainloss:
            print(f"\n[BUY] {time.strftime('%H:%M:%S')}")
            rising, prices, _ = get_ticker()
            if rising and not stopgainloss:
                idx = stock_index % len(rising)
                pair = rising[idx]
                price = prices[idx]
                qty = round(1000 / price, 6)
                if qty > 0.000001:
                    print(f"  Buy {pair} @ {price:.4f} ({qty})")
                    place_order(pair, "BUY", qty)
                    stock_index += 1
            next_buy_time = now + 900
            stopgainloss = False
        time.sleep(10)