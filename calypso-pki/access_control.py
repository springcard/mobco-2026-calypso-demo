"""Access-control callbacks for Calypso PKI cards."""

import os
from pathlib import Path
import re
import subprocess
import sys


def _normalize_serial(serial) -> str:
    if isinstance(serial, bytes):
        return serial.hex().upper()

    text = str(serial).strip().upper()
    if text.startswith("0X"):
        text = text[2:]
    text = re.sub(r"[\s:._-]", "", text)

    if not text:
        return ""
    if re.fullmatch(r"[0-9A-F]+", text) is None:
        raise ValueError(f"Invalid hexadecimal card serial number: {serial}")
    return text


def _load_authorized_serials(file_name):
    if file_name is None:
        return set()

    path = Path(file_name)
    serials = set()

    with path.open("r", encoding="utf-8") as fd:
        for line_number, line in enumerate(fd, start=1):
            value = line.partition("#")[0].strip()
            if not value:
                continue

            try:
                serials.add(_normalize_serial(value))
            except ValueError as e:
                raise ValueError(f"{path}:{line_number}: {e}") from e

    return serials


def _open_script_path(file_name):
    if file_name is None:
        return None

    path = Path(file_name).expanduser().resolve(strict=True)
    if path.suffix.lower() not in (".sh", ".bat"):
        raise ValueError("Open script must be a .sh or .bat file: " + str(path))

    return path


def _open_script_command(path):
    if path.suffix.lower() == ".bat":
        if sys.platform == "win32":
            return ["cmd.exe", "/c", str(path)]
        raise RuntimeError("Batch open scripts are only supported on Windows")

    return ["sh", str(path)]


class AccessControlCallbacks:
    def __init__(self, authorized_cards_file=None, output=None, accept_all_cards=False, open_script=None):
        self.authorized_cards_file = authorized_cards_file
        self.output = output
        self.accept_all_cards = accept_all_cards
        self.open_script = _open_script_path(open_script)
        self.authorized_serials = set()
        if not self.accept_all_cards:
            self.authorized_serials = _load_authorized_serials(authorized_cards_file)

    def _output(self, event_name):
        if self.output is None:
            return

        event = getattr(self.output, event_name, None)
        if event is None:
            return

        try:
            event()
        except Exception as e:
            print("Output error:", e)

    def _run_open_script(self, card_serial_number):
        if self.open_script is None:
            return

        env = os.environ.copy()
        env["CALYPSO_CARD_SERIAL_NUMBER"] = card_serial_number

        try:
            print("Running open script: " + str(self.open_script), flush=True)
            subprocess.run(
                _open_script_command(self.open_script),
                cwd=self.open_script.parent,
                env=env,
                check=True,
            )
        except Exception as e:
            print("Open script error:", e)

    def OnCardUnsupported(self):
        print("Card unsupported")
        self._output("OnCardUnsupported")

    def OnCardNotGenuine(self):
        print("Card not genuine")
        self._output("OnCardNotGenuine")

    def OnCardRead(self, CardSerialNumber):
        card_serial_number = _normalize_serial(CardSerialNumber)
        if self.accept_all_cards or (card_serial_number in self.authorized_serials):
            self.OnCardAccepted(card_serial_number)
            return True

        self.OnCardDenied(card_serial_number)
        return False

    def OnCardAccepted(self, CardSerialNumber):
        card_serial_number = _normalize_serial(CardSerialNumber)
        print("Card accepted: " + card_serial_number, flush=True)
        self._output("OnCardAccepted")
        self._run_open_script(card_serial_number)

    def OnCardDenied(self, CardSerialNumber):
        print("Card denied: " + CardSerialNumber)
        self._output("OnCardDenied")


_callbacks = AccessControlCallbacks()


def Configure(authorized_cards_file=None, output=None, accept_all_cards=False, open_script=None):
    global _callbacks

    _callbacks = AccessControlCallbacks(
        authorized_cards_file,
        output=output,
        accept_all_cards=accept_all_cards,
        open_script=open_script,
    )
    return _callbacks


def OnCardUnsupported():
    return _callbacks.OnCardUnsupported()


def OnCardNotGenuine():
    return _callbacks.OnCardNotGenuine()


def OnCardRead(CardSerialNumber):
    return _callbacks.OnCardRead(CardSerialNumber)


def OnCardAccepted(CardSerialNumber):
    return _callbacks.OnCardAccepted(CardSerialNumber)


def OnCardDenied(CardSerialNumber):
    return _callbacks.OnCardDenied(CardSerialNumber)
