from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.config import Settings
from app.domain import SpeakerEmbeddings, SpeakerMatch
from app.speakers.voice_collection import (
    STATUS_CONFIRMED,
    Key,
    to_point_vector,
)

log = logging.getLogger("speakers.identifier")

GroupScorer = Callable[[Sequence[float]], float]

_MAX_GROUPS = 5


def max_score(scores: Sequence[float]) -> float:
    return max(scores)


class QdrantSpeakerIdentifier:
    def __init__(
        self,
        client: QdrantClient,
        collection: str,
        threshold: float,
        group_size: int,
        scorer: GroupScorer = max_score,
    ) -> None:
        self._client = client
        self._collection = collection
        self._threshold = threshold
        self._group_size = group_size
        self._scorer = scorer

    @classmethod
    def from_settings(
        cls, client: QdrantClient, s: Settings
    ) -> QdrantSpeakerIdentifier:
        return cls(
            client=client,
            collection=s.qdrant_voice_collection,
            threshold=s.speaker_match_threshold,
            group_size=s.speaker_search_group_size,
        )

    def identify(self, embeddings: SpeakerEmbeddings) -> dict[str, SpeakerMatch | None]:
        try:
            return self._identify(embeddings)
        except Exception:
            log.exception("speaker identification failed, continuing without matches")
            no_matches: dict[str, SpeakerMatch | None] = {
                label: None for label in embeddings.vectors
            }
            return no_matches

    def _identify(self, embeddings: SpeakerEmbeddings) -> dict[str, SpeakerMatch | None]:
        matches: dict[str, SpeakerMatch | None] = {}
        for label, vector in embeddings.vectors.items():
            query = to_point_vector(vector)
            if query is None:
                log.warning("speaker has no usable embedding", extra={"label": label})
                matches[label] = None
                continue
            matches[label] = self._search(embeddings.model, query)
        return matches

    def _search(self, model: str, query: list[float]) -> SpeakerMatch | None:
        response = self._client.query_points_groups(
            collection_name=self._collection,
            query=query,
            group_by=Key.PERSON_ID,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key=Key.STATUS, match=MatchValue(value=STATUS_CONFIRMED)
                    ),
                    FieldCondition(key=Key.MODEL, match=MatchValue(value=model)),
                ]
            ),
            limit=_MAX_GROUPS,
            group_size=self._group_size,
            with_payload=False,
            with_vectors=False,
        )

        best_person: str | None = None
        best_score = float("-inf")
        for group in response.groups:
            scores = [hit.score for hit in group.hits]
            if not scores:
                continue
            score = self._scorer(scores)
            if score > best_score:
                best_person, best_score = str(group.id), score

        if best_person is None or best_score < self._threshold:
            return None
        return SpeakerMatch(person_id=best_person, score=best_score)
