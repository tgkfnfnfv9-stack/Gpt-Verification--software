#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/landlock.h>
#include <linux/seccomp.h>
#include <netinet/in.h>
#include <limits.h>
#include <pthread.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

#ifndef CLOSE_RANGE_UNSHARE
#define CLOSE_RANGE_UNSHARE (1U << 1)
#endif

#define DENY_ERRNO(syscall_number, error_number) \
    BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, (syscall_number), 0, 1), \
    BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | ((error_number) & SECCOMP_RET_DATA))

static void install_filter(void) {
    struct sock_filter instructions[] = {
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, arch)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AUDIT_ARCH_X86_64, 1, 0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
        BPF_JUMP(BPF_JMP | BPF_JSET | BPF_K, 0x40000000U, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_socket, 0, 4),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, args[0])),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AF_UNIX, 2, 0),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AF_INET6, 1, 0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_socketpair, 0, 3),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, args[0])),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AF_UNIX, 1, 0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
        DENY_ERRNO(__NR_fork, EPERM),
        DENY_ERRNO(__NR_vfork, EPERM),
        DENY_ERRNO(__NR_clone3, ENOSYS),
        DENY_ERRNO(__NR_execveat, EPERM),
        DENY_ERRNO(__NR_connect, EPERM),
        DENY_ERRNO(__NR_bind, EPERM),
        DENY_ERRNO(__NR_listen, EPERM),
        DENY_ERRNO(__NR_accept, EPERM),
        DENY_ERRNO(__NR_accept4, EPERM),
        DENY_ERRNO(__NR_sendto, EPERM),
        DENY_ERRNO(__NR_sendmsg, EPERM),
        DENY_ERRNO(__NR_sendmmsg, EPERM),
        DENY_ERRNO(__NR_recvfrom, EPERM),
        DENY_ERRNO(__NR_recvmsg, EPERM),
        DENY_ERRNO(__NR_recvmmsg, EPERM),
        DENY_ERRNO(__NR_shutdown, EPERM),
        DENY_ERRNO(__NR_io_uring_setup, EPERM),
        DENY_ERRNO(__NR_io_uring_enter, EPERM),
        DENY_ERRNO(__NR_io_uring_register, EPERM),
        DENY_ERRNO(__NR_ptrace, EPERM),
        DENY_ERRNO(__NR_process_vm_writev, EPERM),
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
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0) {
        perror("PR_SET_NO_NEW_PRIVS");
        exit(70);
    }
    if (prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program) != 0) {
        perror("PR_SET_SECCOMP");
        exit(71);
    }
}

static void sanitize_inherited_descriptors(void) {
    struct stat info;
    for (int descriptor = STDIN_FILENO; descriptor <= STDERR_FILENO; descriptor++) {
        if (fstat(descriptor, &info) != 0) {
            perror("fstat standard descriptor");
            exit(74);
        }
        if (S_ISSOCK(info.st_mode)) {
            fprintf(stderr, "socket-backed standard descriptors are prohibited\n");
            exit(75);
        }
    }
#ifdef __NR_close_range
    if (syscall(__NR_close_range, 3U, ~0U, CLOSE_RANGE_UNSHARE) == 0) {
        return;
    }
    if (errno != ENOSYS && errno != EINVAL) {
        perror("close_range");
        exit(76);
    }
#endif
    long maximum = sysconf(_SC_OPEN_MAX);
    if (maximum < 0 || maximum > 1048576) {
        maximum = 1048576;
    }
    for (int descriptor = 3; descriptor < maximum; descriptor++) {
        close(descriptor);
    }
}

static void install_execute_landlock(const char *target) {
    struct landlock_ruleset_attr ruleset = {
        .handled_access_fs = LANDLOCK_ACCESS_FS_EXECUTE,
    };
    int abi = (int)syscall(__NR_landlock_create_ruleset, NULL, 0, LANDLOCK_CREATE_RULESET_VERSION);
    if (abi < 1) {
        perror("Landlock ABI unavailable");
        exit(85);
    }
    int ruleset_fd = (int)syscall(
        __NR_landlock_create_ruleset, &ruleset, sizeof(ruleset), 0);
    if (ruleset_fd < 0) {
        perror("landlock_create_ruleset");
        exit(86);
    }
    int target_fd = open(target, O_PATH | O_CLOEXEC);
    if (target_fd < 0) {
        perror("open exact executable");
        exit(87);
    }
    struct landlock_path_beneath_attr rule = {
        .allowed_access = LANDLOCK_ACCESS_FS_EXECUTE,
        .parent_fd = target_fd,
    };
    if (syscall(__NR_landlock_add_rule, ruleset_fd, LANDLOCK_RULE_PATH_BENEATH, &rule, 0) != 0) {
        perror("landlock_add_rule");
        exit(88);
    }
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0) {
        perror("PR_SET_NO_NEW_PRIVS for Landlock");
        exit(89);
    }
    if (syscall(__NR_landlock_restrict_self, ruleset_fd, 0) != 0) {
        perror("landlock_restrict_self");
        exit(90);
    }
    close(target_fd);
    close(ruleset_fd);
}

static void *thread_probe(void *unused) {
    (void)unused;
    return NULL;
}

static int expect_errno(long result, int expected, const char *label) {
    if (result != -1 || errno != expected) {
        fprintf(stderr, "%s was not rejected with errno %d\n", label, expected);
        return 1;
    }
    return 0;
}

static int self_test(void) {
    int failures = 0;
    pthread_t thread;
    int inherited[2];
    if (socketpair(AF_UNIX, SOCK_STREAM, 0, inherited) != 0) {
        perror("socketpair inherited descriptor probe");
        return 72;
    }
    int inherited_number = inherited[0];
    sanitize_inherited_descriptors();
    errno = 0;
    failures += expect_errno((long)fcntl(inherited_number, F_GETFD), EBADF, "inherited descriptor closure");
    install_filter();
    if (pthread_create(&thread, NULL, thread_probe, NULL) != 0 || pthread_join(thread, NULL) != 0) {
        fprintf(stderr, "CLONE_THREAD was not allowed\n");
        failures++;
    }
    errno = 0;
    failures += expect_errno((long)fork(), EPERM, "fork");
    errno = 0;
    failures += expect_errno(syscall(__NR_clone3, NULL, 0), ENOSYS, "clone3");
    errno = 0;
    failures += expect_errno(syscall(__NR_execveat, -1, "", NULL, NULL, 0), EPERM, "execveat");
    errno = 0;
    failures += expect_errno(syscall(0x40000000U | __NR_connect, -1, NULL, 0), EPERM, "x32 syscall namespace");
    errno = 0;
    failures += expect_errno((long)socket(AF_NETLINK, SOCK_RAW, 0), EPERM, "AF_NETLINK socket");
    errno = 0;
    failures += expect_errno((long)socket(AF_PACKET, SOCK_RAW, 0), EPERM, "AF_PACKET socket");
    int descriptor = socket(AF_INET6, SOCK_STREAM, 0);
    if (descriptor < 0) {
        perror("socket");
        failures++;
    } else {
        struct sockaddr_in6 address;
        memset(&address, 0, sizeof(address));
        address.sin6_family = AF_INET6;
        errno = 0;
        failures += expect_errno(connect(descriptor, (struct sockaddr *)&address, sizeof(address)), EPERM, "connect");
        close(descriptor);
    }
    if (failures != 0) {
        return 72;
    }
    puts("phase9_gate_c3_seccomp_self_test=PASS");
    return 0;
}

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "--self-test") == 0) {
        return self_test();
    }
    if (argc < 3 || strcmp(argv[1], "--") != 0) {
        fprintf(stderr, "usage: phase9_gate_c3_seccomp -- command [args...]\n");
        return 64;
    }
    sanitize_inherited_descriptors();
    char canonical[PATH_MAX];
    if (argv[2][0] != '/' || realpath(argv[2], canonical) == NULL) {
        fprintf(stderr, "command must be an existing absolute executable\n");
        return 65;
    }
    install_execute_landlock(canonical);
    install_filter();
    syscall(__NR_execve, canonical, &argv[2], environ);
    perror("execve exact executable");
    return 73;
}
