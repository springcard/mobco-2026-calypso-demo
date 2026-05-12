#!/bin/bash
cd "$(dirname "$0")"

# Configuration
READERS=("*Puck*00 00" "*SpringPark*00 00" "*Architect*00 00")
OUTPUT_FILES=("./open-1.sh" "./open-2.sh" "./open-3.sh")
AUTHORIZED_CARDS="./authorized_cards.txt"
LOG_FILE="/tmp/watchdog.log"
CHECK_INTERVAL=30

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

check_readers() {
    local pcsc_output
    pcsc_output=$(pcsc_scan -n 1 2>/dev/null | grep -E "Reader|Device" || true)
    
    for reader in "${READERS[@]}"; do
        if ! echo "$pcsc_output" | grep -q "$(echo "$reader" | sed 's/\*//g')"; then
            log "ERROR: Reader '$reader' not found in PC/SC"
            return 1
        fi
    done
    
    log "OK: All 3 readers detected on PC/SC"
    return 0
}

check_output_files() {
    for file in "${OUTPUT_FILES[@]}"; do
        if [ ! -f "$file" ]; then
            log "ERROR: Output file not found: $file"
            return 1
        fi
    done
    
    log "OK: All output files present"
    return 0
}

check_scripts_running() {
    local count
    count=$(pgrep -f "mobco-calypso-pki.py" | wc -l)
    
    if [ "$count" -eq 0 ]; then
        log "ERROR: No mobco-calypso-pki.py processes running"
        return 1
    fi
    
    log "OK: $count mobco-calypso-pki.py processes running"
    return 0
}

restart_services() {
    log "RESTART: Stopping all services..."
    bash ./stop.sh
    sleep 2
    
    log "RESTART: Starting services..."
    bash ./start.sh
    sleep 3
    
    log "RESTART: Services restarted"
}

main() {
    log "Watchdog started, checking every ${CHECK_INTERVAL}s"
    
    while true; do
        if ! check_readers || ! check_output_files || ! check_scripts_running; then
            log "ALERT: Problem detected, triggering restart..."
            restart_services
        fi
        
        sleep "$CHECK_INTERVAL"
    done
}

main
