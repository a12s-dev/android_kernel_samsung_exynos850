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
    if new and new in s:
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

# --- main: <uapi/linux/mount.h> does not exist on this tree and nothing in
# the file references its symbols (dead include) ---
patch(
    "KernelSU/kernel/infra/su_mount_ns.c",
    "#include <uapi/linux/mount.h>\n",
    "",
    "drop nonexistent uapi/linux/mount.h include",
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
    s = kbuild.read_text()
    if "KSU_HAS_SECCOMP_ACTION_CACHE" not in s:
        s += (
            "\n# seccomp action_cache is Android/GKI-only, absent on 4.19\n"
            "ifeq ($(shell grep -q 'action_cache' $(srctree)/kernel/seccomp.c; echo $$?),0)\n"
            "ccflags-y += -DKSU_HAS_SECCOMP_ACTION_CACHE\n"
            "endif\n"
        )
        kbuild.write_text(s)
        print("OK: Kbuild feature-detects seccomp action_cache")
        fixes += 1
    else:
        print("SKIP: Kbuild already feature-detects seccomp action_cache")
else:
    print("SKIP: Kbuild not present (builtin uses unity Makefile)")

# --- main file_wrapper.c: gate 5.1+/4.20+ fops helpers for 4.19 ---
FW = "KernelSU/kernel/infra/file_wrapper.c"

# iopoll: field + signature only exist 5.1+ (was bare #else assuming it exists)
patch(
    FW,
    """#else
static int ksu_wrapper_iopoll(struct kiocb *kiocb, bool spin)
{
    struct ksu_file_wrapper *data = kiocb->ki_filp->private_data;
    struct file *orig = data->orig;
    kiocb->ki_filp = orig;
    return orig->f_op->iopoll(kiocb, spin);
}
#endif""",
    """#elif LINUX_VERSION_CODE >= KERNEL_VERSION(5, 1, 0)
static int ksu_wrapper_iopoll(struct kiocb *kiocb, bool spin)
{
    struct ksu_file_wrapper *data = kiocb->ki_filp->private_data;
    struct file *orig = data->orig;
    kiocb->ki_filp = orig;
    return orig->f_op->iopoll(kiocb, spin);
}
#endif""",
    "iopoll wrapper >=5.1 only",
)

patch(
    FW,
    "    p->ops.iopoll = fp->f_op->iopoll ? ksu_wrapper_iopoll : NULL;",
    "#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 1, 0)\n"
    "    p->ops.iopoll = fp->f_op->iopoll ? ksu_wrapper_iopoll : NULL;\n"
    "#endif",
    "iopoll assign >=5.1",
)

# remap_file_range / REMAP_FILE_DEDUP: 4.20+ (4.19 has dedupe_file_range instead)
patch(
    FW,
    """static loff_t ksu_wrapper_remap_file_range(struct file *file_in, loff_t pos_in, struct file *file_out, loff_t pos_out,
                                           loff_t len, unsigned int remap_flags)
{""",
    """#if LINUX_VERSION_CODE >= KERNEL_VERSION(4, 20, 0)
static loff_t ksu_wrapper_remap_file_range(struct file *file_in, loff_t pos_in, struct file *file_out, loff_t pos_out,
                                           loff_t len, unsigned int remap_flags)
{""",
    "remap wrapper open >=4.20",
)

# close the remap wrapper (#endif after its closing brace)
patch(
    FW,
    """        return orig->f_op->remap_file_range(orig, pos_in, file_out, pos_out, len, remap_flags);
    }
}""",
    """        return orig->f_op->remap_file_range(orig, pos_in, file_out, pos_out, len, remap_flags);
    }
}
#endif""",
    "remap wrapper close >=4.20",
)

patch(
    FW,
    "    p->ops.remap_file_range = fp->f_op->remap_file_range ? ksu_wrapper_remap_file_range : NULL;",
    "#if LINUX_VERSION_CODE >= KERNEL_VERSION(4, 20, 0)\n"
    "    p->ops.remap_file_range = fp->f_op->remap_file_range ? ksu_wrapper_remap_file_range : NULL;\n"
    "#endif",
    "remap assign >=4.20",
)

# <5.16 anon-inode path: security_inode_init_security_anon is 5.1+ and the
# borrowed anon_inode_mnt is never initialized here (always -ENODEV).
# Match builtin: plain anon_inode_getfile (drops unused 5th arg).
ANON_OLD = """#else
// There is no anon_inode_create_getfile before 5.16, but it's not difficult to implement it.
// https://cs.android.com/android/kernel/superproject/+/common-android12-5.10:common/fs/anon_inodes.c;l=58-125;drc=0d34ce8aa78e38affbb501690bcabec4df88620e

// Borrow kernel's anon_inode_mnt, so that we don't need to mount one by ourselves.
static struct vfsmount *anon_inode_mnt __read_mostly;
"""
# Replace from #else through the end of ksu_anon_inode_create_getfile_compat fn
p_fw = Path(FW)
if p_fw.exists():
    s = p_fw.read_text()
    if "define ksu_anon_inode_create_getfile_compat(a, b, c, d, e) anon_inode_getfile" in s:
        print(f"SKIP: {FW} anon <5.16 path already simplified")
    elif ANON_OLD in s:
        start = s.index(ANON_OLD)
        end_marker = "\n#endif\n\nint ksu_install_file_wrapper"
        end = s.index(end_marker, start)
        new_block = (
            "#else\n"
            "#define ksu_anon_inode_create_getfile_compat(a, b, c, d, e) anon_inode_getfile(a, b, c, d)\n"
        )
        s = s[:start] + new_block + s[end:]
        p_fw.write_text(s)
        print(f"OK: {FW} anon <5.16 path -> anon_inode_getfile macro")
        fixes += 1
    else:
        print(f"WARN: {FW} anon <5.16 anchor not found")
else:
    print(f"SKIP: {FW} not present")

# init() no longer needs anon_inode_mnt (deleted with the custom <5.16 path)
patch(
    FW,
    """void __init ksu_file_wrapper_init(void)
{
#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 16, 0)
    static const struct file_operations tmp = { .owner = THIS_MODULE };
    struct file *dummy = anon_inode_getfile("dummy", &tmp, NULL, 0);
    if (IS_ERR(dummy)) {
        pr_err("file_wrapper: initialize anon_inode_mnt failed, can't get file: %ld\\n", PTR_ERR(dummy));
        return;
    }
    anon_inode_mnt = dummy->f_path.mnt;
    if (unlikely(!anon_inode_mnt)) {
        pr_err("file_wrapper: initialize anon_inode_mnt failed, got NULL\\n");
    }
    fput(dummy);
#endif
}""",
    """void __init ksu_file_wrapper_init(void)
{
}""",
    "init: drop anon_inode_mnt setup",
)

# --- main: seccomp action_cache (SECCOMP_ARCH_NATIVE_NR) is Android/GKI-only;
# on 4.19 the kernel struct has no cache -> no-op stubs, no struct redef ---
SC = "KernelSU/kernel/infra/seccomp_cache.c"
sc_path = Path(SC)
if sc_path.exists():
    s = sc_path.read_text()
    if "KSU_HAS_SECCOMP_ACTION_CACHE" in s:
        print(f"SKIP: {SC} already gated")
    elif "struct action_cache {" in s:
        idx = s.index("struct action_cache {")
        head, body = s[:idx], s[idx:]
        sc_path.write_text(
            head
            + "#ifndef KSU_HAS_SECCOMP_ACTION_CACHE\n"
            + "/* No action_cache in this kernel (4.19): stubs, full filter still runs. */\n"
            + "void ksu_seccomp_clear_cache(struct seccomp_filter *filter, int nr) { (void)filter; (void)nr; }\n"
            + "void ksu_seccomp_allow_cache(struct seccomp_filter *filter, int nr) { (void)filter; (void)nr; }\n"
            + "#else\n"
            + body
            + "\n#endif\n"
        )
        print(f"OK: {SC} gated on KSU_HAS_SECCOMP_ACTION_CACHE")
        fixes += 1
    else:
        print(f"WARN: {SC} action_cache anchor not found")
else:
    print(f"SKIP: {SC} not present")

if fixes == 0:
    print("NOTE: no fixes applied (anchors missing or already applied)")
print(f"DONE ({fixes} fixes)")
