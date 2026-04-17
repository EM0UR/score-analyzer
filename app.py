import streamlit as st
import sys, os, time, csv, io
from datetime import datetime
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from buffett_analyzer.data.fetcher import fetch_ticker_data
from buffett_analyzer.scoring.scorer import run_all_modules
from buffett_analyzer.config import MARKET_CONFIGS
try:
    from data_provider import MultiSourceDataProvider
    _provider_import_error = None
except Exception as _e:
    MultiSourceDataProvider = None
    _provider_import_error = f"{type(_e).__name__}: {_e}"

st.set_page_config(page_title="Buffett Score Analyzer", page_icon="📊", layout="centered")

st.markdown("""
<style>
.verdict-box{padding:14px 20px;border-radius:12px;font-size:20px;font-weight:700;text-align:center;margin-bottom:8px}
.strong-buy{background:#14532d;color:#bbf7d0}.buy{background:#1e3a5f;color:#bfdbfe}
.watch{background:#4a2c10;color:#fde68a}.avoid{background:#4c0519;color:#fecaca}
.audit-card{background:#111827;border:1px solid #374151;border-radius:12px;padding:12px 14px;margin-bottom:10px}
.audit-title{font-size:12px;color:#9ca3af;text-transform:uppercase;letter-spacing:.08em}
.audit-score{font-size:22px;font-weight:800;margin-top:4px}
.small-note{font-size:12px;color:#94a3b8}
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_provider():
    if MultiSourceDataProvider is None:
        raise RuntimeError(_provider_import_error or "data_provider import failed")
    return MultiSourceDataProvider()


def merge_provider_into_fetched(fetched, provider_data):
    base = fetched.copy() if isinstance(fetched, dict) else {}
    info = dict(base.get("info") or {})
    p = provider_data or {}

    if p.get("company_name"):
        info.setdefault("longName", p["company_name"])
        info.setdefault("shortName", p["company_name"])

    if p.get("sector"):
        info.setdefault("sector", p["sector"])
    if p.get("industry"):
        info.setdefault("industry", p["industry"])
    if p.get("currency"):
        info.setdefault("currency", p["currency"])

    if p.get("market_price") is not None:
        info["currentPrice"] = info.get("currentPrice") or p["market_price"]
        info["previousClose"] = info.get("previousClose") or p["market_price"]

    if p.get("market_cap") is not None:
        info["marketCap"] = info.get("marketCap") or p["market_cap"]

    if p.get("shares_outstanding") is not None:
        info["sharesOutstanding"] = info.get("sharesOutstanding") or p["shares_outstanding"]

    if p.get("pe_ratio") is not None:
        info["trailingPE"] = info.get("trailingPE") or p["pe_ratio"]
        info["forwardPE"] = info.get("forwardPE") or p["pe_ratio"]

    if p.get("eps") is not None:
        info["trailingEps"] = info.get("trailingEps") or p["eps"]
        info["forwardEps"] = info.get("forwardEps") or p["eps"]

    if p.get("book_value_per_share") is not None:
        info["bookValue"] = info.get("bookValue") or p["book_value_per_share"]

    if p.get("current_ratio") is not None:
        info["currentRatio"] = info.get("currentRatio") or p["current_ratio"]

    if p.get("free_cash_flow") is not None:
        info["freeCashflow"] = info.get("freeCashflow") or p["free_cash_flow"]

    if p.get("roe") is not None:
        info["returnOnEquity"] = info.get("returnOnEquity") or (p["roe"] / 100.0)

    if p.get("debt_to_equity") is not None:
        info["debtToEquity"] = info.get("debtToEquity") or (p["debt_to_equity"] * 100.0)

    if p.get("gross_margin") is not None:
        info["grossMargins"] = info.get("grossMargins") or (p["gross_margin"] / 100.0)

    if p.get("operating_margin") is not None:
        info["operatingMargins"] = info.get("operatingMargins") or (p["operating_margin"] / 100.0)

    if p.get("net_margin") is not None:
        info["profitMargins"] = info.get("profitMargins") or (p["net_margin"] / 100.0)

    if p.get("dcf_intrinsic") is not None:
        info["providerDcfIntrinsic"] = info.get("providerDcfIntrinsic") or p["dcf_intrinsic"]
    if p.get("dcf_bear") is not None:
        info["providerDcfBear"] = info.get("providerDcfBear") or p["dcf_bear"]
    if p.get("dcf_base") is not None:
        info["providerDcfBase"] = info.get("providerDcfBase") or p["dcf_base"]
    if p.get("dcf_bull") is not None:
        info["providerDcfBull"] = info.get("providerDcfBull") or p["dcf_bull"]
    if p.get("margin_of_safety") is not None:
        info["providerMarginOfSafety"] = info.get("providerMarginOfSafety") or p["margin_of_safety"]

    base["info"] = info
    base["_provider"] = p
    base["_provider_audit"] = p.get("audit", {})
    return base



def provider_or_none(fetched, key, default=None):
    if not isinstance(fetched, dict):
        return default
    provider = fetched.get("_provider") or {}
    return provider.get(key, default)



def safe_get(obj, attr, default=None):
    if hasattr(obj, attr):
        return getattr(obj, attr)
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return default


def get_total(bd):
    if hasattr(bd, "total"):
        return bd.total
    keys = ["earnings","capital","health","oe","moat","valuation","management","jp_fundamentals"]
    return sum((safe_get(bd, k) or {}).get("score", 0) for k in keys)


def get_max_score(bd, market):
    if hasattr(bd, "max_score"):
        return bd.max_score
    return 110 if market == "jp" else 100


def get_verdict(bd, pct):
    v = safe_get(bd, "verdict")
    if v:
        return v
    if pct >= 82:
        return "強い買い 🟢"
    elif pct >= 65:
        return "買い 🔵"
    elif pct >= 48:
        return "様子見 🟡"
    return "非推奨 🔴"


def get_verdict_en(bd, pct):
    v = safe_get(bd, "verdict_en")
    if v:
        return v
    if pct >= 82:
        return "STRONG BUY"
    elif pct >= 65:
        return "BUY"
    elif pct >= 48:
        return "WATCH"
    return "AVOID"


def get_comment(bd):
    vc = safe_get(bd, "verdict_comment")
    if callable(vc):
        return vc()
    if isinstance(vc, str):
        return vc
    return ""


def fmt_num(v, digits=2, none="—"):
    try:
        if v is None:
            return none
        return f"{float(v):,.{digits}f}"
    except Exception:
        return none


def fmt_pct(v, digits=1, none="—"):
    try:
        if v is None:
            return none
        return f"{float(v):.{digits}f}%"
    except Exception:
        return none


def get_audit_block(bd, key, fallback_max):
    blk = safe_get(bd, key) or {}
    return {
        "score": blk.get("score", 0),
        "max_score": blk.get("max_score", fallback_max),
        "detail": blk.get("detail", "")
    }


def color_for_ratio(r):
    return "#22c55e" if r >= 0.80 else "#3b82f6" if r >= 0.55 else "#f59e0b" if r >= 0.35 else "#ef4444"


def has_usable_payload(fetched):
    if not isinstance(fetched, dict):
        return False

    info = fetched.get("info") or {}
    history = fetched.get("history")
    provider = fetched.get("_provider") or {}

    if isinstance(history, pd.DataFrame) and not history.empty:
        return True

    for key in ["currentPrice", "previousClose", "marketCap", "longName", "shortName", "currency"]:
        if info.get(key) is not None:
            return True

    for key in ["market_price", "market_cap", "company_name", "currency"]:
        if provider.get(key) is not None:
            return True

    return False


def render_fetch_debug(fetched, ticker):
    fetch_error = (fetched or {}).get("_fetch_error") if isinstance(fetched, dict) else None
    fetch_meta = (fetched or {}).get("_fetch_meta", {}) if isinstance(fetched, dict) else {}
    info = (fetched or {}).get("info", {}) if isinstance(fetched, dict) else {}

    if fetch_error:
        st.error(f"❌ [{ticker}] データ取得エラー: {fetch_error}")
    else:
        st.warning(f"⚠️ [{ticker}] データは返ったが、分析に必要な価格・基本情報が不足しています。")

    with st.expander("取得診断ログを見る", expanded=True):
        st.write({
            "ticker": ticker,
            "history_rows": fetch_meta.get("history_rows"),
            "info_keys": fetch_meta.get("info_keys"),
            "cache_dir": fetch_meta.get("cache_dir"),
            "warnings": fetch_meta.get("warnings"),
            "has_currentPrice": info.get("currentPrice") is not None,
            "has_previousClose": info.get("previousClose") is not None,
            "has_marketCap": info.get("marketCap") is not None,
            "has_longName": info.get("longName") is not None,
            "has_shortName": info.get("shortName") is not None,
        })
        if isinstance(info, dict) and info:
            preview = {k: info.get(k) for k in ["longName","shortName","sector","industry","currency","currentPrice","previousClose","marketCap"] if k in info}
            st.json(preview)


def sort_results(results, sort_key):
    keymap = {
        "総合点": lambda x: x.get("score", 0),
        "事業の質": lambda x: x.get("quality_score", 0),
        "資本配分": lambda x: x.get("capital_score", 0),
        "財務耐性": lambda x: x.get("resilience_score", 0),
        "価格": lambda x: x.get("price_score", 0),
        "Margin of Safety": lambda x: (-9999 if x.get("mos") is None else x.get("mos")),
        "割安度(PER低)": lambda x: (9999 if x.get("pe") is None else -x.get("pe")),
    }
    fn = keymap.get(sort_key, keymap["総合点"])
    return sorted(results, key=fn, reverse=True)


def build_compare_rows(results, sym):
    rows = []
    for r in results:
        rows.append({
            "Ticker": r.get("ticker"),
            "Name": r.get("name"),
            "Profile": r.get("profile"),
            "Score": f"{r.get('score', 0)}/{r.get('max', 100)}",
            "Quality": f"{r.get('quality_score', 0):.1f}/40",
            "Capital": f"{r.get('capital_score', 0):.1f}/25",
            "Resilience": f"{r.get('resilience_score', 0):.1f}/20",
            "Price": f"{r.get('price_score', 0):.1f}/15",
            "MoS": f"{r.get('mos', 0):+.1f}%" if r.get('mos') is not None else "—",
            "PE": f"{r.get('pe', 0):.1f}x" if r.get('pe') is not None else "—",
            "PriceNow": f"{sym}{r.get('price', 0):,.2f}" if r.get('price') is not None else "—",
            "Verdict": r.get("verdict"),
        })
    return rows


def safe_csv_download(results, filename, label="📥 CSVダウンロード"):
    if not results:
        return
    all_fields = []
    seen = set()
    for row in results:
        for k in row.keys():
            if k not in seen:
                seen.add(k)
                all_fields.append(k)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=all_fields, extrasaction="ignore")
    w.writeheader()
    for row in results:
        safe_row = {k: row.get(k) for k in all_fields}
        w.writerow(safe_row)
    st.download_button(
        label=label,
        data=buf.getvalue().encode("utf-8-sig"),
        file_name=filename,
        mime="text/csv",
        use_container_width=True,
    )


def build_html_report(ticker, market, bd, info, provider):
    provider = provider or {}
    name = info.get("longName") or info.get("shortName") or provider.get("company_name") or ticker
    price = info.get("currentPrice") or info.get("previousClose") or provider.get("market_price")
    sym = "¥" if market == "jp" else "$"
    total = get_total(bd)
    max_s = get_max_score(bd, market)
    pct = total / max_s * 100 if max_s else 0
    ve = get_verdict_en(bd, pct)
    vj = get_verdict(bd, pct)
    comment = get_comment(bd)
    val = safe_get(bd, "valuation") or {}
    iv = val.get("intrinsic_value_dcf") or provider.get("dcf_intrinsic")
    mos = val.get("margin_of_safety_dcf")
    if mos is None:
        mos = provider.get("margin_of_safety")
    pe = val.get("pe_ratio") or provider.get("pe_ratio")
    css_cls = {"STRONG BUY":"strong-buy","BUY":"buy","WATCH":"watch","AVOID":"avoid"}.get(ve, "avoid")

    q = get_audit_block(bd, "quality_block", 40)
    c = get_audit_block(bd, "capital_block", 25)
    r = get_audit_block(bd, "resilience_block", 20)
    p = get_audit_block(bd, "price_block", 15)
    audit = safe_get(bd, "audit") or {}
    profile_label = audit.get("profile_label", "general")
    bear = val.get("intrinsic_value_dcf_bear") or provider.get("dcf_bear")
    base = val.get("intrinsic_value_dcf_base") or provider.get("dcf_base") or provider.get("dcf_intrinsic")
    bull = val.get("intrinsic_value_dcf_bull") or provider.get("dcf_bull")

    rows = ""
    for label, block in [("事業の質", q), ("資本配分", c), ("財務耐性", r), ("価格", p)]:
        s = block.get("score", 0)
        m = block.get("max_score", 1)
        d = block.get("detail", "")
        ratio = (s / m * 100) if m else 0
        clr = color_for_ratio((s / m) if m else 0)
        rows += (
            f'<tr><td style="color:#e2e8f0;font-weight:600">{label}</td>'
            f'<td style="width:200px"><div style="background:#334155;border-radius:4px;height:8px">'
            f'<div style="width:{ratio:.0f}%;background:{clr};height:8px;border-radius:4px"></div></div></td>'
            f'<td style="color:{clr};font-weight:700;text-align:right">{s:.1f}/{m}</td>'
            f'<td style="color:#94a3b8;font-size:12px">{d}</td></tr>'
        )

    price_str = f"{sym}{price:,.2f}" if price else "—"
    iv_str = f"{sym}{iv:,.2f}" if iv else "—"
    mos_str = f"{mos:+.1f}%" if mos is not None else "—"
    pe_str = f"{pe:.1f}x" if pe else "—"
    bear_str = f"{sym}{bear:,.2f}" if bear else "—"
    base_str = f"{sym}{base:,.2f}" if base else "—"
    bull_str = f"{sym}{bull:,.2f}" if bull else "—"
    gen_at = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    verdict_colors = {"strong-buy":"#22c55e","buy":"#3b82f6","watch":"#f59e0b","avoid":"#ef4444"}
    vc = verdict_colors.get(css_cls, "#94a3b8")

    return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8"><title>Buffett Report — {ticker}</title>
<style>
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0f172a;color:#f1f5f9;padding:32px 20px;margin:0}}
.wrap{{max-width:980px;margin:0 auto}} h1{{font-size:24px;font-weight:800;margin-bottom:4px}}
.sub{{font-size:13px;color:#64748b;margin-bottom:24px}}
.verdict{{padding:16px;border-radius:12px;text-align:center;font-size:22px;font-weight:800;background:#1e293b;border:2px solid {vc};color:{vc};margin-bottom:16px}}
.progress-outer{{background:#1e293b;border-radius:8px;height:12px;margin:8px 0 4px}}
.progress-inner{{height:12px;border-radius:8px;background:{vc}}}
.kpi{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}}
.kpi-card{{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:14px}}
.kpi-label{{font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.8px}}
.kpi-val{{font-size:20px;font-weight:800;margin-top:4px}}
table{{width:100%;border-collapse:collapse}} td{{padding:10px 8px;border-bottom:1px solid #1e293b;vertical-align:middle}}
.footer{{text-align:center;font-size:11px;color:#475569;margin-top:28px;padding-top:16px;border-top:1px solid #1e293b}}
</style></head><body><div class="wrap">
<h1>{name} <span style="font-size:16px;color:#64748b">{ticker}</span></h1>
<div class="sub">生成日時: {gen_at} · 市場: {"🇯🇵 JP" if market=='jp' else '🇺🇸 US'} · 業種プロファイル: {profile_label}</div>
<div class="verdict">{vj} — {total} / {max_s} 点 ({pct:.0f}%)</div>
<div class="progress-outer"><div class="progress-inner" style="width:{min(pct,100):.0f}%"></div></div>
<p style="font-size:13px;color:#94a3b8;margin-bottom:24px">{comment}</p>
<div class="kpi">
<div class="kpi-card"><div class="kpi-label">現在株価</div><div class="kpi-val">{price_str}</div></div>
<div class="kpi-card"><div class="kpi-label">保守的 DCF</div><div class="kpi-val">{iv_str}</div></div>
<div class="kpi-card"><div class="kpi-label">Margin of Safety</div><div class="kpi-val" style="color:{'#22c55e' if mos and mos>0 else '#ef4444'}">{mos_str}</div></div>
<div class="kpi-card"><div class="kpi-label">PER</div><div class="kpi-val">{pe_str}</div></div>
</div>
<div class="kpi">
<div class="kpi-card"><div class="kpi-label">悲観DCF</div><div class="kpi-val">{bear_str}</div></div>
<div class="kpi-card"><div class="kpi-label">標準DCF</div><div class="kpi-val">{base_str}</div></div>
<div class="kpi-card"><div class="kpi-label">強気DCF</div><div class="kpi-val">{bull_str}</div></div>
<div class="kpi-card"><div class="kpi-label">業種プロファイル</div><div class="kpi-val" style="font-size:14px">{profile_label}</div></div>
</div>
<table>{rows}</table>
<div class="footer"><p>Buffett Score Analyzer · {gen_at}</p><p style="margin-top:4px">このレポートは教育・研究目的です。実際の投資判断はご自身の責任で行ってください。</p></div>
</div></body></html>"""


st.title("📊 Buffett Score Analyzer")
st.caption("Warren Buffett の投資哲学に基づくスコアリングツール")
st.divider()

tab1, tab2 = st.tabs(["🔍 単銘柄分析", "📋 スクリーニング"])

with tab1:
    c1, c2, c3 = st.columns([1.2, 2, 1])
    with c1:
        market = st.selectbox("市場", ["us", "jp"], format_func=lambda x: "🇺🇸 米国株" if x == "us" else "🇯🇵 日本株", key="market_single")
    with c2:
        ticker_raw = st.text_input("銘柄コード", placeholder="例: AAPL / 6861 / 8058", key="ticker_single")
    with c3:
        st.write("")
        st.write("")
        run = st.button("🔍 分析する", use_container_width=True, type="primary", key="run_single")

    if run:
        ticker = ticker_raw.strip().upper()
        if not ticker:
            st.warning("銘柄コードを入力してください。")
            st.stop()
        if market == "jp" and not ticker.endswith(".T"):
            ticker += ".T"
        cfg = MARKET_CONFIGS[market]

        with st.spinner(f"[{ticker}] データ取得・スコア計算中..."):
            fetched = fetch_ticker_data(ticker)

            provider_error = None
            try:
                provider = get_provider()
                provider_data = provider.get_metrics(ticker, market=market)
                fetched = merge_provider_into_fetched(fetched, provider_data)
            except Exception as e:
                provider_error = f"{type(e).__name__}: {e}"

        if fetched is None:
            st.error(f"❌ [{ticker}] fetcher から None が返りました。fetcher.py の例外処理が未反映の可能性があります。")
            st.stop()

        if provider_error:
            st.warning(f"⚠️ 外部フォールバック取得は一部失敗しました: {provider_error}")

        if not has_usable_payload(fetched):
            render_fetch_debug(fetched, ticker)
            st.stop()

        info = fetched.get("info", {}) if isinstance(fetched, dict) else {}
        provider_flat = fetched.get("_provider", {}) if isinstance(fetched, dict) else {}
        if fetched.get("_fetch_error"):
            st.warning(f"⚠️ 部分取得で続行します: {fetched.get('_fetch_error')}")
            with st.expander("取得診断ログを見る"):
                st.json(fetched.get("_fetch_meta", {}))

        try:
            bd = run_all_modules(fetched, ticker, cfg)
        except Exception as e:
            st.error(f"❌ スコア計算エラー: {type(e).__name__}: {e}")
            with st.expander("取得診断ログを見る", expanded=True):
                st.json(fetched.get("_fetch_meta", {}))
                st.write({"info_keys": len(info) if isinstance(info, dict) else 0})
            st.stop()

        name = (
            info.get("longName")
            or info.get("shortName")
            or provider_flat.get("company_name")
            or ticker
        )
        sector = (
            info.get("sector")
            or info.get("industry")
            or provider_flat.get("sector")
            or provider_flat.get("industry")
            or "—"
        )
        price = (
            info.get("currentPrice")
            or info.get("previousClose")
            or provider_flat.get("market_price")
        )
        sym = cfg.currency_symbol
        mc = info.get("marketCap") or provider_flat.get("market_cap")
        audit = safe_get(bd, "audit") or {}
        profile = audit.get("profile", "general")
        profile_label = audit.get("profile_label", sector)

        st.subheader(f"{name}　`{ticker}`")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("セクター", sector[:15] + "…" if isinstance(sector, str) and len(sector) > 15 else sector)
        m2.metric("現在株価", f"{sym}{price:,.2f}" if price else "—")
        mc_str = (f"{sym}{mc/1e12:.2f}T" if mc and mc >= 1e12 else f"{sym}{mc/1e9:.1f}B" if mc and mc >= 1e9 else f"{sym}{mc/1e6:.0f}M" if mc else "—")
        m3.metric("時価総額", mc_str)
        m4.metric("市場", "🇺🇸 US" if market == "us" else "🇯🇵 JP")
        st.caption(f"業種プロファイル: `{profile}` / {profile_label}")
        st.divider()

        total = get_total(bd)
        max_s = get_max_score(bd, market)
        pct = total / max_s * 100 if max_s else 0
        ve = get_verdict_en(bd, pct)
        vj = get_verdict(bd, pct)
        css_cls = {"STRONG BUY": "strong-buy", "BUY": "buy", "WATCH": "watch", "AVOID": "avoid"}.get(ve, "avoid")

        st.markdown(f'<div class="verdict-box {css_cls}">{vj} &nbsp;—&nbsp; {total} / {max_s} 点 ({pct:.0f}%)</div>', unsafe_allow_html=True)
        st.progress(min(int(pct), 100))
        comment = get_comment(bd)
        if comment:
            st.caption(comment)
        st.divider()

        st.subheader("🧭 4ブロック判定")
        q = get_audit_block(bd, "quality_block", 40)
        c = get_audit_block(bd, "capital_block", 25)
        r = get_audit_block(bd, "resilience_block", 20)
        p = get_audit_block(bd, "price_block", 15)
        cards = [("事業の質", q), ("資本配分", c), ("財務耐性", r), ("価格", p)]
        cols = st.columns(4)
        for col, (label, block) in zip(cols, cards):
            score = block.get("score", 0)
            mx = block.get("max_score", 1)
            col.markdown(
                f'<div class="audit-card"><div class="audit-title">{label}</div>'
                f'<div class="audit-score">{score:.1f}<span style="font-size:12px;color:#9ca3af"> / {mx}</span></div>'
                f'<div class="small-note">{block.get("detail", "")[:120]}</div></div>',
                unsafe_allow_html=True,
            )
        st.divider()

        val_mod = safe_get(bd, "valuation") or {}

        iv = val_mod.get("intrinsic_value_dcf")
        if iv is None:
            iv = provider_flat.get("dcf_intrinsic")

        mos = val_mod.get("margin_of_safety_dcf")
        if mos is None:
            mos = provider_flat.get("margin_of_safety")

        pe = val_mod.get("pe_ratio")
        if pe is None:
            pe = provider_flat.get("pe_ratio")

        bear = val_mod.get("intrinsic_value_dcf_bear")
        if bear is None:
            bear = provider_flat.get("dcf_bear")

        base = val_mod.get("intrinsic_value_dcf_base")
        if base is None:
            base = provider_flat.get("dcf_base") or provider_flat.get("dcf_intrinsic")

        bull = val_mod.get("intrinsic_value_dcf_bull")
        if bull is None:
            bull = provider_flat.get("dcf_bull")

        weighted = val_mod.get("intrinsic_value_dcf_weighted")
        if weighted is None:
            weighted = provider_flat.get("dcf_base") or provider_flat.get("dcf_intrinsic")
        oe_ps = val_mod.get("owner_earnings_per_share_used")
        oe_src = val_mod.get("owner_earnings_source")
        scen = val_mod.get("scenario_assumptions") or {}

        st.subheader("💰 バリュエーション")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("現在株価", f"{sym}{price:,.2f}" if price else "—")
        k2.metric("保守的 DCF", f"{sym}{iv:,.2f}" if iv else "—")
        k3.metric("Margin of Safety", f"{mos:.1f}%" if mos is not None else "—", delta=f"{mos:+.1f}%" if mos is not None else None)
        k4.metric("PER", f"{pe:.1f}x" if pe else "—")

        s1, s2, s3, s4 = st.columns(4)
        s1.metric("悲観 DCF", f"{sym}{bear:,.2f}" if bear else "—")
        s2.metric("標準 DCF", f"{sym}{base:,.2f}" if base else "—")
        s3.metric("強気 DCF", f"{sym}{bull:,.2f}" if bull else "—")
        s4.metric("加重 DCF", f"{sym}{weighted:,.2f}" if weighted else "—")
        st.caption(f"Owner Earnings/株として使用: {fmt_num(oe_ps)} ({oe_src or 'n/a'})")

        with st.expander("DCF前提を見る"):
            bear_a = scen.get("bear", {})
            base_a = scen.get("base", {})
            bull_a = scen.get("bull", {})
            df_rows = [
                {"scenario": "bear", "growth": fmt_pct((bear_a.get("growth") or 0) * 100 if bear_a else None), "discount": fmt_pct((bear_a.get("discount") or 0) * 100 if bear_a else None), "terminal": fmt_pct((bear_a.get("terminal") or 0) * 100 if bear_a else None)},
                {"scenario": "base", "growth": fmt_pct((base_a.get("growth") or 0) * 100 if base_a else None), "discount": fmt_pct((base_a.get("discount") or 0) * 100 if base_a else None), "terminal": fmt_pct((base_a.get("terminal") or 0) * 100 if base_a else None)},
                {"scenario": "bull", "growth": fmt_pct((bull_a.get("growth") or 0) * 100 if bull_a else None), "discount": fmt_pct((bull_a.get("discount") or 0) * 100 if bull_a else None), "terminal": fmt_pct((bull_a.get("terminal") or 0) * 100 if bull_a else None)},
            ]
            st.dataframe(df_rows, use_container_width=True, hide_index=True)
        st.divider()

        st.subheader("📋 モジュール別スコア")
        modules = [
            ("📈 収益の一貫性", "earnings", 20),
            ("⚡ 資本効率（ROE）", "capital", 20),
            ("🏦 財務健全性", "health", 15),
            ("💵 Owner Earnings/FCF", "oe", 20),
            ("🏰 経済的堀（Moat）", "moat", 15),
            ("📊 バリュエーション", "valuation", 10),
            ("👔 経営陣の資本配分", "management", 10),
        ]
        if market == "jp":
            modules.append(("🇯🇵 日本株指標 (PBR/配当)", "jp_fundamentals", 10))

        for label, attr, max_m in modules:
            mod = safe_get(bd, attr) or {}
            s = mod.get("score", 0) if isinstance(mod, dict) else 0
            detail = mod.get("detail", "") if isinstance(mod, dict) else ""
            p_ratio = s / max_m if max_m else 0
            color = color_for_ratio(p_ratio)
            lc, rc = st.columns([3, 1])
            with lc:
                st.markdown(f"**{label}**")
                st.progress(p_ratio)
                if detail:
                    st.caption(detail)
            with rc:
                st.markdown(f'<p style="color:{color};font-size:22px;font-weight:800;text-align:right;margin-top:8px">{s}<span style="font-size:13px;color:#888">/{max_m}</span></p>', unsafe_allow_html=True)
            st.write("")

        st.divider()
        with st.expander("🧾 監査ログ（プロ向け）"):
            st.write({
                "framework": audit.get("framework"),
                "profile": audit.get("profile"),
                "profile_label": audit.get("profile_label"),
                "headline_total": audit.get("headline_total"),
                "legacy_total": audit.get("legacy_total"),
            })
            st.json(audit)

            provider_audit = fetched.get("_provider_audit", {})
            if provider_audit:
                st.write("### Data Provider Audit")
                st.json(provider_audit)

        st.divider()
        html_data = build_html_report(ticker, market, bd, info, provider_flat)
        st.download_button(
            label="📥 HTMLレポートをダウンロード",
            data=html_data.encode("utf-8"),
            file_name=f"buffett_{ticker}_{datetime.now().strftime('%Y%m%d')}.html",
            mime="text/html",
            use_container_width=True,
        )
        st.caption("⚠️ このツールは教育・研究目的です。実際の投資判断はご自身の責任で行ってください。")

with tab2:
    st.subheader("📋 代表銘柄スクリーニング")
    st.caption("S&P500代表約75銘柄 / TOPIX100代表約55銘柄をバフェット基準で自動スキャン")

    sc1, sc2, sc3, sc4 = st.columns(4)
    with sc1:
        sc_market = st.selectbox("市場", ["us", "jp"], format_func=lambda x: "🇺🇸 S&P500代表(75銘柄)" if x == "us" else "🇯🇵 TOPIX100代表(55銘柄)", key="market_screen")
    with sc2:
        top_n = st.number_input("表示上位件数", min_value=5, max_value=50, value=20, step=5)
    with sc3:
        min_score = st.number_input("最低スコア", min_value=0, max_value=90, value=0, step=5)
    with sc4:
        sort_by = st.selectbox("並び替え", ["総合点", "事業の質", "資本配分", "財務耐性", "価格", "Margin of Safety", "割安度(PER低)"], key="sort_screen")

    run_screen = st.button("🚀 スクリーニング開始", type="primary", use_container_width=True, key="run_screen")
    st.warning("⏱️ 初回は全銘柄のデータ取得のため15〜30分かかる場合があります。2回目以降はキャッシュが使われ数分で完了します。")

    if run_screen:
        try:
            from buffett_analyzer.screener.universe import get_universe, get_sector
        except ImportError:
            st.error("screener/universe.py が見つかりません。リポジトリに追加してください。")
            st.stop()

        universe = get_universe(sc_market)
        tickers = list(universe.keys())
        cfg = MARKET_CONFIGS[sc_market]
        sym = cfg.currency_symbol
        results = []

        prog_bar = st.progress(0)
        status = st.empty()
        total_t = len(tickers)

        for i, ticker in enumerate(tickers):
            status.text(f"分析中 [{i+1}/{total_t}] {ticker} — {universe[ticker]}")
            try:
                fetched = fetch_ticker_data(ticker)

                try:
                    provider = get_provider()
                    provider_data = provider.get_metrics(ticker, market=sc_market)
                    fetched = merge_provider_into_fetched(fetched, provider_data)
                except Exception:
                    pass

                if not has_usable_payload(fetched):
                    prog_bar.progress((i + 1) / total_t)
                    time.sleep(0.1)
                    continue
                bd = run_all_modules(fetched, ticker, cfg)
                info = fetched.get("info", {}) if isinstance(fetched, dict) else {}
                total = get_total(bd)
                max_s = get_max_score(bd, sc_market)
                pct = total / max_s * 100 if max_s else 0
                val = safe_get(bd, "valuation") or {}
                cap = safe_get(bd, "capital") or {}
                audit = safe_get(bd, "audit") or {}
                q = get_audit_block(bd, "quality_block", 40)
                c = get_audit_block(bd, "capital_block", 25)
                r = get_audit_block(bd, "resilience_block", 20)
                p = get_audit_block(bd, "price_block", 15)
                results.append({
                    "ticker": ticker,
                    "name": (info.get("longName") or info.get("shortName") or ticker)[:25],
                    "sector": info.get("sector") or get_sector(ticker, sc_market),
                    "profile": audit.get("profile", "general"),
                    "score": total,
                    "max": max_s,
                    "pct": round(pct, 1),
                    "verdict": get_verdict(bd, pct),
                    "verdict_en": get_verdict_en(bd, pct),
                    "mos": val.get("margin_of_safety_dcf"),
                    "roe": cap.get("roe_avg") if isinstance(cap, dict) else None,
                    "pe": val.get("pe_ratio"),
                    "price": info.get("currentPrice") or info.get("previousClose"),
                    "quality_score": q.get("score", 0),
                    "capital_score": c.get("score", 0),
                    "resilience_score": r.get("score", 0),
                    "price_score": p.get("score", 0),
                })
            except Exception:
                pass
            prog_bar.progress((i + 1) / total_t)
            time.sleep(0.1)

        status.text(f"✅ スクリーニング完了 — {len(results)}/{total_t} 銘柄分析成功")
        if min_score > 0:
            results = [r for r in results if r["score"] >= min_score]
        results = sort_results(results, sort_by)
        results = results[:int(top_n)]

        strong = sum(1 for r in results if r["verdict_en"] == "STRONG BUY")
        buy = sum(1 for r in results if r["verdict_en"] == "BUY")
        watch = sum(1 for r in results if r["verdict_en"] == "WATCH")
        avoid = sum(1 for r in results if r["verdict_en"] == "AVOID")
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("強い買い 🟢", strong)
        s2.metric("買い 🔵", buy)
        s3.metric("様子見 🟡", watch)
        s4.metric("非推奨 🔴", avoid)
        st.caption(f"並び替え基準: {sort_by}")
        st.divider()

        if results:
            st.subheader("🆚 上位銘柄比較")
            compare_count = min(8, len(results))
            compare_rows = build_compare_rows(results[:compare_count], sym)
            st.dataframe(compare_rows, use_container_width=True, hide_index=True)
            st.caption("上位8銘柄までを、4ブロック判定・MoS・PERで横比較しています。")
            st.divider()

        for rank, r in enumerate(results, 1):
            ve = r["verdict_en"]
            color = {"STRONG BUY":"#22c55e","BUY":"#3b82f6","WATCH":"#f59e0b","AVOID":"#ef4444"}.get(ve, "#94a3b8")
            mos_s = f"{r['mos']:+.1f}%" if r["mos"] is not None else "—"
            roe_s = f"{r['roe']*100:.1f}%" if r["roe"] else "—"
            pe_s = f"{r['pe']:.1f}x" if r["pe"] else "—"
            p_s = f"{sym}{r['price']:,.0f}" if r["price"] else "—"
            q_s = f"Q {r['quality_score']:.1f}/40"
            c_s = f"C {r['capital_score']:.1f}/25"
            rr_s = f"R {r['resilience_score']:.1f}/20"
            pr_s = f"P {r['price_score']:.1f}/15"
            c1, c2, c3, c4, c5, c6 = st.columns([0.4, 2.2, 1.9, 1.2, 1.1, 1.1])
            c1.markdown(f"**{rank}**")
            c2.markdown(f"**{r['ticker']}** {r['name']}  \\n`{r['profile']}`")
            c3.markdown(
                f'<span style="color:{color};font-weight:700">{r["verdict"]}</span> <strong>{r["score"]}/{r["max"]}</strong><br>'
                f'<span style="font-size:12px;color:#94a3b8">{q_s} · {c_s} · {rr_s} · {pr_s}</span>',
                unsafe_allow_html=True,
            )
            c4.markdown(f"MoS: `{mos_s}`  \\nPE: `{pe_s}`")
            c5.markdown(f"ROE: `{roe_s}`")
            c6.markdown(f"{p_s}")
            st.divider()

        safe_csv_download(
            results,
            f"screen_{sc_market.upper()}_{datetime.now().strftime('%Y%m%d')}.csv",
            label="📥 CSVダウンロード",
        )
