"""库存采集（HTTP 通道）。

关键前提：cookie 必须是 Camoufox 设过具体收货地址后导出的。只有城市级地址时
page/json 返回 142KB 精简版（freeRest/maxItems/stockNumber 全空）；设到街道后
返回 155-170KB 完整版且 freeRest 有值。因此本脚本不自己 mint，只读 cookie.json。

内置两道闸门，避免打到服务端上限：
  1. --rate        稳态限速（页/秒），批间补 sleep，默认 2.0
  2. --hourly-cap  每小时请求上限，到点强制休息到下一小时，默认 7200
  3. 403 过半       立即暂停 60s 并重读 cookie（票据/出口异常）
每批写一行遥测到 run12h/stock_http_metrics.jsonl（含 P50/P95、响应字节数、配额用量）。
"""
import os, sys, json, time, re, sqlite3, threading, argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from curl_cffi import requests as cr
import statistics

BASE = "https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2"
COOKIE = "run12h/cookie.json"
DB = "run12h/monitor_12h.db"
METRICS = "run12h/stock_http_metrics.jsonl"
SRC = "/home/user/Doubao/chats/38452491605179138/ozon-seller-kit/data/toys-slim.db"
KEYMAP = {"freeRest": "free_rest", "maxItems": "max_items", "isUnavailable": "unavailable"}


def load_cookie():
    d = json.load(open(COOKIE))
    return d.get("headers") or {}, d.get("minted_at", 0)


def parse(txt):
    """从 PDP widgetStates 抽库存与价格。widgetStates 的值是二次编码 JSON。"""
    try:
        j = json.loads(txt)
    except Exception:
        return None
    ws = j.get("widgetStates", {})
    out = {"free_rest": None, "max_items": None, "stock_real": None,
           "stock_text": None, "price": None, "unavailable": None}
    for k, v in ws.items():
        if not isinstance(v, str):
            continue
        try:
            d = json.loads(v)
        except Exception:
            continue
        if k.startswith("webAddToCart"):
            stack = [d]
            while stack:
                o = stack.pop()
                if isinstance(o, dict):
                    for kk, vv in o.items():
                        if isinstance(vv, (dict, list)):
                            stack.append(vv)
                        elif kk in KEYMAP and out[KEYMAP[kk]] is None:
                            out[KEYMAP[kk]] = vv
                        elif kk in ("text", "title") and isinstance(vv, str) and "осталось" in vv:
                            out["stock_text"] = vv
                elif isinstance(o, list):
                    stack.extend(o)
        if k.startswith("bigPromoPDP"):
            sn = d.get("stockNumber") or {}
            if isinstance(sn, dict) and str(sn.get("text", "")).strip().isdigit():
                out["stock_real"] = int(str(sn["text"]).strip())
                out["stock_text"] = f'{out["stock_real"]} единиц осталось'
        if k.startswith("webPrice") and out["price"] is None:
            raw = d.get("price") or d.get("cardPrice") or ""
            digits = re.sub(r"[^0-9.,]", "", str(raw)).replace(",", ".")
            if digits:
                out["price"] = float(digits)
    return out


def hit(sku, hdr):
    """返回 (sku, status, parsed, ms, bytes)。status=-1 表示网络异常。"""
    t0 = time.time()
    try:
        r = cr.get(BASE, params={"url": f"/product/{sku}/"}, headers=hdr,
                   impersonate="firefox147", timeout=25)
    except Exception:
        return sku, -1, None, int((time.time() - t0) * 1000), 0
    ms = int((time.time() - t0) * 1000)
    nbytes = len(r.content)
    if r.status_code != 200:
        return sku, r.status_code, None, ms, nbytes
    return sku, 200, parse(r.text), ms, nbytes


def pct(vals, p):
    if not vals:
        return 0
    vals = sorted(vals)
    idx = min(int(len(vals) * p / 100), len(vals) - 1)
    return vals[idx]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=12)
    ap.add_argument("--conc", type=int, default=30)
    ap.add_argument("--chunk", type=int, default=0)
    ap.add_argument("--rate", type=float, default=0.58, help="稳态页/秒，0=不限速。实测出口 IP 日配额约 2.5-3 万请求")
    ap.add_argument("--hourly-cap", type=int, default=2100, help="每小时请求上限，0=不限")
    ap.add_argument("--daily-cap", type=int, default=25000, help="本进程累计请求上限，0=不限")
    a = ap.parse_args()

    hdr, minted = load_cookie()
    if not hdr.get("cookie"):
        print("[http] cookie.json 无 cookie，先跑 mint（必须设街道地址）", flush=True)
        sys.exit(1)

    con = sqlite3.connect(DB, check_same_thread=False)
    lock = threading.Lock()
    con.execute("""CREATE TABLE IF NOT EXISTS stock_obs (round INT, sku TEXT, ts INT, status INT,
        free_rest INT, max_items INT, stock_real INT, stock_text TEXT, price REAL,
        unavailable INT, ms INT, PRIMARY KEY(round, sku))""")
    con.commit()
    src = sqlite3.connect(SRC)
    skus = [r[0] for r in src.execute("select distinct sku from sku")]
    print(f"[http] {len(skus)} SKU, conc={a.conc}, rate={a.rate}页/秒, cap={a.hourly_cap}/h, "
          f"cookie_minted={time.strftime('%H:%M:%S', time.localtime(minted))}", flush=True)

    deadline = time.time() + a.hours * 3600
    chunk = a.chunk or max(a.conc * 4, 40)
    rnd, batch_no = 0, 0
    hour_start, hour_count = time.time(), 0
    st = {"ok": 0, "f403": 0, "other": 0, "req": 0}

    while time.time() < deadline:
        done = {r[0] for r in con.execute("select sku from stock_obs where round=? and status=200", (rnd,))}
        todo = [s for s in skus if s not in done]
        if not todo:
            rnd += 1
            print(f"[http] round {rnd} 开始 @ {time.strftime('%H:%M:%S')}", flush=True)
            continue
        for i in range(0, len(todo), chunk):
            if time.time() >= deadline:
                break
            # 闸门 2：小时配额
            if a.hourly_cap and hour_count >= a.hourly_cap:
                wait = 3600 - (time.time() - hour_start)
                if wait > 0:
                    print(f"[http] 小时配额 {a.hourly_cap} 已用尽 → 休息 {wait/60:.1f} 分钟", flush=True)
                    time.sleep(min(wait, deadline - time.time()))
                hour_start, hour_count = time.time(), 0
                if time.time() >= deadline:
                    break
            if a.daily_cap and st["req"] >= a.daily_cap:
                print(f"[http] 日配额 {a.daily_cap} 已用尽 → 停止（明日再跑或换出口）", flush=True)
                break
            batch = todo[i:i + chunk]
            batch_no += 1
            t0 = time.time()
            rows = []
            with ThreadPoolExecutor(max_workers=a.conc) as ex:
                futs = [ex.submit(hit, s, hdr) for s in batch]
                for f in as_completed(futs):
                    rows.append(f.result())
            ok = sum(1 for r in rows if r[1] == 200)
            f403 = sum(1 for r in rows if r[1] == 403)
            oth = len(rows) - ok - f403
            ts = int(time.time())
            for sku, status, d, ms, nb in rows:
                d = d or {}
                with lock:
                    con.execute("insert or replace into stock_obs values (?,?,?,?,?,?,?,?,?,?,?)",
                                (rnd, sku, ts, status, d.get("free_rest"), d.get("max_items"),
                                 d.get("stock_real"), d.get("stock_text"), d.get("price"),
                                 (1 if d.get("unavailable") else 0) if status == 200 else None, ms))
            with lock:
                con.commit()
            st["ok"] += ok; st["f403"] += f403; st["other"] += oth; st["req"] += len(batch)
            hour_count += len(batch)
            el = time.time() - t0
            rate = len(batch) / el if el > 0 else 0
            mss = [r[3] for r in rows]
            bts = [r[4] for r in rows if r[4] > 0]
            total_ok = con.execute("select count(*) from stock_obs where status=200").fetchone()[0]
            fr = con.execute("select count(*) from stock_obs where free_rest is not null").fetchone()[0]
            # 遥测
            rec = {"ts": ts, "batch": batch_no, "round": rnd, "n": len(batch),
                   "ok": ok, "f403": f403, "other": oth, "rate": round(rate, 2),
                   "ms_p50": pct(mss, 50), "ms_p95": pct(mss, 95), "ms_max": max(mss) if mss else 0,
                   "bytes_min": min(bts) if bts else 0, "bytes_max": max(bts) if bts else 0,
                   "hourly_used": hour_count, "hourly_cap": a.hourly_cap, "hourly_rate": a.rate}
            with open(METRICS, "a") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"[http] r{rnd} b{batch_no} +{ok}/{len(batch)} 403={f403} {rate:.2f}页/秒 "
                  f"P95={rec['ms_p95']}ms 均{rec['bytes_min']}~{rec['bytes_max']}B "
                  f"[本小时 {hour_count}/{a.hourly_cap}] 累计200={total_ok}/{len(skus)} 库存率{fr/max(total_ok,1)*100:.0f}%",
                  flush=True)
            # 闸门 3：403 过半 → 大概率出口 IP 级 challenge（换 cookie 无效），长冷却
            if f403 > len(batch) / 2:
                print(f"[http] 403 过半 ({f403}/{len(batch)}) → 疑似出口 IP 级 challenge，冷却 180s", flush=True)
                time.sleep(180)
                hdr, minted = load_cookie()
            # 闸门 1：稳态限速
            if a.rate > 0:
                target = len(batch) / a.rate
                gap = target - (time.time() - t0)
                if gap > 0:
                    time.sleep(gap)

    print(f"[http] 结束 请求{st['req']} 成功{st['ok']} 403={st['f403']} 其他={st['other']}", flush=True)


if __name__ == "__main__":
    main()
