from datetime import date

import pytest
from pydantic import ValidationError

from newshound.models import Article, ArticleList


def test_article_round_trips_fields():
    article = Article(
        title="Example",
        url="https://example.com/a",
        summary="A summary.",
        date=date(2026, 10, 20),
    )
    assert article.title == "Example"
    assert str(article.url) == "https://example.com/a"
    assert article.score is None


@pytest.mark.parametrize("score", [1, 5, 10])
def test_article_accepts_in_range_scores(score):
    article = Article(
        title="Example",
        url="https://example.com/a",
        summary="A summary.",
        date=date(2026, 10, 20),
        score=score,
    )
    assert article.score == score


@pytest.mark.parametrize("score", [0, 11, -1])
def test_article_rejects_out_of_range_scores(score):
    with pytest.raises(ValidationError):
        Article(
            title="Example",
            url="https://example.com/a",
            summary="A summary.",
            date=date(2026, 10, 20),
            score=score,
        )


def test_article_list_holds_multiple_articles():
    articles = ArticleList(
        articles=[
            Article(title="A", url="https://example.com/a", summary="s", date=date(2026, 10, 20)),
            Article(title="B", url="https://example.com/b", summary="s", date=date(2026, 10, 19)),
        ]
    )
    assert len(articles.articles) == 2
