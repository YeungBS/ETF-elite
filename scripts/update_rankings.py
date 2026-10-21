import json
import math
import os
from datetime import datetime, timezone

import akshare as ak
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST = os.path.join(ROOT, "config", "watchlist.txt")
OUTPUT = os.path.join(ROOT, "data", "results.json")


def load_codes():
    with open(WATCHLIST, "r", encoding="utf-8") as f:
        return [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]


def get_history(code):
    df = ak.fund_etf_hist_em(
        symbol=code,
        period="daily",
        adjust="",
    )
    if df is None or df.empty:
        raise ValueError("行情源没有返回数据")

    df = df.rename(columns={
        "日期": "date",
        "收盘": "close",
    })
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["close"]).sort_values("date")
    if len(df) < 60:
        raise ValueError("有效历史数据不足60个交易日")
    return df


def score_history(code, df):
    close = df["close"]
    last = float(close.iloc[-1])

    def ret(days):
        if len(close) <= days:
            return None
        return round((last / float(close.iloc[-days - 1]) - 1) * 100, 2)

    ma20 = float(close.tail(20).mean())
    ma60 = float(close.tail(60).mean())
    returns = close.pct_change().dropna().tail(20)
    vol = float(returns.std() * math.sqrt(252) * 100)

    peak = close.tail(20).cummax()
    drawdown = float(((close.tail(20) / peak) - 1).min() * 100)

    r5 = ret(5)
    r20 = ret(20)
    r60 = ret(60)

    score = (
        (r20 or 0) * 0.35
        + (r60 or 0) * 0.25
        + (r5 or 0) * 0.15
        + (10 if last > ma20 else 0)
        + (10 if ma20 > ma60 else 0)
        - vol * 0.10
        + drawdown * 0.20
    )

    if last > ma20 and ma20 > ma60:
        signal = "趋势偏强"
    elif last < ma20 and ma20 < ma60:
        signal = "趋势偏弱"
    else:
        signal = "震荡观察"

    return {
        "code": code,
        "date": df["date"].iloc[-1].strftime("%Y-%m-%d"),
        "close": round(last, 4),
        "return_5d_pct": r5,
        "return_20d_pct": r20,
        "return_60d_pct": r60,
        "ma20": round(ma20, 4),
        "ma60": round(ma60, 4),
        "annualized_volatility_pct": round(vol, 2),
        "drawdown_20d_pct": round(drawdown, 2),
        "score": round(score, 2),
        "signal": signal,
    }


def main():
    results = []
    errors = []

    for code in load_codes():
        try:
            df = get_history(code)
            results.append(score_history(code, df))
            print(f"OK {code}: {results[-1]['date']}")
        except Exception as exc:
            errors.append({"code": code, "error": str(exc)})
            print(f"FAILED {code}: {exc}")

    results.sort(key=lambda x: x["score"], reverse=True)

    if not results:
        raise RuntimeError(
            "所有ETF均获取失败，请检查行情源或watchlist；详情见前面的日志"
        )

    for index, item in enumerate(results, start=1):
        item["rank"] = index

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    payload = {
        "status": "ok",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "data_date": max(item["date"] for item in results),
        "count": len(results),
        "rankings": results,
        "errors": errors,
        "disclaimer": "参考指标和启发式评分，不构成投资建议。",
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"成功获取 {len(results)} 只ETF，失败 {len(errors)} 只。")
    print(f"数据文件已写入: {OUTPUT}")


if __name__ == "__main__":
    main()
