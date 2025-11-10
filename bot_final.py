#!/usr/bin/env python
# -*- coding: utf-8 -*-
# FINAL BOT: 15-min buy | 5-min sell check | +3% TP | -1.5% SL
import requests
import hashlib
import hmac
import time

API_KEY = "Uf1MjnJxofjvkQPyrN1YKTEdERgsjGtBznDVh8hqmEG4gqjHvgc1FCI6EqGmKvuy"
SECRET = "5CL4KCVLEYyLLaSq2Jg7VCCu3QsWQYTcv1gQTMngnBG81YJ9VWopJBIwIqsaNjqR"
BASE_URL = "https://mock-api.roostoo.com"

# GLOBALS
bought_stocks = {}        # {pair: {"price": X, "qty": Y}}
next_sell_check = 0       # Every 5 minutes
next_buy_time = 0         # Every 15 minutes
stopgainloss = False
stock_index = 0


def sign(params):
    query = '&'.join([f"{k}={params[k]}" for k in sorted(params)])
    return hmac.new(SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()


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


# MAIN LOOP
if __name__ == "__main__":
    print("FINAL BOT STARTED - LIVE TRADING")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')} HKT | HK")
    print("Buy: every 15 min | Sell Check: every 5 min | TP: +3% | SL: -1.5%")

    while True:
        now = time.time()
        market = {}

        # SELL CHECK: Every 5 minutes
        if now >= next_sell_check and bought_stocks:
            print(f"\n[SELL CHECK] @ {time.strftime('%H:%M:%S')}")
            _, _, market = get_ticker()
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

            next_sell_check = now + 300  # 5 minutes

        # BUY CYCLE: Every 15 minutes OR after sell
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
            next_buy_time = now + 900  # 15 minutes
            stopgainloss = False

        time.sleep(10)