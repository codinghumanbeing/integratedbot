#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ROOSTOO MOCK BOT — FINAL, MINIMAL, WORKING
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
MAX_POSITIONS = 3


def sign(params):
    query = '&'.join([f"{k}={params[k]}" for k in sorted(params)])
    return hmac.new(SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()


def get_balance():
    ts = int(time.time() * 1000)
    payload = {"timestamp": ts}
    headers = {"RST-API-KEY": API_KEY, "MSG-SIGNATURE": sign(payload)}
    r = requests.get(BASE_URL + "/v3/balance", params=payload, headers=headers)
    print(f"[BALANCE] {r.status_code} | {r.text[:200]}")
    return r


def get_ticker():
    r = requests.get(BASE_URL + "/v3/ticker", params={"timestamp": int(time.time())})
    data = r.json().get("Data", {})
    rising = [p for p, d in data.items() if float(d.get("Change", 0)) >= 0.05]
    prices = [float(data[p]["LastPrice"]) for p in rising]
    print(f"[TICKER] {len(rising)} up $0.05+: {rising[:3]}...")
    return rising, prices, data


def place_order(pair, side, qty):
    global bought_stocks
    qty = round(qty, 1)  # YOUR GOLDEN RULE
    payload = {
        "timestamp": int(time.time() * 1000),
        "pair": pair,
        "side": side,
        "quantity": qty,
        "type": "MARKET"
    }
    headers = {"RST-API-KEY": API_KEY, "MSG-SIGNATURE": sign(payload)}
    r = requests.post(BASE_URL + "/v3/place_order", data=payload, headers=headers)
    print(f"[ORDER {side}] {qty} {pair} → {r.status_code}")
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
        return True
    return False


# === SELL ALL ONCE ===
def sell_all_at_once():
    print(f"\nSELL ALL — {time.strftime('%Y-%m-%d %H:%M:%S')} HKT")
    r = get_balance()
    if r.status_code != 200:
        print("Balance failed.")
        return
    wallet = r.json().get("SpotWallet", {})
    to_sell = [(asset, float(info["Free"])) for asset, info in wallet.items() if float(info["Free"]) > 0.1 and asset != "USD"]
    print(f"Found {len(to_sell)} assets to sell")
    for asset, free in to_sell:
        pair = f"{asset}/USD"
        qty = round(free, 1)
        print(f"[SELL] {qty} {pair}")
        place_order(pair, "SELL", qty)
        time.sleep(1)
    print("SELL ALL COMPLETE")
    print("-" * 60)


# === MAIN ===
if __name__ == "__main__":
    print("ROOSTOO MOCK BOT — LIVE")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')} HKT")
    print("Strategy: Buy +$0.05 | TP +3% | SL -1.5% | Max 3 positions")
    print("-" * 60)

    sell_all_at_once()

    while True:
        now = time.time()

        # SELL CHECK
        if now >= next_sell_check and bought_stocks:
            print(f"\n[SELL CHECK] {time.strftime('%H:%M:%S')}")
            _, _, market = get_ticker()
            for pair, pos in list(bought_stocks.items()):
                cur = float(market[pair].get("AskPrice") or market[pair]["LastPrice"])
                pnl = (cur - pos["price"]) / pos["price"]
                print(f"  [P/L] {pair}: {pnl:+.2%}")
                if pnl >= 0.03:
                    place_order(pair, "SELL", pos["qty"])
                    stopgainloss = True
                elif pnl <= -0.015:
                    place_order(pair, "SELL", pos["qty"])
                    stopgainloss = True
            next_sell_check = now + 300

        # BUY CYCLE
        if (now >= next_buy_time or stopgainloss) and len(bought_stocks) < MAX_POSITIONS:
            print(f"\n[BUY CYCLE] {time.strftime('%H:%M:%S')}")
            rising, prices, _ = get_ticker()
            if rising and not stopgainloss:
                idx = stock_index % len(rising)
                pair = rising[idx]
                price = prices[idx]
                qty = round(1000 / price, 1)
                print(f"[BUY] {pair} @ {price:.6f} → {qty}")
                place_order(pair, "BUY", qty)
                stock_index += 1
            next_buy_time = now + 900
            stopgainloss = False
        elif len(bought_stocks) >= MAX_POSITIONS:
            print(f"[MAX POSITIONS] {len(bought_stocks)}/3 — waiting...")

        time.sleep(10)