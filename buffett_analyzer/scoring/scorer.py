SCORER_BUILD = "scorer-20260417-2200-phase6"
from dataclasses import dataclass, field
import importlib
import math
import pandas as pd


# ============================================================
# Buffett Score Analyzer v2.2 — Phase 6: confidence & penalties
# - Keeps existing app.py compatibility
# - Adds confidence score, missing-data penalty, and verdict guardrails
# - Preserves legacy module outputs while improving robustness
# ============================================================


import sys
import importlib

def _safe_import(module_path, func_name):
    try:
        if module_path in sys.modules:
            module = importlib.reload(sys.modules[module_path])
        else:
            module = importlib.import_module(module_path)
        return getattr(module, func_name), None
    except Exception as e:
        return None, e


def _safe_call(fn, default_max, *args, **kwargs):
    try:
        out = fn(*args, **kwargs)
        if isinstance(out, dict):
            out.setdefault("score", 0)
            out.setdefault("max_score", default_max)
            out.setdefault("detail", "")
            return out
        return {"score": 0, "max_score": default_max, "detail": "戻り値がdictではありません"}
    except Exception as e:
        return {"score": 0, "max_score": default_max, "detail": f"モジュールエラー: {type(e).__name__}: {e}"}


def _ensure_df(obj):
    return obj if isinstance(obj, pd.DataFrame) else pd.DataFrame()


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


def _norm(raw_score, raw_max):
    s = _to_float(raw_score)
    m = _to_float(raw_max)
    if s is None or m is None or m <= 0:
        return 0.0
    return max(0.0, min(1.0, s / m))


def _score_bracket(v, brackets, default=0.5):
    if v is None:
        return default
    for threshold, score in brackets:
        if v >= threshold:
            return score
    return brackets[-1][1] if brackets else default


def _text(info, *keys):
    for k in keys:
        v = info.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().lower()
    return ""


def _present(v):
    if isinstance(v, pd.DataFrame):
        return not v.empty
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    return True


def _clip(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


# ----------------------------------------------------------------------
# Industry routing
# ----------------------------------------------------------------------
def _industry_profile(info):
    sector = _text(info, "sector")
    industry = _text(info, "industry")
    label = f"{sector} | {industry}".strip(" |")

    bank_words = ["bank", "banks", "credit", "lending", "regional bank", "financial services"]
    insurance_words = ["insurance", "reinsurance", "property & casualty", "life insurance"]
    asset_light_words = ["software", "consumer electronics", "payments", "credit services", "internet", "media", "branded", "beverages", "household", "personal products"]
    capital_intensive_words = ["airline", "aerospace", "auto", "automobile", "manufacturing", "industrial", "chemical", "telecom", "utility", "railroad", "energy", "semiconductor", "hardware", "steel", "shipping", "construction"]

    joined = f"{sector} {industry}"

    def has_any(words):
        return any(w in joined for w in words)

    if has_any(bank_words):
        return "bank", label
    if has_any(insurance_words):
        return "insurance", label
    if has_any(capital_intensive_words):
        return "capital_intensive", label
    if has_any(asset_light_words):
        return "asset_light", label
    return "general", label


# ----------------------------------------------------------------------
# Common feature scores
# ----------------------------------------------------------------------
def _score_margin_profile(info, profile="general"):
    gm = _pct_to_unit(info.get("grossMargins"))
    om = _pct_to_unit(info.get("operatingMargins"))

    if profile == "asset_light":
        gm_brackets = [(0.65, 1.00), (0.50, 0.88), (0.35, 0.65), (0.20, 0.35)]
        om_brackets = [(0.28, 1.00), (0.20, 0.85), (0.12, 0.60), (0.06, 0.35)]
    elif profile == "capital_intensive":
        gm_brackets = [(0.40, 1.00), (0.28, 0.82), (0.18, 0.58), (0.08, 0.30)]
        om_brackets = [(0.18, 1.00), (0.12, 0.82), (0.08, 0.60), (0.04, 0.35)]
    else:
        gm_brackets = [(0.55, 1.00), (0.40, 0.85), (0.25, 0.55), (0.10, 0.25)]
        om_brackets = [(0.25, 1.00), (0.18, 0.82), (0.10, 0.55), (0.05, 0.30)]

    gm_score = _score_bracket(gm, gm_brackets, default=0.50)
    om_score = _score_bracket(om, om_brackets, default=0.50)
    return (gm_score + om_score) / 2.0, gm, om


def _score_de(info, profile="general"):
    de = _to_float(info.get("debtToEquity"))
    if de is not None and de > 3:
        de = de / 100.0

    if de is None:
        return 0.50, None

    if profile == "capital_intensive":
        if de <= 0.60: return 1.00, de
        if de <= 1.00: return 0.80, de
        if de <= 1.80: return 0.55, de
        if de <= 2.50: return 0.30, de
        return 0.10, de

    if de <= 0.30: return 1.00, de
    if de <= 0.60: return 0.80, de
    if de <= 1.00: return 0.55, de
    if de <= 2.00: return 0.30, de
    return 0.10, de


def _score_current_ratio(info, profile="general"):
    cr = _to_float(info.get("currentRatio"))
    if cr is None:
        return 0.50, None

    if profile == "bank":
        return 0.50, cr
    if profile == "insurance":
        if cr >= 1.2: return 0.75, cr
        if cr >= 1.0: return 0.60, cr
        return 0.40, cr

    if cr >= 2.0: return 1.00, cr
    if cr >= 1.5: return 0.80, cr
    if cr >= 1.0: return 0.55, cr
    return 0.20, cr


def _score_roe_profile(info, profile="general"):
    roe = _pct_to_unit(info.get("returnOnEquity"))
    if roe is None:
        return 0.50, None

    if profile == "bank":
        if roe >= 0.16: return 1.00, roe
        if roe >= 0.12: return 0.82, roe
        if roe >= 0.09: return 0.60, roe
        if roe >= 0.06: return 0.35, roe
        return 0.15, roe

    if profile == "insurance":
        if roe >= 0.14: return 1.00, roe
        if roe >= 0.10: return 0.82, roe
        if roe >= 0.08: return 0.60, roe
        if roe >= 0.05: return 0.35, roe
        return 0.15, roe

    if profile == "capital_intensive":
        if roe >= 0.18: return 1.00, roe
        if roe >= 0.13: return 0.82, roe
        if roe >= 0.09: return 0.60, roe
        if roe >= 0.06: return 0.35, roe
        return 0.15, roe

    if roe >= 0.20: return 1.00, roe
    if roe >= 0.15: return 0.85, roe
    if roe >= 0.10: return 0.60, roe
    if roe >= 0.06: return 0.35, roe
    return 0.15, roe


def _score_roa_profile(info, profile="general"):
    roa = _pct_to_unit(info.get("returnOnAssets"))
    if roa is None:
        return 0.50, None

    if profile == "bank":
        if roa >= 0.015: return 1.00, roa
        if roa >= 0.010: return 0.80, roa
        if roa >= 0.006: return 0.55, roa
        return 0.25, roa

    if profile == "insurance":
        if roa >= 0.040: return 1.00, roa
        if roa >= 0.025: return 0.80, roa
        if roa >= 0.015: return 0.55, roa
        return 0.25, roa

    if roa >= 0.10: return 1.00, roa
    if roa >= 0.06: return 0.80, roa
    if roa >= 0.03: return 0.55, roa
    return 0.25, roa


def _score_cash_liquidity(info):
    cash = _to_float(info.get("totalCash"))
    debt = _to_float(info.get("totalDebt"))
    if cash is None or debt is None or debt <= 0:
        return 0.50, cash, debt
    ratio = cash / debt
    if ratio >= 1.00: return 1.00, cash, debt
    if ratio >= 0.60: return 0.80, cash, debt
    if ratio >= 0.30: return 0.55, cash, debt
    return 0.25, cash, debt


def _score_pe_profile(info, profile="general"):
    pe = _to_float(info.get("trailingPE") or info.get("forwardPE"))
    if pe is None or pe <= 0:
        return 0.50, None

    if profile in ("bank", "insurance"):
        if pe <= 10: return 1.00, pe
        if pe <= 13: return 0.82, pe
        if pe <= 17: return 0.58, pe
        if pe <= 22: return 0.35, pe
        return 0.15, pe

    if profile == "asset_light":
        if pe <= 18: return 1.00, pe
        if pe <= 24: return 0.80, pe
        if pe <= 32: return 0.58, pe
        if pe <= 40: return 0.35, pe
        return 0.18, pe

    if pe <= 14: return 1.00, pe
    if pe <= 20: return 0.80, pe
    if pe <= 28: return 0.58, pe
    if pe <= 35: return 0.35, pe
    return 0.18, pe


def _score_pb_profile(info, profile="general"):
    pb = _to_float(info.get("priceToBook"))
    if pb is None or pb <= 0:
        return 0.50, None

    if profile == "bank":
        if pb <= 1.0: return 1.00, pb
        if pb <= 1.3: return 0.82, pb
        if pb <= 1.8: return 0.58, pb
        if pb <= 2.3: return 0.35, pb
        return 0.15, pb

    if profile == "insurance":
        if pb <= 1.2: return 1.00, pb
        if pb <= 1.6: return 0.82, pb
        if pb <= 2.1: return 0.58, pb
        if pb <= 2.7: return 0.35, pb
        return 0.15, pb

    return 0.50, pb


def _score_mos_overlay(valuation_mod):
    mos = _to_float((valuation_mod or {}).get("margin_of_safety_dcf"))
    if mos is None:
        return 0.45, None
    if mos >= 40: return 1.00, mos
    if mos >= 25: return 0.85, mos
    if mos >= 15: return 0.70, mos
    if mos >= 5: return 0.55, mos
    if mos >= -10: return 0.35, mos
    return 0.10, mos


def _fallback_health(financials, balance_sheet, cashflow, info, cfg, **kwargs):
    result = {
        "score": 0,
        "max_score": 15,
        "de_ratio": None,
        "equity_ratio": None,
        "interest_coverage": None,
        "current_ratio": None,
        "data_source": "fallback",
        "detail": "fallback health"
    }

    de = _to_float(info.get("debtToEquity"))
    if de is not None and de > 3:
        de = de / 100.0
    cr = _to_float(info.get("currentRatio"))

    score = 0
    if de is not None:
        result["de_ratio"] = de
        if de <= getattr(cfg, "de_max_excellent", 0.3):
            score += 6
        elif de <= getattr(cfg, "de_max_good", 0.6):
            score += 4
        elif de <= getattr(cfg, "de_max_ok", 1.0):
            score += 2
    if cr is not None:
        result["current_ratio"] = cr
        if cr >= 2.0:
            score += 3
        elif cr >= 1.5:
            score += 2
        elif cr >= 1.0:
            score += 1

    result["score"] = min(15, score)
    result["detail"] = f"D/E={de if de is not None else '—'} | CR={cr if cr is not None else '—'}"
    return result


def _extract_penalty_context(info, valuation_mod, fetched):
    ctx = {
        "has_history": _present((fetched or {}).get("history")),
        "has_current_price": _present(info.get("currentPrice") or info.get("previousClose")),
        "has_market_cap": _present(info.get("marketCap")),
        "has_name": _present(info.get("longName") or info.get("shortName")),
        "has_sector": _present(info.get("sector") or info.get("industry")),
        "has_gross_margin": _present(info.get("grossMargins")),
        "has_operating_margin": _present(info.get("operatingMargins")),
        "has_roe": _present(info.get("returnOnEquity")),
        "has_roa": _present(info.get("returnOnAssets")),
        "has_de": _present(info.get("debtToEquity")),
        "has_current_ratio": _present(info.get("currentRatio")),
        "has_cash": _present(info.get("totalCash")),
        "has_debt": _present(info.get("totalDebt")),
        "has_pe": _present(info.get("trailingPE") or info.get("forwardPE")),
        "has_pb": _present(info.get("priceToBook")),
        "has_intrinsic": _present((valuation_mod or {}).get("intrinsic_value_dcf")),
        "has_mos": _present((valuation_mod or {}).get("margin_of_safety_dcf")),
        "fetch_error": (fetched or {}).get("_fetch_error") if isinstance(fetched, dict) else None,
    }
    return ctx


def _compute_confidence_and_penalty(info, valuation_mod, fetched, profile):
    ctx = _extract_penalty_context(info, valuation_mod, fetched)
    weighted_checks = [
        ("has_history", 0.12, "price history missing"),
        ("has_current_price", 0.10, "current price missing"),
        ("has_market_cap", 0.06, "market cap missing"),
        ("has_name", 0.03, "company name missing"),
        ("has_sector", 0.04, "sector/industry missing"),
        ("has_gross_margin", 0.06, "gross margin missing"),
        ("has_operating_margin", 0.05, "operating margin missing"),
        ("has_roe", 0.10, "ROE missing"),
        ("has_roa", 0.07, "ROA missing"),
        ("has_de", 0.08, "debt/equity missing"),
        ("has_current_ratio", 0.05, "current ratio missing"),
        ("has_cash", 0.04, "cash missing"),
        ("has_debt", 0.04, "debt missing"),
        ("has_pe", 0.05, "PE missing"),
        ("has_pb", 0.03, "P/B missing"),
        ("has_intrinsic", 0.04, "intrinsic value missing"),
        ("has_mos", 0.04, "margin of safety missing"),
    ]

    if profile in ("bank", "insurance"):
        weighted_checks = [c for c in weighted_checks if c[0] != "has_gross_margin"]
        weighted_checks.append(("has_pb", 0.05, "P/B missing"))
        weighted_checks.append(("has_roa", 0.09, "ROA missing"))

    total_weight = sum(w for _, w, _ in weighted_checks) or 1.0
    confidence = 0.0
    missing_fields = []
    for key, w, msg in weighted_checks:
        if ctx.get(key):
            confidence += w
        else:
            missing_fields.append(msg)
    confidence = _clip(confidence / total_weight)

    penalty = 0
    penalty_reasons = []

    major_missing = []
    for key, _, msg in weighted_checks:
        if not ctx.get(key):
            major_missing.append(msg)

    if not ctx.get("has_current_price"):
        penalty += 6
        penalty_reasons.append("current price missing (-6)")
    if not ctx.get("has_history"):
        penalty += 5
        penalty_reasons.append("price history missing (-5)")
    if not ctx.get("has_roe"):
        penalty += 5
        penalty_reasons.append("ROE missing (-5)")
    if not ctx.get("has_de"):
        penalty += 4
        penalty_reasons.append("debt/equity missing (-4)")
    if not ctx.get("has_intrinsic"):
        penalty += 6
        penalty_reasons.append("intrinsic value missing (-6)")
    if not ctx.get("has_mos"):
        penalty += 4
        penalty_reasons.append("margin of safety missing (-4)")
    if ctx.get("fetch_error"):
        penalty += 3
        penalty_reasons.append("partial fetch error (-3)")

    if profile in ("bank", "insurance") and not ctx.get("has_pb"):
        penalty += 3
        penalty_reasons.append("financial profile without P/B (-3)")

    if confidence < 0.80:
        penalty += 3
        penalty_reasons.append("confidence below 0.80 (-3)")
    if confidence < 0.65:
        penalty += 5
        penalty_reasons.append("confidence below 0.65 (-5)")
    if confidence < 0.50:
        penalty += 8
        penalty_reasons.append("confidence below 0.50 (-8)")

    penalty = min(20, penalty)
    return {
        "confidence": round(confidence, 3),
        "penalty": penalty,
        "missing_fields": major_missing,
        "penalty_reasons": penalty_reasons,
        "is_low_confidence": confidence < 0.65,
        "is_very_low_confidence": confidence < 0.50,
        "fetch_error": ctx.get("fetch_error"),
        "context": ctx,
    }


@dataclass
class ScoreBreakdown:
    earnings: dict = field(default_factory=dict)
    capital: dict = field(default_factory=dict)
    health: dict = field(default_factory=dict)
    oe: dict = field(default_factory=dict)
    moat: dict = field(default_factory=dict)
    valuation: dict = field(default_factory=dict)
    management: dict = field(default_factory=dict)
    jp_fundamentals: dict = field(default_factory=dict)

    quality_block: dict = field(default_factory=dict)
    capital_block: dict = field(default_factory=dict)
    resilience_block: dict = field(default_factory=dict)
    price_block: dict = field(default_factory=dict)
    audit: dict = field(default_factory=dict)

    @property
    def max_score(self):
        return 100

    @property
    def raw_total(self):
        return float(
            self.quality_block.get("score", 0)
            + self.capital_block.get("score", 0)
            + self.resilience_block.get("score", 0)
            + self.price_block.get("score", 0)
        )

    @property
    def penalty(self):
        return int((self.audit or {}).get("missing_data_penalty", 0) or 0)

    @property
    def confidence(self):
        return float((self.audit or {}).get("confidence", 0.0) or 0.0)

    @property
    def total(self):
        return int(round(max(0.0, self.raw_total - self.penalty)))

    @property
    def legacy_total(self):
        return (
            self.earnings.get("score", 0)
            + self.capital.get("score", 0)
            + self.health.get("score", 0)
            + self.oe.get("score", 0)
            + self.moat.get("score", 0)
            + self.valuation.get("score", 0)
            + self.management.get("score", 0)
            + self.jp_fundamentals.get("score", 0)
        )

    @property
    def verdict_en(self):
        pct = self.total / self.max_score * 100 if self.max_score else 0
        if pct >= 82:
            verdict = "STRONG BUY"
        elif pct >= 65:
            verdict = "BUY"
        elif pct >= 48:
            verdict = "WATCH"
        else:
            verdict = "AVOID"

        q = self.quality_block.get("score", 0)
        r = self.resilience_block.get("score", 0)
        p = self.price_block.get("score", 0)
        profile = (self.audit or {}).get("profile")
        confidence = self.confidence

        if q < 18:
            verdict = "AVOID"
        elif q < 22 and verdict in ("STRONG BUY", "BUY"):
            verdict = "WATCH"
        elif r < 8 and verdict in ("STRONG BUY", "BUY"):
            verdict = "WATCH"
        elif p < 4 and verdict == "STRONG BUY":
            verdict = "BUY"

        if profile in ("bank", "insurance") and r < 10 and verdict in ("STRONG BUY", "BUY"):
            verdict = "WATCH"

        if confidence < 0.50:
            verdict = "AVOID"
        elif confidence < 0.65 and verdict in ("STRONG BUY", "BUY"):
            verdict = "WATCH"
        elif confidence < 0.80 and verdict == "STRONG BUY":
            verdict = "BUY"

        return verdict

    @property
    def verdict(self):
        return {
            "STRONG BUY": "強い買い 🟢",
            "BUY": "買い 🔵",
            "WATCH": "様子見 🟡",
            "AVOID": "非推奨 🔴",
        }.get(self.verdict_en, "—")

    def verdict_comment(self):
        mos = _to_float(self.valuation.get("margin_of_safety_dcf"))
        mos_str = f"{mos:.1f}%" if mos is not None else "不明"
        q = self.quality_block.get("score", 0)
        c = self.capital_block.get("score", 0)
        r = self.resilience_block.get("score", 0)
        p = self.price_block.get("score", 0)
        profile = (self.audit or {}).get("profile_label", "general")
        confidence = self.confidence
        penalty = self.penalty

        parts = [
            f"業種プロファイル {profile}",
            f"事業の質 {q:.0f}/40",
            f"資本配分 {c:.0f}/25",
            f"財務耐性 {r:.0f}/20",
            f"価格 {p:.0f}/15",
            f"MoS {mos_str}",
            f"Confidence {confidence:.2f}",
            f"Penalty -{penalty}",
        ]

        v = self.verdict_en
        if confidence < 0.50:
            prefix = "データ欠損が大きく、判定の信頼性が低いため見送り優先です。"
        elif v == "STRONG BUY":
            prefix = "高品質企業を保守的価格で見られる水準です。"
        elif v == "BUY":
            prefix = "質は十分で、価格もおおむね許容範囲です。"
        elif v == "WATCH":
            prefix = "企業の質か価格、またはデータ信頼性に改善余地があります。"
        else:
            prefix = "バフェット基準では見送り優先です。"

        return prefix + " / " + " | ".join(parts)


# ----------------------------------------------------------------------
# Profile-specific blocks
# ----------------------------------------------------------------------
def _build_quality_block(bd, info, profile):
    earnings_norm = _norm(bd.earnings.get("score", 0), bd.earnings.get("max_score", 20))
    moat_norm = _norm(bd.moat.get("score", 0), bd.moat.get("max_score", 15))
    margin_norm, gm, om = _score_margin_profile(info, profile)
    roe_norm, roe = _score_roe_profile(info, profile)
    roa_norm, roa = _score_roa_profile(info, profile)

    if profile == "bank":
        raw = 0.25 * earnings_norm + 0.15 * moat_norm + 0.35 * roe_norm + 0.25 * roa_norm
    elif profile == "insurance":
        raw = 0.25 * earnings_norm + 0.20 * moat_norm + 0.25 * roe_norm + 0.30 * roa_norm
    elif profile == "asset_light":
        raw = 0.30 * earnings_norm + 0.30 * moat_norm + 0.25 * margin_norm + 0.15 * roe_norm
    elif profile == "capital_intensive":
        raw = 0.30 * earnings_norm + 0.20 * moat_norm + 0.20 * margin_norm + 0.30 * roe_norm
    else:
        raw = 0.35 * earnings_norm + 0.30 * moat_norm + 0.20 * margin_norm + 0.15 * roe_norm

    score = round(raw * 40, 1)
    detail = f"profile={profile}, earn={earnings_norm:.2f}, moat={moat_norm:.2f}, margin={margin_norm:.2f}, roe={roe}, roa={roa}, gross={gm}, op={om}"
    return {"score": score, "max_score": 40, "detail": detail}


def _build_capital_block(bd, info, profile):
    capital_norm = _norm(bd.capital.get("score", 0), bd.capital.get("max_score", 20))
    oe_norm = _norm(bd.oe.get("score", 0), bd.oe.get("max_score", 20))
    mgmt_norm = _norm(bd.management.get("score", 0), bd.management.get("max_score", 10))
    roe_norm, roe = _score_roe_profile(info, profile)

    if profile == "bank":
        raw = 0.25 * capital_norm + 0.20 * oe_norm + 0.25 * mgmt_norm + 0.30 * roe_norm
    elif profile == "insurance":
        raw = 0.20 * capital_norm + 0.20 * oe_norm + 0.25 * mgmt_norm + 0.35 * roe_norm
    elif profile == "capital_intensive":
        raw = 0.35 * capital_norm + 0.25 * oe_norm + 0.20 * mgmt_norm + 0.20 * roe_norm
    else:
        raw = 0.40 * capital_norm + 0.30 * oe_norm + 0.20 * mgmt_norm + 0.10 * roe_norm

    score = round(raw * 25, 1)
    detail = f"profile={profile}, capital={capital_norm:.2f}, oe={oe_norm:.2f}, mgmt={mgmt_norm:.2f}, roe={roe}"
    return {"score": score, "max_score": 25, "detail": detail}


def _build_resilience_block(bd, info, profile):
    health_norm = _norm(bd.health.get("score", 0), bd.health.get("max_score", 15))
    de_score, de = _score_de(info, profile)
    cr_score, cr = _score_current_ratio(info, profile)
    cash_score, cash, debt = _score_cash_liquidity(info)
    roa_norm, roa = _score_roa_profile(info, profile)

    if profile == "bank":
        raw = 0.35 * health_norm + 0.35 * roa_norm + 0.15 * cash_score + 0.15 * cr_score
    elif profile == "insurance":
        raw = 0.35 * health_norm + 0.30 * roa_norm + 0.20 * cash_score + 0.15 * cr_score
    elif profile == "capital_intensive":
        raw = 0.45 * health_norm + 0.25 * de_score + 0.15 * cr_score + 0.15 * cash_score
    else:
        raw = 0.45 * health_norm + 0.25 * de_score + 0.15 * cr_score + 0.15 * cash_score

    score = round(raw * 20, 1)
    detail = f"profile={profile}, health={health_norm:.2f}, de={de}, cr={cr}, cash={cash}, debt={debt}, roa={roa}"
    return {"score": score, "max_score": 20, "detail": detail}


def _build_price_block(bd, info, profile):
    valuation_norm = _norm(bd.valuation.get("score", 0), bd.valuation.get("max_score", 10))
    mos_norm, mos = _score_mos_overlay(bd.valuation)
    pe_norm, pe = _score_pe_profile(info, profile)
    pb_norm, pb = _score_pb_profile(info, profile)

    if profile == "bank":
        raw = 0.30 * valuation_norm + 0.25 * mos_norm + 0.20 * pe_norm + 0.25 * pb_norm
    elif profile == "insurance":
        raw = 0.35 * valuation_norm + 0.25 * mos_norm + 0.20 * pe_norm + 0.20 * pb_norm
    elif profile == "asset_light":
        raw = 0.55 * valuation_norm + 0.25 * mos_norm + 0.20 * pe_norm
    else:
        raw = 0.55 * valuation_norm + 0.30 * mos_norm + 0.15 * pe_norm

    score = round(raw * 15, 1)
    detail = f"profile={profile}, valuation={valuation_norm:.2f}, mos={mos}, pe={pe}, pb={pb}"
    return {"score": score, "max_score": 15, "detail": detail}


def run_all_modules(fetched, ticker, cfg):
    fetched = fetched or {}
    info = fetched.get("info") if isinstance(fetched, dict) else {}
    info = info if isinstance(info, dict) else {}
    financials = _ensure_df((fetched or {}).get("financials"))
    balance_sheet = _ensure_df((fetched or {}).get("balance_sheet"))
    cashflow = _ensure_df((fetched or {}).get("cashflow"))

    bd = ScoreBreakdown()

    earnings_fn, earnings_err = _safe_import("buffett_analyzer.metrics.earnings", "analyze_earnings_consistency")
    capital_fn, capital_err = _safe_import("buffett_analyzer.metrics.capital_efficiency", "analyze_capital_efficiency")
    health_fn, health_err = _safe_import("buffett_analyzer.metrics.financial_health", "analyze_financial_health")
    oe_fn, oe_err = _safe_import("buffett_analyzer.metrics.owner_earnings", "analyze_owner_earnings")
    moat_fn, moat_err = _safe_import("buffett_analyzer.metrics.moat", "analyze_moat")
    valuation_fn, valuation_err = _safe_import("buffett_analyzer.metrics.valuation", "analyze_valuation")
    management_fn, management_err = _safe_import("buffett_analyzer.metrics.management", "analyze_management")
    jp_fn, jp_err = _safe_import("buffett_analyzer.metrics.jp_fundamentals", "analyze_jp_fundamentals")

    bd.earnings = _safe_call(earnings_fn, 20, financials, info, cfg) if earnings_fn else {
        "score": 0, "max_score": 20, "detail": f"import error: {earnings_err}"
    }
    bd.capital = _safe_call(capital_fn, 20, financials, info, cfg) if capital_fn else {
        "score": 0, "max_score": 20, "detail": f"import error: {capital_err}"
    }
    bd.health = _safe_call(health_fn, 15, financials, balance_sheet, cashflow, info, cfg) if health_fn else _fallback_health(financials, balance_sheet, cashflow, info, cfg)
    bd.oe = _safe_call(oe_fn, 20, cashflow, info, cfg) if oe_fn else {
        "score": 0, "max_score": 20, "detail": f"import error: {oe_err}"
    }
    bd.moat = _safe_call(moat_fn, 15, financials, info, cfg) if moat_fn else {
        "score": 0, "max_score": 15, "detail": f"import error: {moat_err}"
    }
    bd.valuation = _safe_call(
        valuation_fn, 10,
        financials, cashflow, balance_sheet, info, bd.oe, cfg
    ) if valuation_fn else {
        "score": 0, "max_score": 10, "detail": f"import error: {valuation_err}"
    }

    bd.management = _safe_call(management_fn, 10, financials, cashflow, info, cfg) if management_fn else {
        "score": 0, "max_score": 10, "detail": f"import error: {management_err}"
    }

    market_name = getattr(cfg, "market", getattr(cfg, "name", ""))
    is_jp = str(market_name).lower() == "jp" or str(ticker).upper().endswith('.T')
    if is_jp:
        bd.jp_fundamentals = _safe_call(jp_fn, 10, info, cfg) if jp_fn else {
            "score": 0, "max_score": 10, "detail": f"import error: {jp_err}"
        }
    else:
        bd.jp_fundamentals = {"score": 0, "max_score": 10, "detail": "not applicable"}

    profile, profile_label = _industry_profile(info)
    bd.quality_block = _build_quality_block(bd, info, profile)
    bd.capital_block = _build_capital_block(bd, info, profile)
    bd.resilience_block = _build_resilience_block(bd, info, profile)
    bd.price_block = _build_price_block(bd, info, profile)

    cp = _compute_confidence_and_penalty(info, bd.valuation, fetched, profile)
    bd.audit = {
        "framework": "phase6-confidence-penalty",
        "profile": profile,
        "profile_label": profile_label,
        "headline_total": bd.total,
        "headline_raw_total": round(bd.raw_total, 1),
        "legacy_total": round(bd.legacy_total, 1),
        "confidence": cp["confidence"],
        "missing_data_penalty": cp["penalty"],
        "missing_fields": cp["missing_fields"],
        "penalty_reasons": cp["penalty_reasons"],
        "is_low_confidence": cp["is_low_confidence"],
        "is_very_low_confidence": cp["is_very_low_confidence"],
        "fetch_error": cp["fetch_error"],
        "data_presence": cp["context"],
        "module_imports": {
            "earnings": None if earnings_fn else str(earnings_err),
            "capital": None if capital_fn else str(capital_err),
            "health": None if health_fn else str(health_err),
            "owner_earnings": None if oe_fn else str(oe_err),
            "moat": None if moat_fn else str(moat_err),
            "valuation": None if valuation_fn else str(valuation_err),
            "management": None if management_fn else str(management_err),
            "jp_fundamentals": None if jp_fn else str(jp_err),
        },
    }
    return bd
