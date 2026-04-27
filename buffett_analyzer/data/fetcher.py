import os
from pathlib import Path
from typing import Any, Dict, Optional
import time

def fetch_with_retry(symbol, max_retries=3, wait=5):
    for attempt in range(max_retries):
        try:
            session = requests.Session()
            session.headers.update({"User-Agent": "Mozilla/5.0 ..."})
            ticker = yf.Ticker(symbol, session=session)
            info = ticker.info
            if info and len(info) > 5:  # 空じゃないか確認
                return ticker
        except Exception as e:
            if "Too Many Requests" in str(e) or "Rate" in str(e):
                time.sleep(wait * (attempt + 1))
            else:
                raise
    return None

import pandas as pd

# ------------------------------------------------------------
# Harden yfinance for Streamlit / cloud deployment
# - Writable timezone cache location
# - Newer User-Agent to reduce Yahoo blocks
# - Retry logic with multiple fallbacks
# ------------------------------------------------------------

_CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "py-yfinance"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("YFINANCE_CACHE_DIR", str(_CACHE_DIR))

import yfinance as yf
import requests

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36"
})

ticker = yf.Ticker(symbol, session=session)


try:
    yf.set_tz_cache_location(str(_CACHE_DIR))
except Exception:
    pass

try:
    from yfinance import data as yf_data
    ua = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/133.0.0.0 Safari/537.36"
        )
    }
    if hasattr(yf_data, "YfData"):
        try:
            yf_data.YfData.user_agent_headers = ua
        except Exception:
            pass
except Exception:
    pass


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame()


def _safe_df(value: Any) -> pd.DataFrame:
    return value if isinstance(value, pd.DataFrame) else _empty_df()


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _to_plain_dict(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    try:
        return dict(obj)
    except Exception:
        return {}


def _fast_info_to_dict(tkr: Any) -> Dict[str, Any]:
    try:
        fi = getattr(tkr, "fast_info", None)
        if fi is None:
            return {}
        try:
            return dict(fi)
        except Exception:
            keys = [
                "currency", "quoteType", "timezone", "lastPrice", "previousClose",
                "open", "dayHigh", "dayLow", "marketCap", "shares", "tenDayAverageVolume",
            ]
            out = {}
            for k in keys:
                try:
                    v = fi.get(k)
                    if v is not None:
                        out[k] = v
                except Exception:
                    pass
            return out
    except Exception:
        return {}


def _merge_info(primary: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(fallback or {})
    out.update({k: v for k, v in (primary or {}).items() if v is not None})

    if out.get("currentPrice") is None and out.get("lastPrice") is not None:
        out["currentPrice"] = out.get("lastPrice")
    if out.get("previousClose") is None and fallback.get("previousClose") is not None:
        out["previousClose"] = fallback.get("previousClose")
    if out.get("marketCap") is None and fallback.get("marketCap") is not None:
        out["marketCap"] = fallback.get("marketCap")
    if out.get("sharesOutstanding") is None and fallback.get("shares") is not None:
        out["sharesOutstanding"] = fallback.get("shares")
    if out.get("currency") is None and fallback.get("currency") is not None:
        out["currency"] = fallback.get("currency")

    return out


def _has_core_signal(info: Dict[str, Any], history: pd.DataFrame) -> bool:
    if isinstance(history, pd.DataFrame) and not history.empty:
        return True
    for key in ["currentPrice", "previousClose", "marketCap", "longName", "shortName", "currency"]:
        if info.get(key) is not None:
            return True
    return False


def _fetch_history(tkr: Any) -> pd.DataFrame:
    attempts = [
        {"period": "1mo", "interval": "1d", "auto_adjust": False, "actions": False},
        {"period": "6mo", "interval": "1d", "auto_adjust": False, "actions": False},
        {"period": "5d", "interval": "1d", "auto_adjust": False, "actions": False},
    ]
    last_err = None
    for kwargs in attempts:
        try:
            hist = tkr.history(**kwargs)
            if isinstance(hist, pd.DataFrame) and not hist.empty:
                return hist
        except Exception as e:
            last_err = e
    if last_err:
        raise last_err
    return _empty_df()


def _download_history(symbol: str) -> pd.DataFrame:
    attempts = [
        {"period": "1mo", "interval": "1d", "progress": False, "auto_adjust": False, "threads": False},
        {"period": "6mo", "interval": "1d", "progress": False, "auto_adjust": False, "threads": False},
    ]
    last_err = None
    for kwargs in attempts:
        try:
            df = yf.download(symbol, **kwargs)
            if isinstance(df, pd.DataFrame) and not df.empty:
                return df
        except Exception as e:
            last_err = e
    if last_err:
        raise last_err
    return _empty_df()


def _fetch_info(tkr: Any) -> Dict[str, Any]:
    errs = []
    info = {}

    for attr in ["info", "get_info"]:
        try:
            if attr == "info":
                raw = getattr(tkr, "info", None)
            else:
                raw = getattr(tkr, attr)()
            cand = _to_plain_dict(raw)
            if cand:
                info = cand
                break
        except Exception as e:
            errs.append(f"{attr}: {type(e).__name__}: {e}")

    fast = _fast_info_to_dict(tkr)
    merged = _merge_info(info, fast)
    if errs:
        merged.setdefault("_info_errors", errs)
    return merged


def _fetch_stmt(getter_name: str, tkr: Any) -> pd.DataFrame:
    try:
        getter = getattr(tkr, getter_name, None)
        if getter is None:
            return _empty_df()
        value = getter if isinstance(getter, pd.DataFrame) else getter
        return _safe_df(value)
    except Exception:
        return _empty_df()


def fetch_ticker_data(symbol: str, retries: int = 3, pause: float = 1.2) -> Optional[Dict[str, Any]]:
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return None

    last_errors = []

    for attempt in range(1, retries + 1):
        try:
            tkr = yf.Ticker(symbol)

            info = _fetch_info(tkr)

            try:
                history = _fetch_history(tkr)
            except Exception as e_hist:
                last_errors.append(f"history: {type(e_hist).__name__}: {e_hist}")
                try:
                    history = _download_history(symbol)
                except Exception as e_dl:
                    last_errors.append(f"download: {type(e_dl).__name__}: {e_dl}")
                    history = _empty_df()

            financials = _safe_df(getattr(tkr, "financials", _empty_df()))
            balance_sheet = _safe_df(getattr(tkr, "balance_sheet", _empty_df()))
            cashflow = _safe_df(getattr(tkr, "cashflow", _empty_df()))
            q_financials = _safe_df(getattr(tkr, "quarterly_financials", _empty_df()))
            q_balance_sheet = _safe_df(getattr(tkr, "quarterly_balance_sheet", _empty_df()))
            q_cashflow = _safe_df(getattr(tkr, "quarterly_cashflow", _empty_df()))

            if not _has_core_signal(info, history):
                raise RuntimeError("No core price/info data returned from Yahoo")

            payload = {
                "symbol": symbol,
                "info": _safe_dict(info),
                "history": _safe_df(history),
                "financials": financials,
                "balance_sheet": balance_sheet,
                "cashflow": cashflow,
                "q_financials": q_financials,
                "q_balance_sheet": q_balance_sheet,
                "q_cashflow": q_cashflow,
                "_fetch_meta": {
                    "attempt": attempt,
                    "cache_dir": str(_CACHE_DIR),
                    "history_rows": int(len(history)) if isinstance(history, pd.DataFrame) else 0,
                    "info_keys": len(info) if isinstance(info, dict) else 0,
                    "warnings": last_errors[-10:],
                },
            }
            return payload

        except Exception as e:
            last_errors.append(f"attempt {attempt}: {type(e).__name__}: {e}")
            if attempt < retries:
                time.sleep(pause * attempt)

    return {
        "symbol": symbol,
        "info": {},
        "history": _empty_df(),
        "financials": _empty_df(),
        "balance_sheet": _empty_df(),
        "cashflow": _empty_df(),
        "q_financials": _empty_df(),
        "q_balance_sheet": _empty_df(),
        "q_cashflow": _empty_df(),
        "_fetch_error": " | ".join(last_errors[-12:]) if last_errors else "unknown fetch error",
        "_fetch_meta": {
            "cache_dir": str(_CACHE_DIR),
            "warnings": last_errors[-12:],
        },
    }
