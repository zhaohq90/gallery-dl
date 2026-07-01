# Twitter/X 批量导出工具

基于 [gallery-dl](https://github.com/mikf/gallery-dl) 的 Twitter/X 用户内容批量导出工具。

## 需求背景

从 Twitter/X 平台批量导出指定用户的全部内容，包括推文、回复、引用、媒体文件、用户信息和头像。需要支持 Cookies 认证、多用户批量处理、去重、断点续传。

### 功能需求

- **认证方式**：通过浏览器导出的 `cookies.txt` 进行认证（Twitter 已不支持用户名密码登录）
- **导出内容**：推文 + 回复（保留纯文本推文）、引用内容媒体、用户信息 + 头像
- **媒体下载**：图片（原图优先）、视频（最高比特率）、缩略图
- **目录隔离**：每个用户独立目录，用户资料与推文内容分开放置
- **去重**：自动跳过已下载的内容（支持 SQLite 持久化归档，详见 `docs/dedup-and-persistence.md`）
- **数量控制**：可配置每次导出的推文数量
- **批量处理**：通过配置文件管理用户列表，支持启用/禁用单个用户
- **日志记录**：完整日志写入文件，任务完成后控制台输出汇总（总数、成功、失败）

## 文件结构

```
gallery/
├── README.md                      # 本文件
├── cookies.txt                    # Twitter cookies（Netscape 格式）
├── config.json                    # gallery-dl 原生配置 + 全局开关
├── users.json                     # 用户列表 + 脚本参数
├── export.py                      # 批量导出脚本
├── db.py                          # SQLite 数据库管理器（sql 模式）
├── job_wrapper.py                 # 自定义 DownloadJob 包装器
├── twitter.db                     # SQLite 数据库（sql 模式自动生成）
├── archive.sqlite3                # gallery-dl 下载归档
└── docs/
    ├── export-py-debug.md         # export.py 问题排查记录
    ├── dedup-and-persistence.md   # 去重与持久化机制详解
    └── sqlite-storage.md          # SQLite 存储与增量扫描设计文档
```

## 实现方案

### 架构

```
users.json ──→ export.py ──→ CustomJob (gallery-dl Python API)
                  │                │
config.json ──────┘                ├─ SQL 模式: db.py → twitter.db
cookies.txt ──────┘                └─ JSON 模式: metadata PP → .json 文件
```

### config.json — gallery-dl 原生配置

负责 gallery-dl 的运行时行为，关键配置项：

| 配置项 | 值 | 说明 |
|---|---|---|
| `cookies` | `"./cookies.txt"` | 引用同目录下的 cookies 文件 |
| `videos` | `true` | 下载视频（默认选最高比特率） |
| `previews` | `true` | 下载视频缩略图 |
| `quoted` | `true` | 下载引用推文中的媒体 |
| `text-tweets` | `true` | 保留纯文本推文（无媒体的推文也记录） |
| `retweets` | `false` | 不包含转推 |
| `replies` | `true` | 包含回复 |
| `unique` | `true` | 去重，跳过已处理的推文 |
| `cursor` | `true` | 支持断点续传 |
| `ratelimit` | `"wait"` | 触发速率限制时自动等待 |
| `archive` | `"./archive.sqlite3"` | SQLite 下载归档，持久化记录已下载内容 |

### 全局配置项（顶层）

| 配置项 | 值 | 说明 |
|---|---|---|
| `store_mode` | `"json"` (默认) 或 `"sql"` | 元数据存储模式：json=每文件生成 .json 伴生文件，sql=写入 SQLite 数据库 |
| `incremental_threshold` | `-1` | 连续已知推文阈值，`-1` 不限制；`> 0` 时连续 N 条已知即中止 |
| `download_media` | `true` (默认) | 是否下载媒体文件；设为 false 时仅采集元数据 |
| `store_db` | `"./twitter.db"` | SQLite 数据库路径（sql 模式生效） |
| `max_count` | `-1` | 单用户最大推文数，`-1` 不限制；达到上限后中止并记录日志 |
| `base_path` | `""` | 全局下载根目录前缀，为空时使用 `users.json` 中的 `export_root` |

### 存储模式对比

| 功能 | JSON 模式 | SQL 模式 |
|------|----------|---------|
| 元数据文件 | ✅ 每文件一个 .json | ❌ |
| 结构化查询 | ❌ 需遍历文件 | ✅ SQL / JOIN |
| 推文去重 | 依赖 archive.sqlite3 | tweets 表 |
| 作者信息 | 嵌入推文 JSON | 独立 users 表 |
| 操作日志 | ❌ | ✅ operation_log 表 |
| 增量扫描 | ❌ | ✅ 阈值中止 |

### users.json — 用户列表配置

```json
{
    "settings": {
        "export_root": ".",    // 导出根目录（默认当前 data 目录）
        "limit": 10,           // 每次 API 请求获取的推文数
        "log_file": "export.log"
    },
    "users": [
        {
            "username": "账号",           // Twitter 账号（不带 @）
            "display_name": "显示名",     // 仅用于日志显示
            "enabled": true               // false 时跳过
        }
    ]
}
```

### export.py — 批量导出脚本

**执行流程：**

1. 加载 `users.json`，读取全局设置和用户列表
2. 加载 `config.json`，验证 cookies 文件存在
3. 筛选 `enabled: true` 的用户
4. 对每个用户依次执行：
   - **导出资料**：`gallery-dl` 访问 `/info`、`/photo`、`/header_photo` 三个端点，输出到 `{export_root}/{username}/profile/`
   - **导出推文**：`gallery-dl` 访问 `/with_replies` 端点，输出到 `{export_root}/{username}/content/`
5. 单个用户失败不影响后续用户
6. 全部完成后输出汇总（总用户数、成功数、失败数、详情）

**导出后的目录结构：**

```
{export_root}/
└── {username}/
    ├── profile/    # 用户信息 + 头像 + 背景图
    └── content/    # 推文 + 回复 + 媒体文件
```

## 使用方法

### 前置条件

```bash
# 安装 gallery-dl
python -m pip install gallery-dl
```

### 步骤 1：获取 Cookies

参考 `docs/twitter-guide.zh.md` 中的详细说明，推荐使用浏览器插件导出：
- Chrome: [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
- Firefox: [Export Cookies](https://addons.mozilla.org/en-US/firefox/addon/export-cookies-txt/)

将导出的 `cookies.txt` 放到 `data/` 目录下。

### 步骤 2：编辑用户列表

编辑 `data/users.json`，填入要导出的用户：

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

### 步骤 3：运行导出

```bash
cd data/
python export.py
```

### 步骤 4：查看结果

任务完成后控制台会输出汇总：
```
============================================================
导出完成: 共 3 个用户
  成功: 2
  失败: 1

  [ OK ] @user1
  [ OK ] @user2
  [FAIL] @user3 — private account
============================================================
```

详细日志见 `data/export.log`，导出数据在 `{export_root}/{username}/` 下。

### 常见问题

**Q: 如何只导出媒体推文（不含纯文本）？**
在 `config.json` 中将 `text-tweets` 设为 `false`。

**Q: 如何导出更多推文？**
修改 `users.json` 中的 `limit` 值（每次 API 请求获取的数量）。

**Q: 如何断点续传？**
中断时会自动记录游标位置，`cursor: true` 确保下次运行自动恢复。另外 `unique: true` 保证不会重复下载已有内容。

**Q: 如何更改导出目录？**
修改 `users.json` 中 `settings.export_root`，支持相对路径（相对于 gallery 目录）或绝对路径。

**Q: SQL 模式和 JSON 模式如何选择？**
- **JSON 模式**：轻量，每个媒体文件伴生 .json 元数据文件，适合偶尔使用
- **SQL 模式**：所有数据存入 SQLite 数据库，支持 SQL 查询和增量扫描，适合定期同步
- 切换只需修改 `config.json` 中的 `store_mode` 即可

**Q: 如何使用增量扫描？**
1. 将 `config.json` 中的 `incremental_threshold` 设为正数（如 `10`）
2. 将 `store_mode` 设为 `"sql"`（增量扫描依赖 SQLite）
3. 首次运行设置 `incremental_threshold=-1` 全量抓取，后续设为正数增量同步
4. 详细说明见 `docs/sqlite-storage.md`

**Q: 如何只采集元数据不下载文件？**
将 `config.json` 中的 `download_media` 设为 `false`。此时每条推文的元数据仍会写入 SQLite，但不会下载图片/视频文件。

**Q: 如何查看操作日志？**
sql 模式下，每次运行会生成操作日志，记录每个用户的抓取统计：
```bash
sqlite3 twitter.db "SELECT * FROM operation_log ORDER BY id DESC"
```

**Q: 遇到 `Permission denied: '/data'` 权限错误？**

这是因为通过 snap 安装的 gallery-dl 启用了 strict confinement（AppArmor 沙箱），仅允许访问 `/home`、`/media` 等白名单路径，`/data` 等自定义目录不可访问。即使 snap 连接了 `removable-media` 接口也无法覆盖 `/data`。

解决方法：用 pip 安装 gallery-dl 替代 snap 版本：

```bash
# 安装 pip 版本（无文件系统限制）
python3 -m pip install gallery-dl

# 移除 snap 版本
snap remove gallery-dl
```

之后 `gallery-dl` 可以对任意路径进行读写。
