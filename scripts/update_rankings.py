import json
import math
import os
import time
from datetime import datetime, timezone

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST = os.path.join(ROOT, "config", "watchlist.txt")
OUTPUT = os.path.join(ROOT, "data", "results.json")

API_URL = "https://api.ashareapi.com/v1/kline"
REQUEST_INTERVAL = 31  # 免费匿名脚本限流：约每分钟2次
HEADERS = {"User-Agent": "ETF-Elite/1.0"}


def load_codes():
    with open(WATCHLIST, "r", encoding="utf-8-sig") as f:
        return [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]


def market_code(code):
    # 常见沪市ETF代码以5开头，深市ETF代码以15/16开头
    if code.startswith(("5", "6", "9")):
        return "sh" + code
    return "sz" + code


def get_history(code):
    response = requests.get(
        API_URL,
        params={
            "code": market_code(code),
            "period": "day",
            "count": "80",
        },
        headers=HEADERS,
        timeout=25,
    )
    response.raise_for_status()
    payload = response.json()

    if not payload.get("ok") or not payload.get("data"):
        raise ValueError(
            "行情接口没有返回有效数据：" +
            str(payload.get("message", payload.get("error", payload)))
        )

    rows = []
    for item in payload["data"]:
        date = item.get("date")
        close = item.get("last", item.get("close"))
        if date is None or close is None:
            continue
        try:
            price = float(close)
            if price > 0:
                rows.append({"date": str(date), "close": price})
        except (TypeError, ValueError):
            continue

    rows.sort(key=lambda x: x["date"])
    if len(rows) < 60:
        raise ValueError(f"有效日线不足60条：{len(rows)}条")

    return rows


def score_history(code, rows):
    closes = [x["close"] for x in rows]
    last = closes[-1]

    def ret(days):
        if len(closes) <= days:
            return None
        return round((last / closes[-days - 1] - 1) * 100, 2)

    ma20 = sum(closes[-20:]) / 20
    ma60 = sum(closes[-60:]) / 60

    daily_returns = [
        closes[i] / closes[i - 1] - 1
        for i in range(len(closes) - 20, len(closes))
        if closes[i - 1] > 0
    ]

    if len(daily_returns) > 1:
        avg = sum(daily_returns) / len(daily_returns)
        variance = sum((x - avg) ** 2 for x in daily_returns) / (
            len(daily_returns) - 1
        )
        vol = math.sqrt(variance) * math.sqrt(252) * 100
    else:
        vol = 0.0

    recent = closes[-20:]
    peak = recent[0]
    drawdown = 0.0
    for price in recent:
        peak = max(peak, price)
        drawdown = min(drawdown, (price / peak - 1) * 100)

    r5, r20, r60 = ret(5), ret(20), ret(60)

    score = (
        (r20 or 0) * 0.35
        + (r60 or 0) * 0.25
        + (r5 or 0) * 0.15
        + (10 if last > ma20 else 0)
        + (10 if ma20 > ma60 else 0)
        - vol * 0.10
        + drawdown * 0.20
    )

    if (
    last > ma20
    and ma20 > ma60
    and r20 is not None
    and r20 > 0
    and r5 is not None
    and r5 >= 0
):
    signal = "可以考虑买入"

elif (
    last < ma20
    and ma20 < ma60
) or (
    r20 is not None and r20 <= -8
):
    signal = "暂不买入"

else:
    signal = "观察，等待确认"

    return {
        "code": code,
        "date": rows[-1]["date"],
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
    codes = load_codes()

    if not codes:
        raise RuntimeError("观察列表为空，请检查 config/watchlist.txt")

    session = requests.Session()
    session.headers.update(HEADERS)

    for index, code in enumerate(codes):
        if index > 0:
            time.sleep(REQUEST_INTERVAL)

        try:
            rows = get_history_with_session(session, code)
            item = score_history(code, rows)
            results.append(item)
            print(f"OK {code}: {item['date']}")
        except Exception as exc:
            errors.append({"code": code, "error": str(exc)})
            print(f"FAILED {code}: {exc}")

    if not results:
        raise RuntimeError(
            "所有ETF获取失败。请检查API响应、代码格式及免费额度。"
        )

    results.sort(key=lambda x: x["score"], reverse=True)
    for rank, item in enumerate(results, start=1):
        item["rank"] = rank

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    payload = {
        "status": "ok" if not errors else "partial",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "data_date": max(item["date"] for item in results),
        "count": len(results),
        "rankings": results,
        "errors": errors,
        "source": "A-Share Data API",
        "disclaimer": "参考指标和启发式评分，不构成投资建议。",
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(
        f"完成：成功{len(results)}只，失败{len(errors)}只；"
        f"最新行情日期：{payload['data_date']}"
    )


def get_history_with_session(session, code):
    response = session.get(
        API_URL,
        params={
            "code": market_code(code),
            "period": "day",
            "count": "80",
        },
        timeout=25,
    )
    response.raise_for_status()
    payload = response.json()

    if not payload.get("ok") or not payload.get("data"):
        raise ValueError(
            "行情接口无有效数据：" +
            str(payload.get("message", payload.get("error", payload)))
        )

    rows = []
    for item in payload["data"]:
        date = item.get("date")
        close = item.get("last", item.get("close"))
        try:
            price = float(close)
            if date and price > 0:
                rows.append({"date": str(date), "close": price})
        except (TypeError, ValueError):
            continue

    rows.sort(key=lambda x: x["date"])
    if len(rows) < 60:
        raise ValueError(f"有效日线不足60条：{len(rows)}条")
    return rows


if __name__ == "__main__":
    main()
