# Ozon 前台字段 → 接口映射（实测）

| 字段 | 接口 / 位置 | 实测 | 成本 |
|---|---|---|---|
| **库存** | ①店铺 HTML `/seller/{slug}/products/?page=N` → `quantityButton.maxItems`<br>②PDP `stockNumber.text` / `freeRest` | 549/549 覆盖 | ①1 请求/22 SKU<br>②1 请求/SKU |
| **绿标价**（Ozon Card 价） | PDP `webPrice.*.cardPrice`<br>店铺页 `priceV2.priceStyle.styleType=CARD_PRICE` | 99 ₽ | 同 PDP |
| **黑标价**（普通价） | PDP `webPrice.*.price` | 109 ₽ | 同 PDP |
| **划线原价** | PDP `webPrice.*.originalPrice`<br>店铺页 `textStyle:ORIGINAL_PRICE` | 149 ₽ | 同 PDP |
| **SKU 重量** | PDP `Weight_N` → `Вес товара, г` | 500 | 同 PDP |
| **评论数** | PDP `webReviewProductScore.reviewsCount`<br>或 `/product/{sku}/reviews/` | 13,769 | 同 PDP |
| **评分** | 同上 `totalScore` | 4.8 | 同 PDP |
| **星级分布/差评占比** | `/product/{sku}/reviews/` → `scoreCounts` | 5★23798/4★1423/3★215/2★63/1★141 | **额外 1 请求** |
| **店铺总订单量** | **不存在** | `ordersCountMinOrdersToDisplay:1000` 是阈值 | — |

## 关键结论

1. **PDP 单请求产出 7 个字段**：库存 + 绿标 + 黑标 + 原价 + 重量 + 评论数 + 评分。
2. **差评占比需额外 `/reviews/` 请求**（PDP 里 `webReviewProductScore` 是 `displayType:simple` 简版）。
3. **订单量前台完全没有**。`Заказы` 命中全是导航菜单；`soldCount`=0。

## 差评占比口径
`(1星 + 2星) / 总数`
例：`(141+63)/25640 = 0.80%`

## 店铺页取价 vs PDP 取价的差异（待核）
sima 店铺页 SKU 4316600423 现价 255₽，PDP 同 SKU cardPrice 99₽ / price 109₽。
两者不是同一时点、也可能不是同一商品变体，**跨通道价格不可直接对比**。
