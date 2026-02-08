"""
롱숏 비율 대시보드 - 코인 리스트 수집기
- CoinGecko: 마켓캡 TOP 50 코인 리스트 + 가격
- 롱숏 데이터는 index.html에서 클라이언트 사이드로 수집 (Binance + Bybit)
"""

import json
import os
import time
import urllib.request
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
COINS_FILE = os.path.join(DATA_DIR, "coins.json")

STABLECOINS = {"USDT", "USDC", "BUSD", "DAI", "TUSD", "USDP", "FDUSD", "USDD", "PYUSD", "USDE", "SUSDE", "SDAI", "FRAX", "LUSD", "CRVUSD", "GHO", "ALUSD", "USDS", "USD0", "EURC", "RLUSD"}
WRAPPED = {"WBTC", "WETH", "STETH", "WSTETH", "CBBTC", "CBETH", "RETH", "LIDO", "BETH"}
EXCLUDE = STABLECOINS | WRAPPED | {"LEO", "SHIB2", "CRO", "OKB", "GT", "KCS", "HT", "FTT", "MX"}


def api_get(url, retries=3, delay=2):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            print(f"  [!] Attempt {attempt+1}/{retries} failed: {e}")
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
    return None


def get_top_coins():
    """CoinGecko 마켓캡 TOP 50"""
    print("[1/1] CoinGecko 마켓캡 TOP 코인 가져오기...")
    url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=80&page=1&sparkline=false&price_change_percentage=24h"
    data = api_get(url)
    if not data:
        print("  [!] CoinGecko API 실패")
        return []

    coins = []
    for c in data:
        symbol = c.get("symbol", "").upper()
        if symbol in EXCLUDE:
            continue
        coins.append({
            "id": c["id"],
            "symbol": symbol,
            "name": c.get("name", ""),
            "price": c.get("current_price", 0),
            "price_change_24h": c.get("price_change_percentage_24h", 0),
            "market_cap": c.get("market_cap", 0),
            "market_cap_rank": c.get("market_cap_rank", 0),
            "image": c.get("image", ""),
        })
        if len(coins) >= 50:
            break

    print(f"  → {len(coins)}개 코인")
    return coins


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    print("=" * 50)
    print("코인 리스트 업데이트 (CoinGecko)")
    print("롱숏 데이터는 클라이언트에서 실시간 수집")
    print("=" * 50)

    coins = get_top_coins()
    if not coins:
        print("[!] 실패, 기존 데이터 유지")
        return

    output = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "coins": coins,
    }

    with open(COINS_FILE, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ 완료! {len(coins)}개 코인 저장됨")
    print(f"   파일: {COINS_FILE}")


if __name__ == "__main__":
    main()
