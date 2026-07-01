# 批量导出工具 — 使用指南

> 基于 [gallery-dl](https://github.com/mikf/gallery-dl) 的 Twitter/X 用户内容批量导出工具。

---

## 1. 快速开始

### 1.1 环境准备

```bash
# 进入项目目录
cd gallery/

# 创建虚拟环境（仅首次）
python3 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate

# 安装依赖
pip install gallery-dl
```

> **说明**：macOS Homebrew 的 Python 受 PEP 668 保护，不允许直接 `pip install`。
> 使用虚拟环境可以隔离依赖，避免污染系统 Python。

### 1.2 准备 Cookies

浏览器导出 Netscape 格式 `cookies.txt`，放置到 `gallery/` 目录：
- Chrome: [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) 插件
- Firefox: [Export Cookies](https://addons.mozilla.org/en-US/firefox/addon/export-cookies-txt/) 插件

### 1.3 编辑用户列表

```bash
vim users.json
```

### 1.4 运行

```bash
# 方式一：使用启动脚本（推荐）
./export.sh

# 方式二：手动激活后运行
source .venv/bin/activate
python export.py
```

---

## 2. 文件结构

```
gallery/
├── export.py              # 主脚本
├── export.sh              # 一键启动脚本（自动激活 venv）
├── db.py                  # SQLite 管理器（sql 模式）
├── job_wrapper.py         # gallery-dl Job 包装器
├── config.json            # 配置文件
├── users.json             # 用户列表
├── cookies.txt            # Twitter 认证（需自行导出）
├── .gitignore             # Git 忽略规则
├── .venv/                 # Python 虚拟环境（不纳入版本控制）
├── twitter.db             # SQLite 数据库（sql 模式自动创建）
├── archive.sqlite3        # 下载归档（gallery-dl 原生）
└── docs/
    ├── usage-guide.md          # 本文件
    ├── sqlite-storage.md       # SQLite 存储与增量扫描设计
    ├── dedup-and-persistence.md # 去重与持久化机制
    └── export-py-debug.md      # 排查记录
```

---

## 3. 配置参数

### 3.1 全局配置 (`config.json`)

```json
{
    "extractor": {
        "twitter": {
            "cookies": "./cookies.txt",
            "videos": true,
            "quoted": true,
            "text-tweets": true,
            "retweets": true,
            "replies": true,
            "unique": true,
            "cursor": true,
            "ratelimit": "wait",
            "limit": 10
        }
    },
    "archive": "./archive.sqlite3",

    "store_mode": "sql",
    "incremental_threshold": 10,
    "download_media": true,
    "store_db": "./twitter.db",
    "max_count": -1
}
```

### 3.2 全局参数一览

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `store_mode` | string | `"json"` | 元数据存储模式 |
| `incremental_threshold` | int | `-1` | 连续已知推文阈值，`-1` 不限制 |
| `download_media` | bool | `true` | 是否下载媒体文件 |
| `store_db` | string | `"./twitter.db"` | SQLite 数据库路径（sql 模式） |
| `max_count` | int | `-1` | 单用户最大推文数，`-1` 不限制 |

### 3.3 用户列表 (`users.json`)

```json
{
    "settings": {
        "export_root": ".",
        "limit": 10,
        "log_file": "export.log"
    },
    "users": [
        {
            "username": "elonmusk",
            "display_name": "Elon Musk",
            "enabled": true
        },
        {
            "username": "inactive_user",
            "display_name": "暂不导出",
            "enabled": false
        }
    ]
}
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `settings.export_root` | string | 导出根目录（相对路径相对于 gallery/） |
| `settings.limit` | int | 每次 API 请求获取的推文数（传给 gallery-dl） |
| `settings.log_file` | string | 日志文件名 |
| `users[].username` | string | Twitter 账号（不带 @） |
| `users[].display_name` | string | 仅用于日志显示 |
| `users[].enabled` | bool | 设为 false 时跳过该用户 |

---

## 4. 存储模式

### 4.1 JSON 模式 (`store_mode: "json"`)

每下载一个媒体文件，同目录生成同名 `.json` 元数据伴生文件：

```
{export_root}/{username}/content/
├── 1234567890_1.jpg
├── 1234567890_1.json       # 推文完整元数据
├── 1234567890_2.jpg        # 同一推文的第二张图
├── 1234567890_2.json       # 同上
```

JSON 文件包含：推文 ID、全文、作者信息、hashtags、互动计数等。

**适用场景**：偶尔使用，不需要复杂查询。

### 4.2 SQL 模式 (`store_mode: "sql"`)

所有元数据写入 SQLite 数据库（`twitter.db`），包含四张表：

| 表名 | 内容 |
|------|------|
| `users` | 作者信息（ID、handle、昵称、粉丝数等） |
| `tweets` | 推文完整数据（内容、类型、互动计数、引用关系） |
| `media` | 媒体文件记录（URL、扩展名、本地路径） |
| `operation_log` | 操作日志（每次运行的统计信息） |

**适用场景**：定期同步，需要 SQL 查询和增量扫描。

### 4.3 模式切换

修改 `config.json` 中的 `store_mode`，重新运行即可，无需其他操作。

---

## 5. 中止条件

通过两个参数控制扫描何时停止，`-1` 表示不限制，`> 0` 时生效。两条规则相互独立，**谁先触发谁中止**。

### 5.1 参数组合

| max_count | incremental_threshold | 效果 |
|-----------|----------------------|------|
| `-1` | `-1` | **全量扫描**，永不中止 |
| `50` | `-1` | 扫到第 50 条推文即中止 |
| `-1` | `10` | 连续 10 条已知推文时中止 |
| `50` | `10` | 50 条上限 或 连续 10 条已知，谁先触发谁停 |

### 5.2 典型场景

| 场景 | 配置 | 说明 |
|------|------|------|
| 首次全量导出 | `max=-1, threshold=-1` | 无限制，扫到底 |
| 日常增量同步 | `max=-1, threshold=10` | 只抓增量，遇连续已知自动停 |
| 调试快速验证 | `max=20, threshold=-1` | 每个用户只抓 20 条 |
| 混合模式 | `max=500, threshold=15` | 上限 500 条 + 连续已知保护 |

---

## 6. 下载开关

`download_media` 控制是否下载媒体文件：

| 值 | 行为 |
|----|------|
| `true` (默认) | 正常下载图片/视频 + 记录元数据 |
| `false` | **仅采集元数据**，不下载任何文件 |

**适用场景**：
- 只想建立推文索引，不需要媒体文件
- 调试阶段快速验证数据采集逻辑
- 磁盘空间有限时只保存结构化数据

---

## 7. 推文类型

工具自动识别并标注四种推文类型：

| tweet_type | 说明 | 识别依据 |
|------------|------|----------|
| `tweet` | 原创推文 | 无 retweet_id / quote_id / reply_id |
| `retweet` | 转发推文 | 有 retweet_id |
| `quote` | 引用推文 | 有 quote_id |
| `reply` | 回复推文 | 有 reply_id |

对于转发/引用/回复，会记录原始推文 ID 和作者信息：
- `original_tweet_id` — 被引用/转发/回复的原始推文 ID
- `original_user_name` — 原始作者 @handle
- `reply_to_user_name` — 回复对象 @handle

---

## 8. 操作日志

SQL 模式下每次运行生成操作日志（`operation_log` 表），每条记录包含：

| 字段 | 说明 |
|------|------|
| `username` | 用户 @handle |
| `start_time` / `end_time` | 起止时间 |
| `scan_mode` | full / incremental:N / max:N / mixed |
| `total_scanned` | 本次扫描推文总数 |
| `new_tweets` | 新增推文数 |
| `existing_tweets` | 已存在推文数 |
| `images_downloaded` | 下载图片数 |
| `videos_downloaded` | 下载视频数 |
| `status` | success / failed |

**查看日志**：
```bash
sqlite3 gallery/twitter.db "SELECT * FROM operation_log ORDER BY id DESC"
```

---

## 10. 运行输出示例

```
============================================================
Twitter/X 批量导出开始 — 2026-07-01 12:00:00
配置文件: /path/to/gallery/users.json
存储模式: sql
下载媒体: 是
单用户上限: 不限制
增量阈值: 10 条连续已知推文
数据库:   ./twitter.db
Cookies: /path/to/gallery/cookies.txt
导出根目录: /path/to/export
用户总数: 2 (启用: 2, 禁用: 0)

[1/2] Elon Musk (@elonmusk)
  → 导出用户资料...
  ✓ 资料完成
  → 导出推文 (limit=10)...
  → incremental: 连续 10 条已知推文，中止扫描
  ✓ 推文完成 — 扫描 20, 新增 2, 已有 18, 图片 2, 视频 0

[2/2] Test User (@testuser)
  → 导出用户资料...
  ✓ 资料完成
  → 导出推文 (limit=10)...
  ✓ 推文完成 — 扫描 5, 新增 5, 已有 0, 图片 3, 视频 1

============================================================
导出完成: 共 2 个用户
  成功: 2
  失败: 0

  [ OK ] @elonmusk 扫描20 新增2 已有18 图片2
  [ OK ] @testuser 扫描5 新增5 图片3 视频1

数据目录: /path/to/export
日志文件: /path/to/gallery/export.log
SQLite DB: /path/to/gallery/twitter.db
============================================================
```

---

## 10. 常见问题

### Q: 如何从零开始？

```bash
# 1. 创建虚拟环境并安装依赖
cd gallery/
python3 -m venv .venv
source .venv/bin/activate
pip install gallery-dl

# 2. 导出 Twitter cookies（浏览器插件）
#    → 将 cookies.txt 放到 gallery/ 目录

# 3. 编辑用户列表
vim users.json

# 4. 首次使用建议配置
#    store_mode = "sql"
#    incremental_threshold = -1
#    max_count = -1

# 5. 运行
./export.sh
```

### Q: 首次全量导出后如何日常增量同步？

将 `incremental_threshold` 从 `-1` 改为 `10`（或其他正数），重新运行即可。

### Q: 纯元数据不下载怎么配置？

```json
"download_media": false,
"store_mode": "sql"
```

### Q: 调试时只想抓几条看看？

```json
"max_count": 20,
"download_media": false
```

### Q: JSON 模式和 SQL 模式能同时用吗？

不能。`store_mode` 是互斥的：`"json"` 生成 .json 文件，`"sql"` 写入数据库。切换后重新运行，之前的数据不受影响。

### Q: 如何重置增量扫描状态？

删除 `twitter.db` 文件，重新全量抓取即可（`max_count=-1, incremental_threshold=-1`）。

### Q: 导出的数据在哪里？

- 媒体文件：`{export_root}/{username}/profile/`（用户信息）和 `content/`（推文媒体）
- SQLite 数据库：`gallery/twitter.db`
- 运行日志：`gallery/export.log`

### Q: 遇到 cookies 过期怎么办？

重新从浏览器导出 `cookies.txt`，覆盖 `gallery/cookies.txt` 即可，无需其他操作。
