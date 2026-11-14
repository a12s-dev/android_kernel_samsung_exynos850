#!/usr/bin/env python3
"""4.19 compat fixes for SukiSU sources after setup.sh. Safe no-ops if anchors missing."""
import sys
from pathlib import Path

fixes = 0

def patch(path, old, new, label):
    global fixes
    p = Path(path)
    if not p.exists():
        print(f"SKIP: {path} not present ({label})")
        return
    s = p.read_text()
    if new in s:
        print(f"SKIP: {path} already fixed ({label})")
        return
    if old not in s:
        print(f"WARN: {path} anchor not found ({label})")
        return
    p.write_text(s.replace(old, new, 1))
    print(f"OK: {path} {label}")
    fixes += 1

# --- main: MODULE_IMPORT_NS does not exist before ~5.4 ---
patch(
    "KernelSU/kernel/core/init.c",
    """#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 13, 0)
MODULE_IMPORT_NS("VFS_internal_I_am_really_a_filesystem_and_am_NOT_a_driver");
#else
MODULE_IMPORT_NS(VFS_internal_I_am_really_a_filesystem_and_am_NOT_a_driver);
#endif""",
    """#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 4, 0)
#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 13, 0)
MODULE_IMPORT_NS("VFS_internal_I_am_really_a_filesystem_and_am_NOT_a_driver");
#else
MODULE_IMPORT_NS(VFS_internal_I_am_really_a_filesystem_and_am_NOT_a_driver);
#endif
#endif""",
    "MODULE_IMPORT_NS guarded for <5.4",
)

# --- builtin: linux/static_call.h is 5.5+ only ---
patch(
    "KernelSU/kernel/kernel_includes.h",
    "#include <linux/static_call.h>\n",
    "#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 5, 0)\n"
    "#include <linux/static_call.h>\n"
    "#endif\n",
    "static_call.h guarded for <5.5",
)

# --- main: include/linux/pgtable.h missing on this 4.19 tree; use asm/pgtable.h ---
patch(
    "KernelSU/kernel/feature/sucompat.c",
    "#include <linux/pgtable.h>",
    "#include <asm/pgtable.h>",
    "pgtable.h -> asm/pgtable.h",
)

# --- main: linux/minmax.h is 5.4+; 4.19 has min() in linux/kernel.h ---
patch(
    "KernelSU/kernel/sulog/event.c",
    "#include <linux/gfp.h>\n#include <linux/minmax.h>\n",
    "#include <linux/gfp.h>\n"
    "#include <linux/version.h>\n"
    "#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 4, 0)\n"
    "#include <linux/minmax.h>\n"
    "#else\n"
    "#include <linux/kernel.h>\n"
    "#endif\n",
    "minmax.h guarded for <5.4",
)

# --- main+builtin: bin2hex() comes from linux/hex.h (6.4+); provide fallback ---
BIN2HEX_OLD = """#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 4, 0)
#include <linux/hex.h>
#endif
"""
BIN2HEX_NEW = """#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 4, 0)
#include <linux/hex.h>
#else
#include <linux/version.h>
#include <linux/types.h>
static inline char *ksu_bin2hex(char *dst, const u8 *src, size_t count)
{
	static const char hex[] = "0123456789abcdef";
	size_t i;
	for (i = 0; i < count; i++) {
		dst[i * 2] = hex[src[i] >> 4];
		dst[i * 2 + 1] = hex[src[i] & 0xf];
	}
	dst[count * 2] = '\\0';
	return dst;
}
#define bin2hex(dst, src, count) ksu_bin2hex((dst), (const u8 *)(src), (count))
#endif
"""
patch("KernelSU/kernel/manager/apk_sign.c", BIN2HEX_OLD, BIN2HEX_NEW, "bin2hex fallback for <6.4 (main apk_sign.c)")

# --- builtin: hex.h guard lives in kernel_includes.h ---
patch("KernelSU/kernel/kernel_includes.h", BIN2HEX_OLD, BIN2HEX_NEW, "bin2hex fallback for <6.4 (builtin kernel_includes.h)")

if fixes == 0:
    print("NOTE: no fixes applied (anchors missing or already applied)")
print(f"DONE ({fixes} fixes)")
