#!/system/bin/sh
# Magisk post-fs-data early mount: intercepts bootanimation before it can run
mount -o bind /data/adb/fake_bootanim /system/bin/bootanimation
