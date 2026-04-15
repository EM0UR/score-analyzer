# metrics/management.py — 経営陣の資本配分（配当・自社株買い・内部留保効率）
import numpy as np
import pandas as pd
from typing import Dict


def _safe_row(df: pd.DataFrame, *keys):
    for k in keys:
        if k in df.index:
            return df.loc[k]
    return None


def analyze_management(
    financials: pd.DataFrame,
    cashflow: pd.DataFrame,
    balance_sheet: pd.DataFrame,
    info: dict,
    market_config,
) -> Dict:
    """
    経営陣の資本配分の賢明さを評価。満点: 10 点
    """
    result = {
        "score": 0,
        "max_score": 10,
        "dividend_growth": None,
        "payout_ratio": None,
        "buyback_yield": None,
        "total_shareholder_yield": None,
        "roe_improving": False,
        "detail": "",
    }

    try:
        div_row = _safe_row(cashflow, "Payment Of Dividends",
                            "Cash Dividends Paid", "Dividends Paid")
        buyback_row = _safe_row(cashflow, "Repurchase Of Capital Stock",
                                "Common Stock Repurchased", "Repurchase Of Common Stock")
        net_income_row = _safe_row(financials, "Net Income",
                                   "Net Income Common Stockholders")
        equity_row = _safe_row(balance_sheet, "Stockholders Equity",
                               "Total Stockholders Equity", "Common Stock Equity")
        market_cap = info.get("marketCap", None)

        # ─── 配当成長チェック ──────────────────────────────────────────
        div_hist = info.get("dividendRate") or 0
        div_yield = info.get("dividendYield") or 0
        five_yr_yield = info.get("fiveYearAvgDividendYield")

        payout = info.get("payoutRatio")
        result["payout_ratio"] = payout

        # 配当履歴から成長率を推計
        if div_row is not None:
            div_vals = [abs(v) for v in div_row.dropna() if not pd.isna(v)]
            div_vals = [v for v in div_vals if v > 0]
            if len(div_vals) >= 3:
                div_vals_sorted = sorted(div_vals)[::-1]  # 最新が先頭
                first, last = div_vals_sorted[-1], div_vals_sorted[0]
                if first > 0:
                    n = len(div_vals_sorted) - 1
                    result["dividend_growth"] = (last / first) ** (1 / n) - 1

        # ─── 自社株買いイールド ────────────────────────────────────────
        if buyback_row is not None and market_cap and market_cap > 0:
            bb_vals = [abs(v) for v in buyback_row.dropna().iloc[:3] if v < 0]
            if bb_vals:
                avg_bb = float(np.mean(bb_vals))
                result["buyback_yield"] = avg_bb / market_cap

        # ─── 株主総利回り（配当 + 自社株買い）───────────────────────
        if result["buyback_yield"] is not None:
            total = result["buyback_yield"] + (div_yield or 0)
            result["total_shareholder_yield"] = total

        # ─── ROE 改善トレンド ──────────────────────────────────────────
        if net_income_row is not None and equity_row is not None:
            roe_vals = []
            for col in net_income_row.index:
                if col in equity_row.index:
                    ni = net_income_row[col]
                    eq = equity_row[col]
                    if pd.notna(ni) and pd.notna(eq) and eq != 0:
                        roe_vals.append(ni / eq)
            if len(roe_vals) >= 3:
                result["roe_improving"] = roe_vals[0] > roe_vals[-1]  # 最新 > 最古

    except Exception as e:
        result["detail"] = f"計算エラー: {e}"
        result["score"] = 3
        return result

    score = 0

    # ─── 配当の安定性・成長性（4点）──────────────────────────────────
    dg = result["dividend_growth"]
    if dg is not None:
        if dg >= 0.05:    # 5%以上の配当成長
            score += 4
        elif dg >= 0.02:
            score += 2
        elif dg >= 0:
            score += 1
    elif div_yield and div_yield > 0:
        score += 1  # 配当あり（成長率不明）

    # ─── 自社株買いイールド（3点）────────────────────────────────────
    by = result["buyback_yield"]
    if by is not None:
        if by >= 0.03:
            score += 3
        elif by >= 0.01:
            score += 2
        elif by > 0:
            score += 1

    # ─── 配当性向の健全性（2点：30〜60% がバフェット的理想）─────────
    pr = result["payout_ratio"]
    if pr is not None and 0 < pr <= 0.70:
        score += 2
    elif pr is not None and 0 < pr <= 1.0:
        score += 1

    # ─── ROE 改善トレンド（1点）──────────────────────────────────────
    if result["roe_improving"]:
        score += 1

    result["score"] = min(score, 10)

    dg_str = f"{dg*100:.1f}%"     if dg is not None else "N/A"
    by_str = f"{by*100:.1f}%"     if by is not None else "N/A"
    pr_str = f"{pr*100:.0f}%"     if pr is not None else "N/A"
    ty_str = f"{result['total_shareholder_yield']*100:.1f}%"              if result["total_shareholder_yield"] is not None else "N/A"
    result["detail"] = (
        f"配当成長率 {dg_str} | 自社株買いイールド {by_str} | "
        f"配当性向 {pr_str} | 株主総利回り {ty_str} | "
        f"ROE 改善傾向 {'✅' if result['roe_improving'] else '—'}"
    )
    return result
