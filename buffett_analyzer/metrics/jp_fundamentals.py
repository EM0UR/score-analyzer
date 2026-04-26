# jp_fundamentals.py
import pandas as pd

def _safe_row(df, *keys):
    for k in keys:
        if k in df.index:
            return df.loc[k]
    return None

def analyze_jp_fundamentals(financials, cashflow, balance_sheet, info, cfg):
    result = {
        "score": 0, "max_score": 10,
        "pbr": None, "per": None, "dividend_yield_pct": None,
        "buyback_active": False, "detail": ""
    }

    if cfg.name != "JP":
        result["detail"] = "日本株専用モジュール（米国株は対象外）"
        return result

    try:
        # PBR
        pbr = info.get("priceToBook")
        if pbr is None:
            price = info.get("currentPrice") or info.get("previousClose")
            bv    = info.get("bookValue")
            if price and bv and bv > 0:
                pbr = price / bv
        result["pbr"] = pbr

        # PER
        per = info.get("trailingPE") or info.get("forwardPE")
        result["per"] = per

        # 配当利回り
        dy = info.get("dividendYield")
        if dy is None:
            div_rate = info.get("dividendRate") or 0
            price    = info.get("currentPrice") or info.get("previousClose") or 1
            dy = div_rate / price if price else None
        result["dividend_yield_pct"] = dy * 100 if dy else None

        # 自社株買い
        bb_row = _safe_row(cashflow,
            "Repurchase Of Capital Stock",
            "Common Stock Repurchased",
            "Repurchase Of Common Stock")
        buyback = False
        if bb_row is not None:
            buyback = any(v < 0 for v in bb_row.dropna().iloc[:3])
        result["buyback_active"] = buyback

        # スコアリング
        s = 0
        if pbr is not None:
            if   pbr <= 1.0: s += 3
            elif pbr <= 1.5: s += 2
            elif pbr <= 1.9: s += 1
        else:
            s += 1
        if per is not None:
            if   per <= 10.0: s += 3
            elif per <= 16.6: s += 2
            elif per <= 22.0: s += 1
        else:
            s += 1
        dy_val = result["dividend_yield_pct"]
        if dy_val is not None:
            if   dy_val >= 5.0: s += 3
            elif dy_val >= 3.0: s += 2
            elif dy_val >= 1.5: s += 1
        if buyback:
            s += 1

        result["score"] = min(s, 10)
        result["detail"] = (
            f"PBR {pbr:.2f}x" if pbr else "PBR N/A"
        ) + (
            f" | PER {per:.1f}x" if per else ""
        ) + (
            f" | 配当利回り {dy_val:.2f}%" if dy_val else ""
        ) + (
            " | 自社株買い ✅" if buyback else " | 自社株買い —"
        )

    except Exception as e:
        result["score"]  = 2
        result["detail"] = f"計算エラー: {e}"

    return result
