# metrics/earnings.py — 収益一貫性チェック（EPS 推移・CAGR・ブレ）
import numpy as np
import pandas as pd
from typing import Dict, Optional

def _get_annual_eps(financials: pd.DataFrame, info: dict) -> Optional[pd.Series]:
    """yfinance financials から EPS 年次シリーズを抽出。"""
    try:
        net_income = None
        for key in ["Net Income", "Net Income Common Stockholders"]:
            if key in financials.index:
                net_income = financials.loc[key]
                break
        if net_income is None:
            return None

        shares = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
        if not shares or shares == 0:
            return None

        eps_series = (net_income / shares).sort_index()
        return eps_series
    except Exception:
        return None


def analyze_earnings(financials: pd.DataFrame, info: dict) -> Dict:
    """
    収益一貫性を分析し、スコアと詳細情報を返す。
    満点: 20 点
    """
    result = {
        "score": 0,
        "max_score": 20,
        "eps_series": None,
        "eps_cagr": None,
        "eps_std": None,
        "negative_years": 0,
        "growth_consistent": False,
        "detail": "",
    }

    eps = _get_annual_eps(financials, info)
    if eps is None or len(eps) < 2:
        result["detail"] = "EPS データ不足（スコア対象外）"
        result["score"] = 6  # データ不足ペナルティ
        return result

    result["eps_series"] = eps
    eps_clean = eps.dropna()
    n = len(eps_clean)

    # マイナス EPS の年数
    neg_years = int((eps_clean < 0).sum())
    result["negative_years"] = neg_years

    # CAGR（最古と最新が両方正値のときのみ）
    first, last = eps_clean.iloc[0], eps_clean.iloc[-1]
    years = n - 1
    if first > 0 and last > 0 and years > 0:
        cagr = (last / first) ** (1 / years) - 1
        result["eps_cagr"] = cagr
    else:
        cagr = None

    # 標準偏差（変動係数 = std/mean で正規化）
    if eps_clean.mean() != 0:
        cv = eps_clean.std() / abs(eps_clean.mean())
        result["eps_std"] = cv
    else:
        cv = None

    # 成長一貫性：連続して増加している年率が 70% 以上
    diffs = eps_clean.diff().dropna()
    positive_diffs = (diffs > 0).sum()
    result["growth_consistent"] = positive_diffs / len(diffs) >= 0.7

    # ─── スコアリング（20点満点）────────────────────────────
    score = 0

    # マイナス年数（0年→8点、1年→4点、2年以上→0点）
    if neg_years == 0:
        score += 8
    elif neg_years == 1:
        score += 4

    # CAGR（8%以上→8点、5〜8%→5点、0〜5%→2点、負値→0点）
    if cagr is not None:
        if cagr >= 0.08:
            score += 8
        elif cagr >= 0.05:
            score += 5
        elif cagr >= 0.0:
            score += 2

    # 成長一貫性ボーナス（70%以上で連続増加）
    if result["growth_consistent"]:
        score += 4

    result["score"] = min(score, 20)

    # 詳細コメント
    cagr_str = f"{cagr*100:.1f}%" if cagr is not None else "N/A"
    result["detail"] = (
        f"EPS {n}期分 | CAGR {cagr_str} | "
        f"マイナス年: {neg_years}回 | "
        f"連続成長 {'✅' if result['growth_consistent'] else '❌'}"
    )

    return result
