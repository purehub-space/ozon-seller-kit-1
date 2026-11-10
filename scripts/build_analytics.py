#!/usr/bin/env python3
"""把采集 JSON 归一进分析库，生成派生视图与看板数据。

设计原则：
1. 快照层只增不改，派生层全部是 VIEW，口径变了直接重建视图，不迁移数据。
2. 不新建库，复用 data/toys-slim.db，与已有 kw_metrics（词级横截面）同库。
3. 每张快照表都以 (业务键, 快照日) 为主键，重复导入幂等。
"""
import json
import sqlite3
import sys
from pathlib import Path

DB = Path("data/toys-slim.db")
DATA = Path("data")
OUT = Path("data/dashboard.json")

DDL = """
CREATE TABLE IF NOT EXISTS sku_snap (
  sku          TEXT NOT NULL,
  snap_date    TEXT NOT NULL,
  keyword      TEXT NOT NULL DEFAULT '',
  position     INTEGER,
  title        TEXT,
  price        REAL,
  price_old    REAL,
  stock_real   INTEGER,   -- 列表页文案「N ед осталось」真值
  stock_limit  INTEGER,   -- 加购上限，2000 封顶，不作库存用
  source       TEXT,
  PRIMARY KEY (sku, snap_date, keyword)
);

CREATE TABLE IF NOT EXISTS kw_sku_pos (
  seller      TEXT NOT NULL DEFAULT '',
  sku         TEXT NOT NULL,
  keyword     TEXT NOT NULL,
  position    INTEGER,
  pool_size   INTEGER,
  snap_date   TEXT NOT NULL,
  PRIMARY KEY (seller, sku, keyword, snap_date)
);

CREATE TABLE IF NOT EXISTS action_queue (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  sku         TEXT,
  keyword     TEXT,
  action      TEXT NOT NULL,
  params      TEXT,
  reason      TEXT,
  priority    REAL,
  created_at  TEXT,
  status      TEXT DEFAULT 'pending'
);
"""

VIRTUAL_DATE = "date(COALESCE(snap_date,'1970-01-01'))"


def _date(s, fallback="2026-11-09"):
    """把 09:48:33 这种纯时间补成完整日期。"""
    if not s:
        return fallback
    s = str(s).strip()
    if len(s) <= 8 and ":" in s:
        return f"{fallback} {s}"
    return s


def load_sku_snap(cur):
    """kw_stock_e2e.json：关键词搜索页磁贴，带库存真值。"""
    f = DATA / "kw_stock_e2e.json"
    if not f.exists():
        return 0
    d = json.loads(f.read_text(encoding="utf-8"))
    snap = _date(d.get("collected_at"))
    rows = []
    for it in d.get("kw_sku", []):
        rows.append((
            str(it.get("sku") or ""),
            snap,
            it.get("keyword") or "",
            it.get("position"),
            it.get("title"),
            it.get("price"),
            it.get("old"),
            it.get("stock_max"),
            it.get("stock_limit"),
            "kw_stock_e2e",
        ))
    cur.executemany(
        "INSERT OR REPLACE INTO sku_snap"
        "(sku,snap_date,keyword,position,title,price,price_old,stock_real,stock_limit,source)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        [r for r in rows if r[0]],
    )
    return len(rows)


def load_order_now(cur):
    """kw_order_now.json：关键词默认排序快照，价格与位置。"""
    f = DATA / "kw_order_now.json"
    if not f.exists():
        return 0
    d = json.loads(f.read_text(encoding="utf-8"))
    snap = _date(d.get("captured_at"))
    kw = d.get("kw") or ""
    rows = []
    for r in d.get("rows", []):
        rows.append((
            str(r.get("sku") or ""),
            snap,
            kw,
            r.get("pos"),
            r.get("name"),
            r.get("price"),
            r.get("old"),
            r.get("stock"),
            r.get("stock"),
            "kw_order_now",
        ))
    cur.executemany(
        "INSERT OR IGNORE INTO sku_snap"
        "(sku,snap_date,keyword,position,title,price,price_old,stock_real,stock_limit,source)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        [r for r in rows if r[0]],
    )
    return len(rows)


def load_matrix(cur):
    """kw_sku_matrix_meliora.json：竞品店铺 SKU × 关键词位次矩阵，宽表转长表。"""
    f = DATA / "kw_sku_matrix_meliora.json"
    if not f.exists():
        return 0
    d = json.loads(f.read_text(encoding="utf-8"))
    snap = _date(d.get("captured_at"))
    seller = str(d.get("seller") or "")
    kws = d.get("keywords") or []
    pool = d.get("kw_pool_sizes") or {}
    rows = []
    for r in d.get("rows", []):
        sku = str(r.get("sku_id") or r.get("sku") or "")
        if not sku:
            continue
        for kw in kws:
            pos = r.get(kw)
            if pos is None:
                continue
            rows.append((seller, sku, kw, pos, pool.get(kw), snap))
    cur.executemany(
        "INSERT OR REPLACE INTO kw_sku_pos(seller,sku,keyword,position,pool_size,snap_date)"
        " VALUES (?,?,?,?,?,?)",
        rows,
    )
    return len(rows)


# 派生视图：口径集中在这里，改口径只改这一段并重建
VIEWS = {
    "v_kw_board": """
CREATE VIEW v_kw_board AS
SELECT
  keyword,
  search_volume,
  growth_30d,
  cr4,
  drr_median,
  days_to_sell_median,
  dead_ratio,
  ad_density,
  cpc_median,
  price_median,
  review_floor,
  new60_ratio,
  blue_score,
  boom_index,
  confidence,
  total_sales,
  sku_sellers,
  CASE
    WHEN search_volume < 1000                        THEN '量不足'
    WHEN competing_products > 500                    THEN '红海'
    WHEN drr_median > 15.19                          THEN '重度投流'
    WHEN days_to_sell_median > 90                    THEN '压货'
    WHEN confidence = 'high'
         AND cr4 < 50 AND drr_median < 15.19
         AND days_to_sell_median < 30
         AND review_floor < 800                     THEN '进攻'
    ELSE '观察'
  END AS verdict
FROM kw_metrics
""",
    "v_sku_stock": """
CREATE VIEW v_sku_stock AS
SELECT
  s.sku, s.keyword, s.position, s.title, s.price,
  s.stock_real,
  s.stock_limit,
  s.snap_date,
  ROUND(s.stock_real / NULLIF(k.days_to_sell_median, 0), 1) AS ratio_vs_kw_median,
  CASE
    WHEN s.stock_real IS NULL          THEN '未知'
    WHEN s.stock_real = 2000
     AND s.stock_limit = 2000         THEN '疑似封顶'
    WHEN s.stock_real < 50            THEN '紧张'
    WHEN s.stock_real < 500           THEN '正常'
    ELSE '充足'
  END AS stock_band
FROM sku_snap s
LEFT JOIN kw_metrics k ON k.keyword = s.keyword
WHERE s.stock_real IS NOT NULL
""",
    "v_sku_cross_kw": """
CREATE VIEW v_sku_cross_kw AS
SELECT
  sku,
  COUNT(DISTINCT keyword)                 AS kw_hits,
  GROUP_CONCAT(keyword || '@' || position, ' | ') AS positions,
  MIN(position)                           AS best_position
FROM kw_sku_pos
GROUP BY sku
""",
}


def build():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.executescript(DDL)
    n1 = load_sku_snap(cur)
    n2 = load_order_now(cur)
    n3 = load_matrix(cur)
    for name, sql in VIEWS.items():
        cur.execute(f"DROP VIEW IF EXISTS {name}")
        cur.execute(sql)
    conn.commit()

    stats = {}
    for t in ("sku_snap", "kw_sku_pos", "action_queue"):
        stats[t] = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    for v in VIEWS:
        stats[v] = cur.execute(f"SELECT COUNT(*) FROM {v}").fetchone()[0]
    print("导入行数:", {"kw_stock_e2e": n1, "kw_order_now": n2, "matrix": n3})
    print("表与视图行数:", json.dumps(stats, ensure_ascii=False))

    export(cur)
    conn.close()


def export(cur):
    """导出看板用的紧凑 JSON。"""
    cur.row_factory = sqlite3.Row
    kws = [dict(r) for r in cur.execute("""
        SELECT * FROM v_kw_board
        ORDER BY boom_index DESC LIMIT 300
    """)]
    skus = [dict(r) for r in cur.execute("""
        SELECT * FROM v_sku_stock
        ORDER BY stock_real ASC LIMIT 200
    """)]
    kpi = dict(cur.execute("""
        SELECT
          COUNT(*)                                          AS kw_total,
          SUM(CASE WHEN verdict='进攻' THEN 1 ELSE 0 END)    AS kw_attack,
          SUM(CASE WHEN verdict='观察' THEN 1 ELSE 0 END)    AS kw_watch,
          ROUND(AVG(drr_median),2)                          AS drr_avg,
          ROUND(AVG(days_to_sell_median),1)                 AS dts_avg,
          ROUND(AVG(cr4),1)                                 AS cr4_avg
        FROM v_kw_board
    """).fetchone())
    kpi["sku_total"] = cur.execute("SELECT COUNT(*) FROM v_sku_stock").fetchone()[0]
    kpi["sku_tight"] = cur.execute("SELECT COUNT(*) FROM v_sku_stock WHERE stock_band='紧张'").fetchone()[0]
    kpi["sku_capped"] = cur.execute("SELECT COUNT(*) FROM v_sku_stock WHERE stock_band='疑似封顶'").fetchone()[0]

    payload = {
        "generated_at": cur.execute("SELECT datetime('now','localtime')").fetchone()[0],
        "kpi": kpi,
        "keywords": kws,
        "skus": skus,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"看板数据已导出 {OUT} ({OUT.stat().st_size} bytes)")


def preview():
    """只打印待建对象与冲突检查，不写库，供人工审核。"""
    conn = sqlite3.connect(DB)
    existing = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
    conn.close()

    planned = ["sku_snap", "kw_sku_pos", "action_queue"] + list(VIEWS)
    print(f"目标库: {DB}")
    print("库内现有对象:", ", ".join(sorted(existing)))
    print()
    for name in planned:
        mark = "已存在" if name in existing else "不存在（可新建）"
        print(f"  {name:16} {mark}")
    print()
    print("=== 将要新建的表 ===")
    print(DDL.strip())
    print("\n=== 将要新建的视图 ===")
    for name, sql in VIEWS.items():
        print(f"\n-- {name}\n{sql.strip()}")
    print("\n以上均未写入数据库。审核通过后执行：python3 scripts/build_analytics.py --apply")


if __name__ == "__main__":
    if "--apply" in sys.argv:
        build()
    else:
        preview()
