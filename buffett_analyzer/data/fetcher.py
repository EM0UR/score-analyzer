import os
import time
import pickle
import logging
from datetime import datetime, timedelta

import yfinance as yf

logger = logging.getLogger(__name__)

# キャッシュ設定
CACHE_DIR = os.path.expanduser("~/.buffett_cache")
CACHE_TTL_HOURS = 24
os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_path(ticker: str) -> str:
    return os.path.join(CACHE_DIR, f"{ticker.upper()}.pkl")


def _is_valid(path: str) -> bool:
    if not os.path.exists(path):
        return False
    age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(path))
    return age < timedelta(hours=CACHE_TTL_HOURS)


def _safe_fetch(yft: yf.Ticker):
    """
    yfinance から 1 回だけデータ取得。
    価格が取れない場合は None を返して呼び元でスキップさせる。
    """
    try:
        # 軽いレート制御
        time.sleep(0.8)

        data = {
            # 年次（長期トレンド用）
            "info":            yft.info,
            "financials":      yft.financials,
            "balance_sheet":   yft.balance_sheet,
            "cashflow":        yft.cashflow,
            "history":         yft.history(period="10y"),

            # 四半期（最新業績反映用）
            "q_financials":    yft.quarterly_financials,
            "q_balance_sheet": yft.quarterly_balance_sheet,
            "q_cashflow":      yft.quarterly_cashflow,
        }

        info = data.get("info") or {}
        price = info.get("currentPrice") or info.get("previousClose")
        if price is None:
            logger.warning("価格データなし: %s", yft.ticker)
            return None

        return data

    except Exception as e:
        logger.error("yfinance 取得失敗 (%s): %s", getattr(yft, "ticker", "?"), e)
        return None


def fetch_ticker_data(ticker: str, force_refresh: bool = False):
    """
    ティッカーの全データ(dict)を取得して返す。
    取得できなければ None。
    """
    ticker = ticker.upper()
    path = _cache_path(ticker)

    # キャッシュ読み込み
    if not force_refresh and _is_valid(path):
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception:
            # 壊れていたら削除して取り直し
            try:
                os.remove(path)
            except OSError:
                pass

    print(f"[{ticker}] 取得中...", end="", flush=True)
    data = _safe_fetch(yf.Ticker(ticker))

    if data is not None:
        try:
            with open(path, "wb") as f:
                pickle.dump(data, f)
        except Exception:
            # キャッシュ保存失敗は無視
            pass
        print(" ✓")
    else:
        print(" ✗")

    return data


def clear_cache(ticker: str | None = None):
    if ticker:
        path = _cache_path(ticker)
        if os.path.exists(path):
            os.remove(path)
            print(f"[{ticker}] キャッシュ削除")
    else:
        for fname in os.listdir(CACHE_DIR):
            os.remove(os.path.join(CACHE_DIR, fname))
        print("全キャッシュ削除")
