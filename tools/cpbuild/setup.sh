#!/bin/bash
# One-time setup of the CircuitPython build in WSL Ubuntu-24.04 (run as root):
#   wsl -d Ubuntu-24.04 -u root -- bash "/mnt/c/PATH/TO/THE/PROJECT/tools/cpbuild/setup.sh"
# Source in /opt/cp (the Linux disk: building on /mnt/c is very slow). Version: CP_TAG.
set -euo pipefail
CP_TAG=10.3.2
TC=arm-gnu-toolchain-15.2.rel1-x86_64-arm-none-eabi
export DEBIAN_FRONTEND=noninteractive

echo "== packages"
apt-get update -q
apt-get install -y -q build-essential git gettext uncrustify python3 python3-venv python3-pip cmake ninja-build xz-utils curl pkg-config libffi-dev

echo "== arm toolchain"
if [ ! -x /opt/$TC/bin/arm-none-eabi-gcc ]; then
    curl -sSL "https://developer.arm.com/-/media/Files/downloads/gnu/15.2.rel1/binrel/$TC.tar.xz" -o /tmp/tc.tar.xz
    tar -xf /tmp/tc.tar.xz -C /opt
    rm /tmp/tc.tar.xz
fi
export PATH=/opt/$TC/bin:$PATH
arm-none-eabi-gcc --version | head -1

echo "== circuitpython $CP_TAG"
if [ ! -d /opt/cp/.git ]; then
    git clone --depth 1 --branch $CP_TAG https://github.com/adafruit/circuitpython.git /opt/cp
fi
cd /opt/cp
python3 -m venv /opt/cpvenv
. /opt/cpvenv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements-dev.txt
make -C ports/raspberrypi fetch-port-submodules
make -C mpy-cross -j"$(nproc)"

echo "== stock YD-RP2040 build (proves the setup)"
make -C ports/raspberrypi BOARD=vcc_gnd_yd_rp2040 -j"$(nproc)"
ls -l ports/raspberrypi/build-vcc_gnd_yd_rp2040/firmware.uf2
echo "SETUP DONE"
