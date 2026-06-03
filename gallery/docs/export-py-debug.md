# export.py 问题排查与修复记录

日期: 2026-06-02

## 问题现象

在 Linux 服务器上执行 `export.py`，脚本运行后：
- 看起来卡住不动
- 数据没有导出到预期的目录

脚本在原 Mac 环境下编写，迁移到 Linux 后出现问题。

## 根因分析

三个问题，均与 Mac→Linux 平台差异**无关**，是脚本本身的 bug：

---

### 问题 1: `-o directory=...` 参数不生效（核心问题）

**原因**: gallery-dl 设置输出目录的正确 CLI 参数是 `-D`（或 `--directory`），
而非 `-o directory=PATH`。`-o` 是设置配置项用的，`directory` 键在 `-o` 上下文下
语义不同，被 gallery-dl 静默忽略后回退到默认目录 `./gallery-dl/`。

**证据**: 日志中实际文件路径为
```
./gallery-dl/_/r/o/o/t/_/p/r/o/j/e/c/t/s/_/g/a/l/l/e/r/y/-/d/l/_/d/a/t/a/_/b/l/a/c/k/a/n/g/e/r/_/p/r/o/f/i/l/e/avatar.jpg
```
这是 gallery-dl 的默认路径展开，说明 `-o directory=` 未生效。

**修复**: 
```python
# 改前（无效）
"-o", f"directory={profile_dir}"

# 改后（正确）
"-D", str(profile_dir)
```

验证命令:
```bash
gallery-dl -D "/your/path" "https://x.com/user/photo"
```

---

### 问题 2: `shlex.quote()` 误用

**原因**: `shlex.quote()` 是给 shell 命令行字符串用的（把路径包上引号防空格注入），
但 `subprocess.run(cmd, ...)` 使用列表模式不经过 shell，引号变成了参数的**字面字符**。
gallery-dl 收到的是 `directory='/path/here'`（带引号），无法正确解析。

**修复**: 移除所有 `shlex.quote()` 调用，并删除顶部 `import shlex`。

---

### 问题 3: `capture_output=True` 管道死锁风险

**原因**: `subprocess.run(capture_output=True)` 内部使用 OS 管道接收子进程输出。
当 gallery-dl 输出量超过管道缓冲区上限（Linux 默认 64KB）时，子进程写操作阻塞，
而父进程 `subprocess.run` 要等子进程结束后才读取，形成死锁。
macOS 默认管道缓冲区较大，可能刚好不触发。

**修复**: 改用临时文件接收 stdout/stderr，进程结束后再读取：
```python
stdout_fd, stdout_path = tempfile.mkstemp()
with open(stdout_fd, "w") as f:
    proc = subprocess.run(cmd, stdout=f, stderr=f, ...)
output = Path(stdout_path).read_text()
os.unlink(stdout_path)
```

---

## 其他改进

- 新增 `check_twitter_auth()` 函数，启动时检查 cookies.txt 是否包含必需的
  `auth_token` 和 `ct0` cookie，缺失时给出明确警告。
- 导出日志中不再出现 `shlex.quote` 引起的多余引号。

## 清理旧数据

之前误导出到默认目录的文件可以删除：
```bash
rm -rf /root/projects/gallery-dl/data/gallery-dl/
```

## 文件变更清单

| 文件 | 变更 |
|------|------|
| `export.py` 第 84 行 | `shlex.quote()` 移除 |
| `export.py` 第 101 行 | `shlex.quote()` 移除 |
| `export.py` 第 107 行 | `-o directory=` → `-D` |
| `export.py` 第 124 行 | `-o directory=` → `-D` |
| `export.py` 第 137 行 | 删除无效的 `-o limit=...` |
| `export.py` 第 50-71 行 | 新增 `check_twitter_auth()` |
| `export.py` 第 74-110 行 | `capture_output` → 临时文件模式 |
| `export.py` 第 18 行 | 删除 `import shlex` |
| `config.json` | 新增 `"limit": 10` 到 `extractor.twitter` 下 |


---

### 问题 4: `-o limit=10` 无效，实际导出数量远超限制

**原因**: 两个层面都错了。

1. **键名错误**：`-o limit=10` 设置的是顶层键 `limit`，Twitter 提取器不认。
   正确的配置路径是 `extractor.twitter.limit`，必须写到 `config.json` 里
   （或用 `-o extractor.twitter.limit=10`）。

2. **语义误解**：即使键名正确，`extractor.twitter.limit` 控制的是**每次 API 请求
   返回的分页大小**（默认 50），而不是"总共只下载 N 条推文"。
   gallery-dl 会用游标分页翻到底，不会在 N 条后自动停止。

   gallery-dl 没有"总共限制 N 条"的内置选项。

**修复**: 将 `"limit": 10` 写入 `config.json` 的 `extractor.twitter` 下，
控制每次请求条数。如果确实需要总数限制，需额外手段（如监控输出文件数并手动停止）。

| 之前（无效） | 之后（有效） |
|---|---|
| `export.py`: `-o limit=10` | `export.py`: 删除该参数 |
| `config.json`: 无 limit | `config.json`: `"limit": 10`（分页大小） |

> **注意**: `users.json` 中的 `settings.limit` 字段现在不影响导出数量。
> 要改限制数量，直接修改 `config.json` 中的 `extractor.twitter.limit` 值。
