# report/console_report.py — ターミナル出力レポート
from colorama import init, Fore, Style
init(autoreset=True)

BAR_WIDTH = 20

def _bar(score: int, max_score: int, width: int = BAR_WIDTH) -> str:
    filled = int(round(score / max_score * width))
    bar    = "█" * filled + "░" * (width - filled)
    pct    = score / max_score
    if pct >= 0.80:
        color = Fore.GREEN
    elif pct >= 0.55:
        color = Fore.CYAN
    elif pct >= 0.35:
        color = Fore.YELLOW
    else:
        color = Fore.RED
    return f"{color}[{bar}]{Style.RESET_ALL}"


def _status_icon(score: int, max_score: int) -> str:
    pct = score / max_score
    if pct >= 0.80: return "✅"
    elif pct >= 0.55: return "🔶"
    elif pct >= 0.35: return "⚠️ "
    else: return "❌"


def print_report(ticker: str, bd, market: str) -> None:
    """ScoreBreakdown を受け取り、ターミナルに詳細レポートを表示する。"""

    sep = "=" * 70
    thin = "─" * 70

    print()
    print(Fore.CYAN + Style.BRIGHT + sep)
    print(Fore.CYAN + Style.BRIGHT +
          f"  Buffett Score Analyzer  |  {ticker.upper()}  |  Market: {market.upper()}")
    print(Fore.CYAN + Style.BRIGHT + sep)
    print()

    modules = [
        ("収益の一貫性",       bd.earnings,   20),
        ("資本効率",           bd.capital,    20),
        ("財務健全性",         bd.health,     15),
        ("Owner Earnings / FCF", bd.oe,       20),
        ("経済的堀（Moat）",   bd.moat,       15),
        ("バリュエーション",   bd.valuation,  10),
        ("経営陣の資本配分",   bd.management, 10),
    ]

    label_w = 26

    for name, mod, max_s in modules:
        s   = mod.get("score", 0)
        bar = _bar(s, max_s)
        icon = _status_icon(s, max_s)
        label = f"{name:<{label_w}}"
        score_str = f"{s:>2}/{max_s}"
        print(f"  {Fore.WHITE}{label}{Style.RESET_ALL} {bar} "
              f"{Fore.WHITE}{score_str}{Style.RESET_ALL}  {icon}")
        detail = mod.get("detail", "")
        if detail:
            print(f"  {' ' * label_w}  {Fore.WHITE + Style.DIM}{detail}{Style.RESET_ALL}")
        print()

    print(thin)

    total = bd.total
    if total >= 82:
        tc = Fore.GREEN + Style.BRIGHT
    elif total >= 65:
        tc = Fore.CYAN + Style.BRIGHT
    elif total >= 48:
        tc = Fore.YELLOW + Style.BRIGHT
    else:
        tc = Fore.RED + Style.BRIGHT

    print(f"  総合スコア  :  {tc}{total} / 100{Style.RESET_ALL}")
    print(f"  投資判断   :  {tc}{bd.verdict}{Style.RESET_ALL}")
    print()
    print(f"  {Fore.WHITE}コメント{Style.RESET_ALL}: {bd.verdict_comment()}")
    print(sep)
    print()
