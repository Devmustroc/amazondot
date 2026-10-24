#!/system/bin/sh
# TAD - Intercepts Amazon's anim_start_phase2 and forces solid_green immediately
/system/bin/ledctrl -c
/system/bin/ledctrl -s solid_green -b 50
exit 0
