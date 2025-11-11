#!/usr/bin/env python
# -*- coding: utf-8 -*-
# bot_final.py — SELL ALL FIRST → THEN 24/7 TRADING (FIXED PER ROOSTOO DOCS)
# EC2 SESSION MANAGER READY
import requests
import hashlib
import hmac
import time

API_KEY = "Uf1MjnJxofjvkQPyrN1YKTEdERgsjGtBznDVh8hqmEG4gqjHvgc1FCI6EqGmKvuy"
SECRET = "5CL4KCVLEYyLLaSq2Jg7VCCu3QsWQYTcv1gQTMngnBG81YJ9VWopJBIwIqsaNjqR"
BASE_URL = "https://mock-api.roostoo.com"  # No /api prefix

# GLOBALS
bought_stocks = {}
next_sell_check = 0
next_buy_time = 0
stopgainloss = False
stock_index = 0


def get_server_time():
    r = requests.get(BASE_URL + "/v3/servertime")
    print(f"[DEBUG TIME] Status: {r.status_code}, Response: {r.text[:100]}")
    if r.status_code == 200:
        return int(r.json()["serverTime"])
    return int(time.time() * 1000)


def sign(params):
    query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
    print(f"[DEBUG SIGN] Query: {query_string}")
    return hmac.new(SECRET.encode(), query_string.encode(), hashlib.sha256).hexdigest()


def get_balance():
    ts = get_server_time()
    params = {"timestamp": ts}
    headers = {
        "X-MBX-APIKEY": API_KEY,  # FIXED: Correct header per docs
        "Content-Type": "application/x-www-form-urlencoded"
    }
    r = requests.get(
        BASE_URL + "/v3/account",  # FIXED: /v3/account, not /balance
        params=params,
        headers=headers + {"X-MBX-APIKEY": API_KEY, "signature": sign(params)}  # Signature in query
    )
    print(f"[BALANCE] Status: {r.status_code}, Response: {r.text[:200]}")
    return r


# === 1. SELL ALL HOLDINGS (RUN ONCE - DOCS-COMPLIANT) ===
def sell_all_at_once():
    print(f"\nSELL ALL HOLDINGS — {time.strftime('%Y-%m-%d %H:%M:%S')} HKT")
    
    r = get_balance()
    if r.status_code != 200:
        print(f"ERROR: Balance fetch failed - {r.text}")
        return
    
    balances = r.json().get("balances", [])  # FIXED: 'balances' array per docs
    print(f"[DEBUG] Balances found: {len(balances)} assets")
    
    sold = 0
    failed = []
    for bal in balances:
        asset = bal.get("asset", "")
        free = float(bal.get("free", 0))  # FIXED: 'free' lowercase
        if free > 0.0001 and asset != "USDT":  # Skip USDT (base currency)
            symbol = f"{asset}USDT"  # FIXED: USDT pairs per docs
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
            headers = {"X-MBX-APIKEY": API_KEY}
            r2 = requests.post(
                BASE_URL + "/v3/order",  # FIXED: /v3/order
                params={"timestamp": ts, "signature": sign(params)},  # Auth in query params
                data=params,  # Body for order details
                headers=headers
            )
            print(f"[DEBUG SELL] Status: {r2.status_code}, Response: {r2.text[:200]}")
            
            if r2.status_code == 200:
                res = r2.json()
                status = res.get("status", "ERROR")  # FIXED: 'status' per docs
                if status == "FILLED":
                    sold += 1
                    print(f"  → FILLED @ avg ~{res.get('cummulativeQuoteQty', 'N/A') / qty:.2f}")
                else:
                    print(f"  → {status}: {res}")
                    failed.append((asset, qty))
            else:
                print(f"  → HTTP {r2.status_code}: {r2.text}")
                failed.append((asset, qty))
            
            time.sleep(1)  # Rate limit
    
    print(f"SELL ALL COMPLETE — {sold} sold, {len(failed)} failed: {failed}")
    print("-" * 60)


# === 2. TRADING FUNCTIONS ===
def get_ticker():
    params = {"symbol": ""}  # Empty for all symbols
    r = requests.get(BASE_URL + "/v3/ticker/24hr", params=params)  # FIXED: /v3/ticker/24hr
    print(f"[TICKER] Status: {r.status_code}")
    data = r.json()  # No 'Data' wrapper; direct array/object per docs
    # Filter rising >=5% (docs: priceChangePercent)
    rising = [s for s in data if float(s.get("priceChangePercent", 0)) >= 5.0]
    prices = [float(s["lastPrice"]) for s in rising]
    print(f"[TICKER] Found {len(rising)} rising: {[s['symbol'] for s in rising]}")
    return rising, prices, {s["symbol"]: s for s in data}  # Dict by symbol


def place_order(symbol, side, qty):
    global bought_stocks
    qty = round(qty, 6)  # Higher precision for small coins
    ts = get_server_time()
    params = {
        "symbol": symbol,
        "side": side,
        "type": "MARKET",
        "quantity": qty,
        "timestamp": ts
    }
    headers = {"X-MBX-APIKEY": API_KEY}
    r = requests.post(
        BASE_URL + "/v3/order",
        params={"timestamp": ts, "signature": sign(params)},
        data=params,
        headers=headers
    )
    print(f"[ORDER {side}] {qty} {symbol} | Response: {r.text[:200]}")
    res = r.json()
    status = res.get("status")
    if status == "FILLED":
        filled_qty = float(res.get("executedQty", qty))
        avg_price = float(res.get("cummulativeQuoteQty", 0)) / filled_qty if filled_qty else 0
        if side == "BUY":
            bought_stocks[symbol] = {"price": avg_price, "qty": filled_qty}
            print(f"[BOUGHT] {symbol} @ {avg_price:.2f} | Holdings: {len(bought_stocks)}")
        else:
            bought_stocks.pop(symbol, None)
            print(f"[SOLD] {symbol} | Holdings: {len(bought_stocks)}")
    return res


# === MAIN: SELL ALL → THEN TRADE FOREVER ===
if __name__ == "__main__":
    print("BOT STARTED — EC2 SESSION MANAGER (ROOSTOO DOCS FIXED)")
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
            _, _, market = get_ticker()
            for symbol, pos in list(bought_stocks.items()):
                ticker = market.get(symbol, {})
                cur = float(ticker.get("askPrice", ticker.get("lastPrice", 0)))
                if cur == 0:
                    print(f"  [SKIP] {symbol}: No price")
                    continue
                pnl = (cur - pos["price"]) / pos["price"]
                print(f"  [P/L] {symbol}: {pnl:+.2%}")
                if pnl >= 0.03:
                    print(f"  TAKE PROFIT +3%")
                    place_order(symbol, "SELL", pos["qty"])
                    stopgainloss = True
                elif pnl <= -0.015:
                    print(f"  STOP-LOSS -1.5%")
                    place_order(symbol, "SELL", pos["qty"])
                    stopgainloss = True
            next_sell_check = now + 300

        # BUY CYCLE
        if now >= next_buy_time or stopgainloss:
            print(f"\n[BUY CYCLE] @ {time.strftime('%H:%M:%S')}")
            rising, prices, _ = get_ticker()
            if rising and not stopgainloss:
                idx = stock_index % len(rising)
                symbol = rising[idx]["symbol"]
                price = prices[idx]
                qty = round(1000 / price, 6)  # $1000 worth, precise qty
                if qty > 0.000001:  # Min qty check
                    print(f"[BUY] {symbol} @ {price:.2f} → Qty: {qty}")
                    place_order(symbol, "BUY", qty)
                    stock_index += 1
            next_buy_time = now + 900
            stopgainloss = False

        # Precise sleep
        sleep_time = min(
            max(0, next_sell_check - time.time()),
            max(0, next_buy_time - time.time()),
            10
        )
        time.sleep(sleep_time)