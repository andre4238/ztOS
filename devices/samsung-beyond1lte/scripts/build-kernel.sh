#!/bin/bash
# Builds the Galaxy S10 kernel: mainline v7.2.0 + the S10Plus_Linux series +
# our beyond1lte device tree, configured from arm64 defconfig + the S10+
# fragments + ztos-rescue.config (panfrost, USB gadget, UFS, ... built in).
#
#   build-kernel.sh <S10Plus_Linux checkout> [work dir]
#
# Output: <work>/linux/out-s10/arch/arm64/boot/Image and
#         .../dts/exynos/exynos9820-beyond1lte.dtb
# Natively on arm64 (no cross compiler needed); elsewhere set
# CROSS_COMPILE=aarch64-linux-gnu- and ARCH=arm64.
#
# 2026-11: built in an Ubuntu 24.04 arm64 VM with 6 cores / 8 GB; with 3 GB the
# VM ran out of memory at -j3.
set -euo pipefail
S10P=$(cd "$1" && pwd)
WORK=${2:-$PWD/kernel-build}
HERE=$(cd "$(dirname "$0")/.." && pwd)
BASE=1200d84f4c0a929a0780180d25063d93773be79c        # v7.2.0, the series' base
export ARCH=${ARCH:-arm64}

mkdir -p "$WORK"
cd "$WORK"
if [ ! -d linux/.git ]; then
	git init -q linux
	git -C linux remote add origin https://github.com/torvalds/linux.git
	git -C linux fetch -q --depth 1 origin "$BASE"
	git -C linux checkout -q -b s10 FETCH_HEAD
	git -C linux -c user.name="ztOS build" -c user.email="build@localhost" \
		am -q --3way "$S10P"/patches/0*.patch
	# ours on top: the cameras from the S10e port (+ CMU_ISPPRE), ...
	git -C linux -c user.name="ztOS build" -c user.email="build@localhost" \
		am -q --3way "$HERE"/kernel/0*.patch
fi
cd linux

# the S10 device tree, next to the S10+ one it includes
install -m644 "$HERE/exynos9820-beyond1lte.dts" "$HERE/exynos9820-camera.dtsi" \
	"$HERE/exynos9820-beyond1lte-camera.dtsi" arch/arm64/boot/dts/exynos/
grep -q "exynos9820-beyond1lte.dtb" arch/arm64/boot/dts/exynos/Makefile ||
	sed -i 's/^\texynos9820-beyond2lte.dtb\t\\$/\texynos9820-beyond1lte.dtb\t\\\n&/' \
		arch/arm64/boot/dts/exynos/Makefile

make O=out-s10 defconfig > /dev/null
scripts/kconfig/merge_config.sh -m -O out-s10 out-s10/.config \
	"$S10P/scripts/exynos9820.config" "$S10P/scripts/bringup.config" \
	"$HERE/ztos-rescue.config" > /dev/null
make O=out-s10 olddefconfig > /dev/null
for s in DRM_PANFROST USB_CONFIGFS_NCM SCSI_UFS_EXYNOS DRM_SIMPLEDRM; do
	grep -q "^CONFIG_$s=y" out-s10/.config || { echo "CONFIG_$s is not =y" >&2; exit 1; }
done

make O=out-s10 -j"$(nproc)" Image dtbs
ls -l out-s10/arch/arm64/boot/Image out-s10/arch/arm64/boot/dts/exynos/exynos9820-beyond1lte.dtb
