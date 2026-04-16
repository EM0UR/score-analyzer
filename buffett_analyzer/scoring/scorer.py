from dataclasses import dataclass, field
import pandas as pd

# ── フォールバック関数（financial_health.pyが壊れていても動く）──
def _fallback_health(financials, balance_sheet, cashflow, info, cfg, **kwargs):
    """financial_health.py のインポートが失敗した場合のフォールバック"""
    result = {"score": 0, "max_score": 15, "de_ratio": None,
              "equity_ratio": None, "interest_coverage": None,
              "current_ratio": None, "data_source": "fallback", "detail": ""}
    try:
        de = None
        raw = info.get("debtToEquity")
        if raw is not None:
            de = float(raw) / 100.0
        result["de_ratio"] = de

        cr = info.get("currentRatio")
        if cr: result["current_ratio"] = float(cr)

        s = 0
        if de is not None:
            if   de <= cfg.de_max_excellent: s += 6
            elif de <= cfg.de_max_good:      s += 4
            elif de <= cfg.de_max_ok:        s += 2
        if cr:
            cr = float(cr)
            if   cr >= 2.0: s += 3
            elif cr >= 1.5: s += 2
            elif cr >= 1.0: s += 1
        result["score"]  = min(s, 15)
        result["detail"] = (f"D/E {de:.2f}" if de else "D/E —") +                            (f" | 流動比率 {cr:.1f}x" if result["current_ratio"] else "") +                            " [info/fallback]"
    except Exception as e:
        result["score"]  = 2
        result["detail"] = f"フォールバック計算エラー: {e}"
    return result


@dataclass
class ScoreBreakdown:
    earnings:        dict = field(default_factory=dict)
    capital:         dict = field(default_factory=dict)
    health:          dict = field(default_factory=dict)
    oe:              dict = field(default_factory=dict)
    moat:            dict = field(default_factory=dict)
    valuation:       dict = field(default_factory=dict)
    management:      dict = field(default_factory=dict)
    jp_fundamentals: dict = field(default_factory=dict)

    @property
    def max_score(self):
        return 100 + self.jp_fundamentals.get("max_score", 0)

    @property
    def total(self):
        return (
            self.earnings.get("score", 0) +
            self.capital.get("score", 0)  +
            self.health.get("score", 0)   +
            self.oe.get("score", 0)       +
            self.moat.get("score", 0)     +
            self.valuation.get("score", 0)+
            self.management.get("score", 0)+
            self.jp_fundamentals.get("score", 0)
        )

    @property
    def verdict_en(self):
        pct = self.total / self.max_score * 100
        if   pct >= 82: return "STRONG BUY"
        elif pct >= 65: return "BUY"
        elif pct >= 48: return "WATCH"
        else:           return "AVOID"

    @property
    def verdict(self):
        return {"STRONG BUY":"強い買い 🟢","BUY":"買い 🔵",
                "WATCH":"様子見 🟡","AVOID":"非推奨 🔴"}.get(self.verdict_en, "—")

    def verdict_comment(self):
        mos = self.valuation.get("margin_of_safety_dcf")
        mos_str = f"{mos:.1f}%" if mos is not None else "不明"
        ve = self.verdict_en
        if ve == "STRONG BUY":
            return f"バフェット基準に高水準で合致。Margin of Safety: {mos_str}。長期保有のコア銘柄候補です。"
        elif ve == "BUY":
            return f"基準をおおむね満たしています。Margin of Safety: {mos_str}。段階的な買い増しを検討できます。"
        elif ve == "WATCH":
            return f"一部指標に懸念があります。Margin of Safety: {mos_str}。改善またはバリュエーション低下を待ちましょう。"
        else:
            return f"バフェット基準への適合度が低い状況です。Margin of Safety: {mos_str}。他の銘柄を優先することをお勧めします。"


def run_all_modules(data, ticker, market_config):
    cfg  = market_config
    info = data.get("info", {})
    fin  = data.get("financials")    or pd.DataFrame()
    bs   = data.get("balance_sheet") or pd.DataFrame()
    cf   = data.get("cashflow")      or pd.DataFrame()
    q_fin = data.get("q_financials")    or pd.DataFrame()
    q_bs  = data.get("q_balance_sheet") or pd.DataFrame()
    q_cf  = data.get("q_cashflow")      or pd.DataFrame()

    bd = ScoreBreakdown()

    # ── 各モジュール（失敗しても次へ進む）────────────────────────
    def _safe(fn, *args, **kwargs):
        try: return fn(*args, **kwargs)
        except Exception as e:
            return {"score": 0, "max_score": 10, "detail": f"モジュールエラー: {e}"}

    try:
        from buffett_analyzer.metrics.earnings import analyze_earnings
        bd.earnings = _safe(analyze_earnings, fin, info)
    except Exception as e:
        bd.earnings = {"score": 0, "max_score": 20, "detail": f"import失敗: {e}"}

    try:
        from buffett_analyzer.metrics.capital_efficiency import analyze_capital_efficiency
        bd.capital = _safe(analyze_capital_efficiency, fin, bs, info, cfg)
    except Exception as e:
        bd.capital = {"score": 0, "max_score": 20, "detail": f"import失敗: {e}"}

    # financial_health は壊れていてもフォールバックで動作させる
    try:
        from buffett_analyzer.metrics.financial_health import analyze_financial_health
        bd.health = _safe(analyze_financial_health, fin, bs, cf, info, cfg,
                          q_balance_sheet=q_bs, q_cashflow=q_cf)
    except Exception as e:
        bd.health = _fallback_health(fin, bs, cf, info, cfg)
        bd.health["detail"] += f" ※import失敗({type(e).__name__})"

    try:
        from buffett_analyzer.metrics.owner_earnings import analyze_owner_earnings
        bd.oe = _safe(analyze_owner_earnings, fin, cf, bs, info, cfg,
                      q_cashflow=q_cf, q_financials=q_fin)
    except Exception as e:
        bd.oe = {"score": 0, "max_score": 20, "detail": f"import失敗: {e}"}

    try:
        from buffett_analyzer.metrics.moat import analyze_moat
        bd.moat = _safe(analyze_moat, fin, cf, info, cfg)
    except Exception as e:
        bd.moat = {"score": 0, "max_score": 15, "detail": f"import失敗: {e}"}

    try:
        from buffett_analyzer.metrics.valuation import analyze_valuation
        bd.valuation = _safe(analyze_valuation, fin, cf, bs, info, bd.oe, cfg)
    except Exception as e:
        bd.valuation = {"score": 0, "max_score": 10, "detail": f"import失敗: {e}"}

    try:
        from buffett_analyzer.metrics.management import analyze_management
        bd.management = _safe(analyze_management, fin, cf, bs, info, cfg)
    except Exception as e:
        bd.management = {"score": 0, "max_score": 10, "detail": f"import失敗: {e}"}

    try:
        from buffett_analyzer.metrics.jp_fundamentals import analyze_jp_fundamentals
        bd.jp_fundamentals = _safe(analyze_jp_fundamentals, fin, cf, bs, info, cfg)
    except Exception as e:
        bd.jp_fundamentals = {"score": 0, "max_score": 0, "detail": f"import失敗: {e}"}

    return bd
