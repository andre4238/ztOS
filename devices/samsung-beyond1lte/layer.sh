# The Galaxy S10 (beyond1lte) device layer, run by the installer inside the
# build namespace after the GSI part, with $R (the root), $DEVSRC (this folder:
# vendor/, overlay/, packages.txt), $DEVROOT (the repository), step and ch.
#
# Bring-up state (2026-11): the kernel is ours (mainline 7.2 + S10Plus_Linux,
# booted by U-Boot from the recovery partition, not a package), the panel runs
# on the boot loader's framebuffer (simpledrm) and there is no GPU driver yet,
# so the session draws with software OpenGL. No modem, audio, sensors or Wi-Fi
# firmware yet: the manifest names none of them and ztOS hides what is absent.
D=$DEVSRC

step "adding the Galaxy S10 device layer"
install -d "$R/vendor/ztos"
cp -a "$D/vendor/ztos/." "$R/vendor/ztos/"
chown -R 0:0 "$R/vendor"
cp -a "$D/overlay/." "$R/"

# The root is found by its label (initramfs: findfs LABEL=ZR_ARCH), on USERDATA.
cat > "$R/etc/fstab" <<'FSTAB'
# ztOS on the Galaxy S10: the system lives on USERDATA (UFS LUN 0)
LABEL=ZR_ARCH  /  ext4  rw,relatime  0 1
FSTAB

# The generic USB link (rootfs/overlay) names the phone; say which one it is.
sed -i -e 's/Galaxy S9 Arch Linux ARM/Galaxy S10 ztOS/' -e 's/"starlte"/"beyond1lte"/' \
	"$R/usr/local/sbin/zboot-usb-gadget"

# Every phone gets the first-boot growth of the root; nothing from the S9 here.
touch "$R/etc/zboot-firstboot"
chmod 755 "$R"/usr/local/sbin/* 2>/dev/null || true

DEVICE_UNITS="zboot-usb-gadget zboot-firstboot sshd ztos-s10-firmware"
