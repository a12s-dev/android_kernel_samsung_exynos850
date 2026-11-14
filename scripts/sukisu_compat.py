#!/usr/bin/env python3
"""4.19 compat fixes for SukiSU sources after setup.sh. Safe no-ops if anchors missing."""
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

# --- main+builtin kpm.c: access_ok() lost its type arg in 5.0; 4.19 is 3-arg ---
patch(
    "KernelSU/kernel/extension/kpm/kpm.c",
    "    if (!access_ok(u64_to_user_ptr(cmd.result_code), sizeof(result))) return -EFAULT;",
    "#ifndef VERIFY_READ\n"
    "    if (!access_ok(u64_to_user_ptr(cmd.result_code), sizeof(result))) return -EFAULT;\n"
    "#else\n"
    "    if (!access_ok(VERIFY_WRITE, u64_to_user_ptr(cmd.result_code), sizeof(result))) return -EFAULT;\n"
    "#endif",
    "access_ok 3-arg for <5.0 (kpm.c)",
)

# --- builtin: raw strncpy_from_user_nofault in sulog/event.c -> ksu wrapper ---
# Anchor: end of file (header guard endif after KSU_CAN_USE_KPM).
patch(
    "KernelSU/kernel/kernel_compat.h",
    "#define KSU_CAN_USE_KPM\n#endif\n\n#endif",
    "#define KSU_CAN_USE_KPM\n#endif\n\n"
    "#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 8, 0)\n"
    "#ifndef strncpy_from_user_nofault\n"
    "#define strncpy_from_user_nofault ksu_strncpy_from_user_nofault\n"
    "#endif\n"
    "#endif\n"
    "\n"
    "#endif",
    "strncpy_from_user_nofault -> ksu_ for <5.8 (builtin)",
)

# --- main: force-include a 4.19 nofault compat header for all ksu objects ---
KSU_419_COMPAT = r"""/* 4.19 compat: nofault user/kernel copy helpers (force-included via Kbuild). */
#ifndef __KSU_419_COMPAT_H
#define __KSU_419_COMPAT_H

#include <linux/version.h>
#include <linux/uaccess.h>

#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 8, 0)
#ifndef copy_from_kernel_nofault
#define copy_from_kernel_nofault(dst, src, size) probe_kernel_read((dst), (const void *)(src), (size))
#endif
#ifndef copy_to_kernel_nofault
#define copy_to_kernel_nofault(dst, src, size) probe_kernel_write((dst), (src), (size))
#endif
#ifndef strncpy_from_user_nofault
static inline long strncpy_from_user_nofault(char *dst, const void __user *src, long count)
{
	long ret;
	if (count <= 0)
		return 0;
	pagefault_disable();
	ret = strncpy_from_user(dst, src, count);
	pagefault_enable();
	return ret;
}
#endif
#endif /* <5.8 */

#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 3, 0)
#ifndef copy_from_user_nofault
static inline long copy_from_user_nofault(void *to, const void __user *from, unsigned long count)
{
	long ret;
	pagefault_disable();
	ret = copy_from_user(to, from, count);
	pagefault_enable();
	return ret;
}
#endif
#ifndef copy_to_user_nofault
static inline long copy_to_user_nofault(void __user *to, const void *from, unsigned long count)
{
	long ret;
	pagefault_disable();
	ret = copy_to_user(to, from, count);
	pagefault_enable();
	return ret;
}
#endif
#endif /* <5.3 */

#endif /* __KSU_419_COMPAT_H */
"""

compat_path = Path("KernelSU/kernel/ksu_419_compat.h")
if compat_path.exists() and "__KSU_419_COMPAT_H" in compat_path.read_text():
    print("SKIP: ksu_419_compat.h already written")
else:
    compat_path.write_text(KSU_419_COMPAT)
    print("OK: wrote KernelSU/kernel/ksu_419_compat.h")
    fixes += 1

# Append force-include to main Kbuild (idempotent)
kbuild = Path("KernelSU/kernel/Kbuild")
if kbuild.exists():
    s = kbuild.read_text()
    if "ksu_419_compat.h" not in s:
        s += "\n# 4.19 nofault compat (sukisu_compat.py)\nccflags-y += -include $(KSU_KERNEL_DIR)/ksu_419_compat.h\n"
        kbuild.write_text(s)
        print("OK: Kbuild force-includes ksu_419_compat.h")
        fixes += 1
    else:
        print("SKIP: Kbuild already force-includes ksu_419_compat.h")
else:
    print("SKIP: Kbuild not present (builtin uses unity Makefile)")

if fixes == 0:
    print("NOTE: no fixes applied (anchors missing or already applied)")
print(f"DONE ({fixes} fixes)")
