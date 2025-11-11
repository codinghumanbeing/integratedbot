#!/usr/bin/env python
# -*- coding: utf-8 -*-
# bot_final.py — ROOSTOO MOCK API — FINAL WORKING VERSION
import requests
import hashlib
import hmac
import time
import json

API_KEY = "Uf1MjnJxofjvkQPyrN1YKTEdERgsjGtBznDVh8hqmEG4gqjHvgc1FCI6EqGmKvuy"
SECRET = "5CL4KCVLEYyLLaSq2Jg7VCCu3QsWQYTcv1gQTMngnBG81YJ9VWopJBIwIqsaNjqR"
BASE_URL = "https://mock-api.roostoo.com/api"  # CORRECT

# GLOBALS
bought_stocks = {}
next_sell_check = 0
next_buy_time = 0
stopgainloss = False
stock_index = 0


def get_server_time():
    try:
        r = requests.get(f"{BASE_URL}/v1/time", timeout=5)
        if r.status_code == 200:
            st = r.json()["serverTime"]
            print(f"[TIME] Server: {st}")
            return int(st)
    except:
        pass
    local = int(time.time() * 1000)
    print(f"[TIME] Local fallback: {local}")
    return local


def sign(params):
    query = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
    return hmac.new(SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()


def get_balance():
    ts = get_server_time()
    params = {"timestamp": ts}
    signature = sign(params)
    headers = {"X-MBX-APIKEY": API_KEY}
    url = f"{BASE_URL}/v3/account"
    try:
        r = requests.get(url, params={**params, "signature": signature}, headers=headers, timeout=10)
        print(f"[BALANCE] {r.status_code} | {r.text[:200]}")
        if r.status_code == 200:
            return r
    except:
        pass
    return None


def get_ticker():
    url = f"{BASE_URL}/v3/ticker/price"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200 and r.text.strip():
            data = r.json()
            # Filter for USDT pairs and get 24hr change from /ticker/24hr
            r2 = requests.get(f"{BASE_URL}/v3/ticker/24hr", timeout=10)
            if r2.status_code == 200:
                change_data = {d["symbol"]: d for d in r2.json()}
                rising = []
                prices = []
                market = {}
                for item in data:
                    sym = item["symbol"]
                    if sym.endswith("USDT"):
                        change = float(change_data.get(sym, {}).get("priceChangePercent", 0))
                        if change >= 5.0:
                            rising.append({"symbol": sym})
                            prices.append(float(item["price"]))
                            market[sym] = change_data.get(sym, {})
                print(f"[TICKER] {len(rising)} rising >=5%")
                return rising, prices, market
    except Exception as e:
        print(f"[TICKER ERROR] {e}")
    return [], [], {}


# === SELL ALL ===
def sell_all_at_once():
    print(f"\nSELL ALL — {time.strftime('%Y-%m-%d %H:%M:%S')} HKT")
    r = get_balance()
    if not r or r.status_code != 200:
        print("No balance or API down. Skipping sell.")
        return

    balances = r.json().get("balances", [])
    assets = [b for b in balances if float(b["free"]) > 0.0001 and b["asset"] != "USDT"]
    print(f"Found {len(assets)} assets to sell")

    sold = 0
    for b in assets:
        asset = b["asset"]
        free = float(b["free"])
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
            f"{BASE_URL}/v3/order",
            params={**params, "signature": signature},
            headers=headers,
            timeout=10
        )
        res = r2.json() if r2.text else {}
        status = res.get("status", "ERR")
        print(f"  → {status}")
        if status == "FILLED":
            sold += 1
        time.sleep(1)

    print(f"SELL ALL COMPLETE — {sold} sold")
    print("-" * 60)


# === TRADING ===
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
        f"{BASE_URL}/v3/order",
        params={**params, "signature": signature},
        headers=headers,
        timeout=10
    )
    res = r.json() if r.text else {}
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
    print("BOT STARTED — ROOSTOO MOCK API")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')} HKT")
    print("-" * 60)

    sell_all_at_once()

    print("TRADING LOOP STARTED")
    print("Buy: every 15 min | Sell Check: every 5 min | TP: +3% | SL: -1.5%")
    print("-" * 60)

    while True:
        now = time.time()

        # SELL CHECK
        if now >= next_sell_check and bought_stocks:
            print(f"\n[SELL CHECK] {time.strftime('%H:%M:%S')}")
            _, _, market = get_ticker()
            for symbol, pos in list(bought_stocks.items()):
                data = market.get(symbol, {})
                cur = float(data.get("askPrice") or data.get("lastPrice") or 0)
                if cur == 0: continue
                pnl = (cur - pos["price"]) / pos["price"]
                print(f"  [P/L] {symbol}: {pnl:+.2%}")
                if pnl >= 0.03:
                    place_order(symbol, "SELL", pos["qty"])
                    stopgainloss = True
                elif pnl <= -0.015:
                    place_order(symbol, "SELL", pos["qty"])
                    stopgainloss = True
            next_sell_check = now + 300

        # BUY CYCLE
        if now >= next_buy_time or stopgainloss:
            print(f"\n[BUY CYCLE] {time.strftime('%H:%M:%S')}")
            rising, prices, _ = get_ticker()
            if rising and not stopgainloss:
                idx = stock_index % len(rising)
                d = rising[idx]
                symbol = d["symbol"]
                price = prices[idx]
                qty = max(0.000001, round(1000 / price, 6))
                print(f"[BUY] {symbol} @ {price:.2f} → {qty}")
                place_order(symbol, "BUY", qty)
                stock_index += 1
            next_buy_time = now + 900
            stopgainloss = False

        time.sleep(10)