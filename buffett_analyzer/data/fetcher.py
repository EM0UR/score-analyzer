fetcher.py
import os, time, pickle, logging
from datetime import datetime, timedelta
import yfinance as yf

logger = logging.getLogger(__name__)
CACHE_DIR       = os.path.expanduser("~/.buffett_cache")
CACHE_TTL_HOURS = 24
REQUEST_DELAY   = 1.2
MAX_RETRIES     = 4
BACKOFF_FACTOR  = 3.0
os.makedirs(CACHE_DIR, exist_ok=True)

def _cache_path(ticker):
    return os.path.join(CACHE_DIR, f"{ticker.upper()}.pkl")

def _is_valid(path):
    if not os.path.exists(path): return False
    age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(path))
    return age < timedelta(hours=CACHE_TTL_HOURS)

def _safe_fetch(yft, retry=0):
    try:
        time.sleep(REQUEST_DELAY)
        data = {
            # ── 年次（最大10年分・長期トレンド分析用）──────────────
            "info":          yft.info,
            "financials":    yft.financials,           # 年次 損益計算書
            "balance_sheet": yft.balance_sheet,        # 年次 貸借対照表
            "cashflow":      yft.cashflow,              # 年次 キャッシュフロー
            "history":       yft.history(period="10y"),

            # ── 四半期（直近4Q・最新業績反映用）──────────────────
            "q_financials":    yft.quarterly_financials,
            "q_balance_sheet": yft.quarterly_balance_sheet,
            "q_cashflow":      yft.quarterly_cashflow,
        }
        info = data["info"]
        if not info or (info.get("currentPrice") is None and info.get("previousClose") is None):
            raise ValueError("価格データなし")
        return data

    except Exception as e:
        if retry < MAX_RETRIES:
            wait = REQUEST_DELAY * (BACKOFF_FACTOR ** (retry + 1))
            logger.warning(f"リトライ {retry+1}/{MAX_RETRIES} ({e}), {wait:.1f}秒後...")
            time.sleep(wait)
            return _safe_fetch(yft, retry + 1)
        logger.error(f"データ取得失敗: {e}")
        return None

def fetch_ticker_data(ticker, force_refresh=False):
    ticker = ticker.upper()
    path   = _cache_path(ticker)

    if not force_refresh and _is_valid(path):
        with open(path, "rb") as f:
            return pickle.load(f)

    print(f"[{ticker}] 取得中...", end="", flush=True)
    data = _safe_fetch(yf.Ticker(ticker))

    if data:
        with open(path, "wb") as f:
            pickle.dump(data, f)
        print(" ✓")
    else:
        print(" ✗")
    return data

def clear_cache(ticker=None):
    if ticker:
        path = _cache_path(ticker)
        if os.path.exists(path):
            os.remove(path)
            print(f"[{ticker}] キャッシュ削除")
    else:
        for fname in os.listdir(CACHE_DIR):
            os.remove(os.path.join(CACHE_DIR, fname))
        print("全キャッシュ削除")
