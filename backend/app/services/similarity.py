import re
from difflib import SequenceMatcher

from fastapi import HTTPException

from app.clients.deepseek import DeepSeekSuggestionClient
from app.models.post import PostModel
from app.repositories.posts import PostsRepository
from app.schemas.ai import (
    SimilarRequirementItem,
    SimilarRequirementsRequest,
    SimilarRequirementsResponse,
)

MIN_QUERY_CHARS = 5
MIN_SIMILARITY = 0.22
HIGH_CONFIDENCE_THRESHOLD = 0.72


class SimilarRequirementsService:
    def __init__(self, repository: PostsRepository) -> None:
        self.repository = repository

    async def find_similar(self, payload: SimilarRequirementsRequest) -> SimilarRequirementsResponse:
        title = payload.title.strip()
        description = payload.description.strip()
        query_text = f"{title} {description}".strip()
        if len(query_text) < MIN_QUERY_CHARS:
            return SimilarRequirementsResponse(items=[])

        candidates = [
            self._to_item(post, _similarity(title, description, post))
            for post in self.repository.list_posts_for_similarity()
        ]
        candidates = [
            item
            for item in candidates
            if item.similarity >= MIN_SIMILARITY
        ]
        candidates.sort(key=lambda item: (item.similarity, item.votes_count), reverse=True)
        candidates = candidates[: payload.limit]

        if not candidates:
            return SimilarRequirementsResponse(items=[])

        try:
            enhanced = await DeepSeekSuggestionClient().assess_similar_requirements(title, description, candidates)
        except HTTPException:
            return SimilarRequirementsResponse(items=candidates, ai_enhanced=False)

        return SimilarRequirementsResponse(items=enhanced[: payload.limit], ai_enhanced=enhanced != candidates)

    def _to_item(self, post: PostModel, similarity: float) -> SimilarRequirementItem:
        return SimilarRequirementItem(
            id=post.id,
            number=post.number,
            title=post.title,
            description=post.description,
            status=post.status,
            votes_count=len(post.votes),
            similarity=similarity,
            is_high_confidence=similarity >= HIGH_CONFIDENCE_THRESHOLD,
            reason=None,
        )


def _similarity(title: str, description: str, post: PostModel) -> float:
    source_title = title.strip()
    source_body = f"{title} {description}".strip()
    target_title = post.title.strip()
    target_body = f"{post.title} {post.description}".strip()

    title_score = _text_similarity(source_title, target_title) if source_title else 0.0
    body_score = _text_similarity(source_body, target_body)
    keyword_overlap = _token_overlap(source_body, target_body)
    score = title_score * 0.45 + body_score * 0.35 + keyword_overlap * 0.20
    return round(max(0.0, min(score, 1.0)), 4)


def _text_similarity(left: str, right: str) -> float:
    left_norm = _normalize_text(left)
    right_norm = _normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def _token_overlap(left: str, right: str) -> float:
    left_tokens = set(_tokens(left))
    right_tokens = set(_tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _normalize_text(value: str) -> str:
    return " ".join(_tokens(value))


def _tokens(value: str) -> list[str]:
    return [token for token in re.findall(r"[\w\u4e00-\u9fff]+", value.lower()) if len(token) > 1]
