from __future__ import annotations

import logging
from typing import Final

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

log = logging.getLogger("speakers.collection")

VECTOR_SIZE: Final = 192
DISTANCE: Final = Distance.COSINE

STATUS_UNKNOWN: Final = "unknown"
STATUS_CONFIRMED: Final = "confirmed"


class Key:
    STATUS: Final = "status"
    PERSON_ID: Final = "person_id"
    MEETING_ID: Final = "meeting_id"
    LABEL: Final = "label"
    MODEL: Final = "model"
    SPEECH_MS: Final = "speech_ms"
    PINNED: Final = "pinned"
    CREATED_AT: Final = "created_at"
    ATTACHED_AT: Final = "attached_at"
    SUGGESTED_PERSON_ID: Final = "suggested_person_id"
    SUGGESTED_SCORE: Final = "suggested_score"


INDEXED_FIELDS: Final = (Key.STATUS, Key.PERSON_ID, Key.MODEL)


class VoiceCollectionError(RuntimeError):
    pass


def to_point_vector(vector: np.ndarray) -> list[float] | None:
    flat = np.asarray(vector, dtype=np.float32).reshape(-1)
    if flat.size != VECTOR_SIZE or not np.isfinite(flat).all():
        return None
    return [float(x) for x in flat]


def ensure_voice_collection(client: QdrantClient, name: str) -> None:
    if client.collection_exists(name):
        _verify_schema(client, name)
    else:
        try:
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=DISTANCE),
            )
            log.info("collection created", extra={"collection": name})
        except Exception:
            if not client.collection_exists(name):
                raise
            _verify_schema(client, name)
    _ensure_payload_indexes(client, name)


def _verify_schema(client: QdrantClient, name: str) -> None:
    vectors = client.get_collection(name).config.params.vectors
    if not isinstance(vectors, VectorParams):
        raise VoiceCollectionError(
            f"collection '{name}' must have a single unnamed vector"
        )
    if vectors.size != VECTOR_SIZE:
        raise VoiceCollectionError(
            f"collection '{name}': vector size is {vectors.size}, expected {VECTOR_SIZE}"
        )
    if vectors.distance != DISTANCE:
        raise VoiceCollectionError(
            f"collection '{name}': metric is {vectors.distance}, expected {DISTANCE}"
        )


def _ensure_payload_indexes(client: QdrantClient, name: str) -> None:
    schema = client.get_collection(name).payload_schema
    for field in INDEXED_FIELDS:
        existing = schema.get(field)
        if existing is None:
            client.create_payload_index(
                collection_name=name,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )
        elif existing.data_type != PayloadSchemaType.KEYWORD:
            raise VoiceCollectionError(
                f"collection '{name}': index on '{field}' has type "
                f"{existing.data_type}, expected keyword"
            )
