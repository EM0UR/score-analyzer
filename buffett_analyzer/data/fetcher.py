# data/fetcher.py — yfinance データ取得 + キャッシュ + レートリミット対策
import os
import time
import pickle
import logging
from datetime import datetime, timedelta

import yfinance as yf

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.expanduser("~/.buffett_cache")
os.makedirs(CACHE_DIR, exist_ok=True)
CACHE_TTL_HOURS = 24
REQUEST_DELAY = 1.2       # リクエスト間の待機秒数
MAX_RETRIES = 4           # 最大リトライ回数
BACKOFF_FACTOR = 3.0      # 指数バックオフ倍率

def _cache_path(ticker: str) -> str:
    return os.path.join(CACHE_DIR, f"{ticker.upper()}.pkl")

def _is_cache_valid(path: str) -> bool:
    if not os.path.exists(path):
        return False
    mtime = datetime.fromtimestamp(os.path.getmtime(path))
    return datetime.now() - mtime < timedelta(hours=CACHE_TTL_HOURS)

def _safe_fetch(yf_ticker, retry: int = 0):
    """
    yfinance 全財務データを一括取得。
    429 / ConnectionError 発生時は指数バックオフでリトライ。
    """
    try:
        time.sleep(REQUEST_DELAY)
        data = {
            "info":          yf_ticker.info,
            "financials":    yf_ticker.financials,
            "balance_sheet": yf_ticker.balance_sheet,
            "cashflow":      yf_ticker.cashflow,
            "quarterly_financials": yf_ticker.quarterly_financials,
            "history":       yf_ticker.history(period="10y"),
        }
        # info が空なら実質的な取得失敗
        if not data["info"] or data["info"].get("regularMarketPrice") is None:
            # currentPrice / previousClose などがあれば問題なし
            if (data["info"].get("currentPrice") is None and
                    data["info"].get("previousClose") is None):
                raise ValueError("info が空または価格データなし")
        return data

    except Exception as e:
        err_str = str(e).lower()
        is_ratelimit = "429" in err_str or "too many" in err_str or "rate" in err_str
        if retry < MAX_RETRIES:
            wait = REQUEST_DELAY * (BACKOFF_FACTOR ** (retry + 1))
            logger.warning(f"取得エラー（{e}）: {wait:.0f}秒後にリトライ [{retry+1}/{MAX_RETRIES}]")
            time.sleep(wait)
            return _safe_fetch(yf_ticker, retry + 1)
        logger.error(f"データ取得が{MAX_RETRIES}回失敗しました: {e}")
        return None


def fetch_ticker_data(ticker: str, force_refresh: bool = False):
    """
    銘柄のデータを取得する。
    - キャッシュが有効 かつ force_refresh=False なら API を叩かない。
    - 戻り値は dict or None（取得失敗）
    """
    ticker = ticker.upper()
    path = _cache_path(ticker)

    if not force_refresh and _is_cache_valid(path):
        with open(path, "rb") as f:
            cached = pickle.load(f)
        logger.debug(f"[{ticker}] キャッシュから読み込み")
        return cached

    print(f"[{ticker}] Yahoo Finance からデータ取得中...", end="", flush=True)
    yf_ticker = yf.Ticker(ticker)
    data = _safe_fetch(yf_ticker)

    if data is not None:
        with open(path, "wb") as f:
            pickle.dump(data, f)
        print(" 完了")
    else:
        print(" 失敗")

    return data


def clear_cache(ticker: str = None):
    """キャッシュ削除（ticker 指定で個別、None で全消去）"""
    if ticker:
        path = _cache_path(ticker)
        if os.path.exists(path):
            os.remove(path)
            print(f"[{ticker}] キャッシュを削除しました")
    else:
        for f in os.listdir(CACHE_DIR):
            os.remove(os.path.join(CACHE_DIR, f))
        print("全キャッシュを削除しました")
