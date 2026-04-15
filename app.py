import streamlit as st
from buffett_analyzer.data.fetcher import fetch_ticker_data
from buffett_analyzer.scoring.scorer import run_all_modules
from buffett_analyzer.config import MARKET_CONFIGS

st.title("Buffett Score Analyzer")

market = st.selectbox("市場",["us","jp"])
ticker = st.text_input("銘柄コード")

if st.button("分析"):
    if market == "jp" and not ticker.endswitch(".T"):
        ticker += ".T"

    cfg = MARKET_CONFIGS[market]
    data = fetch_ticker_data(ticker)

    if data is None:
        st.error("データ取得失敗")
    else:
        result = run_all_modules(data,ticker,cfg)
        st.subheader("📊 分析結果")

        # データ取り出し
        data = result.__dict__ if hasattr(result, "__dict__") else result
        
        # 総合スコア(デカく表示)
        total = data.get("total_score") or data.get("score")
        if total:
            st.metric("総合スコア", total)
            
        st.divider()

        # 各項目をきれいに表示
        for key, value in data.items():
            if key in ["total_score", "score"]:
                continue
            st.write(f"▶ {key.upper()}: {value}")
