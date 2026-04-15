# metrics/valuation.py — DCF 本質的価値 / PER / Margin of Safety
import numpy as np
import pandas as pd
from typing import Dict, Optional


def _safe_row(df: pd.DataFrame, *keys):
    for k in keys:
        if k in df.index:
            return df.loc[k]
    return None


def _two_stage_dcf(
    last_oe: float,
    growth_high: float,
    growth_low: float,
    years_high: int,
    discount_rate: float,
    terminal_growth: float,
) -> float:
    """
    2ステージ DCF：最初 years_high 年は growth_high、その後は growth_low で成長し、
    最終的に terminal_growth で永続。
    """
    oe = last_oe
    pv = 0.0

    for t in range(1, years_high + 1):
        oe *= (1 + growth_high)
        pv += oe / ((1 + discount_rate) ** t)

    for t in range(years_high + 1, 21):
        oe *= (1 + growth_low)
        pv += oe / ((1 + discount_rate) ** t)

    # ターミナルバリュー（20年目以降）
    tv = oe * (1 + terminal_growth) / (discount_rate - terminal_growth)
    pv += tv / ((1 + discount_rate) ** 20)

    return pv


def analyze_valuation(
    financials: pd.DataFrame,
    cashflow: pd.DataFrame,
    balance_sheet: pd.DataFrame,
    info: dict,
    owner_earnings_result: dict,
    market_config,
) -> Dict:
    """
    本質的価値計算と Margin of Safety。満点: 10 点
    """
    result = {
        "score": 0,
        "max_score": 10,
        "intrinsic_value_dcf": None,
        "intrinsic_value_per_per": None,
        "margin_of_safety_dcf": None,
        "current_price": None,
        "pe_ratio": None,
        "detail": "",
    }

    try:
        current_price = (
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("previousClose")
        )
        result["current_price"] = current_price

        shares = (
            info.get("sharesOutstanding")
            or info.get("impliedSharesOutstanding")
        )

        oe_latest = owner_earnings_result.get("owner_earnings_latest")
        oe_cagr   = owner_earnings_result.get("owner_earnings_cagr")

        # ─── DCF（2ステージ）──────────────────────────────────────────
        if oe_latest and oe_latest > 0 and shares and shares > 0:
            g_high = min(oe_cagr or market_config.min_oe_cagr, 0.20)  # 上限 20%
            g_low  = max(g_high * 0.5, market_config.terminal_growth)
            firm_value = _two_stage_dcf(
                last_oe      = oe_latest,
                growth_high  = g_high,
                growth_low   = g_low,
                years_high   = 10,
                discount_rate= market_config.discount_rate,
                terminal_growth = market_config.terminal_growth,
            )
            intrinsic = firm_value / shares
            result["intrinsic_value_dcf"] = intrinsic

            if current_price and current_price > 0:
                result["margin_of_safety_dcf"] = (intrinsic - current_price) / intrinsic * 100

        # ─── PER ベース簡易バリュエーション──────────────────────────
        pe = info.get("trailingPE") or info.get("forwardPE")
        result["pe_ratio"] = pe
        eps_ttm = info.get("trailingEps") or info.get("epsCurrentYear")
        fair_pe = 15.0  # バフェットが割安とみなす基準 PER（S&P500 平均を参考）
        if eps_ttm and eps_ttm > 0:
            result["intrinsic_value_per_per"] = eps_ttm * fair_pe

    except Exception as e:
        result["detail"] = f"計算エラー: {e}"
        result["score"] = 3
        return result

    score = 0
    mos = result["margin_of_safety_dcf"]
    pe  = result["pe_ratio"]

    # ─── Margin of Safety スコアリング（7点）────────────────────────
    if mos is not None:
        if mos >= market_config.mos_excellent:
            score += 7
        elif mos >= market_config.mos_good:
            score += 5
        elif mos >= 0:
            score += 3
        else:
            score += 0  # 割高
    else:
        score += 3  # DCF不可なら中立

    # ─── PER チェック（3点）──────────────────────────────────────────
    if pe is not None:
        if pe <= 15:
            score += 3
        elif pe <= 20:
            score += 2
        elif pe <= 25:
            score += 1

    result["score"] = min(score, 10)

    sym = market_config.currency_symbol
    iv_str  = f"{sym}{result['intrinsic_value_dcf']:.2f}"  if result["intrinsic_value_dcf"]  else "N/A"
    cp_str  = f"{sym}{current_price:.2f}"                   if current_price                   else "N/A"
    mos_str = f"{mos:.1f}%"                                 if mos is not None                 else "N/A"
    pe_str  = f"{pe:.1f}x"                                  if pe  is not None                 else "N/A"
    result["detail"] = (
        f"本質的価値(DCF) {iv_str} | 現在株価 {cp_str} | "
        f"MoS {mos_str} | PER {pe_str}"
    )
    return result
