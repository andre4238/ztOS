#!/bin/bash
# Boots a kernel on the Galaxy S10 from RAM through our U-Boot's fastboot,
# nothing is written to the UFS.
#
#   fastboot-boot.sh <Image> <dtb> <initramfs.cpio.gz> ["extra kernel args"]
#
# The phone must be in "Enter Fastboot Mode" of the U-Boot menu (after a reset
# with the cable in, unplug and plug the cable once). Needs fastboot oem run.
#
# Addresses lie in the largest free block of the first RAM bank, as U-Boot's
# lmb shows it (bdinfo): 0x98200000-0xbaafffff. Below it are no-map regions the
# boot loader keeps (0x87000000-0x871fffff, 0x91200000, 0x96000000-0x981fffff);
# a copy into one of them hangs U-Boot. The fastboot buffer is 0xd8000000.
set -euo pipefail
IMAGE=$1
DTB=$2
INITRD=$3
EXTRA=${4:-}
FB=${FASTBOOT:-fastboot}

KERNEL_ADDR=0x98200000      # 2 MiB aligned, kernel + bss up to 0x9fffffff
FDT_ADDR=0xa0000000
INITRD_ADDR=0xa0200000
MAXCPUS=${MAXCPUS:-6}       # 6: A55 x4 + A75 x2; the M4 pair waits for cpufreq/thermal
ARGS="console=tty0 clk_ignore_unused pd_ignore_unused maxcpus=$MAXCPUS loglevel=7 rdinit=/init $EXTRA"

size() { stat -f %z "$1" 2>/dev/null || stat -c %s "$1"; }
hex() { printf '0x%x' "$1"; }

oem() { "$FB" oem "run:$*"; }

put() { # file address
	echo "--- $1 -> $2 ($(size "$1") bytes)"
	"$FB" stage "$1"
	oem "cp.b \${fastboot_addr_r} $2 $(hex "$(size "$1")")"
}

"$FB" devices | grep -q fastboot || { echo "no fastboot device"; exit 1; }
# U-Boot wants the initramfs with a legacy image header (no RAW_INITRD).
UINITRD=$(mktemp -t uinitrd)
trap 'rm -f "$UINITRD"' EXIT
python3 -I "$(dirname "$0")/mkuinitrd.py" "$INITRD" "$UINITRD"
put "$IMAGE" $KERNEL_ADDR
put "$DTB" $FDT_ADDR
put "$UINITRD" $INITRD_ADDR
oem "setenv bootargs $ARGS"
# Not "oem run:booti": that would leave U-Boot from inside the USB request.
# "fastboot boot" answers OKAY first and then runs fastboot_bootcmd, the way
# U-Boot means a fastboot boot to happen. The file it sends is a dummy.
oem "setenv fastboot_bootcmd booti $KERNEL_ADDR $INITRD_ADDR $FDT_ADDR"
echo "--- booti, args: $ARGS"
"$FB" boot "$DTB" || true
echo "started; watch the panel. The rescue gadget appears as 'Galaxy S10 rescue'."
