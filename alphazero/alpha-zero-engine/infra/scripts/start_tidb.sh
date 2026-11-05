#!/usr/bin/env bash
# Download and start a standalone TiDB server (unistore — no PD/TiKV needed).
#
# TiDB is MySQL wire-protocol compatible; the engine's infra.tidb_store
# layer connects over port 4000. During development the same layer can be
# verified against MariaDB/MySQL (see tests).
#
# Usage:
#   ./start_tidb.sh            # download (if needed) and start
#   ./start_tidb.sh stop       # stop the server
set -euo pipefail

VERSION="${TIDB_VERSION:-v8.5.7}"
BASE_DIR="${ALPHA_ZERO_TIDB_DIR:-/opt/alpha-zero/tidb}"
DATA_DIR="${ALPHA_ZERO_TIDB_DATA:-$BASE_DIR/data}"
PORT="${TIDB_PORT:-4000}"
TARBALL="$BASE_DIR/tidb-community-server-$VERSION-linux-amd64.tar.gz"
URL="https://download.pingcap.org/tidb-community-server-$VERSION-linux-amd64.tar.gz"
SERVER="$BASE_DIR/bin/tidb-server"

mkdir -p "$BASE_DIR" "$DATA_DIR"

if [ "$1" = "stop" ]; then
    pkill -f "tidb-server.*$PORT" || true
    echo "TiDB stopped (port $PORT)"
    exit 0
fi

if [ ! -x "$SERVER" ]; then
    echo "Downloading TiDB $VERSION ..."
    curl -fL -o "$TARBALL" "$URL"
    tar -xzf "$TARBALL" -C "$BASE_DIR" --strip-components=1
    rm -f "$TARBALL"
fi

if pgrep -f "tidb-server.*$PORT" > /dev/null; then
    echo "TiDB already running on port $PORT"
    exit 0
fi

nohup "$SERVER" \
    -store unistore \
    -path "$DATA_DIR" \
    -P "$PORT" \
    -log-file "$BASE_DIR/tidb.log" \
    > /dev/null 2>&1 &
echo "TiDB started on port $PORT (pid $!)"
