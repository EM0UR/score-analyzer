# scoring/scorer.py — 全モジュールを集約してスコア計算・判定
from dataclasses import dataclass, field
from typing import Dict

@dataclass
class ScoreBreakdown:
    earnings:    Dict = field(default_factory=dict)  # 収益一貫性   /20
    capital:     Dict = field(default_factory=dict)  # 資本効率     /20
    health:      Dict = field(default_factory=dict)  # 財務健全性   /15
    oe:          Dict = field(default_factory=dict)  # Owner Earnings/20
    moat:        Dict = field(default_factory=dict)  # 経済的堀     /15
    valuation:   Dict = field(default_factory=dict)  # バリュエーション/10
    management:  Dict = field(default_factory=dict)  # 経営陣       /10

    @property
    def total(self) -> int:
        return (
            self.earnings.get("score", 0)  +
            self.capital.get("score", 0)   +
            self.health.get("score", 0)    +
            self.oe.get("score", 0)        +
            self.moat.get("score", 0)      +
            self.valuation.get("score", 0) +
            self.management.get("score", 0)
        )

    @property
    def verdict(self) -> str:
        t = self.total
        if   t >= 82: return "強い買い 🟢"
        elif t >= 65: return "買い 🔵"
        elif t >= 48: return "様子見 🟡"
        else:         return "非推奨 🔴"

    @property
    def verdict_en(self) -> str:
        t = self.total
        if   t >= 82: return "STRONG BUY"
        elif t >= 65: return "BUY"
        elif t >= 48: return "WATCH"
        else:         return "AVOID"

    def verdict_comment(self) -> str:
        t = self.total
        mos = self.valuation.get("margin_of_safety_dcf")
        mos_str = f"{mos:.1f}%" if mos is not None else "不明"
        if t >= 82:
            return (
                "ウォーレン・バフェットの投資基準に高水準で合致。"
                f"Margin of Safety: {mos_str}。長期保有に適したコア銘柄候補。"
            )
        elif t >= 65:
            return (
                "バフェット基準をおおむね満たしている。"
                f"Margin of Safety: {mos_str}。段階的な買い増しを検討できる。"
            )
        elif t >= 48:
            return (
                "一部の指標に懸念あり。"
                f"Margin of Safety: {mos_str}。財務改善やバリュエーション低下を待ちたい。"
            )
        else:
            return (
                "バフェット基準への適合度が低い。"
                f"Margin of Safety: {mos_str}。再評価または他の銘柄を優先すること。"
            )


def run_all_modules(data: dict, ticker: str, market_config) -> ScoreBreakdown:
    """
    fetch されたデータを全モジュールに渡してスコアを計算し ScoreBreakdown を返す。
    """
    from metrics.earnings         import analyze_earnings
    from metrics.capital_efficiency import analyze_capital_efficiency
    from metrics.financial_health import analyze_financial_health
    from metrics.owner_earnings   import analyze_owner_earnings
    from metrics.moat             import analyze_moat
    from metrics.valuation        import analyze_valuation
    from metrics.management       import analyze_management

    info     = data.get("info", {})
    fin      = data.get("financials")
    bs       = data.get("balance_sheet")
    cf       = data.get("cashflow")

    bd = ScoreBreakdown()

    bd.earnings  = analyze_earnings(fin, info)
    bd.capital   = analyze_capital_efficiency(fin, bs, info, market_config)
    bd.health    = analyze_financial_health(fin, bs, cf, info, market_config)
    bd.oe        = analyze_owner_earnings(fin, cf, bs, info, market_config)
    bd.moat      = analyze_moat(fin, cf, info, market_config)
    bd.valuation = analyze_valuation(fin, cf, bs, info, bd.oe, market_config)
    bd.management= analyze_management(fin, cf, bs, info, market_config)

    return bd
