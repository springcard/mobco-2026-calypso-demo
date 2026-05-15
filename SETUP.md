# Installing prerequisites

## Development tools and libraries

sudo apt update
sudo apt install vim acl cmake autoconf automake libtool pkg-config build-essential libpcsclite-dev libusb-1.0-0-dev pcscd pcsc-tools libccid

## Allow user to use PC/SC

If `pcsc_scan` works as root but reports `SCardEstablishContext: Access denied` for your normal user, the access policy shall be corrected.

1. Check the PC/SC socket permissions

```sh
getfacl /run/pcscd /run/pcscd/pcscd.comm
```

Typical output may show that the socket is already writable by all users:

```text
# file: run/pcscd
# owner: root
# group: root
user::rwx
group::r-x
other::r-x

# file: run/pcscd/pcscd.comm
# owner: root
# group: root
user::rw-
group::rw-
other::rw-
```

If the socket permissions look correct but access is still denied, the issue is likely not a Unix file permission problem.

2. Check the polkit policy

```sh
cat /usr/share/polkit-1/actions/org.debian.pcsc-lite.policy
```

The default policy may contain:

```xml
<action id="org.debian.pcsc-lite.access_pcsc">
  <defaults>
    <allow_any>no</allow_any>
    <allow_inactive>no</allow_inactive>
    <allow_active>yes</allow_active>
  </defaults>
</action>

<action id="org.debian.pcsc-lite.access_card">
  <defaults>
    <allow_any>no</allow_any>
    <allow_inactive>no</allow_inactive>
    <allow_active>yes</allow_active>
  </defaults>
</action>
```

This means PC/SC access is only allowed from an active local login session.

This can fail in cases such as:

- SSH sessions without a proper logind session
- su / sudo -u shells
- systemd services
- containers
- headless or minimal environments

You can check whether the current shell belongs to a known session with:

```sh
loginctl session-status "$XDG_SESSION_ID"
```

If this returns:

```text
Failed to get path for session '': Caller does not belong to any known session.
```

then polkit will not consider the process as an active local user session.

Quick workaround: allow PC/SC through polkit

Create a local polkit rule:

```sh
sudo tee /etc/polkit-1/rules.d/49-pcsc-lite.rules >/dev/null <<'EOF'
polkit.addRule(function(action, subject) {
    if (action.id == "org.debian.pcsc-lite.access_pcsc" ||
        action.id == "org.debian.pcsc-lite.access_card") {
        return polkit.Result.YES;
    }
});
EOF
```

Then reload/restart the relevant services:

```sh
sudo systemctl restart polkit
sudo systemctl restart pcscd.socket pcscd
```

If needed:

```sh
sudo systemctl daemon-reload
sudo systemctl restart pcscd.service
```

Then test again:

```sh
pcsc_scan
```

## Enable SCardControl for CCID (USB) PC/SC readers

On Raspberry Pi OS / Debian, for CCID readers using pcsc-lite + libccid, SCardControl() for CCID escape commands is disabled by default. Let's enable it.

### Long version

Edit the CCID driver config:

```sh
sudo vim /usr/lib/pcsc/drivers/ifd-ccid.bundle/Contents/Info.plist
```

Find:

```xml
<key>ifdDriverOptions</key>
<string>0x0000</string>
```

Change it to:

```xml
<key>ifdDriverOptions</key>
<string>0x0001</string>
```

Then restart PC/SC:

```sh
sudo systemctl restart pcscd
```

### Short version

```sh
sudo perl -0pi.bak -e 's#(<key>ifdDriverOptions</key>\s*<string>)0x0000(</string>)#$1 0x0001 $2#x; s#<string>\s*0x0001\s*</string>#<string>0x0001</string>#' /usr/lib/pcsc/drivers/ifd-ccid.bundle/Contents/Info.plist && sudo systemctl restart pcscd.socket
```

## `springcard-ccid-tcp`

This project is a PC/SC-Lite network IFD handler based on the CCID driver for SpringCard network readers. SpringCard provides no binary packages, so build from source.

Clone the repository:

```
mkdir -p ~/src
cd ~/src

git clone https://github.com/springcard/springcard-ccid-tcp.git
cd springcard-ccid-tcp
```

Prepare the build:

```
autoreconf -fi
./configure
```

Build and install:

```
make V=1 -j1
sudo make install
```

Find the installed library:

```
sudo find /usr /usr/local -name '*springcard*tcp*' -o -name '*ccid*tcp*'
```

## Configure a SpringCard TCP reader

Create or edit a configuration file under `/etc/reader.conf.d/` that provides a `FRIENDLYNAME`, `DEVICENAME`, and `LIBPATH`.

Example:

```
sudo vim /etc/reader.conf.d/springpark.cfg
```

Sample content:

```
FRIENDLYNAME "SpringCard SpringPark"
DEVICENAME 192.168.0.101:3999:00:nokey
LIBPATH /usr/lib/pcsc/drivers/ifd-springcard-ccid-tcp.bundle/Contents/Linux/libspringcard_ccid_tcp.so
CHANNELID 1
```

Adjust the values for your setup:

- `DEVICENAME`: reader IP, usually port `3999`
- `LIBPATH`: path returned by `find`

Restart pcscd:

```
sudo systemctl restart pcscd
```

Debug test:

```
sudo systemctl stop pcscd
sudo pcscd --foreground --debug --apdu
```

In another terminal:

```
pcsc_scan
```

The driver debug output follows `pcscd`: it appears on stdout when `pcscd` runs in the foreground, otherwise it goes to syslog.

### `sscp-host`

#### Build

This is not strictly required if `ifd-sscp` already includes `sscp-host` as a subdirectory, but it is useful to validate the library and build the test tools.

```
cd ~/src
git clone https://github.com/springcard/sscp-host.git
cd sscp-host

mkdir -p build
cd build

cmake ..
make -j1
```

You should get at least:

```
ls -l libsscp-host.a sscp-test sscp-tool
```

The `sscp-host` README follows the same flow: `git clone`, `mkdir build`, `cmake ..`, `make`.

#### Allow serial port access

Add your user to the serial group:

```
sudo usermod -aG dialout "$USER"
```

Then log out and log back in.

Verify:

```
groups
ls -l /dev/ttyUSB0
```

#### Test

Quick test:

```
./sscp-test --help || true
./sscp-tool --help || true
```

The `|| true` prevents the shell from failing if the tool returns a non-zero exit code when asked for help.

### `ifd-sscp`

#### Build and install

The `ifd-sscp` `CMakeLists.txt` expects `sscp-host` sources in:

```
ifd-sscp/sscp-host/inc
ifd-sscp/sscp-host/src
```

So clone with submodules if available:

```
cd ~/src
git clone --recursive https://github.com/springcard/ifd-sscp.git
cd ifd-sscp
```

Check:

```
ls -l sscp-host/inc sscp-host/src
```

If `sscp-host` is empty or missing:

```
git submodule update --init --recursive
```

If the repository does not contain the submodule, copy the source manually:

```
cd ~/src/ifd-sscp
rm -rf sscp-host
git clone https://github.com/springcard/sscp-host.git sscp-host
```

Then build:

```
cd ~/src/ifd-sscp

mkdir -p build
cd build

cmake ..
make -j1
```

Install:

```
cd ~/src/ifd-sscp/build
sudo make install
```

The README says the install places the bundle in the standard PC/SC directory `/usr/lib/pcsc/drivers/`.
CMake explicitly installs `ifd-sscp.bundle` to `/usr/lib/pcsc/drivers`.

Verify:

```
find /usr/lib/pcsc/drivers -name '*ifd*' -o -name 'libifd-sscp.so'
```

You should see something like:

```
/usr/lib/pcsc/drivers/ifd-sscp.bundle/Contents/Linux/libifd-sscp.so
```

#### Configure an SSCP STid reader

Create the file:

```
sudo vim /etc/reader.conf.d/architect.cfg
```

Minimal content:

```
FRIENDLYNAME "STid Architect SSCP"
DEVICENAME /dev/ttyUSB0:address=1:bitrate=115200
LIBPATH /usr/lib/pcsc/drivers/ifd-sscp.bundle/Contents/Linux/libifd-sscp.so
```

Adjust `DEVICENAME` with the correct serial device:

```
ls -l /dev/ttyUSB* /dev/ttyACM* /dev/serial/by-id/* 2>/dev/null
```

The README uses this exact pattern with `FRIENDLYNAME`, `DEVICENAME`, and `LIBPATH`.

## Using the GPIOs

```sh
sudo apt install gpiod
```

Where are the right GPIOs?

```sh
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
```

On our demo board we have 

*kuman 4 Channel Raspberry Pi Expansion Board Power Relay Board Module for Raspberry Pi 3 2 A+ B+ 2B 3B, Making Home Appliances Intelligent K82*

e.g.:

- Relay #1 = GPIO 19
- Relay #2 = GPIO 26
- Relay #3 = GPIO 20
- Relay #4 = GPIO 21

Relays are active low:

- 0 = ACTIVE
- 1 = NOT ACTIVE

## Auto-start at system boot

For a demo suitcase that must stay quick to finalize and still robust, use a simple `cron @reboot` entry for the `springcard` user. This avoids complex systemd service setup while still launching the existing `start.sh` script after boot.

### 1. Edit springcard's crontab

Run:

```
sudo -u springcard crontab -e
```

Add this line at the end:

```
@reboot /home/springcard/mobco-2026-calypso-demo/scripts/start.sh
```

Replace `/home/springcard/mobco-2026-calypso-demo/scripts/start.sh` with the real path if needed.

### 2. Make sure start.sh is executable

```
sudo chmod +x /home/springcard/mobco-2026-calypso-demo/scripts/start.sh
```

### 3. Ensure root privileges inside start.sh

Because cron will run the script as `springcard`, the script itself should use `sudo` for commands that need root, or the whole script can be executed via root cron if preferred.

If you want the script to run as root automatically, use root's crontab instead:

```
sudo crontab -e
```

Add:

```
@reboot /bin/bash /home/springcard/mobco-2026-calypso-demo/scripts/start.sh
```

This starts the script as root at boot.

### 4. Optional: wait for Eth0 before starting

If the SpringPark reader needs Eth0 before the script runs, add a small wait loop at the top of `start.sh`:

```bash
#!/bin/bash
cd "$(dirname "$0")"

for i in {1..30}; do
  if ip addr show eth0 | grep -q 'inet '; then
    break
  fi
  sleep 1
done

service pcscd stop
sleep 1
service pcscd start
pkill -f "mobco-calypso-pki.py" || true
sleep 1
python ../calypso-pki/mobco-calypso-pki.py -r "*Puck*00 00" -f ./authorized_cards.txt -o ./open-1.sh
python ../calypso-pki/mobco-calypso-pki.py -r "*SpringPark*00 00" -f ./authorized_cards.txt -o ./open-2.sh
python ../calypso-pki/mobco-calypso-pki.py -r "*Architect*00 00" -f ./authorized_cards.txt -o ./open-3.sh
```

### 5. Verify the cron job

Reboot and then check the logs or process state:

```
systemctl status cron
sudo journalctl -u cron -b | tail
ps -ef | grep mobco-calypso-pki.py
```

If you used root crontab, the script will run as root and behave like a login shell launching the demo.

## Read-only Filesystem for Power Safety

Running the filesystem in read-only (ro) mode protects against data corruption from sudden power loss. This is essential for unattended embedded systems.

### 1. Mount the root filesystem as read-only

Edit the kernel boot parameters. On Raspberry Pi:

```
sudo vim /boot/firmware/cmdline.txt
```

Find the line starting with `console=` and add `ro` at the end. For example:

```
console=serial0,115200 console=tty1 root=PARTUUID=... ro
```

Then reboot:

```
sudo reboot
```

Verify the filesystem is read-only:

```
mount | grep "/ "
```

Look for `ro` in the mount options.

### 2. Create a writable overlay with overlayfs

Since some services need to write to `/run`, `/tmp`, and logs, use overlayfs to create a writable layer on top of the read-only root:

```
sudo apt install overlayroot
```

Configure overlayroot:

```
sudo vim /etc/overlayroot.conf
```

Set:

```
overlayroot="tmpfs"
```

Reboot:

```
sudo reboot
```

Verify:

```
mount | grep overlay
```

### 3. Make logs persistent (optional)

If you need to keep logs after reboot, use `systemd-journald` with a persistent directory:

```
sudo mkdir -p /var/log/journal
sudo systemctl restart systemd-journald
```

### 4. Temporary mount points for applications

Your scripts write to `/tmp` (which is writable via overlayfs). To store persistent data, use a separate writable partition:

```
sudo mkdir -p /data
sudo blkid
```

Find your data partition (e.g., `/dev/mmcblk0p3`), then add to `/etc/fstab`:

```
/dev/mmcblk0p3  /data  ext4  defaults  0  0
```

Reboot and verify:

```
mount | grep /data
```

### 5. Remount filesystem as writable temporarily (for maintenance)

If you need to make changes, remount as writable:

```
sudo mount -o remount,rw /
```

When done, remount as read-only:

```
sudo mount -o remount,ro /
```

### 6. Disable swap on read-only filesystem

Since swap can cause issues with read-only root, disable it:

```
sudo dphys-swapfile swapoff
sudo dphys-swapfile uninstall
sudo update-rc.d dphys-swapfile remove
```

Reboot and confirm:

```
free -h
```

Swap should show 0.

### 7. Cron and persistent logs

If the watchdog needs to log errors beyond `/tmp`, mount `/data` as writable and configure the service to write there:

Edit your watchdog or service to log to `/data/watchdog.log` instead of `/tmp`.

## Enhanced Robustness for Raspberry Pi 5

Beyond read-only filesystems, implement these hardening measures for maximum reliability in production.

### 1. Hardware Watchdog Timer

A hardware watchdog is more reliable than software-based monitoring because it forces a reboot if the system becomes completely unresponsive:

```
sudo apt install watchdog
```

Configure it:

```
sudo vim /etc/watchdog.conf
```

Uncomment and set:

```
watchdog_device = /dev/watchdog
watchdog-timeout = 10
interval = 5
```

Enable and start:

```
sudo systemctl enable watchdog
sudo systemctl start watchdog
```

Verify:

```
systemctl status watchdog
```

### 2. USB Autosuspend Disable

Disable power management for USB devices to prevent card readers from going to sleep:

```
sudo vim /etc/modprobe.d/usb-autosuspend.conf
```

Add:

```
options usbcore autosuspend=-1
```

Reboot or reload:

```
sudo modprobe -r usbcore
sudo modprobe usbcore
```

Verify:

```
cat /sys/module/usbcore/parameters/autosuspend
```

Should be `-1`.

### 3. Network Connectivity Check Before Service Start

Ensure Eth0 is actually up and has an IP address. Modify your systemd service:

```
sudo vim /etc/systemd/system/mobco-calypso-pki.service
```

Add an `ExecStartPre` check:

```ini
ExecStartPre=/usr/bin/test -n "$(ip addr show eth0 | grep 'inet ')"
```

Or create a custom pre-start script:

```
sudo vim /usr/local/bin/check-eth0.sh
```

Add:

```bash
#!/bin/bash
for i in {1..30}; do
  if ip addr show eth0 | grep -q 'inet '; then
    exit 0
  fi
  sleep 1
done
exit 1
```

Make it executable:

```
sudo chmod +x /usr/local/bin/check-eth0.sh
```

Then reference it in your service:

```ini
ExecStartPre=/usr/local/bin/check-eth0.sh
```

### 4. Temperature Monitoring and Thermal Throttling

Monitor CPU temperature and prevent thermal damage:

```
sudo apt install rpi-monitor
```

Or set thermal limits in `/boot/firmware/config.txt`:

```
temp_limit=85
gpu_freq=750
arm_freq=2400
```

Check current temperature:

```
vcgencmd measure_temp
```

Monitor throttling:

```
vcgencmd get_throttled
```

### 5. Power Supply Monitoring

Detect voltage sags that cause random reboots. Check CPU frequency under load:

```
watch -n 1 vcgencmd measure_clock arm
```

If frequency drops unexpectedly, the power supply may be insufficient. Look for warnings in kernel logs:

```
dmesg | grep -i voltage
dmesg | grep -i throttl
```

### 6. SD Card Health Monitoring

Detect failing storage before catastrophic failure:

```
sudo apt install smartmontools
sudo smartctl -a /dev/mmcblk0
```

Check for warnings:

```
sudo smartctl -H /dev/mmcblk0
```

Monitor periodically with a cron job:

```
sudo crontab -e
```

Add:

```
0 */6 * * * smartctl -H /dev/mmcblk0 >> /var/log/sd-health.log 2>&1
```

### 7. Service Resource Limits

Prevent runaway processes from consuming all CPU or memory:

```
sudo vim /etc/systemd/system/mobco-calypso-pki.service
```

Add to the `[Service]` section:

```ini
MemoryLimit=512M
CPUQuota=80%
TasksMax=100
```

### 8. Systemd Service Hardening

Improve security and stability by restricting service permissions:

```ini
[Service]
ProtectSystem=strict
ProtectHome=yes
NoNewPrivileges=yes
ReadWritePaths=/data /run/pcscd /tmp /var/log/journal
PrivateTmp=yes
RestrictNamespaces=yes
RestrictRealtime=yes
RestrictSUIDSGID=yes
LockPersonality=yes
MemoryDenyWriteExecute=yes
```

### 9. Remote Syslog for Persistent Logging

Send logs to a remote server so they survive SD card failure:

```
sudo apt install rsyslog
```

Configure remote destination:

```
sudo vim /etc/rsyslog.d/99-remote.conf
```

Add:

```
*.* @@remote.syslog.server:514
```

Restart:

```
sudo systemctl restart rsyslog
```

### 10. Systemd Journal Persistence

Keep recent logs even after reboots:

```
sudo mkdir -p /var/log/journal
sudo chown root:systemd-journal /var/log/journal
sudo chmod 2755 /var/log/journal
sudo systemctl restart systemd-journald
```

Query logs persistently:

```
journalctl --since "2 days ago" -u mobco-calypso-pki.service
```

### 11. Network Fallback (WiFi as Secondary)

If WiFi is available, configure it as a fallback for diagnostics/monitoring:

```
sudo vim /etc/NetworkManager/conf.d/99-wifi-fallback.conf
```

Add:

```ini
[main]
autoconnect-retries-default=3
```

### 12. Automatic Log Rotation

Prevent `/data` from filling up with logs:

```
sudo apt install logrotate
```

Create a config:

```
sudo vim /etc/logrotate.d/mobco-calypso-pki
```

Add:

```
/data/watchdog.log {
  daily
  rotate 7
  compress
  delaycompress
  missingok
  notifempty
  create 0644 root root
}
```

Test:

```
sudo logrotate -d /etc/logrotate.d/mobco-calypso-pki
```
