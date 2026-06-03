# 去重与持久化机制

本文档梳理 export.py 及其底层 gallery-dl 引擎的**去重（dedup）与持久化（persistence）机制**，说明每次运行时哪些步骤会被跳过、哪些仍需完整执行，以及各配置项的作用范围。

---

## 总览

export.py 的去重依赖 **四个层次**，从内到外依次是：

| 层级 | 机制 | 配置项 | 作用范围 | 持久化 |
|------|------|--------|----------|--------|
| 1 | 推文级内存去重 | `unique: true` | 单次运行内 | 否 |
| 2 | API 游标 | `cursor: true` | 单次运行（退出时打印） | 否（需手动传递） |
| 3 | 文件存在性检查 | gallery-dl 内置 | 跨运行 | 是（依赖磁盘文件） |
| 4 | Download Archive | `archive: "./archive.sqlite3"` | 跨运行 | 是（SQLite 数据库） |

---

## 各层详解

### 1. 推文级内存去重 — `unique: true`

**配置文件**: `config.json` → `extractor.twitter.unique`

**工作原理**:
```python
# twitter.py 第 90 行
seen_tweets = set() if self.config("unique", True) else None
```

在单次 gallery-dl 运行中维护一个 Python `set`，记录已处理的 tweet ID。当 API 翻页返回重复推文时，跳过已处理过的条目。

**作用边界**:
- ✅ 防止同一次运行内重复处理（翻页中 API 返回重复数据）
- ❌ 进程退出后 set 消失，下次运行重新开始
- ❌ 不持久化，不跨运行

**影响**: 对增量导出的贡献很小，主要处理 API 分页中的数据重复问题。

---

### 2. API 游标 — `cursor: true`

**配置文件**: `config.json` → `extractor.twitter.cursor`

**工作原理**:
gallery-dl 在 Twitter API 分页请求中使用游标（cursor）来追踪当前翻页位置。当启用 `cursor: true` 时：
- 每次翻页记录当前游标值
- 进程退出时打印游标到日志：
  ```
  Use '-o cursor=...' to continue downloading from the current position
  ```

**作用边界**:
- ✅ 记录翻页位置，可手动传入恢复
- ❌ **export.py 没有传递 cursor 参数**，下次运行不会自动恢复
- ❌ 不持久化，依赖用户手动记录

**影响**: 当前配置下 cursor **实际不生效**。export.py 的 `run_gallery()` 函数只传了 `-c` 和 `-D` 参数，没有传 `-o cursor=<value>`。

---

### 3. 文件存在性检查 — gallery-dl 内置行为

**配置**: 无需配置，gallery-dl 默认行为

**工作原理**:
在 `job.py` 第 439 行：
```python
if pathfmt.exists():
    self.handle_skip()
    return
```

gallery-dl 在下载每个媒体文件前，会检查目标文件是否已存在于磁盘上。如果存在，跳过下载。

**作用边界**:
- ✅ 跨运行生效（依赖磁盘文件）
- ✅ 避免重复下载已存在的媒体文件
- ❌ **仍然需要完整调用 Twitter API 爬取所有推文**（跳过的是下载，不是爬取）
- ❌ 基于文件路径判断，如果删除文件则失去记录
- ❌ 不记录"这个推文已经处理过了"，仍然遍历每条推文

**性能影响**:
- 首次导出：API 爬取 + 文件下载 = 慢
- 后续导出：API 爬取（完整） + 文件下载（跳过已有）= **API 爬取部分一样慢**
- Twitter API 限速严格，爬取本身是最大瓶颈

---

### 4. Download Archive — `archive: "./archive.sqlite3"` ⭐ 新增

**配置文件**: `config.json` → `archive`

**工作原理**:
gallery-dl 会创建一个 SQLite 数据库文件 `archive.sqlite3`，记录所有成功下载的条目。内部表结构：

```sql
CREATE TABLE IF NOT EXISTS archive (entry TEXT PRIMARY KEY) WITHOUT ROWID
```

每条记录的唯一键（entry）格式为：
```
{prefix}{archive_fmt}
```

对于 Twitter 提取器：
- `prefix` = `"twitter"`（提取器的 category）
- `archive_fmt` = `"{tweet_id}_{retweet_id}_{num}"`（来自 twitter.py 第 26 行）
- 最终键示例：`twitter1234567890_0_0`

**检查时机**（`job.py` 第 431 行）：
```python
if archive is not None and archive.check(kwdict):
    pathfmt.fix_extension()
    self.handle_skip()
    return
```

当 gallery-dl 准备下载某个文件时，先查 archive：
- **在 archive 中** → 直接跳过，不下载也不检查磁盘
- **不在 archive 中** → 检查文件是否存在 → 不存在则下载 → 成功后写入 archive

**写入时机**：下载成功后自动写入 archive，下一次运行时即可识别跳过。

**作用边界**:
- ✅ 跨运行持久化（SQLite 数据库文件）
- ✅ 更快的跳过判断（单次 SQL 查询 vs 文件系统 stat）
- ✅ 不受媒体文件被删除影响（archive 独立记录）
- ✅ 可记录精确的下载历史
- ❌ **仍然需要完整调用 Twitter API 爬取所有推文**（archive 在 Downloader 层面工作，不在 Extractor 层面）

---

## 性能模型

### 首次导出（无 archive 数据库）
```
Twitter API 爬取 → 每条推文 → 生成文件路径 → 检查 archive（无记录）→ 下载文件 → 写入 archive
```
- API 爬取：全量
- 文件下载：全量
- archive 写入：全量写入

### 后续导出（已有 archive 数据库）
```
Twitter API 爬取 → 每条推文 → 生成文件路径 → 检查 archive（有记录）→ 跳过
```
- **API 爬取：全量**（瓶颈未消除）
- 文件下载：跳过（已有 archive 记录）
- archive 写入：无（均为已存在条目）

### 为什么 API 爬取仍然是全量？

gallery-dl 的 archive 机制工作在 **Downloader** 层面（`DownloadJob.handle_url`），而非 **Extractor** 层面。Extractor 仍然会遍历所有推文、为每条推文生成 kwdict，然后在 Downloader 中逐一比对 archive 并跳过。这是 gallery-dl 的架构限制。

Twitter 提取器内部的 `unique: true` 已经可以跳过翻页中的重复推文，但它也无法判断"这条推文上次已经处理过了"，因为那条信息在 archive 里，而 Extractor 看不到 archive。

---

## 配置项速查

| 配置项 | 位置 | 默认值 | 说明 |
|--------|------|--------|------|
| `unique` | `extractor.twitter.unique` | `true` | 单次运行内推文去重（内存 set） |
| `cursor` | `extractor.twitter.cursor` | `true` | 翻页游标记录（需手动恢复） |
| `limit` | `extractor.twitter.limit` | `10` | 每次 API 请求的分页大小 |
| `archive` | 顶层 `archive` | `"./archive.sqlite3"` | SQLite 下载归档数据库路径 |

### archive 相关可选配置

如果需要更细粒度的控制，gallery-dl 还支持以下配置项（当前未使用，按需添加）：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `archive-format` | 覆盖 archive 键的格式字符串 | 提取器的 `archive_fmt` |
| `archive-prefix` | archive 键的前缀 | 提取器的 `category` |
| `archive-table` | SQLite 表名 | `"archive"` |
| `archive-mode` | `"memory"` 表示内存缓存 | 直接写 SQLite |
| `archive-pragma` | SQLite PRAGMA 语句列表 | 无 |
| `archive-event` | 写入 archive 的时机（默认下载成功时） | 下载成功 |

---

## 实际使用建议

### 日常增量导出
```bash
cd gallery/
python export.py
```
- 首次运行：全量下载 + 建立 archive 数据库
- 后续运行：API 爬取（全量）+ 跳过已归档条目
- **注意**: 虽然 API 爬取仍是全量的，但 archive 确保了：
  - 不会重复下载已有文件
  - 即使删除媒体文件也不会重新下载
  - archive 数据库是精确的下载记录

### 查看 archive 状态
```bash
# 查看已归档条目数量
sqlite3 archive.sqlite3 "SELECT COUNT(*) FROM archive"
```

### 重置 archive（重新全量下载）
```bash
rm archive.sqlite3
```

### archive 文件路径
`archive.sqlite3` 使用相对路径 `"./"`，由于 `export.py` 执行 subprocess 时设置了 `cwd=SCRIPT_DIR`（即 `gallery/` 目录），因此 archive 文件会生成在 `gallery/archive.sqlite3`。

---

## 已知限制

1. **API 爬取仍是全量**：archive 无法减少 Twitter API 调用，只是让文件下载步骤变成快速跳过。
2. **cursor 未自动恢复**：`export.py` 没有实现 cursor 的持久化和自动恢复机制，中断后无法从断点继续。
3. **共用一个 archive**：所有用户共享同一个 `archive.sqlite3`，每条记录的键已通过 `{tweet_id}` 天然区分不同用户，不会冲突。
