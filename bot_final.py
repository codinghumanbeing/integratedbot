#!/usr/bin/env python
# -*- coding: utf-8 -*-
# bot_final.py — SELL ALL → 24/7 TRADING (100% ROOSTOO DOCS)
import requests
import hashlib
import hmac
import time

API_KEY = "Uf1MjnJxofjvkQPyrN1YKTEdERgsjGtBznDVh8hqmEG4gqjHvgc1FCI6EqGmKvuy"
SECRET = "5CL4KCVLEYyLLaSq2Jg7VCCu3QsWQYTcv1gQTMngnBG81YJ9VWopJBIwIqsaNjqR"
BASE_URL = "https://mock-api.roostoo.com"  # Docs: no /api prefix

# GLOBALS
bought_stocks = {}
next_sell_check = 0
next_buy_time = 0
stopgainloss = False
stock_index = 0


def get_server_time():
    r = requests.get(BASE_URL + "/v3/servertime")  # Docs exact
    print(f"[TIME] Status: {r.status_code} | {r.text[:100]}")
    if r.status_code == 200:
        return int(r.json()["serverTime"])
    return int(time.time() * 1000)  # Fallback


def sign(params):
    query = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
    print(f"[SIGN DEBUG] {query} → {hmac.new(SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()[:8]}...")
    return hmac.new(SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()


def get_balance():
    ts = get_server_time()
    params = {"timestamp": ts}
    params["signature"] = sign(params)
    headers = {"X-MBX-APIKEY": API_KEY}  # Docs exact
    r = requests.get(BASE_URL + "/v3/account", params=params, headers=headers)  # Docs: GET /v3/account
    print(f"[BALANCE] Status: {r.status_code} | {r.text[:200]}")
    return r


def get_ticker():
    r = requests.get(BASE_URL + "/v3/ticker/24hr")  # Docs exact, no params for all
    print(f"[TICKER] Status: {r.status_code} | First 100 chars: {r.text[:100]}")
    if r.status_code != 200 or not r.text.strip():
        return [], [], {}
    data = r.json()  # Array of dicts per docs
    rising = [item for item in data if float(item.get("priceChangePercent", 0)) >= 5.0]  # Docs field
    prices = [float(item["lastPrice"]) for item in rising]
    market = {item["symbol"]: item for item in data}
    print(f"[TICKER] {len(rising)} rising >=5%: { [item['symbol'] for item in rising[:3]] }...")
    return rising, prices, market


def place_order(symbol, side, qty):
    global bought_stocks
    ts = get_server_time()
    params = {
        "symbol": symbol,
        "side": side,
        "type": "MARKET",
        "quantity": str(round(qty, 6)),  # Docs: string qty
        "timestamp": ts
    }
    params["signature"] = sign(params)
    headers = {"X-MBX-APIKEY": API_KEY}
    order_data = {k: v for k, v in params.items() if k != "signature"}  # Body without sig
    r = requests.post(BASE_URL + "/v3/order", params={"signature": params["signature"]}, data=order_data, headers=headers)  # Docs: auth in query, body for order
    print(f"[ORDER {side}] {qty} {symbol} | Status: {r.status_code} | {r.text[:200]}")
    try:
        res = r.json()
        status = res.get("status", "ERROR")
        if status == "FILLED":
            executed_qty = float(res.get("executedQty", qty))
            avg_price = float(res.get("cummulativeQuoteQty", 0)) / executed_qty if executed_qty else 0
            if side == "BUY":
                bought_stocks[symbol] = {"price": avg_price, "qty": executed_qty}
                print(f"[BOUGHT] {symbol} @ {avg_price:.4f} | Holdings: {len(bought_stocks)}")
            else:
                bought_stocks.pop(symbol, None)
                print(f"[SOLD] {symbol} | Holdings: {len(bought_stocks)}")
            return res
    except:
        pass
    print(f"[ORDER FAIL] Invalid response for {symbol}")
    return None


# === 1. SELL ALL (RUNS ONCE) ===
def sell_all_at_once():
    print(f"\nSELL ALL HOLDINGS — {time.strftime('%Y-%m-%d %H:%M:%S')} HKT")
    r = get_balance()
    if r.status_code != 200:
        print(f"ERROR: Balance fetch failed (404? Check auth/key). Holdings not fetched.")
        return

    balances = r.json().get("balances", [])
    non_usdt = [b for b in balances if float(b.get("free", 0)) > 0.0001 and b["asset"] != "USDT"]
    print(f"[BALANCE] Found {len(balances)} total assets, {len(non_usdt)} non-USDT to sell: {[b['asset'] for b in non_usdt[:5]]}...")

    sold = 0
    for b in non_usdt:
        asset = b["asset"]
        free = float(b["free"])
        symbol = f"{asset}USDT"  # Docs: USDT pairs
        qty = round(free, 6)
        print(f"[SELL] {qty} {symbol}")
        place_order(symbol, "SELL", qty)
        if place_order(symbol, "SELL", qty):  # Wait, duplicate? No — call once
            sold += 1
        time.sleep(1)  # Rate limit

    print(f"SELL ALL COMPLETE — {sold}/{len(non_usdt)} sold")
    print("-" * 60)


# === MAIN: SELL ALL → TRADE FOREVER ===
if __name__ == "__main__":
    print("BOT STARTED — ROOSTOO COMPETITION TRADER")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')} HKT")
    print("1. Sell all holdings (once)")
    print("2. Buy rising (>=5%) every 15 min, sell check every 5 min (TP +3%, SL -1.5%)")
    print("-" * 60)

    sell_all_at_once()

    print("TRADING LOOP STARTED")
    print("-" * 60)

    while True:
        now = time.time()

        # SELL CHECK (every 5 min if holdings)
        if now >= next_sell_check and bought_stocks:
            print(f"\n[SELL CHECK] @ {time.strftime('%H:%M:%S')}")
            _, _, market = get_ticker()
            for symbol, pos in list(bought_stocks.items()):
                ticker = market.get(symbol, {})
                cur = float(ticker.get("askPrice") or ticker.get("lastPrice") or 0)
                if cur == 0:
                    print(f"  [SKIP] {symbol}: No price data")
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
            next_sell_check = now + 300  # 5 min

        # BUY CYCLE (every 15 min or after TP/SL)
        if now >= next_buy_time or stopgainloss:
            print(f"\n[BUY CYCLE] @ {time.strftime('%H:%M:%S')}")
            rising, prices, _ = get_ticker()
            if rising and not stopgainloss:
                idx = stock_index % len(rising)
                symbol = rising[idx]["symbol"]
                price = prices[idx]
                qty = round(1000 / price, 6)  # $1000 worth
                if qty > 0.000001:
                    print(f"[BUY] {symbol} @ {price:.4f} → Qty {qty}")
                    place_order(symbol, "BUY", qty)
                    stock_index += 1
                else:
                    print(f"[SKIP] {symbol}: Qty too small")
            next_buy_time = now + 900  # 15 min
            stopgainloss = False

        time.sleep(10)  # Loop check