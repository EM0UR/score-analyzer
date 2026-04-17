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
    """yfinance.Ticker から素早くデータを取得する。
    info が変でも、とりあえず data を返す方針にする。
    """
    try:
        # 軽いレート制御
        time.sleep(0.8)

        data = {
            "info":            yft.info,
            "financials":      yft.financials,
            "balance_sheet":   yft.balance_sheet,
            "cashflow":        yft.cashflow,
            "history":         yft.history(period="10y"),
            "q_financials":    yft.quarterly_financials,
            "q_balance_sheet": yft.quarterly_balance_sheet,
            "q_cashflow":      yft.quarterly_cashflow,
        }

        info = data.get("info") or {}
        # 価格だけは最低限確認するが、取れなかったら None を返すだけでリトライしない
        price = info.get("currentPrice") or info.get("previousClose")
        if price is None:
            logger.warning("価格データなし: %s", yft.ticker)
            return None

        return data

    except Exception as e:
        logger.error("yfinance 取得失敗 (%s): %s", yft.ticker, e)
        return None

def fetch_ticker_data(ticker, force_refresh=False):
    ticker = ticker.upper()
    path   = _cache_path(ticker)

    # キャッシュ有効なら即返す
    if not force_refresh and _is_valid(path):
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception:
            # キャッシュが壊れていたら削除して再取得
            try:
                os.remove(path)
            except OSError:
                pass

    print(f"[{ticker}] 取得中...", end="", flush=True)
    data = _safe_fetch(yf.Ticker(ticker))

    if 
        with open(path, "wb") as f:
            pickle.dump(data, f)
        print(" ✓")
    else:
        print(" ✗")  # ここで None を返す
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
