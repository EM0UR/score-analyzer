import pandas as pd
import numpy as np

def safe_row(df, *keys):
    """複数キー候補から最初に見つかった行を返す"""
    if df is None or df.empty: return None
    for k in keys:
        if k in df.index: return df.loc[k]
    return None

def ttm_sum(q_df, *keys):
    """四半期DataFrameから直近4Q合計(TTM)を計算する。失敗時はNone"""
    try:
        row = safe_row(q_df, *keys)
        if row is None: return None
        vals = row.dropna().iloc[:4]   # 最新4四半期（列は新しい順）
        if len(vals) < 2: return None
        return float(vals.sum())
    except Exception:
        return None

def ttm_latest(q_df, *keys):
    """四半期DataFrameから直近1Q の値を返す"""
    try:
        row = safe_row(q_df, *keys)
        if row is None: return None
        vals = row.dropna()
        if vals.empty: return None
        return float(vals.iloc[0])
    except Exception:
        return None

def annual_values(a_df, *keys, n=10):
    """年次DataFrameから最大n年分の数値リストを返す（新しい順）"""
    try:
        row = safe_row(a_df, *keys)
        if row is None: return []
        vals = row.dropna().iloc[:n]
        return [float(v) for v in vals]
    except Exception:
        return []

def cagr(values, years=None):
    """成長率 CAGR を計算する（valuesは新しい順）"""
    try:
        vals = [v for v in values if v and v > 0]
        if len(vals) < 2: return None
        n = years or (len(vals) - 1)
        return (vals[0] / vals[-1]) ** (1 / n) - 1
    except Exception:
        return None
