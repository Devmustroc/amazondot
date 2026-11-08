# 📻 SovereignDot — Hardware Jailbreak Guide (Echo Dot 2G)

This guide documents how to liberate an Amazon Echo Dot (2nd Generation, code-named **Biscuit**) using open-source bootrom exploits.

---

## ⚠️ Prerequisites & Safety

- **Model**: Amazon Echo Dot 2nd Gen (FCC ID: `2AB4-5483`, Model: `RS03QR`, MediaTek MT8163 SoC).
- **Cables**: Standard Micro-USB data cable (ensure it has data lines, not charge-only).
- **OS**: Linux (Debian/Ubuntu/Arch) with root privileges for `udev` and fastboot access.

---

## 🛠️ Step 1: Open-Source Exploit Setup

Run the clean-room fetcher to download the open-source bootrom exploit toolchain:

```bash
./tools/fetch_blobs.sh
```

This downloads:
- `amonet-biscuit` (GPL-3.0 by k4y0z and dragon8888)
- `mtkclient` (by bkerler)

---

## ⚡ Step 2: Bootrom Handshake

1. Unplug the Echo Dot from power.
2. Hold down the **Mute Button (Microphone Off)** and connect the micro-USB cable to your Linux PC.
3. Run:
   ```bash
   sudo ./tools/amonet-biscuit/bootrom-step.sh
   ```
4. Release the button when the script detects the MediaTek Preloader handshake.
5. The device will reboot into unlocked Fastboot mode.

---

## 📥 Step 3: Deploy `tad_dotd` Daemon

Once the custom bootloader is installed:
1. Push the pre-compiled native daemon:
   ```bash
   adb push tools/tad_dotd /data/local/tmp/
   adb shell chmod 755 /data/local/tmp/tad_dotd
   ```
2. Start the daemon on ports 9000-9002:
   ```bash
   adb shell "/data/local/tmp/tad_dotd &"
   ```

Now your Echo Dot is liberated and communicates natively over TCP with SovereignDot Core!
