/*
 * tad_dotd.c - Unified Native Hardware Daemon for Amazon Echo Dot 2G (biscuit)
 *
 * Replaces ADB shell overhead & busybox nc pipes with zero-latency native C:
 *   1. Hardware Buttons (/dev/input/event1 & event2):
 *      - Mute (113): Hardware ALSA ADC mute + Red LED + EVT MUTE 0|1
 *      - Vol+ (115) / Vol- (114): Hardware HP Driver Gain + volume_step LED + EVT VOL
 *      - Action (138): Instant Barge-In STOP if playing, else Wake trigger (EVT ACTION)
 *   2. TCP :9000 - Raw 9-channel 16kHz S24_3LE Microphone Stream (tinycap -f)
 *   3. TCP :9001 - Control, Instant LED (<5ms), Streaming WAV Playback & Barge-In:
 *      - PING                       -> PONG vol=<v> muted=<m> playing=<p>
 *      - LED <pattern> <brightness> -> OK LED
 *      - VOL <0..30>                -> OK VOL <v>
 *      - STOP                       -> OK STOP (kills tinyplay immediately + mutes amp)
 *      - PLAY <nbytes>\n<wav_bytes> -> OK PLAY_STARTED (async tinyplay -> EVT PLAY_DONE)
 */

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define MIC_PORT 9000
#define CTRL_PORT 9001

#define VOL_STEP_SIZE 3
#define VOL_MAX 30
#define VOL_MIN 0
#define GAIN_MAX 35
#define MAX_WAV_BYTES (16 * 1024 * 1024)

static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
static volatile sig_atomic_t g_running = 1;

static int g_volume = 18;
static int g_muted = 0;
static int g_amp_gain_db = 12;
static char g_current_led[64] = "solid_green";
static int g_current_bri = 40;

static int g_ctrl_client_fd = -1;
static pid_t g_play_pid = -1;

static int g_vol_timer_ticks = 0;

static void sig_handler(int sig) {
    (void)sig;
    g_running = 0;
}

static int run_exec(char *const argv[]) {
    pid_t pid = fork();
    if (pid < 0) return -1;
    if (pid == 0) {
        int devnull = open("/dev/null", O_RDWR);
        if (devnull >= 0) {
            dup2(devnull, STDIN_FILENO);
            dup2(devnull, STDOUT_FILENO);
            dup2(devnull, STDERR_FILENO);
            if (devnull > 2) close(devnull);
        }
        execv(argv[0], argv);
        _exit(127);
    }
    int status = 0;
    while (waitpid(pid, &status, 0) < 0) {
        if (errno != EINTR) break;
    }
    return status;
}

static void tinymix_set2(const char *ctrl, const char *v1) {
    char *const argv[] = {"/system/bin/tinymix", (char *)ctrl, (char *)v1, NULL};
    run_exec(argv);
}

static void tinymix_set3(const char *ctrl, const char *v1, const char *v2) {
    char *const argv[] = {"/system/bin/tinymix", (char *)ctrl, (char *)v1, (char *)v2, NULL};
    run_exec(argv);
}

static void ledctrl_apply(const char *pattern, int brightness) {
    if (brightness < 0) brightness = 0;
    if (brightness > 100) brightness = 100;
    char bri_str[16];
    snprintf(bri_str, sizeof(bri_str), "%d", brightness);

    char *const clr_argv[] = {"/system/bin/ledctrl", "-c", NULL};
    run_exec(clr_argv);

    char *const set_argv[] = {"/system/bin/ledctrl", "-s", (char *)pattern, "-b", bri_str, NULL};
    run_exec(set_argv);
}

static void send_ctrl_line_locked(const char *line) {
    if (g_ctrl_client_fd >= 0) {
        size_t len = strlen(line);
        ssize_t n = send(g_ctrl_client_fd, line, len, MSG_NOSIGNAL);
        (void)n;
    }
}

static void speaker_amp_enable_locked(void) {
    int gain = (g_volume * GAIN_MAX) / VOL_MAX;
    if (gain < 8) gain = 8;
    if (gain > GAIN_MAX) gain = GAIN_MAX;
    char gain_str[16];
    snprintf(gain_str, sizeof(gain_str), "%d", gain);
    char amp_gain_str[16];
    snprintf(amp_gain_str, sizeof(amp_gain_str), "%ddB", g_amp_gain_db);
    tinymix_set3("HP Driver Gain Volume", gain_str, gain_str);
    tinymix_set3("LO Driver Gain Volume", gain_str, gain_str);
    tinymix_set2("Ext_Amp_Gain", amp_gain_str);
    tinymix_set2("Audio_DacMux_Setting", "Off");
    tinymix_set2("Right Channel Only", "On");
    tinymix_set2("HPL Output Mixer L_DAC Switch", "1");
    tinymix_set2("HPR Output Mixer R_DAC Switch", "1");
    tinymix_set2("LOL Output Mixer L_DAC Switch", "1");
    tinymix_set2("LOR Output Mixer R_DAC Switch", "1");
    tinymix_set3("HP DAC Playback Switch", "1", "1");
    tinymix_set3("LO DAC Playback Switch", "1", "1");
    tinymix_set2("Audio_Amp_R_Switch", "On");
    tinymix_set2("Audio_Amp_L_Switch", "On");
    tinymix_set2("Speaker_Amp_Switch", "On");
    tinymix_set2("Ext_Speaker_Amp_Switch", "On");
    tinymix_set2("MFP Gpio Mute", "Off");
}

static void speaker_amp_disable(void) {
    tinymix_set2("Speaker_Amp_Switch", "Off");
    tinymix_set2("Ext_Speaker_Amp_Switch", "Off");
    tinymix_set2("Audio_Amp_R_Switch", "Off");
    tinymix_set2("Audio_Amp_L_Switch", "Off");
    tinymix_set3("HP DAC Playback Switch", "0", "0");
    tinymix_set3("LO DAC Playback Switch", "0", "0");
}

static int stop_playback_locked(void) {
    if (g_play_pid > 0) {
        pid_t pid = g_play_pid;
        g_play_pid = -1;
        kill(pid, SIGKILL);
        speaker_amp_disable();
        return 1;
    }
    speaker_amp_disable();
    return 0;
}

static void restore_active_led_locked(void) {
    if (g_muted) {
        ledctrl_apply("solid_red", 80);
    } else {
        ledctrl_apply(g_current_led, g_current_bri);
    }
}

static void apply_mute_hardware(int muted) {
    const char *m_val = muted ? "1" : "0";
    const char *pga_val = muted ? "0" : "1";
    tinymix_set2("ADCFGA Left Mute Switch", m_val);
    tinymix_set2("ADCFGA Right Mute Switch", m_val);
    tinymix_set3("Mic PGA Switch", pga_val, pga_val);

    const char *adcs[] = {"ADC_A", "ADC_B", "ADC_C", "ADC_D"};
    for (int i = 0; i < 4; i++) {
        char left[32], right[32];
        snprintf(left, sizeof(left), "%s Left Mute", adcs[i]);
        snprintf(right, sizeof(right), "%s Right Mute", adcs[i]);
        tinymix_set2(left, m_val);
        tinymix_set2(right, m_val);
    }
}

static void set_volume_locked(int new_vol, int show_led) {
    if (new_vol < VOL_MIN) new_vol = VOL_MIN;
    if (new_vol > VOL_MAX) new_vol = VOL_MAX;
    g_volume = new_vol;

    int gain = (g_volume * GAIN_MAX) / VOL_MAX;
    char gain_str[16];
    snprintf(gain_str, sizeof(gain_str), "%d", gain);
    tinymix_set3("HP Driver Gain Volume", gain_str, gain_str);

    if (show_led) {
        char led_anim[64];
        if (g_volume == 0) {
            snprintf(led_anim, sizeof(led_anim), "volume-muted");
        } else {
            snprintf(led_anim, sizeof(led_anim), "volume_step-%02d", g_volume);
        }
        ledctrl_apply(led_anim, 100);
        g_vol_timer_ticks = 20; /* 2.0 seconds */
    }
}

struct play_watch_arg {
    pid_t pid;
};

static void *playback_watcher_thread(void *arg) {
    struct play_watch_arg *wa = (struct play_watch_arg *)arg;
    pid_t pid = wa->pid;
    free(wa);

    int status = 0;
    while (waitpid(pid, &status, 0) < 0) {
        if (errno != EINTR) break;
    }

    pthread_mutex_lock(&g_lock);
    if (g_play_pid == pid) {
        g_play_pid = -1;
        speaker_amp_disable();
        send_ctrl_line_locked("EVT PLAY_DONE\n");
    }
    pthread_mutex_unlock(&g_lock);
    return NULL;
}

static int create_listen_socket(int port) {
    int s = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (s < 0) return -1;

    int yes = 1;
    setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    addr.sin_port = htons((uint16_t)port);

    if (bind(s, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        close(s);
        return -1;
    }
    if (listen(s, 4) < 0) {
        close(s);
        return -1;
    }
    return s;
}

static int read_exact(int fd, unsigned char *buf, size_t total) {
    size_t got = 0;
    while (got < total) {
        ssize_t n = recv(fd, buf + got, total - got, 0);
        if (n <= 0) {
            if (n < 0 && errno == EINTR) continue;
            return -1;
        }
        got += (size_t)n;
    }
    return 0;
}

static int read_line_preempt(int srv_fd, int fd, char *line, size_t maxlen) {
    size_t pos = 0;
    while (pos + 1 < maxlen) {
        struct pollfd pfds[2];
        pfds[0].fd = srv_fd;
        pfds[0].events = POLLIN;
        pfds[1].fd = fd;
        pfds[1].events = POLLIN;

        int pr = poll(pfds, 2, -1);
        if (pr < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        if (pfds[0].revents & POLLIN) {
            /* New client waiting on listen socket -> preempt stale connection */
            return -1;
        }
        char c = 0;
        ssize_t n = recv(fd, &c, 1, 0);
        if (n <= 0) {
            if (n < 0 && errno == EINTR) continue;
            return -1;
        }
        if (c == '\r') continue;
        if (c == '\n') {
            line[pos] = '\0';
            return (int)pos;
        }
        line[pos++] = c;
    }
    line[pos] = '\0';
    return (int)pos;
}

/* ─── Thread 2: Microphone Raw Stream Server (:9000) ──────────────────────── */
static void *mic_server_thread(void *arg) {
    (void)arg;
    int srv = create_listen_socket(MIC_PORT);
    if (srv < 0) {
        fprintf(stderr, "[tad_dotd] Failed to bind mic port %d: %s\n", MIC_PORT, strerror(errno));
        return NULL;
    }
    printf("[tad_dotd] Mic stream server listening on 0.0.0.0:%d\n", MIC_PORT);
    fflush(stdout);

    const char *fifo_path = "/data/local/tmp/tad_dotd_mic.fifo";

    while (g_running) {
        struct sockaddr_in cli_addr;
        socklen_t cli_len = sizeof(cli_addr);
        int cli = accept(srv, (struct sockaddr *)&cli_addr, &cli_len);
        if (cli < 0) {
            if (errno == EINTR) continue;
            usleep(200000);
            continue;
        }

        fcntl(cli, F_SETFD, FD_CLOEXEC);
        int yes = 1;
        int user_timeout_ms = 30000;
        setsockopt(cli, IPPROTO_TCP, TCP_NODELAY, &yes, sizeof(yes));
        setsockopt(cli, SOL_SOCKET, SO_KEEPALIVE, &yes, sizeof(yes));
#ifdef TCP_USER_TIMEOUT
        setsockopt(cli, IPPROTO_TCP, TCP_USER_TIMEOUT, &user_timeout_ms, sizeof(user_timeout_ms));
#endif

        printf("[tad_dotd] Mic client connected (%s)\n", inet_ntoa(cli_addr.sin_addr));
        fflush(stdout);

        unlink(fifo_path);
        mkfifo(fifo_path, 0666);

        pid_t cap_pid = fork();
        if (cap_pid == 0) {
            int devnull = open("/dev/null", O_RDWR);
            if (devnull >= 0) {
                dup2(devnull, STDOUT_FILENO);
                dup2(devnull, STDERR_FILENO);
                if (devnull > 2) close(devnull);
            }
            char *const cap_argv[] = {
                "/system/bin/tinycap", (char *)fifo_path,
                "-D", "0", "-d", "24", "-c", "9", "-r", "16000",
                "-b", "24", "-f", "-p", "1024", "-n", "2", NULL
            };
            execv(cap_argv[0], cap_argv);
            _exit(127);
        }

        int fifo_fd = open(fifo_path, O_RDONLY);
        if (fifo_fd >= 0) {
            unsigned char buf[4320]; /* Exact multiple of 27-byte 9-ch frames (160 frames) */
            while (g_running) {
                struct pollfd srv_poll = { .fd = srv, .events = POLLIN, .revents = 0 };
                if (poll(&srv_poll, 1, 0) > 0 && (srv_poll.revents & POLLIN)) {
                    printf("[tad_dotd] Preempting active mic client for incoming connection.\n");
                    fflush(stdout);
                    break;
                }
                ssize_t r = read(fifo_fd, buf, sizeof(buf));
                if (r <= 0) {
                    if (r < 0 && errno == EINTR) continue;
                    break;
                }
                ssize_t off = 0;
                int send_err = 0;
                while (off < r) {
                    ssize_t s = send(cli, buf + off, (size_t)(r - off), MSG_NOSIGNAL);
                    if (s <= 0) {
                        if (s < 0 && errno == EINTR) continue;
                        send_err = 1;
                        break;
                    }
                    off += s;
                }
                if (send_err) break;
            }
            close(fifo_fd);
        }

        if (cap_pid > 0) {
            kill(cap_pid, SIGKILL);
            int st = 0;
            waitpid(cap_pid, &st, 0);
        }
        unlink(fifo_path);
        close(cli);
        printf("[tad_dotd] Mic client disconnected.\n");
        fflush(stdout);
    }

    close(srv);
    return NULL;
}

/* ─── Thread 3: Control, LED & Audio Playback Server (:9001) ──────────────── */
static void handle_ctrl_client(int srv, int cli) {
    char line[256];
    char reply[256];

    while (g_running) {
        int len = read_line_preempt(srv, cli, line, sizeof(line));
        if (len < 0) break;
        if (len == 0) continue;

        if (strcmp(line, "PING") == 0) {
            pthread_mutex_lock(&g_lock);
            snprintf(reply, sizeof(reply), "PONG vol=%d muted=%d playing=%d\n",
                     g_volume, g_muted, (g_play_pid > 0) ? 1 : 0);
            send_ctrl_line_locked(reply);
            pthread_mutex_unlock(&g_lock);
        } else if (strncmp(line, "LED ", 4) == 0) {
            char pattern[64] = {0};
            int bri = 80;
            if (sscanf(line + 4, "%63s %d", pattern, &bri) >= 1) {
                pthread_mutex_lock(&g_lock);
                snprintf(g_current_led, sizeof(g_current_led), "%s", pattern);
                g_current_bri = bri;
                if (!g_muted && g_vol_timer_ticks == 0) {
                    ledctrl_apply(g_current_led, g_current_bri);
                }
                send_ctrl_line_locked("OK LED\n");
                pthread_mutex_unlock(&g_lock);
            } else {
                pthread_mutex_lock(&g_lock);
                send_ctrl_line_locked("ERR LED_ARGS\n");
                pthread_mutex_unlock(&g_lock);
            }
        } else if (strncmp(line, "VOL ", 4) == 0) {
            int v = atoi(line + 4);
            pthread_mutex_lock(&g_lock);
            set_volume_locked(v, 1);
            snprintf(reply, sizeof(reply), "OK VOL %d\n", g_volume);
            send_ctrl_line_locked(reply);
            pthread_mutex_unlock(&g_lock);
        } else if (strncmp(line, "AMPGAIN ", 8) == 0) {
            int g = atoi(line + 8);
            if (g != 6 && g != 12 && g != 18 && g != 24) g = 12;
            pthread_mutex_lock(&g_lock);
            g_amp_gain_db = g;
            char g_str[16];
            snprintf(g_str, sizeof(g_str), "%ddB", g_amp_gain_db);
            tinymix_set2("Ext_Amp_Gain", g_str);
            snprintf(reply, sizeof(reply), "OK AMPGAIN %d\n", g_amp_gain_db);
            send_ctrl_line_locked(reply);
            pthread_mutex_unlock(&g_lock);
        } else if (strncmp(line, "HPGAIN ", 7) == 0) {
            int g = atoi(line + 7);
            if (g < 0) g = 0;
            if (g > 35) g = 35;
            pthread_mutex_lock(&g_lock);
            char g_str[16];
            snprintf(g_str, sizeof(g_str), "%d", g);
            tinymix_set3("HP Driver Gain Volume", g_str, g_str);
            snprintf(reply, sizeof(reply), "OK HPGAIN %d\n", g);
            send_ctrl_line_locked(reply);
            pthread_mutex_unlock(&g_lock);
        } else if (strncmp(line, "MUTE ", 5) == 0) {
            int m = atoi(line + 5);
            pthread_mutex_lock(&g_lock);
            g_muted = m ? 1 : 0;
            g_vol_timer_ticks = 0;
            apply_mute_hardware(g_muted);
            restore_active_led_locked();
            snprintf(reply, sizeof(reply), "OK MUTE %d\n", g_muted);
            send_ctrl_line_locked(reply);
            pthread_mutex_unlock(&g_lock);
        } else if (strcmp(line, "ACTION") == 0) {
            pthread_mutex_lock(&g_lock);
            if (g_play_pid > 0) {
                stop_playback_locked();
                restore_active_led_locked();
                send_ctrl_line_locked("EVT ACTION BARGE_IN\n");
            } else if (!g_muted) {
                snprintf(g_current_led, sizeof(g_current_led), "solid_cyan");
                g_current_bri = 90;
                ledctrl_apply("solid_cyan", 90);
                send_ctrl_line_locked("EVT ACTION WAKE\n");
            }
            send_ctrl_line_locked("OK ACTION\n");
            pthread_mutex_unlock(&g_lock);
        } else if (strcmp(line, "STOP") == 0) {
            pthread_mutex_lock(&g_lock);
            stop_playback_locked();
            send_ctrl_line_locked("OK STOP\n");
            pthread_mutex_unlock(&g_lock);
        } else if (strncmp(line, "PLAY ", 5) == 0) {
            long nbytes = atol(line + 5);
            if (nbytes <= 44 || nbytes > MAX_WAV_BYTES) {
                pthread_mutex_lock(&g_lock);
                send_ctrl_line_locked("ERR PLAY_SIZE\n");
                pthread_mutex_unlock(&g_lock);
                continue;
            }

            unsigned char *wav_buf = (unsigned char *)malloc((size_t)nbytes);
            if (!wav_buf) {
                pthread_mutex_lock(&g_lock);
                send_ctrl_line_locked("ERR OOM\n");
                pthread_mutex_unlock(&g_lock);
                break;
            }

            if (read_exact(cli, wav_buf, (size_t)nbytes) < 0) {
                free(wav_buf);
                break;
            }

            const char *wav_path = "/data/local/tmp/tad_dotd_play.wav";
            pthread_mutex_lock(&g_lock);
            stop_playback_locked();

            int wfd = open(wav_path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
            if (wfd >= 0) {
                size_t written = 0;
                while (written < (size_t)nbytes) {
                    ssize_t w = write(wfd, wav_buf + written, (size_t)nbytes - written);
                    if (w <= 0) break;
                    written += (size_t)w;
                }
                close(wfd);
            }
            free(wav_buf);

            speaker_amp_enable_locked();

            pid_t pid = fork();
            if (pid == 0) {
                int devnull = open("/dev/null", O_RDWR);
                if (devnull >= 0) {
                    dup2(devnull, STDIN_FILENO);
                    dup2(devnull, STDOUT_FILENO);
                    dup2(devnull, STDERR_FILENO);
                    if (devnull > 2) close(devnull);
                }
                char *const play_argv[] = {
                    "/system/bin/tinyctlplay", (char *)wav_path,
                    "-D", "0", "-d", "23", "-a", "100", "-m", "100", NULL
                };
                execv(play_argv[0], play_argv);
                _exit(127);
            }

            if (pid > 0) {
                g_play_pid = pid;
                struct play_watch_arg *wa = (struct play_watch_arg *)malloc(sizeof(*wa));
                if (wa) {
                    wa->pid = pid;
                    pthread_t wt;
                    if (pthread_create(&wt, NULL, playback_watcher_thread, wa) == 0) {
                        pthread_detach(wt);
                    } else {
                        free(wa);
                    }
                }
                send_ctrl_line_locked("OK PLAY_STARTED\n");
            } else {
                speaker_amp_disable();
                send_ctrl_line_locked("ERR FORK\n");
            }
            pthread_mutex_unlock(&g_lock);
        } else {
            pthread_mutex_lock(&g_lock);
            send_ctrl_line_locked("ERR UNKNOWN_CMD\n");
            pthread_mutex_unlock(&g_lock);
        }
    }
}

static void *ctrl_server_thread(void *arg) {
    (void)arg;
    int srv = create_listen_socket(CTRL_PORT);
    if (srv < 0) {
        fprintf(stderr, "[tad_dotd] Failed to bind control port %d: %s\n", CTRL_PORT, strerror(errno));
        return NULL;
    }
    printf("[tad_dotd] Control & Audio server listening on 0.0.0.0:%d\n", CTRL_PORT);
    fflush(stdout);

    while (g_running) {
        struct sockaddr_in cli_addr;
        socklen_t cli_len = sizeof(cli_addr);
        int cli = accept(srv, (struct sockaddr *)&cli_addr, &cli_len);
        if (cli < 0) {
            if (errno == EINTR) continue;
            usleep(200000);
            continue;
        }

        fcntl(cli, F_SETFD, FD_CLOEXEC);
        int yes = 1;
        setsockopt(cli, IPPROTO_TCP, TCP_NODELAY, &yes, sizeof(yes));
        setsockopt(cli, SOL_SOCKET, SO_KEEPALIVE, &yes, sizeof(yes));

        pthread_mutex_lock(&g_lock);
        if (g_ctrl_client_fd >= 0) {
            shutdown(g_ctrl_client_fd, SHUT_RDWR);
            close(g_ctrl_client_fd);
        }
        g_ctrl_client_fd = cli;
        char hello[128];
        snprintf(hello, sizeof(hello), "EVT HELLO vol=%d muted=%d\n", g_volume, g_muted);
        send_ctrl_line_locked(hello);
        pthread_mutex_unlock(&g_lock);

        printf("[tad_dotd] Control client connected (%s)\n", inet_ntoa(cli_addr.sin_addr));
        fflush(stdout);

        handle_ctrl_client(srv, cli);

        pthread_mutex_lock(&g_lock);
        if (g_ctrl_client_fd == cli) {
            g_ctrl_client_fd = -1;
        }
        pthread_mutex_unlock(&g_lock);
        close(cli);

        printf("[tad_dotd] Control client disconnected.\n");
        fflush(stdout);
    }

    close(srv);
    return NULL;
}

/* ─── Thread 1 (Main): Physical Buttons Event Loop ────────────────────────── */
int main(int argc, char *argv[]) {
    int do_daemon = 1;
    if (argc > 1 && strcmp(argv[1], "-f") == 0) {
        do_daemon = 0;
    }

    signal(SIGPIPE, SIG_IGN);
    signal(SIGTERM, sig_handler);
    signal(SIGINT, sig_handler);

    if (do_daemon) {
        pid_t pid = fork();
        if (pid < 0) return 1;
        if (pid > 0) return 0;
        setsid();
        signal(SIGHUP, SIG_IGN);

        int devnull = open("/dev/null", O_RDONLY);
        if (devnull >= 0) {
            dup2(devnull, STDIN_FILENO);
            if (devnull > 2) close(devnull);
        }
        int log_fd = open("/data/adb/tad_dotd.log", O_WRONLY | O_CREAT | O_APPEND, 0644);
        if (log_fd >= 0) {
            dup2(log_fd, STDOUT_FILENO);
            dup2(log_fd, STDERR_FILENO);
            if (log_fd > 2) close(log_fd);
        }
    }

    printf("[tad_dotd] Starting Unified Echo Dot 2G Daemon v3.0 (PID %d)...\n", getpid());
    fflush(stdout);

    /* Ensure initial clean audio & LED state */
    speaker_amp_disable();
    apply_mute_hardware(0);
    pthread_mutex_lock(&g_lock);
    set_volume_locked(g_volume, 0);
    restore_active_led_locked();
    pthread_mutex_unlock(&g_lock);

    /* Launch Mic (:9000) and Control/Playback (:9001) server threads */
    pthread_t mic_tid, ctrl_tid;
    pthread_create(&mic_tid, NULL, mic_server_thread, NULL);
    pthread_create(&ctrl_tid, NULL, ctrl_server_thread, NULL);

    int input_fds[3] = {-1, -1, -1};
    struct pollfd fds[3];
    int nfds = 0;

    const char *dev_paths[3] = {"/dev/input/event0", "/dev/input/event1", "/dev/input/event2"};
    for (int i = 0; i < 3; i++) {
        int ifd = open(dev_paths[i], O_RDONLY | O_NONBLOCK | O_CLOEXEC);
        input_fds[i] = ifd;
        if (ifd >= 0) {
            fds[nfds].fd = ifd;
            fds[nfds].events = POLLIN;
            nfds++;
            printf("[tad_dotd] Monitoring input device: %s\n", dev_paths[i]);
        } else {
            printf("[tad_dotd] Could not open %s: %s\n", dev_paths[i], strerror(errno));
        }
    }
    fflush(stdout);

    struct input_event ev;
    while (g_running) {
        int ret = (nfds > 0) ? poll(fds, (nfds_t)nfds, 100) : (usleep(100000), 0);

        if (ret > 0) {
            for (int i = 0; i < nfds; i++) {
                if (fds[i].revents & POLLIN) {
                    while (read(fds[i].fd, &ev, sizeof(ev)) == sizeof(ev)) {
                        if (ev.type != EV_KEY) continue;

                        printf("[tad_dotd] Physical Key: code=%d val=%d\n", ev.code, ev.value);
                        fflush(stdout);

                        char evt_msg[64];
                        if (ev.value == 1) {
                            if (ev.code == 113) { /* KEY_MUTE */
                                pthread_mutex_lock(&g_lock);
                                g_muted = !g_muted;
                                g_vol_timer_ticks = 0;
                                apply_mute_hardware(g_muted);
                                restore_active_led_locked();
                                snprintf(evt_msg, sizeof(evt_msg), "EVT MUTE %d\n", g_muted);
                                send_ctrl_line_locked(evt_msg);
                                pthread_mutex_unlock(&g_lock);
                            } else if (ev.code == 138) { /* KEY_HELP (Action Button) */
                                pthread_mutex_lock(&g_lock);
                                if (g_play_pid > 0) {
                                    stop_playback_locked();
                                    restore_active_led_locked();
                                    send_ctrl_line_locked("EVT ACTION BARGE_IN\n");
                                } else if (!g_muted) {
                                    snprintf(g_current_led, sizeof(g_current_led), "solid_cyan");
                                    g_current_bri = 90;
                                    ledctrl_apply("solid_cyan", 90);
                                    send_ctrl_line_locked("EVT ACTION WAKE\n");
                                }
                                pthread_mutex_unlock(&g_lock);
                            }
                        }

                        /* Volume Up / Down supports both press (1) and repeat/hold (2) */
                        if (ev.value == 1 || ev.value == 2) {
                            if (ev.code == 115) { /* KEY_VOLUMEUP */
                                pthread_mutex_lock(&g_lock);
                                set_volume_locked(g_volume + VOL_STEP_SIZE, 1);
                                snprintf(evt_msg, sizeof(evt_msg), "EVT VOL %d\n", g_volume);
                                send_ctrl_line_locked(evt_msg);
                                pthread_mutex_unlock(&g_lock);
                            } else if (ev.code == 114) { /* KEY_VOLUMEDOWN */
                                pthread_mutex_lock(&g_lock);
                                set_volume_locked(g_volume - VOL_STEP_SIZE, 1);
                                snprintf(evt_msg, sizeof(evt_msg), "EVT VOL %d\n", g_volume);
                                send_ctrl_line_locked(evt_msg);
                                pthread_mutex_unlock(&g_lock);
                            }
                        }
                    }
                }
            }
        }

        pthread_mutex_lock(&g_lock);
        if (g_vol_timer_ticks > 0) {
            g_vol_timer_ticks--;
            if (g_vol_timer_ticks == 0) {
                restore_active_led_locked();
            }
        }
        pthread_mutex_unlock(&g_lock);
    }

    for (int i = 0; i < 3; i++) {
        if (input_fds[i] >= 0) close(input_fds[i]);
    }
    speaker_amp_disable();
    return 0;
}
