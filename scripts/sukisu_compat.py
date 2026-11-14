#!/usr/bin/env python3
"""4.19 compat fixes for SukiSU sources after setup.sh. Safe no-ops if anchors missing."""
import sys
from pathlib import Path

fixes = 0

# --- main branch: MODULE_IMPORT_NS does not exist before ~5.4 ---
p = Path("KernelSU/kernel/core/init.c")
if p.exists():
    s = p.read_text()
    old = """#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 13, 0)
MODULE_IMPORT_NS("VFS_internal_I_am_really_a_filesystem_and_am_NOT_a_driver");
#else
MODULE_IMPORT_NS(VFS_internal_I_am_really_a_filesystem_and_am_NOT_a_driver);
#endif"""
    new = """#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 4, 0)
#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 13, 0)
MODULE_IMPORT_NS("VFS_internal_I_am_really_a_filesystem_and_am_NOT_a_driver");
#else
MODULE_IMPORT_NS(VFS_internal_I_am_really_a_filesystem_and_am_NOT_a_driver);
#endif
#endif"""
    if old in s:
        p.write_text(s.replace(old, new, 1))
        print(f"OK: {p} MODULE_IMPORT_NS guarded for <5.4")
        fixes += 1
    elif new in s:
        print(f"SKIP: {p} already fixed")
    else:
        print(f"WARN: {p} MODULE_IMPORT_NS anchor not found (version drift?)")

# --- builtin branch: linux/static_call.h is 5.5+ only ---
p = Path("KernelSU/kernel/kernel_includes.h")
if p.exists():
    s = p.read_text()
    old = "#include <linux/static_call.h>\n"
    new = (
        "#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 5, 0)\n"
        "#include <linux/static_call.h>\n"
        "#endif\n"
    )
    if old in s and new not in s:
        p.write_text(s.replace(old, new, 1))
        print(f"OK: {p} static_call.h guarded for <5.5")
        fixes += 1
    elif new in s:
        print(f"SKIP: {p} already fixed")
    else:
        print(f"WARN: {p} static_call include not found")

if fixes == 0:
    print("NOTE: no fixes applied (anchors missing or already applied)")
print("DONE")
