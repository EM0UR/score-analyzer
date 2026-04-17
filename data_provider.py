import os
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import requests
import yfinance as yf


DEFAULT_TIMEOUT = 12
USER_AGENT = "value-analyzer/0.6 (+educational use)"


CRITICAL_FIELDS = {
    "market_price": 1.5,
    "pe_ratio": 1.0,
    "roe": 1.0,
    "debt_to_equity": 1.0,
    "shares_outstanding": 1.0,
    "free_cash_flow": 1.2,
    "operating_cash_flow": 0.8,
    "market_cap": 0.8,
    "dcf_intrinsic": 1.5,
}


@dataclass
class ProviderAudit:
    sources_used: List[str] = field(default_factory=list)
    field_sources: Dict[str, str] = field(default_factory=dict)
    missing_fields: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    fetch_errors: List[str] = field(default_factory=list)
    confidence: float = 0.0
    coverage_ratio: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sources_used": self.sources_used,
            "field_sources": self.field_sources,
            "missing_fields": self.missing_fields,
            "warnings": self.warnings,
            "fetch_errors": self.fetch_errors,
            "confidence": round(self.confidence, 3),
            "coverage_ratio": round(self.coverage_ratio, 3),
        }


class MultiSourceDataProvider:
    def __init__(
        self,
        fmp_api_key: Optional[str] = None,
        alpha_vantage_api_key: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.fmp_api_key = fmp_api_key or os.getenv("FMP_API_KEY", "")
        self.alpha_vantage_api_key = alpha_vantage_api_key or os.getenv("ALPHAVANTAGE_API_KEY", "")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def get_metrics(self, ticker: str, market: str = "us") -> Dict[str, Any]:
        symbol = self._normalize_symbol(ticker, market)
        audit = ProviderAudit()
        result = self._empty_result(symbol)

        yf_data = self._from_yfinance(symbol, audit)
        self._merge(result, yf_data, "yfinance", audit)

        if self.fmp_api_key:
            fmp_data = self._from_fmp(symbol, audit)
            self._merge(result, fmp_data, "fmp", audit)
        else:
            audit.warnings.append("FMP_API_KEY is missing; FMP fallback skipped")

        if self.alpha_vantage_api_key:
            av_data = self._from_alpha_vantage(symbol, audit)
            self._merge(result, av_data, "alpha_vantage", audit)
        else:
            audit.warnings.append("ALPHAVANTAGE_API_KEY is missing; Alpha Vantage fallback skipped")

        self._finalize(result, audit)
        return result

    def _empty_result(self, symbol: str) -> Dict[str, Any]:
        return {
            "ticker": symbol,
            "company_name": None,
            "sector": None,
            "industry": None,
            "currency": None,
            "market_price": None,
            "market_cap": None,
            "shares_outstanding": None,
            "pe_ratio": None,
            "eps": None,
            "book_value_per_share": None,
            "roe": None,
            "debt_to_equity": None,
            "current_ratio": None,
            "gross_margin": None,
            "operating_margin": None,
            "net_margin": None,
            "revenue": None,
            "net_income": None,
            "operating_cash_flow": None,
            "free_cash_flow": None,
            "cash_and_equivalents": None,
            "total_debt": None,
            "total_equity": None,
            "dcf_intrinsic": None,
            "dcf_bear": None,
            "dcf_base": None,
            "dcf_bull": None,
            "margin_of_safety": None,
            "data_sources": [],
            "audit": {},
        }

    def _normalize_symbol(self, ticker: str, market: str) -> str:
        t = (ticker or "").strip().upper()
        if market.lower() == "jp" and t.isdigit() and not t.endswith(".T"):
            return f"{t}.T"
        return t

    def _merge(self, result: Dict[str, Any], incoming: Dict[str, Any], source: str, audit: ProviderAudit) -> None:
        if not incoming:
            return
        if source not in audit.sources_used:
            audit.sources_used.append(source)
        for key, value in incoming.items():
            if key not in result:
                continue
            if self._is_missing(result.get(key)) and not self._is_missing(value):
                result[key] = value
                audit.field_sources[key] = source
        result["data_sources"] = audit.sources_used[:]

    def _finalize(self, result: Dict[str, Any], audit: ProviderAudit) -> None:
        if result.get("dcf_intrinsic") and result.get("market_price"):
            try:
                result["margin_of_safety"] = (result["dcf_intrinsic"] - result["market_price"]) / result["dcf_intrinsic"] * 100.0
            except Exception:
                audit.warnings.append("Failed to compute margin_of_safety")

        all_fields = [k for k in result.keys() if k not in {"ticker", "data_sources", "audit"}]
        filled = [k for k in all_fields if not self._is_missing(result.get(k))]
        audit.missing_fields = [k for k in all_fields if self._is_missing(result.get(k))]
        audit.coverage_ratio = len(filled) / max(len(all_fields), 1)

        total_weight = sum(CRITICAL_FIELDS.values())
        hit_weight = sum(w for k, w in CRITICAL_FIELDS.items() if not self._is_missing(result.get(k)))
        weighted_ratio = hit_weight / total_weight if total_weight else 0.0
        raw_conf = (audit.coverage_ratio * 0.45) + (weighted_ratio * 0.55)
        if audit.fetch_errors:
            raw_conf *= 0.92
        if len(audit.missing_fields) >= 8:
            raw_conf *= 0.9
        audit.confidence = max(0.0, min(1.0, raw_conf))
        result["audit"] = audit.to_dict()

    def _from_yfinance(self, symbol: str, audit: ProviderAudit) -> Dict[str, Any]:
        try:
            tk = yf.Ticker(symbol)
            info = tk.info or {}
            fast = getattr(tk, "fast_info", {}) or {}
            income = self._first_df_row(tk, ["income_stmt", "financials"])
            balance = self._first_df_row(tk, ["balance_sheet"])
            cashflow = self._first_df_row(tk, ["cashflow"])

            shares = self._pick_num(info, ["sharesOutstanding", "impliedSharesOutstanding"])
            price = self._pick_num_from_objects([fast, info], ["lastPrice", "currentPrice", "regularMarketPrice", "previousClose"])
            equity = self._pick_series(balance, ["Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity"])
            debt = self._pick_series(balance, ["Total Debt", "Long Term Debt And Capital Lease Obligation", "Long Term Debt"])
            cur_assets = self._pick_series(balance, ["Current Assets", "Total Current Assets"])
            cur_liab = self._pick_series(balance, ["Current Liabilities", "Total Current Liabilities"])
            op_cf = self._pick_series(cashflow, ["Operating Cash Flow", "Total Cash From Operating Activities"])
            fcf = self._pick_series(cashflow, ["Free Cash Flow"])
            if self._is_missing(fcf):
                capex = self._pick_series(cashflow, ["Capital Expenditure", "Capital Expenditures"])
                if not self._is_missing(op_cf) and not self._is_missing(capex):
                    fcf = op_cf - abs(capex)

            net_income = self._pick_series(income, ["Net Income", "Net Income Common Stockholders"])
            revenue = self._pick_series(income, ["Total Revenue", "Operating Revenue"])

            roe = None
            if not self._is_missing(net_income) and not self._is_missing(equity) and equity:
                roe = (net_income / equity) * 100.0

            de = None
            if not self._is_missing(debt) and not self._is_missing(equity) and equity:
                de = debt / equity

            current_ratio = None
            if not self._is_missing(cur_assets) and not self._is_missing(cur_liab) and cur_liab:
                current_ratio = cur_assets / cur_liab

            out = {
                "company_name": info.get("shortName") or info.get("longName"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "currency": info.get("currency"),
                "market_price": price,
                "market_cap": self._pick_num(info, ["marketCap"]),
                "shares_outstanding": shares,
                "pe_ratio": self._pick_num(info, ["trailingPE", "forwardPE"]),
                "eps": self._pick_num(info, ["trailingEps", "forwardEps"]),
                "book_value_per_share": self._pick_num(info, ["bookValue"]),
                "roe": roe if roe is not None else self._pick_num(info, ["returnOnEquity"]),
                "debt_to_equity": de if de is not None else self._scaled_ratio(info.get("debtToEquity"), divisor=100.0),
                "current_ratio": current_ratio if current_ratio is not None else self._pick_num(info, ["currentRatio"]),
                "gross_margin": self._scaled_ratio(info.get("grossMargins"), multiplier=100.0),
                "operating_margin": self._scaled_ratio(info.get("operatingMargins"), multiplier=100.0),
                "net_margin": self._scaled_ratio(info.get("profitMargins"), multiplier=100.0),
                "revenue": revenue,
                "net_income": net_income,
                "operating_cash_flow": op_cf,
                "free_cash_flow": fcf if fcf is not None else self._pick_num(info, ["freeCashflow"]),
                "cash_and_equivalents": self._pick_series(balance, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments", "Cash"]),
                "total_debt": debt,
                "total_equity": equity,
            }
            return self._clean(out)
        except Exception as e:
            audit.fetch_errors.append(f"yfinance: {e}")
            return {}

    def _from_fmp(self, symbol: str, audit: ProviderAudit) -> Dict[str, Any]:
        try:
            quote = self._fmp_get(f"quote/{symbol}")
            key = self._fmp_get(f"key-metrics-ttm/{symbol}")
            ratios = self._fmp_get(f"ratios-ttm/{symbol}")
            dcf = self._fmp_get(f"discounted-cash-flow/{symbol}")
            income = self._fmp_get(f"income-statement/{symbol}", {"limit": 1})
            balance = self._fmp_get(f"balance-sheet-statement/{symbol}", {"limit": 1})
            cashflow = self._fmp_get(f"cash-flow-statement/{symbol}", {"limit": 1})

            q = quote[0] if isinstance(quote, list) and quote else {}
            km = key[0] if isinstance(key, list) and key else {}
            rt = ratios[0] if isinstance(ratios, list) and ratios else {}
            dc = dcf[0] if isinstance(dcf, list) and dcf else {}
            inc = income[0] if isinstance(income, list) and income else {}
            bal = balance[0] if isinstance(balance, list) and balance else {}
            cf = cashflow[0] if isinstance(cashflow, list) and cashflow else {}

            out = {
                "company_name": q.get("name"),
                "market_price": self._to_num(q.get("price")),
                "market_cap": self._to_num(q.get("marketCap")),
                "shares_outstanding": self._to_num(km.get("sharesOutstanding")),
                "pe_ratio": self._to_num(rt.get("peRatioTTM") or km.get("peRatioTTM") or q.get("pe")),
                "eps": self._to_num(q.get("eps")),
                "book_value_per_share": self._to_num(km.get("bookValuePerShareTTM")),
                "roe": self._percent_if_fraction(self._to_num(rt.get("returnOnEquityTTM"))),
                "debt_to_equity": self._to_num(rt.get("debtEquityRatioTTM") or km.get("debtToEquity")),
                "current_ratio": self._to_num(rt.get("currentRatioTTM")),
                "gross_margin": self._percent_if_fraction(self._to_num(rt.get("grossProfitMarginTTM"))),
                "operating_margin": self._percent_if_fraction(self._to_num(rt.get("operatingProfitMarginTTM"))),
                "net_margin": self._percent_if_fraction(self._to_num(rt.get("netProfitMarginTTM"))),
                "revenue": self._to_num(inc.get("revenue")),
                "net_income": self._to_num(inc.get("netIncome")),
                "operating_cash_flow": self._to_num(cf.get("operatingCashFlow")),
                "free_cash_flow": self._to_num(cf.get("freeCashFlow")),
                "cash_and_equivalents": self._to_num(bal.get("cashAndCashEquivalents")),
                "total_debt": self._to_num(bal.get("totalDebt")),
                "total_equity": self._to_num(bal.get("totalStockholdersEquity")),
                "dcf_intrinsic": self._to_num(dc.get("dcf")),
                "dcf_base": self._to_num(dc.get("dcf")),
                "sector": q.get("sector"),
                "industry": q.get("industry"),
                "currency": q.get("currency"),
            }
            return self._clean(out)
        except Exception as e:
            audit.fetch_errors.append(f"fmp: {e}")
            return {}

    def _from_alpha_vantage(self, symbol: str, audit: ProviderAudit) -> Dict[str, Any]:
        try:
            data = self._av_get("OVERVIEW", symbol)
            if not data or data.get("Note") or data.get("Information"):
                note = data.get("Note") or data.get("Information") or "empty response"
                audit.warnings.append(f"Alpha Vantage note: {note}")
                return {}
            out = {
                "company_name": data.get("Name"),
                "sector": data.get("Sector"),
                "industry": data.get("Industry"),
                "currency": data.get("Currency"),
                "market_cap": self._to_num(data.get("MarketCapitalization")),
                "pe_ratio": self._to_num(data.get("PERatio")),
                "eps": self._to_num(data.get("EPS")),
                "book_value_per_share": self._to_num(data.get("BookValue")),
                "roe": self._to_num(data.get("ReturnOnEquityTTM")),
                "debt_to_equity": self._safe_div(self._to_num(data.get("TotalDebt")), self._to_num(data.get("BookValue"))),
                "gross_margin": self._to_num(data.get("GrossProfitTTM")),
            }
            return self._clean(out)
        except Exception as e:
            audit.fetch_errors.append(f"alpha_vantage: {e}")
            return {}

    def _fmp_get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        params = dict(params or {})
        params["apikey"] = self.fmp_api_key
        url = f"https://financialmodelingprep.com/api/v3/{path}"
        r = self.session.get(url, params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def _av_get(self, function_name: str, symbol: str) -> Dict[str, Any]:
        params = {
            "function": function_name,
            "symbol": symbol,
            "apikey": self.alpha_vantage_api_key,
        }
        r = self.session.get("https://www.alphavantage.co/query", params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def _first_df_row(self, tk: Any, attrs: List[str]):
        for attr in attrs:
            try:
                obj = getattr(tk, attr)
                if callable(obj):
                    obj = obj()
                if obj is not None and hasattr(obj, "empty") and not obj.empty:
                    return obj.iloc[:, 0]
            except Exception:
                continue
        return None

    def _pick_series(self, series: Any, names: List[str]) -> Optional[float]:
        if series is None:
            return None
        for name in names:
            if name in getattr(series, "index", []):
                return self._to_num(series.get(name))
        return None

    def _pick_num(self, mapping: Dict[str, Any], names: List[str]) -> Optional[float]:
        for name in names:
            if name in mapping:
                value = self._to_num(mapping.get(name))
                if value is not None:
                    return value
        return None

    def _pick_num_from_objects(self, objects: List[Dict[str, Any]], names: List[str]) -> Optional[float]:
        for obj in objects:
            value = self._pick_num(obj or {}, names)
            if value is not None:
                return value
        return None

    def _scaled_ratio(self, value: Any, multiplier: float = 1.0, divisor: float = 1.0) -> Optional[float]:
        n = self._to_num(value)
        if n is None:
            return None
        n = n / divisor
        return n * multiplier

    def _percent_if_fraction(self, value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        if -1.5 <= value <= 1.5:
            return value * 100.0
        return value

    def _safe_div(self, a: Optional[float], b: Optional[float]) -> Optional[float]:
        if a is None or b in (None, 0):
            return None
        return a / b

    def _clean(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in data.items() if not self._is_missing(v)}

    def _is_missing(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return True
        if value == "":
            return True
        return False

    def _to_num(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                return None
            return float(value)
        try:
            s = str(value).replace(",", "").replace("%", "").strip()
            if s in {"", "None", "null", "NaN", "-"}:
                return None
            return float(s)
        except Exception:
            return None


if __name__ == "__main__":
    provider = MultiSourceDataProvider()
    sample = provider.get_metrics("AAPL")
    for k, v in sample.items():
        print(f"{k}: {v}")
