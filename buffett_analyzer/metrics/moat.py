# metrics/moat.py — 経済的堀（Moat）定量スコア
import numpy as np
import pandas as pd
from typing import Dict


def _safe_row(df: pd.DataFrame, *keys):
    for k in keys:
        if k in df.index:
            return df.loc[k]
    return None


def analyze_moat(
    financials: pd.DataFrame,
    cashflow: pd.DataFrame,
    info: dict,
    market_config,
) -> Dict:
    """
    Moat の定量的側面を評価。満点: 15 点
    """
    result = {
        "score": 0,
        "max_score": 15,
        "gross_margin_avg": None,
        "gross_margin_std": None,
        "capex_to_revenue": None,
        "buyback_yield": None,
        "detail": "",
    }

    try:
        rev_row       = _safe_row(financials, "Total Revenue", "Revenue")
        gross_row     = _safe_row(financials, "Gross Profit")
        capex_row     = _safe_row(cashflow,   "Capital Expenditures",
                                  "Purchase Of Property Plant And Equipment", "Capital Expenditure")
        buyback_row   = _safe_row(cashflow,   "Repurchase Of Capital Stock",
                                  "Common Stock Repurchased", "Repurchase Of Common Stock")

        # ─── グロスマージン安定性 ─────────────────────────────────────
        if rev_row is not None and gross_row is not None:
            cols = rev_row.index.intersection(gross_row.index)
            gm_series = []
            for c in cols:
                rev = rev_row[c]
                gp  = gross_row[c]
                if pd.notna(rev) and pd.notna(gp) and rev != 0:
                    gm_series.append(gp / rev)
            if gm_series:
                result["gross_margin_avg"] = float(np.mean(gm_series))
                result["gross_margin_std"] = float(np.std(gm_series))

        # ─── CapEx/Revenue（資産軽量型ビジネスか）─────────────────────
        if rev_row is not None and capex_row is not None:
            cols = rev_row.index.intersection(capex_row.index)
            ratios = []
            for c in cols:
                rev  = rev_row[c]
                capex = capex_row[c]
                if pd.notna(rev) and pd.notna(capex) and rev != 0:
                    ratios.append(abs(capex) / rev)
            if ratios:
                result["capex_to_revenue"] = float(np.mean(ratios[:3]))

        # ─── 自社株買いイールド（buyback yield）──────────────────────
        market_cap = info.get("marketCap")
        if buyback_row is not None and market_cap and market_cap != 0:
            buyback_vals = [abs(v) for v in buyback_row.dropna().iloc[:3] if v < 0]
            if buyback_vals:
                avg_buyback = float(np.mean(buyback_vals))
                result["buyback_yield"] = avg_buyback / market_cap

    except Exception as e:
        result["detail"] = f"計算エラー: {e}"
        result["score"] = 4
        return result

    cfg   = market_config
    score = 0

    # ─── グロスマージン水準（6点）────────────────────────────────────
    gm = result["gross_margin_avg"]
    if gm is not None:
        if gm >= 0.50:
            score += 6
        elif gm >= 0.35:
            score += 4
        elif gm >= 0.20:
            score += 2
    else:
        score += 2

    # ─── グロスマージン安定性（4点：stdが小さいほど良い）────────────
    gm_std = result["gross_margin_std"]
    if gm_std is not None:
        if gm_std <= cfg.gross_margin_std_ok * 0.5:
            score += 4
        elif gm_std <= cfg.gross_margin_std_ok:
            score += 3
        elif gm_std <= cfg.gross_margin_std_ok * 2:
            score += 1
    else:
        score += 1

    # ─── CapEx/Revenue（3点：低いほど Moat が強い）───────────────────
    ctr = result["capex_to_revenue"]
    if ctr is not None:
        if ctr <= cfg.capex_to_revenue_ok * 0.5:
            score += 3
        elif ctr <= cfg.capex_to_revenue_ok:
            score += 2
        elif ctr <= cfg.capex_to_revenue_ok * 2:
            score += 1
    else:
        score += 1

    # ─── 自社株買いボーナス（2点）────────────────────────────────────
    by = result["buyback_yield"]
    if by is not None and by >= 0.01:
        score += 2

    result["score"] = min(score, 15)

    gm_str  = f"{gm*100:.1f}%"      if gm      is not None else "N/A"
    std_str = f"±{gm_std*100:.1f}%" if gm_std  is not None else "N/A"
    ctr_str = f"{ctr*100:.1f}%"     if ctr     is not None else "N/A"
    by_str  = f"{by*100:.1f}%"      if by      is not None else "N/A"
    result["detail"] = (
        f"グロスマージン {gm_str}({std_str}) | "
        f"CapEx/Rev {ctr_str} | 自社株買いイールド {by_str}"
    )
    return result
