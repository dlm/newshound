import sqlite3
import threading
from datetime import date
from pathlib import Path

from pydantic import HttpUrl

from newshound.models import Article


class ArticleStore:
    """SQLite-backed article storage, deduplicated on URL.

    Safe to share across threads: the pipeline's scheduler thread and the
    on-demand /trigger endpoint both operate on the same store.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS articles (
                    url TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    date TEXT NOT NULL,
                    score INTEGER
                )
                """
            )
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "ArticleStore":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def add(self, article: Article) -> bool:
        """Insert an article. Returns False if its URL is already stored."""
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT OR IGNORE INTO articles (url, title, summary, date, score)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(article.url),
                    article.title,
                    article.summary,
                    article.date.isoformat(),
                    article.score,
                ),
            )
            self._conn.commit()
            return cursor.rowcount > 0

    def get_by_url(self, url: str) -> Article | None:
        normalized_url = str(HttpUrl(url))
        with self._lock:
            row = self._conn.execute(
                "SELECT url, title, summary, date, score FROM articles WHERE url = ?",
                (normalized_url,),
            ).fetchone()
        return self._row_to_article(row) if row else None

    def all(self) -> list[Article]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT url, title, summary, date, score FROM articles ORDER BY date DESC"
            ).fetchall()
        return [self._row_to_article(row) for row in rows]

    def update_score(self, url: str, score: int) -> None:
        if not 1 <= score <= 10:
            raise ValueError(f"score must be between 1 and 10, got {score}")
        normalized_url = str(HttpUrl(url))
        with self._lock:
            self._conn.execute(
                "UPDATE articles SET score = ? WHERE url = ?",
                (score, normalized_url),
            )
            self._conn.commit()

    @staticmethod
    def _row_to_article(row: tuple) -> Article:
        url, title, summary, date_str, score = row
        return Article(
            url=url,
            title=title,
            summary=summary,
            date=date.fromisoformat(date_str),
            score=score,
        )
