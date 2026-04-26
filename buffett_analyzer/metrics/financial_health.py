# financial_health.py
# buffett_analyzer/metrics/financial_health.py
# 依存: なし（標準Pythonのみ）

def analyze_financial_health(financials, balance_sheet, cashflow, info, cfg,
                              q_balance_sheet=None, q_cashflow=None):
    result = {
        "score": 0, "max_score": 15,
        "de_ratio": None, "equity_ratio": None,
        "interest_coverage": None, "current_ratio": None,
        "data_source": "info",
        "detail": ""
    }

    try:
        # ── D/E比率（info から取得）────────────────────────────
        de = None
        raw_de = info.get("debtToEquity")
        if raw_de is not None:
            try:
                de = float(raw_de) / 100.0
                result["data_source"] = "info_ttm"
            except Exception:
                pass

        # DataFrame から補完を試みる（失敗しても続行）
        if de is None:
            try:
                bs = q_balance_sheet if (
                    q_balance_sheet is not None and
                    hasattr(q_balance_sheet, "__len__") and
                    len(q_balance_sheet) > 0
                ) else balance_sheet

                if bs is not None and hasattr(bs, "index") and hasattr(bs, "columns") and len(bs.columns) > 0:
                    eq_keys = ["Stockholders Equity","Total Stockholder Equity",
                               "Common Stock Equity","Total Equity Gross Minority Interest"]
                    debt_keys = ["Total Debt","Net Debt"]
                    eq_val = debt_val = None

                    for k in eq_keys:
                        if k in bs.index:
                            v = bs.loc[k, bs.columns[0]]
                            if v == v and v is not None:  # NaN check
                                eq_val = float(v); break
                    for k in debt_keys:
                        if k in bs.index:
                            v = bs.loc[k, bs.columns[0]]
                            if v == v and v is not None:
                                debt_val = float(v); break

                    if eq_val and debt_val and eq_val > 0:
                        de = debt_val / eq_val
                        result["data_source"] = "bs_latest"
            except Exception:
                pass  # DataFrameアクセス失敗しても続行

        result["de_ratio"] = de

        # ── 流動比率（info から取得）───────────────────────────
        cr = None
        raw_cr = info.get("currentRatio")
        if raw_cr is not None:
            try: cr = float(raw_cr)
            except Exception: pass
        result["current_ratio"] = cr

        # ── 自己資本比率（info から推計）──────────────────────
        er = None
        total_assets = info.get("totalAssets")
        book_value   = info.get("bookValue")
        shares       = info.get("sharesOutstanding")
        if book_value and shares and total_assets and total_assets > 0:
            try:
                eq = float(book_value) * float(shares)
                er = eq / float(total_assets)
            except Exception:
                pass
        result["equity_ratio"] = er

        # ── インタレストカバレッジ（info から取得）─────────────
        ic = None
        raw_ic = info.get("interestCoverage")
        if raw_ic is not None:
            try: ic = float(raw_ic)
            except Exception: pass

        if ic is None:
            ebitda  = info.get("ebitda")
            int_exp = info.get("interestExpense")
            if ebitda and int_exp and int_exp != 0:
                try: ic = float(ebitda) / abs(float(int_exp))
                except Exception: pass
        result["interest_coverage"] = ic

        # ── スコアリング ───────────────────────────────────────
        s = 0

        if de is not None:
            if   de <= cfg.de_max_excellent: s += 6
            elif de <= cfg.de_max_good:      s += 4
            elif de <= cfg.de_max_ok:        s += 2

        if er is not None:
            if   er >= 0.60:                      s += 4
            elif er >= cfg.equity_ratio_good:     s += 3
            elif er >= 0.25:                      s += 1

        if cr is not None:
            if   cr >= 2.0: s += 3
            elif cr >= 1.5: s += 2
            elif cr >= 1.0: s += 1

        if ic is not None:
            if   ic >= 10:                         s += 2
            elif ic >= cfg.interest_coverage_good: s += 1

        result["score"] = min(s, 15)

        # ── 詳細テキスト ──────────────────────────────────────
        src  = result["data_source"]
        de_s = f"D/E {de:.2f}" if de is not None else "D/E —"
        er_s = f"自己資本比率 {er*100:.0f}%" if er is not None else ""
        cr_s = f"流動比率 {cr:.1f}x" if cr is not None else ""
        ic_s = f"IC {ic:.1f}x" if ic is not None else ""
        result["detail"] = f"{de_s} [{src}]"             + (f" | {er_s}" if er_s else "")             + (f" | {cr_s}" if cr_s else "")             + (f" | {ic_s}" if ic_s else "")

    except Exception as e:
        result["score"]  = 2
        result["detail"] = f"計算エラー: {e}"

    return result
