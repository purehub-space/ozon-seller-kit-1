#!/usr/bin/env python3
"""单独 mint 一次会话：Camoufox 开首页 → 设街道地址 → 抓实发头 → 写 cookie.json。

用途：HTTP 通道约 400 个请求后会被判 challenge（返回 challengeURL），
需要换一个新会话。本脚本只做 mint，不采集。
"""
import os, time, json, sys

for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)
from playwright.sync_api import sync_playwright

PREFS = {"network.proxy.type": 0, "network.proxy.http": "", "network.proxy.ssl": "",
         "network.proxy.share_proxy_settings": False, "network.proxy.no_proxies_on": "*"}
EXE = "/home/user/.doubao/agent_mode/workspace/tools/camoufox/camoufox-bin"
COOKIE_FILE = "run12h/cookie.json"


def main():
    addr = "Москва, Тверская улица, 1"
    pw = sync_playwright().start()
    browser = pw.firefox.launch(executable_path=EXE, headless=True, firefox_user_prefs=PREFS)
    try:
        ctx = browser.new_context(locale="ru-RU")
        pg = ctx.new_page()
        cap = {}

        def on_req(r):
            if "entrypoint-api" in r.url and "h" not in cap:
                cap["h"] = dict(r.headers)

        pg.on("request", on_req)
        pg.goto("https://www.ozon.ru/", wait_until="domcontentloaded", timeout=45000)
        time.sleep(8)
        for _ in range(3):
            if len("; ".join(f"{c['name']}={c['value']}" for c in ctx.cookies())) > 1000:
                break
            pg.goto("https://www.ozon.ru/", wait_until="domcontentloaded", timeout=45000)
            time.sleep(8)

        # 关键：设具体街道地址，否则 page/json 返回 142KB 精简版（无库存字段）
        ok = False
        for _t in range(2):
            try:
                if pg.locator("text=Укажите адрес").count() == 0:
                    pg.goto("https://www.ozon.ru/", wait_until="domcontentloaded", timeout=45000)
                    time.sleep(6)
                pg.locator("text=Укажите адрес").first.click(timeout=8000)
                time.sleep(3)
                pg.locator("input[type=text]").first.fill(addr, timeout=8000)
                time.sleep(3)
                for sel in ("text=Тверская", "[role=option] >> nth=0"):
                    try:
                        pg.locator(sel).first.click(timeout=5000)
                        break
                    except Exception:
                        continue
                time.sleep(5)
                ok = True
                break
            except Exception as e:
                print(f"[mint] 地址重试 {_t+1} {type(e).__name__}: {str(e)[:50]}", flush=True)
                time.sleep(2)
        print(f"[mint] 地址设置 {'成功' if ok else '失败(将拿到无库存精简版)'}", flush=True)

        # 触发一次 API 请求抓实发头
        pg.evaluate("""async()=>{await fetch('/api/entrypoint-api.bx/page/json/v2?url=/product/2474366854/',{credentials:'include',headers:{'x-o3-app-name':'dweb_client'}});}""")
        time.sleep(0.5)

        if "h" not in cap:
            print("[mint] 未抓到实发头，失败", flush=True)
            return 1
        h = {k: v for k, v in cap["h"].items() if k not in ("host", "content-length", "connection")}
        tmp = COOKIE_FILE + ".tmp"
        json.dump({"headers": h, "minted_at": time.time(), "addr": addr}, open(tmp, "w"))
        os.replace(tmp, COOKIE_FILE)
        n = len(h.get("cookie", ""))
        print(f"[mint] 完成 @ {time.strftime('%H:%M:%S')} cookie_len={n} 地址={'已设' if ok else '未设'}", flush=True)
        # 立刻验证有效性
        try:
            from curl_cffi import requests as cr
            r = cr.get("https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2",
                       params={"url": "/product/2474366854/"}, headers=h,
                       impersonate="firefox147", timeout=20)
            has = "freeRest" in r.text
            print(f"[mint] 验证: {r.status_code} {len(r.content)}B 含库存字段={has}", flush=True)
            if r.status_code != 200:
                return 2
        except Exception as e:
            print(f"[mint] 验证异常 {type(e).__name__}", flush=True)
        ctx.close()
        return 0
    finally:
        browser.close()
        pw.stop()


if __name__ == "__main__":
    sys.exit(main())
