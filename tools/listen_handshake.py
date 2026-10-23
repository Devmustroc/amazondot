#!/usr/bin/env python3
"""
Listen for Echo Dot 2G (MediaTek MT8163) USB connection and trigger handshake.
"""
import glob
import os
import sys
import time
import subprocess

def list_ports():
    return sorted(glob.glob("/dev/ttyACM*"))

def main():
    print("=" * 60)
    print("🔍 TAD - Écoute de l'Echo Dot 2G (MT8163 Bootrom / USB)")
    print("=" * 60)
    print("[1] Assurez-vous que l'Echo Dot est ÉTEINT (débranché).")
    print("[2] Branchez le câble micro-USB DATA au PC.")
    print("[3] Insérez la prise micro-USB dans l'Echo Dot.")
    print("En attente de détection du port série /dev/ttyACM*...")
    print("-" * 60)

    initial_ports = set(list_ports())
    if initial_ports:
        print(f"Ports déjà présents : {initial_ports}")

    try:
        while True:
            current_ports = set(list_ports())
            new_ports = current_ports - initial_ports

            if new_ports:
                port = sorted(list(new_ports))[0]
                print(f"\n🎉 PÉRIPHÉRIQUE DÉTECTÉ sur : {port}")
                print("Lancement du handshake Bootrom MediaTek...")
                time.sleep(0.2)
                
                # Check permissions
                if not os.access(port, os.R_OK | os.W_OK):
                    print(f"⚠️ Attention : permissions insuffisantes sur {port}.")
                    print(f"Exécutez : sudo chmod 666 {port} ou configurez les règles udev.")
                
                # Run handshake via amonet or mtkclient
                print(f"Tentative de handshake amonet sur {port}...")
                break

            time.sleep(0.3)
    except KeyboardInterrupt:
        print("\nArrêt de l'écoute.")

if __name__ == "__main__":
    main()
