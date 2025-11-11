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
    """Fixed: Use correct endpoint /v3/servertime (lowercase 'time')"""
    for attempt in range(3):
        try:
            r = requests.get(BASE_URL + "/v3/servertime")  # ← FIXED: was /serverTime
            print(f"[DEBUG SERVER TIME] Status: {r.status_code}, Response: {r.text[:200]}")
            if r.status_code == 200:
                data = r.json()
                server_time = data.get("serverTime") or data.get("servertime") or data.get("time")
                if server_time:
                    print(f"[SERVER TIME] Retrieved: {server_time}")
                    return int(server_time)
        except Exception as e:
            print(f"[ERROR] Server time fetch failed: {e}")
        time.sleep(1)
    print("[WARNING] Using local time as fallback")
    return int(time.time() * 1000)


def sign(params):
    query = '&'.join([f"{k}={params[k]}" for k in sorted(params)])
    print(f"[DEBUG SIGN] Query: {query}")
    signature = hmac.new(SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    print(f"[DEBUG SIGN] Signature: {signature}")
    return signature


def get_balance():
    ts = get_server_time()
    if ts is None:
        print("[ERROR] get_server_time() returned None")
        return None
    payload = {"timestamp": ts}
    print(f"[DEBUG BALANCE] Sending payload: {payload}")
    
    r = requests.post(
        BASE_URL + "/v3/balance",
        data=payload,
        headers={"RST-API-KEY": API_KEY, "MSG-SIGNATURE": sign(payload)}
    )
    print(f"[DEBUG BALANCE] Response: {r.status_code} - {r.text[:300]}...")
    return r


# === 1. SELL ALL HOLDINGS (RUN ONCE - BULLETPROOF) ===
def sell_all_at_once():
    print(f"\nSELL ALL HOLDINGS — {time.strftime('%Y-%m-%d %H:%M:%S')} HKT")
    
    r = None
    for attempt in range(3):
        r = get_balance()
        if r and r.status_code == 200:
            break
        print(f"[RETRY] Balance attempt {attempt+1} failed. Waiting...")
        time.sleep(2)
    else:
        print(f"ERROR: Balance fetch failed after 3 attempts: {r.text if r else 'No response'}")
        return
    
    data = r.json().get("Wallet", {})
    print(f"[DEBUG] Wallet keys: {list(data.keys())}")
    
    sold = 0
    failed = []
    for asset, info in data.items():
        free = info.get("Free", 0) or info.get("free", 0)
        if free > 0.0001 and asset != "USD":
            pair = f"{asset}/USD"
            qty = round(free, 6)
            print(f"[SELL] {qty} {pair}")
            
            success = False
            for attempt in range(3):
                p = {
                    "timestamp": get_server_time(),
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
                print(f"[DEBUG SELL] Status: {r2.status_code} | {r2.text[:200]}...")
                
                if r2.status_code == 200:
                    res = r2.json().get("OrderDetail", {})
                    status = res.get("Status", "ERROR")
                    price = res.get("FilledAverPrice", "N/A")
                    print(f"  → {status} @ {price}")
                    if status == "FILLED":
                        sold += 1
                        success = True
                        break
                time.sleep(2 ** attempt)
            
            if not success:
                failed.append((asset, qty))
            
            time.sleep(1)
    
    print(f"SELL ALL COMPLETE — {sold} sold, {len(failed)} failed: {failed}")
    if failed:
        print("Check: pair exists? min qty? rate limit?")
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


# === MAIN ===
if __name__ == "__main__":
    print("BOT STARTED — EC2 SESSION MANAGER")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')} HKT")
    print("Step 1: Sell all holdings")
    print("Step 2: Start 15-min buy / 5-min sell trading")
    print("-" * 60)

    sell_all_at_once()

    print("TRADING LOOP STARTED")
    print("Buy: every 15 min | Sell Check: every 5 min | TP: +3% | SL: -1.5%")
    print("-" * 60)

    while True:
        now = time.time()

        if now >= next_sell_check and bought_stocks:
            print(f"\n[SELL CHECK] @ {time.strftime('%H:%M:%S')}")
            rising, prices, market = get_ticker()
            for pair, pos in list(bought_stocks.items()):
                cur = market.get(pair, {}).get("AskPrice") or market.get(pair, {}).get("LastPrice")
                if not cur:
                    continue
                pnl = (float(cur) - pos["price"]) / pos["price"]
                print(f"  [P/L] {pair}: {pnl:+.2%}")
                if pnl >= 0.03:
                    print("  TAKE PROFIT +3%")
                    place_order(pair, "SELL", pos["qty"])
                    stopgainloss = True
                elif pnl <= -0.015:
                    print("  STOP-LOSS -1.5%")
                    place_order(pair, "SELL", pos["qty"])
                    stopgainloss = True
            next_sell_check = now + 300

        if now >= next_buy_time or stopgainloss:
            print(f"\n[BUY CYCLE] @ {time.strftime('%H:%M:%S')}")
            rising, prices, market = get_ticker()
            if rising and not stopgainloss:
                idx = stock_index % len(rising)
                pair = rising[idx]
                price = float(prices[idx])
                qty = round(1000 / price, 1)
                if qty >= 0.1:
                    print(f"[BUY] {pair} @ {price:.6f} → Qty: {qty}")
                    place_order(pair, "BUY", qty)
                    stock_index += 1
            next_buy_time = now + 900
            stopgainloss = False

        sleep_time = min(
            max(0, next_sell_check - time.time()),
            max(0, next_buy_time - time.time()),
            10
        )
        time.sleep(sleep_time)