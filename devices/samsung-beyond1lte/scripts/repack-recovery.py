#!/usr/bin/env python3
"""Put U-Boot into a recovery image of the Galaxy S10 that S-Boot accepts.

S-Boot of the S10 (bootloader rev 16, Android 12) refuses to start a recovery
image without a recovery_dtbo ("[DTB] dt table header check fail", ODIN MODE
"DT Load Fail"): for RECOVERY it takes the DT overlays from the image, not from
the DTBO partition. So we take a recovery image built for this phone (LineageOS
recovery.img for beyond1lte, header v1, 9 overlays for the hw revisions) and
keep its header and recovery_dtbo; only the kernel is replaced by U-Boot and the
ramdisk by an empty one. The AVB footer is added afterwards with avbtool
(add_hash_footer, own key; an unlocked bootloader only warns about the key).

    repack-recovery.py <source recovery.img> <u-boot.bin> <out.img>

Writes the image without padding/footer; avbtool add_hash_footer does both.
"""
import argparse
import gzip
import struct

HEADER_V1_SIZE = 1648


def empty_initramfs() -> bytes:
    """A gzipped newc cpio that holds only the trailer."""
    name = b"TRAILER!!!\0"
    hdr = b"070701" + b"".join(b"%08X" % v for v in
                               (0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, len(name), 0))
    body = hdr + name
    body += b"\0" * (-len(body) % 4)
    body += b"\0" * (-len(body) % 512)
    return gzip.compress(body, mtime=0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src")
    ap.add_argument("kernel")
    ap.add_argument("out")
    a = ap.parse_args()

    d = open(a.src, "rb").read()
    if d[:8] != b"ANDROID!":
        raise SystemExit("source is not an Android boot image")
    ks, _, rs, _, ss, _, _, ps, hv = struct.unpack_from("<9I", d, 8)
    if hv != 1:
        raise SystemExit(f"header version {hv}, expected 1")
    rds, rdo = struct.unpack_from("<IQ", d, 1632)
    if not rds or d[rdo:rdo + 4] != bytes.fromhex("d7b7ab1e"):
        raise SystemExit("source has no recovery_dtbo (dt_table magic missing)")
    dtbo = d[rdo:rdo + rds]

    kernel = open(a.kernel, "rb").read()
    ramdisk = empty_initramfs()
    pg = lambda n: (n + ps - 1) // ps * ps
    pad = lambda b: b + b"\0" * (pg(len(b)) - len(b))

    hdr = bytearray(d[:ps])
    struct.pack_into("<I", hdr, 8, len(kernel))
    struct.pack_into("<I", hdr, 16, len(ramdisk))
    struct.pack_into("<I", hdr, 24, 0)                  # no second stage
    # v1 layout: cmdline 64..576, id 576..608, extra_cmdline 608..1632,
    # recovery_dtbo size/offset 1632..1644, header_size 1644..1648
    hdr[64:576] = bytes(512)                            # cmdline: U-Boot ignores it
    hdr[576:608] = bytes(32)                            # id (SHA-1), unchecked
    hdr[608:1632] = bytes(1024)                         # extra cmdline
    body = pad(kernel) + pad(ramdisk)
    struct.pack_into("<IQI", hdr, 1632, len(dtbo), ps + len(body), HEADER_V1_SIZE)
    body += pad(dtbo)

    assert len(hdr) == ps, len(hdr)
    img = bytes(hdr) + body
    assert img[ps + len(body) - len(pad(dtbo)):][:4] == bytes.fromhex("d7b7ab1e")
    open(a.out, "wb").write(img)
    print(f"{a.out}: {len(img)} bytes (kernel {len(kernel)}, ramdisk {len(ramdisk)}, "
          f"recovery_dtbo {len(dtbo)} at {ps + len(pad(kernel)) + len(pad(ramdisk))}, page {ps})")


if __name__ == "__main__":
    main()
