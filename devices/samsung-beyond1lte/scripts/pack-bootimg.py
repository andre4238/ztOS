#!/usr/bin/env python3
"""Pack a kernel (here: U-Boot) into an Android boot image v1 for the Galaxy S10.

S-Boot of the S10 wants header version 1, a page size of 2048 bytes and the
"SEANDROIDENFORCE" trailer after the image (not part of any page). The same
format serves the boot and the recovery partition. Offsets are those of the
postmarketOS package for the Exynos 9820 phones (base 0x10000000).

    pack-bootimg.py <kernel> <out.img> [--ramdisk initramfs] [--cmdline "..."]
                    [--os-version 12.0.0] [--patch-level 2022-11]

No dependencies besides Python 3 (AOSP's mkbootimg in Ubuntu 24.04 lacks its
`gki` module and does not start).
"""
import argparse
import hashlib
import struct

PAGE = 2048
BASE = 0x10000000
KERNEL_OFFSET = 0x00008000
RAMDISK_OFFSET = 0x01000000
SECOND_OFFSET = 0xF0000000
TAGS_OFFSET = 0x00000100
HEADER_V1_SIZE = 1648
TRAILER = b"SEANDROIDENFORCE"


def os_version_field(version: str, patch: str) -> int:
    a, b, c = (int(x) for x in version.split("."))
    y, m = (int(x) for x in patch.split("-")[:2])
    return ((a << 14) | (b << 7) | c) << 11 | ((y - 2000) << 4) | m


def pad(data: bytes) -> bytes:
    return data + b"\0" * (-len(data) % PAGE)


def build(kernel: bytes, ramdisk: bytes, cmdline: str, os_version: int) -> bytes:
    second = b""
    dtbo = b""
    sha = hashlib.sha1()
    for blob in (kernel, ramdisk, second, dtbo):
        sha.update(blob)
        sha.update(struct.pack("<I", len(blob)))
    ident = sha.digest() + b"\0" * 12          # 32 bytes, SHA-1 in the first 20

    cmd = cmdline.encode()
    if len(cmd) > 512 + 1024 - 2:
        raise SystemExit("cmdline too long")
    cmd_main, cmd_extra = cmd[:511], cmd[511:]

    header = struct.pack(
        "<8s10I16s512s32s1024sIQI",
        b"ANDROID!",
        len(kernel), (BASE + KERNEL_OFFSET) & 0xFFFFFFFF,
        len(ramdisk), (BASE + RAMDISK_OFFSET) & 0xFFFFFFFF,
        len(second), (BASE + SECOND_OFFSET) & 0xFFFFFFFF,
        (BASE + TAGS_OFFSET) & 0xFFFFFFFF,
        PAGE,
        1,                      # header_version
        os_version,
        b"",                    # name
        cmd_main.ljust(512, b"\0"),
        ident,
        cmd_extra.ljust(1024, b"\0"),
        0, 0,                   # recovery_dtbo size/offset
        HEADER_V1_SIZE,
    )
    assert len(header) == HEADER_V1_SIZE, len(header)
    return pad(header) + pad(kernel) + (pad(ramdisk) if ramdisk else b"") + TRAILER


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("kernel")
    ap.add_argument("out")
    ap.add_argument("--ramdisk")
    ap.add_argument("--cmdline", default="")
    ap.add_argument("--os-version", default="12.0.0")
    ap.add_argument("--patch-level", default="2022-11")
    a = ap.parse_args()
    kernel = open(a.kernel, "rb").read()
    ramdisk = open(a.ramdisk, "rb").read() if a.ramdisk else b""
    img = build(kernel, ramdisk, a.cmdline, os_version_field(a.os_version, a.patch_level))
    with open(a.out, "wb") as f:
        f.write(img)
    print(f"{a.out}: {len(img)} bytes (kernel {len(kernel)}, ramdisk {len(ramdisk)})")


if __name__ == "__main__":
    main()
