# metrics/capital_efficiency.py — ROE / ROIC / 利益率分析
import numpy as np
import pandas as pd
from typing import Dict, Optional


def _safe_row(df: pd.DataFrame, *keys):
    for k in keys:
        if k in df.index:
            return df.loc[k]
    return None


def analyze_capital_efficiency(
    financials: pd.DataFrame,
    balance_sheet: pd.DataFrame,
    info: dict,
    market_config,
) -> Dict:
    """
    資本効率を分析しスコアと詳細情報を返す。
    満点: 20 点
    """
    result = {
        "score": 0,
        "max_score": 20,
        "roe_avg": None,
        "roic_latest": None,
        "gross_margin_avg": None,
        "operating_margin_avg": None,
        "net_margin_avg": None,
        "detail": "",
    }

    try:
        # ─── ROE ──────────────────────────────────────────────────────
        net_income_row = _safe_row(financials, "Net Income", "Net Income Common Stockholders")
        equity_row = _safe_row(balance_sheet, "Stockholders Equity", "Total Stockholders Equity",
                               "Common Stock Equity")
        if net_income_row is not None and equity_row is not None:
            roe_series = []
            for col in net_income_row.index:
                if col in equity_row.index:
                    ni = net_income_row[col]
                    eq = equity_row[col]
                    if pd.notna(ni) and pd.notna(eq) and eq != 0:
                        roe_series.append(ni / eq)
            roe_avg = float(np.mean(roe_series)) if roe_series else None
        else:
            roe_avg = None

        # info からバックアップ
        if roe_avg is None:
            roe_avg = info.get("returnOnEquity")
        result["roe_avg"] = roe_avg

        # ─── ROIC ─────────────────────────────────────────────────────
        ebit_row = _safe_row(financials, "EBIT", "Ebit", "Operating Income")
        tax_rate = info.get("effectiveTaxRate", 0.21)
        debt_row = _safe_row(balance_sheet, "Total Debt", "Long Term Debt")
        if ebit_row is not None and equity_row is not None and debt_row is not None:
            latest_col = ebit_row.index[0]
            ebit = ebit_row.iloc[0]
            nopat = ebit * (1 - tax_rate)
            equity = equity_row.get(latest_col, None)
            debt = debt_row.get(latest_col, None)
            if equity is not None and debt is not None and (equity + debt) != 0:
                result["roic_latest"] = float(nopat / (equity + debt))

        # ─── 利益率（直近3年平均）────────────────────────────────────
        revenue_row = _safe_row(financials, "Total Revenue", "Revenue")
        gross_row   = _safe_row(financials, "Gross Profit")
        op_row      = _safe_row(financials, "Operating Income", "EBIT", "Ebit")
        net_row     = _safe_row(financials, "Net Income", "Net Income Common Stockholders")

        def calc_margin_avg(numerator_row, denom_row, n=3):
            if numerator_row is None or denom_row is None:
                return None
            margins = []
            for col in numerator_row.index[:n]:
                if col in denom_row.index:
                    num = numerator_row[col]
                    den = denom_row[col]
                    if pd.notna(num) and pd.notna(den) and den != 0:
                        margins.append(num / den)
            return float(np.mean(margins)) if margins else None

        result["gross_margin_avg"]     = calc_margin_avg(gross_row, revenue_row)
        result["operating_margin_avg"] = calc_margin_avg(op_row, revenue_row)
        result["net_margin_avg"]       = calc_margin_avg(net_row, revenue_row)

    except Exception as e:
        result["detail"] = f"計算エラー: {e}"
        result["score"] = 5
        return result

    cfg = market_config
    score = 0

    # ─── ROE スコアリング（10点）─────────────────────────────────────
    if roe_avg is not None:
        if roe_avg >= cfg.roe_excellent:
            score += 10
        elif roe_avg >= cfg.roe_good:
            score += 7
        elif roe_avg >= cfg.roe_ok:
            score += 4
        else:
            score += 0
    else:
        score += 3  # データ不足

    # ─── ROIC スコアリング（5点）────────────────────────────────────
    roic = result["roic_latest"]
    if roic is not None:
        if roic >= cfg.roic_good * 1.5:
            score += 5
        elif roic >= cfg.roic_good:
            score += 3
        elif roic >= cfg.roic_good * 0.7:
            score += 1
    else:
        score += 2

    # ─── 営業利益率スコアリング（5点）───────────────────────────────
    op_margin = result["operating_margin_avg"]
    if op_margin is not None:
        if op_margin >= 0.25:
            score += 5
        elif op_margin >= 0.15:
            score += 3
        elif op_margin >= 0.08:
            score += 1
    else:
        score += 1

    result["score"] = min(score, 20)

    # 詳細コメント
    roe_str  = f"{roe_avg*100:.1f}%"  if roe_avg  is not None else "N/A"
    roic_str = f"{roic*100:.1f}%"     if roic     is not None else "N/A"
    op_str   = f"{op_margin*100:.1f}%" if op_margin is not None else "N/A"
    gm_str   = f"{result['gross_margin_avg']*100:.1f}%" if result["gross_margin_avg"] is not None else "N/A"
    result["detail"] = (
        f"ROE(avg) {roe_str} | ROIC {roic_str} | "
        f"営業利益率 {op_str} | グロスマージン {gm_str}"
    )
    return result
