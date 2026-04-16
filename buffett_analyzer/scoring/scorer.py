from dataclasses import dataclass, field
import pandas as pd

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
    def max_score(self) -> int:
        return 100 + self.jp_fundamentals.get("max_score", 0)

    @property
    def total(self) -> int:
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
    def verdict_en(self) -> str:
        pct = self.total / self.max_score * 100
        if   pct >= 82: return "STRONG BUY"
        elif pct >= 65: return "BUY"
        elif pct >= 48: return "WATCH"
        else:           return "AVOID"

    @property
    def verdict(self) -> str:
        return {
            "STRONG BUY": "強い買い 🟢",
            "BUY":        "買い 🔵",
            "WATCH":      "様子見 🟡",
            "AVOID":      "非推奨 🔴",
        }.get(self.verdict_en, "—")

    def verdict_comment(self) -> str:
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


def run_all_modules(data: dict, ticker: str, market_config) -> ScoreBreakdown:
    from buffett_analyzer.metrics.earnings           import analyze_earnings
    from buffett_analyzer.metrics.capital_efficiency import analyze_capital_efficiency
    from buffett_analyzer.metrics.financial_health   import analyze_financial_health
    from buffett_analyzer.metrics.owner_earnings     import analyze_owner_earnings
    from buffett_analyzer.metrics.moat               import analyze_moat
    from buffett_analyzer.metrics.valuation          import analyze_valuation
    from buffett_analyzer.metrics.management         import analyze_management
    from buffett_analyzer.metrics.jp_fundamentals    import analyze_jp_fundamentals

    info = data.get("info", {})

    # 年次データ（長期トレンド・EPS一貫性・Moat分析用）
    fin = data.get("financials")    or pd.DataFrame()
    bs  = data.get("balance_sheet") or pd.DataFrame()
    cf  = data.get("cashflow")      or pd.DataFrame()

    # 四半期データ（最新FCF・最新B/S・TTMマージン用）
    q_fin = data.get("q_financials")    or pd.DataFrame()
    q_bs  = data.get("q_balance_sheet") or pd.DataFrame()
    q_cf  = data.get("q_cashflow")      or pd.DataFrame()

    bd = ScoreBreakdown()

    # 年次データのみ使用（長期履歴が重要なモジュール）
    bd.earnings = analyze_earnings(fin, info)
    bd.capital  = analyze_capital_efficiency(fin, bs, info, market_config)
    bd.moat     = analyze_moat(fin, cf, info, market_config)

    # 四半期データを優先使用（最新業績が重要なモジュール）
    bd.health = analyze_financial_health(
        fin, bs, cf, info, market_config,
        q_balance_sheet=q_bs,   # ← 最新四半期B/S
    )
    bd.oe = analyze_owner_earnings(
        fin, cf, bs, info, market_config,
        q_cashflow=q_cf,         # ← 四半期TTM FCF
        q_financials=q_fin,      # ← 四半期TTM 売上
    )

    # バリュエーション・経営陣・JP指標
    bd.valuation       = analyze_valuation(fin, cf, bs, info, bd.oe, market_config)
    bd.management      = analyze_management(fin, cf, bs, info, market_config)
    bd.jp_fundamentals = analyze_jp_fundamentals(fin, cf, bs, info, market_config)

    return bd
