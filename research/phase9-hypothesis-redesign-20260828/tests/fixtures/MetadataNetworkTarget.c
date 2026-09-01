#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <sched.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

static int connect_target(const char *address, int port) {
    int descriptor = socket(AF_INET, SOCK_STREAM, 0);
    if (descriptor < 0) return -1;
    struct sockaddr_in target = {0};
    target.sin_family = AF_INET;
    target.sin_port = htons((uint16_t)port);
    inet_pton(AF_INET, address, &target.sin_addr);
    int result = connect(descriptor, (struct sockaddr *)&target, sizeof(target));
    int saved_errno = errno;
    close(descriptor);
    errno = saved_errno;
    return result;
}

int main(void) {
    if (connect_target("198.18.0.1", 38443) != 0) { perror("allowed connect"); return 1; }
    errno = 0;
    if (connect_target("198.18.0.1", 38444) != -1 || errno != EACCES) {
        fprintf(stderr, "non-allowlisted port was not denied by Landlock: %s\n", strerror(errno));
        return 2;
    }
    errno = 0;
    if (connect_target("198.18.0.3", 38443) != -1
            || (errno != ENETUNREACH && errno != EHOSTUNREACH)) {
        fprintf(stderr, "non-routed address was not denied: %s\n", strerror(errno));
        return 6;
    }
    errno = 0;
    if (socket(AF_INET, SOCK_DGRAM, 0) != -1 || errno != EPERM) {
        fprintf(stderr, "UDP was not denied\n"); return 3;
    }
    errno = 0;
    if (socket(AF_INET, SOCK_RAW, 0) != -1 || errno != EPERM) {
        fprintf(stderr, "raw socket was not denied\n"); return 5;
    }
    errno = 0;
    if (socket(AF_UNIX, SOCK_STREAM, 0) != -1 || errno != EPERM) {
        fprintf(stderr, "AF_UNIX was not denied\n"); return 9;
    }
    errno = 0;
    if (open("/tmp/phase9-metadata-write-must-fail", O_WRONLY | O_CREAT, 0600) != -1
            || errno != EACCES) {
        fprintf(stderr, "outside write was not denied\n"); return 10;
    }
    errno = 0;
    if (fork() != -1 || errno != EPERM) {
        fprintf(stderr, "fork was not denied\n"); return 4;
    }
    errno = 0;
    if (setns(-1, 0) != -1 || errno != EPERM) {
        fprintf(stderr, "setns was not denied\n"); return 7;
    }
    errno = 0;
    if (unshare(0) != -1 || errno != EPERM) {
        fprintf(stderr, "unshare was not denied\n"); return 8;
    }
    puts("phase9_metadata_network_synthetic=PASS");
    return 0;
}
