# Buffett Score Analyzer v1.0
Warren Buffett の投資哲学に基づく株式スコアリングツール

## 必要パッケージのインストール
```
pip install yfinance colorama
```

## 実行方法
```bash
# ツール起動（インタラクティブ）
cd buffett_analyzer
python main.py

# 米国株を直接指定
python main.py AAPL --market us

# 日本株を直接指定
python main.py 7203 --market jp

# キャッシュを無視して最新データで再取得
python main.py MSFT --market us --refresh

# キャッシュ全消去
python main.py --clear-cache
```

## スコアリング基準（100点満点）
| モジュール             | 配点 | 主な指標                        |
|----------------------|------|---------------------------------|
| 収益の一貫性          | /20  | EPS CAGR・連続成長・マイナス年数 |
| 資本効率              | /20  | ROE・ROIC・営業利益率           |
| 財務健全性            | /15  | D/E比・自己資本比率・金利カバレッジ |
| Owner Earnings / FCF | /20  | FCF CAGR・FCFマージン・Yield    |
| 経済的堀（Moat）      | /15  | グロスマージン安定性・CapEx比率  |
| バリュエーション      | /10  | 2ステージDCF・MoS・PER          |
| 経営陣の資本配分      | /10  | 配当成長・自社株買い・ROE改善    |

## 投資判断基準
- 82点以上 → 強い買い 🟢
- 65〜81点 → 買い 🔵
- 48〜64点 → 様子見 🟡
- 48点未満 → 非推奨 🔴

## キャッシュについて
取得データは `~/.buffett_cache/` に24時間キャッシュされます。
API制限（429エラー）対策として、リクエスト間に自動でウェイトが入ります。

## 免責事項
このツールは教育・研究目的のものです。
実際の投資判断はご自身の責任で行ってください。
