#!/bin/bash
cd /home/springcard/mobco-2026-calypso-demo/scripts
PIDDIR=/home/springcard/pid
mkdir -p "$PIDDIR"
LOGDIR=/home/springcard/log
mkdir -p "$LOGDIR"
systemctl stop pcscd
gpioset -c gpiochip0 -t 1s,0 21=0
sleep 3
systemctl start pcscd
sleep 1
echo "Starting Puck"
python ../calypso-pki/mobco-calypso-pki.py -r "*Puck*00 00" -p -f ./authorized_cards.txt -o ./open-1.sh >> "$LOGDIR/puck.log" 2>&1 &
echo $! > "$PIDDIR/puck.pid"
sleep 1
echo "Starting SpringPark"
python ../calypso-pki/mobco-calypso-pki.py -r "*SpringPark*00 00" -p -f ./authorized_cards.txt -o ./open-2.sh >> "$LOGDIR/springpark.log" 2>&1 &
echo $! > "$PIDDIR/springpark.pid"
sleep 1
echo "Starting Architect"
python ../calypso-pki/mobco-calypso-pki.py -r "*Architect*00 00" -p -f ./authorized_cards.txt -o ./open-3.sh >> "$LOGDIR/architect.log" 2>&1 &
echo $! > "$PIDDIR/architect.pid"
