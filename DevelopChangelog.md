# Develop 分支更新日志

> 本文档记录 `develop` 分支相对于 `master` 分支新增的功能和文档，按时间逆序排列。
> 仅包含新功能、重要文档，配置变更和小型 Bug 修复已忽略。

---

## 2026-07-01 — SQLite 结构化存储、增量扫描、使用指南

**新增功能：** SQLite 结构化元数据存储、增量扫描、下载开关、单用户上限控制。

**新增文件：**

| 文件 | 说明 |
|------|------|
| [`gallery/db.py`](gallery/db.py) | SQLite 数据库管理器（users / tweets / media / operation_log 四表） |
| [`gallery/job_wrapper.py`](gallery/job_wrapper.py) | 自定义 DownloadJob（增量检测 + SQL 写入 + 下载/上限控制） |
| [`gallery/docs/sqlite-storage.md`](gallery/docs/sqlite-storage.md) | 设计文档（Schema、推文类型处理、增量原理） |
| [`gallery/docs/usage-guide.md`](gallery/docs/usage-guide.md) | 使用指南（完整参数说明、场景示例、FAQ） |

**重构文件：**

| 文件 | 变更 |
|------|------|
| `gallery/export.py` | subprocess CLI → gallery-dl Python API；JSON/SQL 双模式；操作日志统计 |
| `gallery/config.json` | 新增 6 个全局配置项；postprocessors 改为按模式动态加载 |
| `gallery/README.md` | 新增存储模式对比、扫描模式、FAQ；架构图更新 |

**全局配置项（`config.json`）：**

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `store_mode` | string | `"json"` | 元数据存储：`json`（.json 伴生文件） / `sql`（SQLite 数据库） |
| `incremental_threshold` | int | `-1` | 连续已知推文阈值，`-1` 不限制；`> 0` 时生效 |
| `download_media` | bool | `true` | 是否下载媒体文件；`false` = 仅采集元数据 |
| `store_db` | string | `"./twitter.db"` | SQLite 数据库路径（sql 模式） |
| `max_count` | int | `-1` | 单用户最大推文数，`-1` 不限制；达到上限后中止并记录日志 |

> 两个中止参数独立工作，`-1` = 不限制，谁先触发谁中止。两个均为 `-1` 时等同全量扫描。

**推文类型处理：**
- `tweet` — 原创；`retweet` — 转发；`quote` — 引用；`reply` — 回复
- 转发/引用/回复记录 `original_tweet_id` + `original_user_name`，可按需通过 `tweet_result_by_rest_id()` API 补抓原推

**操作日志：** `operation_log` 表记录每次运行的统计（扫描数、新增数、图片/视频下载数），支持 SQL 查询追踪。

**注意事项：**
- JSON 和 SQL 模式互斥，切换后重新运行即可
- 增量扫描仅 SQL 模式支持
- `max_count` 和 `incremental_threshold` 均可触发 `StopExtraction`，日志会明确标注中止原因

---

## 2026-06-04 — 元数据持久化（推文内容 JSON 存储）

**新增功能：** 启用 gallery-dl 内置 `metadata` 后处理器，将每条推文的完整元数据写入 JSON 文件，与媒体文件并列存放。

**背景：** gallery-dl 通过 Twitter 内部 GraphQL API 获取数据时，已从 API 响应中解析了丰富的业务字段（推文全文、作者信息、hashtags、互动数据等），并通过 `_transform_tweet()` 注入了每个文件的 `kwdict`。但默认行为只保存媒体文件，元数据在下载完成后被丢弃。

**变更概要：**

- 在 `gallery/config.json` 中新增 `postprocessors` 配置节，启用 `metadata` 后处理器
- 每下载一个媒体文件，自动在同目录生成同名 `.json` 文件，包含完整推文元数据
- 配置 `skip: true`，如果 JSON 已存在则跳过写入（配合 archive 使用）

**JSON 中包含的字段：**
- `tweet_id`, `retweet_id`, `quote_id`, `reply_id`, `conversation_id` — 推文标识
- `content` — 推文完整文本（URL 已展开、HTML 实体已解码）
- `author` — 作者完整信息（id, name, nick, verified, followers_count 等）
- `date` — 发布时间
- `hashtags`, `mentions` — 标签和 @提及列表
- `favorite_count`, `quote_count`, `reply_count`, `retweet_count`, `bookmark_count`, `view_count` — 互动数据
- `lang`, `source` — 语言和客户端来源
- `community` — 所属社区信息
- `birdwatch` — 社区笔记内容
- 文件维度字段：`num`, `url`, `extension`, `filename`

**导出后的目录结构示例：**
```
{export_root}/{username}/content/
├── 1234567890_1.jpg       # 媒体文件
├── 1234567890_1.json      # 元数据（推文全文+作者+互动+...）
├── 1234567890_2.jpg       # 同一推文的第二张图
├── 1234567890_2.json      # 同上（同一推文的不同文件共享相同元数据）
```

**注意事项：**
- 每条推文如果有多个媒体文件，会生成多个内容相同的 JSON（每个媒体文件一个），这是 gallery-dl 的 file-level hook 机制决定的
- 如需去重，可以在后处理脚本中按 `tweet_id` 合并或清理
- JSON 文件也会被 archive 数据库追踪，防止重复写入

---

## 2026-06-04 — SQLite 下载归档与持久化去重

**新增功能：** 引入基于 SQLite 的下载归档（Download Archive），实现跨运行的持久化去重。

**变更概要：**

- 在 `gallery/config.json` 中新增 `archive: "./archive.sqlite3"` 配置项，启用 gallery-dl 原生下载归档功能
- 归档以 SQLite 数据库形式持久化存储，记录所有已下载文件的 URL，跨运行生效
- 完善了去重机制的说明，明确定义了四个层级：
  1. **推文级内存去重**（`unique: true`）— 单次运行内，不持久化
  2. **API 游标**（`cursor: true`）— 记录翻页位置，需手动传递恢复
  3. **文件存在性检查**（gallery-dl 内置）— 跨运行，依赖磁盘文件
  4. **Download Archive**（`archive`）— 跨运行，SQLite 持久化

**新增文档：**
- [`gallery/docs/dedup-and-persistence.md`](gallery/docs/dedup-and-persistence.md) — 去重与持久化机制详解

**注意事项：**
- 归档只能减少重复下载，但 **API 爬取仍然是全量的**（gallery-dl 架构限制），每次运行仍会完整遍历 API
- 在 `.gitignore` 中新增了 `**/archive.sqlite3` 排除规则，防止归档数据库被提交到版本控制

---

## 2026-06-03 — 项目目录重组与调试文档

**变更概要：**

- 将批量导出工具目录从 `data/` 重命名为 `gallery/`，语义更清晰
- 新增调试排查文档，记录 `export.py` 从 Mac 迁移到 Linux 时遇到的问题及修复方案

**新增文档：**
- [`gallery/docs/export-py-debug.md`](gallery/docs/export-py-debug.md) — export.py 问题排查与修复记录，涵盖三个典型问题：
  1. `-o directory=...` 参数无效（应使用 `-D` / `--directory`）
  2. `shlex.quote()` 误用导致路径带引号字面字符
  3. `capture_output=True` 在 Linux 下的管道死锁风险

**注意事项：**
- 文档中总结的问题与 Mac/Linux 平台差异无关，均为脚本本身的 Bug，对跨平台使用者有参考价值

---

## 2026-06-02 — 初始文档体系与批量导出工具

**新增功能：** 建立完整的中文文档体系，并实现基于 gallery-dl 的 Twitter/X 批量导出工具。

**变更概要：**

- 实现 `export.py` 批量导出脚本，支持：
  - 通过 `cookies.txt` 进行 Twitter 认证（Netscape 格式）
  - 多用户批量处理，支持启用/禁用单个用户
  - 导出内容包括：推文、回复、引用内容媒体、用户信息、头像
  - 每个用户独立目录，资料与内容分开放置
  - 完整日志记录（文件 + 控制台汇总）
  - 断点续传与去重支持

- 配置文件体系：
  - `gallery/config.json` — gallery-dl 原生配置（认证、下载选项、去重策略）
  - `gallery/users.json` — 用户列表与脚本参数

**新增文档：**

| 文档 | 路径 | 说明 |
|------|------|------|
| 中文 README | [`README.zh.rst`](README.zh.rst) | 项目中文介绍，RST 格式，包含依赖、安装、使用方式 |
| 批量导出说明 | [`gallery/README.md`](gallery/README.md) | 批量导出工具完整使用文档，含需求背景、架构、配置、步骤、常见问题 |
| Twitter 导出指南 | [`docs/twitter-guide.zh.md`](docs/twitter-guide.zh.md) | Twitter/X 内容导出详细指南，含 Cookies 获取、认证配置、常见场景示例 |

**注意事项：**
- Twitter 已不支持用户名密码登录，必须使用 Cookies 认证（`cookies.txt` 或浏览器提取）
- 如果通过 snap 安装 gallery-dl，会遇到 AppArmor 沙箱限制 (`Permission denied: '/data'`)，建议改用 pip 安装
- `gallery/config.json` 中 `quoted: true` 会下载引用推文中的媒体，`text-tweets: true` 会保留纯文本推文

---

## 文档索引

以下为 `develop` 分支新增的全部文档及其路径：

```
README.zh.rst                          # 中文 README
gallery/README.md                      # 批量导出工具说明
gallery/docs/usage-guide.md            # 完整使用指南（参数、场景、FAQ）
gallery/docs/sqlite-storage.md         # SQLite 存储与增量扫描设计
gallery/docs/dedup-and-persistence.md  # 去重与持久化机制
gallery/docs/export-py-debug.md        # export.py 排查记录
docs/twitter-guide.zh.md               # Twitter 导出指南
```
