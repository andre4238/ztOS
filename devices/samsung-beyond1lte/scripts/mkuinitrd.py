#!/usr/bin/env python3
"""Wrap an initramfs in a U-Boot legacy image header (type ramdisk, arm64).

Our U-Boot is built without CONFIG_SUPPORT_RAW_INITRD, so booti refuses a bare
cpio ("Wrong Ramdisk Image Format"). This is what `mkimage -A arm64 -O linux
-T ramdisk -C none` writes, without needing u-boot-tools on the host.

    mkuinitrd.py <initramfs.cpio.gz> <out.uimg>
"""
import struct
import sys
import time
import zlib

IH_MAGIC = 0x27051956
IH_OS_LINUX, IH_ARCH_ARM64, IH_TYPE_RAMDISK, IH_COMP_NONE = 5, 22, 3, 0


def main() -> None:
    src, out = sys.argv[1], sys.argv[2]
    data = open(src, "rb").read()
    name = b"ztOS rescue initramfs".ljust(32, b"\0")

    def header(hcrc: int) -> bytes:
        return struct.pack(">IIIIIIIBBBB32s", IH_MAGIC, hcrc, int(time.time()),
                           len(data), 0, 0, zlib.crc32(data) & 0xFFFFFFFF,
                           IH_OS_LINUX, IH_ARCH_ARM64, IH_TYPE_RAMDISK,
                           IH_COMP_NONE, name)

    hdr = header(zlib.crc32(header(0)) & 0xFFFFFFFF)
    assert len(hdr) == 64
    open(out, "wb").write(hdr + data)
    print(f"{out}: {len(hdr) + len(data)} bytes (ramdisk {len(data)})")


if __name__ == "__main__":
    main()
