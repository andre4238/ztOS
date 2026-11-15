# ztOS on the Samsung Galaxy S10 (SM-G973F, `beyond1lte`)

Status: **in development**. 2026-11-14: U-Boot boots from the recovery partition (menu,
fastboot, USB mass storage), and Linux 7.2 boots from RAM into the rescue initramfs:
console on the panel (simpledrm), UFS, USB gadget (serial + network). Boot log in
`logs/`.

| Part | State on the S10 |
|---|---|
| U-Boot (recovery partition) | runs; fastboot + USB mass storage |
| Kernel 7.2 + S10Plus_Linux patches | boots on 6 cores (`maxcpus=6`; the M4 pair fails the CTR_EL0.IDC capability check) |
| Panel | simpledrm on the S-Boot framebuffer; DSI/DECON driver not yet |
| GPU (Mali-G76 MP12) | panfrost, ztMETRO renders on it (`WLR_RENDER_DRM_DEVICE`); clock left at the firmware's |
| ztOS | boots from USERDATA (`installer/ztos build --target beyond1lte`), ztMETRO runs |
| UFS | works (`sda`–`sde`) |
| USB gadget | ACM + NCM |
| Wi-Fi (BCM4375, PCIe) | found, firmware missing |
| Audio (Madera) | deferred (regulators) |
| Touchscreen (S6SY771) | works (mainline s6sy761 driver) |
| Buttons, haptics, hall sensor, headset jack | detected |

The S10 is the S10+ (`beyond2lte`) board with a smaller battery: same Exynos 9820,
same S6E3HA9 panel (1440x3040), same S2DOS05 display PMIC, same MAX77705 charger,
8 GiB of DRAM. So the port stands on the S10+ mainline work and takes features
from the S10e (`beyond0lte`) port where the S10+ does not have them yet.

| Part | Base | Here |
|---|---|---|
| Bootloader | upstream U-Boot `211de43d` + the S10+ patches of [gangg111/S10Plus_Linux](https://github.com/gangg111/S10Plus_Linux) (`patches-uboot/`) | `uboot/0001-…` adds the S10 board (device tree, defconfig) |
| Kernel | mainline v7.2.0 + the S10+ patches (`patches/`) | `scripts/build-kernel.sh`, `exynos9820-beyond1lte.dts`, `ztos-rescue.config` |
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

## How the phone boots (2026-11-15)

```
power on -> S-Boot -> misc says "boot-recovery" -> RECOVERY = our U-Boot
         -> bootcmd: load scsi 0#userdata /boot/ztos/{boot.env,Image,dtb,initrd.uimg}
         -> booti -> initramfs finds LABEL=ZR_ARCH -> systemd -> ztMETRO
```

- `boot-recovery` in misc is kept by `ztos-s10-bootmode.service`; BOOT and vbmeta
  stay Samsung's (BOOT is a hash in vbmeta, U-Boot there would fail verification).
- The kernel command line is `/boot/ztos/boot.env` (`bootargs=...`), no U-Boot rebuild.
- Menu: hold Volume Down while U-Boot starts. Recovery keys still reach U-Boot.
- Development: `printf bootonce-bootloader` into misc + reboot = U-Boot fastboot once
  (U-Boot clears it; write `boot-recovery` back with
  `fastboot oem run:bcb load scsi 0 misc` / `bcb set command boot-recovery` / `bcb store`
  before `fastboot reboot`, or let ztOS do it on its next boot).
- U-Boot reads ext4 with the generic `load`; `ext4load` is not built in.

## Booting a kernel from RAM

```sh
# phone in the U-Boot menu: "Enter Fastboot Mode", then unplug/plug the cable
scripts/fastboot-boot.sh Image exynos9820-beyond1lte.dtb initramfs.cpio.gz
scripts/rescue-shell.py 'uname -a; dmesg | tail'     # serial console over USB
```

Load addresses come from U-Boot's lmb (`bdinfo`): the boot loader keeps no-map
regions at 0x87000000, 0x91200000 and 0x96000000-0x981fffff; the kernel goes to
0x98200000. U-Boot has no RAW_INITRD, so the initramfs gets a legacy header
(`scripts/mkuinitrd.py`).

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
