#!/bin/bash
# Boots a kernel on the Galaxy S10 from RAM through our U-Boot's fastboot,
# nothing is written to the UFS.
#
#   fastboot-boot.sh <Image> <dtb> <initramfs.cpio.gz> ["extra kernel args"]
#
# The phone must be in "Enter Fastboot Mode" of the U-Boot menu (after a reset
# with the cable in, unplug and plug the cable once). Needs fastboot oem run.
#
# Addresses lie in the first RAM bank (0x80000000 + 0x3ab00000, the first page
# is reserved); U-Boot itself, its fastboot buffer and the framebuffer at
# 0xca000000 are all above.
set -euo pipefail
IMAGE=$1
DTB=$2
INITRD=$3
EXTRA=${4:-}
FB=${FASTBOOT:-fastboot}

KERNEL_ADDR=0x82000000      # 2 MiB aligned, room for ~110 MiB kernel + bss
FDT_ADDR=0x89000000
INITRD_ADDR=0x8a000000
ARGS="console=tty0 clk_ignore_unused pd_ignore_unused maxcpus=1 loglevel=7 rdinit=/init $EXTRA"

size() { stat -f %z "$1" 2>/dev/null || stat -c %s "$1"; }
hex() { printf '0x%x' "$1"; }

oem() { "$FB" oem "run:$*"; }

put() { # file address
	echo "--- $1 -> $2 ($(size "$1") bytes)"
	"$FB" stage "$1"
	oem "cp.b \${fastboot_addr_r} $2 $(hex "$(size "$1")")"
}

"$FB" devices | grep -q fastboot || { echo "no fastboot device"; exit 1; }
put "$IMAGE" $KERNEL_ADDR
put "$DTB" $FDT_ADDR
put "$INITRD" $INITRD_ADDR
oem "setenv bootargs $ARGS"
# Not "oem run:booti": that would leave U-Boot from inside the USB request.
# "fastboot boot" answers OKAY first and then runs fastboot_bootcmd, the way
# U-Boot means a fastboot boot to happen. The file it sends is a dummy.
oem "setenv fastboot_bootcmd booti $KERNEL_ADDR $INITRD_ADDR:$(hex "$(size "$INITRD")") $FDT_ADDR"
echo "--- booti, args: $ARGS"
"$FB" boot "$DTB" || true
echo "started; watch the panel. The rescue gadget appears as 'Galaxy S10 rescue'."
