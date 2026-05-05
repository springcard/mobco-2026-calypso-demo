"""PC/SC direct-control outputs for supported reader families."""

from contextlib import contextmanager
import sys

try:
    from smartcard.scard import (
        SCARD_LEAVE_CARD,
        SCARD_PROTOCOL_T0,
        SCARD_PROTOCOL_T1,
        SCARD_S_SUCCESS,
        SCARD_SHARE_DIRECT,
        SCARD_CTL_CODE,
        SCardConnect,
        SCardControl,
        SCardDisconnect,
        SCardGetErrorMessage,
    )
except ModuleNotFoundError as exc:
    if exc.name != "smartcard":
        raise
    raise ModuleNotFoundError(
        "Missing Python module 'smartcard' from the pyscard package. "
        "On Raspberry Pi OS/Debian, install it with "
        "'sudo apt install python3-pyscard', or create a virtual "
        "environment and run 'python -m pip install -r requirements.txt'."
    ) from exc


SCARD_PROTOCOL_UNDEFINED = 0
SSCP_CMD_OUTPUT_RGB = 0x000050
SPRINGCARD_CONTROL_FUNCTION_LINUX = 1
SPRINGCARD_CONTROL_FUNCTION_WINDOWS = 3500
SPRINGCORE_CLA_CONTROL = 0x58
SPRINGCORE_INS_PLAY_SEQUENCE = 0x90

COLOR_RED = 0xFF0000
COLOR_GREEN = 0x00FF00
COLOR_ORANGE = 0xFF8000

LED_1_SECOND = 10
LED_3_SECONDS = 30
BEEP_100_MS = 1
BEEP_200_MS = 2
BEEP_1_SECOND = 10

SPRINGCARD_SEQUENCE_READ_FAILED = 0x24
SPRINGCARD_SEQUENCE_ACCESS_GRANTED = 0x60
SPRINGCARD_SEQUENCE_ACCESS_DENIED = 0x61


def _springcard_control_code():
    if sys.platform == "win32":
        return SCARD_CTL_CODE(SPRINGCARD_CONTROL_FUNCTION_WINDOWS)

    return SCARD_CTL_CODE(SPRINGCARD_CONTROL_FUNCTION_LINUX)


SPRINGCARD_CONTROL_CODE = _springcard_control_code()


def _check(hresult, where):
    if hresult != SCARD_S_SUCCESS:
        raise RuntimeError(f"{where}: {SCardGetErrorMessage(hresult)}")


@contextmanager
def _direct_channel(context, reader_name):
    hcard = None

    try:
        for protocol in (SCARD_PROTOCOL_UNDEFINED, SCARD_PROTOCOL_T0 | SCARD_PROTOCOL_T1):
            hresult, candidate_hcard, _active_protocol = SCardConnect(
                context,
                reader_name,
                SCARD_SHARE_DIRECT,
                protocol,
            )
            if hresult == SCARD_S_SUCCESS:
                hcard = candidate_hcard
                break
        else:
            _check(hresult, "SCardConnect")

        yield hcard

    finally:
        if hcard is not None:
            SCardDisconnect(hcard, SCARD_LEAVE_CARD)


class _pcsc_output_base:
    def __init__(self, context, reader_name, before_control=None, control_code=SSCP_CMD_OUTPUT_RGB):
        self.context = context
        self.reader_name = reader_name
        self.before_control = before_control
        self.control_code = control_code

    def _before_control(self):
        if self.before_control is not None:
            self.before_control()

    def _control(self, payload):
        self._before_control()

        with _direct_channel(self.context, self.reader_name) as hcard:
            hresult, response = SCardControl(hcard, self.control_code, payload)
            _check(hresult, "SCardControl")
            return bytes(response)


class pcsc_output_stid(_pcsc_output_base):
    def __init__(self, context, reader_name, before_control=None):
        super().__init__(context, reader_name, before_control, SSCP_CMD_OUTPUT_RGB)

    def outputs_rgb(self, rgb, led_duration, buzzer_duration):
        payload = [
            (rgb >> 16) & 0xFF,
            (rgb >> 8) & 0xFF,
            rgb & 0xFF,
            led_duration,
            buzzer_duration,
        ]

        response = self._control(payload)
        if response:
            print("SCardControl response:", response.hex(" "))

    def OnCardUnsupported(self):
        self.outputs_rgb(COLOR_ORANGE, LED_1_SECOND, BEEP_100_MS)

    def OnCardNotGenuine(self):
        self.outputs_rgb(COLOR_ORANGE, LED_1_SECOND, BEEP_1_SECOND)

    def OnCardAccepted(self):
        self.outputs_rgb(COLOR_GREEN, LED_3_SECONDS, BEEP_200_MS)

    def OnCardDenied(self):
        self.outputs_rgb(COLOR_RED, LED_3_SECONDS, BEEP_1_SECOND)


class pcsc_output_springcard(_pcsc_output_base):
    def __init__(self, context, reader_name, before_control=None):
        super().__init__(context, reader_name, before_control, SPRINGCARD_CONTROL_CODE)

    def play_sequence(self, sequence):
        payload = [
            SPRINGCORE_CLA_CONTROL,
            SPRINGCORE_INS_PLAY_SEQUENCE,
            sequence,
        ]
        response = self._control(payload)

        if response and response[0] != 0x00:
            raise RuntimeError(f"PLAY_SEQUENCE failed, status={response[0]:02X}")
        if len(response) > 1:
            print("SCardControl response:", response.hex(" "))

    def OnCardUnsupported(self):
        self.play_sequence(SPRINGCARD_SEQUENCE_READ_FAILED

    def OnCardNotGenuine(self):
        self.play_sequence(SPRINGCARD_SEQUENCE_READ_FAILED)

    def OnCardAccepted(self):
        self.play_sequence(SPRINGCARD_SEQUENCE_ACCESS_GRANTED)

    def OnCardDenied(self):
        self.play_sequence(SPRINGCARD_SEQUENCE_ACCESS_DENIED)


def PcscOutput(context, reader_name, before_control=None):
    reader_name_lower = reader_name.lower()

    if "stid" in reader_name_lower:
        return pcsc_output_stid(context, reader_name, before_control)

    if "springcard" in reader_name_lower:
        return pcsc_output_springcard(context, reader_name, before_control)

    raise RuntimeError("Unsupported reader output type: " + reader_name)
