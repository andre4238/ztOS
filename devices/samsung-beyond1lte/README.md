# ztOS on the Samsung Galaxy S10 (SM-G973F, `beyond1lte`)

Status: **in development** – U-Boot boots from the recovery partition (2026-11-14):
boot menu on the panel, fastboot and USB mass storage over the cable. No kernel yet.

The S10 is the S10+ (`beyond2lte`) board with a smaller battery: same Exynos 9820,
same S6E3HA9 panel (1440x3040), same S2DOS05 display PMIC, same MAX77705 charger,
8 GiB of DRAM. So the port stands on the S10+ mainline work and takes features
from the S10e (`beyond0lte`) port where the S10+ does not have them yet.

| Part | Base | Here |
|---|---|---|
| Bootloader | upstream U-Boot `211de43d` + the S10+ patches of [gangg111/S10Plus_Linux](https://github.com/gangg111/S10Plus_Linux) (`patches-uboot/`) | `uboot/0001-…` adds the S10 board (device tree, defconfig) |
| Kernel | mainline + the Exynos 9820 work of [chiffathefox/exynos-9820-mainline-linux](https://github.com/chiffathefox/exynos-9820-mainline-linux) and the S10+ patches (`patches/`) | next step |
| Later | modem, cameras, always-on display, sensor hub from [pulpoff/linux-beyond0lte](https://github.com/pulpoff/linux-beyond0lte) (S10e) | |

## Boot path (safe by design)

Android stays on the phone. U-Boot goes into the **recovery** partition and loads the
ztOS kernel, initramfs and device tree from a Linux partition, like the S10e port.
Android keeps booting normally; the stock recovery comes back from the stock firmware.

## Phone used for the port

| | |
|---|---|
| Model | SM-G973F (`beyond1lte`, product `beyond1lteeea`), 8 GiB |
| Firmware | G973FXXUGHVJ5, Android 12, bootloader revision 16, CSC DBT |

## Building U-Boot

```sh
git clone https://source.denx.de/u-boot/u-boot.git && cd u-boot
git checkout 211de43d0f954a00a490220c1aac9db298287c40
git am /path/to/S10Plus_Linux/patches-uboot/0*.patch
git am /path/to/ztOS/devices/samsung-beyond1lte/uboot/0*.patch
make O=out exynos9820-beyond1lte_defconfig && make O=out -j$(nproc)
```

## Flashing

- Use `samloader-rs` (topjohnwu) or heimdall natively on the host; USB passthrough in a VM
  (Parallels) fails at the PIT transfer.
- S-Boot needs two things in a recovery image (header v1, page 2048):
  a `recovery_dtbo` (otherwise `[DTB] dt table header check fail`, ODIN MODE "DT Load
  Fail") and a valid AVB hash footer (otherwise "AVB Fail"). The key may be our own;
  with an unlocked bootloader S-Boot only warns that it does not match the chain
  descriptor. So:
  ```sh
  scripts/repack-recovery.py lineage-recovery.img u-boot.bin recovery-uboot.img
  avbtool add_hash_footer --image recovery-uboot.img --partition_name recovery \
      --partition_size $((16512*4096)) --algorithm SHA256_RSA4096 --key own.pem \
      --rollback_index 1
  ```
  The LineageOS `recovery.img` for beyond1lte provides header and `recovery_dtbo`.
- Once U-Boot runs, `fastboot flash recovery …` from its menu replaces download mode.
  After a reset with the cable in, unplug and plug the cable once so the host sees it.
- Backup: menu entry "USB mass storage" exports UFS LUN 0 (all 31 partitions).
- Download mode must show `KG STATE: Completed` (or Checking). With `Prenormal`, S-Boot
  refuses every unofficial binary at the end of the session ("Only official released
  binaries are allowed to be flashed (RECOVERY)", Odin `FAIL!`) even with `OEM LOCK: OFF (U)`.
  Prenormal goes away once the phone has been online in Android long enough for
  KnoxGuard to check in.
- Boot straight into recovery after flashing (Vol Down + Power until black, then
  Vol Up + Bixby + Power with USB connected); Android puts the stock recovery back otherwise.

## Next steps

1. Stock firmware G973FXXUGHVJ5 at hand (restore path), backup of the stock recovery.
2. Check the device tree against the phone (`/proc/device-tree`: memory, framebuffer,
   reserved regions) – lines marked `TODO(S10)`.
3. Kernel: S10+ patches, `exynos9820-beyond1lte.dts`, boot to the initramfs rescue
   shell over USB networking.
4. U-Boot packed as recovery image, first boot.
5. ztOS device layer (`layer.sh`, overlay, ztOSIAL backends) and the GSI.

## License

U-Boot and kernel changes: GPL-2.0 (device trees GPL-2.0 OR BSD-3-Clause), as their
upstreams. ztOS userspace: GPL-3.0-or-later.
