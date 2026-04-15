# config.py — 市場別しきい値・定数
from dataclasses import dataclass

@dataclass
class MarketConfig:
    name: str
    currency: str
    currency_symbol: str
    # --- ROE / ROIC ---
    roe_excellent: float   # 超優秀
    roe_good: float        # 良好
    roe_ok: float          # 許容下限
    roic_good: float
    # --- 財務健全性 ---
    de_max_excellent: float
    de_max_good: float
    de_max_ok: float
    equity_ratio_good: float
    interest_coverage_good: float
    # --- キャッシュフロー ---
    min_oe_cagr: float          # Owner Earnings 最低成長率
    fcf_margin_good: float      # FCF マージン優良ライン
    fcf_yield_good: float       # FCF Yield 優良ライン
    # --- Moat ---
    gross_margin_std_ok: float  # グロスマージン標準偏差許容値
    capex_to_revenue_ok: float  # CapEx/売上 許容値（軽量型）
    # --- バリュエーション ---
    discount_rate: float
    terminal_growth: float
    mos_excellent: float   # Margin of Safety 優良ライン（%）
    mos_good: float        # MoS 良好ライン（%）


US_CONFIG = MarketConfig(
    name="US",
    currency="USD",
    currency_symbol="$",
    roe_excellent=0.20,
    roe_good=0.15,
    roe_ok=0.10,
    roic_good=0.12,
    de_max_excellent=0.30,
    de_max_good=0.50,
    de_max_ok=1.00,
    equity_ratio_good=0.40,
    interest_coverage_good=5.0,
    min_oe_cagr=0.05,
    fcf_margin_good=0.10,
    fcf_yield_good=0.04,
    gross_margin_std_ok=0.05,
    capex_to_revenue_ok=0.05,
    discount_rate=0.09,
    terminal_growth=0.025,
    mos_excellent=25.0,
    mos_good=10.0,
)

JP_CONFIG = MarketConfig(
    name="JP",
    currency="JPY",
    currency_symbol="¥",
    roe_excellent=0.15,
    roe_good=0.10,
    roe_ok=0.08,
    roic_good=0.08,
    de_max_excellent=0.30,
    de_max_good=0.70,
    de_max_ok=1.20,
    equity_ratio_good=0.35,
    interest_coverage_good=4.0,
    min_oe_cagr=0.04,
    fcf_margin_good=0.08,
    fcf_yield_good=0.035,
    gross_margin_std_ok=0.07,
    capex_to_revenue_ok=0.07,
    discount_rate=0.07,
    terminal_growth=0.015,
    mos_excellent=25.0,
    mos_good=10.0,
)

MARKET_CONFIGS = {"us": US_CONFIG, "jp": JP_CONFIG}
