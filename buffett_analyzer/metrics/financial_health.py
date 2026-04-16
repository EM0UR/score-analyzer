financial_health.py
import pandas as pd

# ── インライン ヘルパー ────────────────────────────────────────
def _safe_row(df, *keys):
    if df is None or (hasattr(df, "empty") and df.empty): return None
    for k in keys:
        if k in df.index: return df.loc[k]
    return None

def _first_val(df, col_idx, *keys):
    row = _safe_row(df, *keys)
    if row is None: return None
    try:
        cols = df.columns
        if col_idx < len(cols):
            v = row[cols[col_idx]]
            return float(v) if v is not None and str(v) != "nan" else None
    except Exception:
        return None
    return None

# ── メイン関数 ────────────────────────────────────────────────
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
        # ① D/E 比率（四半期最新 → 年次 → info フォールバック）
        bs_use = None
        if q_balance_sheet is not None and hasattr(q_balance_sheet, "empty") and not q_balance_sheet.empty:
            bs_use = q_balance_sheet
            result["data_source"] = "quarterly_latest"
        elif balance_sheet is not None and hasattr(balance_sheet, "empty") and not balance_sheet.empty:
            bs_use = balance_sheet

        de = None
        if bs_use is not None and len(bs_use.columns) > 0:
            for col_idx in range(min(2, len(bs_use.columns))):
                eq_v  = _first_val(bs_use, col_idx,
                                   "Stockholders Equity", "Total Stockholder Equity",
                                   "Common Stock Equity", "Total Equity Gross Minority Interest")
                ltd_v = _first_val(bs_use, col_idx,
                                   "Long Term Debt", "Long-Term Debt And Capital Lease Obligation") or 0.0
                cld_v = _first_val(bs_use, col_idx,
                                   "Current Debt", "Current Long Term Debt",
                                   "Short Long Term Debt", "Short Term Borrowings") or 0.0
                if eq_v and eq_v > 0:
                    de = (ltd_v + cld_v) / eq_v
                    break

        if de is None:
            raw = info.get("debtToEquity")
            de = raw / 100 if raw is not None else None

        result["de_ratio"] = de

        # ② 自己資本比率
        if bs_use is not None and len(bs_use.columns) > 0:
            eq_v = _first_val(bs_use, 0,
                              "Stockholders Equity", "Total Stockholder Equity",
                              "Common Stock Equity", "Total Equity Gross Minority Interest")
            ta_v = _first_val(bs_use, 0, "Total Assets")
            if eq_v and ta_v and ta_v > 0:
                result["equity_ratio"] = eq_v / ta_v

        # ③ 流動比率
        if bs_use is not None and len(bs_use.columns) > 0:
            ca_v = _first_val(bs_use, 0, "Current Assets", "Total Current Assets")
            cl_v = _first_val(bs_use, 0, "Current Liabilities", "Total Current Liabilities")
            if ca_v and cl_v and cl_v > 0:
                result["current_ratio"] = ca_v / cl_v

        # ④ インタレストカバレッジ（info TTM）
        ic = info.get("interestCoverage")
        if ic is None:
            ebitda = info.get("ebitda")
            int_exp = info.get("interestExpense")
            if ebitda and int_exp and int_exp < 0:
                ic = ebitda / abs(int_exp)
        result["interest_coverage"] = ic

        # ⑤ スコアリング
        s = 0
        if de is not None:
            if   de <= cfg.de_max_excellent: s += 6
            elif de <= cfg.de_max_good:      s += 4
            elif de <= cfg.de_max_ok:        s += 2

        er = result["equity_ratio"]
        if er is not None:
            if   er >= 0.60:                      s += 4
            elif er >= cfg.equity_ratio_good:     s += 3
            elif er >= 0.25:                      s += 1

        cr = result["current_ratio"]
        if cr is not None:
            if   cr >= 2.0: s += 3
            elif cr >= 1.5: s += 2
            elif cr >= 1.0: s += 1

        if ic is not None:
            if   ic >= 10:                         s += 2
            elif ic >= cfg.interest_coverage_good: s += 1

        result["score"] = min(s, 15)

        # ⑥ 詳細テキスト
        src  = "四半期" if result["data_source"] == "quarterly_latest" else "年次"
        de_s = f"D/E {de:.2f}" if de is not None else "D/E —"
        er_s = f"自己資本比率 {er*100:.0f}%" if er is not None else ""
        cr_s = f"流動比率 {cr:.1f}x" if cr is not None else ""
        ic_s = f"IC {ic:.1f}x" if ic is not None else ""
        result["detail"] = f"{de_s} [{src}]"             + (f" | {er_s}" if er_s else "")             + (f" | {cr_s}" if cr_s else "")             + (f" | {ic_s}" if ic_s else "")

    except Exception as e:
        result["score"]  = 2
        result["detail"] = f"計算エラー: {e}"

    return result
