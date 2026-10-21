import json
import math
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import akshare as ak
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
WATCHLIST = ROOT / "config" / "watchlist.txt"
OUT = ROOT / "data" / "results.json"
CST = timezone(timedelta(hours=8))

# This is a research ranking, not a price forecast or order instruction.
def pct(a, b):
    return (a / b - 1.0) * 100.0 if b and math.isfinite(b) else 0.0

def minmax(values, low=-1.0, high=1.0):
    return max(low, min(high, values))

def load_codes():
    return [line.strip() for line in WATCHLIST.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]

def get_hist(code):
    # AKShare wraps public Eastmoney historical daily ETF quotes.
    df = ak.fund_etf_hist_em(
        symbol=code, period="daily",
        start_date=(datetime.now(CST) - timedelta(days=260)).strftime("%Y%m%d"),
        end_date=datetime.now(CST).strftime("%Y%m%d"), adjust="qfq"
    )
    if df is None or df.empty:
        raise ValueError("empty history")
    df = df.rename(columns={"日期":"date", "收盘":"close", "成交额":"amount", "成交量":"volume"})
    for c in ("date", "close"):
        if c not in df.columns:
            raise ValueError("missing column " + c)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["date", "close"]).sort_values("date").drop_duplicates("date")
    if len(df) < 65:
        raise ValueError("not enough daily rows")
    return df

def score_one(code, df, benchmark_returns):
    close = df["close"].astype(float)
    last = float(close.iloc[-1])
    latest_date = df["date"].iloc[-1].strftime("%Y-%m-%d")
    ret5 = pct(last, float(close.iloc[-6]))
    ret20 = pct(last, float(close.iloc[-21]))
    ret60 = pct(last, float(close.iloc[-61]))
    ma20 = float(close.tail(20).mean())
    ma60 = float(close.tail(60).mean())
    trend = "上行" if last > ma20 > ma60 else ("修复中" if last > ma20 else "偏弱")
    returns = close.pct_change().dropna()
    vol20 = float(returns.tail(20).std() * math.sqrt(252) * 100) if len(returns) >= 20 else 0.0
    roll_max = close.tail(20).max()
    dd20 = (last / float(roll_max) - 1) * 100 if roll_max else 0.0
    relative = ret20 - benchmark_returns
    # Scaled, capped score so one extreme return cannot dominate completely.
    momentum = 0.55 * minmax(ret5 / 8) + 0.45 * minmax(ret20 / 15)
    trend_score = (1 if last > ma20 else -1) * 0.55 + (1 if ma20 > ma60 else -1) * 0.45
    relative_score = minmax(relative / 8)
    risk_score = 1 - minmax(vol20 / 60, 0, 1) - minmax(abs(dd20) / 15, 0, 1) * 0.5
    raw = 100 * (0.30 * momentum + 0.30 * trend_score + 0.20 * relative_score + 0.20 * minmax(risk_score, -1, 1))
    score = round(max(0, min(100, 50 + raw / 2)), 1)
    if last > ma20 > ma60 and ret20 > 0 and score >= 65 and dd20 > -8:
        signal, reason = "重点观察", "中期趋势与动量较强；需结合成交流动性、实时价格及比赛规则人工确认"
    elif last < ma60 or ret20 < -5:
        signal, reason = "谨慎", "价格弱于中期趋势或近20日回报偏弱"
    else:
        signal, reason = "等待确认", "趋势条件不完整，不建议仅凭评分追涨"
    return {
        "code": code, "name": code, "latest_date": latest_date, "close": round(last, 4),
        "ret5": round(ret5, 2), "ret20": round(ret20, 2), "ret60": round(ret60, 2),
        "ma20": round(ma20, 4), "ma60": round(ma60, 4), "trend": trend,
        "volatility20_annualized": round(vol20, 2), "drawdown20": round(dd20, 2),
        "relative20_vs_benchmark": round(relative, 2), "score": score,
        "signal": signal, "reason": reason
    }

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(CST)
    results, errors = [], []
    codes = load_codes()
    benchmark_ret = 0.0
    try:
        bdf = get_hist("510300")
        benchmark_ret = pct(float(bdf["close"].iloc[-1]), float(bdf["close"].iloc[-21]))
    except Exception as e:
        errors.append({"code":"510300","error":str(e)[:180]})
    latest_dates = []
    for code in codes:
        try:
            df = get_hist(code)
            item = score_one(code, df, benchmark_ret)
            # Exclude stale data older than 7 calendar days; weekends/holidays are expected.
            age = (now.date() - datetime.strptime(item["latest_date"], "%Y-%m-%d").date()).days
            if age > 7:
                errors.append({"code":code,"error":f"stale quote: {item['latest_date']}"})
                continue
            results.append(item)
            latest_dates.append(item["latest_date"])
        except Exception as e:
            errors.append({"code":code,"error":str(e)[:180]})
        time.sleep(0.4)
    results.sort(key=lambda x: x["score"], reverse=True)
    for i, item in enumerate(results, 1):
        item["rank"] = i
    status = "ok" if results else "no_data"
    payload = {
        "meta": {
            "status": status,
            "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "latest_date": max(latest_dates) if latest_dates else None,
            "source": "AKShare wrapper / Eastmoney ETF daily history",
            "universe_count": len(codes),
            "success_count": len(results),
            "errors": errors[:20],
            "note": "Daily historical data only; not guaranteed real-time. Scores are research heuristics, not investment advice."
        },
        "rankings": results
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {len(results)} rankings; {len(errors)} errors; status={status}")
    if not results:
        raise SystemExit("No ETF data returned; inspect logs. A no-data result is not a trading signal.")

if __name__ == "__main__":
    main()
