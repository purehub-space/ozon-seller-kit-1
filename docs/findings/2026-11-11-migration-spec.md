# 库存采集迁移规格（可直接搬运）

## 前置条件（两条通道都要）

**必须先有街道级地址态**，否则响应 <150KB 且库存字段被裁剪。

```
设置地址：Москва, Тверская улица, 1
判据：后续请求响应体 ≥150KB
```

`cookie` 必须用**浏览器实发的原串**（长度 1,354–1,382 字符），
不能由 dict / CookieJar 重组，否则 403。

---

## 通道 A：搜索页

### 端点

```
GET https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2?url=/search/?text={urlencode(关键词)}&page={N}
```

### Header

```
x-o3-app-name: dweb_client
cookie: <浏览器实发原串>
```

### 响应判据

| | |
|---|---|
| 成功 | `200`，`≈150,086 B`，含 `"maxItems":` |
| 失败 | `317,066 B` 且 `maxItems` 为 0 → URL 打错了（打到了 HTML） |

### 解析（Python）

```python
import re, json
raw = resp.text
u = raw.replace('\\"', '"')      # 必须二次解码，html.unescape 对它无效
skus = re.findall(r'"skuId":"(\d+)"', u)
stock = re.findall(r'"quantityButton":\{"maxItems":(\d+)', u)
```

每页 **9 个 SKU**，库存 9/9。

---

## 通道 B：店铺页

### 端点

```
GET https://www.ozon.ru/seller/{slug}/products/?page={N}
```

**不要带任何 `layout_page_index` / `paginator_token` / `search_page_state` 参数**，
那是分页壳，响应 49KB 且 0 库存。

### Header

```
cookie: <浏览器实发原串>
```

### 响应判据

| | |
|---|---|
| 成功 | `200`，**620–690 KB**，`skuId` ≥ 30 |
| 失败 | `130–150 KB` / 恰好 8 个 SKU → 无效页（首页推荐位冒充） |

### 解析（Python）

```python
import re, html as hm
h = hm.unescape(resp.text)

# 切块方向：以 skuId 为【起点】向后取到下一个 skuId
blocks = re.split(r'(?="skuId":"\d+")', h)

for b in blocks:
    sku = re.search(r'"skuId":"(\d+)"', b)
    if not sku: continue
    m = re.search(r'"quantityButton":\{"maxItems":(\d+),\s*"updateCartAction":\{"id":"(\d+)"', b)
    ...
```

⚠️ 若按「以 skuId 为终点向前切」，全部解析成 None。

### 价格结构

```
"priceV2":{"price":[{"text":"99 ₽","textStyle":"PRICE"}],
           "priceStyle":{"styleType":"CARD_PRICE"}}
```

- `styleType: "CARD_PRICE"` → 绿标（卡价）
- `textStyle: "PRICE"` → 当前售价（黑标）
- `textStyle: "ORIGINAL_PRICE"` → 划线原价

注意 `₽` 前是 NBSP `\u00a0`，折扣符号是 `−`（U+2212）。

---

## 限流（硬约束）

| 项 | 值 |
|---|---|
| 会话级配额 | **约 175–250 请求**（超过即突变 403） |
| IP 级恢复 | 约 **47 分钟** |
| 并发安全值 | **15**（30 立即崩） |
| 熔断 | 提前熔断，永不触发 403 |

HTML 与 API **共享同一配额**。

---

## 吞吐估算

| 目标 | 通道 | 请求数 | 耗时 |
|---|---|---|---|
| 549 SKU | 店铺页 | 25 | ~40 秒 |
| 549 SKU | 搜索页 | 61 | ~2–3 分钟 |
| 10,000 SKU | 店铺页 | 334 | 受配额限制，需分 2 个会话 |

**单会话上限约 5,000–7,000 SKU**（按 200 请求 × 30 算），超过必须换会话等冷却。
