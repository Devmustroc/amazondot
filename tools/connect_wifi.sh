#!/bin/bash
# Connect Echo Dot 2G to local WiFi via ADB and enable wireless ADB

SSID="$1"
PSK="$2"

if [ -z "$SSID" ] || [ -z "$PSK" ]; then
    echo "Usage: $0 <SSID> <PASSWORD>"
    exit 1
fi

echo "Connecting Echo Dot to WiFi: $SSID..."

adb shell "su -c '
wpa_cli -i wlan0 disconnect
wpa_cli -i wlan0 remove_network 0 2>/dev/null
wpa_cli -i wlan0 add_network
wpa_cli -i wlan0 set_network 0 ssid \"\\\"$SSID\\\"\"
wpa_cli -i wlan0 set_network 0 psk \"\\\"$PSK\\\"\"
wpa_cli -i wlan0 set_network 0 key_mgmt WPA-PSK
wpa_cli -i wlan0 enable_network 0
wpa_cli -i wlan0 save_config
wpa_cli -i wlan0 reconnect
'"

echo "Waiting for IP address assignment..."
sleep 5

IP=$(adb shell "su -c 'ip -f inet addr show wlan0 | grep inet | awk \"{print \\\$2}\" | cut -d/ -f1'")
echo "Assigned IP: $IP"

if [ -n "$IP" ]; then
    echo "Enabling Wireless ADB on port 5555..."
    adb tcpip 5555
    echo "You can now connect wirelessly: adb connect $IP:5555"
    echo "And unplug the USB cable from the PC!"
else
    echo "Failed to get IP address. Please check your WiFi credentials."
fi
