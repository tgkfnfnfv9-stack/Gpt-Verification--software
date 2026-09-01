#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/landlock.h>
#include <linux/seccomp.h>
#include <netinet/in.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

extern char **environ;

#ifndef CLOSE_RANGE_UNSHARE
#define CLOSE_RANGE_UNSHARE (1U << 1)
#endif
#ifndef SOCK_TYPE_MASK
#define SOCK_TYPE_MASK 0xf
#endif

#define DENY_ERRNO(number, error_number) \
    BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, (number), 0, 1), \
    BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | ((error_number) & SECCOMP_RET_DATA))

static void install_seccomp(void) {
    struct sock_filter instructions[] = {
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, arch)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AUDIT_ARCH_X86_64, 1, 0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
        BPF_JUMP(BPF_JMP | BPF_JSET | BPF_K, 0x40000000U, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        DENY_ERRNO(__NR_fork, EPERM),
        DENY_ERRNO(__NR_vfork, EPERM),
        DENY_ERRNO(__NR_clone3, ENOSYS),
        DENY_ERRNO(__NR_execveat, EPERM),
        DENY_ERRNO(__NR_setns, EPERM),
        DENY_ERRNO(__NR_unshare, EPERM),
        DENY_ERRNO(__NR_ptrace, EPERM),
        DENY_ERRNO(__NR_process_vm_readv, EPERM),
        DENY_ERRNO(__NR_process_vm_writev, EPERM),
        DENY_ERRNO(__NR_pidfd_getfd, EPERM),
        DENY_ERRNO(__NR_mount, EPERM),
        DENY_ERRNO(__NR_umount2, EPERM),
        DENY_ERRNO(__NR_bpf, EPERM),
        DENY_ERRNO(__NR_bind, EPERM),
        DENY_ERRNO(__NR_listen, EPERM),
        DENY_ERRNO(__NR_accept, EPERM),
        DENY_ERRNO(__NR_accept4, EPERM),
        DENY_ERRNO(__NR_sendto, EPERM),
        DENY_ERRNO(__NR_sendmsg, EPERM),
        DENY_ERRNO(__NR_sendmmsg, EPERM),
        DENY_ERRNO(__NR_io_uring_setup, EPERM),
        DENY_ERRNO(__NR_io_uring_enter, EPERM),
        DENY_ERRNO(__NR_io_uring_register, EPERM),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_socket, 0, 7),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, args[0])),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AF_INET, 1, 0),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AF_INET6, 0, 3),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, args[1])),
        BPF_STMT(BPF_ALU | BPF_AND | BPF_K, SOCK_TYPE_MASK),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SOCK_STREAM, 1, 0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_clone, 0, 4),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, args[0])),
        BPF_STMT(BPF_ALU | BPF_AND | BPF_K, 0x00010000U),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, 0, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
    };
    struct sock_fprog program = {
        .len = (unsigned short)(sizeof(instructions) / sizeof(instructions[0])),
        .filter = instructions,
    };
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0 ||
        prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program) != 0) {
        perror("metadata seccomp");
        exit(70);
    }
}

static void sanitize_inherited_descriptors(void) {
    struct stat info;
    for (int descriptor = STDIN_FILENO; descriptor <= STDERR_FILENO; descriptor++) {
        if (fstat(descriptor, &info) != 0 || S_ISSOCK(info.st_mode)) {
            fprintf(stderr, "socket-backed or invalid standard descriptor\n");
            exit(78);
        }
    }
#ifdef __NR_close_range
    if (syscall(__NR_close_range, 3U, ~0U, CLOSE_RANGE_UNSHARE) == 0) return;
    if (errno != ENOSYS && errno != EINVAL) { perror("close_range"); exit(79); }
#endif
    long maximum = sysconf(_SC_OPEN_MAX);
    if (maximum < 0 || maximum > 1048576) maximum = 1048576;
    for (int descriptor = 3; descriptor < maximum; descriptor++) close(descriptor);
}

static void install_landlock(const char *target, uint16_t allowed_port) {
    struct landlock_ruleset_attr ruleset = {
        .handled_access_fs = LANDLOCK_ACCESS_FS_EXECUTE
                | LANDLOCK_ACCESS_FS_WRITE_FILE
                | LANDLOCK_ACCESS_FS_REMOVE_DIR
                | LANDLOCK_ACCESS_FS_REMOVE_FILE
                | LANDLOCK_ACCESS_FS_MAKE_CHAR
                | LANDLOCK_ACCESS_FS_MAKE_DIR
                | LANDLOCK_ACCESS_FS_MAKE_REG
                | LANDLOCK_ACCESS_FS_MAKE_SOCK
                | LANDLOCK_ACCESS_FS_MAKE_FIFO
                | LANDLOCK_ACCESS_FS_MAKE_BLOCK
                | LANDLOCK_ACCESS_FS_MAKE_SYM
                | LANDLOCK_ACCESS_FS_REFER
                | LANDLOCK_ACCESS_FS_TRUNCATE,
        .handled_access_net = LANDLOCK_ACCESS_NET_CONNECT_TCP,
    };
    int abi = (int)syscall(__NR_landlock_create_ruleset, NULL, 0, LANDLOCK_CREATE_RULESET_VERSION);
    if (abi < 4) {
        fprintf(stderr, "Landlock network ABI 4 required\n");
        exit(71);
    }
    int ruleset_fd = (int)syscall(__NR_landlock_create_ruleset, &ruleset, sizeof(ruleset), 0);
    if (ruleset_fd < 0) { perror("landlock_create_ruleset"); exit(72); }
    int target_fd = open(target, O_PATH | O_CLOEXEC);
    if (target_fd < 0) { perror("open exact target"); exit(73); }
    struct landlock_path_beneath_attr path_rule = {
        .allowed_access = LANDLOCK_ACCESS_FS_EXECUTE,
        .parent_fd = target_fd,
    };
    if (syscall(__NR_landlock_add_rule, ruleset_fd, LANDLOCK_RULE_PATH_BENEATH, &path_rule, 0) != 0) {
        perror("landlock exact executable"); exit(74);
    }
    struct landlock_net_port_attr net_rule = {
        .allowed_access = LANDLOCK_ACCESS_NET_CONNECT_TCP,
        .port = allowed_port,
    };
    if (syscall(__NR_landlock_add_rule, ruleset_fd, LANDLOCK_RULE_NET_PORT, &net_rule, 0) != 0) {
        perror("landlock exact port"); exit(75);
    }
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0 ||
        syscall(__NR_landlock_restrict_self, ruleset_fd, 0) != 0) {
        perror("landlock_restrict_self"); exit(76);
    }
    close(target_fd);
    close(ruleset_fd);
}

int main(int argc, char **argv) {
    if (argc < 4 || strcmp(argv[2], "--") != 0) {
        fprintf(stderr, "usage: guard allowed_port -- exact_target [args...]\n");
        return 64;
    }
    char *end = NULL;
    unsigned long port = strtoul(argv[1], &end, 10);
    if (*argv[1] == '\0' || *end != '\0' || port != 38443UL || argv[3][0] != '/') {
        fprintf(stderr, "Only the frozen synthetic destination is accepted\n");
        return 65;
    }
    sanitize_inherited_descriptors();
    install_landlock(argv[3], (uint16_t)port);
    install_seccomp();
    execve(argv[3], &argv[3], environ);
    perror("exec exact metadata target");
    return 77;
}
