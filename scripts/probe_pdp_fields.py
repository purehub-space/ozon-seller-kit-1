import os, time, re, json
for k in ("HTTP_PROXY","HTTPS_PROXY","http_proxy","https_proxy","ALL_PROXY","all_proxy"): os.environ.pop(k,None)
from playwright.sync_api import sync_playwright
PREFS={"network.proxy.type":0,"network.proxy.http":"","network.proxy.ssl":"","network.proxy.share_proxy_settings":False,"network.proxy.no_proxies_on":"*"}
EXE="/home/user/.doubao/agent_mode/workspace/tools/camoufox/camoufox-bin"
ADDR="Москва, Тверская улица, 1"
PW=sync_playwright().start(); br=PW.firefox.launch(executable_path=EXE,headless=True,firefox_user_prefs=PREFS)
try:
    ctx=br.new_context(locale="ru-RU", viewport={"width":1280,"height":1000}); pg=ctx.new_page()
    pg.goto("https://www.ozon.ru/",wait_until="domcontentloaded",timeout=45000); time.sleep(8)
    for _ in range(2):
        try:
            if pg.locator("text=Укажите адрес").count()==0:
                pg.goto("https://www.ozon.ru/",wait_until="domcontentloaded",timeout=45000); time.sleep(6)
            pg.locator("text=Укажите адрес").first.click(timeout=8000); time.sleep(3)
            pg.locator("input[type=text]").first.fill(ADDR,timeout=8000); time.sleep(3)
            for s in ("text=Тверская","[role=option] >> nth=0"):
                try: pg.locator(s).first.click(timeout=5000); break
                except: pass
            time.sleep(4); break
        except Exception as e: print("addr",type(e).__name__); time.sleep(2)
    SKU="4316600423"
    r=pg.evaluate("""async(v)=>{const r=await fetch('/api/entrypoint-api.bx/page/json/v2?url='+v,{credentials:'include',headers:{'x-o3-app-name':'dweb_client'}});const t=await r.text();return{st:r.status,len:t.length,txt:t};}""",f"/product/{SKU}/")
    print(f"PDP API: {r['st']} {r['len']}B")
    open("pdp_full.json","w").write(r["txt"])
    if r["st"]==200 and r["len"]>100000:
        u=r["txt"].replace('\\"','"')
        for kw in ["cardPrice","CARD_PRICE","greenPrice","priceStyle","Вес","weight","reviewsCount",
                   "soldCount","ordersCount","dist","rating","О товаре","characteristics","Характеристики"]:
            print(f"  {kw:18} {u.count(kw)}")
    ctx.close()
finally:
    br.close(); PW.stop()
