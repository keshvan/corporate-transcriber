import logging
from uuid import uuid4

from app.config import Settings, get_settings
from app.models.asr import WhisperTranscriber
from app.pipeline import TranscribeJob, TranscribePipeline
from app.storage.s3 import S3Storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

def build_pipeline(settings: Settings) -> TranscribePipeline:
    asr = WhisperTranscriber.from_settings(settings)
    asr.warmup()
    return TranscribePipeline(
        storage=S3Storage.from_settings(settings),
        asr=asr,
    )

def main():
    settings = get_settings()
    pipeline = build_pipeline(settings)

    job = TranscribeJob(
        job_id=str(uuid4()),
        meeting_id=str(uuid4()),
        audio_uri=f"s3://{settings.s3_bucket}/meeting.mp3",
        language="ru",
    )

    transcript = pipeline.run(job)

    print(f"Language: {transcript.language}")
    print(f"Segments: {len(transcript.segments)}")

    for segment in transcript.segments:
        print(f"[{segment.start_ms} - {segment.end_ms}] {segment.text}")


if __name__ == "__main__":
    main()
