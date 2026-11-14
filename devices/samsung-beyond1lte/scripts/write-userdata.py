#!/usr/bin/env python3
"""Write an Android sparse image (img2simg) to the S10's USERDATA over U-Boot's
"USB mass storage", then read it back and compare.

U-Boot's fastboot loses replies on this phone (dwc3: "request ... was not
queued to ep1in-bulk"), which is harmless for short commands and unreliable for
42 sparse pieces. USB mass storage moved the 8 GB backup without a fault, so
the system goes this way.

    sudo python3 -I write-userdata.py <root.simg> /dev/diskN
    python3 -I write-userdata.py --dry-run <root.simg>      (parse only)

The partition is found by its GPT name (userdata), never by number, and its
device size must match the GPT; the script refuses if the image does not fit.
Only that partition is written. DONT_CARE chunks are skipped (not zeroed): the
ext4 in the image does not read them.
"""
import os
import struct
import sys

SPARSE_MAGIC = 0xED26FF3A
RAW, FILL, DONT_CARE, CRC32 = 0xCAC1, 0xCAC2, 0xCAC3, 0xCAC4
CHUNK = 8 * 1024 * 1024


def device_size(fd):
    """Size of a disk device: lseek(SEEK_END) gives 0 for macOS raw disks."""
    if sys.platform == "darwin":
        import fcntl
        DKIOCGETBLOCKSIZE, DKIOCGETBLOCKCOUNT = 0x40046418, 0x40086419
        bs = struct.unpack("<I", fcntl.ioctl(fd, DKIOCGETBLOCKSIZE, b"\0" * 4))[0]
        n = struct.unpack("<Q", fcntl.ioctl(fd, DKIOCGETBLOCKCOUNT, b"\0" * 8))[0]
        return bs * n
    return os.lseek(fd, 0, os.SEEK_END)


def read_at(fd, off, size):
    os.lseek(fd, off, os.SEEK_SET)
    out = bytearray()
    while len(out) < size:
        b = os.read(fd, min(CHUNK, size - len(out)))
        if not b:
            raise IOError(f"short read at {off + len(out)}")
        out += b
    return bytes(out)


def find_userdata(disk):
    raw = disk.replace("/dev/disk", "/dev/rdisk")
    fd = os.open(raw, os.O_RDONLY)
    for sector in (4096, 512):
        hdr = read_at(fd, sector, sector)
        if hdr[:8] == b"EFI PART":
            break
    else:
        sys.exit("no GPT on " + raw)
    lba, n, esz = struct.unpack_from("<QII", hdr, 72)
    table = read_at(fd, lba * sector, -(-n * esz // sector) * sector)
    os.close(fd)
    for i in range(n):
        e = table[i * esz:(i + 1) * esz]
        if e[56:128].decode("utf-16-le").rstrip("\0") == "userdata":
            first, last = struct.unpack_from("<QQ", e, 32)
            return f"{raw}s{i + 1}", (last - first + 1) * sector
    sys.exit("no partition named userdata")


def regions(f):
    """(kind, offset, size, file position of the data or the fill pattern)"""
    f.seek(0)
    magic, major, _, fhs, chs, blk, total_blks, total_chunks, _ = struct.unpack("<IHHHHIIII", f.read(28))
    if magic != SPARSE_MAGIC or major != 1:
        sys.exit("not an Android sparse image")
    f.seek(fhs)
    pos, out = 0, []
    for _ in range(total_chunks):
        ctype, _, nblk, total = struct.unpack("<HHII", f.read(12))
        f.seek(chs - 12, 1)
        here = f.tell()
        if ctype == RAW:
            out.append(("raw", pos * blk, nblk * blk, here))
        elif ctype == FILL:
            out.append(("fill", pos * blk, nblk * blk, here))
        elif ctype not in (DONT_CARE, CRC32):
            sys.exit(f"unknown chunk type {ctype:#x}")
        f.seek(here + total - chs)
        pos += nblk
    if pos != total_blks:
        sys.exit("block count mismatch in the sparse image")
    return total_blks * blk, out


def expected(f, kind, src, off_in, n):
    if kind == "raw":
        f.seek(src + off_in)
        return f.read(n)
    f.seek(src)
    return f.read(4) * (n // 4)


def main():
    args = sys.argv[1:]
    dry = args and args[0] == "--dry-run"
    if dry:
        args = args[1:]
    simg = args[0]
    with open(simg, "rb") as f:
        size, regs = regions(f)
        data = sum(r[2] for r in regs)
        print(f"image: {size} bytes, {len(regs)} data regions, {data / 2**30:.2f} GiB to write")
        if dry:
            return
        part, part_size = find_userdata(args[1])
        print(f"userdata: {part}, {part_size} bytes")
        if size > part_size:
            sys.exit(f"image ({size}) larger than userdata ({part_size})")
        out = os.open(part, os.O_RDWR)
        have = device_size(out)
        if have != part_size:
            sys.exit(f"{part} is {have} bytes, the GPT says {part_size}: refusing")

        done = 0
        for kind, off, n, src in regs:
            os.lseek(out, off, os.SEEK_SET)
            for o in range(0, n, CHUNK):
                b = expected(f, kind, src, o, min(CHUNK, n - o))
                os.write(out, b)
                done += len(b)
                print(f"\r  written  {done / 2**30:6.2f} / {data / 2**30:.2f} GiB", end="", flush=True)
        os.fsync(out)
        print()

        done, bad = 0, 0
        for kind, off, n, src in regs:
            for o in range(0, n, CHUNK):
                m = min(CHUNK, n - o)
                if read_at(out, off + o, m) != expected(f, kind, src, o, m):
                    bad += 1
                done += m
                print(f"\r  verified {done / 2**30:6.2f} / {data / 2**30:.2f} GiB", end="", flush=True)
        print()
        os.close(out)
    if bad:
        sys.exit(f"VERIFY FAILED: {bad} pieces differ")
    print(f"ok: written to {part} and verified")


if __name__ == "__main__":
    main()
