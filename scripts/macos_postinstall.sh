#!/bin/bash
# OpenBeat package postinstall. Installs the payload for the console user without
# ever leaving them without a working OpenBeat; scripts/staged_install.py performs
# the same steps for the Windows installer. For each payload folder, relative to
# the Resolve Fusion support folder:
#
# 1. Restore any installation that an interrupted earlier update left aside.
# 2. Copy the payload folder next to its target as .OpenBeat.new and verify it
#    against the SHA-256 manifest written by build_installers.py.
# 3. Rename the current target to .OpenBeat.old and the staged folder to the
#    target name. Both renames stay inside one folder, so each is atomic.
# 4. If anything fails or the script is interrupted, rename .OpenBeat.old back
#    into place. Once every target is replaced, write Modules/.OpenBeat.committed
#    and discard the .OpenBeat.old folders. While that marker exists the update is
#    complete, so a later run deletes leftover folders instead of restoring them.
#
# The package installs the payload under OPENBEAT_STAGING on the target volume.
# That folder and every folder above it must belong to root and be writable only
# by root, so no other user can place or swap files the script then copies as
# root. The script refuses to run otherwise and removes the folder when done.
#
# The installer runs openbeat_main. The other functions take explicit paths so
# tests can source this file and run them against temporary folders. macOS runs
# this with bash 3.2, so avoid arrays and newer bash features.

OPENBEAT_TARGETS="Modules/OpenBeat Scripts/Utility/OpenBeat"
# Relative to the target volume; build_installers.py passes it to pkgbuild as
# --install-location.
OPENBEAT_STAGING="Library/Application Support/OpenBeat/Installer"
# Owner required for the staging folders. Tests override it after sourcing.
OPENBEAT_TRUSTED_UID=0
OPENBEAT_ROOT=""
OPENBEAT_CREATED=""
OPENBEAT_USER=""

openbeat_log() {
  echo "OpenBeat: $*"
}

openbeat_exists() {
  [ -e "$1" ] || [ -L "$1" ]
}

# Renames $1 to $2, refusing to move it inside an existing $2.
openbeat_rename() {
  if openbeat_exists "$2"; then
    openbeat_log "Cannot move $1 because $2 already exists"
    return 1
  fi
  mv "$1" "$2"
}

# Checks that directory $1 holds every file listed in manifest $2 with the recorded digest.
openbeat_verify() {
  local directory="$1" manifest="$2" line digest name result
  if [ ! -s "$manifest" ]; then
    openbeat_log "The installer payload manifest $manifest is missing or empty"
    return 1
  fi
  # shasum -c skips lines it cannot parse, so reject them here.
  while IFS= read -r line || [ -n "$line" ]; do
    digest="${line%%  *}"
    name="${line#*  }"
    case "$digest" in
      *[!0-9a-f]*) digest="" ;;
    esac
    case "$name" in
      "" | /* | .. | ../* | */.. | */../*) name="" ;;
    esac
    if [ "${#digest}" -ne 64 ] || [ -z "$name" ] || [ "$name" = "$line" ]; then
      openbeat_log "The installer payload manifest $manifest is malformed"
      return 1
    fi
  done < "$manifest"
  if ! result="$({ cd "$directory" && shasum -a 256 -c - 2>&1; } < "$manifest")"; then
    openbeat_log "The prepared files in $directory do not match the installer payload:"
    printf '%s\n' "$result" | grep -v ': OK$'
    return 1
  fi
}

# Puts every .OpenBeat.old folder under Fusion root $1 back in place and removes
# staged copies. Targets listed in OPENBEAT_CREATED did not exist before this run
# and are removed.
openbeat_restore() {
  local root="$1" relative target parent status=0
  for relative in $OPENBEAT_TARGETS; do
    target="$root/$relative"
    parent="${target%/*}"
    rm -rf "$parent/.OpenBeat.new" "$parent/.OpenBeat.discard" || status=1
    if openbeat_exists "$parent/.OpenBeat.old"; then
      if openbeat_exists "$target" && ! openbeat_rename "$target" "$parent/.OpenBeat.discard"; then
        status=1
      elif openbeat_rename "$parent/.OpenBeat.old" "$target"; then
        openbeat_log "Restored the previous installation at $target"
      else
        status=1
      fi
    else
      case " $OPENBEAT_CREATED " in
        *" $relative "*) rm -rf "$target" || status=1 ;;
      esac
    fi
    rm -rf "$parent/.OpenBeat.discard"
  done
  return "$status"
}

# Deletes what a committed update under Fusion root $1 left behind, then its marker.
# The marker stays if anything remains, so the next run finishes the job.
openbeat_finish() {
  local root="$1" relative parent status=0
  for relative in $OPENBEAT_TARGETS; do
    parent="$root/${relative%/*}"
    rm -rf "$parent/.OpenBeat.old" "$parent/.OpenBeat.discard" "$parent/.OpenBeat.new" || status=1
  done
  if [ "$status" -eq 0 ]; then
    rm -f "$root/Modules/.OpenBeat.committed" || status=1
  fi
  return "$status"
}

# Completes or undoes an update under Fusion root $1 that stopped early.
openbeat_recover() {
  if openbeat_exists "$1/Modules/.OpenBeat.committed"; then
    openbeat_finish "$1"
  else
    openbeat_restore "$1"
  fi
}

openbeat_abort() {
  trap - INT TERM HUP
  openbeat_log "Interrupted; restoring the previous installation"
  if [ -n "$OPENBEAT_ROOT" ]; then
    openbeat_restore "$OPENBEAT_ROOT"
  fi
  exit 1
}

# Moves target $2 under Fusion root $1 aside and renames its staged copy into place.
openbeat_swap() {
  local target="$1/$2" parent
  parent="${target%/*}"
  if openbeat_exists "$target"; then
    openbeat_rename "$target" "$parent/.OpenBeat.old" || return 1
  else
    OPENBEAT_CREATED="$OPENBEAT_CREATED $2"
  fi
  openbeat_rename "$parent/.OpenBeat.new" "$target"
}

openbeat_write_config() {
  printf 'return {\n  python_bin = "%s",\n}\n' "$2" > "$1/OpenBeatConfig.local.lua"
}

openbeat_install_steps() {
  local payload="$1" root="$2" relative parent staged

  if ! openbeat_recover "$root"; then
    openbeat_log "A previous update was interrupted and could not be completed or undone automatically"
    return 1
  fi

  for relative in $OPENBEAT_TARGETS; do
    staged="$root/${relative%/*}/.OpenBeat.new"
    if ! { mkdir -p "${staged%/*}" &&
      cp -R "$payload/$relative" "$staged" &&
      openbeat_verify "$staged" "$payload/$relative.sha256"; }; then
      openbeat_log "Could not prepare $relative; the existing installation was not changed"
      openbeat_restore "$root"
      return 1
    fi
  done

  staged="$root/Modules/.OpenBeat.new"
  if ! { chmod 755 "$staged/bin/openbeat" &&
    openbeat_write_config "$staged" "$root/Modules/OpenBeat/bin/openbeat"; }; then
    openbeat_log "Could not configure the new files; the existing installation was not changed"
    openbeat_restore "$root"
    return 1
  fi

  for relative in $OPENBEAT_TARGETS; do
    if ! openbeat_swap "$root" "$relative"; then
      openbeat_log "Could not replace $relative; restoring the previous installation"
      openbeat_restore "$root"
      return 1
    fi
  done

  # Every target is replaced. Record that before deleting the previous folders,
  # so an interruption from here on completes the update instead of mixing versions.
  OPENBEAT_ROOT=""
  if ! : > "$root/Modules/.OpenBeat.committed"; then
    openbeat_log "Could not record the update; restoring the previous installation"
    openbeat_restore "$root"
    return 1
  fi
  if ! openbeat_finish "$root"; then
    openbeat_log "Some previous files could not be deleted yet; the next update removes them"
  fi
  return 0
}

# Installs payload folder $1 into Resolve Fusion folder $2, with the permissions of
# whoever runs it. openbeat_main runs it as the target user (see openbeat_as_user).
openbeat_install() {
  local status=0
  OPENBEAT_ROOT="$2"
  OPENBEAT_CREATED=""
  trap openbeat_abort INT TERM HUP
  openbeat_install_steps "$@" || status=$?
  trap - INT TERM HUP
  OPENBEAT_ROOT=""
  return "$status"
}

# What openbeat_install needs, passed to the shell openbeat_install_as_user starts.
OPENBEAT_INSTALL_FUNCTIONS="openbeat_log openbeat_exists openbeat_rename openbeat_verify openbeat_restore
  openbeat_finish openbeat_recover openbeat_abort openbeat_swap openbeat_write_config
  openbeat_install_steps openbeat_install"

# Runs command $2... as user $1. Tests replace this function.
openbeat_as_user() {
  local user="$1"
  shift
  /usr/bin/sudo -u "$user" -H "$@"
}

# Installs payload $2 into Fusion root $3 as user $1. The Fusion folder is in the
# user's home folder, where their own processes can swap files and symlinks at any
# time, so root must not copy, verify, or change permissions there: a swapped path
# could make root change or reveal a file the user cannot.
openbeat_install_as_user() {
  local definitions
  # shellcheck disable=SC2086 # The list is split into function names on purpose.
  definitions="$(declare -f $OPENBEAT_INSTALL_FUNCTIONS)" || return 1
  openbeat_as_user "$1" /bin/bash -c "set -euo pipefail
OPENBEAT_TARGETS='$OPENBEAT_TARGETS'
$definitions
openbeat_install \"\$1\" \"\$2\"" openbeat-postinstall "$2" "$3"
}

# Succeeds if $1/$2 and every folder between it and volume $1 is a real folder
# owned by OPENBEAT_TRUSTED_UID that no other user can write to.
openbeat_check_staging() {
  local path="${1%/}" remaining="$2" component owner_mode owner mode
  while [ -n "$remaining" ]; do
    component="${remaining%%/*}"
    if [ "$component" = "$remaining" ]; then
      remaining=""
    else
      remaining="${remaining#*/}"
    fi
    [ -n "$component" ] || continue
    path="$path/$component"
    if [ -L "$path" ] || [ ! -d "$path" ]; then
      openbeat_log "Refusing to install: $path is not a folder"
      return 1
    fi
    owner_mode="$(stat -f '%u %Lp' "$path")" || owner_mode=""
    owner="${owner_mode%% *}"
    mode="${owner_mode#* }"
    case "$mode" in
      "" | *[!0-7]*) mode=777 ;;
    esac
    if [ "$owner" != "$OPENBEAT_TRUSTED_UID" ] || [ $((8#$mode & 8#22)) -ne 0 ]; then
      openbeat_log "Refusing to install: $path must belong to root and be writable only by root"
      return 1
    fi
  done
}

# Sets OPENBEAT_USER to the user to install for: the console user, or for a
# command-line install with nobody logged in, the user who ran sudo. Fails for
# root and system accounts rather than installing into their home folders.
openbeat_target_user() {
  local user uid
  OPENBEAT_USER=""
  user="$(stat -f %Su /dev/console 2>/dev/null)" || user=""
  if [ -z "$user" ] || [ "$user" = "root" ] || [ "$user" = "loginwindow" ]; then
    user="${SUDO_USER:-${USER:-}}"
  fi
  uid=""
  if [ -n "$user" ] && [ "$user" != "root" ]; then
    uid="$(id -u "$user" 2>/dev/null)" || uid=""
  fi
  case "$uid" in
    "" | *[!0-9]*) uid=0 ;;
  esac
  if [ "$uid" -lt 500 ]; then
    openbeat_log "Could not tell which user to install OpenBeat for. Log in as the user who runs DaVinci Resolve and run the installer again."
    return 1
  fi
  OPENBEAT_USER="$user"
}

openbeat_main() {
  set -euo pipefail

  local volume="${3:-/}" staging user_home resolve_root status=0
  staging="${volume%/}/$OPENBEAT_STAGING"
  openbeat_check_staging "$volume" "$OPENBEAT_STAGING" || return 1

  if ! openbeat_target_user; then
    rm -rf "$staging"
    return 1
  fi
  if ! user_home="$(dscl . -read /Users/"$OPENBEAT_USER" NFSHomeDirectory | awk '{print $2}')" ||
    [ -z "$user_home" ] || [ "$user_home" = "/" ] || [ "$user_home" = "/var/root" ] || [ ! -d "$user_home" ]; then
    openbeat_log "Could not find the home folder of $OPENBEAT_USER"
    rm -rf "$staging"
    return 1
  fi
  resolve_root="$user_home/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion"

  openbeat_install_as_user "$OPENBEAT_USER" "$staging/payload" "$resolve_root" || status=$?
  rm -rf "$staging"
  rmdir "${staging%/*}" 2>/dev/null || true
  return "$status"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  openbeat_main "$@"
fi
