from __future__ import annotations

import logging
from collections.abc import Sequence

from confluent_kafka import (
    Consumer,
    KafkaError,
    KafkaException,
    Message,
    Producer,
    TopicPartition,
)

from app.config import Settings
from app.kafka.errors import CommitFailedError, DlqPublishError, KafkaFatalError
from app.schemas.events import ConsumedMessage, DeadLetter

log = logging.getLogger("messaging.kafka")

KafkaConfig = dict[str, str | int | float | bool]

_METADATA_TIMEOUT_S = 10.0

def _security_config(s: Settings) -> KafkaConfig:
    cfg: KafkaConfig = {"security.protocol": s.kafka_security_protocol}
    if s.kafka_sasl_mechanism:
        cfg["sasl.mechanism"] = s.kafka_sasl_mechanism
    if s.kafka_sasl_username:
        cfg["sasl.username"] = s.kafka_sasl_username
    if s.kafka_sasl_password is not None:
        cfg["sasl.password"] = s.kafka_sasl_password.get_secret_value()
    return cfg

def consumer_config(s: Settings) -> KafkaConfig:
    cfg: KafkaConfig = {
        "bootstrap.servers": s.kafka_bootstrap_servers,
        "client.id": s.kafka_client_id,
        "group.id": s.kafka_group_id,
        "enable.auto.commit": s.kafka_enable_auto_commit,
        "auto.offset.reset": s.kafka_auto_offset_reset,
        "session.timeout.ms": s.kafka_session_timeout_ms,
        "heartbeat.interval.ms": s.kafka_heartbeat_interval_ms,
        "max.poll.interval.ms": s.kafka_max_poll_interval_ms,
    }
    cfg.update(_security_config(s))
    return cfg


def producer_config(s: Settings) -> KafkaConfig:
    cfg: KafkaConfig = {
        "bootstrap.servers": s.kafka_bootstrap_servers,
        "client.id": f"{s.kafka_client_id}-dlq",
        "acks": "all",
        "enable.idempotence": True,
        "message.timeout.ms": int(s.kafka_dlq_publish_timeout_s * 1000),
    }
    cfg.update(_security_config(s))
    return cfg

def _as_bytes(value: object) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    raise KafkaFatalError(f"unexpected message payload type {type(value).__name__}")


class ConfluentMessageSource:
    def __init__(self, consumer: Consumer, topic: str) -> None:
        self._consumer = consumer
        self._topic = topic

    @classmethod
    def from_settings(cls, settings: Settings) -> ConfluentMessageSource:
        return cls(Consumer(consumer_config(settings)), settings.kafka_meetings_topic)

    def connect(self) -> None:
        """Fail fast if the broker or the topic is unavailable, then subscribe."""
        try:
            metadata = self._consumer.list_topics(self._topic, timeout=_METADATA_TIMEOUT_S)
        except KafkaException as exc:
            raise KafkaFatalError(f"cannot reach Kafka: {exc}") from exc
        topic_metadata = metadata.topics.get(self._topic)
        if topic_metadata is None or topic_metadata.error is not None:
            raise KafkaFatalError(f"topic {self._topic!r} is not available (was it created?)")
        log.info(
            "consumer connected",
            extra={"brokers": len(metadata.brokers), "subscribed_topic": self._topic},
        )
        self._consumer.subscribe(
            [self._topic],
            on_assign=self._on_assign,
            on_revoke=self._on_revoke,
            on_lost=self._on_lost,
        )

    def poll(self, timeout_s: float) -> ConsumedMessage | None:
        raw = self._consumer.poll(timeout_s)
        if raw is None:
            return None
        error = raw.error()
        if error is not None:
            if error.fatal():
                raise KafkaFatalError(f"{error.name()}: {error.str()}")
            log.warning(
                "kafka consumer error",
                extra={"kafka_error": error.name(), "detail": error.str()},
            )
            return None
        topic, partition, offset = raw.topic(), raw.partition(), raw.offset()
        if topic is None or partition is None or offset is None:
            raise KafkaFatalError("message without topic/partition/offset")
        return ConsumedMessage(
            topic=topic,
            partition=partition,
            offset=offset,
            key=_as_bytes(raw.key()),
            value=_as_bytes(raw.value()),
        )

    def commit(self, message: ConsumedMessage) -> None:
        position = TopicPartition(message.topic, message.partition, message.offset + 1)
        try:
            results = self._consumer.commit(offsets=[position], asynchronous=False)
        except KafkaException as exc:
            raise CommitFailedError(str(exc)) from exc
        for result in results or []:
            if result.error is not None:
                raise CommitFailedError(str(result.error))

    def keepalive(self) -> None:
        try:
            self._consumer.pause(self._consumer.assignment())
            raw = self._consumer.poll(0)
        except KafkaException as exc:
            log.warning("keepalive poll failed", extra={"detail": str(exc)})
            return
        if raw is None or raw.error() is not None:
            return
        topic, partition, offset = raw.topic(), raw.partition(), raw.offset()
        if topic is None or partition is None or offset is None:
            return
        position = TopicPartition(topic, partition, offset)
        try:
            self._consumer.seek(position)
            self._consumer.pause([position])
        except KafkaException as exc:
            log.warning("could not rewind partition after keepalive", extra={"detail": str(exc)})

    def resume(self) -> None:
        try:
            self._consumer.resume(self._consumer.assignment())
        except KafkaException as exc:
            log.warning("resume failed", extra={"detail": str(exc)})

    def close(self) -> None:
        try:
            self._consumer.close()
        except KafkaException as exc:
            log.warning("consumer close failed", extra={"detail": str(exc)})
        else:
            log.info("kafka consumer closed")

    @staticmethod
    def _numbers(partitions: Sequence[TopicPartition]) -> list[int]:
        return [p.partition for p in partitions]

    def _on_assign(self, _consumer: Consumer, partitions: list[TopicPartition]) -> None:
        log.info("partitions assigned", extra={"partitions": self._numbers(partitions)})

    def _on_revoke(self, _consumer: Consumer, partitions: list[TopicPartition]) -> None:
        log.info("partitions revoked", extra={"partitions": self._numbers(partitions)})

    def _on_lost(self, _consumer: Consumer, partitions: list[TopicPartition]) -> None:
        log.warning("partitions lost", extra={"partitions": self._numbers(partitions)})

class _Delivery:
    def __init__(self) -> None:
        self.finished = False
        self.error: str | None = None

    def __call__(self, error: KafkaError | None, _message: Message) -> None:
        self.finished = True
        if error is not None:
            self.error = f"{error.name()}: {error.str()}"


class ConfluentDeadLetterSink:
    def __init__(self, producer: Producer, topic: str, timeout_s: float) -> None:
        self._producer = producer
        self._topic = topic
        self._timeout_s = timeout_s

    @classmethod
    def from_settings(cls, settings: Settings) -> ConfluentDeadLetterSink:
        return cls(
            Producer(producer_config(settings)),
            settings.kafka_dlq_topic,
            settings.kafka_dlq_publish_timeout_s,
        )

    def publish(self, key: bytes | None, record: DeadLetter) -> None:
        delivery = _Delivery()
        try:
            self._producer.produce(
                topic=self._topic,
                key=key,
                value=record.model_dump_json().encode("utf-8"),
                on_delivery=delivery,
            )
        except (BufferError, KafkaException) as exc:
            raise DlqPublishError(f"cannot enqueue DLQ message: {exc}") from exc

        still_queued = self._producer.flush(self._timeout_s)
        if still_queued > 0 or not delivery.finished:
            raise DlqPublishError(f"DLQ publish not confirmed within {self._timeout_s}s")
        if delivery.error is not None:
            raise DlqPublishError(f"DLQ publish failed: {delivery.error}")

    def close(self) -> None:
        remaining = self._producer.flush(self._timeout_s)
        if remaining > 0:
            log.warning("dlq producer closed with unsent messages", extra={"unsent": remaining})
        else:
            log.info("dlq producer closed")
