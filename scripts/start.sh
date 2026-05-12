#!/bin/bash
cd "$(dirname "$0")"
service pcscd stop
sleep 1
service pcscd start
pkill -f "mobco-calypso-pki.py" || true
sleep 1
python ../calypso-pki/mobco-calypso-pki.py -r "*Puck*00 00" -f ./authorized_cards.txt -o ./open-1.sh
python ../calypso-pki/mobco-calypso-pki.py -r "*SpringPark*00 00" -f ./authorized_cards.txt -o ./open-2.sh
python ../calypso-pki/mobco-calypso-pki.py -r "*Architect*00 00" -f ./authorized_cards.txt -o ./open-3.sh
