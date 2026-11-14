#!/usr/bin/env python3
"""Run shell commands on the S10 rescue initramfs over its USB serial console.

    rescue-shell.py [--port /dev/cu.usbmodemztos_s10*] 'command; command' [...]

Each argument is sent as one line; the output until the shell is quiet again is
printed. No pyserial needed (termios only).
"""
import argparse
import glob
import os
import select
import sys
import termios
import time


def open_port(path: str) -> int:
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0                                      # iflag
    attrs[1] = 0                                      # oflag
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[3] = 0                                      # lflag: raw
    attrs[4] = attrs[5] = termios.B115200
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    return fd


def drain(fd: int, quiet: float, limit: float) -> bytes:
    out = b""
    start = last = time.time()
    while time.time() - start < limit:
        r, _, _ = select.select([fd], [], [], 0.2)
        if r:
            try:
                chunk = os.read(fd, 65536)
            except BlockingIOError:
                chunk = b""
            if chunk:
                out += chunk
                last = time.time()
        elif out and time.time() - last > quiet:
            break
        elif not out and time.time() - start > quiet * 4:
            break
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port")
    ap.add_argument("--quiet", type=float, default=1.5)
    ap.add_argument("--limit", type=float, default=60)
    ap.add_argument("cmd", nargs="+")
    a = ap.parse_args()
    port = a.port or (sorted(glob.glob("/dev/cu.usbmodemztos_s10*")) or [None])[0]
    if not port:
        sys.exit("no /dev/cu.usbmodemztos_s10* (is the rescue initramfs running?)")
    fd = open_port(port)
    os.write(fd, b"\n")
    drain(fd, 0.5, 3)
    for c in a.cmd:
        os.write(fd, c.encode() + b"\n")
        sys.stdout.write(drain(fd, a.quiet, a.limit).decode(errors="replace").replace("\r", ""))
        sys.stdout.flush()
    os.close(fd)


if __name__ == "__main__":
    main()
