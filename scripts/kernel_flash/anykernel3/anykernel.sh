### AnyKernel3 kernel flash
### SukiSU manual kernel for Galaxy A12/M12 (exynos850)
### built by @varifocal on GitHub Actions

### AnyKernel setup
# global properties
properties() { '
kernel.string=SukiSU manual kernel r21 for Galaxy A12/M12 (exynos850) by @varifocal
do.devicecheck=1
do.modules=0
do.systemless=0
do.cleanup=1
do.cleanuponabort=0
device.name1=a12s
device.name2=a12nsxx
device.name3=m12s
device.name4=m12nsxx
device.name5=
supported.versions=
supported.patchlevels=
supported.vendorpatchlevels=
'; } # end properties


### AnyKernel install
# boot files attributes
boot_attributes() {
set_perm_recursive 0 0 755 644 $RAMDISK/*;
set_perm_recursive 0 0 750 750 $RAMDISK/init* $RAMDISK/sbin;
} # end attributes

# boot shell variables
BLOCK=/dev/block/by-name/boot;
IS_SLOT_DEVICE=0;
RAMDISK_COMPRESSION=auto;
PATCH_VBMETA_FLAG=auto;

# import functions/variables and setup patching - see for reference (DO NOT REMOVE)
. tools/ak3-core.sh;

ui_print " ";
ui_print "================================================";
ui_print "  SukiSU r21-manual kernel  ::  Galaxy A12 / M12";
ui_print "  4.19.148-suki-r21-manual-varifocal";
ui_print "  kernel built by @varifocal";
ui_print "  github.com/varifocal";
ui_print "================================================";
ui_print " ";

# unpack boot (kernel + ramdisk; AK3 handles the v2 dtb section itself)
dump_boot;

# inject the new kernel Image from the zip root and repack boot
write_boot;

# flash stock dtb partition dump (bundled as dtb_partition.img so AK3
# does not mistake it for the boot image's own dtb section)
ui_print "Flashing dtb partition (stock verified dump)...";
if [ -f "$AKHOME/dtb_partition.img" ]; then
  dd if="$AKHOME/dtb_partition.img" of=/dev/block/by-name/dtb bs=4096;
  sync;
  ui_print "dtb partition flashed OK (md5 96995b58...).";
else
  ui_print "! dtb_partition.img missing from zip - dtb not flashed";
fi
ui_print " ";
ui_print "  Done - kernel by @varifocal. Rebooting recommended.";
ui_print " ";
## end boot install
