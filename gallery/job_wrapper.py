#!/usr/bin/env python3
"""
自定义 gallery-dl DownloadJob 包装器。

提供：
  - SQLite 元数据写入（prepare / after / skip 钩子）
  - 增量扫描（连续已知推文达到阈值时中止）
  - 下载开关（纯元数据采集模式）
  - 操作日志统计
"""

import logging
from pathlib import Path

from gallery_dl import job, exception


class CustomJob(job.DownloadJob):
    """扩展 DownloadJob，支持 SQLite 存储和增量扫描。"""

    def __init__(self, url, db, settings, parent=None):
        """
        :param url:      提取器 URL
        :param db:       TweetDB 实例
        :param settings: 配置 dict (store_mode / scan_mode / threshold / download_media / ...)
        """
        super().__init__(url, parent)

        self._db = db
        self._store_mode = settings.get("store_mode", "json")
        self._scan_mode = settings.get("scan_mode", "full")
        self._threshold = settings.get("incremental_threshold", 10)
        self._download_media = settings.get("download_media", True)
        self._max_count = settings.get("max_count", -1)

        # 运行时状态
        self._dup_tweets = set()        # 当前连续已知推文 ID 集合
        self._processed_tweets = set()   # 本次已处理的推文 ID
        self._stop_reason = None         # 中止原因（用于日志区分）
        self._op_log_id: int | None = None
        self._stats = {
            "total_scanned": 0,
            "new_tweets": 0,
            "existing_tweets": 0,
            "images_downloaded": 0,
            "videos_downloaded": 0,
        }

        self.log = logging.getLogger("export")

    # ── lifecycle ──────────────────────────────────────────

    def _init(self):
        """在 DownloadJob._init() 之后注册钩子。"""
        super()._init()

        # 只有 sql 模式才注册钩子
        if self._store_mode != "sql":
            return

        # prepare: 增量检查 + 写 user + 写 tweet
        self.hooks.setdefault("prepare", []).append(self._on_prepare)

        # after: 写 media（文件下载成功后）
        self.hooks.setdefault("after", []).append(self._on_after)

        # skip: 写 media（文件被跳过时，如已在 archive 中）
        self.hooks.setdefault("skip", []).append(self._on_skip)

    # ── hooks ──────────────────────────────────────────────

    def _on_prepare(self, pathfmt):
        """prepare 钩子：最大数量检查 + 增量检查 + 写入 user 和 tweet。"""
        kwdict = pathfmt.kwdict
        tweet_id = kwdict.get("tweet_id")
        if not tweet_id:
            return

        # ---- 已处理过的推文跳过（同一推文的后续媒体文件）----
        if tweet_id in self._processed_tweets:
            return

        # ---- 最大数量检查（优先于增量检查）----
        if self._max_count > 0 and self._stats["total_scanned"] >= self._max_count:
            self._stop_reason = f"max_count: 已达到单用户上限 {self._max_count} 条"
            self.log.info(self._stop_reason)
            raise exception.StopExtraction()

        # ---- 增量扫描检查 ----
        if self._scan_mode == "incremental" and self._threshold > 0:
            if self._db.tweet_exists(tweet_id):
                self._dup_tweets.add(tweet_id)
                if len(self._dup_tweets) >= self._threshold:
                    self._stop_reason = (f"incremental: 连续 {len(self._dup_tweets)} "
                                         f"条已知推文，中止扫描")
                    self.log.info(self._stop_reason)
                    raise exception.StopExtraction()
            else:
                self._dup_tweets.clear()

        # ---- 写入 user（幂等 upsert）----
        author = kwdict.get("author") or kwdict.get("user")
        if author and author.get("id"):
            self._db.insert_user(author)

        # ---- 写入 tweet ----
        self._processed_tweets.add(tweet_id)
        self._stats["total_scanned"] += 1

        if self._db.insert_tweet(kwdict):
            self._stats["new_tweets"] += 1
        else:
            self._stats["existing_tweets"] += 1

    def _on_after(self, pathfmt):
        """after 钩子：写入 media 记录（文件成功下载后）。"""
        kwdict = pathfmt.kwdict
        tweet_id = kwdict.get("tweet_id")
        if not tweet_id:
            return

        # 记录媒体
        filepath = getattr(pathfmt, "path", "")
        if filepath:
            relpath = _relative_path(filepath)
        else:
            relpath = ""

        self._db.insert_media(kwdict, relpath)

        # 更新统计
        ext = (kwdict.get("extension") or "").lower()
        if ext in ("mp4", "mov", "webm", "mkv", "gif"):
            self._stats["videos_downloaded"] += 1
        else:
            self._stats["images_downloaded"] += 1

    def _on_skip(self, pathfmt):
        """skip 钩子：文件跳过时也写入 media 记录。"""
        if self._download_media:
            return  # 正常下载模式下，skip 说明文件已在 archive 中，不重复记录

        kwdict = pathfmt.kwdict
        tweet_id = kwdict.get("tweet_id")
        if not tweet_id:
            return

        filepath = getattr(pathfmt, "path", "")
        relpath = _relative_path(filepath) if filepath else ""
        self._db.insert_media(kwdict, relpath)

    # ── download toggle ────────────────────────────────────

    def handle_url(self, url, kwdict):
        """覆盖父类方法，支持 download_media=false。"""
        if not self._download_media:
            # 纯元数据模式：运行 prepare 钩子，跳过实际下载
            self.pathfmt.set_filename(kwdict)
            if "prepare" in self.hooks:
                for cb in self.hooks["prepare"]:
                    cb(self.pathfmt)
            # 跳过下载 → 触发 skip 钩子
            self.pathfmt.temppath = ""
            self.handle_skip()
            return

        super().handle_url(url, kwdict)

    # ── operation log ──────────────────────────────────────

    def start_log(self, user_id: int, username: str):
        """开始操作日志记录。"""
        self._op_log_id = self._db.log_start(user_id, username, self._scan_mode)

    def finish_log(self, status: str = "success"):
        """结束操作日志，写入统计数据。"""
        if self._op_log_id:
            self._db.log_update(self._op_log_id, **self._stats)
            self._db.log_end(self._op_log_id, status)

    def get_stats(self) -> dict:
        """返回当前统计信息。"""
        return dict(self._stats)


def _relative_path(absolute_path: str) -> str:
    """将绝对路径转为相对于当前工作目录的路径。"""
    try:
        return str(Path(absolute_path).relative_to(Path.cwd()))
    except ValueError:
        return absolute_path
