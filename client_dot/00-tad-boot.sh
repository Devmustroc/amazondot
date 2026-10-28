#!/system/bin/sh
exec > /data/adb/service_boot.log 2>&1
set -x
# ==============================================================================
# TAD Boot & Persistence Service for Amazon Echo Dot 2G
# Installed in: /data/adb/service.d/00-tad-boot.sh (Magisk autostart)
# ==============================================================================

# 1. Open Firewall (ADB 5555, Mic Stream 9000 & Control/Playback 9001)
iptables -I INPUT 1 -p tcp --dport 5555 -j ACCEPT 2>/dev/null
iptables -I INPUT 1 -p tcp --dport 9000 -j ACCEPT 2>/dev/null
iptables -I INPUT 1 -p tcp --dport 9001 -j ACCEPT 2>/dev/null
iptables -I INPUT 1 -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null

# 2. Wireless ADB properties
setprop service.adb.tcp.port 5555
setprop persist.adb.tcp.port 5555

# 3. Audio Hardware Mixer & LED
if [ -f /data/adb/active-thinking-purple.animation ]; then
    mount -o bind /data/adb/active-thinking-purple.animation /system/etc/led-resources/active-thinking.animation 2>/dev/null
fi
if [ -f /data/adb/active-talking-cyberpunk.animation ]; then
    mount -o bind /data/adb/active-talking-cyberpunk.animation /system/etc/led-resources/active-talking.animation 2>/dev/null
fi
/system/bin/ledctrl -c 2>/dev/null
/system/bin/ledctrl -s solid_green -b 40 2>/dev/null

tinymix "MFP Gpio Mute" Off 2>/dev/null
tinymix "ADCFGA Left Mute Switch" 0 2>/dev/null
tinymix "ADCFGA Right Mute Switch" 0 2>/dev/null
tinymix "Mic PGA Switch" 1 1 2>/dev/null
tinymix "ADC Level Volume" 50 50 2>/dev/null

for adc in A B C D; do
    tinymix "ADC_${adc} Left Mute" 0 2>/dev/null
    tinymix "ADC_${adc} Right Mute" 0 2>/dev/null
    tinymix "ADC_${adc} Left Ip Select ADC_${adc} DIF1_L switch" 1 2>/dev/null
    tinymix "ADC_${adc} Right Ip Select ADC_${adc} DIF1_R switch" 1 2>/dev/null
    tinymix "ADC_${adc} DIF1_L Input Gain" 1 2>/dev/null
    tinymix "ADC_${adc} DIF1_R Input Gain" 1 2>/dev/null
    tinymix "ADC_${adc} MICPGA Volume Ctrl" 60 60 2>/dev/null
    tinymix "ADC_${adc} Digital Volume Control" 64 64 2>/dev/null
done

tinymix "HPL Output Mixer L_DAC Switch" 1 2>/dev/null
tinymix "HPR Output Mixer R_DAC Switch" 1 2>/dev/null
tinymix "Right Channel Only" On 2>/dev/null
tinymix "HP Driver Gain Volume" 21 21 2>/dev/null
tinymix Audio_Amp_R_Switch Off 2>/dev/null
tinymix Audio_Amp_L_Switch Off 2>/dev/null
tinymix Speaker_Amp_Switch Off 2>/dev/null
tinymix Ext_Speaker_Amp_Switch Off 2>/dev/null

# Find busybox
BB="/data/adb/busybox"
[ -x "$BB" ] || BB="/data/local/tmp/busybox"
[ -x "$BB" ] || BB="/sbin/.core/busybox/busybox"

# 4. Unified Native Daemon tad_dotd (Buttons + TCP :9000 Mic + TCP :9001 Control/Playback)
$BB killall -9 tad_buttonsd tad_dotd nc tinycap 2>/dev/null
chmod 755 /data/adb/tad_dotd 2>/dev/null
/data/adb/tad_dotd

# 5. Watchdog ensuring tad_dotd stays alive 24/7
(
    while true; do
        sleep 5
        if ! $BB pidof tad_dotd >/dev/null 2>&1; then
            echo "[watchdog] restarting tad_dotd..." >> /data/adb/service_boot.log
            /data/adb/tad_dotd
        fi
    done
) >/dev/null 2>&1 &

# 6. Background Bloatware Cleaner & Netd Keeper (Waits for Android Framework to complete boot)
(
    count=0
    while [ "$(getprop sys.boot_completed)" != "1" ] && [ $count -lt 60 ]; do
        sleep 2
        count=$((count + 2))
    done
    sleep 3

    for pkg in \
      com.amazon.device.networkderegistrationcontroller \
      com.amazon.whisperjoin.middleware \
      com.amazon.whisperjoin.wss.wifiprovisioner \
      com.amazon.alexa.beaconbroadcaster \
      com.amazon.headlessbeacon \
      com.amazon.device.smarthome.dshs.headlessux \
      com.amazon.device.csmbluetooth.headlessUxController \
      com.amazon.device.smarthome.adapters.echo \
      com.amazon.device.smarthome.adapters.ble \
      com.amazon.banyan.core \
      com.amazon.echo.csm.oobe \
      amazon.speech.sim; do
        pm disable $pkg 2>/dev/null
        am force-stop $pkg 2>/dev/null
    done

    # Re-apply ALSA mixer routes once bloatware is killed
    tinymix "MFP Gpio Mute" Off 2>/dev/null
    tinymix "ADCFGA Left Mute Switch" 0 2>/dev/null
    tinymix "ADCFGA Right Mute Switch" 0 2>/dev/null
    tinymix "Mic PGA Switch" 1 1 2>/dev/null
    tinymix "ADC Level Volume" 50 50 2>/dev/null
    for adc in A B C D; do
        tinymix "ADC_${adc} Left Mute" 0 2>/dev/null
        tinymix "ADC_${adc} Right Mute" 0 2>/dev/null
        tinymix "ADC_${adc} Left Ip Select ADC_${adc} DIF1_L switch" 1 2>/dev/null
        tinymix "ADC_${adc} Right Ip Select ADC_${adc} DIF1_R switch" 1 2>/dev/null
        tinymix "ADC_${adc} DIF1_L Input Gain" 1 2>/dev/null
        tinymix "ADC_${adc} DIF1_R Input Gain" 1 2>/dev/null
        tinymix "ADC_${adc} MICPGA Volume Ctrl" 60 60 2>/dev/null
        tinymix "ADC_${adc} Digital Volume Control" 64 64 2>/dev/null
    done
    tinymix "HPL Output Mixer L_DAC Switch" 1 2>/dev/null
    tinymix "HPR Output Mixer R_DAC Switch" 1 2>/dev/null
    tinymix "Right Channel Only" On 2>/dev/null
    tinymix "HP Driver Gain Volume" 21 21 2>/dev/null

    /system/bin/ledctrl -s solid_green -b 50 2>/dev/null

    # Keep firewall open permanently against netd resets
    while true; do
        iptables -I INPUT 1 -j ACCEPT 2>/dev/null
        iptables -P INPUT ACCEPT 2>/dev/null
        sleep 15
    done
) >/dev/null 2>&1 &

exit 0
