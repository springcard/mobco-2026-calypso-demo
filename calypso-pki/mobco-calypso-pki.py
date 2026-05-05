"""
File: calypso-pki-example.py
Author: springcard/johann.d
Created: 2025-08-22
Description:

    Implementation of the Calypso TN #325 PkiModeExample.
    It has been tested with Thales (Gemalto) Calypso Prime G3 cards only.

    This script is a free sample developed by SpringCard for demonstration purposes only.
    It is provided "as is", without support and without any warranty of any kind.
    Use it at your own risk.

License: MIT License (see LICENSE file for details)
Copyright (c) 2025 SpringCard SAS, France

Dependencies:
    - Python 3
    - pyscard module, provided by the Debian/Raspberry Pi OS python3-pyscard package
      or installed in a virtual environment with pip
    - cryptography module, provided by the Debian/Raspberry Pi OS python3-cryptography
      package or installed in a virtual environment with pip

Usage:
    Place a compliant Calypso Prime card on a SpringCard NFC/RFID HF PC/SC Coupler and run
        python calypso-pki-example.py
    List the available PC/SC readers and exit:
        python calypso-pki-example.py -l
    Use a specific PC/SC reader, optionally with shell-style wildcards:
        python calypso-pki-example.py -r "ReaderName"
        python calypso-pki-example.py -r "SpringCard *"
        python calypso-pki-example.py -r "STid *"
    Use a text file containing accepted CardSerialNumber values:
        python calypso-pki-example.py -f accepted-cards.txt
    Accept every genuine card, ignoring the accepted CardSerialNumber list:
        python calypso-pki-example.py -y
    Run an external script when a card is accepted:
        python calypso-pki-example.py -o open-gpio.sh

"""

import argparse
import sys


def parse_command_line(argv=None):
    parser = argparse.ArgumentParser(
        description="Calypso TN #325 PKI mode example"
    )
    parser.add_argument(
        "-l",
        "--list-readers",
        action="store_true",
        help="list available PC/SC readers and exit",
    )
    parser.add_argument(
        "-r",
        "--reader",
        metavar="ReaderName",
        help="use this PC/SC reader instead of auto-detecting a SpringCard contactless reader; accepts wildcards like 'SpringCard *'",
    )
    parser.add_argument(
        "-f",
        "--file",
        dest="authorized_cards_file",
        metavar="FileName",
        help="text file containing authorized CardSerialNumber values in hexadecimal",
    )
    parser.add_argument(
        "-y",
        "--yes",
        dest="accept_all_cards",
        action="store_true",
        help="accept every genuine card, ignoring the authorized CardSerialNumber list",
    )
    parser.add_argument(
        "-o",
        "--open",
        dest="open_script",
        metavar="ScriptName",
        help="run this .sh or .bat script when a card is accepted",
    )
    return parser.parse_args(argv)


def _print_stats(stats, card_communication_time, crypto_time):
    print("Bytes exchanged")
    print(f"\tPC to Card: {stats.command_bytes}")
    print(f"\tCard to PC: {stats.response_bytes}")
    print(f"\tTotal: {stats.command_bytes + stats.response_bytes}")
    print(f"Number of APDU: {stats.apdus_count}")
    print("Time elapsed")
    print(f"\tCard communication: {card_communication_time}")
    print(f"\tPostponed Cryptography: {crypto_time}")


def _pause_on_windows_when_launched_without_args(argv):
    if (argv is None) and ("win32" == sys.platform) and (len(sys.argv) == 1):
        print("Press Enter to continue")
        sys.stdin.read(1)


def list_pcsc_readers() -> int:
    try:
        import pcsc_channel

        with pcsc_channel.pcsc_context(verbose=False) as hcontext:
            readers = pcsc_channel.list_readers(hcontext)
            pcsc_channel.print_readers(readers)
        return 0
    except Exception as e:
        print("Exception:", e)
        return 1


def run_example(args) -> int:
    try:
        import access_control
        import pcsc_channel
        import pcsc_output

        with pcsc_channel.pcsc_context(verbose=True) as hcontext:
            readers = pcsc_channel.list_readers(hcontext)
            pcsc_channel.print_readers(readers)

            reader = pcsc_channel.select_reader(readers, args.reader)
            print("Using reader: " + reader)

            from calypso_pki import calypso

            calypso.run_self_tests()
            access_control.Configure(
                args.authorized_cards_file,
                accept_all_cards=args.accept_all_cards,
                open_script=args.open_script,
            )

            while True:
                pcsc_channel.wait_for_card_present(hcontext, reader)

                callbacks = access_control.Configure(
                    args.authorized_cards_file,
                    accept_all_cards=args.accept_all_cards,
                    open_script=args.open_script,
                )
                stats = pcsc_channel.ApduStats()
                transaction = None
                card_communication_time = 0.0
                crypto_time = 0.0

                try:
                    with pcsc_channel.connect_channel(hcontext, reader, stats=stats, benchmark=False) as channel:
                        output = pcsc_output.PcscOutput(hcontext, reader, before_control=channel.disconnect)
                        callbacks = access_control.Configure(
                            args.authorized_cards_file,
                            output=output,
                            accept_all_cards=args.accept_all_cards,
                            open_script=args.open_script,
                        )
                        transaction = calypso.read_calypso_pki_transaction(channel, callbacks=callbacks, benchmark=False)
                        card_communication_time = transaction.communication_time
                    print()
                except Exception as e:
                    print("Exception:", e)

                try:
                    if transaction is not None:
                        crypto_time = calypso.verify_calypso_pki_transaction(
                            transaction,
                            callbacks=callbacks,
                            benchmark=False,
                        )
                except Exception as e:
                    print("Exception:", e)

                _print_stats(stats, card_communication_time, crypto_time)
                pcsc_channel.wait_for_card_removal(hcontext, reader)

        return 0
    except KeyboardInterrupt:
        print()
        print("Interrupted.")
        return 0
    except Exception as e:
        print("Exception:", e)
        return 1


def main(argv=None) -> int:
    args = parse_command_line(argv)

    try:
        if args.list_readers:
            return list_pcsc_readers()
        return run_example(args)
    finally:
        _pause_on_windows_when_launched_without_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
