from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from speechbrain.inference.speaker import EncoderClassifier

from app.config import Settings
from app.domain import SpeakerEmbeddings, SpeakerTurn

SAMPLE_RATE = 16_000


class SpeechBrainEmbedder:
    def __init__(
        self,
        model_name: str,
        device: str,
        savedir: str | None = None,
        min_turn_ms: int = 1_000,
        max_speaker_ms: int = 60_000,
    ) -> None:
        self._model_name = model_name
        self._min_turn_ms = min_turn_ms
        self._max_speaker_ms = max_speaker_ms
        classifier = EncoderClassifier.from_hparams(
            source=model_name,
            savedir=savedir,
            run_opts={"device": device},
        )
        if classifier is None:
            raise RuntimeError(f"cannot load {model_name}")
        self._classifier = classifier

    @classmethod
    def from_settings(cls, s: Settings) -> SpeechBrainEmbedder:
        savedir = None
        if s.worker_models_dir:
            savedir = str(
                Path(s.worker_models_dir) / s.worker_embedding_model.replace("/", "--")
            )
        return cls(
            model_name=s.worker_embedding_model,
            device=s.worker_device,
            savedir=savedir,
        )

    def embed(self, wav: Path, turns: list[SpeakerTurn]) -> SpeakerEmbeddings:
        by_label: dict[str, list[SpeakerTurn]] = defaultdict(list)
        for t in turns:
            by_label[t.label].append(t)

        vectors: dict[str, np.ndarray] = {}
        speech_ms: dict[str, int] = {}
        for label, label_turns in by_label.items():
            result = self._embed_speaker(wav, label_turns)
            if result is None:
                continue
            vector, used_ms = result
            vectors[label] = vector
            speech_ms[label] = used_ms

        return SpeakerEmbeddings(model=self._model_name, vectors=vectors, speech_ms=speech_ms)

    def _select(self, turns: list[SpeakerTurn]) -> list[tuple[int, int]]:
        chunks: list[tuple[int, int]] = []
        total = 0
        for t in sorted(turns, key=lambda t: t.duration_ms, reverse=True):
            if total >= self._max_speaker_ms:
                break
            if chunks and t.duration_ms < self._min_turn_ms:
                break
            length = min(t.duration_ms, self._max_speaker_ms - total)
            chunks.append((t.start_ms, t.start_ms + length))
            total += length
        return chunks

    @torch.inference_mode()
    def _embed_speaker(self, wav: Path, turns: list[SpeakerTurn]) -> tuple[np.ndarray, int] | None:
        vectors: list[np.ndarray] = []
        weights: list[int] = []

        for start_ms, end_ms in self._select(turns):
            signal = self._read(wav, start_ms, end_ms)
            if signal.numel() == 0:
                continue
            emb = self._classifier.encode_batch(signal).squeeze().cpu().numpy()
            if not np.isfinite(emb).all():
                continue
            vectors.append(emb / np.linalg.norm(emb))
            weights.append(end_ms - start_ms)

        if not vectors:
            return None

        mean = np.average(np.stack(vectors), axis=0, weights=weights)
        return mean / np.linalg.norm(mean),sum(weights)

    def _read(self, wav: Path, start_ms: int, end_ms: int) -> torch.Tensor:
        data, sr = sf.read(
            str(wav),
            start=start_ms * SAMPLE_RATE // 1000,
            stop=end_ms * SAMPLE_RATE // 1000,
            dtype="float32",
            always_2d=True,
        )
        if sr != SAMPLE_RATE:
            raise ValueError(f"expected {SAMPLE_RATE} Hz wav, got {sr}")
        mono = torch.from_numpy(data.mean(axis=1))
        return mono.unsqueeze(0).to(self._classifier.device)
