"""
롱숏 비율 대시보드 데이터 수집기
- CoinGecko: 마켓캡 TOP 50 → 스테이블코인 제외 → Binance 선물 존재 확인
- Binance: topLongShortAccountRatio, topLongShortPositionRatio, globalLongShortAccountRatio
- Bybit: /v5/market/account-ratio
- 가격: CoinGecko
"""

import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
HISTORY_DIR = os.path.join(DATA_DIR, "history")
COINS_FILE = os.path.join(DATA_DIR, "coins.json")

STABLECOINS = {"USDT", "USDC", "BUSD", "DAI", "TUSD", "USDP", "FDUSD", "USDD", "PYUSD", "USDE", "SUSDE", "SDAI", "FRAX", "LUSD", "CRVUSD", "GHO", "ALUSD", "USDS", "USD0", "EURC", "RLUSD"}
WRAPPED = {"WBTC", "WETH", "STETH", "WSTETH", "CBBTC", "CBETH", "RETH", "LIDO", "BETH"}
EXCLUDE = STABLECOINS | WRAPPED | {"LEO", "SHIB2", "CRO", "OKB", "GT", "KCS", "HT", "FTT", "MX"}

def api_get(url, retries=3, delay=2):
    """Simple GET request with retries"""
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
    """CoinGecko 마켓캡 TOP 50 가져오기 (스테이블/래핑 제외)"""
    print("[1/5] CoinGecko 마켓캡 TOP 코인 가져오기...")
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


def get_binance_futures_symbols():
    """Binance USDT 무기한 선물 심볼 목록"""
    print("[2/5] Binance 선물 심볼 확인...")
    url = "https://fapi.binance.me/fapi/v1/exchangeInfo"
    data = api_get(url)
    if not data:
        return set()
    symbols = set()
    for s in data.get("symbols", []):
        if s.get("contractType") == "PERPETUAL" and s.get("quoteAsset") == "USDT" and s.get("status") == "TRADING":
            base = s.get("baseAsset", "").upper()
            symbols.add(base)
    print(f"  → {len(symbols)}개 Binance 선물 심볼")
    return symbols


def filter_coins_with_futures(coins, binance_symbols):
    """Binance 선물이 있는 코인만 필터"""
    filtered = [c for c in coins if c["symbol"] in binance_symbols]
    print(f"  → {len(filtered)}개 코인 (Binance 선물 있는 것만)")
    return filtered


def get_binance_longshort(symbol, period="1h", limit=1):
    """Binance 롱숏 비율 가져오기 (3종류)"""
    pair = f"{symbol}USDT"
    result = {}

    # 1. Top Trader Account Ratio
    url = f"https://fapi.binance.me/futures/data/topLongShortAccountRatio?symbol={pair}&period={period}&limit={limit}"
    data = api_get(url, retries=2, delay=1)
    if data and len(data) > 0:
        result["top_account"] = {
            "long": float(data[-1].get("longAccount", 0)),
            "short": float(data[-1].get("shortAccount", 0)),
            "ratio": float(data[-1].get("longShortRatio", 0)),
        }

    # 2. Top Trader Position Ratio
    url = f"https://fapi.binance.me/futures/data/topLongShortPositionRatio?symbol={pair}&period={period}&limit={limit}"
    data = api_get(url, retries=2, delay=1)
    if data and len(data) > 0:
        result["top_position"] = {
            "long": float(data[-1].get("longAccount", 0)),
            "short": float(data[-1].get("shortAccount", 0)),
            "ratio": float(data[-1].get("longShortRatio", 0)),
        }

    # 3. Global Account Ratio
    url = f"https://fapi.binance.me/futures/data/globalLongShortAccountRatio?symbol={pair}&period={period}&limit={limit}"
    data = api_get(url, retries=2, delay=1)
    if data and len(data) > 0:
        result["global_account"] = {
            "long": float(data[-1].get("longAccount", 0)),
            "short": float(data[-1].get("shortAccount", 0)),
            "ratio": float(data[-1].get("longShortRatio", 0)),
        }

    return result


def get_bybit_longshort(symbol, period="1h", limit=1):
    """Bybit 롱숏 비율"""
    pair = f"{symbol}USDT"
    url = f"https://api.bybit.com/v5/market/account-ratio?category=linear&symbol={pair}&period={period}&limit={limit}"
    data = api_get(url, retries=2, delay=1)
    if data and data.get("retCode") == 0:
        lst = data.get("result", {}).get("list", [])
        if lst:
            return {
                "long": float(lst[0].get("buyRatio", 0)),
                "short": float(lst[0].get("sellRatio", 0)),
                "ratio": round(float(lst[0].get("buyRatio", 0)) / max(float(lst[0].get("sellRatio", 0.001)), 0.001), 4),
            }
    return None


def get_binance_history(symbol, period="4h", limit=500):
    """Binance 롱숏 히스토리 (최대 30일)"""
    pair = f"{symbol}USDT"
    url = f"https://fapi.binance.me/futures/data/topLongShortAccountRatio?symbol={pair}&period={period}&limit={limit}"
    data = api_get(url, retries=2, delay=1)
    if not data:
        return []

    history = []
    for d in data:
        ts = int(d.get("timestamp", 0))
        dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        history.append({
            "timestamp": dt.strftime("%Y-%m-%d %H:%M"),
            "long": float(d.get("longAccount", 0)),
            "short": float(d.get("shortAccount", 0)),
            "ratio": float(d.get("longShortRatio", 0)),
        })
    return history


def collect_all_data(coins):
    """모든 코인의 롱숏 데이터 수집"""
    print("[3/5] Binance 롱숏 비율 수집 중...")
    for i, coin in enumerate(coins):
        symbol = coin["symbol"]
        print(f"  ({i+1}/{len(coins)}) {symbol}...")

        # Current ratios
        binance = get_binance_longshort(symbol)
        coin["binance"] = binance
        time.sleep(0.3)  # Rate limit

    print("[4/5] Bybit 롱숏 비율 수집 중...")
    for i, coin in enumerate(coins):
        symbol = coin["symbol"]
        bybit = get_bybit_longshort(symbol)
        coin["bybit"] = bybit
        time.sleep(0.2)

    # Top 10 코인만 히스토리 수집 (API 제한)
    print("[5/5] 상위 10개 코인 히스토리 수집 중...")
    histories = {}
    for coin in coins[:10]:
        symbol = coin["symbol"]
        print(f"  히스토리: {symbol}...")
        hist = get_binance_history(symbol, period="4h", limit=500)
        if hist:
            histories[symbol] = hist
        time.sleep(0.5)

    return coins, histories


def compute_signals(coins):
    """극단 시그널 계산"""
    for coin in coins:
        binance = coin.get("binance", {})
        global_acc = binance.get("global_account", {})
        long_pct = global_acc.get("long", 0.5)

        signal = "neutral"
        signal_strength = 0

        if long_pct >= 0.70:
            signal = "extreme_long"
            signal_strength = round((long_pct - 0.5) * 200)
        elif long_pct >= 0.60:
            signal = "long"
            signal_strength = round((long_pct - 0.5) * 200)
        elif long_pct <= 0.30:
            signal = "extreme_short"
            signal_strength = round((0.5 - long_pct) * 200)
        elif long_pct <= 0.40:
            signal = "short"
            signal_strength = round((0.5 - long_pct) * 200)

        coin["signal"] = signal
        coin["signal_strength"] = signal_strength

    return coins


def save_daily_snapshot(coins):
    """일별 스냅샷 저장 (히스토리 누적용)"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snapshot_file = os.path.join(HISTORY_DIR, f"{today}.json")

    snapshot = {}
    for coin in coins:
        binance = coin.get("binance", {})
        bybit = coin.get("bybit", {})
        global_acc = binance.get("global_account", {})
        top_acc = binance.get("top_account", {})

        snapshot[coin["symbol"]] = {
            "price": coin.get("price", 0),
            "binance_global_long": global_acc.get("long", 0),
            "binance_global_short": global_acc.get("short", 0),
            "binance_top_long": top_acc.get("long", 0),
            "binance_top_short": top_acc.get("short", 0),
            "bybit_long": bybit.get("long", 0) if bybit else 0,
            "bybit_short": bybit.get("short", 0) if bybit else 0,
        }

    with open(snapshot_file, "w") as f:
        json.dump(snapshot, f, indent=2)
    print(f"  → 일별 스냅샷 저장: {snapshot_file}")


def load_history_data():
    """누적된 히스토리 데이터 로드"""
    history = {}
    if not os.path.exists(HISTORY_DIR):
        return history

    files = sorted([f for f in os.listdir(HISTORY_DIR) if f.endswith(".json")])
    for fname in files:
        date = fname.replace(".json", "")
        filepath = os.path.join(HISTORY_DIR, fname)
        try:
            with open(filepath) as f:
                history[date] = json.load(f)
        except:
            pass

    print(f"  → 히스토리: {len(history)}일치 데이터 로드")
    return history


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(HISTORY_DIR, exist_ok=True)

    print("=" * 50)
    print("롱숏 비율 대시보드 데이터 수집")
    print("=" * 50)

    # 1. 코인 리스트
    coins = get_top_coins()
    if not coins:
        print("[!] 코인 리스트 가져오기 실패, 기존 데이터 유지")
        return
    time.sleep(1)

    # 2. Binance 선물 필터
    binance_symbols = get_binance_futures_symbols()
    if binance_symbols:
        coins = filter_coins_with_futures(coins, binance_symbols)
    time.sleep(1)

    # 3. 롱숏 데이터 수집
    coins, histories = collect_all_data(coins)

    # 4. 시그널 계산
    coins = compute_signals(coins)

    # 5. 일별 스냅샷 저장
    save_daily_snapshot(coins)

    # 6. 히스토리 로드
    daily_history = load_history_data()

    # 7. 최종 JSON 저장
    output = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "coins": coins,
        "histories": histories,
        "daily_history": daily_history,
    }

    with open(COINS_FILE, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ 완료! {len(coins)}개 코인 데이터 저장됨")
    print(f"   파일: {COINS_FILE}")

    # 극단 시그널 요약
    extreme_long = [c for c in coins if c.get("signal") == "extreme_long"]
    extreme_short = [c for c in coins if c.get("signal") == "extreme_short"]
    if extreme_long:
        print(f"\n🔴 극단 롱 과밀: {', '.join(c['symbol'] for c in extreme_long)}")
    if extreme_short:
        print(f"\n🟢 극단 숏 과밀: {', '.join(c['symbol'] for c in extreme_short)}")


if __name__ == "__main__":
    main()
