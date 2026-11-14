#!/bin/sh
# Packs the ztOS rescue initramfs (static busybox + init) as a gzip'ed newc cpio.
# Uses the kernel's usr/gen_init_cpio, so /dev/console can be in the archive
# without root rights (the kernel needs it before init runs).
#   build-initramfs.sh <static busybox> <gen_init_cpio> <out.cpio.gz>
set -eu
BB=$1
GEN=$2
OUT=$3
here=$(cd "$(dirname "$0")" && pwd)
list=$(mktemp)
trap 'rm -f "$list"' EXIT

cat > "$list" <<EOF
dir /dev 0755 0 0
nod /dev/console 0600 0 0 c 5 1
nod /dev/null 0666 0 0 c 1 3
nod /dev/tty1 0620 0 0 c 4 1
dir /bin 0755 0 0
dir /proc 0755 0 0
dir /sys 0755 0 0
dir /tmp 1777 0 0
dir /run 0755 0 0
file /bin/busybox $BB 0755 0 0
slink /bin/sh busybox 0777 0 0
file /init $here/init 0755 0 0
EOF

"$GEN" "$list" | gzip -9 > "$OUT"
echo "$OUT: $(wc -c < "$OUT") bytes"
