# Libération Matérielle de l'Echo Dot 2G (Jailbreak)

Ce guide décrit la procédure pas à pas pour libérer un **Amazon Echo Dot 2ème Génération** (nom de code matériel : *bison*), obtenir un accès root permanent et remplacer le firmware propriétaire Amazon par le démon audio libre **SovereignDot Bridge**.

---

## 🛠️ Spécifications Matérielles de l'Echo Dot 2G

L'Echo Dot 2G est une plateforme matérielle particulièrement intéressante et bon marché pour un assistant vocal privé :

- **SoC** : MediaTek MT8163V (Quad-Core ARM Cortex-A53 @ 1.3 GHz, 64-bit).
- **RAM** : 512 Mo LPDDR3.
- **Stockage** : 4 Go eMMC.
- **Microphones** : Réseau de 7 microphones avec annulateur d'écho acoustique matériel (ADC Texas Instruments / DSP).
- **Sortie Audio** : Transducteur 35 mm avec amplificateur audio Class-D + Jack 3,5 mm stéréo.
- **Connectivité** : Wi-Fi 802.11 a/b/g/n (2.4/5 GHz) + Bluetooth 4.0.

---

## ⚖️ Politique Clean-Room & Légalité

> [!IMPORTANT] Approche Clean-Room Stricte
> Ce dépôt ne contient **aucun binaire propriétaire Amazon**, aucune clé cryptographique extraite et aucun composant protégé par le droit d'auteur.
> Tous les scripts et payloads d'exploit sont téléchargés à la volée depuis les dépôts open-source de la communauté de rétro-ingénierie matérielle via le script fourni.

Avant de commencer, préparez l'environnement sur votre machine Linux :

```bash
# Téléchargement des outils et payloads open-source
chmod +x tools/fetch_blobs.sh
./tools/fetch_blobs.sh
```

---

## 🔌 Étape 1 : Démontage & Accès aux Points de Test (Testpoints)

1. Décollez délicatement la semelle antidérapante en caoutchouc sous l'Echo Dot à l'aide d'un pistolet à air chaud ou d'un sèche-cheveux.
2. Dévissez les 4 vis Torx T6 pour retirer le socle inférieur.
3. Repérez les points de test sur la carte mère :
   - **`GND`** : Masse du circuit imprimé (blindage métallique).
   - **`CLK` / `DAT0`** : Point de test eMMC pour forcer le mode BootROM MediaTek (BROM).
   - **`UART TX` / `UART RX`** (facultatif mais recommandé pour le debug série à 115200 bauds).

---

## ⚡ Étape 2 : Exploitation BootROM (MediaTek BROM / Kamakiri)

Le SoC MediaTek MT8163 souffre d'une vulnérabilité matérielle dans sa ROM de démarrage (BootROM) connue sous le nom d'exploit **kamakiri** (contournement SLA / DAA via injection USB).

1. Connectez l'Echo Dot à votre PC Linux via un câble Micro-USB tout en maintenant le point de test **`CLK`** relié à la masse (**`GND`**) pendant 2 secondes.
2. Vérifiez la détection du périphérique en mode BROM dans les journaux système :

```bash
dmesg | grep -i "usb"
# Périphérique détecté : MediaTek Inc. MT65xx Preloader / BROM (ID 0e8d:0003)
```

3. Exécutez le script d'injection BROM :

```bash
cd tools/exploits/amzn_dot2g/
sudo python3 mtk_brom_exploit.py --soc mt8163 --payload payload.bin
```

Le script contourne la signature matérielle et charge le bootloader open-source **U-Boot**.

---

## 🔓 Étape 3 : Flash du Bootloader U-Boot & Root Shell

Une fois le contrôle du bootloader obtenu :

```bash
# Démarrer le noyau minimal avec console root
sudo ./fastboot boot boot-root.img
```

Vous disposez désormais d'un shell root BusyBox sur le port série ou via USB ADB :

```bash
adb shell
id
# uid=0(root) gid=0(root)
```

---

## 🚀 Étape 4 : Déploiement du Démon `dot_bridge`

Pour transformer l'enceinte en satellite audio autonome :

1. Copiez le binaire compilé `dot_bridge` sur l'eMMC de l'Echo Dot (`/system/bin/dot_bridge`).
2. Créez le service de démarrage automatique :

```bash
cat << 'EOF' > /system/etc/init.d/99sovereigndot
#!/system/bin/sh
# Démarrage du bridge audio SovereignDot
/system/bin/dot_bridge --port 9001 --alsa-in hw:0,0 --alsa-out hw:0,1 &
EOF
chmod +x /system/etc/init.d/99sovereigndot
```

3. Redémarrez l'Echo Dot : l'enceinte écoute désormais en permanence sur le port `TCP:9001`. Le serveur central SovereignDot prend le relais pour toute l'intelligence !
