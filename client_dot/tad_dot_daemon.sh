#!/system/bin/sh
# ==============================================================================
# TAD Echo Dot 2G (biscuit) Native Hardware Daemon
# Runs locally on Fire OS 5.5.5.4 as root under Magisk.
# Manages ALSA hardware mixer, LED ring, and microphone array stream server.
# ==============================================================================

BUSYBOX="/data/local/tmp/busybox"
FIFO_MIC="/data/local/tmp/tad_mic.fifo"
PORT_MIC=9000

echo "[TAD] Initializing Echo Dot hardware..."

# 1. Unmute and setup TI TLV320AIC3101 7-Mic Array with boosted gain
tinymix "MFP Gpio Mute" Off
tinymix "ADCFGA Left Mute Switch" 0
tinymix "ADCFGA Right Mute Switch" 0
tinymix "Mic PGA Switch" 1 1
tinymix "ADC Level Volume" 50 50

for adc in A B C D; do
    tinymix "ADC_${adc} Left Mute" 0
    tinymix "ADC_${adc} Right Mute" 0
    tinymix "ADC_${adc} Left Ip Select ADC_${adc} DIF1_L switch" 1
    tinymix "ADC_${adc} Right Ip Select ADC_${adc} DIF1_R switch" 1
    tinymix "ADC_${adc} DIF1_L Input Gain" 1
    tinymix "ADC_${adc} DIF1_R Input Gain" 1
    tinymix "ADC_${adc} MICPGA Volume Ctrl" 80 80
    tinymix "ADC_${adc} Digital Volume Control" 64 64
done

# 2. Setup Playback DAC Route
tinymix "HPL Output Mixer L_DAC Switch" 1
tinymix "HPR Output Mixer R_DAC Switch" 1

# 3. Set LED to solid green (idle / ready)
/system/bin/ledctrl -c
/system/bin/ledctrl -s solid_green -b 50

# 4. Streamer helper script
STREAM_HELPER="/data/local/tmp/tad_stream_worker.sh"
cat << 'EOF' > ${STREAM_HELPER}
#!/system/bin/sh
/data/local/tmp/busybox killall -9 tinycap 2>/dev/null
PIPE="/data/local/tmp/tad_stream_$$.fifo"
rm -f $PIPE
/data/local/tmp/busybox mkfifo $PIPE
tinycap $PIPE -D 0 -d 24 -c 9 -r 16000 -b 24 -f -p 1024 -n 2 &
PID_CAP=$!
trap "/data/local/tmp/busybox killall -9 tinycap 2>/dev/null; rm -f $PIPE" EXIT INT TERM
cat $PIPE
/data/local/tmp/busybox killall -9 tinycap 2>/dev/null
rm -f $PIPE
EOF
chmod 755 ${STREAM_HELPER}

echo "[TAD] Hardware initialized. Starting audio stream server on port ${PORT_MIC}..."

# 5. Persistent Stream Server Loop
while true; do
    /data/local/tmp/busybox killall -9 tinycap 2>/dev/null
    ${BUSYBOX} nc -l -p ${PORT_MIC} -e ${STREAM_HELPER}
    sleep 1
done

