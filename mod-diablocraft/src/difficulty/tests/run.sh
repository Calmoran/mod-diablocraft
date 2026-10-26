#!/usr/bin/env bash
# Tier login checks. Linux port of run.ps1: Unix Makefiles, no -C configuration.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "$repo"
cmake --fresh -S mod-diablocraft/src/difficulty/tests -B build/tier-login-tests -G 'Unix Makefiles' -DCMAKE_BUILD_TYPE=Release
cmake --build build/tier-login-tests --parallel "${DC_BUILD_JOBS:-1}"
ctest --test-dir build/tier-login-tests --output-on-failure --no-tests=error
