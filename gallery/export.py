#!/usr/bin/env python3
"""
批量导出 Twitter/X 用户内容。

支持两种元数据存储模式：
  - json : 每个媒体文件生成同名 .json 元数据文件（gallery-dl metadata 后处理器）
  - sql  : 写入 SQLite 数据库（推文 + 用户 + 媒体 + 操作日志）

支持两种扫描模式：
  - full         : 全量扫描所有推文
  - incremental  : 增量扫描，遇到连续 N 条已知推文时中止

依赖 gallery-dl，请确保已安装：
    python -m pip install gallery-dl

用法：
    cd gallery/
    python export.py
"""

import json
import os
import sys
import subprocess
import logging
from pathlib import Path
from datetime import datetime


SCRIPT_DIR = Path(__file__).parent.resolve()
USERS_FILE = SCRIPT_DIR / "users.json"
CONFIG_FILE = SCRIPT_DIR / "config.json"
COOKIES_FILE = SCRIPT_DIR / "cookies.txt"


# ── helpers ────────────────────────────────────────────────

def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        logging.error("JSON 解析失败: %s — %s", path, e)
        return None


def find_cookies(extractor_cfg):
    cookies_cfg = extractor_cfg.get("cookies")
    if isinstance(cookies_cfg, str):
        p = Path(cookies_cfg)
        if not p.is_absolute():
            p = SCRIPT_DIR / p
        return p
    return COOKIES_FILE


def check_twitter_auth(cookies_path):
    required = {"auth_token", "ct0"}
    found = set()
    try:
        with open(cookies_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 7:
                    domain = parts[0]
                    name = parts[5]
                    if domain in ("twitter.com", "x.com", ".twitter.com", ".x.com"):
                        found.add(name)
    except Exception:
        return False, "无法读取 cookies 文件"
    missing = required - found
    if missing:
        return False, f"缺少必需 cookies: {', '.join(sorted(missing))}"
    return True, "OK"


def run_gallery(cmd, timeout=600):
    """Run a gallery-dl CLI command (用于导出用户资料等简单操作)."""
    import tempfile
    logging.debug("  CMD: %s", " ".join(str(x) for x in cmd))
    stdout_fd, stdout_path = tempfile.mkstemp(prefix="gallery_stdout_", suffix=".log")
    stderr_fd, stderr_path = tempfile.mkstemp(prefix="gallery_stderr_", suffix=".log")
    try:
        with open(stdout_fd, "w", encoding="utf-8") as stdout_f, \
             open(stderr_fd, "w", encoding="utf-8") as stderr_f:
            proc = subprocess.run(
                cmd,
                stdout=stdout_f,
                stderr=stderr_f,
                timeout=timeout,
                cwd=SCRIPT_DIR,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
        stdout_text = Path(stdout_path).read_text(encoding="utf-8", errors="replace")
        stderr_text = Path(stderr_path).read_text(encoding="utf-8", errors="replace")
        if stdout_text.strip():
            logging.debug("  STDOUT:\n%s", stdout_text.strip())
        if stderr_text.strip():
            logging.debug("  STDERR:\n%s", stderr_text.strip())
        return proc.returncode == 0, stdout_text + stderr_text
    except subprocess.TimeoutExpired:
        logging.error("  gallery-dl 超时 (%ds)", timeout)
        return False, "timeout"
    except FileNotFoundError:
        logging.error("  gallery-dl 未找到，请先安装: pip install gallery-dl")
        return False, "gallery-dl not found"
    finally:
        for p in (stdout_path, stderr_path):
            try:
                os.unlink(p)
            except OSError:
                pass


# ── export functions ───────────────────────────────────────

def export_profile(export_root, username):
    """Export user info + avatar + header → profile/ (使用 CLI)."""
    profile_dir = export_root / username / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "gallery-dl",
        "-c", str(CONFIG_FILE),
        "-D", str(profile_dir),
        f"https://x.com/{username}/info",
        f"https://x.com/{username}/photo",
        f"https://x.com/{username}/header_photo",
    ]
    ok, output = run_gallery(cmd)
    return ok, output


def export_content_python(username, export_root, gal_config, global_settings):
    """
    使用 gallery-dl Python API 导出推文（支持 SQLite 存储 + 增量扫描）。

    :returns: (ok: bool, stats: dict, error: str|None)
    """
    store_mode = global_settings.get("store_mode", "json")
    download_media = global_settings.get("download_media", True)
    threshold = global_settings.get("incremental_threshold", -1)
    max_count = global_settings.get("max_count", -1)
    store_db_path = global_settings.get("store_db", "./twitter.db")

    content_dir = export_root / username / "content"
    content_dir.mkdir(parents=True, exist_ok=True)

    stats = {"total_scanned": 0, "new_tweets": 0, "existing_tweets": 0,
             "images_downloaded": 0, "videos_downloaded": 0}

    # ── 初始化 gallery-dl config ──
    from gallery_dl import config, extractor, exception as gd_exc

    # 加载配置文件（覆盖默认值）
    config.load([str(CONFIG_FILE)], strict=False)

    # 设置输出目录（模拟 CLI -D 参数）
    config.set((), "base-directory", str(content_dir))
    config.set((), "directory", ())

    # ── JSON 模式：注册 metadata 后处理器 ──
    if store_mode == "json":
        if "postprocessors" not in gal_config or not any(
                p.get("name") == "metadata" for p in gal_config.get("postprocessors", ())):
            # 动态添加 metadata postprocessor
            pp_list = list(gal_config.get("postprocessors", ()))
            pp_list.append({
                "name": "metadata",
                "mode": "json",
                "directory": ["{_directory}"],
                "extension": "json",
                "event": "file",
                "skip": True,
            })
            gal_config["postprocessors"] = pp_list
            config.set((), "postprocessors", pp_list)

    # ── 设置 skip 安全网（tweet 级中止由 prepare hook 控制）──
    if threshold > 0 or max_count > 0:
        # 文件级 skip 上限设为 tweet 级阈值的 5 倍（一个推文可能有多张图）
        config.set((), "skip", f"abort:{max(threshold, max_count, 10) * 5}")

    # ── SQL 模式：初始化数据库 ──
    db = None
    if store_mode == "sql":
        from db import TweetDB
        db_path = SCRIPT_DIR / store_db_path
        db = TweetDB(str(db_path.resolve()))

    # ── 创建 Job ──
    from job_wrapper import CustomJob

    url = f"https://x.com/{username}/with_replies"
    job = CustomJob(url, db, {
        "store_mode": store_mode,
        "incremental_threshold": threshold,
        "download_media": download_media,
        "max_count": max_count,
    })

    # 获取用户 ID（用于操作日志）
    user_id = None
    try:
        # 从 extractor 获取用户信息
        extr = extractor.find(url)
        if extr:
            extr.initialize()
            user_obj = None
            try:
                user_obj = extr.api.user_by_screen_name(username)
            except Exception:
                pass
            if user_obj:
                user_id = int(user_obj.get("rest_id") or user_obj.get("id_str", 0))
    except Exception:
        pass

    job.start_log(user_id or 0, username)

    # ── 运行 Job ──
    ok = True
    error_msg = None
    try:
        status = job.run()
        if status:
            ok = False
            error_msg = f"gallery-dl exit status: {status}"
    except gd_exc.StopExtraction:
        reason = getattr(job, "_stop_reason", None) or "连续已知推文达标"
        logging.info("  → %s", reason)
    except gd_exc.AbortExtraction as e:
        ok = False
        error_msg = str(e.message) if hasattr(e, "message") else str(e)
    except gd_exc.GalleryDLException as e:
        ok = False
        error_msg = f"{e.__class__.__name__}: {e}"
    except Exception as e:
        ok = False
        error_msg = str(e)
    finally:
        # 更新统计
        stats = job.get_stats()
        job.finish_log("success" if ok else "failed")
        if db:
            db.close()

    return ok, stats, error_msg


# ── logging ────────────────────────────────────────────────

def setup_logging(log_file):
    log_path = SCRIPT_DIR / log_file
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # File
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(fh)

    # Console
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(ch)

    return log_path


# ── main ───────────────────────────────────────────────────

def main():
    user_config = load_json(USERS_FILE)
    if user_config is None:
        print("错误: users.json 不存在或格式错误")
        sys.exit(1)

    settings = user_config.get("settings", {})
    limit = settings.get("limit", 10)
    log_file = settings.get("log_file", "export.log")

    log_path = setup_logging(log_file)
    logging.info("=" * 60)
    logging.info("Twitter/X 批量导出开始 — %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logging.info("配置文件: %s", USERS_FILE)
    logging.info("日志文件: %s", log_path)

    gal_config = load_json(CONFIG_FILE)
    if gal_config is None:
        logging.error("gallery-dl 配置文件 %s 不存在或格式错误", CONFIG_FILE)
        sys.exit(1)

    # ── 全局设置 ──
    global_settings = {
        "store_mode":            gal_config.get("store_mode", "json"),
        "incremental_threshold": gal_config.get("incremental_threshold", -1),
        "download_media":        gal_config.get("download_media", True),
        "store_db":              gal_config.get("store_db", "./twitter.db"),
        "max_count":             gal_config.get("max_count", -1),
    }

    logging.info("存储模式: %s", global_settings["store_mode"])
    logging.info("下载媒体: %s", "是" if global_settings["download_media"] else "否")
    if global_settings["max_count"] > 0:
        logging.info("单用户上限: %d 条推文", global_settings["max_count"])
    else:
        logging.info("单用户上限: 不限制")
    if global_settings["incremental_threshold"] > 0:
        logging.info("增量阈值: %d 条连续已知推文", global_settings["incremental_threshold"])
    else:
        logging.info("增量阈值: 不限制（全量扫描）")
    if global_settings["store_mode"] == "sql":
        logging.info("数据库:   %s", global_settings["store_db"])

    # cookies
    cookies_path = find_cookies(gal_config.get("extractor", {}).get("twitter", {}))
    if not cookies_path.exists():
        logging.error("Cookies 文件不存在: %s", cookies_path)
        logging.error("请将 cookies.txt 放到 %s", SCRIPT_DIR)
        sys.exit(1)
    logging.info("Cookies: %s", cookies_path)

    auth_ok, auth_msg = check_twitter_auth(cookies_path)
    if auth_ok:
        logging.info("Cookies 验证: ✓ 包含 auth_token / ct0")
    else:
        logging.warning("Cookies 验证: ✗ %s", auth_msg)
        logging.warning("没有有效的登录凭据，with_replies 等接口将无法使用")

    # 导出根目录
    export_root_raw = settings.get("export_root", ".")
    export_root = Path(export_root_raw)
    if not export_root.is_absolute():
        export_root = SCRIPT_DIR / export_root
    export_root = export_root.resolve()
    logging.info("导出根目录: %s", export_root)

    # 用户列表
    all_users = user_config.get("users", [])
    if not all_users:
        logging.warning("users.json 中没有配置任何用户")
        sys.exit(0)

    enabled = [u for u in all_users if u.get("enabled", True)]
    disabled = len(all_users) - len(enabled)
    logging.info("用户总数: %d (启用: %d, 禁用: %d)", len(all_users), len(enabled), disabled)

    if not enabled:
        logging.warning("没有启用的用户，退出")
        sys.exit(0)

    # ── 逐个导出 ──
    results = []
    total = len(enabled)
    ok_count = 0
    fail_count = 0

    for i, user in enumerate(enabled, 1):
        username = user["username"].strip().lstrip("@")
        display = user.get("display_name", username)

        logging.info("")
        logging.info("[%d/%d] %s (@%s)", i, total, display, username)

        result = {
            "username": username,
            "display": display,
            "profile": False,
            "content": False,
            "error": None,
            "stats": None,
        }

        try:
            # Step 1: 导出用户信息（使用 CLI）
            if global_settings["download_media"]:
                logging.info("  → 导出用户资料...")
                ok, _ = export_profile(export_root, username)
                result["profile"] = ok
                if ok:
                    logging.info("  ✓ 资料完成")
                else:
                    logging.warning("  ✗ 资料导出失败（继续导出推文）")
            else:
                logging.info("  → 跳过用户资料（download_media=false）")

            # Step 2: 导出推文（使用 Python API）
            logging.info("  → 导出推文 (limit=%d)...", limit)
            ok, stats, error = export_content_python(
                username, export_root, gal_config, global_settings)
            result["content"] = ok
            result["stats"] = stats
            if ok:
                if stats:
                    logging.info("  ✓ 推文完成 — 扫描 %d, 新增 %d, 已有 %d, 图片 %d, 视频 %d",
                                 stats.get("total_scanned", 0),
                                 stats.get("new_tweets", 0),
                                 stats.get("existing_tweets", 0),
                                 stats.get("images_downloaded", 0),
                                 stats.get("videos_downloaded", 0))
                else:
                    logging.info("  ✓ 推文完成")
            else:
                result["error"] = error
                logging.warning("  ✗ 推文导出失败: %s", error)

        except Exception as exc:
            result["error"] = str(exc)
            logging.error("  ✗ 异常: %s", exc)

        results.append(result)
        if result["error"] or not (result["profile"] or result["content"]):
            fail_count += 1
        else:
            ok_count += 1

    # ── 汇总 ──
    logging.info("")
    logging.info("=" * 60)
    logging.info("导出完成: 共 %d 个用户", total)
    logging.info("  成功: %d", ok_count)
    logging.info("  失败: %d", fail_count)
    logging.info("")

    for r in results:
        if r["error"]:
            logging.info("  [FAIL] @%s — %s", r["username"], r["error"])
        elif r["profile"] and r["content"]:
            s = r.get("stats") or {}
            parts = ["  [ OK ] @%s" % r["username"]]
            if s:
                parts.append("扫描%d" % s.get("total_scanned", 0))
                parts.append("新增%d" % s.get("new_tweets", 0))
                if s.get("existing_tweets"):
                    parts.append("已有%d" % s.get("existing_tweets", 0))
                if s.get("images_downloaded"):
                    parts.append("图片%d" % s.get("images_downloaded", 0))
                if s.get("videos_downloaded"):
                    parts.append("视频%d" % s.get("videos_downloaded", 0))
            logging.info(" ".join(parts))
        else:
            parts = []
            if r["profile"]:
                parts.append("资料✓")
            if r["content"]:
                parts.append("推文✓")
            logging.info("  [PART] @%s (%s)", r["username"], ", ".join(parts) if parts else "无")

    logging.info("")
    logging.info("数据目录: %s", export_root)
    logging.info("日志文件: %s", log_path)
    if global_settings["store_mode"] == "sql":
        db_path = SCRIPT_DIR / global_settings["store_db"]
        logging.info("SQLite DB: %s", db_path.resolve())
    logging.info("=" * 60)

    return 1 if fail_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
