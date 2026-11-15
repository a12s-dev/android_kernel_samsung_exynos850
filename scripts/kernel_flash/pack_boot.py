#!/usr/bin/env python3
"""Pack a raw arm64 Image into a full boot partition image.

Layout (validated against this device's known-good dump):
  [1 page header | kernel (page-aligned) | tail: ramdisk+dtb+rest verbatim]
  tail starts at the template's original ramdisk offset (old kernel end),
  moved down to follow the new kernel so the bootloader's header walk
  (kernel -> ramdisk -> dtb) stays consistent. Output padded to the
  template/partition size.

Usage: pack_boot.py <Image> <boot_template.img> <out.img>
"""
import struct
import sys
import hashlib
import os


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    if len(sys.argv) != 4:
        fail("usage: pack_boot.py <Image> <boot_template.img> <out.img>")
    image_path, tpl_path, out_path = sys.argv[1:4]

    tpl = open(tpl_path, "rb").read()
    if tpl[:8] != b"ANDROID!":
        fail("template is not an ANDROID! boot image")
    page = struct.unpack_from("<I", tpl, 36)[0]
    if page == 0 or page > 16384 or (page & (page - 1)):
        fail(f"bad page size {page}")

    ks, _, rs, *_ = struct.unpack_from("<10I", tpl, 8)
    ram_off_old = (page + ks + page - 1) // page * page
    tail = tpl[ram_off_old:]
    if tail[:3] != b"\x1f\x8b\x08":
        fail("template ramdisk is not gzip at expected offset")

    newk = open(image_path, "rb").read()
    if newk[0x38:0x3C] != b"ARM\x64":
        fail("Image lacks arm64 ARM\\x64 magic (not a raw Image?)")

    hdr = bytearray(tpl[:page])
    struct.pack_into("<I", hdr, 8, len(newk))
    out = bytes(hdr) + newk
    # ramdisk must start at align(page + kernel_size), zero-pad if needed
    out += b"\x00" * ((-len(out)) % page)
    out += tail
    if len(out) < len(tpl):
        out += b"\x00" * (len(tpl) - len(out))
    if len(out) != len(tpl):
        fail(f"size mismatch {len(out)} != {len(tpl)}")

    # header-walk validation: ramdisk gzip at align(page+kernel_size),
    # FDT exactly 0x40 after the ramdisk region
    rw = page + len(newk)
    rw = (rw + page - 1) // page * page
    if out[rw : rw + 3] != b"\x1f\x8b\x08":
        fail("gzip ramdisk not at header-walk offset")
    rend = rw + (rs + page - 1) // page * page
    fdt = out.find(b"\xd0\x0d\xfe\xed")
    if fdt != rend + 0x40:
        fail(f"FDT at {fdt:#x}, expected {rend + 0x40:#x}")

    open(out_path, "wb").write(out)
    print(f"OK {out_path} size={len(out)}")
    print(f"kernel_size={len(newk)} md5={hashlib.md5(out).hexdigest()}")


if __name__ == "__main__":
    main()
