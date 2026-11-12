import logging
import signal
import threading
from contextlib import ExitStack
from types import FrameType

from psycopg import Connection
from psycopg.rows import TupleRow
from psycopg_pool import ConnectionPool
from qdrant_client.qdrant_client import QdrantClient

from app.config import Settings, get_settings
from app.kafka.client import ConfluentDeadLetterSink, ConfluentMessageSource
from app.kafka.consumer import MeetingConsumer
from app.models.asr import WhisperTranscriber
from app.models.diarizer import PyannoteDiarizer
from app.models.embedder import SpeechBrainEmbedder
from app.pipeline import TranscribePipeline
from app.speakers.identifier import QdrantSpeakerIdentifier
from app.speakers.store import QdrantSpeakerStore
from app.speakers.voice_collection import ensure_voice_collection
from app.storage.meeting_repository import PostgresMeetingResultRepository
from app.storage.postgres import create_postgres_pool
from app.storage.processed_events import ProcessedEvents
from app.storage.qdrant import create_qdrant_client
from app.storage.s3 import S3Storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

log = logging.getLogger("main")

def build_pipeline(
    settings: Settings,
    qdrant: QdrantClient,
    pool: ConnectionPool[Connection[TupleRow]],
    storage: S3Storage,
) -> TranscribePipeline:
    asr = WhisperTranscriber.from_settings(settings)
    asr.warmup()
    return TranscribePipeline(
        storage=storage,
        asr=asr,
        diarizer=PyannoteDiarizer.from_settings(settings),
        embedder=SpeechBrainEmbedder.from_settings(settings),
        identifier=QdrantSpeakerIdentifier.from_settings(qdrant, settings),
        store=QdrantSpeakerStore.from_settings(qdrant, settings),
        results=PostgresMeetingResultRepository(pool),
    )


def _install_signal_handlers(stop: threading.Event) -> None:
    def handle(signum: int, _frame: FrameType | None) -> None:
        if stop.is_set():
            log.warning("second signal, aborting | signal=%s", signum)
            raise KeyboardInterrupt
        log.info("shutdown requested, finishing the current message | signal=%s", signum)
        stop.set()

    signal.signal(signal.SIGINT, handle)
    signal.signal(signal.SIGTERM, handle)


def _run(settings: Settings, stop: threading.Event) -> None:
    with ExitStack() as resources:
        qdrant = create_qdrant_client(settings)
        resources.callback(qdrant.close)
        ensure_voice_collection(qdrant, settings.qdrant_voice_collection)

        pool = create_postgres_pool(settings)
        resources.callback(pool.close)

        storage = S3Storage.from_settings(settings)
        pipeline = build_pipeline(settings, qdrant, pool, storage)

        dead_letters = ConfluentDeadLetterSink.from_settings(settings)
        resources.callback(dead_letters.close)

        source = ConfluentMessageSource.from_settings(settings)
        resources.callback(source.close)
        source.connect()

        MeetingConsumer(
            source=source,
            pipeline=pipeline,
            processed_events=ProcessedEvents(pool),
            dead_letters=dead_letters,
            stop=stop,
            audio_uri=storage.uri,
            default_language=settings.worker_default_language,
            max_retries=settings.kafka_max_retries,
            backoff_ms=settings.kafka_retry_backoff_ms,
            backoff_max_ms=settings.kafka_retry_backoff_max_ms,
        ).run()

def main() -> int:
    settings = get_settings()
    stop = threading.Event()
    _install_signal_handlers(stop)
    log.info(
        "worker starting | bootstrap=%s group=%s topic=%s dlq=%s",
        settings.kafka_bootstrap_servers,
        settings.kafka_group_id,
        settings.kafka_meetings_topic,
        settings.kafka_dlq_topic,
    )
    try:
        _run(settings, stop)
    except KeyboardInterrupt:
        log.warning("aborted; the in-flight message was not committed and will be redelivered")
        return 130
    except Exception:
        log.exception("worker stopped by a fatal error; uncommitted messages will be redelivered")
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
