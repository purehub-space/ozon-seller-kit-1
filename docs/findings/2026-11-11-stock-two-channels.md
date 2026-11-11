# 库存采集的两条通道（2026-11-11 全部实测）

## 一句话结论

| | 搜索页 | 店铺页 |
|---|---|---|
| **走哪个口** | **API**（`entrypoint-api`） | **页面 HTML 本体** |
| 反面陷阱 | ❌ HTML 是空壳（0 SKU） | ❌ API 是推荐位（非本店） |
| 每页 SKU | **9** | **30** |
| 库存覆盖 | **9/9 = 100%** | **549/549 = 100%** |
| 需要 slug | ❌ 不需要 | ✅ 需要 |

**两条通道的可用口正好相反。** 这是最容易踩错的地方。

## 通道 A：搜索页 → 必须走 API

### 正确请求

```
GET /api/entrypoint-api.bx/page/json/v2?url=/search/?text=<urlencode(关键词)>&page=N
```

实测：`200 / 150,086 B`，`skuId` 9 个、`maxItems` 9 个、`quantityButton` 9 个。

### 反面：直接 fetch HTML

```
GET /search/?text=игрушки&page=1
→ 200 / 317,066 B / skuId=0 / maxItems=0 / quantityButton=0
```

**317KB 的 HTML 里一个商品都没有**，商品全靠 API 后面拉。所以搜索页**不能复用店铺页那套 HTML 解析**。

### 字段

- 库存：`"quantityButton":{"maxItems":N,...}`
- 价格：`"priceV2":{"price":[...],"priceStyle":{"styleType":"CARD_PRICE"}}`
- 每页 **9 个 SKU**

## 通道 B：店铺页 → 必须走 HTML 本体

### 正确请求

```js
fetch('/seller/{slug}/products/?page=N', {credentials:'include'})
```

实测：`200 / 620–690 KB`，每页 **30 个 SKU**，页间零交集。

### 反面：走 API

```
GET ?url=/seller/{slug}/products/
→ 返回的 38 个商品与目标池交集 0
```

**API 给的是「通用推荐位商品」，不属于该店铺**，虽然页面标题正确显示店名。

### 字段

- 库存：`"quantityButton":{"maxItems":N,"updateCartAction":{"id":"<sku>"}}`
- 价格：同上 `priceV2` / `priceStyle.styleType`
- 每页 **30 个 SKU**

## 效率对比（拿 549 个 SKU 的库存）

| 通道 | 请求数 | 耗时 | 备注 |
|---|---|---|---|
| 店铺页 HTML | **25** | **约 40 秒** | 单请求 22 SKU |
| 搜索页 API | **61** | 约 2–3 分钟 | 单请求 9 SKU |
| PDP 逐条 | 549 | 4–8 分钟 | 单请求 1 SKU |

## 怎么选用

1. **已知 slug** → 走店铺页 HTML，30/页最快。
2. **不知道 slug** → 走搜索页 API，用关键词切开 SKU 池；不需要 slug 是它唯一的优势。
3. **要全套字段**（绿标/黑标/重量/评论）→ 必须回 PDP，前两条都只给库存+价格+评分。

## 库存封顶

`maxItems` > 2000 时一律显示 **2000**，真值未知。sima-lend 549 个里 161 个（29%）命中天花板。
