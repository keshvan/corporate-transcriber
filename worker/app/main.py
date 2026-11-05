import logging
from uuid import uuid4

from qdrant_client.qdrant_client import QdrantClient

from app.config import Settings, get_settings
from app.models.asr import WhisperTranscriber
from app.models.diarizer import PyannoteDiarizer
from app.models.embedder import SpeechBrainEmbedder
from app.pipeline import TranscribeJob, TranscribePipeline
from app.speakers.identifier import QdrantSpeakerIdentifier
from app.speakers.store import QdrantSpeakerStore
from app.speakers.voice_collection import ensure_voice_collection
from app.storage.qdrant import create_qdrant_client
from app.storage.s3 import S3Storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

def build_pipeline(settings: Settings, qdrant: QdrantClient) -> TranscribePipeline:
    asr = WhisperTranscriber.from_settings(settings)
    asr.warmup()
    return TranscribePipeline(
        storage=S3Storage.from_settings(settings),
        asr=asr,
        diarizer=PyannoteDiarizer.from_settings(settings),
        embedder=SpeechBrainEmbedder.from_settings(settings),
        identifier=QdrantSpeakerIdentifier.from_settings(qdrant, settings),
        store=QdrantSpeakerStore.from_settings(qdrant, settings)
    )

def main():
    settings = get_settings()
    qdrant = create_qdrant_client(settings)
    ensure_voice_collection(qdrant, settings.qdrant_voice_collection)
    pipeline = build_pipeline(settings, qdrant)

    job = TranscribeJob(
        job_id=str(uuid4()),
        meeting_id=str(uuid4()),
        audio_uri=f"s3://{settings.s3_bucket}/meeting.mp3",
        language="ru",
    )

    result = pipeline.run(job)
    transcript = result.transcript

    print(f"Language: {transcript.language}")
    print(f"Segments: {len(transcript.segments)}")
    print(f"Speakers: {[s.label for s in transcript.speakers]}")

    for segment in transcript.segments:
        print(f"[{segment.start_ms} - {segment.end_ms}] {segment.label}: {segment.text}")


if __name__ == "__main__":
    main()
