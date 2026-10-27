#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <linux/input.h>
#include <sys/types.h>
#include <sys/stat.h>

#define VOL_STEP_SIZE 3
#define VOL_MAX 30
#define VOL_MIN 0
#define GAIN_MAX 35

static int g_volume = 15;
static int g_muted = 0;
static volatile sig_atomic_t g_running = 1;

static void sig_handler(int sig) {
    (void)sig;
    g_running = 0;
}

static void apply_mute_state(int muted) {
    g_muted = muted;
    if (g_muted) {
        system("/system/bin/tinymix 'ADCFGA Left Mute Switch' 1 >/dev/null 2>&1");
        system("/system/bin/tinymix 'ADCFGA Right Mute Switch' 1 >/dev/null 2>&1");
        system("/system/bin/tinymix 'Mic PGA Switch' 0 0 >/dev/null 2>&1");
        system("/system/bin/tinymix 'ADC_A Left Mute' 1 >/dev/null 2>&1; "
               "/system/bin/tinymix 'ADC_A Right Mute' 1 >/dev/null 2>&1; "
               "/system/bin/tinymix 'ADC_B Left Mute' 1 >/dev/null 2>&1; "
               "/system/bin/tinymix 'ADC_B Right Mute' 1 >/dev/null 2>&1; "
               "/system/bin/tinymix 'ADC_C Left Mute' 1 >/dev/null 2>&1; "
               "/system/bin/tinymix 'ADC_C Right Mute' 1 >/dev/null 2>&1; "
               "/system/bin/tinymix 'ADC_D Left Mute' 1 >/dev/null 2>&1; "
               "/system/bin/tinymix 'ADC_D Right Mute' 1 >/dev/null 2>&1");
        system("/system/bin/ledctrl -c >/dev/null 2>&1");
        system("/system/bin/ledctrl -s solid_red -b 80 >/dev/null 2>&1");
        printf("[tad_buttonsd] Microphone MUTED (LED red)\n");
    } else {
        system("/system/bin/tinymix 'ADCFGA Left Mute Switch' 0 >/dev/null 2>&1");
        system("/system/bin/tinymix 'ADCFGA Right Mute Switch' 0 >/dev/null 2>&1");
        system("/system/bin/tinymix 'Mic PGA Switch' 1 1 >/dev/null 2>&1");
        system("/system/bin/tinymix 'ADC_A Left Mute' 0 >/dev/null 2>&1; "
               "/system/bin/tinymix 'ADC_A Right Mute' 0 >/dev/null 2>&1; "
               "/system/bin/tinymix 'ADC_B Left Mute' 0 >/dev/null 2>&1; "
               "/system/bin/tinymix 'ADC_B Right Mute' 0 >/dev/null 2>&1; "
               "/system/bin/tinymix 'ADC_C Left Mute' 0 >/dev/null 2>&1; "
               "/system/bin/tinymix 'ADC_C Right Mute' 0 >/dev/null 2>&1; "
               "/system/bin/tinymix 'ADC_D Left Mute' 0 >/dev/null 2>&1; "
               "/system/bin/tinymix 'ADC_D Right Mute' 0 >/dev/null 2>&1");
        system("/system/bin/ledctrl -c >/dev/null 2>&1");
        system("/system/bin/ledctrl -s solid_green -b 50 >/dev/null 2>&1");
        printf("[tad_buttonsd] Microphone UNMUTED (LED green)\n");
    }
    fflush(stdout);
}

static void apply_volume(int vol) {
    if (vol < VOL_MIN) vol = VOL_MIN;
    if (vol > VOL_MAX) vol = VOL_MAX;
    g_volume = vol;

    int gain = (g_volume * GAIN_MAX) / VOL_MAX;
    char cmd[128];
    snprintf(cmd, sizeof(cmd), "/system/bin/tinymix 'HP Driver Gain Volume' %d %d >/dev/null 2>&1", gain, gain);
    system(cmd);

    char led_anim[64];
    if (g_volume == 0) {
        snprintf(led_anim, sizeof(led_anim), "volume_muted");
    } else {
        snprintf(led_anim, sizeof(led_anim), "volume_step-%02d", g_volume);
    }

    snprintf(cmd, sizeof(cmd), "/system/bin/ledctrl -s %s -b 80 >/dev/null 2>&1", led_anim);
    system(cmd);
    printf("[tad_buttonsd] Volume set to %d/30 (gain %d), animation: %s\n", g_volume, gain, led_anim);
    fflush(stdout);

    // Fork a child to revert LED after 2 seconds
    pid_t pid = fork();
    if (pid == 0) {
        sleep(2);
        if (g_muted) {
            system("/system/bin/ledctrl -s solid_red -b 80 >/dev/null 2>&1");
        } else {
            system("/system/bin/ledctrl -s solid_green -b 50 >/dev/null 2>&1");
        }
        _exit(0);
    }
}

int main(void) {
    signal(SIGTERM, sig_handler);
    signal(SIGINT, sig_handler);
    signal(SIGCHLD, SIG_IGN); // prevent zombies from fork

    printf("[tad_buttonsd] Starting TAD Hardware Button Monitor for Echo Dot 2G...\n");
    fflush(stdout);

    int fd1 = open("/dev/input/event1", O_RDONLY | O_NONBLOCK);
    int fd2 = open("/dev/input/event2", O_RDONLY | O_NONBLOCK);

    if (fd1 < 0 && fd2 < 0) {
        fprintf(stderr, "[tad_buttonsd] Failed to open /dev/input/event1 and event2\n");
        return 1;
    }

    struct pollfd fds[2];
    int nfds = 0;

    if (fd1 >= 0) {
        fds[nfds].fd = fd1;
        fds[nfds].events = POLLIN;
        nfds++;
    }
    if (fd2 >= 0) {
        fds[nfds].fd = fd2;
        fds[nfds].events = POLLIN;
        nfds++;
    }

    // Initialize to unmuted green state
    apply_mute_state(0);

    struct input_event ev;

    while (g_running) {
        int ret = poll(fds, nfds, -1);
        if (ret < 0) {
            break;
        }

        for (int i = 0; i < nfds; i++) {
            if (fds[i].revents & POLLIN) {
                while (read(fds[i].fd, &ev, sizeof(ev)) == sizeof(ev)) {
                    if (ev.type == EV_KEY && ev.value == 1) { // Key pressed (down)
                        switch (ev.code) {
                            case 113: // KEY_MUTE
                                printf("[tad_buttonsd] Button: MUTE\n");
                                apply_mute_state(!g_muted);
                                break;
                            case 115: // KEY_VOLUMEUP
                                printf("[tad_buttonsd] Button: VOLUME UP\n");
                                apply_volume(g_volume + VOL_STEP_SIZE);
                                break;
                            case 114: // KEY_VOLUMEDOWN
                                printf("[tad_buttonsd] Button: VOLUME DOWN\n");
                                apply_volume(g_volume - VOL_STEP_SIZE);
                                break;
                            case 138: // KEY_HELP (Action button)
                                printf("[tad_buttonsd] Button: ACTION (KEY_HELP)\n");
                                system("/system/bin/ledctrl -s solid_blue -b 85 >/dev/null 2>&1");
                                pid_t apid = fork();
                                if (apid == 0) {
                                    sleep(3);
                                    if (g_muted) {
                                        system("/system/bin/ledctrl -s solid_red -b 80 >/dev/null 2>&1");
                                    } else {
                                        system("/system/bin/ledctrl -s solid_green -b 50 >/dev/null 2>&1");
                                    }
                                    _exit(0);
                                }
                                break;
                            default:
                                break;
                        }
                    }
                }
            }
        }
    }

    if (fd1 >= 0) close(fd1);
    if (fd2 >= 0) close(fd2);
    printf("[tad_buttonsd] Exiting.\n");
    return 0;
}
