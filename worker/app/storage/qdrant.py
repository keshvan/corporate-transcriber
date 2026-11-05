from __future__ import annotations

from qdrant_client import QdrantClient

from app.config import Settings


def create_qdrant_client(s: Settings) -> QdrantClient:
    """Единственный клиент Qdrant на процесс; передаётся в компоненты через конструкторы."""
    api_key = s.qdrant_api_key.get_secret_value() if s.qdrant_api_key else None
    return QdrantClient(url=s.qdrant_url, api_key=api_key)
