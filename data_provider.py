DATA_PROVIDER_BUILD = "provider-20260417-2200-dcf-fallback"
import os
import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests
import yfinance as yf


DEFAULT_TIMEOUT = 15
USER_AGENT = "value-analyzer/1.0 (+educational use)"

CRITICAL_FIELDS = {
    "market_price": 1.5,
    "market_cap": 1.0,
    "shares_outstanding": 1.2,
    "pe_ratio": 0.8,
    "book_value_per_share": 0.8,
    "roe": 1.0,
    "debt_to_equity": 1.0,
    "current_ratio": 0.8,
    "operating_cash_flow": 1.0,
    "free_cash_flow": 1.4,
    "cash_and_equivalents": 0.8,
    "total_debt": 0.8,
    "dcf_intrinsic": 1.8,
}


@dataclass
class ProviderAudit:
    sources_used: List[str] = field(default_factory=list)
    field_sources: Dict[str, str] = field(default_factory=dict)
    derived_fields: List[str] = field(default_factory=list)
    missing_fields: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    fetch_errors: List[str] = field(default_factory=list)
    confidence: float = 0.0
    coverage_ratio: float = 0.0
    dcf_method: Optional[str] = None
    dcf_inputs: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sources_used": self.sources_used,
            "field_sources": self.field_sources,
            "derived_fields": self.derived_fields,
            "missing_fields": self.missing_fields,
            "warnings": self.warnings,
            "fetch_errors": self.fetch_errors,
            "confidence": round(self.confidence, 3),
            "coverage_ratio": round(self.coverage_ratio, 3),
            "dcf_method": self.dcf_method,
            "dcf_inputs": self.dcf_inputs,
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

        self._derive_missing_fields(result, audit)
        self._build_dcf(result, audit, market=market)
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
            "total_current_assets": None,
            "total_current_liabilities": None,
            "capital_expenditure": None,
            "dcf_intrinsic": None,
            "dcf_bear": None,
            "dcf_base": None,
            "dcf_bull": None,
            "margin_of_safety": None,
            "_fcf_history": [],
            "_revenue_history": [],
            "_dcf_source": None,
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

            if key in {"_fcf_history", "_revenue_history"}:
                current = result.get(key) or []
                merged = current if current else value
                if merged:
                    result[key] = merged
                    if key not in audit.field_sources:
                        audit.field_sources[key] = source
                continue

            if self._is_missing(result.get(key)) and not self._is_missing(value):
                result[key] = value
                audit.field_sources[key] = source

        result["data_sources"] = audit.sources_used[:]

    def _derive_missing_fields(self, result: Dict[str, Any], audit: ProviderAudit) -> None:
        self._derive(result, audit, "shares_outstanding", self._safe_div(result.get("market_cap"), result.get("market_price")))
        self._derive(result, audit, "market_cap", self._safe_mul(result.get("shares_outstanding"), result.get("market_price")))
        self._derive(result, audit, "book_value_per_share", self._safe_div(result.get("total_equity"), result.get("shares_outstanding")))
        self._derive(result, audit, "roe", self._ratio_pct(result.get("net_income"), result.get("total_equity")))
        self._derive(result, audit, "debt_to_equity", self._safe_div(result.get("total_debt"), result.get("total_equity")))
        self._derive(result, audit, "current_ratio", self._safe_div(result.get("total_current_assets"), result.get("total_current_liabilities")))
        self._derive(result, audit, "pe_ratio", self._safe_div(result.get("market_price"), result.get("eps")))
        self._derive(result, audit, "gross_margin", self._ratio_pct(None, None))
        self._derive(result, audit, "free_cash_flow", self._derive_fcf(result))
        self._derive(result, audit, "market_price", result.get("market_price") or None)

        if self._is_missing(result.get("gross_margin")):
            gm = None
            result["gross_margin"] = gm

        if self._is_missing(result.get("operating_margin")) and not self._is_missing(result.get("operating_cash_flow")) and not self._is_missing(result.get("revenue")) and result.get("revenue"):
            # CFO margin is not operating margin, so don't fabricate it.
            pass

        if self._is_missing(result.get("net_margin")):
            nm = self._ratio_pct(result.get("net_income"), result.get("revenue"))
            self._derive(result, audit, "net_margin", nm)

    def _derive_fcf(self, result: Dict[str, Any]) -> Optional[float]:
        fcf = result.get("free_cash_flow")
        if fcf is not None:
            return fcf

        op_cf = result.get("operating_cash_flow")
        capex = result.get("capital_expenditure")
        if op_cf is not None and capex is not None:
            return op_cf - abs(capex)
        return None

    def _derive(self, result: Dict[str, Any], audit: ProviderAudit, key: str, value: Optional[float]) -> None:
        if self._is_missing(result.get(key)) and not self._is_missing(value):
            result[key] = value
            audit.field_sources[key] = "derived"
            if key not in audit.derived_fields:
                audit.derived_fields.append(key)

    def _build_dcf(self, result: Dict[str, Any], audit: ProviderAudit, market: str = "us") -> None:
        if not self._is_missing(result.get("dcf_intrinsic")):
            audit.dcf_method = audit.dcf_method or "external_api"
            result["dcf_base"] = result.get("dcf_base") or result.get("dcf_intrinsic")
            if self._is_missing(result.get("dcf_bear")) and result.get("dcf_base") is not None:
                result["dcf_bear"] = result["dcf_base"] * 0.85
            if self._is_missing(result.get("dcf_bull")) and result.get("dcf_base") is not None:
                result["dcf_bull"] = result["dcf_base"] * 1.15
            result["_dcf_source"] = result.get("_dcf_source") or "external_api"
            return

        fcf_history = [x for x in (result.get("_fcf_history") or []) if x is not None and x > 0]
        current_fcf = result.get("free_cash_flow")

        if not fcf_history and current_fcf is not None and current_fcf > 0:
            fcf_history = [current_fcf]

        if not fcf_history:
            audit.warnings.append("DCF fallback skipped: positive free_cash_flow history unavailable")
            return

        base_fcf = self._normalized_fcf(fcf_history)
        if base_fcf is None or base_fcf <= 0:
            audit.warnings.append("DCF fallback skipped: normalized FCF is non-positive")
            return

        shares = result.get("shares_outstanding")
        if shares is None or shares <= 0:
            shares = self._safe_div(result.get("market_cap"), result.get("market_price"))
            if shares:
                result["shares_outstanding"] = shares
                audit.field_sources["shares_outstanding"] = "derived"
                if "shares_outstanding" not in audit.derived_fields:
                    audit.derived_fields.append("shares_outstanding")

        if shares is None or shares <= 0:
            audit.warnings.append("DCF fallback skipped: shares_outstanding unavailable")
            return

        base_growth = self._estimate_growth(fcf_history)
        discount_base = 0.10 if market.lower() == "us" else 0.09
        terminal_growth = 0.025 if market.lower() == "us" else 0.015

        scenarios = {
            "bear": {"growth": max(-0.01, base_growth - 0.03), "discount": discount_base + 0.015},
            "base": {"growth": base_growth, "discount": discount_base},
            "bull": {"growth": min(0.14, base_growth + 0.03), "discount": max(terminal_growth + 0.03, discount_base - 0.01)},
        }

        cash = result.get("cash_and_equivalents") or 0.0
        debt = result.get("total_debt") or 0.0

        prices = {}
        for name, cfg in scenarios.items():
            px = self._dcf_per_share(
                base_fcf=base_fcf,
                growth=cfg["growth"],
                discount=cfg["discount"],
                terminal_growth=terminal_growth,
                cash=cash,
                debt=debt,
                shares=shares,
                years=5,
            )
            if px is not None and px > 0:
                prices[name] = px

        if "base" not in prices:
            audit.warnings.append("DCF fallback failed: could not compute base scenario")
            return

        result["dcf_bear"] = prices.get("bear")
        result["dcf_base"] = prices.get("base")
        result["dcf_bull"] = prices.get("bull")
        result["dcf_intrinsic"] = prices.get("base")
        result["_dcf_source"] = "self_dcf_fallback"
        audit.dcf_method = "self_dcf_fallback"
        audit.field_sources["dcf_intrinsic"] = "derived_dcf"
        audit.field_sources["dcf_base"] = "derived_dcf"
        if result.get("dcf_bear") is not None:
            audit.field_sources["dcf_bear"] = "derived_dcf"
        if result.get("dcf_bull") is not None:
            audit.field_sources["dcf_bull"] = "derived_dcf"

        for k in ["dcf_intrinsic", "dcf_base", "dcf_bear", "dcf_bull"]:
            if k not in audit.derived_fields:
                audit.derived_fields.append(k)

        audit.dcf_inputs = {
            "base_fcf": round(base_fcf, 2),
            "fcf_history_count": len(fcf_history),
            "base_growth": round(base_growth, 4),
            "discount_rate": round(discount_base, 4),
            "terminal_growth": round(terminal_growth, 4),
            "cash": round(cash, 2),
            "debt": round(debt, 2),
            "shares": round(shares, 2),
        }

    def _dcf_per_share(
        self,
        base_fcf: float,
        growth: float,
        discount: float,
        terminal_growth: float,
        cash: float,
        debt: float,
        shares: float,
        years: int = 5,
    ) -> Optional[float]:
        if any(x is None for x in [base_fcf, discount, terminal_growth, shares]):
            return None
        if shares <= 0 or discount <= terminal_growth:
            return None
        if base_fcf <= 0:
            return None

        pv = 0.0
        fcf_t = base_fcf

        for year in range(1, years + 1):
            fcf_t = fcf_t * (1.0 + growth)
            pv += fcf_t / ((1.0 + discount) ** year)

        terminal_fcf = fcf_t * (1.0 + terminal_growth)
        terminal_value = terminal_fcf / (discount - terminal_growth)
        pv_terminal = terminal_value / ((1.0 + discount) ** years)

        equity_value = pv + pv_terminal + cash - debt
        if equity_value <= 0:
            return None

        per_share = equity_value / shares
        if not math.isfinite(per_share) or per_share <= 0:
            return None
        return per_share

    def _normalized_fcf(self, history: List[float]) -> Optional[float]:
        vals = [x for x in history if x is not None and x > 0]
        if not vals:
            return None
        window = vals[:3] if len(vals) >= 3 else vals
        try:
            return float(statistics.median(window))
        except Exception:
            return float(window[0])

    def _estimate_growth(self, history: List[float]) -> float:
        vals = [x for x in history if x is not None and x > 0]
        if len(vals) >= 3:
            newest = vals[0]
            oldest = vals[min(len(vals) - 1, 2)]
            years = min(len(vals) - 1, 2)
            if oldest > 0 and years > 0:
                cagr = (newest / oldest) ** (1 / years) - 1
                return max(0.02, min(0.10, cagr))
        if len(vals) >= 2 and vals[1] > 0:
            growth = (vals[0] / vals[1]) - 1
            return max(0.02, min(0.10, growth))
        return 0.04

    def _finalize(self, result: Dict[str, Any], audit: ProviderAudit) -> None:
        if result.get("dcf_intrinsic") is not None and result.get("market_price") is not None and result["dcf_intrinsic"] > 0:
            try:
                result["margin_of_safety"] = (result["dcf_intrinsic"] - result["market_price"]) / result["dcf_intrinsic"] * 100.0
                audit.field_sources["margin_of_safety"] = result.get("_dcf_source") or audit.field_sources.get("dcf_intrinsic", "computed")
            except Exception:
                audit.warnings.append("Failed to compute margin_of_safety")

        public_fields = [
            k for k in result.keys()
            if k not in {"ticker", "data_sources", "audit"} and not k.startswith("_")
        ]
        filled = [k for k in public_fields if not self._is_missing(result.get(k))]
        audit.missing_fields = [k for k in public_fields if self._is_missing(result.get(k))]
        audit.coverage_ratio = len(filled) / max(len(public_fields), 1)

        total_weight = sum(CRITICAL_FIELDS.values())
        hit_weight = sum(w for k, w in CRITICAL_FIELDS.items() if not self._is_missing(result.get(k)))
        weighted_ratio = hit_weight / total_weight if total_weight else 0.0

        raw_conf = (audit.coverage_ratio * 0.45) + (weighted_ratio * 0.55)

        if audit.fetch_errors:
            raw_conf *= 0.92
        if len(audit.missing_fields) >= 8:
            raw_conf *= 0.90
        if result.get("_dcf_source") == "self_dcf_fallback":
            raw_conf *= 0.96
        if self._is_missing(result.get("dcf_intrinsic")):
            raw_conf *= 0.90

        audit.confidence = max(0.0, min(1.0, raw_conf))
        result["audit"] = audit.to_dict()

    def _from_yfinance(self, symbol: str, audit: ProviderAudit) -> Dict[str, Any]:
        try:
            tk = yf.Ticker(symbol)
            info = tk.info or {}
            fast = getattr(tk, "fast_info", {}) or {}
            try:
                if not isinstance(fast, dict):
                    fast = dict(fast)
            except Exception:
                fast = {}

            income_df = self._get_df(tk, ["income_stmt", "financials"])
            balance_df = self._get_df(tk, ["balance_sheet"])
            cashflow_df = self._get_df(tk, ["cashflow"])

            income = self._first_df_col(income_df)
            balance = self._first_df_col(balance_df)
            cashflow = self._first_df_col(cashflow_df)

            shares = self._pick_num(info, ["sharesOutstanding", "impliedSharesOutstanding"])
            price = self._pick_num_from_objects([fast, info], ["lastPrice", "currentPrice", "regularMarketPrice", "previousClose"])
            equity = self._pick_series(balance, ["Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity"])
            debt = self._pick_series(balance, ["Total Debt", "Long Term Debt And Capital Lease Obligation", "Long Term Debt"])
            cur_assets = self._pick_series(balance, ["Current Assets", "Total Current Assets"])
            cur_liab = self._pick_series(balance, ["Current Liabilities", "Total Current Liabilities"])
            op_cf = self._pick_series(cashflow, ["Operating Cash Flow", "Total Cash From Operating Activities"])
            capex = self._pick_series(cashflow, ["Capital Expenditure", "Capital Expenditures"])
            fcf = self._pick_series(cashflow, ["Free Cash Flow"])
            if self._is_missing(fcf) and op_cf is not None and capex is not None:
                fcf = op_cf - abs(capex)

            net_income = self._pick_series(income, ["Net Income", "Net Income Common Stockholders"])
            revenue = self._pick_series(income, ["Total Revenue", "Operating Revenue"])

            roe = None
            if net_income is not None and equity not in (None, 0):
                roe = (net_income / equity) * 100.0

            de = None
            if debt is not None and equity not in (None, 0):
                de = debt / equity

            current_ratio = None
            if cur_assets is not None and cur_liab not in (None, 0):
                current_ratio = cur_assets / cur_liab

            fcf_history = self._fcf_history_from_yf(cashflow_df)
            rev_history = self._history_values_from_df(income_df, ["Total Revenue", "Operating Revenue"], limit=5)

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
                "roe": roe if roe is not None else self._percent_if_fraction(self._pick_num(info, ["returnOnEquity"])),
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
                "total_current_assets": cur_assets,
                "total_current_liabilities": cur_liab,
                "capital_expenditure": capex,
                "_fcf_history": fcf_history,
                "_revenue_history": rev_history,
            }
            return self._clean(out)
        except Exception as e:
            audit.fetch_errors.append(f"yfinance: {e}")
            return {}

    def _from_fmp(self, symbol: str, audit: ProviderAudit) -> Dict[str, Any]:
        try:
            quote = self._fmp_get(f"quote/{symbol}")
            profile = self._fmp_get(f"profile/{symbol}")
            key = self._fmp_get(f"key-metrics-ttm/{symbol}")
            ratios = self._fmp_get(f"ratios-ttm/{symbol}")
            dcf = self._fmp_get(f"discounted-cash-flow/{symbol}")
            income = self._fmp_get(f"income-statement/{symbol}", {"limit": 5})
            balance = self._fmp_get(f"balance-sheet-statement/{symbol}", {"limit": 1})
            cashflow = self._fmp_get(f"cash-flow-statement/{symbol}", {"limit": 5})

            q = self._first_record(quote)
            pf = self._first_record(profile)
            km = self._first_record(key)
            rt = self._first_record(ratios)
            dc = self._first_record(dcf)
            inc = self._first_record(income)
            bal = self._first_record(balance)
            cf = self._first_record(cashflow)

            fcf_history = self._fmp_history_values(cashflow, "freeCashFlow")
            if not fcf_history:
                fcf_history = self._fmp_fcf_fallback_history(cashflow)

            rev_history = self._fmp_history_values(income, "revenue")

            out = {
                "company_name": q.get("name") or pf.get("companyName"),
                "sector": pf.get("sector") or q.get("sector"),
                "industry": pf.get("industry") or q.get("industry"),
                "currency": q.get("currency"),
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
                "total_current_assets": self._to_num(bal.get("totalCurrentAssets")),
                "total_current_liabilities": self._to_num(bal.get("totalCurrentLiabilities")),
                "capital_expenditure": self._to_num(cf.get("capitalExpenditure")),
                "dcf_intrinsic": self._to_num(dc.get("dcf")),
                "dcf_base": self._to_num(dc.get("dcf")),
                "_fcf_history": fcf_history,
                "_revenue_history": rev_history,
                "_dcf_source": "fmp_api" if self._to_num(dc.get("dcf")) is not None else None,
            }
            return self._clean(out)
        except Exception as e:
            audit.fetch_errors.append(f"fmp: {e}")
            return {}

    def _from_alpha_vantage(self, symbol: str, audit: ProviderAudit) -> Dict[str, Any]:
        try:
            data = self._av_get("OVERVIEW", symbol)
            if not data or data.get("Note") or data.get("Information") or data.get("Error Message"):
                note = data.get("Note") or data.get("Information") or data.get("Error Message") or "empty response"
                audit.warnings.append(f"Alpha Vantage note: {note}")
                return {}

            out = {
                "company_name": data.get("Name"),
                "sector": data.get("Sector"),
                "industry": data.get("Industry"),
                "currency": data.get("Currency"),
                "market_cap": self._to_num(data.get("MarketCapitalization")),
                "shares_outstanding": self._to_num(data.get("SharesOutstanding")),
                "pe_ratio": self._to_num(data.get("PERatio")),
                "eps": self._to_num(data.get("EPS")),
                "book_value_per_share": self._to_num(data.get("BookValue")),
                "roe": self._percent_if_fraction(self._to_num(data.get("ReturnOnEquityTTM"))),
                "gross_margin": None,
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
        data = r.json()
        if isinstance(data, dict) and data.get("Error Message"):
            raise RuntimeError(data.get("Error Message"))
        return data

    def _av_get(self, function_name: str, symbol: str) -> Dict[str, Any]:
        params = {
            "function": function_name,
            "symbol": symbol,
            "apikey": self.alpha_vantage_api_key,
        }
        r = self.session.get("https://www.alphavantage.co/query", params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def _first_record(self, obj: Any) -> Dict[str, Any]:
        if isinstance(obj, list) and obj:
            first = obj[0]
            return first if isinstance(first, dict) else {}
        return obj if isinstance(obj, dict) else {}

    def _get_df(self, tk: Any, attrs: List[str]):
        for attr in attrs:
            try:
                obj = getattr(tk, attr)
                if callable(obj):
                    obj = obj()
                if obj is not None and hasattr(obj, "empty") and not obj.empty:
                    return obj
            except Exception:
                continue
        return None

    def _first_df_col(self, df: Any):
        if df is None:
            return None
        try:
            if hasattr(df, "empty") and not df.empty:
                return df.iloc[:, 0]
        except Exception:
            pass
        return None

    def _history_values_from_df(self, df: Any, row_names: List[str], limit: int = 5) -> List[float]:
        if df is None:
            return []
        try:
            for name in row_names:
                if name in df.index:
                    row = df.loc[name]
                    vals = []
                    for x in list(row.values)[:limit]:
                        n = self._to_num(x)
                        if n is not None:
                            vals.append(n)
                    return vals
        except Exception:
            return []
        return []

    def _fcf_history_from_yf(self, cashflow_df: Any, limit: int = 5) -> List[float]:
        vals = self._history_values_from_df(cashflow_df, ["Free Cash Flow"], limit=limit)
        if vals:
            return vals

        op = self._history_values_from_df(cashflow_df, ["Operating Cash Flow", "Total Cash From Operating Activities"], limit=limit)
        capex = self._history_values_from_df(cashflow_df, ["Capital Expenditure", "Capital Expenditures"], limit=limit)
        out = []
        for i in range(min(len(op), len(capex))):
            if op[i] is not None and capex[i] is not None:
                out.append(op[i] - abs(capex[i]))
        return out

    def _fmp_history_values(self, rows: Any, key: str, limit: int = 5) -> List[float]:
        if not isinstance(rows, list):
            return []
        vals = []
        for row in rows[:limit]:
            if not isinstance(row, dict):
                continue
            n = self._to_num(row.get(key))
            if n is not None:
                vals.append(n)
        return vals

    def _fmp_fcf_fallback_history(self, rows: Any, limit: int = 5) -> List[float]:
        if not isinstance(rows, list):
            return []
        vals = []
        for row in rows[:limit]:
            if not isinstance(row, dict):
                continue
            op_cf = self._to_num(row.get("operatingCashFlow"))
            capex = self._to_num(row.get("capitalExpenditure"))
            if op_cf is not None and capex is not None:
                vals.append(op_cf - abs(capex))
        return vals

    def _pick_series(self, series: Any, names: List[str]) -> Optional[float]:
        if series is None:
            return None
        for name in names:
            try:
                if name in getattr(series, "index", []):
                    return self._to_num(series.get(name))
            except Exception:
                continue
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

    def _ratio_pct(self, numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
        if numerator is None or denominator in (None, 0):
            return None
        return (numerator / denominator) * 100.0

    def _safe_div(self, a: Optional[float], b: Optional[float]) -> Optional[float]:
        if a is None or b in (None, 0):
            return None
        return a / b

    def _safe_mul(self, a: Optional[float], b: Optional[float]) -> Optional[float]:
        if a is None or b is None:
            return None
        return a * b

    def _clean(self,  Dict[str, Any]) -> Dict[str, Any]:
        out = {}
        for k, v in data.items():
            if k.startswith("_"):
                if isinstance(v, list) and v:
                    out[k] = v
                elif isinstance(v, str) and v:
                    out[k] = v
                continue
            if not self._is_missing(v):
                out[k] = v
        return out

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
            if s in {"", "None", "null", "NaN", "-", "N/A"}:
                return None
            return float(s)
        except Exception:
            return None


if __name__ == "__main__":
    provider = MultiSourceDataProvider()
    sample = provider.get_metrics("AAPL", market="us")
    for k, v in sample.items():
        if k != "audit":
            print(f"{k}: {v}")
    print(sample.get("audit", {}))
