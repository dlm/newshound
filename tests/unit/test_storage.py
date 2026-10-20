from datetime import date

import pytest

from newshound.models import Article
from newshound.storage import ArticleStore


def make_article(url: str = "https://example.com/a", score: int | None = None) -> Article:
    return Article(
        title="Example",
        url=url,
        summary="A summary.",
        date=date(2026, 10, 20),
        score=score,
    )


def test_add_persists_article(tmp_path):
    with ArticleStore(tmp_path / "feed.db") as store:
        assert store.add(make_article()) is True
        fetched = store.get_by_url("https://example.com/a")
        assert fetched is not None
        assert fetched.title == "Example"


def test_add_dedupes_on_url(tmp_path):
    with ArticleStore(tmp_path / "feed.db") as store:
        assert store.add(make_article()) is True
        assert store.add(make_article()) is False
        assert len(store.all()) == 1


def test_get_by_url_missing_returns_none(tmp_path):
    with ArticleStore(tmp_path / "feed.db") as store:
        assert store.get_by_url("https://example.com/missing") is None


def test_update_score(tmp_path):
    with ArticleStore(tmp_path / "feed.db") as store:
        store.add(make_article())
        store.update_score("https://example.com/a", 7)
        assert store.get_by_url("https://example.com/a").score == 7


def test_store_creates_parent_directory(tmp_path):
    db_path = tmp_path / "nested" / "feed.db"
    with ArticleStore(db_path) as store:
        store.add(make_article())
    assert db_path.exists()


def test_store_persists_across_reopen(tmp_path):
    db_path = tmp_path / "feed.db"
    with ArticleStore(db_path) as store:
        store.add(make_article())
    with ArticleStore(db_path) as store:
        assert len(store.all()) == 1


def test_get_by_url_normalizes_url(tmp_path):
    with ArticleStore(tmp_path / "feed.db") as store:
        store.add(make_article(url="https://example.com"))
        # pydantic's HttpUrl normalizes this to "https://example.com/"
        assert store.get_by_url("https://example.com") is not None


def test_update_score_rejects_out_of_range(tmp_path):
    with ArticleStore(tmp_path / "feed.db") as store:
        store.add(make_article())
        with pytest.raises(ValueError, match="between 1 and 10"):
            store.update_score("https://example.com/a", 99)
        assert store.get_by_url("https://example.com/a").score is None


def test_add_and_get_from_different_threads(tmp_path):
    import threading

    with ArticleStore(tmp_path / "feed.db") as store:
        errors: list[Exception] = []

        def worker():
            try:
                store.add(make_article())
                store.get_by_url("https://example.com/a")
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        assert not errors
