# metrics/financial_health.py — 財務健全性（D/E比・インタレストカバレッジ）
import numpy as np
import pandas as pd
from typing import Dict


def _safe_row(df: pd.DataFrame, *keys):
    for k in keys:
        if k in df.index:
            return df.loc[k]
    return None


def analyze_financial_health(
    financials: pd.DataFrame,
    balance_sheet: pd.DataFrame,
    cashflow: pd.DataFrame,
    info: dict,
    market_config,
) -> Dict:
    """満点: 15 点"""
    result = {
        "score": 0,
        "max_score": 15,
        "de_ratio": None,
        "equity_ratio": None,
        "interest_coverage": None,
        "current_ratio": None,
        "detail": "",
    }

    try:
        total_debt     = _safe_row(balance_sheet, "Total Debt", "Long Term Debt")
        total_equity   = _safe_row(balance_sheet, "Stockholders Equity",
                                   "Total Stockholders Equity", "Common Stock Equity")
        total_assets   = _safe_row(balance_sheet, "Total Assets")
        ebit_row       = _safe_row(financials,    "Operating Income", "EBIT", "Ebit")
        interest_row   = _safe_row(financials,    "Interest Expense")
        current_assets = _safe_row(balance_sheet, "Current Assets", "Total Current Assets")
        current_liab   = _safe_row(balance_sheet, "Current Liabilities", "Total Current Liabilities")

        latest = lambda row: float(row.iloc[0]) if row is not None and len(row) > 0 else None

        debt   = latest(total_debt)
        equity = latest(total_equity)
        assets = latest(total_assets)
        ebit   = latest(ebit_row)
        intr   = latest(interest_row)
        ca     = latest(current_assets)
        cl     = latest(current_liab)

        # D/E Ratio
        if debt is not None and equity and equity != 0:
            result["de_ratio"] = debt / abs(equity)
        elif info.get("debtToEquity"):
            result["de_ratio"] = info["debtToEquity"] / 100.0  # yfinance は 100倍

        # 自己資本比率
        if equity is not None and assets and assets != 0:
            result["equity_ratio"] = abs(equity) / assets
        elif info.get("bookValue") and info.get("totalAssets"):
            shares = info.get("sharesOutstanding", 1)
            result["equity_ratio"] = (info["bookValue"] * shares) / info["totalAssets"]

        # インタレスト・カバレッジ（EBIT/利払い費）
        if ebit is not None and intr and intr != 0:
            result["interest_coverage"] = ebit / abs(intr)
        # info フォールバック
        if result["interest_coverage"] is None:
            result["interest_coverage"] = info.get("interestCoverage") or None

        # 流動比率
        if ca is not None and cl and cl != 0:
            result["current_ratio"] = ca / cl
        elif info.get("currentRatio"):
            result["current_ratio"] = info["currentRatio"]

    except Exception as e:
        result["detail"] = f"計算エラー: {e}"
        result["score"] = 4
        return result

    cfg   = market_config
    score = 0

    # ─── D/E Ratio スコアリング（7点）────────────────────────────────
    de = result["de_ratio"]
    if de is not None:
        if de <= cfg.de_max_excellent:
            score += 7
        elif de <= cfg.de_max_good:
            score += 5
        elif de <= cfg.de_max_ok:
            score += 2
    else:
        score += 3

    # ─── インタレスト・カバレッジ（5点）────────────────────────────
    ic = result["interest_coverage"]
    if ic is not None:
        if ic >= cfg.interest_coverage_good * 3:    # 15倍以上
            score += 5
        elif ic >= cfg.interest_coverage_good * 2:  # 10倍以上
            score += 4
        elif ic >= cfg.interest_coverage_good:       # 5倍以上
            score += 3
        elif ic >= 2:
            score += 1
    else:
        score += 2

    # ─── 自己資本比率（3点）─────────────────────────────────────────
    er = result["equity_ratio"]
    if er is not None:
        if er >= cfg.equity_ratio_good * 1.5:
            score += 3
        elif er >= cfg.equity_ratio_good:
            score += 2
        elif er >= 0.20:
            score += 1
    else:
        score += 1

    result["score"] = min(score, 15)

    de_str = f"{de:.2f}" if de is not None else "N/A"
    er_str = f"{er*100:.1f}%" if er is not None else "N/A"
    ic_str = f"{ic:.1f}x" if ic is not None else "N/A"
    cr_str = f"{result['current_ratio']:.1f}x" if result["current_ratio"] is not None else "N/A"
    result["detail"] = (
        f"D/E {de_str} | 自己資本比率 {er_str} | "
        f"インタレストカバレッジ {ic_str} | 流動比率 {cr_str}"
    )
    return result
