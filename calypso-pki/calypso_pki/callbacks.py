"""Callbacks emitted by the Calypso PKI business logic."""

from typing import Protocol


class CalypsoPkiCallbacks(Protocol):
    def OnCardUnsupported(self) -> None:
        """The card is not Calypso or does not support the Calypso PKI AID."""

    def OnCardNotGenuine(self) -> None:
        """The card is Calypso-compatible but failed the PKI verification."""

    def OnCardRead(self, CardSerialNumber: str) -> None:
        """The card is Calypso-compatible and genuine."""
