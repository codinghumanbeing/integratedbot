#!/usr/bin/env python
# -*- coding: utf-8 -*-
# bot_final.py — ROOSTOO COMPETITION — FINAL WORKING
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
    print(f"[TIME] Status: {r.status_code} | {r.text[:100]}")
    if r.status_code == 200:
        return r.json().get("ServerTime")  # FIXED: Capital S
    return int(time.time() * 1000)


def sign(params):
    query = '&'.join([f"{k}={params[k]}" for k in sorted(params)])
    sig = hmac.new(SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    print(f"[SIGN] {query[:60]}... → {sig[:8]}...")
    return sig


def get_balance():
    ts = get_server_time()
    if ts is None:
        print("[ERROR] Server time is None")
        return None
    payload = {"timestamp": ts}
    headers = {
        "RST-API-KEY": API_KEY,
        "MSG-SIGNATURE": sign(payload)
    }
    r = requests.get(BASE_URL + "/v3/balance", params=payload, headers=headers)
    print(f"[BALANCE] Status: {r.status_code} | {r.text[:200]}")
    return r


def get_ticker():
    ts = get_server_time()
    payload = {"timestamp": ts}
    headers = {"RST-API-KEY": API_KEY, "MSG-SIGNATURE": sign(payload)}
    r = requests.get(BASE_URL + "/v3/ticker", params=payload, headers=headers)
    print(f"[TICKER] Status: {r.status_code}")
    if r.status_code != 200:
        return [], [], {}
    data = r.json().get("Data", {})
    
    # Buy: coins up $0.05 or more
    rising = [p for p, d in data.items() if float(d.get("Change", 0)) >= 0.05]
    prices = [float(data[p]["LastPrice"]) for p in rising]
    market = data
    
    print(f"[TICKER] {len(rising)} up $0.05+: {rising[:3]}")
    return rising, prices, market


def place_order(pair, side, qty):
    global bought_stocks
    
    # === STEP SIZE RULES (FROM ROOSTOO MOCK) ===
    STEP_SIZES = {
        'FET/USD': 0.001,
        'UNI/USD': 0.001,
        'AAVE/USD': 0.001,
        'ADA/USD': 0.1,
        'XRP/USD': 0.1,
        'DOGE/USD': 0.1,
        'BONK/USD': 1.0,
        'SHIB/USD': 1000.0,
        'PEPE/USD': 1000.0,
        'FLOKI/USD': 100.0,
        'WLFI/USD': 0.1,
        'PUMP/USD': 0.1,
        'SOMI/USD': 0.1,
        'TRUMP/USD': 0.1,
        'EDEN/USD': 0.1,
        'XLM/USD': 0.1,
        'APT/USD': 0.01,
        'SOL/USD': 0.01,
        'ETH/USD': 0.0001,
        'BTC/USD': 0.00001,
    }
    
    step = STEP_SIZES.get(pair, 0.001)  # Default 0.001
    qty_rounded = (qty // step) * step  # Round down to step
    if qty_rounded < step:
        print(f"[SKIP] {pair}: qty {qty_rounded} < min step {step}")
        return False
    
    qty_str = f"{qty_rounded:.10f}".rstrip('0').rstrip('.')
    print(f"[ROUNDED] {qty} → {qty_str} (step {step})")
    
    ts = get_server_time()
    payload = {
        "timestamp": ts,
        "pair": pair,
        "side": side,
        "quantity": qty_str,
        "type": "MARKET"
    }
    headers = {
        "RST-API-KEY": API_KEY,
        "MSG-SIGNATURE": sign(payload)
    }
    r = requests.post(BASE_URL + "/v3/place_order", data=payload, headers=headers)
    print(f"[ORDER {side}] {qty_str} {pair} | Status: {r.status_code} | {r.text[:200]}")
    
    try:
        res = r.json()
        if res.get("Success") and res.get("OrderDetail", {}).get("Status") == "FILLED":
            price = float(res["OrderDetail"].get("FilledAverPrice", 0))
            if side == "BUY":
                bought_stocks[pair] = {"price": price, "qty": qty_rounded}
                print(f"[BOUGHT] {pair} @ {price:.6f} | Qty: {qty_rounded}")
            else:
                bought_stocks.pop(pair, None)
                print(f"[SOLD] {pair}")
            return True
    except:
        pass
    return False


# === SELL ALL (ONCE) ===
def sell_all_at_once():
    print(f"\nSELL ALL — {time.strftime('%Y-%m-%d %H:%M:%S')} HKT")
    r = get_balance()
    if not r or r.status_code != 200:
        print("ERROR: Balance failed.")
        return
    
    wallet = r.json().get("SpotWallet", {})
    to_sell = []
    for asset, info in wallet.items():
        free = float(info.get("Free", 0))
        if free > 0.0001 and asset != "USD":
            to_sell.append((asset, free))
    
    print(f"Found {len(to_sell)} assets to sell: {[a for a, _ in to_sell[:5]]}...")
    sold = 0
    for asset, free in to_sell:
        pair = f"{asset}/USD"  # FIXED: /USD not USD
        qty = round(free, 6)
        print(f"[SELL] {qty} {pair}")
        if place_order(pair, "SELL", qty):
            sold += 1
        time.sleep(1)
    
    print(f"SELL ALL COMPLETE — {sold}/{len(to_sell)} sold")
    print("-" * 60)


# === MAIN ===
if __name__ == "__main__":
    print("BOT STARTED")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')} HKT")
    print("-" * 60)
    sell_all_at_once()
    print("TRADING STARTED")
    print("-" * 60)
    while True:
        now = time.time()
        if now >= next_sell_check and bought_stocks:
            print(f"\n[SELL CHECK] {time.strftime('%H:%M:%S')}")
            _, _, market = get_ticker()
            for pair, pos in list(bought_stocks.items()):
                d = market.get(pair, {})
                cur = float(d.get("AskPrice") or d.get("LastPrice", 0))
                if cur == 0: continue
                pnl = (cur - pos["price"]) / pos["price"]
                if pnl >= 0.03:
                    place_order(pair, "SELL", pos["qty"])
                    stopgainloss = True
                elif pnl <= -0.015:
                    place_order(pair, "SELL", pos["qty"])
                    stopgainloss = True
            next_sell_check = now + 300
        if now >= next_buy_time or stopgainloss:
            print(f"\n[BUY] {time.strftime('%H:%M:%S')}")
            rising, prices, _ = get_ticker()
            if rising and not stopgainloss:
                idx = stock_index % len(rising)
                pair = rising[idx]
                price = prices[idx]
                qty = round(1000 / price, 6)
                if qty > 0.000001:
                    place_order(pair, "BUY", qty)
                    stock_index += 1
            next_buy_time = now + 900
            stopgainloss = False
        time.sleep(10)