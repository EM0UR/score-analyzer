owner_earnings.py
import numpy as np
from buffett_analyzer.metrics.utils import safe_row, ttm_sum, annual_values, cagr

def analyze_owner_earnings(financials, cashflow, balance_sheet, info, cfg,
                            q_cashflow=None, q_financials=None):
    result = {
        "score": 0, "max_score": 20,
        "fcf_ttm": None, "fcf_margin": None,
        "oe_cagr": None, "fcf_yield": None,
        "data_source": "annual",
        "detail": ""
    }

    try:
        # ── ① TTM FCF（四半期優先・年次フォールバック）──────────────
        fcf_ttm = None

        if q_cashflow is not None and not q_cashflow.empty:
            op  = ttm_sum(q_cashflow,
                          "Operating Cash Flow", "Total Cash From Operating Activities",
                          "Cash Flow From Continuing Operating Activities")
            cap = ttm_sum(q_cashflow,
                          "Capital Expenditure", "Purchase Of Property Plant And Equipment",
                          "Capital Expenditures")
            if op is not None:
                fcf_ttm = op + (cap if cap is not None else 0)  # capexは通常負値
                result["data_source"] = "quarterly_TTM"

        if fcf_ttm is None:
            # 年次フォールバック（最新年度）
            op_a  = annual_values(cashflow,
                                  "Operating Cash Flow", "Total Cash From Operating Activities",
                                  "Cash Flow From Continuing Operating Activities")
            cap_a = annual_values(cashflow,
                                  "Capital Expenditure", "Purchase Of Property Plant And Equipment",
                                  "Capital Expenditures")
            if op_a:
                cap_v = cap_a[0] if cap_a else 0
                fcf_ttm = op_a[0] + cap_v
                result["data_source"] = "annual_latest"

        result["fcf_ttm"] = fcf_ttm

        # ── ② FCFマージン（TTM売上との比率）─────────────────────────
        rev_ttm = None
        if q_financials is not None and not q_financials.empty:
            rev_ttm = ttm_sum(q_financials, "Total Revenue", "Revenue", "Net Revenue")
        if rev_ttm is None:
            revs = annual_values(financials, "Total Revenue", "Revenue", "Net Revenue")
            rev_ttm = revs[0] if revs else None

        if fcf_ttm and rev_ttm and rev_ttm > 0:
            result["fcf_margin"] = fcf_ttm / rev_ttm

        # ── ③ FCF成長CAGR（年次データで長期トレンドを計算）──────────
        op_hist  = annual_values(cashflow,
                                 "Operating Cash Flow", "Total Cash From Operating Activities",
                                 "Cash Flow From Continuing Operating Activities")
        cap_hist = annual_values(cashflow,
                                 "Capital Expenditure", "Purchase Of Property Plant And Equipment",
                                 "Capital Expenditures")
        fcf_hist = []
        for i, op_v in enumerate(op_hist):
            cap_v = cap_hist[i] if i < len(cap_hist) else 0
            fcf_hist.append(op_v + cap_v)

        oe_cagr = cagr(fcf_hist)
        result["oe_cagr"] = oe_cagr

        # ── ④ FCFイールド（時価総額比）────────────────────────────
        mc = info.get("marketCap")
        if fcf_ttm and mc and mc > 0:
            result["fcf_yield"] = fcf_ttm / mc

        # ── ⑤ スコアリング ────────────────────────────────────────
        s = 0
        fm = result["fcf_margin"]
        if fm is not None:
            if   fm >= 0.20: s += 6
            elif fm >= cfg.fcf_margin_good: s += 4
            elif fm >= 0.04: s += 2

        if oe_cagr is not None:
            if   oe_cagr >= 0.12: s += 6
            elif oe_cagr >= cfg.min_oe_cagr: s += 4
            elif oe_cagr >= 0.02: s += 2

        fy = result["fcf_yield"]
        if fy is not None:
            if   fy >= 0.06: s += 5
            elif fy >= cfg.fcf_yield_good: s += 3
            elif fy >= 0.02: s += 1
        elif fcf_ttm and fcf_ttm > 0:
            s += 3  # 時価総額不明でもFCF正値なら加点

        result["score"] = min(s, 20)

        # ── ⑥ 詳細テキスト ──────────────────────────────────────
        src   = "四半期TTM" if result["data_source"] == "quarterly_TTM" else "年次"
        fcf_b = f"{fcf_ttm/1e9:.2f}B" if fcf_ttm and abs(fcf_ttm) >= 1e9 else (
                f"{fcf_ttm/1e6:.0f}M" if fcf_ttm else "—")
        fm_s  = f"{fm*100:.1f}%" if fm else "—"
        cg_s  = f"{oe_cagr*100:.1f}%" if oe_cagr else "—"
        fy_s  = f"{fy*100:.1f}%" if fy else "—"
        result["detail"] = (
            f"FCF {fcf_b} [{src}] | マージン {fm_s} | CAGR(年次) {cg_s} | FCFイールド {fy_s}"
        )

    except Exception as e:
        result["score"]  = 3
        result["detail"] = f"計算エラー: {e}"

    return result
