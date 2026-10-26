#!/usr/bin/env bash
# Stamp X-Torment-Client-Patch in our own addons' TOCs (manifest.py OWN_ADDONS) from VERSION
# client_patch, so the AIO handshake reports the patch the archive was built at.
# Idempotent; only rewrites an existing field line, never appends into the file
# list. Called by client-patch/build.sh before packaging.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/.." && pwd)"
patch="$(sed -n 's/^client_patch=//p' "$root/VERSION")"
[ -n "$patch" ] || { echo "client_patch missing from $root/VERSION" >&2; exit 1; }
for name in Torment ElvUI_Torment; do
    toc="$here/addons/$name/$name.toc"
    [ -f "$toc" ] || continue
    if grep -q '^## X-Torment-Client-Patch:' "$toc"; then
        sed -i "s/^## X-Torment-Client-Patch:.*/## X-Torment-Client-Patch: $patch/" "$toc"
        printf 'stamped %s client_patch=%s\n' "$(basename "$toc")" "$patch"
    else
        printf 'no X-Torment-Client-Patch field in %s\n' "$(basename "$toc")" >&2
        exit 1
    fi
done
