import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from buffett_analyzer.data.fetcher import fetch_ticker_data
from buffett_analyzer.scoring.scorer import run_all_modules
from buffett_analyzer.config import MARKET_CONFIGS

# ── ページ設定 ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Buffett Score Analyzer",
    page_icon="📊",
    layout="centered",
)

# ── スタイル ────────────────────────────────────────────────────
st.markdown("""
<style>
.verdict-box {
    padding: 14px 20px; border-radius: 12px;
    font-size: 20px; font-weight: 700; text-align: center; margin-bottom: 8px;
}
.strong-buy { background:#14532d; color:#bbf7d0; }
.buy        { background:#1e3a5f; color:#bfdbfe; }
.watch      { background:#4a2c10; color:#fde68a; }
.avoid      { background:#4c0519; color:#fecaca; }
.module-card {
    background: #1e293b; border: 1px solid #334155;
    border-radius: 10px; padding: 14px 16px; margin-bottom: 10px;
}
.module-title { font-weight: 700; font-size: 15px; color: #e2e8f0; }
.module-detail { font-size: 12px; color: #94a3b8; margin-top: 4px; }
.kpi-val { font-size: 22px; font-weight: 800; }
</style>
""", unsafe_allow_html=True)

# ── ヘッダー ────────────────────────────────────────────────────
st.title("📊 Buffett Score Analyzer")
st.caption("Warren Buffett の投資哲学に基づくスコアリングツール")
st.divider()

# ── 入力フォーム ────────────────────────────────────────────────
col1, col2, col3 = st.columns([1.2, 2, 1])
with col1:
    market = st.selectbox("市場", ["us", "jp"], format_func=lambda x: "🇺🇸 米国株" if x == "us" else "🇯🇵 日本株")
with col2:
    ticker_raw = st.text_input("銘柄コード", placeholder="例: AAPL / 6861 / 8058")
with col3:
    st.write("")
    st.write("")
    run = st.button("🔍 分析する", use_container_width=True, type="primary")

# ── 分析実行 ────────────────────────────────────────────────────
if run:
    ticker = ticker_raw.strip().upper()
    if not ticker:
        st.warning("銘柄コードを入力してください。")
        st.stop()

    # JP は末尾 .T を付与
    if market == "jp" and not ticker.endswith(".T"):
        ticker += ".T"

    cfg = MARKET_CONFIGS[market]

    with st.spinner(f"[{ticker}] データ取得・スコア計算中..."):
        fetched = fetch_ticker_data(ticker)

    if fetched is None:
        st.error(f"❌ [{ticker}] データ取得に失敗しました。銘柄コードを確認してください。")
        st.stop()

    bd = run_all_modules(fetched, ticker, cfg)
    info = fetched.get("info", {})

    # ── 企業情報 ──────────────────────────────────────────────
    name    = info.get("longName") or info.get("shortName") or ticker
    sector  = info.get("sector") or info.get("industry") or "—"
    price   = info.get("currentPrice") or info.get("previousClose")
    sym     = cfg.currency_symbol
    mc      = info.get("marketCap")

    st.subheader(f"{name}　`{ticker}`")
    meta_cols = st.columns(4)
    meta_cols[0].metric("セクター", sector)
    meta_cols[1].metric("現在株価", f"{sym}{price:,.2f}" if price else "—")
    if mc:
        if mc >= 1e12: mc_str = f"{sym}{mc/1e12:.2f}T"
        elif mc >= 1e9: mc_str = f"{sym}{mc/1e9:.1f}B"
        else: mc_str = f"{sym}{mc/1e6:.0f}M"
        meta_cols[2].metric("時価総額", mc_str)
    else:
        meta_cols[2].metric("時価総額", "—")
    meta_cols[3].metric("市場", "🇺🇸 US" if market == "us" else "🇯🇵 JP")

    st.divider()

    # ── 総合スコア & 判定 ────────────────────────────────────
    max_s  = bd.max_score
    total  = bd.total
    ve     = bd.verdict_en
    vj     = bd.verdict
    pct    = total / max_s * 100

    css_cls = {"STRONG BUY":"strong-buy","BUY":"buy","WATCH":"watch","AVOID":"avoid"}.get(ve,"avoid")
    st.markdown(f'<div class="verdict-box {css_cls}">{vj} &nbsp;—&nbsp; {total} / {max_s} 点 ({pct:.0f}%)</div>', unsafe_allow_html=True)
    st.progress(int(pct))
    st.caption(bd.verdict_comment())
    st.divider()

    # ── バリュエーション KPI ─────────────────────────────────
    val = bd.valuation
    iv  = val.get("intrinsic_value_dcf")
    mos = val.get("margin_of_safety_dcf")
    pe  = val.get("pe_ratio")

    st.subheader("💰 バリュエーション")
    kpi_cols = st.columns(4)
    kpi_cols[0].metric("現在株価",       f"{sym}{price:,.2f}" if price else "—")
    kpi_cols[1].metric("本質的価値(DCF)", f"{sym}{iv:,.2f}"   if iv    else "—")
    mos_delta = f"{mos:+.1f}%" if mos else None
    kpi_cols[2].metric("Margin of Safety", f"{mos:.1f}%" if mos else "—", delta=mos_delta)
    kpi_cols[3].metric("PER", f"{pe:.1f}x" if pe else "—")
    st.divider()

    # ── モジュール別スコア ───────────────────────────────────
    st.subheader("📋 モジュール別スコア")

    modules = [
        ("📈 収益の一貫性",          bd.earnings,        20),
        ("⚡ 資本効率（ROE/ROIC）",  bd.capital,         20),
        ("🏦 財務健全性",            bd.health,          15),
        ("💵 Owner Earnings / FCF",  bd.oe,              20),
        ("🏰 経済的堀（Moat）",      bd.moat,            15),
        ("📊 バリュエーション",      bd.valuation,       10),
        ("👔 経営陣の資本配分",      bd.management,      10),
    ]
    if market == "jp":
        modules.append(("🇯🇵 日本株指標 (PBR/配当)", bd.jp_fundamentals, 10))

    for label, mod, max_m in modules:
        s      = mod.get("score", 0)
        detail = mod.get("detail", "")
        p      = s / max_m
        color  = "#22c55e" if p >= 0.80 else "#3b82f6" if p >= 0.55 else "#f59e0b" if p >= 0.35 else "#ef4444"

        with st.container():
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"**{label}**")
                st.progress(p)
                if detail:
                    st.caption(detail)
            with c2:
                st.markdown(
                    f'<p class="kpi-val" style="color:{color};text-align:right;">'
                    f'{s}<span style="font-size:13px;color:#64748b;">/{max_m}</span></p>',
                    unsafe_allow_html=True
                )
        st.write("")

    # ── フッター ──────────────────────────────────────────────
    st.divider()
    st.caption("⚠️ このツールは教育・研究目的です。実際の投資判断はご自身の責任で行ってください。")
