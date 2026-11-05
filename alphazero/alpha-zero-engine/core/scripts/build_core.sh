#!/usr/bin/env bash
# Build the native Go core for Alpha Zero.
set -euo pipefail
cd "$(dirname "$0")/../alphacore"
mkdir -p ../bin
go build -o ../bin/alphacore .
echo "Built $(cd .. && pwd)/bin/alphacore"
