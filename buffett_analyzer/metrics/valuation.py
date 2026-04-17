VALUATION_BUILD = "valuation-20260417-2200-fixed"
import math
import pandas as pd


def _to_float(x):
    try:
        if x is None or isinstance(x, bool):
            return None
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def _pct_to_unit(v):
    v = _to_float(v)
    if v is None:
        return None
    return v / 100.0 if v > 1.5 else v


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _pick(*values):
    for v in values:
        fv = _to_float(v)
        if fv is not None:
            return fv
    return None


def _cfg_value(cfg, *names, default=None):
    for name in names:
        if hasattr(cfg, name):
            v = _to_float(getattr(cfg, name))
            if v is not None:
                return v
    return default


def _is_jp(info, cfg):
    c = str(info.get("currency") or "").upper()
    if c == "JPY":
        return True
    if hasattr(cfg, "currency_symbol") and getattr(cfg, "currency_symbol") == "¥":
        return True
    return False


def _price(info):
    return _pick(info.get("currentPrice"), info.get("previousClose"), info.get("regularMarketPrice"))


def _eps(info):
    return _pick(info.get("trailingEps"), info.get("forwardEps"))


def _pe(info, price=None):
    price = _pick(price, _price(info))
    pe = _pick(info.get("trailingPE"), info.get("forwardPE"))
    if pe is not None and pe > 0:
        return pe
    eps = _eps(info)
    if price is not None and eps is not None and eps > 0:
        return price / eps
    return None


def _book_value_ps(info):
    return _pick(info.get("bookValue"))


def _pb(info, price=None):
    price = _pick(price, _price(info))
    pb = _pick(info.get("priceToBook"))
    if pb is not None and pb > 0:
        return pb
    bvps = _book_value_ps(info)
    if price is not None and bvps is not None and bvps > 0:
        return price / bvps
    return None


def _shares(info, financials=None):
    sh = _pick(info.get("sharesOutstanding"), info.get("impliedSharesOutstanding"))
    if sh is not None and sh > 0:
        return sh
    return None


def _series_value(df, labels):
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    for label in labels:
        if label in df.index:
            row = df.loc[label]
            if isinstance(row, pd.Series):
                vals = row.dropna().tolist()
                for v in vals:
                    fv = _to_float(v)
                    if fv is not None:
                        return fv
            else:
                fv = _to_float(row)
                if fv is not None:
                    return fv
    return None


def _derive_fcf_per_share(cashflow, info):
    sh = _shares(info)
    if sh is None or sh <= 0:
        return None

    info_fcf = _pick(info.get("freeCashflow"))
    if info_fcf is not None and info_fcf > 0:
        return info_fcf / sh

    op_cf = _series_value(cashflow, [
        "Operating Cash Flow",
        "Total Cash From Operating Activities",
        "Cash Flow From Continuing Operating Activities",
    ])
    capex = _series_value(cashflow, [
        "Capital Expenditure",
        "Capital Expenditures",
    ])

    if op_cf is None:
        return None

    if capex is None:
        fcf = op_cf
    else:
        fcf = op_cf - abs(capex)

    if fcf is None or fcf <= 0:
        return None
    return fcf / sh


def _owner_earnings_per_share(oe, cashflow, info):
    if isinstance(oe, dict):
        for key in [
            "owner_earnings_per_share",
            "oe_per_share",
            "fcf_per_share",
            "normalized_oe_per_share",
            "normalized_fcf_per_share",
        ]:
            v = _pick(oe.get(key))
            if v is not None and v > 0:
                return v, key

    derived = _derive_fcf_per_share(cashflow, info)
    if derived is not None and derived > 0:
        return derived, "derived_fcf_per_share"

    return None, None


def _base_growth(info, oe):
    candidates = []

    if isinstance(oe, dict):
        for key in [
            "growth_rate",
            "oe_growth_rate",
            "owner_earnings_growth",
            "fcf_growth_rate",
            "normalized_growth_rate",
        ]:
            v = _pct_to_unit(oe.get(key))
            if v is not None:
                candidates.append(v)

    for key in ["earningsGrowth", "revenueGrowth", "earningsQuarterlyGrowth"]:
        v = _pct_to_unit(info.get(key))
        if v is not None:
            candidates.append(v)

    if candidates:
        arr = sorted(candidates)
        g = arr[len(arr) // 2]
        return _clamp(g, 0.00, 0.16)

    return None


def _discount_rate(info, cfg):
    base = _cfg_value(cfg, "discount_rate", "discountRate", "required_return", default=None)
    if base is not None:
        return _clamp(base, 0.05, 0.15)
    return 0.07 if _is_jp(info, cfg) else 0.10


def _terminal_growth(info, cfg):
    base = _cfg_value(cfg, "terminal_growth", "terminalGrowth", "g_terminal", default=None)
    if base is not None:
        return _clamp(base, 0.005, 0.04)
    return 0.015 if _is_jp(info, cfg) else 0.025


def _scenario_assumptions(info, oe, cfg):
    g = _base_growth(info, oe)
    r = _discount_rate(info, cfg)
    tg = _terminal_growth(info, cfg)

    if g is None:
        g = 0.03 if _is_jp(info, cfg) else 0.06

    base_g = _clamp(g, 0.00, 0.14)
    base_r = _clamp(r, max(tg + 0.03, 0.05), 0.15)
    base_tg = _clamp(tg, 0.005, min(0.04, base_r - 0.02))

    bear = {
        "growth": _clamp(base_g - 0.03, 0.00, 0.12),
        "discount": _clamp(base_r + 0.02, 0.06, 0.18),
        "terminal": _clamp(min(base_tg, max(0.005, base_tg - 0.005)), 0.005, 0.03),
    }
    base = {
        "growth": base_g,
        "discount": base_r,
        "terminal": base_tg,
    }
    bull = {
        "growth": _clamp(base_g + 0.02, 0.01, 0.18),
        "discount": _clamp(base_r - 0.01, max(base_tg + 0.02, 0.05), 0.14),
        "terminal": _clamp(base_tg + 0.005, 0.01, 0.04),
    }

    return {"bear": bear, "base": base, "bull": bull}


def _dcf_per_share(oe_ps, growth, discount, terminal, years=10):
    if oe_ps is None or oe_ps <= 0:
        return None
    if discount <= terminal:
        return None

    pv = 0.0
    cash = oe_ps
    for y in range(1, years + 1):
        cash = cash * (1.0 + growth)
        pv += cash / ((1.0 + discount) ** y)

    terminal_cash = cash * (1.0 + terminal)
    terminal_value = terminal_cash / (discount - terminal)
    pv += terminal_value / ((1.0 + discount) ** years)
    return pv


def _score_mos(mos):
    if mos is None:
        return 3
    if mos >= 40: return 8
    if mos >= 25: return 7
    if mos >= 15: return 6
    if mos >= 5: return 5
    if mos >= -10: return 3
    return 1


def _score_pe(pe, is_financial=False):
    if pe is None or pe <= 0:
        return 2
    if is_financial:
        if pe <= 10: return 2
        if pe <= 13: return 1.5
        if pe <= 17: return 1.0
        return 0.5
    if pe <= 15: return 2
    if pe <= 22: return 1.5
    if pe <= 30: return 1.0
    return 0.5


def _fmt(v):
    return f"{v:.2f}" if v is not None else "—"


def analyze_valuation(financials, cashflow, balance_sheet, info, oe, cfg):
    price = _price(info)
    pe_ratio = _pe(info, price)
    pb_ratio = _pb(info, price)

    provider_intrinsic = _pick(info.get("providerDcfIntrinsic"))
    provider_bear = _pick(info.get("providerDcfBear"))
    provider_base = _pick(info.get("providerDcfBase"))
    provider_bull = _pick(info.get("providerDcfBull"))
    provider_mos = _pick(info.get("providerMarginOfSafety"))

    oe_ps, oe_source = _owner_earnings_per_share(oe, cashflow, info)
    scenarios = _scenario_assumptions(info, oe, cfg)

    bear_val = _dcf_per_share(oe_ps, scenarios["bear"]["growth"], scenarios["bear"]["discount"], scenarios["bear"]["terminal"])
    base_val = _dcf_per_share(oe_ps, scenarios["base"]["growth"], scenarios["base"]["discount"], scenarios["base"]["terminal"])
    bull_val = _dcf_per_share(oe_ps, scenarios["bull"]["growth"], scenarios["bull"]["discount"], scenarios["bull"]["terminal"])

    if bear_val is None:
        bear_val = provider_bear
    if base_val is None:
        base_val = provider_base or provider_intrinsic
    if bull_val is None:
        bull_val = provider_bull

    scenario_values = [v for v in [bear_val, base_val, bull_val] if v is not None]
    conservative_value = None
    weighted_value = None

    if scenario_values:
        conservative_value = min(scenario_values)

        weights = []
        vals = []
        for _, weight, val in [("bear", 0.50, bear_val), ("base", 0.35, base_val), ("bull", 0.15, bull_val)]:
            if val is not None:
                weights.append(weight)
                vals.append(val * weight)
        if weights:
            weighted_value = sum(vals) / sum(weights)

    intrinsic_value_dcf = conservative_value if conservative_value is not None else weighted_value
    if intrinsic_value_dcf is None:
        intrinsic_value_dcf = provider_intrinsic

    margin_of_safety_dcf = None
    if price is not None and intrinsic_value_dcf is not None and intrinsic_value_dcf > 0:
        margin_of_safety_dcf = (intrinsic_value_dcf / price - 1.0) * 100.0
    elif provider_mos is not None:
        margin_of_safety_dcf = provider_mos

    is_fin = any(s in str(info.get("sector") or "").lower() for s in ["financial"]) or any(
        s in str(info.get("industry") or "").lower() for s in ["bank", "insurance"]
    )

    score = 0
    score += _score_mos(margin_of_safety_dcf)
    score += _score_pe(pe_ratio, is_financial=is_fin)

    if intrinsic_value_dcf is not None and weighted_value is not None:
        if weighted_value >= intrinsic_value_dcf * 1.10:
            score += 0.5

    score = max(0, min(10, score))

    if margin_of_safety_dcf is not None:
        detail = (
            f"DCF {_fmt(bear_val)} / {_fmt(base_val)} / {_fmt(bull_val)}"
            f" | OEps={_fmt(oe_ps)} ({oe_source or 'n/a'})"
            f" | PE={_fmt(pe_ratio)}"
            f" | PB={_fmt(pb_ratio)}"
            f" | MoS={margin_of_safety_dcf:.1f}%"
        )
    else:
        detail = (
            f"DCF {_fmt(bear_val)} / {_fmt(base_val)} / {_fmt(bull_val)}"
            f" | OEps={_fmt(oe_ps)} ({oe_source or 'n/a'})"
            f" | PE={_fmt(pe_ratio)}"
            f" | PB={_fmt(pb_ratio)}"
        )

    return {
        "score": score,
        "max_score": 10,
        "detail": detail,
        "price": price,
        "pe_ratio": pe_ratio,
        "pb_ratio": pb_ratio,
        "owner_earnings_per_share_used": oe_ps,
        "owner_earnings_source": oe_source,
        "intrinsic_value_dcf": intrinsic_value_dcf,
        "intrinsic_value_dcf_conservative": conservative_value,
        "intrinsic_value_dcf_weighted": weighted_value,
        "intrinsic_value_dcf_bear": bear_val,
        "intrinsic_value_dcf_base": base_val,
        "intrinsic_value_dcf_bull": bull_val,
        "margin_of_safety_dcf": margin_of_safety_dcf,
        "scenario_assumptions": scenarios,
    }
