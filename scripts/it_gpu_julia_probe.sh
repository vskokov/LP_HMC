#!/usr/bin/env bash
# Moved to it_hazel_gpu_probe/ (standalone tarball for Hazel IT).
exec "$(cd "$(dirname "$0")/.." && pwd)/it_hazel_gpu_probe/probe.sh" "$@"
