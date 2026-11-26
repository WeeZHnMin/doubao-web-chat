# 豆包 Web：mssdk / msToken 机制记录

> 状态：**接口层已摸清，生成层（strData 加密指纹）未逆向**。
> 关键结论：**localStorage 的 `xmst` 可直接当作 msToken 使用（已实测通过）**，因此当前无需每轮刷新，也无需逆向 strData。

---

## 0. 结论先行

| 问题 | 结论 |
|---|---|
| msToken 是什么 | 字节 mssdk（风险 SDK）生成的设备风险 token |
| 能否直接用 `xmst` 当 msToken | ✅ 能（已实测发消息成功、多轮成功） |
| 是否需要每轮刷新 msToken | ❌ 不需要，`xmst` 是稳定母 token，约几十分钟~数小时有效 |
| 彻底自动化轮换还差什么 | `strData` 的生成算法（加密设备指纹）未逆向 |

---

## 1. 端点与调用流程

```
POST https://mssdk.bytedance.com/web/r/token?ms_appid=497858
     └─ 首次（无 msToken 参数）  → 响应头 x-ms-token 返回初始 token
     └─ 刷新（带 msToken=旧token）→ 响应头 x-ms-token 返回新 token

POST https://mssdk.bytedance.com/web/common?ms_appid=497858&msToken=...
     └─ 事件上报（高频，msToken 每调用都在变）
```

`ms_appid` = `497858`（豆包 chat 的 app id）。

---

## 2. 请求体结构（POST /web/r/token）

```json
{
  "magic": 538969122,
  "version": 1,
  "dataType": 8,
  "strData": "<加密设备指纹，base64，约 4KB>",
  "tspFromClient": 1795698990838,
  "ulr": 0
}
```

| 字段 | 含义 |
|---|---|
| `magic` | 请求魔数 `538969122`（固定） |
| `version` | `1` |
| `dataType` | `8` |
| `strData` | **加密设备指纹**（必填、被校验，见 §4） |
| `tspFromClient` | 客户端时间戳（ms） |
| `ulr` | `0` |

请求头（关键）：
- `content-type: text/plain;charset=UTF-8`
- `user-agent` / `referer` / `sec-ch-ua-*`（标准浏览器头）
- 无特殊 `x-mssdk-info` / `x-ms-req` 头（这些出现在 CORS 预检里）

---

## 3. 响应结构

**响应头（关键）**：
```
x-ms-token: <新 token>          ← 刷新后的 msToken 在这里
access-control-expose-headers: x-ms-token,x-ms-resp
access-control-allow-origin: https://www.doubao.com
access-control-allow-credentials: true
```

**响应体**（很小，只是 ACK）：
```json
{"maigc": 538051346, "version": 1, "dataType": 8}
```

注意：响应体里没有 token，token 只在 `x-ms-token` 响应头里。

---

## 4. 关键实测

| 实验 | 结果 |
|---|---|
| `strData` 置空发 `/web/r/token` | `{"resultCode":-7,...}`，**拒绝**，无 `x-ms-token` |
| 用 `localStorage.xmst` 直接当 msToken 发 `/chat/completion` | ✅ 成功创建对话、AI 正常回复 |
| 用 `/chat/completion` 请求里抓到的 msToken 发请求 | ✅ 成功（同窗口内可复用） |

→ **`strData` 必填且被服务端校验**；但 **`xmst` 可绕开整个轮换，直接当 msToken 用**。

---

## 5. token 关系（三种 token）

| token | 来源 | 说明 |
|---|---|---|
| `xmst` | `localStorage.xmst` | 母 token，客户端生成/缓存，稳定 |
| `x-ms-token` | `/web/r/token` 响应头 | 服务端下发的 token |
| 每请求 `msToken` | mssdk 客户端派生 | 短时 token，在 `/web/common` 里高频轮换（`4101QhGW…`/`WbQc23q5…`/`4knuIuSI…` 等） |

关键发现：**`xmst` 也出现在 `/web/common` 的 msToken 里**（如请求 #1686），且**直接当 `/chat/completion` 的 msToken 用也通过**。说明服务端对 msToken 的校验不是严格「必须是最新派生值」，`xmst` 这类母 token 即可。

---

## 6. 已摸清 vs 未摸清

### ✅ 已摸清（接口层）
- 端点：`/web/r/token`、`/web/common`，`ms_appid=497858`
- 请求体结构：`magic/version/dataType/strData/tspFromClient/ulr`
- 响应：新 token 在 `x-ms-token` 响应头
- `strData` 必填且校验（空 → `resultCode:-7`）
- `xmst` 可直接当 msToken（稳定、无需轮换）

### ❌ 未摸清（生成层）
- `strData` 的生成算法：设备指纹采集内容 + 加密算法（约 4KB base64）
- mssdk JS 的具体位置：捆在主包内；`mst.885c5796d9.js` **不是** mssdk（无 `strData`/`magic`/`r/token` 关键字）
- 每请求 msToken 的派生算法（如何从母 token 派生短时 token）

---

## 7. 若要彻底自动化轮换（路线图）

当前不需要（`xmst` 直接可用），但若 `xmst` 失效频繁、要彻底脱离浏览器：

1. **定位 mssdk JS**：在主包/async chunk 里搜 `538969122`（magic）或 `strData` 或 `dataType:8`；`mst.js` 已排除。
2. **逆向 `strData` 生成**：设备指纹采集（屏幕/UA/时区/硬件等）+ 加密算法（类似 bdms 的 RC4/Base64/SM3 风格，或 AES）。
3. **逆向每请求 msToken 派生**：母 token → 短时 token 的客户端派生逻辑。
4. **或走浏览器辅助**：用 Playwright 定时从浏览器 `localStorage` 读新 `xmst` 回填（简单，但依赖浏览器存活）。

---

## 8. 附：mssdk 相关网络请求索引（本次抓包）

| # | 请求 | 说明 |
|---|---|---|
| 526 | POST /web/r/token（无 msToken） | 首次，响应头下发 `x-ms-token: p_4fRmk7J8uxyfog…` |
| 1347 | POST /web/r/token?msToken=p_4fRmk7J8uxyfog… | 刷新，响应头 `x-ms-token: htxWt5vPuUVJ…` |
| 1371/1374 | POST /web/r/token?msToken=… | 继续刷新 |
| 1569…1710 | POST /web/common?msToken=… | 事件上报，msToken 每调用轮换 |

`strData` 实测样例（来自 #1347，已截断）：`fR9vRtxIeiO+vJoK7Jfk3mkz92TBvKVNhx2zGsfY6b5OWORUYNES/dbq1QigtKh7…`（约 4KB base64）。
