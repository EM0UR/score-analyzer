import streamlit as st
import sys, os, time, csv, io
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from buffett_analyzer.data.fetcher   import fetch_ticker_data
from buffett_analyzer.scoring.scorer import run_all_modules
from buffett_analyzer.config          import MARKET_CONFIGS

st.set_page_config(page_title="Buffett Score Analyzer", page_icon="📊", layout="centered")

st.markdown("""
<style>
.verdict-box{padding:14px 20px;border-radius:12px;font-size:20px;font-weight:700;text-align:center;margin-bottom:8px}
.strong-buy{background:#14532d;color:#bbf7d0}.buy{background:#1e3a5f;color:#bfdbfe}
.watch{background:#4a2c10;color:#fde68a}.avoid{background:#4c0519;color:#fecaca}
</style>
""", unsafe_allow_html=True)

# ── ヘルパー（scorer.py バージョン差を吸収）──────────────────────
def safe_get(obj, attr, default=None):
    if hasattr(obj, attr): return getattr(obj, attr)
    if isinstance(obj, dict): return obj.get(attr, default)
    return default

def get_total(bd):
    if hasattr(bd, "total"): return bd.total
    keys = ["earnings","capital","health","oe","moat","valuation","management","jp_fundamentals"]
    return sum((safe_get(bd, k) or {}).get("score", 0) for k in keys)

def get_max_score(bd, market):
    if hasattr(bd, "max_score"): return bd.max_score
    return 110 if market == "jp" else 100

def get_verdict(bd, pct):
    v = safe_get(bd, "verdict")
    if v: return v
    if pct >= 82: return "強い買い 🟢"
    elif pct >= 65: return "買い 🔵"
    elif pct >= 48: return "様子見 🟡"
    return "非推奨 🔴"

def get_verdict_en(bd, pct):
    v = safe_get(bd, "verdict_en")
    if v: return v
    if pct >= 82: return "STRONG BUY"
    elif pct >= 65: return "BUY"
    elif pct >= 48: return "WATCH"
    return "AVOID"

def get_comment(bd):
    vc = safe_get(bd, "verdict_comment")
    if callable(vc): return vc()
    if isinstance(vc, str): return vc
    return ""

# ── HTMLレポート生成 ──────────────────────────────────────────────
def build_html_report(ticker, market, bd, info):
    name   = info.get("longName") or info.get("shortName") or ticker
    price  = info.get("currentPrice") or info.get("previousClose")
    mc     = info.get("marketCap")
    sym    = "¥" if market == "jp" else "$"
    total  = get_total(bd)
    max_s  = get_max_score(bd, market)
    pct    = total / max_s * 100
    ve     = get_verdict_en(bd, pct)
    vj     = get_verdict(bd, pct)
    comment= get_comment(bd)
    val    = safe_get(bd, "valuation") or {}
    iv     = val.get("intrinsic_value_dcf")
    mos    = val.get("margin_of_safety_dcf")
    pe     = val.get("pe_ratio")
    css_cls= {"STRONG BUY":"strong-buy","BUY":"buy","WATCH":"watch","AVOID":"avoid"}.get(ve,"avoid")

    modules = [
        ("📈 収益の一貫性",         "earnings",   20),
        ("⚡ 資本効率",             "capital",    20),
        ("🏦 財務健全性",           "health",     15),
        ("💵 Owner Earnings/FCF",  "oe",         20),
        ("🏰 経済的堀（Moat）",    "moat",       15),
        ("📊 バリュエーション",    "valuation",  10),
        ("👔 経営陣の資本配分",    "management", 10),
    ]
    if market == "jp":
        modules.append(("🇯🇵 日本株指標", "jp_fundamentals", 10))

    rows = ""
    for label, attr, max_m in modules:
        mod = safe_get(bd, attr) or {}
        s   = mod.get("score", 0)
        d   = mod.get("detail", "")
        p   = s / max_m * 100
        clr = "#22c55e" if p>=80 else "#3b82f6" if p>=55 else "#f59e0b" if p>=35 else "#ef4444"
        rows += (
            f'<tr><td style="color:#e2e8f0;font-weight:600">{label}</td>'
            f'<td style="width:200px"><div style="background:#334155;border-radius:4px;height:8px">'
            f'<div style="width:{p:.0f}%;background:{clr};height:8px;border-radius:4px"></div></div></td>'
            f'<td style="color:{clr};font-weight:700;text-align:right">{s}/{max_m}</td>'
            f'<td style="color:#94a3b8;font-size:12px">{d}</td></tr>'
        )

    price_str = f"{sym}{price:,.2f}" if price else "—"
    iv_str    = f"{sym}{iv:,.2f}"    if iv    else "—"
    mos_str   = f"{mos:+.1f}%"       if mos is not None else "—"
    pe_str    = f"{pe:.1f}x"          if pe   else "—"
    mc_str    = (f"{sym}{mc/1e12:.2f}T" if mc and mc>=1e12 else
                 f"{sym}{mc/1e9:.1f}B"  if mc and mc>=1e9  else
                 f"{sym}{mc/1e6:.0f}M"  if mc               else "—")
    gen_at    = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    verdict_colors = {"strong-buy":"#22c55e","buy":"#3b82f6","watch":"#f59e0b","avoid":"#ef4444"}
    vc = verdict_colors.get(css_cls, "#94a3b8")

    return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8">
<title>Buffett Report — {ticker}</title>
<style>
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0f172a;color:#f1f5f9;padding:32px 20px;margin:0}}
.wrap{{max-width:900px;margin:0 auto}}
h1{{font-size:24px;font-weight:800;margin-bottom:4px}}
.sub{{font-size:13px;color:#64748b;margin-bottom:24px}}
.verdict{{padding:16px;border-radius:12px;text-align:center;font-size:22px;font-weight:800;background:#1e293b;border:2px solid {vc};color:{vc};margin-bottom:16px}}
.progress-outer{{background:#1e293b;border-radius:8px;height:12px;margin:8px 0 4px}}
.progress-inner{{height:12px;border-radius:8px;background:{vc}}}
.kpi{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}}
.kpi-card{{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:14px}}
.kpi-label{{font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.8px}}
.kpi-val{{font-size:20px;font-weight:800;margin-top:4px}}
table{{width:100%;border-collapse:collapse}}
td{{padding:10px 8px;border-bottom:1px solid #1e293b;vertical-align:middle}}
.footer{{text-align:center;font-size:11px;color:#475569;margin-top:28px;padding-top:16px;border-top:1px solid #1e293b}}
</style></head><body><div class="wrap">
<h1>{name} <span style="font-size:16px;color:#64748b">{ticker}</span></h1>
<div class="sub">生成日時: {gen_at} &nbsp;·&nbsp; 市場: {"🇯🇵 JP" if market=="jp" else "🇺🇸 US"}</div>
<div class="verdict">{vj} — {total} / {max_s} 点 ({pct:.0f}%)</div>
<div class="progress-outer"><div class="progress-inner" style="width:{min(pct,100):.0f}%"></div></div>
<p style="font-size:13px;color:#94a3b8;margin-bottom:24px">{comment}</p>
<div class="kpi">
<div class="kpi-card"><div class="kpi-label">現在株価</div><div class="kpi-val">{price_str}</div></div>
<div class="kpi-card"><div class="kpi-label">本質的価値 DCF</div><div class="kpi-val">{iv_str}</div></div>
<div class="kpi-card"><div class="kpi-label">Margin of Safety</div>
  <div class="kpi-val" style="color:{'#22c55e' if mos and mos>0 else '#ef4444'}">{mos_str}</div></div>
<div class="kpi-card"><div class="kpi-label">PER</div><div class="kpi-val">{pe_str}</div></div>
</div>
<table>{rows}</table>
<div class="footer">
<p>Buffett Score Analyzer &nbsp;·&nbsp; {gen_at}</p>
<p style="margin-top:4px">このレポートは教育・研究目的です。実際の投資判断はご自身の責任で行ってください。</p>
</div></div></body></html>"""

# ── タブ ─────────────────────────────────────────────────────────
st.title("📊 Buffett Score Analyzer")
st.caption("Warren Buffett の投資哲学に基づくスコアリングツール")
st.divider()

tab1, tab2 = st.tabs(["🔍 単銘柄分析", "📋 スクリーニング"])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 1 — 単銘柄分析
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab1:
    c1, c2, c3 = st.columns([1.2, 2, 1])
    with c1:
        market = st.selectbox("市場", ["us","jp"],
                              format_func=lambda x: "🇺🇸 米国株" if x=="us" else "🇯🇵 日本株",
                              key="market_single")
    with c2:
        ticker_raw = st.text_input("銘柄コード", placeholder="例: AAPL / 6861 / 8058", key="ticker_single")
    with c3:
        st.write(""); st.write("")
        run = st.button("🔍 分析する", use_container_width=True, type="primary", key="run_single")

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

        name   = info.get("longName") or info.get("shortName") or ticker
        sector = info.get("sector") or info.get("industry") or "—"
        price  = info.get("currentPrice") or info.get("previousClose")
        sym    = cfg.currency_symbol
        mc     = info.get("marketCap")

        st.subheader(f"{name}　`{ticker}`")
        m1,m2,m3,m4 = st.columns(4)
        m1.metric("セクター", sector[:15]+"…" if len(sector)>15 else sector)
        m2.metric("現在株価", f"{sym}{price:,.2f}" if price else "—")
        mc_str = (f"{sym}{mc/1e12:.2f}T" if mc and mc>=1e12 else
                  f"{sym}{mc/1e9:.1f}B"  if mc and mc>=1e9  else
                  f"{sym}{mc/1e6:.0f}M"  if mc               else "—")
        m3.metric("時価総額", mc_str)
        m4.metric("市場", "🇺🇸 US" if market=="us" else "🇯🇵 JP")
        st.divider()

        total  = get_total(bd)
        max_s  = get_max_score(bd, market)
        pct    = total / max_s * 100
        ve     = get_verdict_en(bd, pct)
        vj     = get_verdict(bd, pct)
        css_cls= {"STRONG BUY":"strong-buy","BUY":"buy","WATCH":"watch","AVOID":"avoid"}.get(ve,"avoid")

        st.markdown(f'<div class="verdict-box {css_cls}">{vj} &nbsp;—&nbsp; {total} / {max_s} 点 ({pct:.0f}%)</div>', unsafe_allow_html=True)
        st.progress(min(int(pct), 100))
        comment = get_comment(bd)
        if comment: st.caption(comment)
        st.divider()

        val_mod = safe_get(bd, "valuation") or {}
        iv  = val_mod.get("intrinsic_value_dcf")
        mos = val_mod.get("margin_of_safety_dcf")
        pe  = val_mod.get("pe_ratio")

        st.subheader("💰 バリュエーション")
        k1,k2,k3,k4 = st.columns(4)
        k1.metric("現在株価",         f"{sym}{price:,.2f}" if price else "—")
        k2.metric("本質的価値(DCF)",  f"{sym}{iv:,.2f}"    if iv    else "—")
        k3.metric("Margin of Safety", f"{mos:.1f}%" if mos is not None else "—",
                  delta=f"{mos:+.1f}%" if mos is not None else None)
        k4.metric("PER", f"{pe:.1f}x" if pe else "—")
        st.divider()

        st.subheader("📋 モジュール別スコア")
        modules = [
            ("📈 収益の一貫性",        "earnings",        20),
            ("⚡ 資本効率（ROE）",     "capital",         20),
            ("🏦 財務健全性",          "health",          15),
            ("💵 Owner Earnings/FCF",  "oe",              20),
            ("🏰 経済的堀（Moat）",    "moat",            15),
            ("📊 バリュエーション",    "valuation",       10),
            ("👔 経営陣の資本配分",    "management",      10),
        ]
        if market == "jp":
            modules.append(("🇯🇵 日本株指標 (PBR/配当)", "jp_fundamentals", 10))

        for label, attr, max_m in modules:
            mod    = safe_get(bd, attr) or {}
            s      = mod.get("score", 0) if isinstance(mod, dict) else 0
            detail = mod.get("detail", "") if isinstance(mod, dict) else ""
            p      = s / max_m
            color  = "#22c55e" if p>=0.80 else "#3b82f6" if p>=0.55 else "#f59e0b" if p>=0.35 else "#ef4444"
            lc, rc = st.columns([3,1])
            with lc:
                st.markdown(f"**{label}**")
                st.progress(p)
                if detail: st.caption(detail)
            with rc:
                st.markdown(
                    f'<p style="color:{color};font-size:22px;font-weight:800;text-align:right;margin-top:8px">'
                    f'{s}<span style="font-size:13px;color:#888">/{max_m}</span></p>',
                    unsafe_allow_html=True)
            st.write("")

        # HTMLレポートダウンロード
        st.divider()
        html_data = build_html_report(ticker, market, bd, info)
        st.download_button(
            label="📥 HTMLレポートをダウンロード",
            data=html_data.encode("utf-8"),
            file_name=f"buffett_{ticker}_{datetime.now().strftime('%Y%m%d')}.html",
            mime="text/html",
            use_container_width=True,
        )
        st.caption("⚠️ このツールは教育・研究目的です。実際の投資判断はご自身の責任で行ってください。")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 2 — スクリーニング
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab2:
    st.subheader("📋 代表銘柄スクリーニング")
    st.caption("S&P500代表約75銘柄 / TOPIX100代表約55銘柄をバフェット基準で自動スキャン")

    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        sc_market = st.selectbox("市場", ["us","jp"],
                                 format_func=lambda x: "🇺🇸 S&P500代表(75銘柄)" if x=="us" else "🇯🇵 TOPIX100代表(55銘柄)",
                                 key="market_screen")
    with sc2:
        top_n = st.number_input("表示上位件数", min_value=5, max_value=50, value=20, step=5)
    with sc3:
        min_score = st.number_input("最低スコア", min_value=0, max_value=90, value=0, step=5)

    run_screen = st.button("🚀 スクリーニング開始", type="primary", use_container_width=True, key="run_screen")

    st.warning("⏱️ 初回は全銘柄のデータ取得のため15〜30分かかる場合があります。2回目以降はキャッシュが使われ数分で完了します。")

    if run_screen:
        try:
            from buffett_analyzer.screener.universe import get_universe, get_sector
        except ImportError:
            st.error("screener/universe.py が見つかりません。リポジトリに追加してください。"); st.stop()

        universe = get_universe(sc_market)
        tickers  = list(universe.keys())
        cfg      = MARKET_CONFIGS[sc_market]
        sym      = cfg.currency_symbol
        results  = []

        prog_bar = st.progress(0)
        status   = st.empty()
        total_t  = len(tickers)

        for i, ticker in enumerate(tickers):
            status.text(f"分析中 [{i+1}/{total_t}] {ticker} — {universe[ticker]}")
            try:
                fetched = fetch_ticker_data(ticker)
                if fetched is None: continue
                bd   = run_all_modules(fetched, ticker, cfg)
                info = fetched.get("info", {})
                total  = get_total(bd)
                max_s  = get_max_score(bd, sc_market)
                pct    = total / max_s * 100
                val    = safe_get(bd, "valuation") or {}
                cap    = safe_get(bd, "capital")   or {}
                results.append({
                    "ticker":    ticker,
                    "name":      (info.get("longName") or info.get("shortName") or ticker)[:25],
                    "sector":    info.get("sector") or get_sector(ticker, sc_market),
                    "score":     total,
                    "max":       max_s,
                    "pct":       round(pct, 1),
                    "verdict":   get_verdict(bd, pct),
                    "verdict_en":get_verdict_en(bd, pct),
                    "mos":       val.get("margin_of_safety_dcf"),
                    "roe":       cap.get("roe_avg"),
                    "pe":        val.get("pe_ratio"),
                    "price":     info.get("currentPrice") or info.get("previousClose"),
                })
            except Exception:
                pass
            prog_bar.progress((i+1) / total_t)
            time.sleep(0.8)

        status.text(f"✅ スクリーニング完了 — {len(results)}/{total_t} 銘柄分析成功")
        results.sort(key=lambda x: x["score"], reverse=True)
        if min_score > 0:
            results = [r for r in results if r["score"] >= min_score]
        results = results[:int(top_n)]

        # サマリー
        strong = sum(1 for r in results if r["verdict_en"]=="STRONG BUY")
        buy    = sum(1 for r in results if r["verdict_en"]=="BUY")
        watch  = sum(1 for r in results if r["verdict_en"]=="WATCH")
        avoid  = sum(1 for r in results if r["verdict_en"]=="AVOID")
        s1,s2,s3,s4 = st.columns(4)
        s1.metric("強い買い 🟢", strong)
        s2.metric("買い 🔵",     buy)
        s3.metric("様子見 🟡",   watch)
        s4.metric("非推奨 🔴",   avoid)
        st.divider()

        # テーブル表示
        for rank, r in enumerate(results, 1):
            ve    = r["verdict_en"]
            color = {"STRONG BUY":"#22c55e","BUY":"#3b82f6","WATCH":"#f59e0b","AVOID":"#ef4444"}.get(ve,"#94a3b8")
            mos_s = f"{r['mos']:+.1f}%" if r["mos"] is not None else "—"
            roe_s = f"{r['roe']*100:.1f}%" if r["roe"] else "—"
            pe_s  = f"{r['pe']:.1f}x" if r["pe"] else "—"
            p_s   = f"{sym}{r['price']:,.0f}" if r["price"] else "—"
            c1,c2,c3,c4,c5,c6 = st.columns([0.4,2,1.5,1,1,1])
            c1.markdown(f"**{rank}**")
            c2.markdown(f"**{r['ticker']}** {r['name']}")
            c3.markdown(f'<span style="color:{color};font-weight:700">{r["verdict"]}</span> **{r["score"]}/{r["max"]}**', unsafe_allow_html=True)
            c4.markdown(f"MoS: `{mos_s}`")
            c5.markdown(f"ROE: `{roe_s}`")
            c6.markdown(f"{p_s}")
            st.divider()

        # CSV ダウンロード
        if results:
            buf = io.StringIO()
            w   = csv.DictWriter(buf, fieldnames=["ticker","name","sector","score","max","pct","verdict","mos","roe","pe","price"])
            w.writeheader()
            w.writerows(results)
            st.download_button(
                label="📥 CSVダウンロード",
                data=buf.getvalue().encode("utf-8-sig"),
                file_name=f"screen_{sc_market.upper()}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True,
            )
