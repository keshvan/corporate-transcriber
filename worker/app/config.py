from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra='allow')

    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: SecretStr = SecretStr("minioadmin")
    s3_bucket: str = "audio"

    hf_token: SecretStr | None = None

    worker_whisper_model: str = "small"
    worker_device: str = "cpu"
    worker_compute_type: str = "float32"
    worker_models_dir: str | None = None
    worker_beam_size: int = 5

    worker_diarization_model: str = "pyannote/speaker-diarization-3.1"
    worker_min_speakers: int | None = None
    worker_max_speakers: int | None = None

    worker_embedding_model: str = "speechbrain/spkrec-ecapa-voxceleb"

    worker_default_language: str | None = "ru"

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None

    qdrant_voice_collection: str = "voice_profiles"

    speaker_match_threshold: float = Field(default=0.5, ge=-1.0, le=1.0)
    speaker_save_min_speech_ms: int = Field(default=5_000, ge=0)
    speaker_search_group_size: int = Field(default=3, ge=1)

    postgres_dsn: SecretStr = SecretStr("postgres://postgres:postgres@localhost:5432/project_memory")
    postgres_pool_min_size: int = Field(default=1, ge=0)
    postgres_pool_max_size: int = Field(default=4, ge=1)
    postgres_connect_timeout_s: float = Field(default=10.0, gt=0)

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_client_id: str = "project-memory-worker"
    kafka_group_id: str = "meeting-processing-group"

    kafka_meetings_topic: str = "meetings.processing"
    kafka_dlq_topic: str = "meetings.processing.dlq"

    kafka_auto_offset_reset: Literal["earliest", "latest"] = "earliest"
    kafka_enable_auto_commit: Literal[False] = False

    kafka_session_timeout_ms: int = Field(default=45_000, ge=6_000, le=1_800_000)
    kafka_heartbeat_interval_ms: int = Field(default=3_000, ge=1)
    kafka_max_poll_interval_ms: int = Field(default=7_200_000, ge=1, le=86_400_000)

    kafka_max_retries: int = Field(default=3, ge=0)
    kafka_retry_backoff_ms: int = Field(default=2_000, ge=0)
    kafka_retry_backoff_max_ms: int = Field(default=60_000, ge=0)
    kafka_dlq_publish_timeout_s: float = Field(default=30.0, gt=0)

    kafka_security_protocol: Literal["PLAINTEXT", "SSL", "SASL_PLAINTEXT", "SASL_SSL"] = "PLAINTEXT"
    kafka_sasl_mechanism: str | None = None
    kafka_sasl_username: str | None = None
    kafka_sasl_password: SecretStr | None = None

    @model_validator(mode="after")
    def _check_postgres_pool(self) -> "Settings":
        if self.postgres_pool_min_size > self.postgres_pool_max_size:
            raise ValueError("postgres_pool_min_size must be <= postgres_pool_max_size")
        return self

    @model_validator(mode="after")
    def _check_kafka(self) -> "Settings":
        if self.kafka_heartbeat_interval_ms * 3 > self.kafka_session_timeout_ms:
            raise ValueError("kafka_heartbeat_interval_ms must be <= kafka_session_timeout_ms / 3")
        if self.kafka_max_poll_interval_ms < self.kafka_session_timeout_ms:
            raise ValueError("kafka_max_poll_interval_ms must be >= kafka_session_timeout_ms")
        if self.kafka_retry_backoff_max_ms < self.kafka_retry_backoff_ms:
            raise ValueError("kafka_retry_backoff_max_ms must be >= kafka_retry_backoff_ms")
        if self.kafka_meetings_topic == self.kafka_dlq_topic:
            raise ValueError("kafka_dlq_topic must differ from kafka_meetings_topic")
        if self.kafka_security_protocol.startswith("SASL") and not (
            self.kafka_sasl_mechanism and self.kafka_sasl_username and self.kafka_sasl_password
        ):
            raise ValueError(
                "SASL security protocols require kafka_sasl_mechanism, "
                "kafka_sasl_username and kafka_sasl_password"
            )
        return self

@lru_cache
def get_settings() -> Settings:
    return Settings()
