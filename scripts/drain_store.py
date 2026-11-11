import os, time, re, html as hm, json
for k in ("HTTP_PROXY","HTTPS_PROXY","http_proxy","https_proxy","ALL_PROXY","all_proxy"): os.environ.pop(k,None)
from playwright.sync_api import sync_playwright
PREFS={"network.proxy.type":0,"network.proxy.http":"","network.proxy.ssl":"","network.proxy.share_proxy_settings":False,"network.proxy.no_proxies_on":"*"}
EXE="/home/user/.doubao/agent_mode/workspace/tools/camoufox/camoufox-bin"
ADDR="Москва, Тверская улица, 1"
SLUG="sima-lend"
PAT=r'"quantityButton":\{"maxItems":\d+,\s*"updateCartAction":\{"id":"(\d+)"'
pw=sync_playwright().start(); br=pw.firefox.launch(executable_path=EXE,headless=True,firefox_user_prefs=PREFS)
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
    allskus=set(); pages=[]
    for page in range(1,26):
        u=f"/seller/{SLUG}/products/?page={page}"
        r=pg.evaluate("""async(v)=>{const r=await fetch(v,{credentials:'include'});const t=await r.text();return{st:r.status,len:t.length,txt:t};}""",u)
        pages.append(r["txt"])
        s=set(re.findall(PAT, hm.unescape(r["txt"])))
        new=s-allskus
        print(f"page{page}: {r['st']} {r['len']}B | 本页 {len(s)} | 新增 {len(new)} | 累计 {len(allskus|s)}")
        allskus|=s
        if len(new)==0 and page>1: break
        time.sleep(0.8)
    json.dump({"slug":SLUG,"pages":pages,"skus":sorted(allskus)}, open("sima_all_pages.json","w"))
    print(f"\n=== 全店 {len(allskus)} 个 SKU，共 {len(pages)} 页 ===")
    # 探测订单量字段
    alltxt=" ".join(pages)
    for kw in ["заказ","Заказ","куплен","Купили","продано","sold","ordersCount","orderCount",
               "сколько раз","покупател","рейтинг товара","отзыв"]:
        print(f"  '{kw}': {alltxt.count(kw)}")
    ctx.close()
finally:
    br.close(); pw.stop()
