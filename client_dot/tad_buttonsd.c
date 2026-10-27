#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <time.h>
#include <linux/input.h>
#include <sys/types.h>
#include <sys/stat.h>

#define VOL_STEP_SIZE 3
#define VOL_MAX 30
#define VOL_MIN 0
#define GAIN_MAX 35

static int g_volume = 15;
static int g_muted = 0;
static int g_vol_timer_ticks = 0; // Number of 100ms ticks remaining for volume LED display
static int g_action_timer_ticks = 0;
static volatile sig_atomic_t g_running = 1;

static void sig_handler(int sig) {
    (void)sig;
    g_running = 0;
}

static void apply_mute_state(int muted) {
    g_muted = muted;
    g_vol_timer_ticks = 0; // Cancel any volume display override
    g_action_timer_ticks = 0;

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
        system("/system/bin/ledctrl -c >/dev/null 2>&1 && /system/bin/ledctrl -s solid_red -b 80 >/dev/null 2>&1");
        printf("[tad_buttonsd] Microphone MUTED (LED solid_red)\n");
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
        system("/system/bin/ledctrl -c >/dev/null 2>&1 && /system/bin/ledctrl -s solid_green -b 50 >/dev/null 2>&1");
        printf("[tad_buttonsd] Microphone UNMUTED (LED solid_green)\n");
    }
    fflush(stdout);
}

static void apply_volume(int delta) {
    int new_vol = g_volume + delta;
    if (new_vol < VOL_MIN) new_vol = VOL_MIN;
    if (new_vol > VOL_MAX) new_vol = VOL_MAX;
    g_volume = new_vol;

    int gain = (g_volume * GAIN_MAX) / VOL_MAX;
    char cmd[128];
    snprintf(cmd, sizeof(cmd), "/system/bin/tinymix 'HP Driver Gain Volume' %d %d >/dev/null 2>&1", gain, gain);
    system(cmd);

    char led_anim[64];
    if (g_volume == 0) {
        snprintf(led_anim, sizeof(led_anim), "volume-muted");
    } else {
        snprintf(led_anim, sizeof(led_anim), "volume_step-%02d", g_volume);
    }

    // Clear previous pattern and immediately display the volume arc
    snprintf(cmd, sizeof(cmd), "/system/bin/ledctrl -c >/dev/null 2>&1 && /system/bin/ledctrl -s %s -b 100 >/dev/null 2>&1", led_anim);
    system(cmd);

    // Reset volume display timer to 20 ticks (2.0 seconds) after THIS button press
    g_vol_timer_ticks = 20;

    printf("[tad_buttonsd] Volume adjusted: %d/30 (gain %d), animation: %s\n", g_volume, gain, led_anim);
    fflush(stdout);
}

static void restore_standby_led(void) {
    if (g_muted) {
        system("/system/bin/ledctrl -c >/dev/null 2>&1 && /system/bin/ledctrl -s solid_red -b 80 >/dev/null 2>&1");
    } else {
        system("/system/bin/ledctrl -c >/dev/null 2>&1 && /system/bin/ledctrl -s solid_green -b 50 >/dev/null 2>&1");
    }
    printf("[tad_buttonsd] Standby LED restored (%s)\n", g_muted ? "red" : "green");
    fflush(stdout);
}

int main(int argc, char *argv[]) {
    int do_daemon = 1;
    if (argc > 1 && strcmp(argv[1], "-f") == 0) {
        do_daemon = 0;
    }

    if (do_daemon) {
        pid_t pid = fork();
        if (pid < 0) exit(1);
        if (pid > 0) exit(0); // Parent exits immediately
        setsid();             // Detach completely from terminal/session
        signal(SIGHUP, SIG_IGN);

        int log_fd = open("/data/adb/tad_buttons.log", O_WRONLY | O_CREAT | O_APPEND, 0644);
        if (log_fd >= 0) {
            dup2(log_fd, STDOUT_FILENO);
            dup2(log_fd, STDERR_FILENO);
            close(log_fd);
        }
    }

    signal(SIGTERM, sig_handler);
    signal(SIGINT, sig_handler);

    printf("[tad_buttonsd] Starting TAD Hardware Button Monitor for Echo Dot 2G (PID %d)...\n", getpid());
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

    // Set initial unmuted green state
    apply_mute_state(0);

    struct input_event ev;

    while (g_running) {
        // Poll with 100ms timeout for clean timer debouncing
        int ret = poll(fds, nfds, 100);

        if (ret > 0) {
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
                                    printf("[tad_buttonsd] Button: VOLUME UP (+3)\n");
                                    apply_volume(+VOL_STEP_SIZE);
                                    break;
                                case 114: // KEY_VOLUMEDOWN
                                    printf("[tad_buttonsd] Button: VOLUME DOWN (-3)\n");
                                    apply_volume(-VOL_STEP_SIZE);
                                    break;
                                case 138: // KEY_HELP (Action button)
                                    printf("[tad_buttonsd] Button: ACTION (KEY_HELP)\n");
                                    system("/system/bin/ledctrl -c >/dev/null 2>&1 && /system/bin/ledctrl -s active-thinking -b 85 >/dev/null 2>&1");
                                    g_action_timer_ticks = 30; // 3 seconds of action animation
                                    break;
                                default:
                                    break;
                            }
                        }
                    }
                }
            }
        }

        // Handle volume display timeout (revert to standby after 2.0s without button press)
        if (g_vol_timer_ticks > 0) {
            g_vol_timer_ticks--;
            if (g_vol_timer_ticks == 0) {
                restore_standby_led();
            }
        }

        // Handle action button animation timeout
        if (g_action_timer_ticks > 0) {
            g_action_timer_ticks--;
            if (g_action_timer_ticks == 0 && g_vol_timer_ticks == 0) {
                restore_standby_led();
            }
        }
    }

    if (fd1 >= 0) close(fd1);
    if (fd2 >= 0) close(fd2);
    printf("[tad_buttonsd] Exiting.\n");
    return 0;
}
