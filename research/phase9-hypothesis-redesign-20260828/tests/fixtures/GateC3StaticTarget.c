#define _GNU_SOURCE
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

extern char **environ;

int main(int argc, char **argv) {
    if (argc == 1) {
        return 0;
    }
    if (argc == 2 && strcmp(argv[1], "--exec-other") == 0) {
        char *other[] = {"/bin/true", NULL};
        errno = 0;
        syscall(__NR_execve, other[0], other, environ);
        if (errno == EACCES) {
            puts("second_exec_denied=PASS");
            return 0;
        }
        perror("unexpected second exec result");
        return 1;
    }
    return 64;
}
