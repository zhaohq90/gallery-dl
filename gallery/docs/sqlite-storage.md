# SQLite 元数据存储与增量扫描

## 概述

在 gallery-dl 原生媒体文件下载的基础上，新增 SQLite 持久化存储方案，将推文完整元数据（内容、作者、互动数据等）写入结构化数据库，同时支持增量扫描模式，避免全量 API 爬取。

---

## 架构设计

```
users.json ─→ export.py ─→ CustomJob (DownloadJob 子类)
                  │              │
config.json ──────┘              ├─ dispatch loop
                                 │
                                 ├─ Message.Directory → 合并 metadata
                                 │
                                 └─ Message.Url →
                                      │
                                      ├─ prepare hook:
                                      │    ├─ tweet_id 已存在? → dup_count++
                                      │    │   └─ dup_count ≥ threshold → StopExtraction
                                      │    ├─ tweet_id 不存在  → dup_count = 0
                                      │    ├─ INSERT OR REPLACE users
                                      │    └─ INSERT OR IGNORE tweets (含引用关系)
                                      │
                                      ├─ [download_media=true]  → 正常下载
                                      ├─ [download_media=false] → handle_skip()
                                      │
                                      └─ after hook:
                                           └─ INSERT media + 更新操作日志统计
```

### 与原方案的关系

| 特性 | 原方案 (JSON metadata) | 新方案 (SQLite) |
|------|----------------------|-----------------|
| 存储格式 | 每文件一个 .json | 单文件 SQLite 数据库 |
| 数据查询 | 需遍历 JSON 文件 | SQL 查询，支持 JOIN |
| 去重依据 | archive.sqlite3（文件级） | tweets 表（推文级） |
| 增量扫描 | 不支持 | 连续已知推文阈值停止 |
| 作者信息 | 嵌入在推文 JSON 中 | 独立 users 表 |
| 引用关系 | 无结构化关联 | original_tweet_id / original_user_id |

---

## 数据库 Schema

### users — 用户表

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | Twitter 用户 ID（数字） |
| `screen_name` | TEXT NOT NULL | @handle |
| `name` | TEXT | 显示名称 |
| `verified` | INTEGER | 是否认证 |
| `protected` | INTEGER | 是否私密账户 |
| `followers_count` | INTEGER | 粉丝数 |
| `friends_count` | INTEGER | 关注数 |
| `statuses_count` | INTEGER | 推文总数 |
| `media_count` | INTEGER | 媒体总数 |
| `favourites_count` | INTEGER | 喜欢数 |
| `listed_count` | INTEGER | 列表数 |
| `description` | TEXT | 个人简介 |
| `location` | TEXT | 位置 |
| `profile_image` | TEXT | 头像 URL |
| `profile_banner` | TEXT | 背景图 URL |
| `url` | TEXT | 外部链接 |
| `created_at` | TEXT | 注册时间 |
| `updated_at` | TEXT | 记录更新时间 |

### tweets — 推文表

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | Twitter 推文 ID |
| `user_id` | INTEGER FK→users | 推文作者 ID |
| `content` | TEXT | 推文全文（URL 已展开） |
| `tweet_type` | TEXT | `tweet` / `retweet` / `quote` / `reply` |
| `lang` | TEXT | 语言代码 |
| `source` | TEXT | 发布客户端 |
| `sensitive` | INTEGER | 敏感内容标记 |
| `created_at` | TEXT | 发布时间 |
| `favorite_count` | INTEGER | 喜欢数 |
| `quote_count` | INTEGER | 引用数 |
| `reply_count` | INTEGER | 回复数 |
| `retweet_count` | INTEGER | 转发数 |
| `bookmark_count` | INTEGER | 书签数 |
| `view_count` | INTEGER | 查看数 |
| `original_tweet_id` | INTEGER FK→tweets | 原始推文 ID（转发/引用/回复） |
| `original_user_id` | INTEGER FK→users | 原始作者 ID |
| `original_user_name` | TEXT | 原始作者 @handle |
| `reply_to_user_id` | INTEGER FK→users | 回复对象用户 ID |
| `reply_to_user_name` | TEXT | 回复对象 @handle |
| `conversation_id` | INTEGER | 对话 ID |
| `birdwatch` | TEXT | 社区笔记内容 |
| `hashtags` | TEXT | JSON 数组，如 `["tag1","tag2"]` |
| `mentions` | TEXT | JSON 数组，如 `[{"id":123,"name":"user","nick":"Name"}]` |
| `updated_at` | TEXT | 记录更新时间 |

### media — 媒体文件表

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK AUTO | 自增 ID |
| `tweet_id` | INTEGER FK→tweets | 所属推文 ID |
| `num` | INTEGER | 推文内序号（1-based） |
| `url` | TEXT | 原始媒体 URL |
| `extension` | TEXT | 文件扩展名 |
| `filename` | TEXT | 文件名 |
| `filepath` | TEXT | 本地相对路径 |
| `created_at` | TEXT | 记录创建时间 |

### operation_log — 操作日志

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK AUTO | 自增 ID |
| `user_id` | INTEGER FK→users | Twitter 用户 ID |
| `username` | TEXT | @handle |
| `start_time` | TEXT | 开始时间 |
| `end_time` | TEXT | 结束时间 |
| `scan_mode` | TEXT | `full` / `incremental` |
| `total_scanned` | INTEGER | 本次扫描推文总数 |
| `new_tweets` | INTEGER | 新增推文数 |
| `existing_tweets` | INTEGER | 已存在推文数 |
| `images_downloaded` | INTEGER | 下载图片数 |
| `videos_downloaded` | INTEGER | 下载视频数 |
| `status` | TEXT | `running` / `success` / `failed` |

---

## 推文类型处理

### 四种推文类型

```
tweet_type = "tweet"   → 原创推文（无 retweet_id / quote_id / reply_id）
tweet_type = "retweet" → 转发推文（有 retweet_id）
tweet_type = "quote"   → 引用推文（有 quote_id）
tweet_type = "reply"   → 回复推文（有 reply_id）
```

### 引用关系存储

| tweet_type | 存储字段 | 数据来源 |
|------------|----------|----------|
| `retweet` | `original_tweet_id` = retweet_id | `legacy.retweeted_status_id_str` |
| | `original_user_name` = reply_to | `legacy.in_reply_to_screen_name`（转推者信息） |
| `quote` | `original_tweet_id` = quote_id | `legacy.quoted_by_id_str` |
| `reply` | `original_tweet_id` = reply_id | `legacy.in_reply_to_status_id_str` |
| | `reply_to_user_name` = reply_to | `legacy.in_reply_to_screen_name` |

**已知限制**：gallery-dl 当前从 API 响应中提取了原始推文的 ID 和作者 screen_name，但**未提取原始推文的完整内容**。`original_tweet_id` 字段预留了外键引用，后续可通过 gallery-dl 的 `tweet_result_by_rest_id()` API 补抓原始推文内容。

---

## 增量扫描

### 工作原理

gallery-dl 按时间倒序扫描推文（最新在前）。在增量模式下，每处理一条推文时：

1. 查询 SQLite tweets 表：该 tweet_id 是否已存在
2. **已存在** → 推入去重集合 `_dup_tweets`（set 去重）
3. **不存在** → 清空 `_dup_tweets`，写入数据库
4. 当 `len(_dup_tweets) >= incremental_threshold` → 抛出 `StopExtraction`，终止扫描

### 与全量模式对比

| | 全量模式 (`full`) | 增量模式 (`incremental`) |
|---|---|---|
| API 爬取范围 | 全部推文，直到分页结束 | 遇到阈值个连续已知推文即停止 |
| 适用场景 | 首次导出、数据恢复 | 日常同步、定时更新 |
| 数据库写入 | 全部 INSERT OR IGNORE | 只到阈值点为止 |

### scan_mode × max_count 组合行为

| scan_mode | max_count | 实际行为 |
|-----------|-----------|----------|
| `full` | `-1` | 全量扫描直到分页结束（无限制） |
| `full` | `50` | 扫到第 50 条推文时 `StopExtraction` 中止 |
| `incremental` | `-1` | 遇到连续 N 条已知推文中止，无数量上限 |
| `incremental` | `50` | 两者谁先触发谁中止（50 条上限 或 连续 N 条已知） |

> **注意**：`max_count` 对 `full` 和 `incremental` **均生效**，不受 `scan_mode` 限制。全量模式下如需不限制，请设为 `-1`。

---

## 配置参考

### 完整 config.json

```json
{
    "extractor": {
        "twitter": {
            "cookies": "./cookies.txt",
            "videos": true,
            "previews": true,
            "quoted": true,
            "text-tweets": true,
            "retweets": true,
            "replies": true,
            "pinned": false,
            "cards": false,
            "ads": false,
            "unique": true,
            "transform": true,
            "cursor": true,
            "ratelimit": "wait",
            "retries-api": 5,
            "limit": 10
        }
    },
    "archive": "./archive.sqlite3",

    "store_mode": "sql",
    "scan_mode": "incremental",
    "incremental_threshold": 10,
    "download_media": true,
    "store_db": "./twitter.db",
    "max_count": -1
}
```

### 配置项说明

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `store_mode` | string | `"json"` | 元数据存储模式：`json` 生成 .json 文件，`sql` 写入 SQLite |
| `scan_mode` | string | `"full"` | 扫描模式：`full` 全量，`incremental` 增量 |
| `incremental_threshold` | int | `10` | 增量模式下连续已知推文阈值 |
| `download_media` | bool | `true` | 是否下载媒体文件；`false` 时只抓元数据 |
| `store_db` | string | `"./twitter.db"` | SQLite 数据库路径（相对于 gallery/ 目录） |
| `max_count` | int | `-1` | 单用户最大推文数，`-1` 不限制；达到上限后中止并记录日志 |

---

## 数据抓取原理

gallery-dl **不模拟浏览器**，而是直接向 Twitter 内部 GraphQL API 发送 HTTP 请求获取 JSON 数据：

- **端点**：`https://x.com/i/api/graphql/{graphql_id}/UserTweets` 等
- **认证**：`auth_token` Cookie + Bearer Token
- **提取**：`_transform_tweet()` 从 JSON 响应中解析推文全文、作者信息、hashtags、互动计数等

所有数据均来自 Twitter 官方 API，非爬虫模拟。

---

## 操作日志示例

```
sqlite> SELECT * FROM operation_log ORDER BY id DESC LIMIT 3;

id  user_id  username    start_time           end_time             scan_mode     total  new  exist  imgs  vids  status
--- -------- ----------- -------------------- -------------------- ------------ ------ ---- ------ ----- ----- -------
3   44196397  elonmusk   2026-07-01 10:30:00  2026-07-01 10:32:15  incremental  15     3    12     2     1     success
2   123456    user2      2026-07-01 10:25:00  2026-07-01 10:28:40  incremental  10     5    5      4     0     success
1   44196397  elonmusk   2026-07-01 09:00:00  2026-07-01 09:45:30  full          320    320  0      180   45    success
```
