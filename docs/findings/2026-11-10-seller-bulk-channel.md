# 店铺页批量取库存通道（已验证）

> 建立时间：2026-11-10 20:40 CST
> 结论状态：**已实测打通**，一次请求 41 对库存 / 38 个独立 SKU

## 一、为什么值得做

| 通道 | 1 次请求带回 | 1 万件的请求数 |
|---|---|---|
| PDP API `url=/product/{sku}/` | 1 个 SKU | 10,000 |
| **店铺页 `url=/seller/{slug}/products/`** | **38–41 个 SKU** | **约 430** |

**约 24–40 倍请求效率提升。**

## 二、店铺 URL 用 slug，不用数字 ID

- 店铺页真实 slug 示例：数字 ID `4616499` → slug **`jinghongtu`**
- 两种都能请求成功，但 slug 是站内主用法（分页请求里只用 slug）

### seller_name → slug 推断规则（实测 4/5 命中）

规则：**转小写 → 空格换连字符 → 去掉特殊字符（«»、点、引号等）**

| seller_name | 推断 slug | 实测结果 |
|---|---|---|
| Сима-Ленд - Маркет | `sima-lend` | ✓ 200，标题「Каталог Сима-Ленд」 |
| NNN SHOP | `nnn-shop` | ✓ 200，标题「Каталог NNN Shop」 |
| СИМБАТ | `simbat` | ✓ 200，标题「Каталог СИМБАТ」 |
| ФОРМИКС | `formiks` | ✓ 200，标题「Каталог ФОРМИКС」 |
| Малыши и Малышки | `malyshi-i-malyshki` | ✗ 200 但 134KB，标题为空 |

**判据：响应 ≥200KB 且标题含「Каталог」= slug 正确；<150KB 或标题空 = 未命中。**

`seller_name` 存在于 `ozon-seller-kit/data/toys-slim.db` 的 `sku` 表，29,823 行全覆盖。

## 三、请求方式

```
GET https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2?url=/seller/{slug}/products/
```

- 需街道地址态（`Москва, Тверская улица, 1`），否则库存字段缺失
- `url=` 必须用未编码的完整路径串；用 `params={"url":...}` 会把 `/` 编码、落到别的页面
- 浏览器页内 fetch 需 `credentials:'include'` + `headers:{'x-o3-app-name':'dweb_client'}`
- 首页 referer 即可，无需先渲染店铺页

## 四、★ 解析陷阱（两次踩坑，务必记住）

响应里的商品 JSON 是**二次编码**：

```
\"quantityButton\":{\"maxItems\":2000, \"updateCartAction\":{\"id\":\"1546517660\", ...
```

- ❌ 直接正则 `"quantityButton":\{"maxItems"` → 0 命中（误判「API 不含库存」）
- ❌ `html.unescape()` → 仍然 0 命中（`\"` 不是 HTML 实体）
- ✅ **`t.replace('\\"','"')` 后再正则** → 41 对

而**渲染后 DOM** 里是 HTML 实体 `&quot;` 编码：

```
&quot;quantityButton&quot;:{&quot;maxItems&quot;:2000, ...
```

- ✅ 对 DOM 用 `html.unescape()` → 46 对

两种来源要分别处理，别用同一套正则。

解析正则（自己实测）：
```python
p = re.findall(r'"quantityButton":\{"maxItems":(\d+),\s*"updateCartAction":\{"id":"(\d+)"', t.replace('\\"','"'))
```

## 五、实测数据（店铺 jinghongtu / 4616499）

| 指标 | API 响应 | 渲染后 DOM |
|---|---|---|
| 体积 | 311,287 B | 1,321,113 字符 |
| `quantityButton` 原始次数 | 41 | 46 |
| 解析后对数 / 独立 SKU | **41 对 / 38 SKU** | 46 对 / 38 SKU |
| 2000 封顶 | 23 个 | 23 个 |
| 正常值 | 15 个 | 15 个 |

样例：`sku=1546517660 maxItems=2000`、`sku=225851726 maxItems=9`、`sku=1620591213 maxItems=22`、`sku=5918363558 maxItems=16`、`sku=138898173 maxItems=91/49`（两变体）、`sku=231349313 maxItems=2000/744`、`sku=976587255 maxItems=37`。

## 六、店铺分页：拿不到更多库存（已验证）

真实分页请求形态（浏览器滚动时自动发出）：

```
?url=/seller/jinghongtu/products/?layout_page_index=2&page=2&paginator_token=3618992&search_page_state=be0RB_0m8eO5QOstgBHnbj0kiHNl-h3x34s8dnSHMCv3R...
```

变体：`?layout_container=default&layout_page_index=N&page=N&paginator_token=3635012&search_page_state=...`

**实测结果：分页响应 200 / 49,052 B / 0 个库存字段** —— 是分页组件壳，不带商品卡片。滚动 10 次（wheel 3000px）SKU 数恒为 38，商品链接从 124 涨到 141（懒加载只加卡片不加库存）。

**所以单店可靠产出 = 首屏 38–41 个。**

## 七、卖家分布与覆盖面

`toys-slim.db.sku` 共 29,823 行，分布：

| 阈值 | 卖家数 | 覆盖 SKU | 占比 |
|---|---|---|---|
| SKU≥40 | 59 | 4,331 | 14.5% |
| SKU≥20 | 184 | 7,629 | 25.6% |
| **SKU≥10** | **476** | **11,540** | **38.7%** |
| 1–9 | 9,978 | 约 16,000 | — |

长尾极重：9,978 个卖家只有 1–9 个 SKU，这些只能走 PDP。

## 八、产能结论

**476 个头部卖家 × 1 请求 = 11,540 个 SKU**，约 4 分钟（2 请求/秒），配合会话配额 150 提前熔断 → 需 4 个会话（每次 mint 约 70 秒）。

混合策略（全量 29,823）：
1. 头部 476 卖家 → 店铺页批量（11,540 个，约 15 分钟含 mint）
2. 剩余 18,283 个长尾 → PDP + 每 150 请求自动 mint（约 3.5 小时）

前 1 万件用店铺批量可压到约 15 分钟。

## 九、待验证

- [ ] 476 个卖家 slug 批量推断的实际命中率（当前样本 4/5，需扩大）
- [ ] 店铺 API 走 curl_cffi（而非页内 fetch）是否同样返回 41 对（当前 cookie 配额已满，需重新 mint 后测）
- [ ] 单店商品数远大于 38 时（如 345 个商品的店铺）首屏是否只给 38 个
