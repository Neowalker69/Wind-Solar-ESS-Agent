from hashlib import sha256

from packages.harness_common.schemas.channel import ChannelEnvelope


def bind_session(envelope: ChannelEnvelope) -> str:
    digest = sha256(envelope.session_key.encode("utf-8")).hexdigest()[:16]
    return f"session_{digest}"
