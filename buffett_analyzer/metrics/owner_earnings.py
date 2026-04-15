# metrics/owner_earnings.py — Owner Earnings / FCF 分析
import numpy as np
import pandas as pd
from typing import Dict, Optional


def _safe_row(df: pd.DataFrame, *keys):
    for k in keys:
        if k in df.index:
            return df.loc[k]
    return None


def analyze_owner_earnings(
    financials: pd.DataFrame,
    cashflow: pd.DataFrame,
    balance_sheet: pd.DataFrame,
    info: dict,
    market_config,
) -> Dict:
    """
    バフェット流 Owner Earnings = 営業CF − 維持的CapEx を計算。
    満点: 20 点
    """
    result = {
        "score": 0,
        "max_score": 20,
        "owner_earnings_latest": None,
        "owner_earnings_cagr": None,
        "fcf_margin_latest": None,
        "fcf_yield_latest": None,
        "owner_earnings_series": None,
        "detail": "",
    }

    try:
        op_cf_row = _safe_row(cashflow, "Total Cash From Operating Activities",
                               "Operating Cash Flow", "Cash From Operations")
        capex_row = _safe_row(cashflow, "Capital Expenditures", "Purchase Of Property Plant And Equipment",
                               "Capital Expenditure")
        revenue_row = _safe_row(financials, "Total Revenue", "Revenue")

        if op_cf_row is None or capex_row is None:
            result["detail"] = "キャッシュフローデータ不足"
            result["score"] = 6
            return result

        # 共通カラムで計算
        cols = op_cf_row.index.intersection(capex_row.index)
        if len(cols) == 0:
            result["detail"] = "OCF/CapEx のカラム不一致"
            result["score"] = 6
            return result

        op_cf = op_cf_row[cols]
        capex = capex_row[cols]

        # CapEx はマイナス値で格納されているため絶対値を引く
        oe_series = op_cf - capex.abs()
        oe_series = oe_series.sort_index()
        result["owner_earnings_series"] = oe_series

        # 最新値
        latest_oe = float(oe_series.iloc[-1])
        result["owner_earnings_latest"] = latest_oe

        # CAGR（最低2期）
        n = len(oe_series)
        if n >= 2:
            first, last = oe_series.iloc[0], oe_series.iloc[-1]
            if first > 0 and last > 0:
                result["owner_earnings_cagr"] = (last / first) ** (1 / (n - 1)) - 1

        # FCF マージン（最新期）
        if revenue_row is not None:
            rev_cols = revenue_row.index.intersection(capex_row.index)
            if len(rev_cols) > 0:
                latest_rev = float(revenue_row[rev_cols[0]])
                if latest_rev != 0:
                    result["fcf_margin_latest"] = latest_oe / latest_rev

        # FCF Yield
        market_cap = info.get("marketCap")
        if market_cap and market_cap != 0:
            result["fcf_yield_latest"] = latest_oe / market_cap

    except Exception as e:
        result["detail"] = f"計算エラー: {e}"
        result["score"] = 5
        return result

    cfg   = market_config
    score = 0
    oe_cagr  = result["owner_earnings_cagr"]
    fcf_margin = result["fcf_margin_latest"]
    fcf_yield  = result["fcf_yield_latest"]

    # ─── OE の水準（最新値がプラスか）（5点）────────────────────────
    if result["owner_earnings_latest"] is not None:
        if result["owner_earnings_latest"] > 0:
            score += 5

    # ─── OE CAGR スコアリング（8点）─────────────────────────────────
    if oe_cagr is not None:
        if oe_cagr >= 0.12:
            score += 8
        elif oe_cagr >= 0.08:
            score += 6
        elif oe_cagr >= cfg.min_oe_cagr:
            score += 3
        elif oe_cagr >= 0:
            score += 1
    else:
        score += 3

    # ─── FCF マージン（4点）─────────────────────────────────────────
    if fcf_margin is not None:
        if fcf_margin >= cfg.fcf_margin_good * 2:
            score += 4
        elif fcf_margin >= cfg.fcf_margin_good:
            score += 3
        elif fcf_margin >= cfg.fcf_margin_good * 0.5:
            score += 1
    else:
        score += 1

    # ─── FCF Yield（3点）────────────────────────────────────────────
    if fcf_yield is not None:
        if fcf_yield >= cfg.fcf_yield_good * 1.5:
            score += 3
        elif fcf_yield >= cfg.fcf_yield_good:
            score += 2
        elif fcf_yield >= cfg.fcf_yield_good * 0.5:
            score += 1
    else:
        score += 1

    result["score"] = min(score, 20)

    sym = market_config.currency_symbol
    oe_val = result["owner_earnings_latest"]
    oe_str = f"{sym}{oe_val/1e9:.2f}B" if oe_val and abs(oe_val) >= 1e9 else              f"{sym}{oe_val/1e6:.1f}M" if oe_val else "N/A"
    cagr_str   = f"{oe_cagr*100:.1f}%"    if oe_cagr  is not None else "N/A"
    margin_str = f"{fcf_margin*100:.1f}%" if fcf_margin is not None else "N/A"
    yield_str  = f"{fcf_yield*100:.1f}%"  if fcf_yield  is not None else "N/A"

    result["detail"] = (
        f"Owner Earnings {oe_str} | CAGR {cagr_str} | "
        f"FCF Margin {margin_str} | FCF Yield {yield_str}"
    )
    return result
