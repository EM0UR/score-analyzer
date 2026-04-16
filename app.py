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
</style>
""", unsafe_allow_html=True)

# ── ヘルパー（scorer.py バージョン差を吸収）───────────────────
def safe_get(obj, attr, default=None):
    """getattr + dict.get 両対応"""
    if hasattr(obj, attr):
        return getattr(obj, attr)
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return default

def get_total(bd):
    """total プロパティがなければ各モジュールを手動合算"""
    if hasattr(bd, "total"):
        return bd.total
    keys = ["earnings","capital","health","oe","moat","valuation","management","jp_fundamentals"]
    t = 0
    for k in keys:
        mod = safe_get(bd, k, {})
        if isinstance(mod, dict):
            t += mod.get("score", 0)
    return t

def get_max_score(bd, market):
    """max_score プロパティがなければ市場に応じた固定値を返す"""
    if hasattr(bd, "max_score"):
        return bd.max_score
    return 110 if market == "jp" else 100

def get_verdict(bd, pct):
    """verdict プロパティがなければ pct から判定"""
    v = safe_get(bd, "verdict")
    if v:
        return v
    if pct >= 82: return "強い買い 🟢"
    elif pct >= 65: return "買い 🔵"
    elif pct >= 48: return "様子見 🟡"
    else:           return "非推奨 🔴"

def get_verdict_en(bd, pct):
    v = safe_get(bd, "verdict_en")
    if v: return v
    if pct >= 82: return "STRONG BUY"
    elif pct >= 65: return "BUY"
    elif pct >= 48: return "WATCH"
    else:           return "AVOID"

def get_comment(bd):
    vc = safe_get(bd, "verdict_comment")
    if callable(vc):
        return vc()
    if isinstance(vc, str):
        return vc
    return ""

# ── UI ─────────────────────────────────────────────────────────
st.title("📊 Buffett Score Analyzer")
st.caption("Warren Buffett の投資哲学に基づくスコアリングツール")
st.divider()

col1, col2, col3 = st.columns([1.2, 2, 1])
with col1:
    market = st.selectbox("市場", ["us", "jp"],
                          format_func=lambda x: "🇺🇸 米国株" if x == "us" else "🇯🇵 日本株")
with col2:
    ticker_raw = st.text_input("銘柄コード", placeholder="例: AAPL / 6861 / 8058")
with col3:
    st.write(""); st.write("")
    run = st.button("🔍 分析する", use_container_width=True, type="primary")

# ── 分析 ────────────────────────────────────────────────────────
if run:
    ticker = ticker_raw.strip().upper()
    if not ticker:
        st.warning("銘柄コードを入力してください。"); st.stop()

    if market == "jp" and not ticker.endswith(".T"):
        ticker += ".T"

    cfg = MARKET_CONFIGS[market]

    with st.spinner(f"[{ticker}] データ取得・スコア計算中..."):
        fetched = fetch_ticker_data(ticker)

    if fetched is None:
        st.error(f"❌ [{ticker}] データ取得失敗。銘柄コードを確認してください。"); st.stop()

    bd   = run_all_modules(fetched, ticker, cfg)
    info = fetched.get("info", {})

    # 企業基本情報
    name  = info.get("longName") or info.get("shortName") or ticker
    sector= info.get("sector") or info.get("industry") or "—"
    price = info.get("currentPrice") or info.get("previousClose")
    sym   = cfg.currency_symbol
    mc    = info.get("marketCap")

    st.subheader(f"{name}　`{ticker}`")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("セクター",  sector[:15] + "..." if len(sector) > 15 else sector)
    c2.metric("現在株価",  f"{sym}{price:,.2f}" if price else "—")
    if mc:
        mc_str = f"{sym}{mc/1e12:.2f}T" if mc>=1e12 else f"{sym}{mc/1e9:.1f}B" if mc>=1e9 else f"{sym}{mc/1e6:.0f}M"
        c3.metric("時価総額", mc_str)
    else:
        c3.metric("時価総額", "—")
    c4.metric("市場", "🇺🇸 US" if market == "us" else "🇯🇵 JP")
    st.divider()

    # 総合スコア
    total = get_total(bd)
    max_s = get_max_score(bd, market)
    pct   = total / max_s * 100
    ve    = get_verdict_en(bd, pct)
    vj    = get_verdict(bd, pct)
    css   = {"STRONG BUY":"strong-buy","BUY":"buy","WATCH":"watch","AVOID":"avoid"}.get(ve,"avoid")
    comment = get_comment(bd)

    st.markdown(
        f'<div class="verdict-box {css}">{vj} &nbsp;—&nbsp; {total} / {max_s} 点 ({pct:.0f}%)</div>',
        unsafe_allow_html=True
    )
    st.progress(min(int(pct), 100))
    if comment:
        st.caption(comment)
    st.divider()

    # バリュエーション KPI
    val_mod = safe_get(bd, "valuation", {})
    iv   = val_mod.get("intrinsic_value_dcf") if isinstance(val_mod, dict) else None
    mos  = val_mod.get("margin_of_safety_dcf") if isinstance(val_mod, dict) else None
    pe   = val_mod.get("pe_ratio") if isinstance(val_mod, dict) else None

    st.subheader("💰 バリュエーション")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("現在株価",        f"{sym}{price:,.2f}" if price else "—")
    k2.metric("本質的価値(DCF)", f"{sym}{iv:,.2f}"    if iv    else "—")
    k3.metric("Margin of Safety",
              f"{mos:.1f}%" if mos is not None else "—",
              delta=f"{mos:+.1f}%" if mos is not None else None)
    k4.metric("PER", f"{pe:.1f}x" if pe else "—")
    st.divider()

    # モジュール別スコア
    st.subheader("📋 モジュール別スコア")

    modules = [
        ("📈 収益の一貫性",         "earnings",        20),
        ("⚡ 資本効率（ROE/ROIC）", "capital",         20),
        ("🏦 財務健全性",           "health",          15),
        ("💵 Owner Earnings / FCF", "oe",              20),
        ("🏰 経済的堀（Moat）",     "moat",            15),
        ("📊 バリュエーション",     "valuation",       10),
        ("👔 経営陣の資本配分",     "management",      10),
    ]
    if market == "jp":
        modules.append(("🇯🇵 日本株指標 (PBR/配当)", "jp_fundamentals", 10))

    for label, attr, max_m in modules:
        mod    = safe_get(bd, attr, {})
        s      = mod.get("score", 0) if isinstance(mod, dict) else 0
        detail = mod.get("detail", "") if isinstance(mod, dict) else ""
        p      = s / max_m
        color  = "#22c55e" if p >= 0.80 else "#3b82f6" if p >= 0.55 else "#f59e0b" if p >= 0.35 else "#ef4444"

        lc, rc = st.columns([3, 1])
        with lc:
            st.markdown(f"**{label}**")
            st.progress(p)
            if detail:
                st.caption(detail)
        with rc:
            st.markdown(
                f'<p style="color:{color};font-size:22px;font-weight:800;text-align:right;margin-top:8px;">'
                f'{s}<span style="font-size:13px;color:#888;">/{max_m}</span></p>',
                unsafe_allow_html=True
            )
        st.write("")

    st.divider()
    st.caption("⚠️ このツールは教育・研究目的です。実際の投資判断はご自身の責任で行ってください。")
