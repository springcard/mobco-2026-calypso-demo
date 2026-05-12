#!/bin/bash
cd "$(dirname "$0")"
pkill -f "mobco-calypso-pki.py" || true
sleep 1
service pcscd stop
