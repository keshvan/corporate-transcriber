from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env")

    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: SecretStr = SecretStr("minioadmin")
    s3_bucket: str = "audio"

    hf_token: SecretStr = SecretStr("")

    worker_whisper_model: str = "small"
    worker_device: str = "cpu"
    worker_compute_type: str = "float32"
    worker_models_dir: str | None = None
    worker_beam_size: int = 5

    worker_diarization_model: str = "pyannote/speaker-diarization-3.1"
    worker_min_speakers: int | None = None
    worker_max_speakers: int | None = None

    worker_embedding_model: str = "speechbrain/spkrec-ecapa-voxceleb"

@lru_cache
def get_settings() -> Settings:
    return Settings()
