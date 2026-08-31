#!/usr/bin/env bash
set -euo pipefail

[[ $# -eq 8 ]]
[[ "$(id -u)" == 0 ]]
target_uid=$1
target_gid=$2
gate_root=$3
host_namespace=$4
java_exact=$5
probe_classes=$6
jna_path=$7
zstd_path=$8
work_root="$gate_root/probe-work"
evidence_root="$gate_root/evidence-private"
ready_path="$work_root/ready.pid"
release_path="$work_root/release"

for path in "$gate_root" "$java_exact" "$probe_classes" "$jna_path" "$zstd_path"; do
  [[ "$path" == /* ]]
done
[[ "$probe_classes" == "$gate_root"/* ]]
[[ "$jna_path" == "$gate_root"/* ]]
[[ "$zstd_path" == "$gate_root"/* ]]
[[ ! -L "$gate_root" ]]
[[ ! -e "$work_root" ]]
[[ ! -e "$evidence_root" ]]
mkdir -m 0700 "$work_root" "$evidence_root"
chown "$target_uid:$target_gid" "$work_root"

mount --bind / /
mount --make-rprivate /
mount --bind "$work_root" "$work_root"
mount --bind "$evidence_root" "$evidence_root"
mount -o remount,bind,ro /
mapfile -t mount_targets < <(findmnt -rn -o TARGET | awk '{print length($0), $0}' | sort -rn | cut -d' ' -f2-)
for target in "${mount_targets[@]}"; do
  case "$target" in
    "$work_root"|"$work_root"/*|"$evidence_root"|"$evidence_root"/*) continue ;;
  esac
  options=$(findmnt -rn -o OPTIONS --target "$target")
  if [[ ",$options," == *,rw,* ]]; then
    mount -o remount,bind,ro "$target" 2>/dev/null || mount -o remount,ro "$target"
  fi
done
mount -o remount,bind,rw "$work_root"
mount -o remount,bind,rw "$evidence_root"

findmnt -rn -o TARGET,OPTIONS > "$evidence_root/mount_inventory.txt"
while read -r target options; do
  case "$target" in
    "$work_root"|"$work_root"/*|"$evidence_root"|"$evidence_root"/*) ;;
    *) [[ ",$options," != *,rw,* ]] ;;
  esac
done < "$evidence_root/mount_inventory.txt"
isolated_namespace=$(readlink /proc/self/ns/net)
[[ "$isolated_namespace" != "$host_namespace" ]]
printf 'host_net_namespace=%s\nisolated_net_namespace=%s\n' \
  "$host_namespace" "$isolated_namespace" > "$evidence_root/network_namespace.txt"

home_path="$work_root/home"
cache_path="$work_root/xdg-cache"
config_path="$work_root/xdg-config"
data_path="$work_root/xdg-data"
mkdir -m 0700 "$home_path" "$cache_path" "$config_path" "$data_path"
chown "$target_uid:$target_gid" "$home_path" "$cache_path" "$config_path" "$data_path"

setpriv_exact=$(command -v setpriv)
env_exact=$(command -v env)
strace -s 0 -v -ff -o "$evidence_root/trace" -e trace=process,network \
  "$setpriv_exact" --reuid="$target_uid" --regid="$target_gid" --clear-groups --no-new-privs -- \
  "$env_exact" -i HOME="$home_path" XDG_CACHE_HOME="$cache_path" \
  XDG_CONFIG_HOME="$config_path" XDG_DATA_HOME="$data_path" PATH=/usr/bin:/bin \
  "$java_exact" -XX:-UsePerfData -Djava.io.tmpdir="$work_root" -cp "$probe_classes" \
  org.phase9.gatec.GateCNativeMapProbe "$jna_path" "$zstd_path" "$ready_path" "$release_path" &
trace_supervisor_pid=$!

for _ in $(seq 1 300); do
  [[ -s "$ready_path" ]] && break
  kill -0 "$trace_supervisor_pid"
  sleep 0.1
done
[[ -s "$ready_path" ]]
read -r java_pid < "$ready_path"
[[ "$java_pid" =~ ^[0-9]+$ ]]
kill -0 "$java_pid"
[[ "$(awk '/^Uid:/ {print $2}' "/proc/$java_pid/status")" == "$target_uid" ]]
[[ "$(awk '/^NoNewPrivs:/ {print $2}' "/proc/$java_pid/status")" == 1 ]]
[[ -z "$(awk '/^Groups:/ {for (index = 2; index <= NF; index++) printf $index}' "/proc/$java_pid/status")" ]]
[[ "$(readlink -f "/proc/$java_pid/exe")" == "$(readlink -f "$java_exact")" ]]
grep -azF 'org.phase9.gatec.GateCNativeMapProbe' "/proc/$java_pid/cmdline" >/dev/null
cp "/proc/$java_pid/maps" "$evidence_root/probe_proc_maps.txt"
printf 'trace_supervisor_uid=%s\ntracee_uid=%s\ntracee_pid=%s\nno_new_privs_expected=1\nsetpriv_path=%s\nenv_path=%s\njava_path=%s\n' \
  "$(id -u)" "$target_uid" "$java_pid" "$setpriv_exact" "$env_exact" "$java_exact" \
  > "$evidence_root/supervisor_identity.txt"
touch "$release_path"
chmod 0644 "$release_path"
wait "$trace_supervisor_pid"

(
  cd "$evidence_root"
  find . -maxdepth 1 -type f ! -name sandbox_evidence_manifest.txt -print0 \
    | LC_ALL=C sort -z | xargs -0 sha256sum
) > "$evidence_root/sandbox_evidence_manifest.txt"
chmod 0600 "$evidence_root"/*
chown -R "$target_uid:$target_gid" "$evidence_root"
