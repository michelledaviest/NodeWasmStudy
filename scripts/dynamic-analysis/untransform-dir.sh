#!/bin/sh

set -eux

tooldir="$(dirname "$0")"
find "$1" -type f -name "*.js" -o -name "*.cjs" -o -name "*.mjs" | xargs --no-run-if-empty -L1 -P$(nproc) "$tooldir"/untransform.py
