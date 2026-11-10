#!/usr/bin/env python3
"""生成 Ozon 市场决策台单页看板。

设计取舍：
- 首屏 KPI 与榜单前 20 行直接写进 HTML 文本，不依赖 JS 渲染，保证 LCP。
- 四象限散点用 CR4（竞争集中度）× DRR（投流依赖）定位，点击展开词详情。
- 只保留三种状态色（进攻/观察/回避），细分原因写在表里，避免配色失控。
"""
import json
from pathlib import Path

SRC = Path("data/dashboard.json")
OUT_DIR = Path("/home/user/Doubao/chats/38452491605179138/ozon-market-board")
OUT = OUT_DIR / "Ozon市场决策台.html"

d = json.loads(SRC.read_text(encoding="utf-8"))
kpi = d["kpi"]
kws = d["keywords"]
skus = d["skus"]


def band(v):
    if v == "进攻":
        return "attack"
    if v == "观察":
        return "watch"
    return "avoid"


def fmt(v, nd=0):
    if v is None:
        return "—"
    if isinstance(v, (int, float)):
        return f"{v:,.{nd}f}"
    return str(v)


for k in kws:
    k["band"] = band(k["verdict"])

# ---------- 首屏榜单 ----------
top = kws[:20]
rows_html = []
for i, k in enumerate(top, 1):
    rows_html.append(
        '<tr data-kw="{kw}"><td class="num">{i}</td><td class="kw">{kw}</td>'
        '<td class="num">{vol}</td><td class="num">{growth}</td>'
        '<td class="num">{cr4}</td><td class="num">{drr}</td>'
        '<td class="num">{dts}</td><td class="num">{cpc}</td>'
        '<td class="num">{price}</td>'
        '<td><span class="tag {band}">{verdict}</span></td></tr>'.format(
            i=i,
            kw=k["keyword"],
            vol=fmt(k.get("search_volume")),
            growth=(f'{k["growth_30d"]:+.0f}%' if k.get("growth_30d") is not None else "—"),
            cr4=(f'{k["cr4"]:.1f}%' if k.get("cr4") is not None else "—"),
            drr=(f'{k["drr_median"]:.1f}%' if k.get("drr_median") is not None else "—"),
            dts=(f'{k["days_to_sell_median"]:.0f}天' if k.get("days_to_sell_median") is not None else "—"),
            cpc=(f'{k["cpc_median"]:.2f}₽' if k.get("cpc_median") is not None else "—"),
            price=(f'{k["price_median"]:.0f}₽' if k.get("price_median") is not None else "—"),
            band=k["band"],
            verdict=k["verdict"],
        )
    )

# ---------- 库存榜 ----------
sku_rows = []
for s in skus[:18]:
    sku_rows.append(
        '<tr><td class="mono">{sku}</td><td class="kw">{kw}</td>'
        '<td class="num">{pos}</td><td class="num strong">{stock}</td>'
        '<td class="num">{limit}</td><td class="num">{price}</td>'
        '<td><span class="tag {b}">{band_cn}</span></td></tr>'.format(
            sku=s.get("sku"),
            kw=(s.get("keyword") or "—"),
            pos=(s.get("position") or "—"),
            stock=fmt(s.get("stock_real")),
            limit=fmt(s.get("stock_limit")),
            price=(f'{s["price"]:.0f}₽' if s.get("price") else "—"),
            b={"紧张": "attack", "疑似封顶": "watch", "正常": "calm", "充足": "calm", "未知": "watch"}.get(s.get("stock_band"), "watch"),
            band_cn=s.get("stock_band") or "—",
        )
    )

payload = {
    "generated_at": d["generated_at"],
    "points": [
        {
            "kw": k["keyword"],
            "x": round(k.get("cr4") or 0, 1),
            "y": round(k.get("drr_median") or 0, 1),
            "v": k.get("search_volume") or 0,
            "b": k["band"],
            "verdict": k["verdict"],
            "g": round(k.get("growth_30d") or 0, 0),
            "dts": (round(k["days_to_sell_median"], 0) if k.get("days_to_sell_median") else None),
            "cpc": round(k.get("cpc_median") or 0, 2),
            "price": round(k.get("price_median") or 0, 0),
            "boom": round(k.get("boom_index") or 0, 2),
            "rf": round(k.get("review_floor") or 0, 0),
            "ad": round(k.get("ad_density") or 0, 0),
        }
        for k in kws
    ],
}

TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ozon 市场决策台</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' fill='%23121417'/><circle cx='16' cy='16' r='9' fill='none' stroke='%23D8A24A' stroke-width='2.5'/><path d='M16 7v18M7 16h18' stroke='%23D8A24A' stroke-width='1' opacity='.5'/></svg>">
<style>
:root{
  --bg:#121417; --panel:#191C20; --panel2:#1E2227; --line:#2A2E34;
  --ink:#E6E2DA; --dim:#8B8F96; --faint:#5E646C;
  --amber:#D8A24A; --red:#9E5252; --gray:#6B7078;
  --mono:ui-monospace,"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
  --sans:"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans SC",system-ui,sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:14px;line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{width:100%;max-width:1240px;margin:0 auto;padding:28px 18px 56px}

head{display:block}
.mast{display:flex;flex-wrap:wrap;align-items:baseline;gap:10px 18px;padding-bottom:14px;border-bottom:1px solid var(--line)}
h1{font-size:26px;font-weight:700;letter-spacing:-.01em}
.mast .meta{font-family:var(--mono);font-size:12px;color:var(--faint);letter-spacing:.02em}
.mast .rule{margin-left:auto;font-size:12px;color:var(--dim);max-width:520px}

.kpis{display:grid;grid-template-columns:repeat(2,1fr);gap:1px;background:var(--line);margin:22px 0 30px;border:1px solid var(--line)}
.kpi{background:var(--panel);padding:14px 16px}
.kpi .lab{font-size:12px;color:var(--dim);letter-spacing:.03em}
.kpi .val{font-family:var(--mono);font-size:30px;font-weight:600;line-height:1.15;margin-top:2px;font-variant-numeric:tabular-nums}
.kpi .sub{font-family:var(--mono);font-size:11px;color:var(--faint);margin-top:2px}
.kpi.att .val{color:var(--amber)}

.sec{margin-bottom:34px}
.sec-h{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:4px}
h2{font-size:17px;font-weight:650}
.sec-h .note{font-size:12px;color:var(--dim)}
.sec p.lead{font-size:13px;color:var(--dim);margin:2px 0 14px;max-width:760px}

.split{display:grid;grid-template-columns:1fr;gap:18px}
@media(min-width:820px){.split{grid-template-columns:1.05fr .95fr}}

.card{background:var(--panel);border:1px solid var(--line)}
.card .hd{display:flex;align-items:center;justify-content:space-between;padding:10px 14px;border-bottom:1px solid var(--line)}
.card .hd .t{font-size:13px;font-weight:650}
.card .hd .s{font-family:var(--mono);font-size:11px;color:var(--faint)}
#quad{width:100%;height:360px}
.detail{padding:12px 14px;border-top:1px solid var(--line);min-height:86px}
.detail .name{font-weight:650;margin-bottom:6px;word-break:break-word}
.detail .grid4{display:grid;grid-template-columns:repeat(2,1fr);gap:6px 14px}
.detail .cell{font-size:12px;color:var(--dim)}
.detail .cell b{font-family:var(--mono);color:var(--ink);font-weight:600}

.tblwrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{width:100%;border-collapse:collapse;font-size:13px;table-layout:fixed}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}
th{font-size:11px;color:var(--dim);font-weight:600;background:var(--panel2);cursor:pointer;user-select:none;white-space:nowrap}
th:hover{color:var(--ink)}
th .arrow{color:var(--amber);margin-left:4px;font-size:10px}
td.num{font-family:var(--mono);text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.strong{color:var(--amber);font-weight:600}
td.kw{font-size:12.5px;word-break:break-word;hyphens:auto}
td.mono{font-family:var(--mono);font-size:12px;color:var(--dim)}
.tag{display:inline-block;padding:1px 8px;font-size:11.5px;border:1px solid currentColor;white-space:nowrap}
.tag.attack{color:var(--amber)}
.tag.watch{color:var(--gray)}
.tag.avoid{color:var(--red)}
.tag.calm{color:var(--dim)}

.filters{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}
.filters button{background:transparent;border:1px solid var(--line);color:var(--dim);padding:6px 12px;font-size:12.5px;font-family:var(--sans);cursor:pointer;transition:color .12s,border-color .12s}
.filters button:hover{color:var(--ink);border-color:var(--dim)}
.filters button[aria-pressed="true"]{color:var(--amber);border-color:var(--amber)}

.legend{display:flex;gap:16px;flex-wrap:wrap;padding:8px 14px;border-top:1px solid var(--line);font-size:11.5px;color:var(--dim)}
.legend i{display:inline-block;width:9px;height:9px;margin-right:6px;border-radius:50%;vertical-align:middle}

.note-block{border-left:2px solid var(--amber);padding:10px 14px;background:var(--panel);font-size:12.5px;color:var(--dim);line-height:1.75}
.note-block b{color:var(--ink)}

footer{margin-top:40px;padding-top:14px;border-top:1px solid var(--line);font-size:11.5px;color:var(--faint);font-family:var(--mono)}
</style>
</head>
<body>
<div class="wrap">

  <div class="mast">
    <h1>Ozon 市场决策台</h1>
    <div class="meta">SNAP __GEN__</div>
    <div class="rule">词级横截面 = 1642 词 · SKU 快照 = 211 条 · 口径：CR4 为前 4 名销量占前 30 名销量比，DRR 为广告费占 GMV 比</div>
  </div>

  <div class="kpis">
    <div class="kpi"><div class="lab">可进攻词</div><div class="val att">__ATK__</div><div class="sub">/ __KWT__ 词 · 占比 __ATKPCT__%</div></div>
    <div class="kpi"><div class="lab">观察中</div><div class="val">__WATCH__</div><div class="sub">信号不足或条件冲突</div></div>
    <div class="kpi"><div class="lab">回避</div><div class="val">__AVOID__</div><div class="sub">量不足 / 红海 / 重度投流 / 压货</div></div>
    <div class="kpi"><div class="lab">库存紧张 SKU</div><div class="val">__TIGHT__</div><div class="sub">真值 &lt; 50 件 · 共 __SKUT__ 个有库存样本</div></div>
  </div>

  <div class="sec">
    <div class="sec-h"><h2>竞争 × 投流 四象限</h2><span class="note">横轴 CR4 越低越分散，纵轴 DRR 越低越不依赖买量</span></div>
    <p class="lead">左下角是结构性机会：集中度低、投流依赖低。右下有需求但被头部占住，右上两侧都在买量，左上几乎没有自然流量。点击任意点查看该词明细。</p>
    <div class="split">
      <div class="card">
        <div class="hd"><span class="t">每点一词，点大小 = 搜索量</span><span class="s">x: CR4 % · y: DRR %</span></div>
        <div id="quad"></div>
        <div class="legend">
          <span><i style="background:#D8A24A"></i>进攻</span>
          <span><i style="background:#6B7078"></i>观察</span>
          <span><i style="background:#9E5252"></i>回避</span>
        </div>
        <div class="detail" id="detail">
          <div class="name">未选中</div>
          <div class="grid4">
            <div class="cell">点击图中散点或下方榜单行</div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="hd"><span class="t">爆品指数 Top 20</span><span class="s">按 boom_index 降序</span></div>
        <div class="tblwrap">
          <table>
            <colgroup><col style="width:7%"><col style="width:33%"><col style="width:11%"><col style="width:10%"><col style="width:9%"><col style="width:8%"><col style="width:10%"><col style="width:12%"></colgroup>
            <thead><tr>
              <th data-sort="rank">#</th><th data-sort="kw">关键词</th><th data-sort="vol" class="num">搜索量</th>
              <th data-sort="growth" class="num">30天增长</th><th data-sort="cr4" class="num">CR4</th>
              <th data-sort="drr" class="num">DRR</th><th data-sort="dts" class="num">可售天数</th><th>判定</th>
            </tr></thead>
            <tbody id="topbody">
__ROWS__
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

  <div class="sec">
    <div class="sec-h"><h2>词库全表</h2><span class="note">可筛选、可排序，取爆品指数前 300</span></div>
    <div class="filters" id="filters">
      <button data-f="all" aria-pressed="true">全部</button>
      <button data-f="attack" aria-pressed="false">进攻</button>
      <button data-f="watch" aria-pressed="false">观察</button>
      <button data-f="avoid" aria-pressed="false">回避</button>
    </div>
    <div class="card">
      <div class="tblwrap">
        <table>
          <colgroup><col style="width:6%"><col style="width:26%"><col style="width:9%"><col style="width:8%"><col style="width:8%"><col style="width:7%"><col style="width:9%"><col style="width:8%"><col style="width:8%"><col style="width:11%"></colgroup>
          <thead><tr>
            <th data-s="i">#</th><th data-s="kw">关键词</th><th data-s="vol" class="num">搜索量</th>
            <th data-s="g" class="num">30天增长</th><th data-s="x" class="num">CR4</th>
            <th data-s="y" class="num">DRR</th><th data-s="dts" class="num">可售天数</th>
            <th data-s="cpc" class="num">CPC</th><th data-s="boom" class="num">爆品指数</th><th>判定</th>
          </tr></thead>
          <tbody id="allbody"></tbody>
        </table>
      </div>
      <div class="hd" style="border-top:1px solid var(--line);border-bottom:none">
        <span class="s" id="count">—</span>
      </div>
    </div>
  </div>

  <div class="sec">
    <div class="sec-h"><h2>库存缺口 SKU</h2><span class="note">真值取列表页文案，limit 为加购上限（2000 封顶，非库存）</span></div>
    <div class="card">
      <div class="tblwrap">
        <table>
          <colgroup><col style="width:16%"><col style="width:30%"><col style="width:8%"><col style="width:12%"><col style="width:12%"><col style="width:10%"><col style="width:12%"></colgroup>
          <thead><tr><th>SKU</th><th>品名</th><th class="num">位次</th><th class="num">库存真值</th><th class="num">加购上限</th><th class="num">价格</th><th>区间</th></tr></thead>
          <tbody>
__SKUROWS__
          </tbody>
        </table>
      </div>
      <div class="legend" style="border-top:1px solid var(--line)">
        <span>紧张 &lt; 50 件</span><span>正常 50–500</span><span>充足 ≥ 500</span><span>疑似封顶：真值与上限同为 2000，文案未给出更高值</span>
      </div>
    </div>
  </div>

  <div class="sec">
    <div class="note-block">
      <b>怎么用这张表：</b>先看四象限左下有没有点，再看 Top 20 里判定是否为「进攻」，两者重合的才是本周该动手的词。库存表只用来定进场时点——真值低于 50 件且位次在前 30 的 SKU，是竞品断货窗口的候选。<br>
      <b>已知缺口：</b>SKU 级日销未入库，库存周转目前只能借词级中位天数代理；利润、投流出价所需的佣金矩阵与尾程报价尚未接入，本页不展示净利与建议出价。
    </div>
  </div>

  <footer>DATA · __GEN__ · keywords __KWT__ / sku_snap __SKUT__</footer>
</div>

<script src="https://fastly.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<script>
const RAW = __DATA__;

/* ===== 四象限 ===== */
const quadEl = document.getElementById('quad');
let chart = null;
const COLOR = {attack:'#D8A24A', watch:'#6B7078', avoid:'#9E5252'};
const LABEL = {attack:'进攻', watch:'观察', avoid:'回避'};

function detailOf(p){
  const el = document.getElementById('detail');
  el.innerHTML =
    '<div class="name">' + p.kw + '</div>' +
    '<div class="grid4">' +
      '<div class="cell">判定 <b>' + p.verdict + '</b></div>' +
      '<div class="cell">搜索量 <b>' + p.v.toLocaleString() + '</b></div>' +
      '<div class="cell">CR4 <b>' + p.x.toFixed(1) + '%</b></div>' +
      '<div class="cell">DRR <b>' + p.y.toFixed(1) + '%</b></div>' +
      '<div class="cell">可售天数 <b>' + (p.dts===null?'—':p.dts+' 天') + '</b></div>' +
      '<div class="cell">CPC <b>' + p.cpc.toFixed(2) + '₽</b></div>' +
      '<div class="cell">价格中位 <b>' + (p.price?p.price+'₽':'—') + '</b></div>' +
      '<div class="cell">评价门槛 <b>' + (p.rf?p.rf+' 条':'0') + '</b></div>' +
    '</div>';
}

function drawQuad(){
  if(!chart) chart = echarts.init(quadEl, null, {renderer:'canvas'});
  const sets = {attack:[], watch:[], avoid:[]};
  RAW.points.forEach(p=>{ sets[p.b].push(p); });
  const series = ['attack','watch','avoid'].map(k=>{
    const pts = sets[k];
    return {
      name: LABEL[k],
      type:'scatter',
      data: pts.map(p=>({value:[p.x,p.y], p:p})),
      symbolSize: p=>{
        const v = p.data.p.v || 0;
        return Math.max(6, Math.min(26, 6 + Math.sqrt(v)/11));
      },
      itemStyle:{color:COLOR[k], opacity: k==='attack'?0.92:0.55, borderColor:COLOR[k], borderWidth: k==='attack'?1:0},
      emphasis:{itemStyle:{opacity:1, borderColor:'#E6E2DA', borderWidth:1.5}},
      z: k==='attack'?3:2
    };
  });
  chart.setOption({
    animationDuration: 600,
    grid:{left:52,right:18,top:18,bottom:44},
    xAxis:{
      name:'CR4 %', nameLocation:'middle', nameGap:26, nameTextStyle:{color:'#8B8F96',fontSize:11},
      min:0, max:100, splitLine:{lineStyle:{color:'#22262B'}},
      axisLine:{lineStyle:{color:'#3A3F46'}},
      axisLabel:{color:'#6E747C',fontSize:10},
      axisTick:{show:false}
    },
    yAxis:{
      name:'DRR %', nameLocation:'middle', nameGap:34, nameTextStyle:{color:'#8B8F96',fontSize:11},
      min:0, max:70, splitLine:{lineStyle:{color:'#22262B'}},
      axisLine:{lineStyle:{color:'#3A3F46'}},
      axisLabel:{color:'#6E747C',fontSize:10},
      axisTick:{show:false}
    },
    series: series.concat([
      {name:'阈值', type:'scatter', data:[[50,15.19]], symbol:'none',
       markLine:{silent:true, symbol:'none', label:{color:'#5E646C',fontSize:10,formatter:'CR4 50 / DRR 15.19'},
         lineStyle:{color:'#3A3F46',type:'dashed'},
         data:[{xAxis:50},{yAxis:15.19}]}}
    ]),
    tooltip:{
      trigger:'item', confine:true,
      backgroundColor:'#1E2227', borderColor:'#3A3F46', borderWidth:1,
      textStyle:{color:'#E6E2DA',fontSize:12},
      formatter: p=>{
        const d = p.data.p;
        if(!d) return '';
        return '<b>' + d.kw + '</b><br/>判定 ' + d.verdict +
               '<br/>CR4 ' + d.x + '% · DRR ' + d.y + '%' +
               '<br/>搜索量 ' + d.v.toLocaleString();
      }
    }
  });
  chart.on('click', params=>{
    if(params.data && params.data.p) detailOf(params.data.p);
  });
  window.addEventListener('resize', ()=>chart && chart.resize());
}

/* ===== 词库全表 ===== */
let filter = 'all';
let sortKey = 'boom';
let sortDir = -1;
const allBody = document.getElementById('allbody');
const countEl = document.getElementById('count');

function renderAll(){
  let list = RAW.points.slice();
  if(filter !== 'all') list = list.filter(p=>p.b===filter);
  list.sort((a,b)=>{
    const va = a[sortKey], vb = b[sortKey];
    if(typeof va === 'string') return sortDir * (va > vb ? 1 : va < vb ? -1 : 0);
    return sortDir * ((va||0) - (vb||0));
  });
  const rows = list.slice(0,120).map((p,i)=>
    '<tr data-kw="'+p.kw+'"><td class="num">'+(i+1)+'</td>'+
    '<td class="kw">'+p.kw+'</td>'+
    '<td class="num">'+(p.v?p.v.toLocaleString():'—')+'</td>'+
    '<td class="num">'+(p.g?(p.g>0?'+':'')+p.g+'%':'—')+'</td>'+
    '<td class="num">'+p.x.toFixed(1)+'%</td>'+
    '<td class="num">'+p.y.toFixed(1)+'%</td>'+
    '<td class="num">'+(p.dts===null?'—':p.dts+'天')+'</td>'+
    '<td class="num">'+p.cpc.toFixed(2)+'₽</td>'+
    '<td class="num">'+p.boom.toFixed(2)+'</td>'+
    '<td><span class="tag '+p.b+'">'+p.verdict+'</span></td></tr>').join('');
  allBody.innerHTML = rows;
  countEl.textContent = '显示 ' + Math.min(120,list.length) + ' / ' + list.length + ' 词';
}

/* ===== 事件 ===== */
document.getElementById('filters').addEventListener('click', e=>{
  const b = e.target.closest('button');
  if(!b) return;
  filter = b.dataset.f;
  [...document.querySelectorAll('#filters button')].forEach(x=>x.setAttribute('aria-pressed', x===b?'true':'false'));
  renderAll();
});

document.querySelectorAll('th[data-s], th[data-sort]').forEach(th=>{
  th.addEventListener('click', ()=>{
    const key = th.dataset.s || ({kw:'kw',vol:'v',growth:'g',cr4:'x',drr:'y',dts:'dts',rank:'i'})[th.dataset.sort];
    if(key === undefined) return;
    if(key === 'kw'){ sortKey='kw'; sortDir = sortDir===1?-1:1; }
    else { if(sortKey===key) sortDir = -sortDir; else { sortKey=key; sortDir=-1; } }
    renderAll();
  });
});

[...document.querySelectorAll('#topbody tr, #allbody tr')].forEach(r=>{
  // 事件委托在下面统一处理，这里不绑定
});
document.querySelectorAll('.tblwrap').forEach(w=>{
  w.addEventListener('click', e=>{
    const tr = e.target.closest('tr[data-kw]');
    if(!tr) return;
    const kw = tr.dataset.kw;
    const p = RAW.points.find(x=>x.kw===kw);
    if(p) detailOf(p);
  });
});

drawQuad();
renderAll();
</script>
</body>
</html>
"""

html = (TEMPLATE
        .replace("__GEN__", d["generated_at"])
        .replace("__ATK__", str(kpi.get("kw_attack") or 0))
        .replace("__WATCH__", str(kpi.get("kw_watch") or 0))
        .replace("__AVOID__", str((kpi.get("kw_total") or 0) - (kpi.get("kw_attack") or 0) - (kpi.get("kw_watch") or 0)))
        .replace("__KWT__", str(kpi.get("kw_total") or 0))
        .replace("__ATKPCT__", f'{(kpi.get("kw_attack") or 0) / max(1, kpi.get("kw_total") or 1) * 100:.1f}')
        .replace("__TIGHT__", str(kpi.get("sku_tight") or 0))
        .replace("__SKUT__", str(kpi.get("sku_total") or 0))
        .replace("__ROWS__", "\n".join(rows_html))
        .replace("__SKUROWS__", "\n".join(sku_rows))
        .replace("__DATA__", json.dumps(payload, ensure_ascii=False, separators=(",", ":"))))

OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT.write_text(html, encoding="utf-8")
print(f"生成 {OUT} ({OUT.stat().st_size/1024:.1f} KB)")
