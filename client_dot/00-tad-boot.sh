#!/system/bin/sh
# ==============================================================================
# TAD Boot & Persistence Script (Runs at Magisk service.d phase)
# Forks to background immediately so Magisk never hangs bootanimation!
# ==============================================================================

(
    # 1. Wait until Android system boot has completed
    count=0
    while [ "$(getprop sys.boot_completed)" != "1" ] && [ $count -lt 60 ]; do
        sleep 2
        count=$((count + 2))
    done

    # 2. Allow all inbound traffic on iptables (unblock port 5555 & 9000)
    iptables -I INPUT 1 -j ACCEPT
    iptables -P INPUT ACCEPT

    # 3. Enable Wireless ADB permanently
    setprop service.adb.tcp.port 5555
    setprop persist.adb.tcp.port 5555
    stop adbd
    start adbd

    # 4. Disable Amazon bloatware / telemetry
    pm disable com.amazon.echo.csm.oobe 2>/dev/null
    pm disable com.amazon.device.software.ota 2>/dev/null
    pm disable amazon.speech.sim 2>/dev/null
    /data/local/tmp/busybox pkill -9 -f speech 2>/dev/null
    /data/local/tmp/busybox pkill -9 -f oobe 2>/dev/null

    # 5. Stop boot animation and set LED to solid green (idle)
    setprop ctl.stop bootanim 2>/dev/null
    /system/bin/ledctrl -c
    /system/bin/ledctrl -s solid_green -b 50

    # 6. Start TAD Hardware Audio Stream Daemon
    killall -9 tad_dot_daemon.sh 2>/dev/null
    killall -9 tinycap 2>/dev/null
    exec /data/local/tmp/tad_dot_daemon.sh > /data/local/tmp/daemon.log 2>&1
) &

exit 0
