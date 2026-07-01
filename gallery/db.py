#!/usr/bin/env python3
"""
SQLite 数据库管理器 — 推文/用户/媒体元数据持久化存储。

表结构:
  users          — Twitter 用户信息
  tweets         — 推文内容 + 互动数据 + 引用关系
  media          — 媒体文件记录
  operation_log  — 每次运行的操作日志
"""

import sqlite3
import json
import threading
from datetime import datetime
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY,
    screen_name     TEXT    NOT NULL,
    name            TEXT,
    verified        INTEGER DEFAULT 0,
    protected       INTEGER DEFAULT 0,
    followers_count INTEGER,
    friends_count   INTEGER,
    statuses_count  INTEGER,
    media_count     INTEGER,
    favourites_count INTEGER,
    listed_count    INTEGER,
    description     TEXT,
    location        TEXT,
    profile_image   TEXT,
    profile_banner  TEXT,
    url             TEXT,
    created_at      TEXT,
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tweets (
    id              INTEGER PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    content         TEXT,
    tweet_type      TEXT    NOT NULL DEFAULT 'tweet',
    lang            TEXT,
    source          TEXT,
    sensitive       INTEGER DEFAULT 0,
    created_at      TEXT,
    favorite_count  INTEGER DEFAULT 0,
    quote_count     INTEGER DEFAULT 0,
    reply_count     INTEGER DEFAULT 0,
    retweet_count   INTEGER DEFAULT 0,
    bookmark_count  INTEGER DEFAULT 0,
    view_count      INTEGER DEFAULT 0,
    original_tweet_id   INTEGER REFERENCES tweets(id),
    original_user_id    INTEGER REFERENCES users(id),
    original_user_name  TEXT,
    reply_to_user_id    INTEGER REFERENCES users(id),
    reply_to_user_name  TEXT,
    conversation_id     INTEGER,
    birdwatch       TEXT,
    hashtags        TEXT,
    mentions        TEXT,
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS media (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id    INTEGER NOT NULL REFERENCES tweets(id),
    num         INTEGER,
    url         TEXT,
    extension   TEXT,
    filename    TEXT,
    filepath    TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS operation_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER REFERENCES users(id),
    username            TEXT    NOT NULL,
    start_time          TEXT    NOT NULL,
    end_time            TEXT,
    scan_mode           TEXT,
    total_scanned       INTEGER DEFAULT 0,
    new_tweets          INTEGER DEFAULT 0,
    existing_tweets     INTEGER DEFAULT 0,
    images_downloaded   INTEGER DEFAULT 0,
    videos_downloaded   INTEGER DEFAULT 0,
    status              TEXT    DEFAULT 'running'
);

CREATE INDEX IF NOT EXISTS idx_tweets_user_id ON tweets(user_id);
CREATE INDEX IF NOT EXISTS idx_tweets_created ON tweets(created_at);
CREATE INDEX IF NOT EXISTS idx_tweets_original ON tweets(original_tweet_id);
CREATE INDEX IF NOT EXISTS idx_media_tweet_id ON media(tweet_id);
CREATE INDEX IF NOT EXISTS idx_operation_log_user ON operation_log(user_id);
"""


class TweetDB:
    """SQLite 数据库管理器（线程安全）。"""

    def __init__(self, db_path: str):
        self._db_path = Path(db_path)
        self._local = threading.local()
        self._init_db()

    # ── connection management ──────────────────────────────

    @property
    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self._db_path))
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn

    def _init_db(self):
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._conn
        conn.executescript(SCHEMA)
        conn.commit()

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ── user ───────────────────────────────────────────────

    def insert_user(self, user: dict) -> bool:
        """Insert or update a user record. Returns True if new."""
        if not user or not user.get("id"):
            return False

        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sql = """
            INSERT INTO users (
                id, screen_name, name, verified, protected,
                followers_count, friends_count, statuses_count,
                media_count, favourites_count, listed_count,
                description, location, profile_image, profile_banner,
                url, created_at, updated_at
            ) VALUES (
                :id, :screen_name, :name, :verified, :protected,
                :followers_count, :friends_count, :statuses_count,
                :media_count, :favourites_count, :listed_count,
                :description, :location, :profile_image, :profile_banner,
                :url, :created_at, :updated_at
            )
            ON CONFLICT(id) DO UPDATE SET
                screen_name=excluded.screen_name,
                name=excluded.name,
                verified=excluded.verified,
                protected=excluded.protected,
                followers_count=excluded.followers_count,
                friends_count=excluded.friends_count,
                statuses_count=excluded.statuses_count,
                media_count=excluded.media_count,
                favourites_count=excluded.favourites_count,
                listed_count=excluded.listed_count,
                description=excluded.description,
                location=excluded.location,
                profile_image=excluded.profile_image,
                profile_banner=excluded.profile_banner,
                url=excluded.url,
                updated_at=excluded.updated_at
            """
            self._conn.execute(sql, {
                "id":                user.get("id"),
                "screen_name":       user.get("name") or "",
                "name":              user.get("nick") or "",
                "verified":          1 if user.get("verified") else 0,
                "protected":         1 if user.get("protected") else 0,
                "followers_count":   user.get("followers_count"),
                "friends_count":     user.get("friends_count"),
                "statuses_count":    user.get("statuses_count"),
                "media_count":       user.get("media_count"),
                "favourites_count":  user.get("favourites_count"),
                "listed_count":      user.get("listed_count"),
                "description":       user.get("description") or "",
                "location":          user.get("location") or "",
                "profile_image":     user.get("profile_image") or "",
                "profile_banner":    user.get("profile_banner") or "",
                "url":               user.get("url") or "",
                "created_at":        _fmt_date(user.get("date")),
                "updated_at":        now,
            })
            self._conn.commit()
            return True
        except Exception:
            return False

    # ── tweet ──────────────────────────────────────────────

    def insert_tweet(self, kwdict: dict) -> bool:
        """Insert a tweet record if not exists. Returns True if new."""
        tid = kwdict.get("tweet_id")
        if not tid:
            return False

        # Determine tweet type
        if kwdict.get("retweet_id"):
            tweet_type = "retweet"
        elif kwdict.get("quote_id"):
            tweet_type = "quote"
        elif kwdict.get("reply_id"):
            tweet_type = "reply"
        else:
            tweet_type = "tweet"

        # Original tweet reference
        original_tweet_id = (kwdict.get("retweet_id") or
                             kwdict.get("quote_id") or
                             kwdict.get("reply_id") or None)
        original_user_name = kwdict.get("reply_to") or kwdict.get("quote_by") or None

        # Author
        author = kwdict.get("author") or kwdict.get("user") or {}
        user_id = author.get("id")
        if not user_id:
            return False
        self.insert_user(author)

        # Hashtags & mentions as JSON
        hashtags = kwdict.get("hashtags")
        mentions = kwdict.get("mentions")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sql = """
            INSERT OR IGNORE INTO tweets (
                id, user_id, content, tweet_type, lang, source,
                sensitive, created_at,
                favorite_count, quote_count, reply_count,
                retweet_count, bookmark_count, view_count,
                original_tweet_id, original_user_id, original_user_name,
                reply_to_user_id, reply_to_user_name,
                conversation_id, birdwatch,
                hashtags, mentions, updated_at
            ) VALUES (
                :id, :user_id, :content, :tweet_type, :lang, :source,
                :sensitive, :created_at,
                :favorite_count, :quote_count, :reply_count,
                :retweet_count, :bookmark_count, :view_count,
                :original_tweet_id, :original_user_id, :original_user_name,
                :reply_to_user_id, :reply_to_user_name,
                :conversation_id, :birdwatch,
                :hashtags, :mentions, :updated_at
            )
        """
        try:
            self._conn.execute(sql, {
                "id":                  tid,
                "user_id":             user_id,
                "content":             kwdict.get("content") or "",
                "tweet_type":          tweet_type,
                "lang":                kwdict.get("lang") or "",
                "source":              kwdict.get("source") or "",
                "sensitive":           1 if kwdict.get("sensitive") else 0,
                "created_at":          _fmt_date(kwdict.get("date")),
                "favorite_count":      kwdict.get("favorite_count") or 0,
                "quote_count":         kwdict.get("quote_count") or 0,
                "reply_count":         kwdict.get("reply_count") or 0,
                "retweet_count":       kwdict.get("retweet_count") or 0,
                "bookmark_count":      kwdict.get("bookmark_count") or 0,
                "view_count":          kwdict.get("view_count") or 0,
                "original_tweet_id":   original_tweet_id,
                "original_user_id":    None,
                "original_user_name":  original_user_name,
                "reply_to_user_id":    None,
                "reply_to_user_name":  kwdict.get("reply_to") if tweet_type == "reply" else None,
                "conversation_id":     kwdict.get("conversation_id"),
                "birdwatch":           kwdict.get("birdwatch") or "",
                "hashtags":            json.dumps(hashtags, ensure_ascii=False) if hashtags else None,
                "mentions":            json.dumps(mentions, ensure_ascii=False) if mentions else None,
                "updated_at":          now,
            })
            self._conn.commit()
            return self._conn.total_changes > 0
        except sqlite3.IntegrityError:
            return False

    def tweet_exists(self, tweet_id: int) -> bool:
        """Check if a tweet already exists in the database."""
        if not tweet_id:
            return False
        row = self._conn.execute(
            "SELECT 1 FROM tweets WHERE id = ?", (tweet_id,)
        ).fetchone()
        return row is not None

    def get_latest_tweet_id(self, user_id: int) -> int | None:
        """Get the most recent tweet ID for a user."""
        row = self._conn.execute(
            "SELECT id FROM tweets WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,)
        ).fetchone()
        return row[0] if row else None

    # ── media ──────────────────────────────────────────────

    def insert_media(self, kwdict: dict, filepath: str = "") -> bool:
        """Insert a media record. Returns True if new."""
        tid = kwdict.get("tweet_id")
        if not tid:
            return False

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Use ON CONFLICT to avoid duplicate entries for the same tweet+num
        sql = """
            INSERT OR IGNORE INTO media (
                tweet_id, num, url, extension, filename, filepath, created_at
            ) VALUES (
                :tweet_id, :num, :url, :extension, :filename, :filepath, :created_at
            )
        """
        try:
            self._conn.execute(sql, {
                "tweet_id":  tid,
                "num":       kwdict.get("num"),
                "url":       kwdict.get("url") or "",
                "extension": kwdict.get("extension") or "",
                "filename":  kwdict.get("filename") or "",
                "filepath":  filepath or "",
                "created_at": now,
            })
            self._conn.commit()
            return self._conn.total_changes > 0
        except sqlite3.IntegrityError:
            return False

    # ── operation log ──────────────────────────────────────

    def log_start(self, user_id: int, username: str, scan_mode: str) -> int:
        """Create an operation_log row, return its id."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur = self._conn.execute(
            """INSERT INTO operation_log
               (user_id, username, start_time, scan_mode, status)
               VALUES (?, ?, ?, ?, 'running')""",
            (user_id, username, now, scan_mode)
        )
        self._conn.commit()
        return cur.lastrowid

    def log_update(self, log_id: int, **stats):
        """Update stats on an operation_log row."""
        if not log_id:
            return
        sets = []
        params = []
        for key in ("total_scanned", "new_tweets", "existing_tweets",
                     "images_downloaded", "videos_downloaded"):
            if key in stats:
                sets.append(f"{key} = ?")
                params.append(stats[key])
        if not sets:
            return
        params.append(log_id)
        self._conn.execute(
            f"UPDATE operation_log SET {', '.join(sets)} WHERE id = ?",
            params
        )
        self._conn.commit()

    def log_end(self, log_id: int, status: str = "success"):
        """Mark an operation_log row as completed."""
        if not log_id:
            return
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._conn.execute(
            "UPDATE operation_log SET end_time = ?, status = ? WHERE id = ?",
            (now, status, log_id)
        )
        self._conn.commit()


# ── helpers ────────────────────────────────────────────────

def _fmt_date(d) -> str | None:
    """Convert a datetime-like object to ISO-format string."""
    if d is None:
        return None
    if isinstance(d, str):
        return d
    try:
        return d.strftime("%Y-%m-%d %H:%M:%S")
    except AttributeError:
        return str(d)
