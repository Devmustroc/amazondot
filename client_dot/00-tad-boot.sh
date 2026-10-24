#!/system/bin/sh
# ==============================================================================
# TAD Boot & Persistence Service for Amazon Echo Dot 2G
# Installed in: /data/adb/service.d/00-tad-boot.sh (Magisk autostart)
# ==============================================================================

# 1. Open Firewall (ADB 5555 & Mic Stream 9000)
iptables -I INPUT 1 -p tcp --dport 5555 -j ACCEPT 2>/dev/null
iptables -I INPUT 1 -p tcp --dport 9000 -j ACCEPT 2>/dev/null
iptables -I INPUT 1 -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null

# 2. Wireless ADB properties
setprop service.adb.tcp.port 5555
setprop persist.adb.tcp.port 5555

# 3. Audio Hardware Mixer & LED
/system/bin/ledctrl -c 2>/dev/null
/system/bin/ledctrl -s solid_green -b 50 2>/dev/null

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
    tinymix "ADC_${adc} MICPGA Volume Ctrl" 40 40 2>/dev/null
    tinymix "ADC_${adc} Digital Volume Control" 64 64 2>/dev/null
done

tinymix "HPL Output Mixer L_DAC Switch" 1 2>/dev/null
tinymix "HPR Output Mixer R_DAC Switch" 1 2>/dev/null
tinymix "Right Channel Only" On 2>/dev/null
tinymix "HP Driver Gain Volume" 6 6 2>/dev/null
tinymix Audio_Amp_R_Switch On 2>/dev/null
tinymix Audio_Amp_L_Switch On 2>/dev/null
tinymix Speaker_Amp_Switch On 2>/dev/null
tinymix Ext_Speaker_Amp_Switch On 2>/dev/null

# 4. Persistent Mic Stream Server on Port 9000
STREAM_HELPER="/data/adb/tad_stream_worker.sh"
cat << 'HELPER_EOF' > ${STREAM_HELPER}
#!/system/bin/sh
for p in $(/data/local/tmp/busybox pgrep tinycap); do kill -9 $p 2>/dev/null; done
PIPE="/data/local/tmp/tad_stream_$$.fifo"
rm -f $PIPE
/data/local/tmp/busybox mkfifo $PIPE
tinycap $PIPE -D 0 -d 24 -c 9 -r 16000 -b 24 -f -p 1024 -n 2 &
PID_CAP=$!
trap "kill -9 $PID_CAP 2>/dev/null; rm -f $PIPE" EXIT INT TERM
cat $PIPE
kill -9 $PID_CAP 2>/dev/null
rm -f $PIPE
HELPER_EOF
chmod 755 ${STREAM_HELPER}

for p in $(/data/local/tmp/busybox pgrep nc); do kill -9 $p 2>/dev/null; done
/data/local/tmp/busybox nohup /data/local/tmp/busybox nc -lk -p 9000 -e ${STREAM_HELPER} >/dev/null 2>&1 &

# 5. Background Bloatware Cleaner (Waits for Android Framework to complete boot)
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

    /system/bin/ledctrl -s solid_green -b 50 2>/dev/null
) >/dev/null 2>&1 &

exit 0
