#!/bin/bash
# Connect Echo Dot 2G to local WiFi network via ADB without Amazon app

SSID="$1"
PASS="$2"

if [ -z "$SSID" ]; then
    echo "Usage: ./tools/connect_wifi.sh <SSID> [PASSWORD]"
    exit 1
fi

echo "Configuration du WiFi sur l'Echo Dot..."
echo "SSID: $SSID"

adb shell "su -c '
NETWORK_ID=\$(wpa_cli -i wlan0 add_network | tail -n 1)
echo \"Network ID: \$NETWORK_ID\"

wpa_cli -i wlan0 set_network \$NETWORK_ID ssid \"\\\"$SSID\\\"\"
if [ -n \"$PASS\" ]; then
    wpa_cli -i wlan0 set_network \$NETWORK_ID psk \"\\\"$PASS\\\"\"
    wpa_cli -i wlan0 set_network \$NETWORK_ID key_mgmt WPA-PSK
else
    wpa_cli -i wlan0 set_network \$NETWORK_ID key_mgmt NONE
fi

wpa_cli -i wlan0 select_network \$NETWORK_ID
wpa_cli -i wlan0 enable_network \$NETWORK_ID
wpa_cli -i wlan0 save_config

echo \"Demande d'adresse IP (DHCP)...\"
netcfg wlan0 dhcp 2>/dev/null || dhcptool wlan0 2>/dev/null || dhcpcd wlan0 2>/dev/null || true
sleep 3
ip addr show wlan0
'"

echo ""
echo "Pour activer ADB sans fil (une fois l'IP obtenue) :"
echo "  adb tcpip 5555"
echo "  adb connect <IP_DU_DOT>:5555"
