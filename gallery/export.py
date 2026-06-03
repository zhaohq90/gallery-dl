#!/usr/bin/env python3
"""
批量导出 Twitter/X 用户内容。

依赖 gallery-dl，请确保已安装：
    python -m pip install gallery-dl

用法：
    cd data/
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
    """Find the actual cookies path from gallery-dl config."""
    cookies_cfg = extractor_cfg.get("cookies")
    if isinstance(cookies_cfg, str):
        p = Path(cookies_cfg)
        if not p.is_absolute():
            p = SCRIPT_DIR / p
        return p
    return COOKIES_FILE  # fallback


def check_twitter_auth(cookies_path):
    """Verify cookies.txt contains Twitter/X authentication cookies."""
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
    """Run a gallery-dl command, return (success, stdout)."""
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
        # Read output after process exits (no deadlock risk with files)
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
        # Clean up temp files
        for p in (stdout_path, stderr_path):
            try:
                os.unlink(p)
            except OSError:
                pass


def export_profile(export_root, username):
    """Export user info + avatar + header to profile/ subdirectory."""
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


def export_content(export_root, username, limit):
    """Export tweets with replies to content/ subdirectory."""
    content_dir = export_root / username / "content"
    content_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "gallery-dl",
        "-c", str(CONFIG_FILE),
        "-D", str(content_dir),
        f"https://x.com/{username}/with_replies",
    ]
    ok, output = run_gallery(cmd)
    return ok, output


def setup_logging(log_file):
    """Configure dual logging: file + console."""
    log_path = SCRIPT_DIR / log_file
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # File handler — full detail
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(fh)

    # Console handler — info and above
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(ch)

    return log_path


def main():
    # ---- 加载用户配置 ----
    user_config = load_json(USERS_FILE)
    if user_config is None:
        print("错误: users.json 不存在或格式错误")
        sys.exit(1)

    settings = user_config.get("settings", {})
    limit = settings.get("limit", 10)
    log_file = settings.get("log_file", "export.log")

    # ---- 设置日志 ----
    log_path = setup_logging(log_file)
    logging.info("=" * 60)
    logging.info("Twitter/X 批量导出开始 — %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logging.info("配置文件: %s", USERS_FILE)
    logging.info("日志文件: %s", log_path)

    # ---- 检查前置条件 ----
    # cookies
    gal_config = load_json(CONFIG_FILE)
    if gal_config is None:
        logging.error("gallery-dl 配置文件 %s 不存在或格式错误", CONFIG_FILE)
        sys.exit(1)

    cookies_path = find_cookies(gal_config.get("extractor", {}).get("twitter", {}))
    if not cookies_path.exists():
        logging.error("Cookies 文件不存在: %s", cookies_path)
        logging.error("请将 cookies.txt 放到 %s", SCRIPT_DIR)
        sys.exit(1)
    logging.info("Cookies: %s", cookies_path)

    # 验证 Twitter/X 登录凭据
    auth_ok, auth_msg = check_twitter_auth(cookies_path)
    if auth_ok:
        logging.info("Cookies 验证: ✓ 包含 auth_token / ct0")
    else:
        logging.warning("Cookies 验证: ✗ %s", auth_msg)
        logging.warning("没有有效的登录凭据，with_replies 等接口将无法使用")
        logging.warning("请重新导出 cookies（推荐使用浏览器插件如 'cookies.txt'）")

    # ---- 确定导出根目录 ----
    export_root_raw = settings.get("export_root", ".")
    export_root = Path(export_root_raw)
    if not export_root.is_absolute():
        export_root = SCRIPT_DIR / export_root
    export_root = export_root.resolve()
    logging.info("导出根目录: %s", export_root)

    # ---- 筛选启用的用户 ----
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

    # ---- 逐个导出 ----
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
        }

        try:
            # Step 1: 导出用户信息和头像
            logging.info("  → 导出用户资料...")
            ok, _ = export_profile(export_root, username)
            result["profile"] = ok
            if ok:
                logging.info("  ✓ 资料完成")
            else:
                logging.warning("  ✗ 资料导出失败（继续导出推文）")

            # Step 2: 导出推文和回复
            logging.info("  → 导出推文 (limit=%d)...", limit)
            ok, _ = export_content(export_root, username, limit)
            result["content"] = ok
            if ok:
                logging.info("  ✓ 推文完成")
            else:
                logging.warning("  ✗ 推文导出失败")

        except Exception as exc:
            result["error"] = str(exc)
            logging.error("  ✗ 异常: %s", exc)

        results.append(result)
        if result["error"] or not (result["profile"] or result["content"]):
            fail_count += 1
        else:
            ok_count += 1

    # ---- 汇总 ----
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
            logging.info("  [ OK ] @%s", r["username"])
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
    logging.info("=" * 60)

    return 1 if fail_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
