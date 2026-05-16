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

## Read-only microSD for power safety

The goal is simple: keep the whole microSD card read-only during normal operation, without overlayfs and without persistent logs. Runtime files and logs stay writable only in RAM, so the system and the demo can still run normally.

This is intentionally brutal. It lacks the finesse of a clean overlayfs or a service-by-service hardening profile, but for this demo appliance the end justifies the means: the system must tolerate sudden power loss, and there is no need to preserve local runtime state.

### 1. Prepare volatile writable directories

Make sure `/tmp`, `/var/tmp`, and `/var/log` are RAM-backed. This avoids boot or service failures caused by software trying to write temporary files or logs while the microSD is read-only.

Edit `/etc/fstab`:

```sh
sudo vim /etc/fstab
```

Add these lines:

```fstab
tmpfs /tmp     tmpfs defaults,noatime,nosuid,nodev,mode=1777,size=256M 0 0
tmpfs /var/tmp tmpfs defaults,noatime,nosuid,nodev,mode=1777,size=128M 0 0
tmpfs /var/log tmpfs defaults,noatime,nosuid,nodev,mode=0755,size=128M 0 0
```

This is not persistent logging: logs disappear at reboot. It only keeps services from failing because `/var/log` is not writable.

Configure systemd-journald for volatile logs:

```sh
sudo mkdir -p /etc/systemd/journald.conf.d
sudo tee /etc/systemd/journald.conf.d/volatile.conf >/dev/null <<'EOF'
[Journal]
Storage=volatile
RuntimeMaxUse=64M
EOF
```

If `rsyslog` is installed, either leave it writing into the RAM-backed `/var/log`, or disable it if journald is enough:

```sh
sudo systemctl disable --now rsyslog 2>/dev/null || true
```

The demo scripts already write their own logs under `/tmp/springcard/log`, which remains writable because `/tmp` is a tmpfs.

### 2. Disable boot-time writers

Disable provisioning and resize services that may try to modify the filesystem during boot. They are useful on a freshly imaged Raspberry Pi, but not on a finalized demo image:

```sh
sudo touch /etc/cloud/cloud-init.disabled
sudo systemctl disable cloud-init-local cloud-init cloud-config cloud-final 2>/dev/null || true

sudo systemctl disable --now rpi-resize-var-swap-service 2>/dev/null || true
sudo systemctl mask rpi-resize-var-swap-service 2>/dev/null || true
```

Disable user/session services that are not needed for the demo and can keep files open or write state:

```sh
systemctl --user disable rpi-connect.service 2>/dev/null || true
sudo systemctl disable bluetooth 2>/dev/null || true
```

Disable file-backed swap if present. It is fine if `dphys-swapfile` is not installed:

```sh
sudo dphys-swapfile swapoff 2>/dev/null || true
sudo dphys-swapfile uninstall 2>/dev/null || true
sudo systemctl disable dphys-swapfile 2>/dev/null || true
```

Detach a stale `/var/swap` loop device if one exists:

```sh
losetup -j /var/swap
sudo losetup -d /dev/loop0 2>/dev/null || true
```

Check swap status:

```sh
free -h
swapon --show
```

`/dev/zram0` is acceptable: it is compressed swap in RAM and does not write to the microSD. Avoid `/swapfile`, `/var/swap`, or any swap partition on the microSD.

### 3. Mount the microSD partitions read-only

Edit `/etc/fstab` again and add `ro` to the mount options of the microSD partitions, at least `/` and `/boot/firmware`.

Typical example before:

```fstab
PARTUUID=xxxxxxxx-02 /               ext4 defaults,noatime 0 1
PARTUUID=xxxxxxxx-01 /boot/firmware  vfat defaults          0 2
```

After:

```fstab
PARTUUID=xxxxxxxx-02 /               ext4 ro,defaults,noatime 0 1
PARTUUID=xxxxxxxx-01 /boot/firmware  vfat ro,defaults          0 2
```

Also force the root filesystem to start read-only from the kernel command line:

```sh
sudo vim /boot/firmware/cmdline.txt
```

Keep everything on a single line and add `ro` near the end if it is not already present:

```text
console=serial0,115200 console=tty1 root=PARTUUID=... ro
```

Reboot:

```sh
sudo reboot
```

Verify:

```sh
findmnt -no TARGET,OPTIONS / /boot/firmware /tmp /var/log
```

Expected result:

- `/` contains `ro`
- `/boot/firmware` contains `ro`
- `/tmp` and `/var/log` are `tmpfs` and writable

### 4. Maintenance mode

For maintenance, remount the microSD partitions read/write:

```sh
sudo mount -o remount,rw /
sudo mount -o remount,rw /boot/firmware
```

Make your changes, install packages, edit configuration, or update the project. Then flush writes and return to read-only mode:

```sh
sync
sudo mount -o remount,ro /boot/firmware
sudo mount -o remount,ro /
```

If a process still has a writable file open on `/`, the remount may fail with `busy`. In that case, reboot after maintenance:

```sh
sudo reboot
```

After reboot, verify again:

```sh
findmnt -no TARGET,OPTIONS / /boot/firmware /tmp /var/log
```

### 5. If remounting `/` as read-only fails

If this command fails with `mount point is busy`:

```sh
sudo mount -o remount,ro /
```

look for write-open files and stale loop devices:

```sh
sudo lsof -nP +f -- / | awk 'NR==1 || $4 ~ /[0-9]+[uw]/ || $4 ~ /DEL/ {print}'
losetup -a
sudo dmesg -T | tail -40
```

Known culprits on Raspberry Pi OS include:

- `/var/swap` attached through `/dev/loop0`
- `cloud-init-*` services
- `rpi-resize-var-swap-service`
- `rpi-connect.service`
- `bluetooth.service`
- a user `systemd --user` session keeping `/usr/lib/systemd/systemd-executor` open

Useful recovery commands:

```sh
sudo losetup -d /dev/loop0 2>/dev/null || true
systemctl --user exit
sudo systemctl daemon-reexec
sync
sudo mount -o remount,ro /
```

If the live remount remains blocked by PID 1, do not spend too much time on it. Booting directly with `/` configured as `ro` is the real target state; use `journalctl -b` and `systemctl --failed` after that boot to diagnose any remaining service failure.
