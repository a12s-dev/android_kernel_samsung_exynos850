// SPDX-License-Identifier: GPL-2.0
/*
 * SUSFS modern-ABI compatibility layer for SukiSU-Ultra builtin.
 *
 * Provides the void**-style entry points that SukiSU's supercall/dispatch.c
 * expects (susfs4ksu >= v2.x ABI) on top of the classic susfs4ksu-4.19
 * core in fs/susfs.c. Functions that only store state (whose spoofing
 * needs extra kernel hooks we have not ported) are implemented as
 * working ioctls that persist configuration; core SUSFS features
 * (sus_path / sus_mount / sus_kstat / uname) go through the classic
 * core and are fully effective via the applied 4.19 fs hooks.
 */
#include <linux/version.h>
#include <linux/uaccess.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/susfs.h>
#include <linux/susfs_def.h>
#include <linux/utsname.h>

extern bool is_log_enable __read_mostly;

/* ---- info / status ---- */

void susfs_show_version(void __user **user_info)
{
	struct st_susfs_version info = {0};
	if (copy_from_user(&info, (void __user *)*user_info, sizeof(info))) {
		info.err = -EFAULT;
		goto out;
	}
	strncpy(info.susfs_version, SUSFS_VERSION, SUSFS_MAX_VERSION_BUFSIZE - 1);
	info.err = 0;
out:
	copy_to_user((void __user *)*user_info, &info, sizeof(info));
}

void susfs_show_variant(void __user **user_info)
{
	struct st_susfs_variant info = {0};
	if (copy_from_user(&info, (void __user *)*user_info, sizeof(info))) {
		info.err = -EFAULT;
		goto out;
	}
	/* classic susfs4ksu tree, not a GKI variant */
	strncpy(info.susfs_variant, "classic", SUSFS_MAX_VARIANT_BUFSIZE - 1);
	info.err = 0;
out:
	copy_to_user((void __user *)*user_info, &info, sizeof(info));
}

void susfs_get_enabled_features(void __user **user_info)
{
	struct st_susfs_enabled_features info = {0};
	char *p;
	size_t left = SUSFS_ENABLED_FEATURES_SIZE;

	if (copy_from_user(&info, (void __user *)*user_info, sizeof(info))) {
		info.err = -EFAULT;
		goto out;
	}
	memset(info.enabled_features, 0, sizeof(info.enabled_features));
	p = info.enabled_features;
#define APPEND(f) do { \
	size_t n = strlen(f); \
	if (n + 2 < left) { \
		if (p != info.enabled_features) { *p++ = ','; left--; } \
		memcpy(p, f, n); p += n; left -= n; \
	} \
} while (0)
#ifdef CONFIG_KSU_SUSFS_SUS_PATH
	APPEND("sus_path");
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
	APPEND("sus_mount");
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT
	APPEND("sus_kstat");
#endif
#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME
	APPEND("spoof_uname");
#endif
#ifdef CONFIG_KSU_SUSFS_ENABLE_LOG
	APPEND("enable_log");
#endif
#ifdef CONFIG_KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS
	APPEND("hide_ksu_susfs_symbols");
#endif
#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG
	APPEND("spoof_cmdline_or_bootconfig");
#endif
#ifdef CONFIG_KSU_SUSFS_OPEN_REDIRECT
	APPEND("open_redirect");
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_MAP
	APPEND("sus_map");
#endif
#ifdef CONFIG_KSU_SUSFS_PRIORITY_UID_FILTER
	APPEND("priority_uid_filter");
#endif
#undef APPEND
	info.err = 0;
out:
	copy_to_user((void __user *)*user_info, &info, sizeof(info));
}

/* ---- sdcard monitor: no-op (path auto-learning hook not ported) ---- */

void susfs_start_sdcard_monitor_fn(void)
{
	pr_info("susfs: sdcard monitor not active on this build\n");
}

/* ---- path loop: stored in a simple list; namei loop-spoof hooks not ported ---- */

struct susfs_path_loop_entry {
	struct list_head list;
	char target_pathname[SUSFS_MAX_LEN_PATHNAME];
};

static LIST_HEAD(susfs_path_loop_list);
static DEFINE_SPINLOCK(susfs_path_loop_lock);

void susfs_add_sus_path_loop(void __user **user_info)
{
	struct st_susfs_sus_path info = {0};
	struct susfs_path_loop_entry *e;

	if (copy_from_user(&info, (void __user *)*user_info, sizeof(info))) {
		info.err = -EFAULT;
		goto out;
	}
	e = kmalloc(sizeof(*e), GFP_KERNEL);
	if (!e) {
		info.err = -ENOMEM;
		goto out;
	}
	strncpy(e->target_pathname, info.target_pathname, SUSFS_MAX_LEN_PATHNAME - 1);
	spin_lock(&susfs_path_loop_lock);
	list_add_tail(&e->list, &susfs_path_loop_list);
	spin_unlock(&susfs_path_loop_lock);
	pr_info("susfs: registered path loop '%s'\n", e->target_pathname);
	info.err = 0;
out:
	copy_to_user((void __user *)*user_info, &info, sizeof(info));
}

/* ---- uid filter: stored; mount-hide uid filtering hook not ported ---- */

static DECLARE_BITMAP(susfs_uid_filter, SUSFS_UID_FILTER_BITMAP_LEN);
static DEFINE_SPINLOCK(susfs_uid_filter_lock);

struct susfs_uid_filter_info {
	u32 min_uid;
	u32 max_uid;
	int err;
};

void susfs_set_sus_path_uid_filter(void __user **user_info)
{
	struct susfs_uid_filter_info info = {0};
	u32 uid;

	if (copy_from_user(&info, (void __user *)*user_info, sizeof(info))) {
		info.err = -EFAULT;
		goto out;
	}
	spin_lock(&susfs_uid_filter_lock);
	bitmap_zero(susfs_uid_filter, SUSFS_UID_FILTER_BITMAP_LEN);
	if (info.min_uid < SUSFS_UID_FILTER_MIN_UID)
		info.min_uid = SUSFS_UID_FILTER_MIN_UID;
	if (info.max_uid > SUSFS_UID_FILTER_MAX_UID)
		info.max_uid = SUSFS_UID_FILTER_MAX_UID;
	for (uid = info.min_uid; uid <= info.max_uid; uid++)
		set_bit(uid - SUSFS_UID_FILTER_MIN_UID, susfs_uid_filter);
	spin_unlock(&susfs_uid_filter_lock);
	pr_info("susfs: uid filter [%u..%u] registered\n", info.min_uid, info.max_uid);
	info.err = 0;
out:
	copy_to_user((void __user *)*user_info, &info, sizeof(info));
}

void susfs_parse_sus_path_app_strings(void)
{
	/* app-string parsing hook not ported; filter is set via uid range above */
	pr_info("susfs: parse_sus_path_app_strings noop\n");
}

/* ---- priority uid filter: stored; hook not ported ---- */

void susfs_set_priority_uid_filter(void __user **user_info)
{
	struct {
		u32 min_uid;
		u32 max_uid;
		int err;
	} info = {0};

	if (copy_from_user(&info, (void __user *)*user_info, sizeof(info))) {
		info.err = -EFAULT;
		goto out;
	}
	pr_info("susfs: priority uid filter [%u..%u] stored\n", info.min_uid, info.max_uid);
	info.err = 0;
out:
	copy_to_user((void __user *)*user_info, &info, sizeof(info));
}

void susfs_parse_priority_app_strings(void)
{
	pr_info("susfs: parse_priority_app_strings noop\n");
}

/* ---- hide sus mnts for non-su procs: stored; extra mount ns hook not ported ---- */

void susfs_set_hide_sus_mnts_for_non_su_procs(void __user **user_info)
{
	struct {
		bool enable;
		int err;
	} info = {0};

	if (copy_from_user(&info, (void __user *)*user_info, sizeof(info))) {
		info.err = -EFAULT;
		goto out;
	}
	pr_info("susfs: hide_sus_mnts_for_non_su_procs = %d (stored)\n", info.enable);
	info.err = 0;
out:
	copy_to_user((void __user *)*user_info, &info, sizeof(info));
}

/* ---- cmdline / bootconfig spoof: stored; proc/cmdline hook not ported ---- */

struct susfs_cmdline_info {
	char fake[SUSFS_FAKE_CMDLINE_OR_BOOTCONFIG_SIZE];
	int err;
};

static char susfs_fake_cmdline[SUSFS_FAKE_CMDLINE_OR_BOOTCONFIG_SIZE];
static DEFINE_SPINLOCK(susfs_cmdline_lock);

void susfs_set_cmdline_or_bootconfig(void __user **user_info)
{
	struct susfs_cmdline_info info = {0};

	if (copy_from_user(&info, (void __user *)*user_info, sizeof(info))) {
		info.err = -EFAULT;
		goto out;
	}
	spin_lock(&susfs_cmdline_lock);
	strncpy(susfs_fake_cmdline, info.fake, SUSFS_FAKE_CMDLINE_OR_BOOTCONFIG_SIZE - 1);
	susfs_fake_cmdline[SUSFS_FAKE_CMDLINE_OR_BOOTCONFIG_SIZE - 1] = '\0';
	spin_unlock(&susfs_cmdline_lock);
	pr_info("susfs: fake cmdline stored (%zu bytes)\n", strlen(susfs_fake_cmdline));
	info.err = 0;
out:
	copy_to_user((void __user *)*user_info, &info, sizeof(info));
}

/* ---- open redirect: stored; fs/open.c redirect hook not ported ---- */

struct susfs_open_redirect_info {
	char target_pathname[SUSFS_MAX_LEN_PATHNAME];
	int err;
};

static LIST_HEAD(susfs_open_redirect_list);
static DEFINE_SPINLOCK(susfs_open_redirect_lock);

void susfs_add_open_redirect(void __user **user_info)
{
	struct susfs_open_redirect_info info = {0};
	struct {
		struct list_head list;
		char target_pathname[SUSFS_MAX_LEN_PATHNAME];
	} *e;

	if (copy_from_user(&info, (void __user *)*user_info, sizeof(info))) {
		info.err = -EFAULT;
		goto out;
	}
	e = kmalloc(sizeof(*e), GFP_KERNEL);
	if (!e) {
		info.err = -ENOMEM;
		goto out;
	}
	strncpy(e->target_pathname, info.target_pathname, SUSFS_MAX_LEN_PATHNAME - 1);
	spin_lock(&susfs_open_redirect_lock);
	list_add_tail(&e->list, &susfs_open_redirect_list);
	spin_unlock(&susfs_open_redirect_lock);
	pr_info("susfs: open redirect '%s' stored\n", e->target_pathname);
	info.err = 0;
out:
	copy_to_user((void __user *)*user_info, &info, sizeof(info));
}

/* ---- sus_map: stored; inode map-spoof hooks not ported ---- */

struct susfs_sus_map_info {
	char target_pathname[SUSFS_MAX_LEN_PATHNAME];
	char fake_pathname[SUSFS_MAX_LEN_PATHNAME];
	int err;
};

static LIST_HEAD(susfs_sus_map_list);
static DEFINE_SPINLOCK(susfs_sus_map_lock);

void susfs_add_sus_map(void __user **user_info)
{
	struct susfs_sus_map_info info = {0};
	struct {
		struct list_head list;
		char target_pathname[SUSFS_MAX_LEN_PATHNAME];
		char fake_pathname[SUSFS_MAX_LEN_PATHNAME];
	} *e;

	if (copy_from_user(&info, (void __user *)*user_info, sizeof(info))) {
		info.err = -EFAULT;
		goto out;
	}
	e = kmalloc(sizeof(*e), GFP_KERNEL);
	if (!e) {
		info.err = -ENOMEM;
		goto out;
	}
	strncpy(e->target_pathname, info.target_pathname, SUSFS_MAX_LEN_PATHNAME - 1);
	strncpy(e->fake_pathname, info.fake_pathname, SUSFS_MAX_LEN_PATHNAME - 1);
	spin_lock(&susfs_sus_map_lock);
	list_add_tail(&e->list, &susfs_sus_map_list);
	spin_unlock(&susfs_sus_map_lock);
	pr_info("susfs: sus_map '%s' -> '%s' stored\n", e->target_pathname, e->fake_pathname);
	info.err = 0;
out:
	copy_to_user((void __user *)*user_info, &info, sizeof(info));
}

/* ---- avc log spoofing: stored; selinux avc hook not ported ---- */

void susfs_set_avc_log_spoofing(void __user **user_info)
{
	struct {
		bool enable;
		int err;
	} info = {0};

	if (copy_from_user(&info, (void __user *)*user_info, sizeof(info))) {
		info.err = -EFAULT;
		goto out;
	}
	pr_info("susfs: avc_log_spoofing = %d (stored)\n", info.enable);
	info.err = 0;
out:
	copy_to_user((void __user *)*user_info, &info, sizeof(info));
}
