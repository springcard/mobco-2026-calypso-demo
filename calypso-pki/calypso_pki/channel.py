"""Generic APDU channel contract used by the Calypso PKI algorithm."""

from typing import Protocol, Sequence


class ApduChannel(Protocol):
    def transmit(self, command: Sequence[int], label: str = "") -> tuple[bytes, int]:
        """Send one APDU and return response data without SW plus the status word."""
