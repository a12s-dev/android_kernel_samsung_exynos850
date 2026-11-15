#!/usr/bin/env python3
"""Insert SukiSU builtin (manual) hook calls into kernel sources.
Only for the 'manual' CI job. Aborts if anchors are missing/multiple.
"""
import sys
import re
from pathlib import Path

def edit(path, old, new, count=1):
    p = Path(path)
    if not p.exists():
        sys.exit(f"FAIL: missing {path}")
    s = p.read_text()
    if new and new in s:
        print(f"SKIP: {path} (already applied)")
        return
    n = s.count(old)
    if n != count:
        sys.exit(f"FAIL: {path}: anchor found {n} times (expected {count}):\n{old!r}")
    p.write_text(s.replace(old, new, count))
    print(f"OK: {path}")

# ---------- fs/exec.c ----------
edit(
    "fs/exec.c",
    """static int do_execveat_common(int fd, struct filename *filename,
			      struct user_arg_ptr argv,
			      struct user_arg_ptr envp,
			      int flags)
{
	return __do_execve_file(fd, filename, argv, envp, flags, NULL);
}
""",
    """#ifdef CONFIG_KSU
extern bool ksu_execveat_hook __read_mostly;
extern int ksu_handle_execveat_ksud(int *fd, struct filename **filename_ptr,
				    struct user_arg_ptr *argv,
				    struct user_arg_ptr *envp, int *flags);
extern int ksu_handle_execveat_sucompat(int *fd, struct filename **filename_ptr,
					void *argv, void *envp, int *flags);
#endif
static int do_execveat_common(int fd, struct filename *filename,
			      struct user_arg_ptr argv,
			      struct user_arg_ptr envp,
			      int flags)
{
#ifdef CONFIG_KSU
	if (unlikely(ksu_execveat_hook))
		ksu_handle_execveat_ksud(&fd, &filename, &argv, &envp, &flags);
	else
		ksu_handle_execveat_sucompat(&fd, &filename, &argv, &envp, &flags);
#endif
	return __do_execve_file(fd, filename, argv, envp, flags, NULL);
}
""",
)

# ---------- fs/open.c ----------
edit(
    "fs/open.c",
    """long do_faccessat(int dfd, const char __user *filename, int mode)
{
	const struct cred *old_cred;
	struct cred *override_cred;
	struct path path;
	struct inode *inode;
	int res;
	unsigned int lookup_flags = LOOKUP_FOLLOW;

	if (mode & ~S_IRWXO)	/* where's F_OK, X_OK, W_OK, R_OK? */
		return -EINVAL;
""",
    """#ifdef CONFIG_KSU
extern int ksu_handle_faccessat(int *dfd, const char __user **filename_user,
				int *mode, int *flags);
#endif
long do_faccessat(int dfd, const char __user *filename, int mode)
{
	const struct cred *old_cred;
	struct cred *override_cred;
	struct path path;
	struct inode *inode;
	int res;
	unsigned int lookup_flags = LOOKUP_FOLLOW;
#ifdef CONFIG_KSU
	ksu_handle_faccessat(&dfd, &filename, &mode, NULL);
#endif

	if (mode & ~S_IRWXO)	/* where's F_OK, X_OK, W_OK, R_OK? */
		return -EINVAL;
""",
)

# ---------- fs/read_write.c ----------
edit(
    "fs/read_write.c",
    """ssize_t vfs_read(struct file *file, char __user *buf, size_t count, loff_t *pos)
{
	ssize_t ret;

	if (!(file->f_mode & FMODE_READ))
		return -EBADF;
""",
    """#ifdef CONFIG_KSU
extern bool ksu_vfs_read_hook __read_mostly;
extern int ksu_handle_vfs_read(struct file **file_ptr, char __user **buf_ptr,
				size_t *count_ptr, loff_t **pos);
#endif
ssize_t vfs_read(struct file *file, char __user *buf, size_t count, loff_t *pos)
{
	ssize_t ret;
#ifdef CONFIG_KSU
	if (unlikely(ksu_vfs_read_hook))
		ksu_handle_vfs_read(&file, &buf, &count, &pos);
#endif

	if (!(file->f_mode & FMODE_READ))
		return -EBADF;
""",
)

# ---------- fs/stat.c ----------
edit(
    "fs/stat.c",
    """int vfs_statx(int dfd, const char __user *filename, int flags,
	      struct kstat *stat, u32 request_mask)
{
	struct path path;
	int error = -EINVAL;
	unsigned int lookup_flags = LOOKUP_FOLLOW | LOOKUP_AUTOMOUNT;

	if ((flags & ~(AT_SYMLINK_NOFOLLOW | AT_NO_AUTOMOUNT |
		       AT_EMPTY_PATH | KSTAT_QUERY_FLAGS)) != 0)
		return -EINVAL;
""",
    """#ifdef CONFIG_KSU
extern int ksu_handle_stat(int *dfd, const char __user **filename_user,
			   int *flags);
#endif
int vfs_statx(int dfd, const char __user *filename, int flags,
	      struct kstat *stat, u32 request_mask)
{
	struct path path;
	int error = -EINVAL;
	unsigned int lookup_flags = LOOKUP_FOLLOW | LOOKUP_AUTOMOUNT;
#ifdef CONFIG_KSU
	ksu_handle_stat(&dfd, &filename, &flags);
#endif

	if ((flags & ~(AT_SYMLINK_NOFOLLOW | AT_NO_AUTOMOUNT |
		       AT_EMPTY_PATH | KSTAT_QUERY_FLAGS)) != 0)
		return -EINVAL;
""",
)

# ---------- drivers/input/input.c (safe mode / vol detector) ----------
edit(
    "drivers/input/input.c",
    """static void input_handle_event(struct input_dev *dev,
			       unsigned int type, unsigned int code, int value)
{
	int disposition = input_get_disposition(dev, type, code, &value);

	if (disposition != INPUT_IGNORE_EVENT && type != EV_SYN)
""",
    """#ifdef CONFIG_KSU
extern bool ksu_input_hook __read_mostly;
extern int ksu_handle_input_handle_event(unsigned int *type, unsigned int *code,
					 int *value);
#endif
static void input_handle_event(struct input_dev *dev,
			       unsigned int type, unsigned int code, int value)
{
	int disposition = input_get_disposition(dev, type, code, &value);
#ifdef CONFIG_KSU
	if (unlikely(ksu_input_hook))
		ksu_handle_input_handle_event(&type, &code, &value);
#endif

	if (disposition != INPUT_IGNORE_EVENT && type != EV_SYN)
""",
)

# ---------- kernel/reboot.c (ksud driver-fd install via magic reboot) ----------
edit(
    "kernel/reboot.c",
    """SYSCALL_DEFINE4(reboot, int, magic1, int, magic2, unsigned int, cmd,
		void __user *, arg)
{
	struct pid_namespace *pid_ns = task_active_pid_ns(current);
	char buffer[256];
	int ret = 0;

	/* We only trust the superuser with rebooting the system. */
""",
    """#ifdef CONFIG_KSU
extern int ksu_handle_sys_reboot(int magic1, int magic2, unsigned int cmd,
			void __user **arg);
#endif
SYSCALL_DEFINE4(reboot, int, magic1, int, magic2, unsigned int, cmd,
		void __user *, arg)
{
	struct pid_namespace *pid_ns = task_active_pid_ns(current);
	char buffer[256];
	int ret = 0;

#ifdef CONFIG_KSU
	if (!ksu_handle_sys_reboot(magic1, magic2, cmd, &arg))
		return 0;
#endif

	/* We only trust the superuser with rebooting the system. */
""",
)

print("ALL MANUAL HOOKS APPLIED")
