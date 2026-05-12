#!/bin/bash

CHIP=gpiochip0
GPIOS="4 5 6 7 8 9 10 11 12 13 16 17 18 19 20 21 22 23 24 25 26 27"

for g in $GPIOS
do
  echo "Test GPIO $g"
  
  # 0 during 1s, then wait 1 before next
  gpioset -c $CHIP -t 1s,0 $g=0
  
  sleep 1
done
