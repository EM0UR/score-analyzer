# buffett_analyzer/screener/universe.py

SP500_UNIVERSE = {
    # テクノロジー
    "AAPL":"Apple","MSFT":"Microsoft","GOOGL":"Alphabet","META":"Meta","NVDA":"NVIDIA",
    "AVGO":"Broadcom","ORCL":"Oracle","IBM":"IBM","CRM":"Salesforce","ADBE":"Adobe",
    "TXN":"Texas Instruments","QCOM":"Qualcomm","AMD":"AMD","INTC":"Intel","MU":"Micron",
    # ヘルスケア
    "JNJ":"Johnson & Johnson","UNH":"UnitedHealth","LLY":"Eli Lilly","ABBV":"AbbVie",
    "MRK":"Merck","PFE":"Pfizer","TMO":"Thermo Fisher","ABT":"Abbott","DHR":"Danaher",
    "BMY":"Bristol-Myers Squibb","MDT":"Medtronic",
    # 消費財（必需品）
    "PG":"Procter & Gamble","KO":"Coca-Cola","PEP":"PepsiCo","WMT":"Walmart",
    "MCD":"McDonald's","MDLZ":"Mondelez","CL":"Colgate","KMB":"Kimberly-Clark","GIS":"General Mills",
    # 金融
    "BRK-B":"Berkshire Hathaway","JPM":"JPMorgan","BAC":"Bank of America","WFC":"Wells Fargo",
    "GS":"Goldman Sachs","MS":"Morgan Stanley","AXP":"American Express",
    "V":"Visa","MA":"Mastercard","BLK":"BlackRock","CB":"Chubb",
    # 一般消費財
    "AMZN":"Amazon","TSLA":"Tesla","NKE":"Nike","SBUX":"Starbucks",
    "HD":"Home Depot","LOW":"Lowe's","TGT":"Target","BKNG":"Booking Holdings","COST":"Costco",
    # 資本財・エネルギー
    "CAT":"Caterpillar","HON":"Honeywell","UPS":"UPS","BA":"Boeing","GE":"GE Aerospace",
    "MMM":"3M","RTX":"RTX","LMT":"Lockheed Martin",
    "XOM":"ExxonMobil","CVX":"Chevron","COP":"ConocoPhillips",
    # 通信・メディア
    "NFLX":"Netflix","DIS":"Disney","CMCSA":"Comcast","T":"AT&T","VZ":"Verizon",
    # 公益・不動産
    "AMT":"American Tower","NEE":"NextEra Energy","DUK":"Duke Energy",
}

TOPIX100_UNIVERSE = {
    # 精密・電機
    "6861.T":"キーエンス","6758.T":"ソニーG","6954.T":"ファナック","8035.T":"東京エレクトロン",
    "6857.T":"アドバンテスト","6723.T":"ルネサス","6762.T":"TDK","6501.T":"日立","6702.T":"富士通",
    "6503.T":"三菱電機","7751.T":"キヤノン","7974.T":"任天堂","4543.T":"テルモ","6645.T":"オムロン",
    "6902.T":"デンソー","6752.T":"パナソニックHD","6971.T":"京セラ","6594.T":"ニデック",
    # 半導体・素材
    "4063.T":"信越化学工業","5713.T":"住友金属鉱山",
    # 自動車
    "7203.T":"トヨタ自動車","7267.T":"ホンダ","7269.T":"スズキ","7270.T":"SUBARU",
    # 商社
    "8058.T":"三菱商事","8001.T":"伊藤忠商事","8002.T":"丸紅","8053.T":"住友商事","8031.T":"三井物産",
    # 金融・保険
    "8306.T":"三菱UFJFG","8316.T":"三井住友FG","8411.T":"みずほFG",
    "8766.T":"東京海上HD","8750.T":"第一生命HD",
    # 医薬品
    "4519.T":"中外製薬","4568.T":"第一三共","4502.T":"武田薬品","4503.T":"アステラス","7741.T":"HOYA",
    # 通信・IT
    "9432.T":"NTT","9433.T":"KDDI","9434.T":"ソフトバンク","9984.T":"ソフトバンクG",
    "4307.T":"野村総研","9613.T":"NTTデータG",
    # 消費・小売
    "9983.T":"ファーストリテイリング","3382.T":"セブン&アイHD","2914.T":"JT",
    "2802.T":"味の素","2503.T":"キリンHD",
    # 機械・重工
    "7011.T":"三菱重工","6326.T":"クボタ",
    # 化学
    "4188.T":"三菱ケミカルG","5401.T":"日本製鉄",
}

SECTOR_MAP_US = {
    "AAPL":"Technology","MSFT":"Technology","GOOGL":"Technology","META":"Technology",
    "NVDA":"Technology","AVGO":"Technology","ORCL":"Technology","IBM":"Technology",
    "CRM":"Technology","ADBE":"Technology","TXN":"Technology","QCOM":"Technology",
    "AMD":"Technology","INTC":"Technology","MU":"Technology",
    "JNJ":"Healthcare","UNH":"Healthcare","LLY":"Healthcare","ABBV":"Healthcare",
    "MRK":"Healthcare","PFE":"Healthcare","TMO":"Healthcare","ABT":"Healthcare",
    "DHR":"Healthcare","BMY":"Healthcare","MDT":"Healthcare",
    "PG":"Consumer Staples","KO":"Consumer Staples","PEP":"Consumer Staples",
    "WMT":"Consumer Staples","MCD":"Consumer Discretionary","MDLZ":"Consumer Staples",
    "CL":"Consumer Staples","KMB":"Consumer Staples","GIS":"Consumer Staples",
    "BRK-B":"Financials","JPM":"Financials","BAC":"Financials","WFC":"Financials",
    "GS":"Financials","MS":"Financials","AXP":"Financials","V":"Financials",
    "MA":"Financials","BLK":"Financials","CB":"Financials",
    "AMZN":"Consumer Discretionary","TSLA":"Consumer Discretionary","NKE":"Consumer Discretionary",
    "SBUX":"Consumer Discretionary","HD":"Consumer Discretionary","LOW":"Consumer Discretionary",
    "TGT":"Consumer Discretionary","BKNG":"Consumer Discretionary","COST":"Consumer Discretionary",
    "CAT":"Industrials","HON":"Industrials","UPS":"Industrials","BA":"Industrials",
    "GE":"Industrials","MMM":"Industrials","RTX":"Industrials","LMT":"Industrials",
    "XOM":"Energy","CVX":"Energy","COP":"Energy",
    "NFLX":"Communication","DIS":"Communication","CMCSA":"Communication",
    "T":"Communication","VZ":"Communication",
    "AMT":"Real Estate","NEE":"Utilities","DUK":"Utilities",
}

SECTOR_MAP_JP = {
    "6861.T":"精密機器","6758.T":"電気機器","6954.T":"精密機器","8035.T":"電気機器",
    "6857.T":"電気機器","6723.T":"電気機器","6762.T":"電気機器","6501.T":"電気機器",
    "6702.T":"電気機器","6503.T":"電気機器","7751.T":"精密機器","7974.T":"情報通信",
    "4543.T":"医療機器","6645.T":"電気機器","6902.T":"輸送用機器","6752.T":"電気機器",
    "6971.T":"電気機器","6594.T":"電気機器","4063.T":"化学","5713.T":"非鉄金属",
    "7203.T":"輸送用機器","7267.T":"輸送用機器","7269.T":"輸送用機器","7270.T":"輸送用機器",
    "8058.T":"卸売業","8001.T":"卸売業","8002.T":"卸売業","8053.T":"卸売業","8031.T":"卸売業",
    "8306.T":"銀行業","8316.T":"銀行業","8411.T":"銀行業",
    "8766.T":"保険業","8750.T":"保険業",
    "4519.T":"医薬品","4568.T":"医薬品","4502.T":"医薬品","4503.T":"医薬品","7741.T":"精密機器",
    "9432.T":"情報通信","9433.T":"情報通信","9434.T":"情報通信","9984.T":"情報通信",
    "4307.T":"情報通信","9613.T":"情報通信",
    "9983.T":"小売業","3382.T":"小売業","2914.T":"食料品","2802.T":"食料品","2503.T":"食料品",
    "7011.T":"機械","6326.T":"機械","4188.T":"化学","5401.T":"鉄鋼",
}

def get_universe(market: str) -> dict:
    return SP500_UNIVERSE if market == "us" else TOPIX100_UNIVERSE

def get_sector(ticker: str, market: str) -> str:
    if market == "us":
        return SECTOR_MAP_US.get(ticker, "Other")
    return SECTOR_MAP_JP.get(ticker, "その他")
