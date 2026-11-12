from functools import lru_cache

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

    @model_validator(mode="after")
    def _check_postgres_pool(self) -> "Settings":
        if self.postgres_pool_min_size > self.postgres_pool_max_size:
            raise ValueError("postgres_pool_min_size must be <= postgres_pool_max_size")
        return self

@lru_cache
def get_settings() -> Settings:
    return Settings()
