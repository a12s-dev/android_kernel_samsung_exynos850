#!/usr/bin/env python3
"""Assemble the TWRP-flashable AnyKernel3 zip.

Takes the committed anykernel3/ template (anykernel.sh, tools, META-INF,
dtb_partition.img) and injects the freshly built kernel Image.

Usage: make_zip.py <anykernel3_dir> <Image> <out.zip>
"""
import hashlib
import os
import sys
import zipfile


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    if len(sys.argv) != 4:
        fail("usage: make_zip.py <anykernel3_dir> <Image> <out.zip>")
    src, image_path, out_path = sys.argv[1:4]

    if not os.path.isfile(os.path.join(src, "anykernel.sh")):
        fail(f"{src}: anykernel.sh missing")
    if not os.path.isfile(os.path.join(src, "META-INF/com/google/android/update-binary")):
        fail(f"{src}: update-binary missing")
    if not os.path.isfile(os.path.join(src, "dtb_partition.img")):
        fail(f"{src}: dtb_partition.img missing")

    if os.path.exists(out_path):
        os.remove(out_path)

    skip_names = {"README.md", "LICENSE", ".git"}
    skip_dirs = {".github", ".git"}
    n = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for root, dirs, files in os.walk(src):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for f in files:
                if f in skip_names:
                    continue
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, src))
                n += 1
        z.write(image_path, "Image")
        n += 1

    with zipfile.ZipFile(out_path) as z:
        bad = z.testzip()
        if bad:
            fail(f"corrupt entry {bad}")
        names = set(z.namelist())
        for req in ("Image", "anykernel.sh", "dtb_partition.img",
                    "META-INF/com/google/android/update-binary",
                    "tools/ak3-core.sh"):
            if req not in names:
                fail(f"zip missing {req}")

    md5 = hashlib.md5(open(out_path, "rb").read()).hexdigest()
    print(f"OK {out_path} files={n} size={os.path.getsize(out_path)} md5={md5}")


if __name__ == "__main__":
    main()
