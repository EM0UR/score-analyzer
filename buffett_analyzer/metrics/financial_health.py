financial_health.py
import numpy as np
from buffett_analyzer.metrics.utils import safe_row, ttm_latest, annual_values

def analyze_financial_health(financials, balance_sheet, cashflow, info, cfg,
                              q_balance_sheet=None, q_cashflow=None):
    result = {
        "score": 0, "max_score": 15,
        "de_ratio": None, "equity_ratio": None,
        "interest_coverage": None, "current_ratio": None,
        "data_source": "annual",
        "detail": ""
    }

    try:
        # ── ① D/E比率（四半期最新 → 年次フォールバック）────────────
        de = None
        bs_use = None

        if q_balance_sheet is not None and not q_balance_sheet.empty:
            bs_use = q_balance_sheet
            result["data_source"] = "quarterly_latest"
        elif balance_sheet is not None and not balance_sheet.empty:
            bs_use = balance_sheet

        if bs_use is not None:
            total_debt = None
            for col in bs_use.columns[:2]:   # 直近2期を試行
                eq_row  = safe_row(bs_use, "Stockholders Equity", "Total Stockholder Equity",
                                   "Common Stock Equity", "Total Equity Gross Minority Interest")
                ltd_row = safe_row(bs_use, "Long Term Debt", "Long-Term Debt And Capital Lease Obligation")
                cld_row = safe_row(bs_use, "Current Debt", "Current Long Term Debt",
                                   "Short Long Term Debt", "Short Term Borrowings")
                try:
                    eq  = float(eq_row[col])   if eq_row  is not None else None
                    ltd = float(ltd_row[col])   if ltd_row is not None else 0
                    cld = float(cld_row[col])   if cld_row is not None else 0
                    if eq and eq > 0:
                        de = (ltd + cld) / eq
                        total_debt = ltd + cld
                        break
                except Exception:
                    continue

        if de is None:
            de = (info.get("debtToEquity") or 0) / 100
        result["de_ratio"] = de

        # ── ② 自己資本比率 ─────────────────────────────────────────
        if bs_use is not None:
            try:
                col     = bs_use.columns[0]
                eq_row  = safe_row(bs_use, "Stockholders Equity", "Total Stockholder Equity",
                                   "Common Stock Equity", "Total Equity Gross Minority Interest")
                ta_row  = safe_row(bs_use, "Total Assets")
                eq_v    = float(eq_row[col]) if eq_row  is not None else None
                ta_v    = float(ta_row[col]) if ta_row  is not None else None
                if eq_v and ta_v and ta_v > 0:
                    result["equity_ratio"] = eq_v / ta_v
            except Exception:
                pass

        # ── ③ 流動比率（四半期優先）────────────────────────────────
        if bs_use is not None:
            try:
                col     = bs_use.columns[0]
                ca_row  = safe_row(bs_use, "Current Assets", "Total Current Assets")
                cl_row  = safe_row(bs_use, "Current Liabilities", "Total Current Liabilities")
                ca_v = float(ca_row[col]) if ca_row is not None else None
                cl_v = float(cl_row[col]) if cl_row is not None else None
                if ca_v and cl_v and cl_v > 0:
                    result["current_ratio"] = ca_v / cl_v
            except Exception:
                pass

        # ── ④ インタレストカバレッジ（infoから取得が最新）──────────
        ebit = info.get("ebitda")  # 近似値
        interest_exp = info.get("totalDebt", 0)
        ic = info.get("interestCoverage")
        if ic is None and ebit:
            int_exp = info.get("interestExpense")
            if int_exp and int_exp < 0:
                ic = ebit / abs(int_exp)
        result["interest_coverage"] = ic

        # ── ⑤ スコアリング ────────────────────────────────────────
        s = 0
        if de is not None:
            if   de <= cfg.de_max_excellent: s += 6
            elif de <= cfg.de_max_good:      s += 4
            elif de <= cfg.de_max_ok:        s += 2

        er = result["equity_ratio"]
        if er is not None:
            if   er >= 0.60: s += 4
            elif er >= cfg.equity_ratio_good: s += 3
            elif er >= 0.25: s += 1

        cr = result["current_ratio"]
        if cr is not None:
            if   cr >= 2.0: s += 3
            elif cr >= 1.5: s += 2
            elif cr >= 1.0: s += 1

        if ic is not None:
            if   ic >= 10: s += 2
            elif ic >= cfg.interest_coverage_good: s += 1

        result["score"] = min(s, 15)

        # ── ⑥ 詳細テキスト ──────────────────────────────────────
        src  = "四半期" if result["data_source"] == "quarterly_latest" else "年次"
        de_s = f"D/E {de:.2f}" if de is not None else "D/E —"
        er_s = f"自己資本比率 {er*100:.0f}%" if er is not None else ""
        cr_s = f"流動比率 {cr:.1f}x" if cr is not None else ""
        ic_s = f"IC {ic:.1f}x" if ic is not None else ""
        result["detail"] = f"{de_s} [{src}]" + (f" | {er_s}" if er_s else "") +                            (f" | {cr_s}" if cr_s else "") + (f" | {ic_s}" if ic_s else "")

    except Exception as e:
        result["score"]  = 2
        result["detail"] = f"計算エラー: {e}"

    return result
