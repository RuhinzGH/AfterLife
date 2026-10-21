#!/bin/sh
# Afterlife device collector -- macOS and Linux.
#
# The companion to collect_device.ps1, emitting the same JSON shape so the
# backend, the passport and every card downstream work unchanged.
#
# Read-only and unprivileged by design. Every probe is wrapped: a machine that
# will not answer a question yields null for that field rather than failing the
# run, and "we could not read this" is never reported as "this is absent" --
# that distinction decides real verdicts elsewhere in this product.
#
# POSIX sh rather than bash: macOS ships bash 3.2 from 2007 for licensing
# reasons, and several Linux images ship no bash at all. Nothing here needs
# more than sh provides.
#
#   sh collect_device.sh                     print JSON
#   sh collect_device.sh --post URL --token T deliver to the web app

set -u

POST_URL=""
TOKEN=""
while [ $# -gt 0 ]; do
    case "$1" in
        --post)  POST_URL="${2:-}"; shift 2 ;;
        --token) TOKEN="${2:-}"; shift 2 ;;
        *) shift ;;
    esac
done

OS="$(uname -s)"

# ---------------------------------------------------------------- helpers
# Every value goes through one of these, so a probe that errors, prints nothing,
# or does not exist on this box all collapse to the same JSON null.
try() { v="$("$@" 2>/dev/null)"; [ -n "$v" ] && printf '%s' "$v"; }

# JSON string, with the escapes that actually occur in this data. Device model
# names contain quotes and backslashes often enough to matter.
jstr() {
    if [ -z "${1:-}" ]; then printf 'null'; return; fi
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/\t/ /g' \
        | tr -d '\000-\037' | awk '{printf "\"%s\"", $0}'
}

# Numbers are emitted bare so the backend sees a number, not a string, but only
# when the value really is numeric -- otherwise null.
jnum() {
    case "${1:-}" in
        ''|*[!0-9.-]*) printf 'null' ;;
        # A capacity or size of exactly zero is a probe that failed, not a real
        # measurement -- reporting 0.0 GB of disk would be a confident wrong
        # number where null correctly says "we could not read this".
        0|0.0|0.00) printf 'null' ;;
        *) printf '%s' "$1" ;;
    esac
}

jbool() { [ "${1:-}" = "1" ] && printf 'true' || printf 'false'; }

# Counts, where zero is a real and important answer rather than a failed probe.
# jnum() deliberately maps 0 to null because a disk of 0.0 GB is a broken read --
# but "0 files in Documents" is exactly what a wiped machine looks like, and
# reporting that as "could not check" would break the wipe verification this
# feeds. Empty still means unknown; zero means zero.
jcount() {
    case "${1:-}" in
        ''|*[!0-9]*) printf 'null' ;;
        *) printf '%s' "$1" ;;
    esac
}

# ---------------------------------------------------------------- identity
if [ "$OS" = "Darwin" ]; then
    HW="$(system_profiler SPHardwareDataType 2>/dev/null)"
    MANUFACTURER="Apple"
    MODEL="$(printf '%s' "$HW" | awk -F': ' '/Model Name/ {print $2; exit}')"
    MODEL_ID="$(printf '%s' "$HW" | awk -F': ' '/Model Identifier/ {print $2; exit}')"
    [ -n "$MODEL_ID" ] && MODEL="${MODEL:-$MODEL_ID}"
    OS_CAPTION="macOS $(sw_vers -productVersion 2>/dev/null)"
    OS_VERSION="$(try sw_vers -buildVersion)"
    CPU_NAME="$(try sysctl -n machdep.cpu.brand_string)"
    CPU_CORES="$(try sysctl -n hw.physicalcpu)"
    CPU_LOGICAL="$(try sysctl -n hw.logicalcpu)"
    RAM_BYTES="$(try sysctl -n hw.memsize)"
    RAM_GB="$(printf '%s' "${RAM_BYTES:-0}" | awk '{printf "%.1f", $1/1073741824}')"
    GPU_NAME="$(system_profiler SPDisplaysDataType 2>/dev/null | awk -F': ' '/Chipset Model/ {print $2; exit}')"
else
    # /etc/os-release is the standard on every modern distribution; the fallbacks
    # cover older or minimal images.
    if [ -r /etc/os-release ]; then
        . /etc/os-release 2>/dev/null || true
        OS_CAPTION="${PRETTY_NAME:-${NAME:-Linux}}"
        OS_VERSION="${VERSION_ID:-}"
    else
        OS_CAPTION="$(try uname -o)"; OS_VERSION="$(try uname -r)"
    fi
    # DMI is world-readable for these two fields on almost every distribution,
    # unlike dmidecode which needs root.
    MANUFACTURER="$(try cat /sys/devices/virtual/dmi/id/sys_vendor)"
    MODEL="$(try cat /sys/devices/virtual/dmi/id/product_name)"
    CPU_NAME="$(awk -F': ' '/^model name/ {print $2; exit}' /proc/cpuinfo 2>/dev/null)"
    [ -z "$CPU_NAME" ] && CPU_NAME="$(awk -F': ' '/^Model/ {print $2; exit}' /proc/cpuinfo 2>/dev/null)"
    CPU_CORES="$(awk -F': ' '/^cpu cores/ {print $2; exit}' /proc/cpuinfo 2>/dev/null)"
    CPU_LOGICAL="$(grep -c '^processor' /proc/cpuinfo 2>/dev/null)"
    [ -z "$CPU_CORES" ] && CPU_CORES="$CPU_LOGICAL"
    RAM_KB="$(awk '/^MemTotal/ {print $2; exit}' /proc/meminfo 2>/dev/null)"
    RAM_GB="$(printf '%s' "${RAM_KB:-0}" | awk '{printf "%.1f", $1/1048576}')"
    GPU_NAME="$(lspci 2>/dev/null | awk -F': ' '/VGA compatible|3D controller/ {print $2; exit}')"
fi

# ---------------------------------------------------------------- storage
if [ "$OS" = "Darwin" ]; then
    ROOT_DISK="$(df / 2>/dev/null | awk 'NR==2 {print $1}' | sed 's|/dev/||;s|s[0-9]*$||')"
    DISK_INFO="$(diskutil info "$ROOT_DISK" 2>/dev/null)"
    # Apple's SMART verdict is a single word, not the raw attribute table --
    # coarser than the Windows path but the same three states.
    SMART="$(printf '%s' "$DISK_INFO" | awk -F': ' '/SMART Status/ {gsub(/^ +/,"",$2); print $2; exit}')"
    case "$SMART" in
        Verified) DISK_HEALTH="Healthy" ;;
        Failing)  DISK_HEALTH="Unhealthy" ;;
        *)        DISK_HEALTH="" ;;
    esac
    SOLID="$(printf '%s' "$DISK_INFO" | awk -F': ' '/Solid State/ {gsub(/^ +/,"",$2); print $2; exit}')"
    [ "$SOLID" = "Yes" ] && MEDIA="SSD" || MEDIA=""
    TOTAL_GB="$(df -k / 2>/dev/null | awk 'NR==2 {printf "%.1f", $2/1048576}')"
    FREE_GB="$(df -k / 2>/dev/null | awk 'NR==2 {printf "%.1f", $4/1048576}')"
else
    TOTAL_GB="$(df -k / 2>/dev/null | awk 'NR==2 {printf "%.1f", $2/1048576}')"
    FREE_GB="$(df -k / 2>/dev/null | awk 'NR==2 {printf "%.1f", $4/1048576}')"
    # rotational is world-readable and settles SSD vs HDD without smartctl,
    # which would need root.
    ROOT_SRC="$(df / 2>/dev/null | awk 'NR==2 {print $1}' | sed 's|/dev/||')"
    BASE_DEV="$(printf '%s' "$ROOT_SRC" | sed -e 's/p\?[0-9]*$//')"
    MEDIA=""
    if [ -r "/sys/block/$BASE_DEV/queue/rotational" ]; then
        if [ "$(cat "/sys/block/$BASE_DEV/queue/rotational")" = "0" ]; then MEDIA="SSD"; else MEDIA="HDD"; fi
    fi
    # smartctl needs root on nearly every distribution, so its absence is
    # expected and reported as "unknown" rather than "healthy".
    DISK_HEALTH="$(smartctl -H "/dev/$BASE_DEV" 2>/dev/null | awk '/overall-health/ {print $NF; exit}')"
    case "$DISK_HEALTH" in PASSED) DISK_HEALTH="Healthy" ;; FAILED!) DISK_HEALTH="Unhealthy" ;; *) DISK_HEALTH="" ;; esac
fi

# ---------------------------------------------------------------- battery
# Presence is the field the backend uses to tell a laptop from a desktop, so
# "no battery" and "could not tell" must stay distinguishable.
BATTERY_PRESENT=""
BATTERY_HEALTH=""
BATTERY_CYCLES=""

if [ "$OS" = "Darwin" ]; then
    BATT="$(ioreg -rn AppleSmartBattery 2>/dev/null)"
    if [ -n "$BATT" ]; then
        BATTERY_PRESENT=1
        DESIGN="$(printf '%s' "$BATT" | awk -F'= ' '/"DesignCapacity"/ {print $2; exit}' | tr -d ' ')"
        MAXCAP="$(printf '%s' "$BATT" | awk -F'= ' '/"AppleRawMaxCapacity"/ {print $2; exit}' | tr -d ' ')"
        [ -z "$MAXCAP" ] && MAXCAP="$(printf '%s' "$BATT" | awk -F'= ' '/"MaxCapacity"/ {print $2; exit}' | tr -d ' ')"
        BATTERY_CYCLES="$(printf '%s' "$BATT" | awk -F'= ' '/"CycleCount"/ {print $2; exit}' | tr -d ' ')"
        if [ -n "$DESIGN" ] && [ -n "$MAXCAP" ] && [ "$DESIGN" -gt 0 ] 2>/dev/null; then
            BATTERY_HEALTH="$(awk -v m="$MAXCAP" -v d="$DESIGN" 'BEGIN{printf "%.1f", 100*m/d}')"
        fi
    else
        # A Mac with no battery interface at all is a desktop.
        case "$(try sysctl -n hw.model)" in
            *MacBook*) BATTERY_PRESENT=1 ;;
            iMac*|Macmini*|MacPro*|MacStudio*) BATTERY_PRESENT=0 ;;
        esac
    fi
else
    BAT_DIR=""
    for d in /sys/class/power_supply/BAT*; do
        [ -d "$d" ] && BAT_DIR="$d" && break
    done
    if [ -n "$BAT_DIR" ]; then
        BATTERY_PRESENT=1
        # Kernels expose either charge_* (µAh) or energy_* (µWh) depending on the
        # driver. The ratio is what matters, so either pair works.
        FULL="$(try cat "$BAT_DIR/charge_full")"; DESIGN="$(try cat "$BAT_DIR/charge_full_design")"
        if [ -z "$FULL" ]; then
            FULL="$(try cat "$BAT_DIR/energy_full")"; DESIGN="$(try cat "$BAT_DIR/energy_full_design")"
        fi
        if [ -n "$FULL" ] && [ -n "$DESIGN" ] && [ "$DESIGN" -gt 0 ] 2>/dev/null; then
            BATTERY_HEALTH="$(awk -v f="$FULL" -v d="$DESIGN" 'BEGIN{printf "%.1f", 100*f/d}')"
        fi
        BATTERY_CYCLES="$(try cat "$BAT_DIR/cycle_count")"
        [ "$BATTERY_CYCLES" = "0" ] && BATTERY_CYCLES=""   # 0 means "not reported"
    elif [ -d /sys/class/power_supply ]; then
        BATTERY_PRESENT=0
    fi
fi

# ---------------------------------------------------------------- firmware
# UEFI vs legacy BIOS. Every Mac since 2006 is EFI; on Linux the presence of
# efivars is the standard test.
if [ "$OS" = "Darwin" ]; then
    UEFI=1
    SECURE_BOOT=""   # Apple's equivalent is Startup Security Utility, not readable here
else
    [ -d /sys/firmware/efi ] && UEFI=1 || UEFI=0
    SECURE_BOOT=""
    if [ -d /sys/firmware/efi/efivars ]; then
        SB_FILE="$(ls /sys/firmware/efi/efivars/SecureBoot-* 2>/dev/null | head -1)"
        if [ -n "$SB_FILE" ] && [ -r "$SB_FILE" ]; then
            # Five bytes: four of attributes, then the flag itself.
            SB_VAL="$(od -An -t u1 -j 4 -N 1 "$SB_FILE" 2>/dev/null | tr -d ' ')"
            [ "$SB_VAL" = "1" ] && SECURE_BOOT=1 || SECURE_BOOT=0
        fi
    fi
fi

[ "$(id -u 2>/dev/null)" = "0" ] && ELEVATED=1 || ELEVATED=0

# The category the repair-rights panel needs. Derived from the battery, which is
# a measurement, and left null when the battery probe could not decide.
CATEGORY=""
[ "$BATTERY_PRESENT" = "1" ] && CATEGORY="Laptop"
[ "$BATTERY_PRESENT" = "0" ] && CATEGORY="Desktop computer"

# ---------------------------------------------------------------- device age
# The Windows collector derives age from the BIOS release date. Linux exposes
# the same value in DMI, world-readable. macOS has no BIOS date, so first-setup
# is used instead -- .AppleSetupDone is written once when the Mac is first
# configured and only changes on a full reinstall, which makes it both a decent
# purchase proxy and the exact analogue of the Windows install-date check used
# by the wipe verification below. Approximate on purpose, and never invented:
# absent whenever it cannot be read.
AGE_YEARS=""
BIOS_DATE=""
NOW_EPOCH="$(date +%s)"
if [ "$OS" = "Darwin" ]; then
    SETUP_EPOCH="$(stat -f %B /var/db/.AppleSetupDone 2>/dev/null)"
    if [ -n "$SETUP_EPOCH" ] && [ "$SETUP_EPOCH" -gt 0 ] 2>/dev/null; then
        AGE_YEARS="$(awk -v n="$NOW_EPOCH" -v s="$SETUP_EPOCH" 'BEGIN{printf "%.1f",(n-s)/31557600}')"
        BIOS_DATE="$(date -r "$SETUP_EPOCH" +%Y-%m-%d 2>/dev/null)"
    fi
else
    RAW_BIOS="$(try cat /sys/devices/virtual/dmi/id/bios_date)"
    if [ -n "$RAW_BIOS" ]; then
        B_EPOCH="$(date -d "$RAW_BIOS" +%s 2>/dev/null)"
        if [ -n "$B_EPOCH" ]; then
            AGE_YEARS="$(awk -v n="$NOW_EPOCH" -v b="$B_EPOCH" 'BEGIN{printf "%.1f",(n-b)/31557600}')"
            BIOS_DATE="$(date -d "$RAW_BIOS" +%Y-%m-%d 2>/dev/null)"
        fi
    fi
fi
# A negative or absurd age is a misparsed date, not a device from the future.
case "$AGE_YEARS" in -*) AGE_YEARS="" ;; esac

# ------------------------------------------------ factory-fresh indicators
# The sell/wipe flow needs this or it silently does nothing -- which is exactly
# how the first version of this collector shipped. Same contract as the
# PowerShell one: every field is a COUNT, never a name. No filename, account,
# network or application is read, transmitted or stored. A count answers "is
# this clean?" completely; a list would answer it no better and would be a
# genuine privacy problem.
#
# File counting stops at a cap, because the exact number is irrelevant to a
# threshold test and expensive to compute. The unbounded Windows version took
# 10.5 seconds for 41,662 files before it was fixed.
FILE_CAP=30
USER_FILES=0
USER_PROFILES=0
WIFI_COUNT=""
INSTALLED_APPS=""
OS_INSTALL_DAYS=""
CLEAN_CHECKED=0

if [ "$OS" = "Darwin" ]; then
    HOME_ROOT="/Users"
    SKIP_PROFILES="Shared Guest"
else
    HOME_ROOT="/home"
    SKIP_PROFILES="lost+found"
fi

if [ -d "$HOME_ROOT" ]; then
    CLEAN_CHECKED=1
    for d in "$HOME_ROOT"/*; do
        [ -d "$d" ] || continue
        base="$(basename "$d")"
        skip=0
        for sk in $SKIP_PROFILES; do
            [ "$base" = "$sk" ] && skip=1
        done
        [ "$skip" = "1" ] && continue
        USER_PROFILES=$((USER_PROFILES + 1))
        [ "$USER_FILES" -ge "$FILE_CAP" ] && continue
        for sub in Desktop Documents Downloads Pictures; do
            [ "$USER_FILES" -ge "$FILE_CAP" ] && break
            [ -d "$d/$sub" ] || continue
            n="$(find "$d/$sub" -type f 2>/dev/null | head -n "$FILE_CAP" | wc -l | tr -d ' ')"
            USER_FILES=$((USER_FILES + n))
        done
    done
    [ "$USER_FILES" -gt "$FILE_CAP" ] && USER_FILES="$FILE_CAP"
fi

if [ "$OS" = "Darwin" ]; then
    WIFI_IF="$(networksetup -listallhardwareports 2>/dev/null | awk '/Wi-Fi|AirPort/{getline; print $2; exit}')"
    if [ -n "$WIFI_IF" ]; then
        # The first line of this output is a header, not a network.
        W="$(networksetup -listpreferredwirelessnetworks "$WIFI_IF" 2>/dev/null | grep -c .)"
        if [ -n "$W" ] && [ "$W" -gt 0 ] 2>/dev/null; then WIFI_COUNT=$((W - 1)); fi
    fi
    INSTALLED_APPS="$(ls -1d /Applications/*.app 2>/dev/null | wc -l | tr -d ' ')"
    S_EPOCH="$(stat -f %B /var/db/.AppleSetupDone 2>/dev/null)"
    if [ -n "$S_EPOCH" ] && [ "$S_EPOCH" -gt 0 ] 2>/dev/null; then
        OS_INSTALL_DAYS="$(awk -v n="$NOW_EPOCH" -v s="$S_EPOCH" 'BEGIN{printf "%.1f",(n-s)/86400}')"
    fi
else
    # nmcli is unprivileged; the connection files themselves need root.
    W="$(nmcli -t -f TYPE connection show 2>/dev/null | grep -c wireless)"
    [ -n "$W" ] && WIFI_COUNT="$W"
    if command -v dpkg-query >/dev/null 2>&1; then
        INSTALLED_APPS="$(dpkg-query -f 'x\n' -W 2>/dev/null | wc -l | tr -d ' ')"
    elif command -v rpm >/dev/null 2>&1; then
        INSTALLED_APPS="$(rpm -qa 2>/dev/null | wc -l | tr -d ' ')"
    elif command -v pacman >/dev/null 2>&1; then
        INSTALLED_APPS="$(pacman -Qq 2>/dev/null | wc -l | tr -d ' ')"
    fi
    # Filesystem birth time where it is recorded; machine-id creation otherwise,
    # which is written once when the system is first installed.
    R_EPOCH="$(stat -c %W / 2>/dev/null)"
    if [ -z "$R_EPOCH" ] || [ "$R_EPOCH" = "0" ]; then
        R_EPOCH="$(stat -c %Y /etc/machine-id 2>/dev/null)"
    fi
    if [ -n "$R_EPOCH" ] && [ "$R_EPOCH" -gt 0 ] 2>/dev/null; then
        OS_INSTALL_DAYS="$(awk -v n="$NOW_EPOCH" -v r="$R_EPOCH" 'BEGIN{printf "%.1f",(n-r)/86400}')"
    fi
fi

# ------------------------------------------------- usage-persona signals
# Categories only, never the inventory. This answers "which kind of tool is on
# this machine", not "here is everything you have installed" -- the same line
# the Windows collector draws, and the reason Usage Fit can say "coding"
# without the app ever receiving a program list.
if [ "$OS" = "Darwin" ]; then
    APP_NAMES="$( { ls -1 /Applications 2>/dev/null; ls -1 "$HOME/Applications" 2>/dev/null; } )"
else
    APP_NAMES="$( { ls -1 /usr/share/applications 2>/dev/null
                    ls -1 /var/lib/flatpak/exports/share/applications 2>/dev/null
                    ls -1 /var/lib/snapd/desktop/applications 2>/dev/null; } | sed 's/\.desktop$//' )"
fi

# Underscores stand in for spaces so each keyword survives word-splitting.
match_apps() {
    hits=""
    for kw in $1; do
        pretty="$(printf '%s' "$kw" | tr '_' ' ')"
        if printf '%s\n' "$APP_NAMES" | grep -qi -- "$pretty"; then
            hits="$hits$(jstr "$pretty"),"
        fi
    done
    printf '[%s]' "$(printf '%s' "$hits" | sed 's/,$//')"
}

GAMER_HITS="$(match_apps "Steam Epic_Games Battle.net GOG_Galaxy Lutris Heroic Minecraft")"
CODER_HITS="$(match_apps "Visual_Studio_Code PyCharm IntelliJ WebStorm Android_Studio Docker GitHub_Desktop Sublime_Text Postman iTerm Xcode")"
EDITOR_HITS="$(match_apps "Premiere After_Effects Photoshop Lightroom Illustrator DaVinci Blender Audacity OBS Kdenlive GIMP Final_Cut")"

STEAM_GAMES=0
for sd in "$HOME/Library/Application Support/Steam/steamapps" \
          "$HOME/.steam/steam/steamapps" \
          "$HOME/.local/share/Steam/steamapps"; do
    if [ -d "$sd" ]; then
        STEAM_GAMES="$(ls -1 "$sd"/appmanifest_*.acf 2>/dev/null | wc -l | tr -d ' ')"
        break
    fi
done

# ---------------------------------------------------------------- emit
JSON=$(cat <<EOF
{
  "collected_at": $(jstr "$(date -u +%Y-%m-%dT%H:%M:%S)"),
  "collector": $(jstr "sh/$OS"),
  "manufacturer": $(jstr "${MANUFACTURER:-}"),
  "model": $(jstr "${MODEL:-}"),
  "os_caption": $(jstr "${OS_CAPTION:-}"),
  "os_version": $(jstr "${OS_VERSION:-}"),
  "os_architecture": $(jstr "$(uname -m)"),
  "cpu_name": $(jstr "${CPU_NAME:-}"),
  "cpu_cores": $(jcount "${CPU_CORES:-}"),
  "cpu_logical": $(jcount "${CPU_LOGICAL:-}"),
  "gpu_name": $(jstr "${GPU_NAME:-}"),
  "ram_gb": $(jnum "${RAM_GB:-}"),
  "sysdrive_total_gb": $(jnum "${TOTAL_GB:-}"),
  "sysdrive_free_gb": $(jnum "${FREE_GB:-}"),
  "disk_media_type": $(jstr "${MEDIA:-}"),
  "disk_health": $(jstr "${DISK_HEALTH:-}"),
  "battery_present": $([ -n "$BATTERY_PRESENT" ] && jbool "$BATTERY_PRESENT" || printf 'null'),
  "battery_health_pct": $(jnum "${BATTERY_HEALTH:-}"),
  "battery_cycle_count": $(jcount "${BATTERY_CYCLES:-}"),
  "uefi": $(jbool "${UEFI:-0}"),
  "secure_boot_on": $([ -n "$SECURE_BOOT" ] && jbool "$SECURE_BOOT" || printf 'null'),
  "collected_elevated": $(jbool "$ELEVATED"),
  "product_category": $(jstr "${CATEGORY:-}"),
  "approx_age_years": $(jnum "${AGE_YEARS:-}"),
  "bios_release_date": $(jstr "${BIOS_DATE:-}"),
  "clean_state": {
    "checked": $(jbool "$CLEAN_CHECKED"),
    "user_profiles": $(jcount "$USER_PROFILES"),
    "user_files": $(jcount "$USER_FILES"),
    "user_files_capped": $(if [ "$USER_FILES" -ge "$FILE_CAP" ] 2>/dev/null; then printf 'true'; else printf 'false'; fi),
    "wifi_profiles": $(jcount "${WIFI_COUNT:-}"),
    "installed_apps": $(jcount "${INSTALLED_APPS:-}"),
    "os_install_days": $(jcount "${OS_INSTALL_DAYS:-}")
  },
  "persona_signals": {
    "gamer_matches": ${GAMER_HITS:-[]},
    "coder_matches": ${CODER_HITS:-[]},
    "editor_matches": ${EDITOR_HITS:-[]},
    "steam_game_count": $(jcount "${STEAM_GAMES:-0}"),
    "wsl_distro_count": 0
  }
}
EOF
)

if [ -n "$POST_URL" ]; then
    TARGET="$POST_URL"
    [ -n "$TOKEN" ] && TARGET="$POST_URL/$TOKEN"
    # Generous timeout: the backend may be asleep on a free tier and take a while
    # to wake before it starts processing.
    if curl -sS -m 90 -X POST -H "Content-Type: application/json" -d "$JSON" "$TARGET" >/dev/null 2>&1; then
        echo "  Delivered to Afterlife. Return to the browser tab."
    else
        echo "  Could not reach $TARGET. Is the app running?" >&2
        exit 1
    fi
else
    printf '%s\n' "$JSON"
fi
