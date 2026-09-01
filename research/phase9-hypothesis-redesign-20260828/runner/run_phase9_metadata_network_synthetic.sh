#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# -eq 3 ]]
[[ "$(id -u)" == 0 ]]
guard=$1
target=$2
evidence=$3
for path in "$guard" "$target" "$evidence"; do [[ "$path" == /* ]]; done
[[ -x "$guard" ]]
[[ -x "$target" ]]
[[ -d "$evidence" ]]
[[ ! -L "$evidence" ]]
[[ "$(stat -c %a "$evidence")" == 700 ]]

suffix="$$"
client_ns="p9mc-${suffix}"
server_ns="p9ms-${suffix}"
client_if="p9c${suffix: -7}"
server_if="p9s${suffix: -7}"
for name in "$client_ns" "$server_ns" "$client_if" "$server_if"; do
  [[ "$name" =~ ^[a-z0-9-]{1,15}$ ]]
done

server_pid=''
cleanup() {
  if [[ -n "$server_pid" ]]; then kill "$server_pid" 2>/dev/null || true; fi
  ip netns del "$client_ns" 2>/dev/null || true
  ip netns del "$server_ns" 2>/dev/null || true
}
trap cleanup EXIT

ip netns add "$client_ns"
ip netns add "$server_ns"
ip link add "$client_if" type veth peer name "$server_if"
ip link set "$client_if" netns "$client_ns"
ip link set "$server_if" netns "$server_ns"
ip netns exec "$client_ns" sysctl -q -w \
  net.ipv6.conf.all.disable_ipv6=1 \
  net.ipv6.conf.default.disable_ipv6=1 \
  "net.ipv6.conf.${client_if}.disable_ipv6=1"
ip -n "$client_ns" address add 198.18.0.2/32 dev "$client_if"
ip -n "$server_ns" address add 198.18.0.1/32 dev "$server_if"
ip -n "$client_ns" link set "$client_if" up
ip -n "$server_ns" link set "$server_if" up
ip -n "$client_ns" route add 198.18.0.1/32 dev "$client_if"
ip -n "$server_ns" route add 198.18.0.2/32 dev "$server_if"

test -z "$(ip -n "$client_ns" route show default)"
test "$(ip -n "$client_ns" -o route show | awk '{print $1}')" = '198.18.0.1'
test -z "$(ip -n "$client_ns" -o -6 route show)"
ip -n "$client_ns" -o address show > "$evidence/network_interfaces.txt"
ip -n "$client_ns" -o route show > "$evidence/network_routes.txt"

ip netns exec "$server_ns" python3 - "$evidence" <<'PY' &
import os
import socket
import sys

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("198.18.0.1", 38443))
server.listen(1)
descriptor = os.open(
    os.path.join(sys.argv[1], "server.ready"),
    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
    0o600,
)
os.write(descriptor, b"ready\n")
os.close(descriptor)
connection, _ = server.accept()
connection.close()
server.close()
PY
server_pid=$!
for _ in $(seq 1 100); do
  [[ -s "$evidence/server.ready" ]] && break
  kill -0 "$server_pid"
  sleep 0.05
done
[[ -s "$evidence/server.ready" ]]

ip netns exec "$client_ns" \
  unshare --pid --fork --kill-child --mount-proc \
  setpriv --reuid=65534 --regid=65534 --clear-groups --no-new-privs \
  "$guard" 38443 -- "$target" > "$evidence/network_guard.txt"
wait "$server_pid"
server_pid=''
test "$(cat "$evidence/network_guard.txt")" = phase9_metadata_network_synthetic=PASS
chmod 0600 "$evidence"/*
