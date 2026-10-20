from datetime import date

from pydantic import BaseModel, Field, HttpUrl


class Article(BaseModel):
    title: str
    url: HttpUrl
    summary: str
    date: date
    score: int | None = Field(default=None, ge=1, le=10)


class ArticleList(BaseModel):
    articles: list[Article]
