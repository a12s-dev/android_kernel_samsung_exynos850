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

# --- main: pkg_observer fsnotify handler signature split at 5.9 ---
# Port builtin's pkg_observer_compat.h (handler decl macro + fname helpers).
PO_COMPAT = """// This header should not be used outside of pkg_observer.c!

#include <linux/version.h>

#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 2, 0)
typedef const struct qstr *ksu_fname_t;
#define ksu_fname_len(f) ((f)->len)
#define ksu_fname_arg(f) ((f)->name)
#else
typedef const unsigned char *ksu_fname_t;
#define ksu_fname_len(f) (strlen(f))
#define ksu_fname_arg(f) (f)
#endif

#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 9, 0)
#define KSU_DECL_FSNOTIFY_OPS(name)                                                                                    \\
    int name(struct fsnotify_mark *mark, u32 mask, struct inode *inode, struct inode *dir,                             \\
             const struct qstr *file_name, u32 cookie)
#elif LINUX_VERSION_CODE >= KERNEL_VERSION(5, 2, 0)
#define KSU_DECL_FSNOTIFY_OPS(name)                                                                                    \\
    int name(struct fsnotify_group *group, struct inode *inode, u32 mask, const void *data, int data_type,             \\
             ksu_fname_t file_name, u32 cookie, struct fsnotify_iter_info *iter_info)
#elif LINUX_VERSION_CODE >= KERNEL_VERSION(4, 18, 0)
#define KSU_DECL_FSNOTIFY_OPS(name)                                                                                    \\
    int name(struct fsnotify_group *group, struct inode *inode, u32 mask, const void *data, int data_type,             \\
             ksu_fname_t file_name, u32 cookie, struct fsnotify_iter_info *iter_info)
#elif LINUX_VERSION_CODE >= KERNEL_VERSION(4, 12, 0)
#define KSU_DECL_FSNOTIFY_OPS(name)                                                                                    \\
    int name(struct fsnotify_group *group, struct inode *inode, struct fsnotify_mark *inode_mark,                      \\
             struct fsnotify_mark *vfsmount_mark, u32 mask, const void *data, int data_type, ksu_fname_t file_name,    \\
             u32 cookie, struct fsnotify_iter_info *iter_info)
#else
#define KSU_DECL_FSNOTIFY_OPS(name)                                                                                    \\
    int name(struct fsnotify_group *group, struct inode *inode, struct fsnotify_mark *inode_mark,                      \\
             struct fsnotify_mark *vfsmount_mark, u32 mask, void *data, int data_type, ksu_fname_t file_name,          \\
             u32 cookie)
#endif
"""
po_compat = Path("KernelSU/kernel/manager/pkg_observer_compat.h")
if po_compat.exists() and "KSU_DECL_FSNOTIFY_OPS" in po_compat.read_text():
    print("SKIP: pkg_observer_compat.h already written")
else:
    po_compat.parent.mkdir(parents=True, exist_ok=True)
    po_compat.write_text(PO_COMPAT)
    print("OK: wrote KernelSU/kernel/manager/pkg_observer_compat.h")
    fixes += 1

patch(
    "KernelSU/kernel/manager/pkg_observer.c",
    '#include "manager/throne_tracker.h"',
    '#include "manager/throne_tracker.h"\n#include "manager/pkg_observer_compat.h" // KSU_DECL_FSNOTIFY_OPS',
    "include pkg_observer_compat.h",
)

patch(
    "KernelSU/kernel/manager/pkg_observer.c",
    """static int ksu_handle_inode_event(struct fsnotify_mark *mark, u32 mask, struct inode *inode, struct inode *dir,
                                  const struct qstr *file_name, u32 cookie)
{
    if (!file_name)
        return 0;
    if (mask & FS_ISDIR)
        return 0;
    if (file_name->len == 13 && !memcmp(file_name->name, "packages.list", 13)) {
        pr_info("packages.list detected: %d\\n", mask);
        ksu_defer_track_throne();
    }
    return 0;
}

static const struct fsnotify_ops ksu_ops = {
    .handle_inode_event = ksu_handle_inode_event,
};""",
    """static KSU_DECL_FSNOTIFY_OPS(ksu_handle_generic_event)
{
    if (!file_name || (mask & FS_ISDIR))
        return 0;

    if (ksu_fname_len(file_name) == 13 && !memcmp(ksu_fname_arg(file_name), "packages.list", 13)) {
        pr_info("packages.list detected: %d\\n", mask);
        ksu_defer_track_throne();
    }
    return 0;
}

static const struct fsnotify_ops ksu_ops = {
#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 9, 0)
    .handle_inode_event = ksu_handle_generic_event,
#else
    .handle_event = ksu_handle_generic_event,
#endif
};""",
    "fsnotify handler version guard",
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
KSU_419_COMPAT = r"""/* 4.19 compat: nofault copies + misc 5.x helpers (force-included via Kbuild). */
#ifndef __KSU_419_COMPAT_H
#define __KSU_419_COMPAT_H

#include <linux/version.h>
#include <linux/uaccess.h>
#include <linux/string.h>
#include <linux/fs.h>
#include <linux/cred.h>
#include <linux/sched/task.h>
#include <linux/task_work.h>

/* SELinux accessors: helpers appeared ~5.1; pre-5.1 i_security/security
   point directly at the SELinux structs (builtin does the same). */
struct inode_security_struct;
struct task_security_struct;
#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 1, 0) && !defined(KSU_HAS_SELINUX_INODE)
static inline struct inode_security_struct *selinux_inode(const struct inode *inode)
{
	return (struct inode_security_struct *)inode->i_security;
}
#endif
#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 1, 0) && !defined(KSU_HAS_SELINUX_CRED)
static inline struct task_security_struct *selinux_cred(const struct cred *cred)
{
	return (struct task_security_struct *)cred->security;
}
#endif

/* task_work_add() 3rd arg became TWA_* flags in 5.7; 4.19 takes bool. */
#ifndef TWA_RESUME
#define TWA_RESUME 1
#endif

/* fallthrough: kernel macro since 5.4 (compiler_attributes.h). */
#ifndef fallthrough
#define fallthrough do { } while (0)
#endif

/* strscpy_pad(): upstream 5.4+. Zero-pads the whole dest buffer. */
#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 4, 0)
static inline void ksu_strscpy_pad(char *dest, const char *src, size_t count)
{
	memset(dest, 0, count);
	if (count)
		strncpy(dest, src, count - 1);
}
#define strscpy_pad(dest, src, count) ksu_strscpy_pad((dest), (src), (count))
#endif

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
if compat_path.exists() and compat_path.read_text() == KSU_419_COMPAT:
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
    s = kbuild.read_text()
    if "KSU_OPTIONAL_SECCOMP_FILTER_CNT" not in s:
        s += (
            "\n# struct seccomp.filter_count: present on GKI/newer, absent on 4.19\n"
            "ifeq ($(shell grep -q 'filter_count' $(srctree)/include/linux/seccomp.h; echo $$?),0)\n"
            "ccflags-y += -DKSU_OPTIONAL_SECCOMP_FILTER_CNT\n"
            "endif\n"
        )
        kbuild.write_text(s)
        print("OK: Kbuild feature-detects seccomp filter_count")
        fixes += 1
    else:
        print("SKIP: Kbuild already feature-detects seccomp filter_count")
    s = kbuild.read_text()
    if "KSU_HAS_SELINUX_INODE" not in s:
        s += (
            "\n# selinux_inode/selinux_cred accessors: tree-provided on newer Android\n"
            "ifeq ($(shell grep -q 'selinux_inode' $(srctree)/security/selinux/include/objsec.h; echo $$?),0)\n"
            "ccflags-y += -DKSU_HAS_SELINUX_INODE\n"
            "endif\n"
            "ifeq ($(shell grep -q 'selinux_cred' $(srctree)/security/selinux/include/objsec.h; echo $$?),0)\n"
            "ccflags-y += -DKSU_HAS_SELINUX_CRED\n"
            "endif\n"
        )
        kbuild.write_text(s)
        print("OK: Kbuild feature-detects selinux_inode/selinux_cred")
        fixes += 1
    else:
        print("SKIP: Kbuild already feature-detects selinux accessors")
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

# --- main: app_profile disable_seccomp - seccomp_filter_release is 5.9+,
# struct seccomp.filter_count is optional (grep-detected); 4.19 uses
# put_seccomp_filter() path like builtin ---
AP = "KernelSU/kernel/policy/app_profile.c"
ap_path = Path(AP)
if ap_path.exists():
    s = ap_path.read_text()
    if "KSU_HAS_SECCOMP_FILTER_RELEASE" in s:
        print(f"SKIP: {AP} already guarded")
    else:
        start_m = "void seccomp_filter_release(struct task_struct *tsk);"
        end_m = "    seccomp_filter_release(fake);\n    kfree(fake);\n}"
        if start_m in s and end_m in s:
            start = s.index(start_m)
            end = s.index(end_m, start) + len(end_m)
            new_block = """#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 9, 0)
void seccomp_filter_release(struct task_struct *tsk);
#define KSU_HAS_SECCOMP_FILTER_RELEASE
#endif

// https://cs.android.com/android/_/android/kernel/common/+/5346453405bf12d7ed6003f45dd47b71744fe1be
// Some 15-6.6 kernel have this backport while others don't have, e.g. Pixel 10
// See also:
// https://github.com/tiann/KernelSU/issues/3629
#define NEED_BACKPORT_COMPAT \\
    LINUX_VERSION_CODE >= KERNEL_VERSION(6, 6, 0) && LINUX_VERSION_CODE < KERNEL_VERSION(6, 11, 0)

#if NEED_BACKPORT_COMPAT
static bool has_call_to_spin_lock = false;
#endif

static void disable_seccomp(void)
{
#ifdef KSU_HAS_SECCOMP_FILTER_RELEASE
    struct task_struct *fake;

    fake = kmalloc(sizeof(*fake), GFP_KERNEL);
    if (!fake) {
        pr_warn("failed to alloc fake task_struct\\n");
        return;
    }
#endif

    // Refer to kernel/seccomp.c: seccomp_set_mode_strict
    // When disabling Seccomp, ensure that current->sighand->siglock is held during the operation.
    spin_lock_irq(&current->sighand->siglock);
    // disable seccomp
#if defined(CONFIG_GENERIC_ENTRY) && LINUX_VERSION_CODE >= KERNEL_VERSION(5, 11, 0)
    clear_syscall_work(SECCOMP);
#else
    clear_thread_flag(TIF_SECCOMP);
#endif

#ifdef KSU_HAS_SECCOMP_FILTER_RELEASE
    memcpy(fake, current, sizeof(*fake));
#endif
    current->seccomp.mode = 0;
#ifndef KSU_HAS_SECCOMP_FILTER_RELEASE
    // put_seccomp_filter is allowed while we holding sighand
    put_seccomp_filter(current);
#endif
    current->seccomp.filter = NULL;
#if (LINUX_VERSION_CODE >= KERNEL_VERSION(6, 7, 0) || defined(KSU_OPTIONAL_SECCOMP_FILTER_CNT))
    atomic_set(&current->seccomp.filter_count, 0);
#endif
    spin_unlock_irq(&current->sighand->siglock);

#ifdef KSU_HAS_SECCOMP_FILTER_RELEASE
#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 11, 0)
    fake->flags |= PF_EXITING;
#elif NEED_BACKPORT_COMPAT
    if (has_call_to_spin_lock) {
        fake->flags |= PF_EXITING;
    } else {
        fake->sighand = NULL;
    }
#elif LINUX_VERSION_CODE >= KERNEL_VERSION(5, 11, 0)
    fake->sighand = NULL;
#endif
    seccomp_filter_release(fake);
    kfree(fake);
#endif
}"""
            s = s[:start] + new_block + s[end:]
            ap_path.write_text(s)
            print(f"OK: {AP} disable_seccomp guarded for <5.9 (seccomp_filter_release)")
            fixes += 1
        else:
            print(f"WARN: {AP} anchors not found")
else:
    print(f"SKIP: {AP} not present")

# --- main: cpu_spoof needs 5.10+ vDSO/clocksource (builtin compiles it out <5.10) ---
# 1) Kbuild: only link extension/cpu_spoof.o on >=5.10
patch(
    "KernelSU/kernel/Kbuild",
    "kernelsu-objs += extension/cpu_spoof.o",
    "# cpu_spoof needs 5.10+ vDSO interfaces; builtin gates KSU_CAN_USE_CPU_SPOOF <5.10\n"
    "ifeq ($(shell test $(VERSION) -gt 5 -o $(VERSION) -eq 5 -a $(PATCHLEVEL) -ge 10; echo $$?),0)\n"
    "kernelsu-objs += extension/cpu_spoof.o\n"
    "endif",
    "cpu_spoof.o only >=5.10",
)

# 2) extension.c: guard include, handler struct, registration
patch(
    "KernelSU/kernel/extension/extension.c",
    '#include "kpm.h"\n#include "cpu_spoof.h"\n#include "umount_paths.h"',
    '#include "kpm.h"\n'
    "#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)\n"
    '#include "cpu_spoof.h"\n'
    "#endif\n"
    '#include "umount_paths.h"',
    "guard cpu_spoof.h include >=5.10",
)

patch(
    "KernelSU/kernel/extension/extension.c",
    """    static const struct ksu_extension_handler cpu_spoof_handler = {
        .extension_id = KSU_EXTENSION_CPU_SPOOF,
        .name = "cpu_spoof",
        /* State lives in each ioctl payload; nothing to toggle or keep. */
        .caps = 0,
        .ops = NULL,
        .io_handler = ksu_extension_cpu_spoof_io,
    };""",
    """#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)
    static const struct ksu_extension_handler cpu_spoof_handler = {
        .extension_id = KSU_EXTENSION_CPU_SPOOF,
        .name = "cpu_spoof",
        /* State lives in each ioctl payload; nothing to toggle or keep. */
        .caps = 0,
        .ops = NULL,
        .io_handler = ksu_extension_cpu_spoof_io,
    };
#endif""",
    "guard cpu_spoof handler >=5.10",
)

patch(
    "KernelSU/kernel/extension/extension.c",
    """    if (ksu_register_extension_handler(&cpu_spoof_handler))
        pr_err("extension: failed to register cpu_spoof\\n");""",
    """#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)
    if (ksu_register_extension_handler(&cpu_spoof_handler))
        pr_err("extension: failed to register cpu_spoof\\n");
#endif""",
    "guard cpu_spoof registration >=5.10",
)

# =========================================================================
# SELinux: main only has the modern (selinux_state.policy) path. Port
# builtin's dual-path rules.c and gate 5.10+-only pieces (backup_sepolicy,
# selinux_hide) exactly like builtin does.
# =========================================================================

# 1) rules.c = main's include block + builtin's dual-path body
main_rules = Path("KernelSU/kernel/selinux/rules.c")
ref_rules = Path("scripts/reference/selinux_rules.c")
if main_rules.exists() and ref_rules.exists():
    s = main_rules.read_text()
    if "ksu_get_policy_rwlock" in s:
        print("SKIP: rules.c already dual-path")
    elif "struct selinux_policy *backup_sepolicy;" in s:
        inc_end = s.index("struct selinux_policy *backup_sepolicy;")
        includes = s[:inc_end]
        extra = (
            "#include <linux/mm.h>\n"
            "#include <linux/cpumask.h>\n"
            "#include <linux/spinlock.h>\n"
            "#include <linux/sched/types.h>\n"
            "#include <linux/stop_machine.h>\n"
            "\n"
        )
        main_rules.write_text(includes + extra + ref_rules.read_text())
        print("OK: rules.c replaced with builtin dual-path body")
        fixes += 1
    else:
        print("WARN: rules.c include-split anchor not found")
else:
    print("SKIP: rules.c or scripts/reference/selinux_rules.c missing")

# 2) ksu.h: backup_sepolicy only exists >=5.10 (matches builtin)
patch(
    "KernelSU/kernel/include/ksu.h",
    "extern struct selinux_policy *backup_sepolicy;",
    "#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)\n"
    "extern struct selinux_policy *backup_sepolicy;\n"
    "#endif",
    "backup extern guarded >=5.10",
)

# 3) selinux.h: define KSU_COMPAT_USE_SELINUX_STATE like builtin
patch(
    "KernelSU/kernel/selinux/selinux.h",
    "#ifndef __KSU_H_SELINUX\n#define __KSU_H_SELINUX\n",
    "#ifndef __KSU_H_SELINUX\n"
    "#define __KSU_H_SELINUX\n\n"
    "#if (LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)) || defined(KSU_COMPAT_HAS_SELINUX_STATE)\n"
    "#define KSU_COMPAT_USE_SELINUX_STATE\n"
    "#endif\n",
    "KSU_COMPAT_USE_SELINUX_STATE like builtin",
)

# 4) sepolicy.h: dup/destroy protos only exist >=5.10
patch(
    "KernelSU/kernel/selinux/sepolicy.h",
    "struct selinux_policy *ksu_dup_sepolicy(struct selinux_policy *old_pol);\n\n"
    "void ksu_destroy_sepolicy(struct selinux_policy *orig);",
    "#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)\n"
    "struct selinux_policy *ksu_dup_sepolicy(struct selinux_policy *old_pol);\n\n"
    "void ksu_destroy_sepolicy(struct selinux_policy *orig);\n"
    "#endif",
    "dup/destroy protos guarded >=5.10",
)

# 5) sepolicy.c: wholesale swap to builtin's version-forked body
#    (avtab flex_array vs ptr, filename_trans old/new, type_val paths,
#    dup/destroy already >=5.10-gated inside builtin's file)
main_sp = Path("KernelSU/kernel/selinux/sepolicy.c")
ref_sp = Path("scripts/reference/selinux_sepolicy.c")
if main_sp.exists() and ref_sp.exists():
    s = main_sp.read_text()
    if "susfs_add_sus_avd_allowed_by_type" in s:
        print("SKIP: sepolicy.c already builtin body")
    elif "#define KSU_SUPPORT_ADD_TYPE" in s:
        inc_end = s.index("#define KSU_SUPPORT_ADD_TYPE")
        includes = s[:inc_end]
        main_sp.write_text(includes + ref_sp.read_text())
        print("OK: sepolicy.c replaced with builtin dual-version body")
        fixes += 1
    else:
        print("WARN: sepolicy.c include-split anchor not found")
else:
    print("SKIP: sepolicy.c or scripts/reference/selinux_sepolicy.c missing")

# 6) selinux_hide call sites: file itself is >=5.10-only
patch(
    "KernelSU/kernel/core/init.c",
    "    ksu_lsm_hook_init();\n    ksu_selinux_hide_init();\n    ksu_avc_spoof_init();",
    "    ksu_lsm_hook_init();\n"
    "#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)\n"
    "    ksu_selinux_hide_init();\n"
    "#endif\n"
    "    ksu_avc_spoof_init();",
    "guard hide_init call >=5.10",
)

patch(
    "KernelSU/kernel/core/init.c",
    "    ksu_shell_su_adb_only_exit();\n    ksu_avc_spoof_exit();\n    ksu_selinux_hide_exit();\n    ksu_lsm_hook_exit();",
    "    ksu_shell_su_adb_only_exit();\n"
    "    ksu_avc_spoof_exit();\n"
    "#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)\n"
    "    ksu_selinux_hide_exit();\n"
    "#endif\n"
    "    ksu_lsm_hook_exit();",
    "guard hide_exit call >=5.10",
)

patch(
    "KernelSU/kernel/runtime/boot_event.c",
    "    ksu_stop_input_hook_runtime();\n    ksu_selinux_hide_handle_post_fs_data();",
    "    ksu_stop_input_hook_runtime();\n"
    "#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)\n"
    "    ksu_selinux_hide_handle_post_fs_data();\n"
    "#endif",
    "guard hide_post_fs_data call >=5.10",
)

patch(
    "KernelSU/kernel/runtime/boot_event.c",
    "    track_throne(true);\n    ksu_selinux_hide_drop_backup_if_unused();\n    ksu_avc_spoof_late_init();",
    "    track_throne(true);\n"
    "#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)\n"
    "    ksu_selinux_hide_drop_backup_if_unused();\n"
    "#endif\n"
    "    ksu_avc_spoof_late_init();",
    "guard hide_drop_backup call >=5.10",
)

patch(
    "KernelSU/kernel/runtime/ksud_integration.c",
    "            ksu_preinit_release();\n            ksu_selinux_hide_handle_second_stage();\n            apply_kernelsu_rules();",
    "            ksu_preinit_release();\n"
    "#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 10, 0)\n"
    "            ksu_selinux_hide_handle_second_stage();\n"
    "#endif\n"
    "            apply_kernelsu_rules();",
    "guard hide_second_stage call >=5.10",
)

# 7) Kbuild: exclude selinux_hide.o below 5.10; detect struct selinux_state
patch(
    "KernelSU/kernel/Kbuild",
    "kernelsu-objs += feature/selinux_hide.o",
    "# selinux_hide needs selinux_state.policy dup (5.10+); builtin excludes the file too\n"
    "ifeq ($(shell test $(VERSION) -gt 5 -o $(VERSION) -eq 5 -a $(PATCHLEVEL) -ge 10; echo $$?),0)\n"
    "kernelsu-objs += feature/selinux_hide.o\n"
    "endif",
    "selinux_hide.o only >=5.10",
)

kbuild = Path("KernelSU/kernel/Kbuild")
if kbuild.exists():
    s = kbuild.read_text()
    if "KSU_COMPAT_HAS_SELINUX_STATE" not in s:
        s += (
            "\n# struct selinux_state: present in selinux's security.h (4.19+ here)\n"
            "ifeq ($(shell grep -q 'struct selinux_state ' $(srctree)/security/selinux/include/security.h; echo $$?),0)\n"
            "ccflags-y += -DKSU_COMPAT_HAS_SELINUX_STATE\n"
            "endif\n"
            "# old policy_rwlock exported from services.c (pre-selinux_ss relocations)\n"
            "ifeq ($(shell grep -q '^DEFINE_RWLOCK(policy_rwlock);' $(srctree)/security/selinux/ss/services.c; echo $$?),0)\n"
            "ccflags-y += -DKSU_COMPAT_HAS_EXPORTED_POLICY_RWLOCK\n"
            "endif\n"
        )
        kbuild.write_text(s)
        print("OK: Kbuild feature-detects selinux_state / policy_rwlock")
        fixes += 1
    else:
        print("SKIP: Kbuild already feature-detects selinux_state")

if fixes == 0:
    print("NOTE: no fixes applied (anchors missing or already applied)")
print(f"DONE ({fixes} fixes)")
