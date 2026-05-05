# MOBCO 2026 Calypso / SPAC Demonstrator

This repository contains a trade-show demonstrator prepared by SpringCard and STid for SPAC Alliance and Calypso Networks Association in the context of MOBCO 2026.

The purpose of the demonstration is simple: show that a Calypso card, normally associated with mobility and contactless ticketing, can also be presented as a credential in a physical access-control scenario. The demo is intended to make the connection visible between two ecosystems that usually address different operational domains:

- Calypso, with its roots in open contactless ticketing for transport and mobility.
- SPAC Alliance, with its focus on smart physical access control, security, interoperability and certification.

SpringCard and STid act as technical sponsors and enablers of the demonstration. The main audience and beneficiaries are SPAC Alliance and Calypso Networks Association. The value of the demo is the bridge it creates between mobility credentials and access-control infrastructures.

## Demonstration Scope

This code is a proof-of-concept demonstrator for a controlled event setup. It is designed to support a specific narrative at MOBCO 2026:

- using a Calypso card in an access-control interaction;
- checking that the card is genuine in the context of the demo;
- matching the card serial number against an authorized list;
- optionally triggering a local action when access is accepted;
- using PC/SC communication with a compatible contactless reader.

The current code lives mainly under `calypso-pki/`. It includes a command-line demonstration script, PC/SC reader handling, Calypso PKI-related logic and simple access-control callbacks.

## Not A Product, Not A SDK

This repository is published for transparency, traceability and demonstration support only.

It is not intended to be forked, reused, repackaged, integrated into another product or treated as a reference implementation. It is not a generic Calypso library, not an access-control SDK, not a security product and not a certification-ready implementation.

The code may contain assumptions that only make sense for the MOBCO 2026 booth setup, selected cards, selected readers, local scripts, local keys, lab conditions or a specific demonstration flow. It is provided as-is, with no support commitment, no maintenance commitment and no compatibility promise.

If you are interested in a real-world deployment, use this repository only as a conversation starter. Contact the relevant organizations and technology providers instead of building from this code.

## Repository Layout

- `calypso-pki/`: Python proof-of-concept code used by the demonstrator.
- `LICENSE.txt`: legal license attached to the published source code.
- `.gitignore`: local build and Python cache exclusions.

## Related Organizations

- [Calypso Networks Association](https://calypsonet.org/) brings the transport, mobility and services community together around open contactless ticketing standards.
- [SPAC Alliance](https://spac-alliance.org/) promotes smart physical access control, security standards and certification.
- [MOBCO](https://mobco-expo.com/) is the mobility event where this demonstrator is intended to be shown in 2026.
- [STid](https://www.stid.com/) provides secure access-control readers, physical and mobile credentials, and related solutions.
- [SpringCard](https://www.springcard.com/) designs RFID/NFC readers and contactless solutions.

## Status

Demo repository for MOBCO 2026. No roadmap, no public support policy, no contribution process.
