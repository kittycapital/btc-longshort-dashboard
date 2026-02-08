"""
롱숏 비율 대시보드 데이터 수집기
- CoinGecko: 마켓캡 TOP 50 → 스테이블코인 제외
- Bybit: /v5/market/account-ratio (서버 사이드)
- Binance: 클라이언트 사이드에서 직접 호출 (index.html)
"""

import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
HISTORY_DIR = os.path.join(DATA_DIR, "history")
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
            print(f"  [!] Attempt {attempt+1}/{retries} failed for {url[:80]}...: {e}")
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
    return None


def get_top_coins():
    """CoinGecko 마켓캡 TOP 50"""
    print("[1/4] CoinGecko 마켓캡 TOP 코인 가져오기...")
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

    print(f"  → {len(coins)}개 코인 (스테이블/래핑 제외)")
    return coins


def get_bybit_symbols():
    """Bybit USDT 무기한 선물 심볼 목록"""
    print("[2/4] Bybit 선물 심볼 확인...")
    url = "https://api.bybit.com/v5/market/instruments-info?category=linear&limit=1000"
    data = api_get(url)
    if not data or data.get("retCode") != 0:
        return set()
    symbols = set()
    for s in data.get("result", {}).get("list", []):
        if s.get("quoteCoin") == "USDT" and s.get("status") == "Trading" and s.get("contractType") == "LinearPerpetual":
            symbols.add(s.get("baseCoin", "").upper())
    print(f"  → {len(symbols)}개 Bybit 선물 심볼")
    return symbols


def get_bybit_longshort(symbol, period="1h", limit=1):
    """Bybit 롱숏 비율"""
    pair = f"{symbol}USDT"
    url = f"https://api.bybit.com/v5/market/account-ratio?category=linear&symbol={pair}&period={period}&limit={limit}"
    data = api_get(url, retries=2, delay=1)
    if data and data.get("retCode") == 0:
        lst = data.get("result", {}).get("list", [])
        if lst:
            buy = float(lst[0].get("buyRatio", 0))
            sell = float(lst[0].get("sellRatio", 0))
            return {"long": buy, "short": sell, "ratio": round(buy / max(sell, 0.001), 4)}
    return None


def get_bybit_history(symbol, period="4h", limit=200):
    """Bybit 롱숏 히스토리"""
    pair = f"{symbol}USDT"
    url = f"https://api.bybit.com/v5/market/account-ratio?category=linear&symbol={pair}&period={period}&limit={limit}"
    data = api_get(url, retries=2, delay=1)
    if not data or data.get("retCode") != 0:
        return []

    history = []
    for d in data.get("result", {}).get("list", []):
        ts = int(d.get("timestamp", 0))
        dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        buy = float(d.get("buyRatio", 0))
        sell = float(d.get("sellRatio", 0))
        history.append({
            "timestamp": dt.strftime("%Y-%m-%d %H:%M"),
            "long": buy, "short": sell,
            "ratio": round(buy / max(sell, 0.001), 4),
        })
    history.reverse()
    return history


def collect_all_data(coins):
    """모든 코인의 Bybit 롱숏 수집"""
    print("[3/4] Bybit 롱숏 비율 수집 중...")
    for i, coin in enumerate(coins):
        symbol = coin["symbol"]
        print(f"  ({i+1}/{len(coins)}) {symbol}...")
        coin["bybit"] = get_bybit_longshort(symbol)
        time.sleep(0.15)

    print("[4/4] 상위 15개 코인 히스토리 수집 중...")
    histories = {}
    for coin in coins[:15]:
        symbol = coin["symbol"]
        print(f"  히스토리: {symbol}...")
        hist = get_bybit_history(symbol, period="4h", limit=200)
        if hist:
            histories[symbol] = hist
        time.sleep(0.3)

    return coins, histories


def compute_signals(coins):
    """극단 시그널 계산 (Bybit 기준)"""
    for coin in coins:
        bybit = coin.get("bybit")
        if not bybit:
            coin["signal"] = "neutral"
            coin["signal_strength"] = 0
            continue

        long_pct = bybit.get("long", 0.5)
        if long_pct >= 0.70:
            coin["signal"] = "extreme_long"
            coin["signal_strength"] = round((long_pct - 0.5) * 200)
        elif long_pct >= 0.60:
            coin["signal"] = "long"
            coin["signal_strength"] = round((long_pct - 0.5) * 200)
        elif long_pct <= 0.30:
            coin["signal"] = "extreme_short"
            coin["signal_strength"] = round((0.5 - long_pct) * 200)
        elif long_pct <= 0.40:
            coin["signal"] = "short"
            coin["signal_strength"] = round((0.5 - long_pct) * 200)
        else:
            coin["signal"] = "neutral"
            coin["signal_strength"] = 0

    return coins


def save_daily_snapshot(coins):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snapshot_file = os.path.join(HISTORY_DIR, f"{today}.json")
    snapshot = {}
    for coin in coins:
        bybit = coin.get("bybit")
        snapshot[coin["symbol"]] = {
            "price": coin.get("price", 0),
            "bybit_long": bybit.get("long", 0) if bybit else 0,
            "bybit_short": bybit.get("short", 0) if bybit else 0,
        }
    with open(snapshot_file, "w") as f:
        json.dump(snapshot, f, indent=2)
    print(f"  → 일별 스냅샷 저장: {snapshot_file}")


def load_history_data():
    history = {}
    if not os.path.exists(HISTORY_DIR):
        return history
    files = sorted([f for f in os.listdir(HISTORY_DIR) if f.endswith(".json")])
    for fname in files:
        date = fname.replace(".json", "")
        try:
            with open(os.path.join(HISTORY_DIR, fname)) as f:
                history[date] = json.load(f)
        except:
            pass
    print(f"  → 히스토리: {len(history)}일치 데이터 로드")
    return history


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(HISTORY_DIR, exist_ok=True)

    print("=" * 50)
    print("롱숏 비율 대시보드 데이터 수집 (Bybit)")
    print("=" * 50)

    coins = get_top_coins()
    if not coins:
        print("[!] 코인 리스트 가져오기 실패")
        return
    time.sleep(1)

    bybit_symbols = get_bybit_symbols()
    if bybit_symbols:
        coins = [c for c in coins if c["symbol"] in bybit_symbols]
        print(f"  → {len(coins)}개 코인 (Bybit 선물 있는 것만)")
    time.sleep(1)

    coins, histories = collect_all_data(coins)
    coins = compute_signals(coins)
    save_daily_snapshot(coins)
    daily_history = load_history_data()

    output = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "coins": coins,
        "histories": histories,
        "daily_history": daily_history,
    }

    with open(COINS_FILE, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ 완료! {len(coins)}개 코인 데이터 저장됨")

    extreme_long = [c for c in coins if c.get("signal") == "extreme_long"]
    extreme_short = [c for c in coins if c.get("signal") == "extreme_short"]
    if extreme_long:
        print(f"\n🟢 극단 롱 과밀: {', '.join(c['symbol'] for c in extreme_long)}")
    if extreme_short:
        print(f"\n🔴 극단 숏 과밀: {', '.join(c['symbol'] for c in extreme_short)}")


if __name__ == "__main__":
    main()
