import pandas as pd

# ── インライン ヘルパー ────────────────────────────────────────
def _safe_row(df, *keys):
    if df is None or (hasattr(df, "empty") and df.empty): return None
    for k in keys:
        if k in df.index: return df.loc[k]
    return None

def _ttm_sum(q_df, *keys):
    """四半期DataFrameから直近4Q合計(TTM)を計算"""
    try:
        row = _safe_row(q_df, *keys)
        if row is None: return None
        vals = row.dropna().iloc[:4]
        if len(vals) < 2: return None
        return float(vals.sum())
    except Exception:
        return None

def _annual_list(a_df, *keys, n=10):
    """年次DataFrameから最大n年分をリストで返す（新しい順）"""
    try:
        row = _safe_row(a_df, *keys)
        if row is None: return []
        return [float(v) for v in row.dropna().iloc[:n]]
    except Exception:
        return []

def _cagr(values):
    try:
        vals = [v for v in values if v and v > 0]
        if len(vals) < 2: return None
        n = len(vals) - 1
        return (vals[0] / vals[-1]) ** (1 / n) - 1
    except Exception:
        return None

# ── メイン関数 ────────────────────────────────────────────────
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
        # ① TTM FCF（四半期優先・年次フォールバック）
        fcf_ttm = None

        if q_cashflow is not None and hasattr(q_cashflow, "empty") and not q_cashflow.empty:
            op  = _ttm_sum(q_cashflow,
                           "Operating Cash Flow",
                           "Total Cash From Operating Activities",
                           "Cash Flow From Continuing Operating Activities")
            cap = _ttm_sum(q_cashflow,
                           "Capital Expenditure",
                           "Purchase Of Property Plant And Equipment",
                           "Capital Expenditures") or 0.0
            if op is not None:
                fcf_ttm = op + cap   # capexは通常負値なのでそのまま加算
                result["data_source"] = "quarterly_TTM"

        if fcf_ttm is None and cashflow is not None and hasattr(cashflow, "empty") and not cashflow.empty:
            op_a  = _annual_list(cashflow,
                                 "Operating Cash Flow",
                                 "Total Cash From Operating Activities",
                                 "Cash Flow From Continuing Operating Activities")
            cap_a = _annual_list(cashflow,
                                 "Capital Expenditure",
                                 "Purchase Of Property Plant And Equipment",
                                 "Capital Expenditures")
            if op_a:
                cap_v = cap_a[0] if cap_a else 0.0
                fcf_ttm = op_a[0] + cap_v
                result["data_source"] = "annual_latest"

        result["fcf_ttm"] = fcf_ttm

        # ② FCFマージン（TTM売上との比率）
        rev_ttm = None
        if q_financials is not None and hasattr(q_financials, "empty") and not q_financials.empty:
            rev_ttm = _ttm_sum(q_financials, "Total Revenue", "Revenue", "Net Revenue")
        if rev_ttm is None and financials is not None and hasattr(financials, "empty") and not financials.empty:
            revs = _annual_list(financials, "Total Revenue", "Revenue", "Net Revenue")
            rev_ttm = revs[0] if revs else None

        if fcf_ttm and rev_ttm and rev_ttm > 0:
            result["fcf_margin"] = fcf_ttm / rev_ttm

        # ③ FCF成長CAGR（年次データで長期トレンドを計算）
        op_hist  = _annual_list(cashflow,
                                "Operating Cash Flow",
                                "Total Cash From Operating Activities",
                                "Cash Flow From Continuing Operating Activities")
        cap_hist = _annual_list(cashflow,
                                "Capital Expenditure",
                                "Purchase Of Property Plant And Equipment",
                                "Capital Expenditures")
        fcf_hist = []
        for i, op_v in enumerate(op_hist):
            cap_v = cap_hist[i] if i < len(cap_hist) else 0.0
            fcf_hist.append(op_v + cap_v)

        result["oe_cagr"] = _cagr(fcf_hist)

        # ④ FCFイールド（時価総額比）
        mc = info.get("marketCap")
        if fcf_ttm and mc and mc > 0:
            result["fcf_yield"] = fcf_ttm / mc

        # ⑤ スコアリング
        s  = 0
        fm = result["fcf_margin"]
        if fm is not None:
            if   fm >= 0.20:                  s += 6
            elif fm >= cfg.fcf_margin_good:   s += 4
            elif fm >= 0.04:                  s += 2

        oe_cagr = result["oe_cagr"]
        if oe_cagr is not None:
            if   oe_cagr >= 0.12:             s += 6
            elif oe_cagr >= cfg.min_oe_cagr:  s += 4
            elif oe_cagr >= 0.02:             s += 2

        fy = result["fcf_yield"]
        if fy is not None:
            if   fy >= 0.06:                  s += 5
            elif fy >= cfg.fcf_yield_good:    s += 3
            elif fy >= 0.02:                  s += 1
        elif fcf_ttm and fcf_ttm > 0:
            s += 3  # 時価総額不明でもFCF正値なら加点

        result["score"] = min(s, 20)

        # ⑥ 詳細テキスト
        src   = "四半期TTM" if result["data_source"] == "quarterly_TTM" else "年次"
        if fcf_ttm:
            fcf_b = f"{fcf_ttm/1e9:.2f}B" if abs(fcf_ttm) >= 1e9 else f"{fcf_ttm/1e6:.0f}M"
        else:
            fcf_b = "—"
        fm_s  = f"{fm*100:.1f}%"        if fm       is not None else "—"
        cg_s  = f"{oe_cagr*100:.1f}%"  if oe_cagr  is not None else "—"
        fy_s  = f"{fy*100:.1f}%"        if fy       is not None else "—"
        result["detail"] = (
            f"FCF {fcf_b} [{src}] | マージン {fm_s} | CAGR(年次) {cg_s} | FCFイールド {fy_s}"
        )

    except Exception as e:
        result["score"]  = 3
        result["detail"] = f"計算エラー: {e}"

    return result
