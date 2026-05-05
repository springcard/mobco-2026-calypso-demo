"""PC/SC reader discovery, card connection and APDU channel implementation."""

from contextlib import contextmanager
from dataclasses import dataclass

from smartcard.scard import *

CARD_STATUS_CHANGE_TIMEOUT_MS = 1000


@dataclass
class ApduStats:
    apdus_count: int = 0
    command_bytes: int = 0
    response_bytes: int = 0


@contextmanager
def pcsc_context(verbose: bool = False):
    hresult, hcontext = SCardEstablishContext(SCARD_SCOPE_USER)
    if hresult != SCARD_S_SUCCESS:
        raise Exception("Failed to establish context : " + SCardGetErrorMessage(hresult))

    if verbose:
        print("Context established!")

    try:
        yield hcontext
    finally:
        hresult = SCardReleaseContext(hcontext)
        if hresult != SCARD_S_SUCCESS:
            raise Exception("Failed to release context: " + SCardGetErrorMessage(hresult))
        if verbose:
            print("Released context.")


def list_readers(hcontext):
    hresult, readers = SCardListReaders(hcontext, [])
    if hresult == SCARD_E_NO_READERS_AVAILABLE:
        return []
    if hresult != SCARD_S_SUCCESS:
        raise Exception("Failed to list readers: " + SCardGetErrorMessage(hresult))
    return readers


def print_readers(readers) -> None:
    if len(readers) < 1:
        print("No smart card readers")
    else:
        print("PCSC Readers:")
        for reader in readers:
            print("\t" + reader)


def select_reader(readers, requested_reader=None):
    if len(readers) < 1:
        raise Exception("No smart card readers")

    if requested_reader is not None:
        if requested_reader not in readers:
            raise Exception("Reader not found: " + requested_reader)
        return requested_reader

    for reader in readers:
        reader_lower = reader.lower()
        if "springcard" in reader_lower:
            if (" contactless " in reader_lower) or (" nfc " in reader_lower):
                return reader

    raise Exception("SpringCard contactless reader not found")


def _check_status_change(hresult):
    if hresult != SCARD_S_SUCCESS:
        raise Exception("Failed to get reader status: " + SCardGetErrorMessage(hresult))


def _reader_event_state(hcontext, reader_name, current_state=SCARD_STATE_UNAWARE, timeout_ms=0):
    hresult, states = SCardGetStatusChange(
        hcontext,
        timeout_ms,
        [(reader_name, current_state)],
    )
    _check_status_change(hresult)
    _reader, event_state, _atr = states[0]
    return event_state


def _wait_for_reader_state(hcontext, reader_name, current_state, timeout_ms):
    hresult, states = SCardGetStatusChange(
        hcontext,
        timeout_ms,
        [(reader_name, current_state)],
    )
    if hresult == SCARD_E_TIMEOUT:
        return current_state
    _check_status_change(hresult)
    _reader, event_state, _atr = states[0]
    return event_state


def wait_for_card_present(hcontext, reader_name, timeout_ms=CARD_STATUS_CHANGE_TIMEOUT_MS):
    event_state = _reader_event_state(hcontext, reader_name)
    if event_state & SCARD_STATE_PRESENT:
        return

    print("Waiting for card insertion...")
    while True:
        event_state = _wait_for_reader_state(hcontext, reader_name, event_state, timeout_ms)
        if event_state & SCARD_STATE_PRESENT:
            return


def wait_for_card_removal(hcontext, reader_name, timeout_ms=CARD_STATUS_CHANGE_TIMEOUT_MS):
    event_state = _reader_event_state(hcontext, reader_name)
    if not (event_state & SCARD_STATE_PRESENT):
        return

    print("Waiting for card removal...")
    while True:
        event_state = _wait_for_reader_state(hcontext, reader_name, event_state, timeout_ms)
        if not (event_state & SCARD_STATE_PRESENT):
            return


@dataclass
class PcscApduChannel:
    hcard: int
    protocol: int
    stats: ApduStats
    benchmark: bool = False
    connected: bool = True

    def transmit(self, command, label=""):
        if not self.connected:
            raise Exception("Card channel is closed")

        if not self.benchmark:
            print(f"{label} command:\n\t{bytes(command).hex().upper()}")

        hresult, response = SCardTransmit(self.hcard, self.protocol, command)
        if hresult != SCARD_S_SUCCESS:
            raise Exception(f"Failed to transmit {label}: " + SCardGetErrorMessage(hresult))
        sw = (response[-2] << 8) + response[-1]

        if not self.benchmark:
            print(f"{label} response:\n\t{bytes(response).hex().upper()} (SW={sw:04X})")

        self.stats.apdus_count += 1
        self.stats.command_bytes += len(command)
        self.stats.response_bytes += len(response)

        return bytes(response[:-2]), sw

    def disconnect(self):
        if not self.connected:
            return

        hresult = SCardDisconnect(self.hcard, SCARD_RESET_CARD)
        self.connected = False
        if hresult != SCARD_S_SUCCESS:
            raise Exception("Failed to disconnect: " + SCardGetErrorMessage(hresult))
        print("Disconnected")


@contextmanager
def connect_channel(hcontext, reader_name, stats=None, benchmark: bool = False):
    if stats is None:
        stats = ApduStats()

    hresult, hcard, active_protocol = SCardConnect(
        hcontext,
        reader_name,
        SCARD_SHARE_SHARED,
        SCARD_PROTOCOL_T0 | SCARD_PROTOCOL_T1,
    )
    if hresult != SCARD_S_SUCCESS:
        raise Exception("Unable to connect: " + SCardGetErrorMessage(hresult))

    if not benchmark:
        print(f"Connected with active protocol={active_protocol}")
        print()

    channel = PcscApduChannel(hcard, active_protocol, stats, benchmark)
    try:
        yield channel
    finally:
        channel.disconnect()
