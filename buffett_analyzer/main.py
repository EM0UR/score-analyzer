# main.py — Buffett Score Analyzer エントリーポイント
import sys
import os
import logging
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

from config import MARKET_CONFIGS
from data.fetcher import fetch_ticker_data, clear_cache
from scoring.scorer import run_all_modules
from report.console_report import print_report


def select_market() -> str:
    print()
    print("╔══════════════════════════════════════╗")
    print("║   Buffett Score Analyzer  v1.0       ║")
    print("╠══════════════════════════════════════╣")
    print("║  [1]  US — 米国株 (e.g. AAPL, MSFT) ║")
    print("║  [2]  JP — 日本株 (e.g. 7203.T)     ║")
    print("╚══════════════════════════════════════╝")
    while True:
        choice = input("  市場を選択してください [1/2]: ").strip()
        if choice == "1":
            return "us"
        elif choice == "2":
            return "jp"
        else:
            print("  ⚠️  1 か 2 を入力してください。")


def main():
    parser = argparse.ArgumentParser(
        description="Buffett Score Analyzer — Warren Buffett 流投資スコアリングツール"
    )
    parser.add_argument("ticker", nargs="?", help="銘柄コード (例: AAPL, 7203.T)")
    parser.add_argument("--market", "-m", choices=["us", "jp"],
                        help="市場 (us / jp)。省略時はインタラクティブに選択。")
    parser.add_argument("--refresh", "-r", action="store_true",
                        help="キャッシュを無視して再取得する。")
    parser.add_argument("--clear-cache", action="store_true",
                        help="全キャッシュを削除して終了。")
    args = parser.parse_args()

    if args.clear_cache:
        clear_cache()
        return

    market = args.market or select_market()
    cfg = MARKET_CONFIGS[market]

    ticker = args.ticker
    if not ticker:
        ticker = input(f"\n  銘柄コードを入力してください [{market.upper()}]: ").strip()
    if not ticker:
        print("  銘柄コードが入力されていません。終了します。")
        return

    if market == "jp" and not ticker.upper().endswith(".T"):
        ticker = ticker + ".T"

    data = fetch_ticker_data(ticker, force_refresh=args.refresh)
    if data is None:
        print(f"\n  ❌ [{ticker}] データの取得に失敗しました。")
        print("     - ティッカーコードを確認してください。")
        print("     - しばらく待ってから再実行してください（API制限の可能性）。")
        return

    print(f"  [{ticker}] スコア計算中...")
    bd = run_all_modules(data, ticker, cfg)
    print_report(ticker, bd, market)

    while True:
        again = input("  別の銘柄を分析しますか？ [y/N]: ").strip().lower()
        if again != "y":
            print("\n  Buffett Score Analyzer を終了します。\n")
            break
        ticker2 = input(f"  銘柄コードを入力してください [{market.upper()}]: ").strip()
        if not ticker2:
            continue
        if market == "jp" and not ticker2.upper().endswith(".T"):
            ticker2 = ticker2 + ".T"
        data2 = fetch_ticker_data(ticker2, force_refresh=args.refresh)
        if data2 is None:
            print(f"  ❌ [{ticker2}] データの取得に失敗しました。")
            continue
        bd2 = run_all_modules(data2, ticker2, cfg)
        print_report(ticker2, bd2, market)


if __name__ == "__main__":
    main()
