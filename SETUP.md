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

- #1 = GPIO17
- #2 = GPIO18
- #3 = GPIO27
- #4 = GPIO22

Relays are active low:

- 0 = ACTIVE
- 1 = NOT ACTIVE

