"""
Phase 8 — delivery abstraction.

Pluggable channels that deliver a finished evaluation report (PDF attachment +
HTML body) to wherever the customer wants it: email, a shared folder, etc.

    from app.delivery import get_channel, DeliveryPayload
    channel = get_channel("email")
    result = channel.dispatch(payload, {"email": "cfo@acme.com"})

8a (this module) is the channel layer. The event-driven dispatcher + Mode C
auto-trigger that *call* these channels arrive in Phase 8b.
"""
from app.delivery.base import DeliveryChannel, DeliveryPayload, DeliveryResult
from app.delivery.email_smtp import EmailSmtpChannel, build_email_message
from app.delivery.folder_drop import FolderDropChannel

# Channel registry — name → instance. Add new channels (sftp, teams, slack) here.
_CHANNELS: dict[str, DeliveryChannel] = {
    EmailSmtpChannel.name: EmailSmtpChannel(),
    FolderDropChannel.name: FolderDropChannel(),
}


def get_channel(name: str) -> DeliveryChannel:
    """Return the delivery channel for `name` (e.g. 'email', 'folder')."""
    try:
        return _CHANNELS[name]
    except KeyError:
        raise ValueError(
            f"Unknown delivery channel {name!r}. Available: {sorted(_CHANNELS)}"
        )


def available_channels() -> list[str]:
    return sorted(_CHANNELS)


__all__ = [
    "DeliveryChannel", "DeliveryPayload", "DeliveryResult",
    "EmailSmtpChannel", "FolderDropChannel", "build_email_message",
    "get_channel", "available_channels",
]
