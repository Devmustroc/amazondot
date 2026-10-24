#!/system/bin/sh
# Magisk post-fs-data early mount: intercepts boot animation before init triggers it
mount -o bind /data/adb/fake_bootanim /system/bin/bootanimation
mount -o bind /data/adb/fake_start_animation.sh /system/bin/start_animation.sh
