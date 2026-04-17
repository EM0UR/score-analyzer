from dataclasses import dataclass, field
import importlib
import math
import pandas as pd


# ============================================================
# Buffett Score Analyzer v2.0 — Phase 1: score redesign
# Purpose:
# - Keep existing module compatibility for app.py
# - Redesign headline score into 4 Buffett-style blocks
#   1) Business Quality   40
#   2) Capital Allocation 25
#   3) Financial Strength 20
#   4) Price / MoS        15
# - Avoid pandas truthiness errors
# - Add audit data for professional review
# ============================================================


def _safe_import(module_path, func_name):
    try:
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
        if x is None:
            return None
        if isinstance(x, bool):
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
    if v > 1.5:
        return v / 100.0
    return v


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


def _score_margin_profile(info):
    gm = _pct_to_unit(info.get("grossMargins"))
    om = _pct_to_unit(info.get("operatingMargins"))

    gm_score = _score_bracket(gm, [
        (0.55, 1.00),
        (0.40, 0.85),
        (0.25, 0.55),
        (0.10, 0.25),
    ], default=0.50)

    om_score = _score_bracket(om, [
        (0.25, 1.00),
        (0.18, 0.82),
        (0.10, 0.55),
        (0.05, 0.30),
    ], default=0.50)

    return (gm_score + om_score) / 2.0, gm, om


def _score_balance_overlay(info, health_mod):
    de = info.get("debtToEquity")
    de = _to_float(de)
    if de is not None and de > 3:
        de = de / 100.0

    cr = _to_float(info.get("currentRatio"))

    de_score = 0.50
    if de is not None:
        if de <= 0.30:
            de_score = 1.00
        elif de <= 0.60:
            de_score = 0.80
        elif de <= 1.00:
            de_score = 0.55
        elif de <= 2.00:
            de_score = 0.30
        else:
            de_score = 0.10

    cr_score = 0.50
    if cr is not None:
        if cr >= 2.0:
            cr_score = 1.00
        elif cr >= 1.5:
            cr_score = 0.80
        elif cr >= 1.0:
            cr_score = 0.55
        else:
            cr_score = 0.20

    health_norm = _norm(health_mod.get("score", 0), health_mod.get("max_score", 15))
    overlay = 0.65 * health_norm + 0.20 * de_score + 0.15 * cr_score
    return overlay, de, cr


def _score_mos_overlay(valuation_mod):
    mos = _to_float(valuation_mod.get("margin_of_safety_dcf"))
    if mos is None:
        return 0.45, None

    if mos >= 40:
        s = 1.00
    elif mos >= 25:
        s = 0.85
    elif mos >= 15:
        s = 0.70
    elif mos >= 5:
        s = 0.55
    elif mos >= -10:
        s = 0.35
    else:
        s = 0.10
    return s, mos


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

    # New professional blocks
    quality_block: dict = field(default_factory=dict)       # max 40
    capital_block: dict = field(default_factory=dict)       # max 25
    resilience_block: dict = field(default_factory=dict)    # max 20
    price_block: dict = field(default_factory=dict)         # max 15
    audit: dict = field(default_factory=dict)

    @property
    def max_score(self):
        return 100

    @property
    def total(self):
        return int(round(
            self.quality_block.get("score", 0)
            + self.capital_block.get("score", 0)
            + self.resilience_block.get("score", 0)
            + self.price_block.get("score", 0)
        ))

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
        pct = self.total / self.max_score * 100

        if pct >= 82:
            verdict = "STRONG BUY"
        elif pct >= 65:
            verdict = "BUY"
        elif pct >= 48:
            verdict = "WATCH"
        else:
            verdict = "AVOID"

        # Buffett-style quality gate: low quality cannot become high conviction
        q = self.quality_block.get("score", 0)
        r = self.resilience_block.get("score", 0)
        p = self.price_block.get("score", 0)

        if q < 18:
            verdict = "AVOID"
        elif q < 22 and verdict in ("STRONG BUY", "BUY"):
            verdict = "WATCH"
        elif r < 8 and verdict in ("STRONG BUY", "BUY"):
            verdict = "WATCH"
        elif p < 4 and verdict == "STRONG BUY":
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

        parts = [
            f"事業の質 {q:.0f}/40",
            f"資本配分 {c:.0f}/25",
            f"財務耐性 {r:.0f}/20",
            f"価格 {p:.0f}/15",
            f"MoS {mos_str}",
        ]

        v = self.verdict_en
        if v == "STRONG BUY":
            prefix = "高品質企業を保守的価格で見られる水準です。"
        elif v == "BUY":
            prefix = "質は十分で、価格もおおむね許容範囲です。"
        elif v == "WATCH":
            prefix = "企業の質か価格のどちらかに改善余地があります。"
        else:
            prefix = "バフェット基準では見送り優先です。"

        return prefix + " / " + " | ".join(parts)



def _build_quality_block(bd, info):
    earnings_norm = _norm(bd.earnings.get("score", 0), bd.earnings.get("max_score", 20))
    moat_norm = _norm(bd.moat.get("score", 0), bd.moat.get("max_score", 15))
    margin_norm, gm, om = _score_margin_profile(info)

    raw = 0.45 * earnings_norm + 0.35 * moat_norm + 0.20 * margin_norm
    score = round(raw * 40, 1)
    detail = f"earn={earnings_norm:.2f}, moat={moat_norm:.2f}, margin={margin_norm:.2f}, gross={gm}, op={om}"
    return {"score": score, "max_score": 40, "detail": detail}



def _build_capital_block(bd):
    capital_norm = _norm(bd.capital.get("score", 0), bd.capital.get("max_score", 20))
    oe_norm = _norm(bd.oe.get("score", 0), bd.oe.get("max_score", 20))
    mgmt_norm = _norm(bd.management.get("score", 0), bd.management.get("max_score", 10))

    raw = 0.45 * capital_norm + 0.35 * oe_norm + 0.20 * mgmt_norm
    score = round(raw * 25, 1)
    detail = f"capital={capital_norm:.2f}, oe={oe_norm:.2f}, mgmt={mgmt_norm:.2f}"
    return {"score": score, "max_score": 25, "detail": detail}



def _build_resilience_block(bd, info):
    overlay, de, cr = _score_balance_overlay(info, bd.health)
    score = round(overlay * 20, 1)
    detail = f"health={_norm(bd.health.get('score', 0), bd.health.get('max_score', 15)):.2f}, de={de}, cr={cr}"
    return {"score": score, "max_score": 20, "detail": detail}



def _build_price_block(bd):
    valuation_norm = _norm(bd.valuation.get("score", 0), bd.valuation.get("max_score", 10))
    mos_norm, mos = _score_mos_overlay(bd.valuation)
    raw = 0.65 * valuation_norm + 0.35 * mos_norm
    score = round(raw * 15, 1)
    detail = f"valuation={valuation_norm:.2f}, mos={mos}, mos_norm={mos_norm:.2f}"
    return {"score": score, "max_score": 15, "detail": detail}



def run_all_modules(data, ticker, market_config):
    cfg = market_config
    info = data.get("info", {}) if isinstance(data, dict) else {}

    fin = _ensure_df(data.get("financials") if isinstance(data, dict) else None)
    bs = _ensure_df(data.get("balance_sheet") if isinstance(data, dict) else None)
    cf = _ensure_df(data.get("cashflow") if isinstance(data, dict) else None)
    q_fin = _ensure_df(data.get("q_financials") if isinstance(data, dict) else None)
    q_bs = _ensure_df(data.get("q_balance_sheet") if isinstance(data, dict) else None)
    q_cf = _ensure_df(data.get("q_cashflow") if isinstance(data, dict) else None)

    bd = ScoreBreakdown()

    # Legacy modules ---------------------------------------------------------
    fn, err = _safe_import("buffett_analyzer.metrics.earnings", "analyze_earnings")
    bd.earnings = _safe_call(fn, 20, fin, info) if fn else {"score": 0, "max_score": 20, "detail": f"import失敗: {err}"}

    fn, err = _safe_import("buffett_analyzer.metrics.capital_efficiency", "analyze_capital_efficiency")
    bd.capital = _safe_call(fn, 20, fin, bs, info, cfg) if fn else {"score": 0, "max_score": 20, "detail": f"import失敗: {err}"}

    fn, err = _safe_import("buffett_analyzer.metrics.financial_health", "analyze_financial_health")
    if fn:
        bd.health = _safe_call(fn, 15, fin, bs, cf, info, cfg, q_balance_sheet=q_bs, q_cashflow=q_cf)
    else:
        bd.health = _fallback_health(fin, bs, cf, info, cfg)
        bd.health["detail"] += f" | import失敗: {err}"

    fn, err = _safe_import("buffett_analyzer.metrics.owner_earnings", "analyze_owner_earnings")
    bd.oe = _safe_call(fn, 20, fin, cf, bs, info, cfg, q_cashflow=q_cf, q_financials=q_fin) if fn else {"score": 0, "max_score": 20, "detail": f"import失敗: {err}"}

    fn, err = _safe_import("buffett_analyzer.metrics.moat", "analyze_moat")
    bd.moat = _safe_call(fn, 15, fin, cf, info, cfg) if fn else {"score": 0, "max_score": 15, "detail": f"import失敗: {err}"}

    fn, err = _safe_import("buffett_analyzer.metrics.valuation", "analyze_valuation")
    bd.valuation = _safe_call(fn, 10, fin, cf, bs, info, bd.oe, cfg) if fn else {"score": 0, "max_score": 10, "detail": f"import失敗: {err}"}

    fn, err = _safe_import("buffett_analyzer.metrics.management", "analyze_management")
    bd.management = _safe_call(fn, 10, fin, cf, bs, info, cfg) if fn else {"score": 0, "max_score": 10, "detail": f"import失敗: {err}"}

    fn, err = _safe_import("buffett_analyzer.metrics.jp_fundamentals", "analyze_jp_fundamentals")
    if fn:
        bd.jp_fundamentals = _safe_call(fn, 10, fin, cf, bs, info, cfg)
    else:
        bd.jp_fundamentals = {"score": 0, "max_score": 0, "detail": f"import失敗: {err}"}

    # New headline score blocks ---------------------------------------------
    bd.quality_block = _build_quality_block(bd, info)
    bd.capital_block = _build_capital_block(bd)
    bd.resilience_block = _build_resilience_block(bd, info)
    bd.price_block = _build_price_block(bd)

    bd.audit = {
        "ticker": ticker,
        "framework": "Buffett 4-block v2.0",
        "legacy_total": bd.legacy_total,
        "headline_total": bd.total,
        "quality_block": bd.quality_block,
        "capital_block": bd.capital_block,
        "resilience_block": bd.resilience_block,
        "price_block": bd.price_block,
    }

    # Professional annotation in legacy module details for debugging
    bd.management["headline_detail"] = (
        f"Q={bd.quality_block.get('score', 0):.1f}/40 | "
        f"C={bd.capital_block.get('score', 0):.1f}/25 | "
        f"R={bd.resilience_block.get('score', 0):.1f}/20 | "
        f"P={bd.price_block.get('score', 0):.1f}/15"
    )

    return bd
