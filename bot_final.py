#!/usr/bin/env python
# -*- coding: utf-8 -*-
# bot_final.py — SELL ALL FIRST → THEN 24/7 TRADING
# EC2 SESSION MANAGER READY
import requests
import hashlib
import hmac
import time
import urllib.parse  # For potential encoding debug

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
    for attempt in range(2):  # Retry once
        try:
            r = requests.get(BASE_URL + "/v3/serverTime")
            if r.status_code == 200:
                return r.json().get("serverTime")
        except:
            pass
        time.sleep(1)
    return int(time.time() * 1000)  # Fallback


def sign(params):
    # Build query string from sorted keys
    query = '&'.join([f"{k}={params[k]}" for k in sorted(params)])
    print(f"[DEBUG SIGN] Query string: {query}")  # <-- NEW: See exact signed string
    signature = hmac.new(SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    print(f"[DEBUG SIGN] Signature: {signature}")  # <-- NEW
    return signature


def get_balance():
    ts = get_server_time()
    payload = {"timestamp": ts}
    print(f"[DEBUG BALANCE] Timestamp: {ts}, Payload: {payload}")
    
    # Use POST like place_order to avoid GET param encoding issues
    r = requests.post(  # <-- CHANGED: POST with data
        BASE_URL + "/v3/balance",
        data=payload,  # <-- CHANGED: data= (body), not params
        headers={"RST-API-KEY": API_KEY, "MSG-SIGNATURE": sign(payload)}
    )
    print(f"[DEBUG BALANCE] Response: {r.status_code} - {r.text[:300]}...")
    return r


# === 1. SELL ALL HOLDINGS (RUN ONCE - BULLETPROOF VERSION) ===
def sell_all_at_once():
    print(f"\nSELL ALL HOLDINGS — {time.strftime('%Y-%m-%d %H:%M:%S')} HKT")
    
    # Get balance with retry
    for attempt in range(2):
        r = get_balance()
        if r.status_code == 200:
            break
        print(f"[ERROR] Balance attempt {attempt+1} failed. Retrying...")
        time.sleep(2)
    else:
        print(f"ERROR: Balance fetch failed after retries - {r.text}")
        return
    
    data = r.json().get("Wallet", {})
    print(f"[DEBUG] Wallet keys: {list(data.keys())}")
    
    sold = 0
    failed = []
    for asset, info in data.items():
        free = info.get("Free", 0)
        if free > 0.0001 and asset != "USD":  # Skip dust & USD
            pair = f"{asset}/USD"
            qty = round(free, 6)
            print(f"[SELL] {qty} {pair}")
            
            success = False
            for attempt in range(3):
                ts = get_server_time()
                p = {
                    "timestamp": ts,
                    "pair": pair,
                    "side": "SELL",
                    "quantity": qty,
                    "type": "MARKET"
                }
                print(f"[DEBUG SELL] Payload: {p}")  # <-- NEW: See sell payload
                r2 = requests.post(
                    BASE_URL + "/v3/place_order",
                    data=p,
                    headers={"RST-API-KEY": API_KEY, "MSG-SIGNATURE": sign(p)}
                )
                print(f"[DEBUG] Sell attempt {attempt+1}: {r2.status_code} - {r2.text[:200]}...")
                
                if r2.status_code == 200:
                    res = r2.json().get("OrderDetail", {})
                    status = res.get("Status", "ERROR")
                    price = res.get("FilledAverPrice", "N/A")
                    print(f"  → {status} @ {price}")
                    if status == "FILLED":
                        sold += 1
                        success = True
                        break
                    else:
                        print(f"  → FAILED ({status}): {res}")
                else:
                    print(f"  → HTTP {r2.status_code}: {r2.text}")
                time.sleep(2 ** attempt)  # Exponential backoff
            
            if not success:
                failed.append((asset, qty))
            
            time.sleep(1)  # Rate limit buffer
    
    print(f"SELL ALL COMPLETE — {sold} sold, {len(failed)} failed: {failed}")
    if failed:
        print("WARNING: Some assets failed. Check pairs, min qty, or API limits.")
    print("-" * 60)


# === 2. TRADING FUNCTIONS ===
def get_ticker():
    ts = int(time.time() * 1000)
    r = requests.get(BASE_URL + "/v3/ticker", params={"timestamp": ts})
    print(f"[TICKER] Status: {r.status_code}")
    data = r.json().get("Data", {})
    rising = [p for p, d in data.items() if d.get("Change", 0) >= 0.05]
    prices = [data[p]["LastPrice"] for p in rising]
    print(f"[TICKER] Found {len(rising)} rising: {rising}")
    return rising, prices, data


def place_order(pair, side, qty):
    global bought_stocks
    qty = round(qty, 1)
    payload = {
        "timestamp": get_server_time(),
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
                cur = market.get(pair, {}).get("AskPrice") or market.get(pair, {}).get("LastPrice")
                if cur is None:
                    print(f"  [SKIP] {pair}: No price data")
                    continue
                pnl = (float(cur) - pos["price"]) / pos["price"]
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
                idx = stock_index % len(rising)
                pair = rising[idx]
                price = float(prices[idx])
                qty = round(1000 / price, 1)
                if qty < 0.1:
                    print(f"[SKIP BUY] {pair}: Qty {qty} too small")
                else:
                    print(f"[BUY] Selecting {pair} @ {price:.6f} → Qty: {qty}")
                    place_order(pair, "BUY", qty)
                    stock_index += 1
            next_buy_time = now + 900
            stopgainloss = False

        # Smart sleep: wait until next event
        sleep_time = min(
            *[max(0, t - time.time()) for t in [next_sell_check, next_buy_time] if t > 0],
            10
        )
        time.sleep(sleep_time)