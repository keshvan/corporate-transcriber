from app.domain import SpeakerEmbeddings, SpeakerMatch


class SpeakerIdentifier:  # TODO: qdrant speaker identifier
    def identify(self, embeddings: SpeakerEmbeddings) -> dict[str, SpeakerMatch | None]:
        return {label: None for label in embeddings.vectors}
