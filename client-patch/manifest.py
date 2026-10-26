#!/usr/bin/env python3
"""Build the launcher's release files: manifest.json and the website feeds (neither is signed).

Follows docs/contracts/launcher-manifest.md; client-patch/release.sh drives it.

    manifest.py client  --staging DIR [--channel stable] [--aio-client DIR]
                        [--elvui-zip FILE] [--allow-dirty] [--no-live-check]
                        [--client-rebuild DIR]
    manifest.py republish --from OLD/manifest.json --staging DIR [--channel stable]
    manifest.py verify-published --work DIR [--channel stable] [--expect FILE] [--readable]
    manifest.py readable-plan --manifest FILE
    manifest.py verify-readable --manifest FILE
    manifest.py feeds --out DIR [--site https://example.com] [--content-dir DIR] [--allow-dirty]
    manifest.py launcher-plan --exe FILE --latest FILE [--channel stable]
    manifest.py verify-launcher --exe FILE --latest FILE [--channel stable]
    manifest.py status-schema-check FILE
    manifest.py conf-get KEY

Output layout under --staging: `<channel>/manifest.json`, blobs as
`files/<sha256>` and a readable copy of each hosted component as
`<channel>/<client_patch>/<name>` (patch-4.MPQ, Torment.zip; the launcher
ignores them), which mirrors the download host. `feeds` writes
`<out>/api/v1/{news,slides,links,patchnotes}.json` and `<out>/media/`, which
mirrors the website (content.json is retired: news, slides, links and patch
notes come from the website unsigned; the features and services flags are in
manifest.json). Settings come from client-patch/release.conf (see
release.conf.example); --conf picks another file.

Every function that release.sh relies on is importable, so test_release.py
calls them directly.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DEFAULT_CONF = HERE / "release.conf"


def releases_dir(repo: Path) -> Path:
    """Where kept copies live: the MAIN checkout's client-patch/.releases (git's common dir), not the
    tree release.sh runs from, which is a clean scratch worktree with an empty folder."""
    r = subprocess.run(["git", "-C", str(repo), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                       capture_output=True, text=True)
    common = Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None
    if common is not None and common.name == ".git":
        return common.parent / "client-patch" / ".releases"
    return Path(repo) / "client-patch" / ".releases"

CHANNELS = ("stable", "nightly")
ZIP_DATE = (1980, 1, 1, 0, 0, 0)
LFS_MAGIC = b"version https://git-lfs"
TOC_FIELD = re.compile(r"^## X-Torment-Client-Patch:\s*(\S+)\s*$", re.M)

KNOWN_MPQS = ["patch.MPQ", "patch-2.MPQ", "patch-3.MPQ", "patch-4.MPQ",
              "patch-{locale}.MPQ", "patch-{locale}-2.MPQ", "patch-{locale}-3.MPQ"]
APPROVED_ADDONS = ["Torment", "ElvUI_Torment", "ElvUI", "ElvUI_OptionsUI", "AIO_Client"]
# Mirror of launcher/engine/src/allow.rs: the launcher (0.1.3+) refuses a manifest whose
# targets are not exactly these, so a release that names anything else must fail here.
# Torment_BountyBoard shipped its own component until 2026-10-10, when the tester board was
# retired (diablocraft-xq7ft): dropped from both lists, so the next update removes the copy
# the launcher installed (launcher-manifest.md section 8).
# The rebuilt 64-bit client: each file at the top of the unpacked client-rebuild CI artefact
# (.github/workflows/client-rebuild.yml, "Stage the artefact"), which is also its WoW-relative
# target, installed only with a sha256 the launcher pins (allow.rs PINNED). The decoder and the
# VC++ runtime come before the exe that loads them. The client extension's DLLs and the Wow.exe
# loader patch are gone; the launcher removes the copies it installed.
CLIENT_REBUILD_FILES = ("XvidDecoder.dll", "msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll",
                        "WowClient64.exe")
ALLOWED_FILE_TARGETS = ("Data/patch-4.MPQ",) + CLIENT_REBUILD_FILES
ALLOWED_ZIP_TARGETS = tuple(f"Interface/AddOns/{a}" for a in APPROVED_ADDONS)
OWN_ADDONS = ("Torment", "ElvUI_Torment")  # folders under client-patch/addons we ship
# The first launcher that installs the rebuilt client (its five file targets and pins) and retires
# the client extension; an older one refuses those targets.
CLIENT_REBUILD_MIN_LAUNCHER = "0.1.12"

NEWS_CATEGORIES = {"announcements", "blog", "seasons", "rifts", "community"}
LINK_ICONS = {"chat", "bug", "doc", "globe"}
NEWS_REQUIRED = ("title", "category", "author", "date", "summary")
PATCH_REQUIRED = ("patch", "date", "title", "summary")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VIDEO_RE = re.compile(r"^::video\[([^\]]+)\]\(([^)\s]+)\)\s*$")
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
ACTION_RE = re.compile(r"^(play|settings|patchnotes:latest|patchnotes:\d+|news:[a-z0-9-]+|url:https://\S+)$")


class ReleaseError(Exception):
    """A refusal, printed as one line."""


# ============================================================ config, version, git

def load_conf(path: Path | None = None) -> dict[str, str]:
    path = Path(path or DEFAULT_CONF)
    if not path.is_file():
        raise ReleaseError(f"{path} not found; copy client-patch/release.conf.example and edit it")
    conf: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        conf[k.strip()] = v.strip()
    return conf


def conf_need(conf: dict, key: str) -> str:
    v = conf.get(key, "")
    if not v:
        raise ReleaseError(f"release.conf has no {key}=")
    return v


def read_version(repo: Path) -> dict[str, str]:
    out = {}
    for line in (Path(repo) / "VERSION").read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def client_patch_of(repo: Path) -> int:
    v = read_version(repo).get("client_patch", "")
    if not v.isdigit():
        raise ReleaseError(f"VERSION client_patch is missing or not a number: {v!r}")
    return int(v)


VERSION_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,4}[a-z]?$")


def game_version_of(repo: Path) -> str:
    """The version players see (decisions.md 2026-10-02): VERSION `module` X.Y.Z plus `launcher_letter`.

    A label for people, never compared: the machine number stays `client_patch`."""
    v = read_version(repo)
    label = v.get("module", "") + v.get("launcher_letter", "")
    if not VERSION_RE.match(label):
        raise ReleaseError(f"VERSION module + launcher_letter is not X.Y.Z or X.Y.Z<letter>: {label!r}")
    return label


def pinned_commit(repo: Path, module: str) -> str | None:
    p = Path(repo) / "modules-commit.txt"
    if not p.is_file():
        return None
    for line in p.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == module:
            return parts[1]
    return None


def git_dirty(repo: Path, paths: list[str]) -> list[str]:
    """Changed or untracked (not ignored) files under `paths`, or raise if not a git checkout."""
    spec = list(paths) + [":(exclude)client-patch/.releases", ":(exclude)client-patch/release.conf"]
    r = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all", "--", *spec],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise ReleaseError(f"{repo} is not a git checkout ({r.stderr.strip()}); use --allow-dirty to skip")
    return [l for l in r.stdout.splitlines() if l.strip()]


def require_clean(repo: Path, paths: list[str]) -> None:
    dirty = git_dirty(repo, paths)
    if dirty:
        raise ReleaseError(f"working tree is dirty ({len(dirty)} file(s), first: {dirty[0].strip()}); commit first")


# ============================================================ fetching

def fetch(url: str, timeout: int = 60) -> bytes | None:
    """GET a URL (https, http, file://, or a local path). None when it does not exist."""
    if url.startswith(("https://", "http://")):
        req = urllib.request.Request(url, headers={"User-Agent": "torment-release/1", "Cache-Control": "no-cache"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise ReleaseError(f"GET {url}: HTTP {e.code}") from None
        except (urllib.error.URLError, OSError) as e:
            raise ReleaseError(f"GET {url}: {e}") from None
    path = Path(url[len("file://"):] if url.startswith("file://") else url)
    return path.read_bytes() if path.is_file() else None


def host_url(host: str, rel: str) -> str:
    return host.rstrip("/") + "/" + rel.lstrip("/")


def live_client_patch(host: str, channel: str) -> int | None:
    data = fetch(host_url(host, f"{channel}/manifest.json"))
    if data is None:
        return None
    try:
        return int(json.loads(data)["client_patch"])
    except (ValueError, KeyError, TypeError):
        raise ReleaseError(f"live {channel}/manifest.json on {host} is unreadable") from None


def live_manifest(host: str, channel: str) -> dict | None:
    data = fetch(host_url(host, f"{channel}/manifest.json"))
    if data is None:
        return None
    try:
        obj = json.loads(data)
        int(obj["client_patch"])
        return obj
    except (ValueError, KeyError, TypeError):
        raise ReleaseError(f"live {channel}/manifest.json on {host} is unreadable") from None


# ============================================================ one number, one build

def head_commit(repo: Path) -> str | None:
    """Full sha of the checkout release.sh runs from; None when it is not a git checkout."""
    r = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True)
    sha = r.stdout.strip()
    return sha if r.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", sha) else None


def component_hashes(manifest: dict) -> dict[str, str]:
    """id -> sha256 (or tree_sha256 for a component with no zip hash): what the build is made of."""
    out = {}
    for c in manifest.get("components", []):
        out[str(c.get("id"))] = str(c.get("sha256") or c.get("tree_sha256") or c.get("url"))
    return out


def same_build(a: dict, b: dict) -> bool:
    """Same commit when both name one; a record from before the field is judged by its component hashes."""
    if a.get("commit") and b.get("commit"):
        return a["commit"] == b["commit"]
    return component_hashes(a) == component_hashes(b)


def used_records(host: str | None, releases: Path, number: int) -> list[tuple[str, str, dict]]:
    """Every record of `number` on either channel: (channel, where it came from, manifest).

    The live manifest, the host's `<channel>/<n>/manifest.json` (uploaded with the readable
    components, fetched by exact name: no listing) and the kept copy in the main checkout's
    client-patch/.releases/<channel>/<n>/ (only the host sources when `host` is None).
    A record that cannot be read refuses.
    """
    found = []
    for ch in CHANNELS:
        if host is not None:
            live = live_manifest(host, ch)
            if live is not None and int(live["client_patch"]) == number:
                found.append((ch, "the live manifest", live))
            url = host_url(host, f"{ch}/{number}/manifest.json")
            data = fetch(url)
            if data is not None:
                try:
                    rec = json.loads(data)
                    if int(rec["client_patch"]) != number:
                        raise ValueError
                except (ValueError, KeyError, TypeError):
                    raise ReleaseError(f"{url} is unreadable; cannot tell whether {number} is used") from None
                found.append((ch, f"{ch}/{number}/manifest.json on the host", rec))
        kept = Path(releases) / ch / str(number) / "manifest.json"
        if kept.is_file():
            try:
                found.append((ch, f"the kept copy {kept}", json.loads(kept.read_text(encoding="utf-8"))))
            except (OSError, ValueError):
                raise ReleaseError(f"{kept} is unreadable; cannot tell whether {number} is used") from None
    return found


def check_number_unused(host: str | None, releases: Path, manifest: dict, channel: str | None = None,
                        republish: bool = False) -> list[str]:
    """One client_patch number is one build on both channels (decisions.md 2026-10-02, next.md).

    Refuses when `manifest`'s number is used on either channel by a different build; the same
    build on the other channel is allowed (Nightly N, then Stable N). Floor, failing closed: a
    number at or below the OTHER channel's live number was possibly used there, so it needs a
    record of that exact number on that channel and it must be the same build; a missing record
    refuses. A republish of a number this channel itself published (its own record found and the
    same build, or the loop above has refused) is never blocked by that floor: a rollback to an
    older Stable must work while Nightly is ahead; a found other-channel record of a different
    build still refuses. Returns the verdict lines."""
    n = int(manifest["client_patch"])
    mine = manifest.get("commit") or "no commit recorded; judged by component hashes"
    lines = []
    seen = set()
    for ch, where, rec in used_records(host, releases, n):
        if not same_build(manifest, rec):
            theirs = rec.get("commit") or "no commit recorded; judged by component hashes"
            raise ReleaseError(f"client_patch {n} is already used on {ch} ({where}) by a different build "
                               f"({theirs}); this build is {mine}. One number is one build: bump VERSION")
        seen.add(ch)
        lines.append(f"{ch} {n} ({where}) is the same build")
    own_record = republish and channel in seen
    if own_record:
        lines.append(f"{channel} {n} is this channel's own record: the other channel's floor does not apply")
    if host is not None and channel is not None and not own_record:
        for other in CHANNELS:
            if other == channel:
                continue
            live = live_manifest(host, other)
            if live is not None and n <= int(live["client_patch"]) and other not in seen:
                raise ReleaseError(f"client_patch {n} is at or below live {other} ({live['client_patch']}) and no "
                                   f"record of {other} {n} was found (host {other}/{n}/manifest.json, kept "
                                   f"copies); cannot tell it is the same build as this one ({mine}). "
                                   f"One number is one build: bump VERSION")
    if not lines:
        lines.append(f"{n} is not used on stable or nightly")
    return lines


# ============================================================ hashing, blobs, zips

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_allowed_targets(components: list[dict]) -> None:
    """Refuse, at release time, a component the launcher's allow-list would refuse at every player."""
    for c in components:
        if c["kind"] == "file":
            targets = [c["target"]]
            allowed = ALLOWED_FILE_TARGETS
        elif c["kind"] == "zip":
            targets = list(c["folders"].values())
            allowed = ALLOWED_ZIP_TARGETS
        else:
            raise ReleaseError(f"component {c['id']}: unknown kind {c['kind']!r}")
        for t in targets:
            if t.rstrip("/").lower() not in (a.lower() for a in allowed):
                raise ReleaseError(f"component {c['id']}: target {t!r} is not on the launcher's allow-list "
                                   f"({', '.join(allowed)}); a launcher release must add it first")


def store_blob(staging: Path, *, data: bytes | None = None, path: Path | None = None) -> tuple[str, int]:
    """Copy bytes or a file to staging/files/<sha256>. Returns (sha256, size)."""
    files = Path(staging) / "files"
    files.mkdir(parents=True, exist_ok=True)
    if data is not None:
        sha, size = sha256_bytes(data), len(data)
        dest = files / sha
        if not dest.exists():
            dest.write_bytes(data)
    else:
        sha, size = sha256_file(path), Path(path).stat().st_size
        dest = files / sha
        if not dest.exists():
            shutil.copyfile(path, dest)
    return sha, size


def tree_hash(entries: dict[str, str]) -> str:
    """Contract section 2: sorted `<path>\\t<sha256>\\n` lines, SHA-256 of the concatenation."""
    lines = sorted(entries.items(), key=lambda kv: kv[0].encode("utf-8"))
    return sha256_bytes("".join(f"{p}\t{h}\n" for p, h in lines).encode("utf-8"))


def safe_rel(path: str) -> bool:
    return not (path.startswith("/") or "\\" in path or re.match(r"^[A-Za-z]:", path)
                or any(part == ".." for part in path.split("/")))


def tree_hash_from_zip(zip_bytes: bytes, folders: dict[str, str]) -> str:
    """Tree hash of the files a zip installs, given the contract's `folders` map."""
    entries: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        for info in z.infolist():
            name = info.filename
            if name.endswith("/"):
                continue
            if not safe_rel(name):
                raise ReleaseError(f"zip entry {name!r} is unsafe")
            for src, dst in folders.items():
                prefix = src.rstrip("/") + "/"
                if name.startswith(prefix):
                    entries[dst.rstrip("/") + "/" + name[len(prefix):]] = sha256_bytes(z.read(info))
                    break
    if not entries:
        raise ReleaseError(f"zip has no files under {', '.join(folders)}")
    return tree_hash(entries)


def tree_hash_dir(wow_root: Path, targets: list[str]) -> str:
    """Tree hash of installed folders under a WoW root (what the engine computes)."""
    entries = {}
    for t in targets:
        base = Path(wow_root) / t
        for p in base.rglob("*"):
            if p.is_file() and not p.is_symlink():
                entries[p.relative_to(wow_root).as_posix()] = sha256_file(p)
    return tree_hash(entries)


def _shipped(rel: Path) -> bool:
    # Hidden files and caches never ship (.git, .DS_Store, __pycache__).
    return not any(part.startswith(".") or part == "__pycache__" for part in rel.parts)


def deterministic_zip(folders: list[tuple[Path, str]], extra: list[tuple[str, Path]] = ()) -> bytes:
    """Zip each (source dir, top-level name) with sorted entries, fixed times, 0644/0755 perms.

    `extra` adds (arcname, file) pairs, e.g. a LICENSE kept beside the folder.
    """
    items: dict[str, Path | None] = {}
    for src, top in folders:
        src = Path(src)
        if not src.is_dir():
            raise ReleaseError(f"addon folder {src} not found")
        items[top + "/"] = None
        for p in src.rglob("*"):
            rel = p.relative_to(src)
            if not _shipped(rel) or p.is_symlink():
                continue
            arc = top + "/" + rel.as_posix()
            if p.is_dir():
                items[arc + "/"] = None
            elif p.is_file():
                items[arc] = p
    for arc, p in extra:
        items[arc] = Path(p)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for arc in sorted(items, key=lambda s: s.encode("utf-8")):
            info = zipfile.ZipInfo(arc, date_time=ZIP_DATE)
            info.create_system = 3
            if arc.endswith("/"):
                info.external_attr = ((stat.S_IFDIR | 0o755) << 16) | 0x10
                info.compress_type = zipfile.ZIP_STORED
                z.writestr(info, b"")
            else:
                src = items[arc]
                mode = 0o755 if src.stat().st_mode & 0o100 else 0o644
                info.external_attr = (stat.S_IFREG | mode) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, src.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return buf.getvalue()


# ============================================================ client manifest

def check_tocs(addons: Path, client_patch: int) -> None:
    for name in OWN_ADDONS:
        toc = Path(addons) / name / f"{name}.toc"
        if not toc.is_file():
            raise ReleaseError(f"{toc} not found")
        m = TOC_FIELD.search(toc.read_text(encoding="utf-8", errors="replace"))
        stamped = m.group(1) if m else None
        if stamped != str(client_patch):
            raise ReleaseError(f"{name}.toc X-Torment-Client-Patch is {stamped}, VERSION client_patch is "
                               f"{client_patch}; run client-patch/stamp_client_patch.sh and commit")


# The 3.3.5 client signature-checks the login (GlueXML) and in-world (FrameXML) interface
# files and shows "Your login interface files are corrupt" for any edited one (Nightly 52,
# 2026-10-02: patch-4.MPQ carried Interface/GlueXML/CharacterCreate.lua). Our MPQ holds a file
# under either folder only when the release also ships a build whose launcher pin carries the
# glue-unlock flag (allow.rs PINNED): the rebuilt client, built with the signature checks off
# (build.sh follows the same rule). A player who starts the stock Wow.exe still gets the MPQ and
# the corrupt-interface error, and that exe is refused at login anyway.
FORBIDDEN_MPQ_PREFIXES = ("interface/gluexml/", "interface/framexml/")


def list_mpq(mpq: Path) -> list[str]:
    """The archive's entry names, as smpq -l prints them. Fails closed: an archive that
    cannot be listed cannot be shown clean."""
    exe = shutil.which("smpq")
    if not exe:
        raise ReleaseError("smpq not found; cannot list patch-4.MPQ to prove it has no GlueXML/FrameXML "
                           "file (sudo apt install smpq)")
    r = subprocess.run([exe, "-l", str(mpq)], capture_output=True, text=True)
    if r.returncode != 0:
        raise ReleaseError(f"{Path(mpq).name} cannot be listed ({(r.stderr or r.stdout).strip()}); "
                           "it is not a readable MPQ")
    names = []
    for line in r.stdout.splitlines():
        parts = line.split(None, 3)       # size, date, time, name
        if len(parts) == 4:
            names.append(parts[3].strip())
    return names


def forbidden_mpq_entries(names: list[str]) -> list[str]:
    return [n for n in names if n.replace("\\", "/").lower().startswith(FORBIDDEN_MPQ_PREFIXES)]


def check_mpq(mpq: Path, glue_unlock: bool = False) -> list[str]:
    """Refuse an archive that is not the built MPQ, or that holds a GlueXML/FrameXML file when the
    release ships no glue-unlock build. Returns the GlueXML/FrameXML files it lets through."""
    if not Path(mpq).is_file():
        raise ReleaseError(f"{mpq} not found; run client-patch/build.sh")
    with open(mpq, "rb") as f:
        if f.read(len(LFS_MAGIC)) == LFS_MAGIC:
            raise ReleaseError(f"{mpq.name} is a Git LFS pointer, not the built archive; "
                               "run `git lfs pull` or client-patch/build.sh")
    bad = forbidden_mpq_entries(list_mpq(mpq))
    if bad and not glue_unlock:
        raise ReleaseError(f"{Path(mpq).name} contains {', '.join(bad)}: the 3.3.5 client signature-checks "
                           "Interface/GlueXML and Interface/FrameXML and refuses to start with an edited "
                           "file (\"Your login interface files are corrupt\"). Such a file ships only with "
                           "--client-rebuild and a build whose pin in "
                           f"{LAUNCHER_ALLOW_RS} PINNED carries the glue-unlock flag; otherwise remove it "
                           "from client-patch/art.")
    return bad


def check_aio_pin(repo: Path, aio_client: Path) -> None:
    """Refuse to package unless the AIO folder (the parent of AIO_Client) is the top
    of its own git checkout at the commit modules-commit.txt pins. A folder inside
    another checkout would answer for that repo instead, so it is refused too
    (the designer, docs/briefs/launcher-followup-brief.md §1)."""
    want = pinned_commit(repo, "AIO")
    if not want:
        raise ReleaseError(f"modules-commit.txt in {repo} has no AIO pin")
    aio_root = Path(aio_client).resolve().parent
    top = subprocess.run(["git", "-C", str(aio_root), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True)
    if top.returncode != 0 or Path(top.stdout.strip()).resolve() != aio_root:
        raise ReleaseError(f"{aio_root} is not the top of its own git checkout; check out AIO at {want[:12]} "
                           "and point aio_client= at its AIO_Client folder")
    r = subprocess.run(["git", "-C", str(aio_root), "rev-parse", "HEAD"], capture_output=True, text=True)
    head = r.stdout.strip()
    if r.returncode != 0 or head != want:
        raise ReleaseError(f"AIO checkout is at {head[:12] or '?'}, modules-commit.txt pins {want[:12]}")


def zip_component(staging: Path, cid: str, zip_bytes: bytes, top: str) -> dict:
    sha, size = store_blob(staging, data=zip_bytes)
    folders = {top: f"Interface/AddOns/{top}"}
    return {"id": cid, "kind": "zip", "name": cid, "url": f"files/{sha}", "sha256": sha, "size": size,
            "folders": folders, "tree_sha256": tree_hash_from_zip(zip_bytes, folders)}


def elvui_component(conf: dict, elvui_zip: Path | None) -> dict:
    commit = conf_need(conf, "elvui_commit")
    url = conf_need(conf, "elvui_url")
    if not url.startswith(("https://github.com/", "https://codeload.github.com/")):
        raise ReleaseError(f"elvui_url must be on github.com or codeload.github.com: {url}")
    if commit not in url:
        raise ReleaseError("elvui_url does not contain elvui_commit")
    data = Path(elvui_zip).read_bytes() if elvui_zip else fetch(url, timeout=300)
    if data is None:
        raise ReleaseError(f"ElvUI archive not found at {url}")
    root = f"ElvUI-{commit}"
    folders = {f"{root}/ElvUI": "Interface/AddOns/ElvUI",
               f"{root}/ElvUI_OptionsUI": "Interface/AddOns/ElvUI_OptionsUI"}
    return {"id": "ElvUI", "kind": "zip", "name": conf.get("elvui_name", "ElvUI"), "url": url,
            "sha256": None, "size": 0, "folders": folders,
            "tree_sha256": tree_hash_from_zip(data, folders)}


def aio_zip(aio_client: Path) -> bytes:
    aio_client = Path(aio_client)
    if not aio_client.is_dir():
        raise ReleaseError(f"AIO_Client folder {aio_client} not found (--aio-client or aio_client= in release.conf)")
    extra = []
    if not any(p.name.upper().startswith("LICENSE") for p in aio_client.iterdir()):
        for p in sorted(aio_client.parent.glob("LICENSE*")):
            if p.is_file():
                extra.append((f"AIO_Client/{p.name}", p))
    return deterministic_zip([(aio_client, "AIO_Client")], extra)


def version_tuple(v: str) -> tuple[int, ...]:
    if not re.fullmatch(r"\d+(\.\d+)*", v):
        raise ReleaseError(f"{v!r} is not a launcher version")
    return tuple(int(p) for p in v.split("."))


LAUNCHER_ALLOW_RS = Path("launcher") / "engine" / "src" / "allow.rs"
PIN_ROW_RE = re.compile(r'\(\s*"([^"]+)",\s*"([0-9a-f]{64})",\s*(true|false),?\s*\)')


def launcher_pins(repo: Path) -> dict[str, dict[str, bool]]:
    """The rebuilt client's builds the launcher of this commit installs: lowercased target ->
    {pinned sha256: glue-unlock flag}, read from the PINNED constant of launcher/engine/src/allow.rs.
    A row it cannot read refuses, a pending pin included, so no pin or flag is dropped."""
    path = Path(repo) / LAUNCHER_ALLOW_RS
    try:
        src = path.read_text(encoding="utf-8")
    except OSError:
        raise ReleaseError(f"{path} not found; cannot tell which builds the launcher installs") from None
    m = re.search(r"const PINNED: \[\(&str, &str, bool\); (\d+)\] = \[(.*?)\n\];", src, re.S)
    if not m:
        raise ReleaseError(f"no pins found in {path} (const PINNED)")
    pending = re.findall(r'"(PIN_PENDING[^"]*)"', m.group(2))
    if pending:
        raise ReleaseError(f"{path} const PINNED has a pending pin ({', '.join(pending)}): the hash of that "
                           "file in the client-rebuild CI artefact goes there before any release")
    rows = PIN_ROW_RE.findall(m.group(2))
    if len(rows) != int(m.group(1)):
        raise ReleaseError(f"{path} const PINNED has {m.group(1)} rows but {len(rows)} read as "
                           "(target, sha256, glue-unlock flag)")
    pins: dict[str, dict[str, bool]] = {}
    for target, sha, flag in rows:
        pins.setdefault(target.lower(), {})[sha] = flag == "true"
    return pins


def ships_glue_unlock(rebuild_dir: Path, repo: Path = REPO) -> bool:
    """Whether the client-rebuild artefact in `rebuild_dir` holds a build whose launcher pin carries
    the glue-unlock flag (the rebuilt exe, built with the signature checks off).
    client_rebuild_components refuses a missing or unpinned file on its own."""
    pins = launcher_pins(repo)
    for rel in CLIENT_REBUILD_FILES:
        f = Path(rebuild_dir) / rel
        if f.is_file() and pins.get(rel.lower(), {}).get(sha256_file(f), False):
            return True
    return False


def client_rebuild_components(staging: Path, rebuild_dir: Path, conf: dict, repo: Path = REPO) -> list[dict]:
    """The rebuilt 64-bit client's components, from the client-rebuild CI artefact unpacked in
    `rebuild_dir`: XvidDecoder.dll, the VC++ x64 runtime and WowClient64.exe, each `kind: file` at
    its own name in the game folder. Each must be the very build the launcher of this commit pins:
    MSVC builds differ run to run, so a release ships the one artefact whose hashes are in allow.rs."""
    rebuild_dir = Path(rebuild_dir)
    if version_tuple(conf_need(conf, "min_launcher")) < version_tuple(CLIENT_REBUILD_MIN_LAUNCHER):
        raise ReleaseError(f"the rebuilt client needs min_launcher {CLIENT_REBUILD_MIN_LAUNCHER} or later "
                           "(an older launcher refuses its file targets)")
    pins = launcher_pins(repo)
    components = []
    for rel in CLIENT_REBUILD_FILES:
        f = rebuild_dir / rel
        if not f.is_file():
            raise ReleaseError(f"{rel} not found in {rebuild_dir}: unpack the client-rebuild CI artefact there")
        with open(f, "rb") as fh:
            if fh.read(2) != b"MZ":
                raise ReleaseError(f"{f} is not a Windows image")
        sha = sha256_file(f)
        if sha not in pins.get(rel.lower(), {}):
            raise ReleaseError(f"{rel} in {rebuild_dir} is sha256 {sha}, not a build the launcher pins "
                               f"({LAUNCHER_ALLOW_RS} PINNED): a client change needs its hashes there and a "
                               "launcher release first, and the release ships that same CI artefact (MSVC "
                               "builds differ run to run)")
        sha, size = store_blob(staging, path=f)
        components.append({"id": rel, "kind": "file", "name": rel, "url": f"files/{sha}", "sha256": sha,
                           "size": size, "target": rel})
    return components


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def build_client(repo: Path, conf: dict, staging: Path, channel: str, *, aio_client: Path | None = None,
                 elvui_zip: Path | None = None, allow_dirty: bool = False, live_check: bool = True,
                 releases: Path | None = None, log=None, client_rebuild: Path | None = None) -> dict:
    repo, staging = Path(repo), Path(staging)
    if channel not in CHANNELS:
        raise ReleaseError(f"unknown channel {channel}")
    if not allow_dirty:
        require_clean(repo, ["client-patch", "VERSION", "modules-commit.txt"])
    client_patch = client_patch_of(repo)
    addons = repo / "client-patch" / "addons"
    check_tocs(addons, client_patch)
    mpq = repo / "client-patch" / "patch-4.MPQ"
    glue_unlock = client_rebuild is not None and ships_glue_unlock(client_rebuild, repo)
    signed = check_mpq(mpq, glue_unlock)
    if signed and log:
        log(f"patch-4.MPQ ships {len(signed)} GlueXML/FrameXML file(s) with the glue-unlock build: "
            + ", ".join(signed))
    host = conf_need(conf, "host")
    if live_check:
        live = live_client_patch(host, channel)
        if live is not None and client_patch <= live:
            raise ReleaseError(f"VERSION client_patch {client_patch} is not greater than live {channel} "
                               f"({live}); bump VERSION or use release.sh republish")
    aio_client = Path(aio_client or conf_need(conf, "aio_client"))
    check_aio_pin(repo, aio_client)
    features, services = build_services(conf)

    sha, size = store_blob(staging, path=mpq)
    components = [{"id": "patch-4", "kind": "file", "name": "patch-4.MPQ", "url": f"files/{sha}",
                   "sha256": sha, "size": size, "target": "Data/patch-4.MPQ"}]
    for name in OWN_ADDONS:
        components.append(zip_component(staging, name, deterministic_zip([(addons / name, name)]), name))
    components.append(zip_component(staging, "AIO_Client", aio_zip(aio_client), "AIO_Client"))
    components.append(elvui_component(conf, elvui_zip))
    if client_rebuild is not None:
        components.extend(client_rebuild_components(staging, client_rebuild, conf, repo))

    check_allowed_targets(components)
    manifest = {
        "schema": 1,
        "channel": channel,
        "client_patch": client_patch,
        "version": game_version_of(repo),
        "released": utc_now(),
        "min_launcher": conf_need(conf, "min_launcher"),
        "realmlist": conf_need(conf, "realmlist"),
        "features": features,
        "services": services,
        "components": components,
        "known_mpqs": KNOWN_MPQS,
        "approved_addons": APPROVED_ADDONS,
    }
    # The build's source: only a clean checkout names one (a dirty tree is not its HEAD).
    commit = head_commit(repo)
    if commit and not git_dirty(repo, ["client-patch", "VERSION", "modules-commit.txt"]):
        manifest["commit"] = commit
    # Before anything is written for upload. --no-live-check skips the host reads only.
    for line in check_number_unused(host if live_check else None,
                                    Path(releases or releases_dir(repo)), manifest, channel):
        if log:
            log(f"number guard: {line}")
    write_json(staging / channel / "manifest.json", manifest)
    stage_readable(staging, manifest)
    return manifest


SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def readable_plan(manifest: dict) -> list[tuple[str, str]]:
    """Readable copies of a release's hosted components: (path under the host, sha256 of the blob).

    `<channel>/<client_patch>/patch-4.MPQ`, `.../Torment.zip`: the same bytes as
    the `files/<sha256>` blob, under a name a person can use from a link. The
    launcher never reads them. Components hosted elsewhere (ElvUI on GitHub)
    have no blob and no copy.
    """
    base = f"{manifest['channel']}/{manifest['client_patch']}"
    plan: list[tuple[str, str]] = []
    for c in manifest["components"]:
        sha = c.get("sha256")
        if not sha or c.get("url") != f"files/{sha}":
            continue
        name = os.path.basename(c["target"]) if c["kind"] == "file" else f"{c['id']}.zip"
        if not SAFE_NAME.match(name):
            raise ReleaseError(f"component {c['id']}: no safe readable name (got {name!r})")
        plan.append((f"{base}/{name}", sha))
    names = [p for p, _ in plan]
    if len(set(names)) != len(names):
        raise ReleaseError("two components share a readable name")
    return plan


def stage_readable(staging: Path, manifest: dict) -> list[str]:
    """Copy each planned blob from staging/files to its readable path under staging."""
    staging = Path(staging)
    out = []
    for rel, sha in readable_plan(manifest):
        dest = staging / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(staging / "files" / sha, dest)
        out.append(rel)
    return out


def republish(src: Path, staging: Path, channel: str, conf: dict | None = None,
              releases: Path | None = None, log=None) -> dict:
    """Republish a kept manifest as-is with a new `released` time.

    A manifest kept from before features/services moved into it gets them from
    release.conf, so a rollback does not lose the flags.
    """
    manifest = json.loads(Path(src).read_text())
    if manifest.get("schema") != 1 or manifest.get("channel") != channel:
        raise ReleaseError(f"{src} is not a schema 1 manifest for channel {channel}")
    if conf is not None:  # the kept build may not take a number another build holds on either channel
        for line in check_number_unused(conf_need(conf, "host"), Path(releases or releases_dir(REPO)), manifest,
                                    channel, republish=True):
            if log:
                log(f"number guard: {line}")
    manifest["released"] = utc_now()
    if conf is not None and ("features" not in manifest or "services" not in manifest):
        features, services = build_services(conf)
        manifest.setdefault("features", features)
        manifest.setdefault("services", services)
    write_json(Path(staging) / channel / "manifest.json", manifest)
    return manifest


# ============================================================ website feeds (interim)
#
# News, slides, links and patch notes are served unsigned by the website at
# <site>/api/v1/{news,slides,links,patchnotes}.json (docs/proposals/website.md
# section 8). Until the website writes them itself, `feeds` builds the same four
# files from launcher/content/.

DEFAULT_SITE = "https://example.com"
API_PATH = "api/v1"
FEED_MAX_BYTES = 1 << 20  # each file must stay under 1 MiB
NEWS_MAX = 50
DEFAULT_TINT = "#e0703f"
NAMED_TINTS = {"ember": "#e0703f", "violet": "#9a6bd0", "teal": "#5ab4a0", "gold": "#c9a45c"}
TINT_RE = re.compile(r"^#[0-9a-f]{6}$")
SHORT_TINT_RE = re.compile(r"^#[0-9a-f]{3}$")
MEDIA_EXT_RE = re.compile(r"^\.[a-z0-9]{1,5}$")


def parse_front_matter(text: str, where: str) -> tuple[dict, str]:
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        raise ReleaseError(f"{where}: no front matter (first line must be ---)")
    meta: dict = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body = "\n".join(lines[i + 1:]).strip("\n")
            return meta, body
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ReleaseError(f"{where}:{i + 1}: expected `key: value`")
        k, v = line.split(":", 1)
        v = re.sub(r"\s+#.*$", "", v).strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        meta[k.strip()] = v
    raise ReleaseError(f"{where}: front matter is not closed with ---")


def _bool(v: str, where: str) -> bool:
    if v.lower() in ("true", "yes"):
        return True
    if v.lower() in ("false", "no", ""):
        return False
    raise ReleaseError(f"{where}: expected true or false, got {v!r}")


class Media:
    """Resolves content-relative media paths, copies each file to <out>/media/<sha256>.<ext>
    and returns its absolute URL on the site."""

    def __init__(self, content_dir: Path, out: Path, site: str = DEFAULT_SITE):
        self.root, self.out, self.site = Path(content_dir), Path(out), site.rstrip("/")

    def ref(self, ref: str, where: str, near: Path | None = None) -> str:
        if ref.startswith(("https://", "http://", "files/")):
            raise ReleaseError(f"{where}: media {ref!r} must be a file in launcher/content/, not a URL")
        if not safe_rel(ref):
            raise ReleaseError(f"{where}: unsafe media path {ref!r}")
        for base in ([near] if near else []) + [self.root, self.root / "media"]:
            p = base / ref
            if p.is_file():
                ext = p.suffix.lower()
                if not MEDIA_EXT_RE.match(ext):
                    raise ReleaseError(f"{where}: media {ref!r} needs a file extension")
                name = f"{sha256_file(p)}{ext}"
                dest = self.out / "media" / name
                if not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(p, dest)
                return f"{self.site}/media/{name}"
        raise ReleaseError(f"{where}: media {ref!r} not found")


def rewrite_body(body: str, media: Media, where: str, near: Path) -> str:
    out = []
    for n, line in enumerate(body.split("\n"), start=1):
        m = VIDEO_RE.match(line.strip())
        if m:
            line = f"::video[{media.ref(m.group(1), f'{where}:{n}', near)}]({media.ref(m.group(2), f'{where}:{n}', near)})"
        elif line.strip().startswith("::video"):
            raise ReleaseError(f"{where}:{n}: malformed ::video line (want ::video[cover](video))")
        else:
            def img(mm):
                target = mm.group(2)
                if target.startswith("https://"):
                    return mm.group(0)
                return f"![{mm.group(1)}]({media.ref(target, f'{where}:{n}', near)})"
            line = IMAGE_RE.sub(img, line)
        out.append(line)
    return "\n".join(out)


def load_news(content_dir: Path, media: Media) -> list[dict]:
    posts = []
    for p in sorted((content_dir / "news").glob("*.md")):
        where = f"news/{p.name}"
        if not ID_RE.match(p.stem):
            raise ReleaseError(f"{where}: file name must be lower-case letters, digits and dashes")
        meta, body = parse_front_matter(p.read_text(encoding="utf-8"), where)
        missing = [k for k in NEWS_REQUIRED if not meta.get(k)]
        if missing:
            raise ReleaseError(f"{where}: missing {', '.join(missing)}")
        if meta["category"] not in NEWS_CATEGORIES:
            raise ReleaseError(f"{where}: unknown category {meta['category']!r} "
                               f"(one of {', '.join(sorted(NEWS_CATEGORIES))})")
        if not DATE_RE.match(meta["date"]):
            raise ReleaseError(f"{where}: date must be YYYY-MM-DD")
        unknown = set(meta) - set(NEWS_REQUIRED) - {"cover", "featured"}
        if unknown:
            raise ReleaseError(f"{where}: unknown field(s) {', '.join(sorted(unknown))}")
        post = {"id": p.stem, **{k: meta[k] for k in NEWS_REQUIRED},
                "cover": media.ref(meta["cover"], where, p.parent) if meta.get("cover") else None,
                "featured": _bool(meta.get("featured", ""), where),
                "body_md": rewrite_body(body, media, where, p.parent)}
        posts.append(post)
    posts.sort(key=lambda x: (x["date"], x["id"]), reverse=True)
    return posts[:NEWS_MAX]


def load_patchnotes(content_dir: Path, media: Media) -> list[dict]:
    notes = []
    for p in sorted((content_dir / "patchnotes").glob("*.md")):
        where = f"patchnotes/{p.name}"
        meta, body = parse_front_matter(p.read_text(encoding="utf-8"), where)
        missing = [k for k in PATCH_REQUIRED if not meta.get(k)]
        if missing:
            raise ReleaseError(f"{where}: missing {', '.join(missing)}")
        if not meta["patch"].isdigit() or meta["patch"] != p.stem:
            raise ReleaseError(f"{where}: patch must be a number equal to the file name")
        if not DATE_RE.match(meta["date"]):
            raise ReleaseError(f"{where}: date must be YYYY-MM-DD")
        note = {"patch": int(meta["patch"]), "date": meta["date"], "title": meta["title"],
                "summary": meta["summary"], "body_md": rewrite_body(body, media, where, p.parent)}
        if meta.get("version"):  # optional: the launcher falls back to "Patch N" without it
            if not VERSION_RE.match(meta["version"]):
                raise ReleaseError(f"{where}: version must be X.Y.Z or X.Y.Z<letter>")
            note["version"] = meta["version"]
        notes.append(note)
    notes.sort(key=lambda x: x["patch"], reverse=True)
    return notes


def _load_json(path: Path, key: str):
    if not path.is_file():
        raise ReleaseError(f"{path.name} not found in launcher/content/")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ReleaseError(f"{path.name}: invalid JSON: {e}") from None
    return data if isinstance(data, dict) else {key: data}


def check_action(action: str, where: str, news_ids: set, patches: set) -> None:
    if not isinstance(action, str) or not ACTION_RE.match(action):
        raise ReleaseError(f"{where}: invalid action {action!r} (play, settings, news:<id>, "
                           "patchnotes:<n>, patchnotes:latest or url:https://...)")
    if action.startswith("news:") and action[5:] not in news_ids:
        raise ReleaseError(f"{where}: {action} names no news post")
    if action.startswith("patchnotes:") and action[11:] != "latest" and int(action[11:]) not in patches:
        raise ReleaseError(f"{where}: {action} names no patch notes file")


def normalise_tint(v) -> str:
    """A `#rrggbb` colour; old named tints map to their hex, anything malformed falls back to ember."""
    if not isinstance(v, str):
        return DEFAULT_TINT
    v = v.strip().lower()
    if v in NAMED_TINTS:
        return NAMED_TINTS[v]
    if SHORT_TINT_RE.match(v):
        return "#" + "".join(c * 2 for c in v[1:])
    return v if TINT_RE.match(v) else DEFAULT_TINT


def _focus(v, where: str) -> int:
    if v is None:
        return 50
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 100:
        raise ReleaseError(f"{where}: must be a number from 0 to 100")
    return int(round(v))


def load_slides(content_dir: Path, media: Media, news_ids: set, patches: set) -> tuple[list, int]:
    data = _load_json(content_dir / "slides.json", "slides")
    seconds = data.get("slide_seconds", 8)
    if not isinstance(seconds, int) or isinstance(seconds, bool) or seconds <= 0:
        raise ReleaseError("slides.json: slide_seconds must be a positive integer")
    slides, seen = [], set()
    for i, s in enumerate(data.get("slides", [])):
        where = f"slides.json slide {i + 1}"
        if not isinstance(s, dict) or not s.get("id") or not s.get("title"):
            raise ReleaseError(f"{where}: needs id and title")
        if s["id"] in seen:
            raise ReleaseError(f"{where}: duplicate id {s['id']}")
        seen.add(s["id"])
        s = dict(s)
        for key in ("image", "cover", "video"):
            if s.get(key):
                s[key] = media.ref(s[key], f"{where} {key}")
        s.setdefault("active", True)
        s.setdefault("order", i + 1)
        s["focus_x"] = _focus(s.get("focus_x"), f"{where} focus_x")
        s["focus_y"] = _focus(s.get("focus_y"), f"{where} focus_y")
        s["tint"] = normalise_tint(s.get("tint"))
        for j, b in enumerate(s.get("buttons", [])):
            if not isinstance(b, dict) or not b.get("label"):
                raise ReleaseError(f"{where} button {j + 1}: needs a label")
            check_action(b.get("action"), f"{where} button {j + 1}", news_ids, patches)
        if s["active"]:  # the website serves only the slides switched on
            slides.append(s)
    slides.sort(key=lambda x: x["order"])
    return slides, seconds


def load_links(content_dir: Path) -> tuple[list, list]:
    """Returns (links, dropped ids). `app:` links are built into the launcher and never served."""
    data = _load_json(content_dir / "links.json", "links")
    links, dropped = [], []
    for i, l in enumerate(data.get("links", [])):
        where = f"links.json link {i + 1}"
        if not isinstance(l, dict) or not l.get("id") or not l.get("title") or not l.get("url"):
            raise ReleaseError(f"{where}: needs id, title and url")
        if l["url"].startswith("app:"):
            dropped.append(l["id"])
            continue
        if l.get("icon") not in LINK_ICONS:
            raise ReleaseError(f"{where}: icon must be one of {', '.join(sorted(LINK_ICONS))}")
        if not l["url"].startswith("https://"):
            raise ReleaseError(f"{where}: url must be https://")
        l = dict(l)
        l.setdefault("active", True)
        l.setdefault("order", i + 1)
        if l["active"]:
            links.append(l)
    links.sort(key=lambda x: x["order"])
    return links, dropped


def feed_bytes(obj, name: str) -> bytes:
    data = (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if len(data) >= FEED_MAX_BYTES:
        raise ReleaseError(f"{name} is {len(data)} bytes; each feed must stay under 1 MiB")
    return data


def build_feeds(repo: Path, out: Path, *, site: str = DEFAULT_SITE, content_dir: Path | None = None,
                allow_dirty: bool = False) -> dict:
    """Write <out>/api/v1/{news,slides,links,patchnotes}.json and <out>/media/. Returns the four objects."""
    repo, out = Path(repo), Path(out)
    if not site.startswith("https://"):
        raise ReleaseError(f"--site must be https://, got {site}")
    content_dir = Path(content_dir or repo / "launcher" / "content")
    if not content_dir.is_dir():
        raise ReleaseError(f"{content_dir} not found")
    if not allow_dirty:
        require_clean(repo, [str(content_dir.relative_to(repo))] if content_dir.is_relative_to(repo) else [])
    media = Media(content_dir, out, site)
    news = load_news(content_dir, media)
    patchnotes = load_patchnotes(content_dir, media)
    slides, seconds = load_slides(content_dir, media, {n["id"] for n in news}, {p["patch"] for p in patchnotes})
    links, dropped = load_links(content_dir)
    feeds = {
        "news": {"news": news},
        "slides": {"slide_seconds": seconds, "slides": slides},
        "links": {"links": links},
        "patchnotes": {"patchnotes": patchnotes},
    }
    data = {k: feed_bytes(v, f"{k}.json") for k, v in feeds.items()}  # check all before writing any
    api = out / API_PATH
    api.mkdir(parents=True, exist_ok=True)
    for k, b in data.items():
        (api / f"{k}.json").write_bytes(b)
    feeds["dropped_links"] = dropped
    return feeds


# ============================================================ launcher exe (release.sh launcher)

LAUNCHER_RE = re.compile(r"^TormentLauncher_(\d+\.\d+\.\d+)\.exe$")
LAUNCHER_FIXED = "TormentLauncher.exe"
# The CI artefact's feed per channel (launcher.yml writes both; diablocraft-oae32).
LAUNCHER_FEEDS = {"stable": "latest.json", "nightly": "latest-nightly.json"}


def launcher_urls(feed: dict) -> dict[str, str]:
    """latest.json's download url per platform."""
    platforms = feed.get("platforms") if isinstance(feed, dict) else None
    if not isinstance(platforms, dict):
        return {}
    return {name: str((p or {}).get("url", "")) if isinstance(p, dict) else "" for name, p in platforms.items()}


def launcher_plan(exe: Path, latest: Path, channel: str, host: str) -> list[tuple[Path, str]]:
    """Upload order for a launcher release: (local file, path under the rclone target).

    The versioned exe and its .sig, then the same exe under the fixed name the
    website links to (the first-install address), then latest.json last so the
    updater never points at a file that is not there yet. latest.json must
    describe this exe: version, sha256, size and the .sig's signature, and every
    platform url must be <host>/launcher/<channel>/<exe> (a nightly publish of the
    stable feed pointed the self-update at a 404, diablocraft-nk3l; CI writes one
    feed per channel, LAUNCHER_FEEDS). A wrong url is refused, never rewritten.
    """
    exe, latest = Path(exe), Path(latest)
    if channel not in CHANNELS:
        raise ReleaseError(f"unknown channel {channel}")
    if not exe.is_file():
        raise ReleaseError(f"launcher exe {exe} not found")
    m = LAUNCHER_RE.match(exe.name)
    if not m:
        raise ReleaseError(f"launcher exe must be named TormentLauncher_X.Y.Z.exe, got {exe.name}")
    if not latest.is_file():
        raise ReleaseError(f"{latest} not found")
    try:
        feed = json.loads(latest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ReleaseError(f"{latest.name}: invalid JSON: {e}") from None
    version = str(feed.get("version", "")).lstrip("v") if isinstance(feed, dict) else ""
    if version != m.group(1):
        raise ReleaseError(f"{latest.name} version {version or '(none)'} does not match {exe.name}")
    win = (feed.get("platforms") or {}).get("windows-x86_64") or {}
    want = host_url(host, f"launcher/{channel}/{exe.name}")
    urls = launcher_urls(feed)
    urls.setdefault("windows-x86_64", "")
    for name, url in sorted(urls.items()):
        if url != want:
            raise ReleaseError(f"{latest.name} {name} url is {url or '(none)'}, not {want}: the self-update "
                               f"downloads from that address; publish the CI artefact's {LAUNCHER_FEEDS[channel]} "
                               f"for the {channel} channel")
    if win.get("sha256") != sha256_file(exe):
        raise ReleaseError(f"{latest.name} windows-x86_64 sha256 is not {exe.name}'s")
    if win.get("size") != exe.stat().st_size:
        raise ReleaseError(f"{latest.name} windows-x86_64 size is not {exe.name}'s")
    if not str(win.get("signature", "")).strip():
        raise ReleaseError(f"{latest.name} windows-x86_64 has no signature")
    sig = exe.with_name(exe.name + ".sig")
    if sig.is_file() and win["signature"].strip() != sig.read_text().strip():
        raise ReleaseError(f"{latest.name} windows-x86_64 signature differs from {sig.name}")
    base = f"launcher/{channel}"
    plan = [(exe, f"{base}/{exe.name}")]
    if sig.is_file():
        plan.append((sig, f"{base}/{sig.name}"))
    plan.append((exe, f"{base}/{LAUNCHER_FIXED}"))
    plan.append((latest, f"{base}/latest.json"))
    return plan


def verify_launcher(host: str, exe: Path, latest: Path, channel: str, log=print) -> int:
    """After the upload: fetch each latest.json platform url (what the self-update downloads)
    and every planned file back from the host and compare sha256. Returns the file count."""
    plan = launcher_plan(exe, latest, channel, host)
    want = sha256_file(exe)
    for name, url in sorted(launcher_urls(json.loads(Path(latest).read_text(encoding="utf-8"))).items()):
        data = fetch(url, timeout=600)
        if data is None:
            raise ReleaseError(f"{Path(latest).name} {name} url {url} is missing (404): the self-update would fail")
        if sha256_bytes(data) != want:
            raise ReleaseError(f"{Path(latest).name} {name} url {url} does not serve {Path(exe).name} "
                               f"(a CDN cache, or another upload)")
        log(f"{name} url {url} serves {Path(exe).name}")
    for src, dst in plan:
        data = fetch(host_url(host, dst), timeout=600)
        if data is None:
            raise ReleaseError(f"{dst} is missing on {host}")
        if sha256_bytes(data) != sha256_file(src):
            raise ReleaseError(f"{dst} on {host} does not match {src.name} (a CDN cache, or another upload)")
    return len(plan)


def build_services(conf: dict) -> tuple[dict, dict]:
    """The `features` and `services` blocks of manifest.json, from release.conf."""
    host = conf_need(conf, "host")
    shop = _bool(conf.get("feature_shop", "false"), "release.conf feature_shop")
    report = conf.get("report_url") or host_url(host, "report")
    account = conf.get("account_api") or None
    for key in ("report_url", "account_api"):
        url = conf.get(key)
        if url and not url.startswith("https://"):
            raise ReleaseError(f"release.conf {key} must be https://, got {url}")
    return {"shop": shop}, {"account_api": account, "report_url": report}


# ============================================================ status.json (contract section 4)

TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def validate_status(obj) -> list[str]:
    errs: list[str] = []

    def ts(v, where, nullable=False):
        if v is None and nullable:
            return
        if not isinstance(v, str) or not TS_RE.match(v):
            errs.append(f"{where}: expected a UTC timestamp like 2026-09-24T12:00:00Z")

    def strlist(v, where):
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            errs.append(f"{where}: expected a list of strings")

    if not isinstance(obj, dict):
        return ["top level: expected an object"]
    extra = set(obj) - {"generated", "realms", "maintenance", "season"}
    if extra:
        errs.append(f"top level: unknown field(s) {', '.join(sorted(extra))}")
    ts(obj.get("generated"), "generated")
    realms = obj.get("realms")
    if not isinstance(realms, list):
        errs.append("realms: expected a list")
    else:
        for i, r in enumerate(realms):
            w = f"realms[{i}]"
            if not isinstance(r, dict):
                errs.append(f"{w}: expected an object")
                continue
            for k in ("name", "kind"):
                if not isinstance(r.get(k), str) or not r.get(k):
                    errs.append(f"{w}.{k}: expected a non-empty string")
            for k in ("open", "online"):
                if not isinstance(r.get(k), bool):
                    errs.append(f"{w}.{k}: expected true or false")
            p = r.get("players")
            if not isinstance(p, int) or isinstance(p, bool) or p < 0:
                errs.append(f"{w}.players: expected a non-negative integer")
    for key in ("maintenance", "season"):
        if key not in obj:
            errs.append(f"{key}: required (null when absent)")
    m = obj.get("maintenance")
    if m is not None:
        if not isinstance(m, dict):
            errs.append("maintenance: expected an object or null")
        else:
            strlist(m.get("realms"), "maintenance.realms")
            if not isinstance(m.get("message"), str):
                errs.append("maintenance.message: expected a string")
            ts(m.get("until"), "maintenance.until", nullable=True)
    s = obj.get("season")
    if s is not None:
        if not isinstance(s, dict):
            errs.append("season: expected an object or null")
        else:
            n = s.get("number")
            if not isinstance(n, int) or isinstance(n, bool) or n < 1:
                errs.append("season.number: expected a positive integer")
            strlist(s.get("realms"), "season.realms")
            ts(s.get("starts"), "season.starts")
            ts(s.get("ends"), "season.ends", nullable=True)
            d = s.get("details")
            if d is not None and not (isinstance(d, str) and re.match(r"^(news:[a-z0-9-]+|patchnotes:(\d+|latest))$", d)):
                errs.append("season.details: expected null, news:<id> or patchnotes:<n>")
    return errs


# ============================================================ verifying a published release

def blob_refs(obj) -> set[str]:
    """Every files/<sha256> reference in a manifest."""
    refs: set[str] = set()
    if isinstance(obj, dict):
        for v in obj.values():
            refs |= blob_refs(v)
    elif isinstance(obj, list):
        for v in obj:
            refs |= blob_refs(v)
    elif isinstance(obj, str):
        refs |= set(re.findall(r"files/[0-9a-f]{64}", obj))
    return refs


def verify_readable(host: str, manifest: dict) -> int:
    """Fetch each readable copy from the host and require its blob's sha256. Returns the count."""
    plan = readable_plan(manifest)
    for rel, sha in plan:
        data = fetch(host_url(host, rel), timeout=600)
        if data is None:
            raise ReleaseError(f"{rel} is missing on {host}")
        if sha256_bytes(data) != sha:
            raise ReleaseError(f"{rel} on {host} is not the bytes of files/{sha}")
    return len(plan)


def verify_published(host: str, channel: str, work: Path, expect: Path | None = None,
                     readable: bool = False) -> int:
    """Fetch <channel>/manifest.json back from the host and check every blob it names.

    Returns the number of blobs checked. `expect` is the staged file that should be live.
    `readable` also fetches each readable copy (readable_plan) and requires the
    sha256 of its blob.
    """
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    name = "manifest.json"
    doc = fetch(host_url(host, f"{channel}/{name}"))
    if doc is None:
        raise ReleaseError(f"{channel}/{name} is missing on {host}")
    (work / name).write_bytes(doc)
    if expect is not None and Path(expect).read_bytes() != doc:
        raise ReleaseError(f"published {channel}/{name} is not the file just built (a CDN cache, or another upload)")
    obj = json.loads(doc)
    refs = sorted(blob_refs(obj))
    for ref in refs:
        data = fetch(host_url(host, ref), timeout=600)
        if data is None:
            raise ReleaseError(f"{ref} is missing on {host}")
        if sha256_bytes(data) != ref[len("files/"):]:
            raise ReleaseError(f"{ref} on {host} does not match its hash")
    for c in obj["components"]:
        if c["url"].startswith("files/") and c.get("sha256") and c["url"] != f"files/{c['sha256']}":
            raise ReleaseError(f"component {c['id']}: url and sha256 disagree")
    if readable:
        verify_readable(host, obj)
    return len(refs)


# ============================================================ CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--conf", type=Path, default=None)
    ap.add_argument("--repo", type=Path, default=REPO)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("client")
    c.add_argument("--staging", type=Path, required=True)
    c.add_argument("--channel", default="stable", choices=CHANNELS)
    c.add_argument("--aio-client", type=Path)
    c.add_argument("--elvui-zip", type=Path)
    c.add_argument("--allow-dirty", action="store_true")
    c.add_argument("--no-live-check", action="store_true")
    c.add_argument("--client-rebuild", type=Path,
                   help="the client-rebuild CI artefact, unpacked: ships WowClient64.exe, XvidDecoder.dll and "
                        "the VC++ x64 runtime")

    f = sub.add_parser("feeds")
    f.add_argument("--out", type=Path, required=True)
    f.add_argument("--site", default=DEFAULT_SITE)
    f.add_argument("--content-dir", type=Path)
    f.add_argument("--allow-dirty", action="store_true")

    for name in ("launcher-plan", "verify-launcher"):
        lp = sub.add_parser(name)
        lp.add_argument("--exe", type=Path, required=True)
        lp.add_argument("--latest", type=Path, required=True)
        lp.add_argument("--channel", default="stable", choices=CHANNELS)

    r = sub.add_parser("republish")
    r.add_argument("--from", dest="src", type=Path, required=True)
    r.add_argument("--staging", type=Path, required=True)
    r.add_argument("--channel", default="stable", choices=CHANNELS)

    v = sub.add_parser("verify-published")
    v.add_argument("--channel", default="stable", choices=CHANNELS)
    v.add_argument("--work", type=Path, required=True)
    v.add_argument("--expect", type=Path)
    v.add_argument("--readable", action="store_true", help="also fetch back the readable copies")

    rp = sub.add_parser("readable-plan")
    rp.add_argument("--manifest", type=Path, required=True)

    vr = sub.add_parser("verify-readable")
    vr.add_argument("--manifest", type=Path, required=True)

    s = sub.add_parser("status-schema-check")
    s.add_argument("file", type=Path)

    sub.add_parser("releases-dir")  # the main checkout's client-patch/.releases

    g = sub.add_parser("conf-get")
    g.add_argument("key")

    a = ap.parse_args(argv)
    try:
        if a.cmd == "feeds":  # needs no release.conf
            fd = build_feeds(a.repo, a.out, site=a.site, content_dir=a.content_dir, allow_dirty=a.allow_dirty)
            if fd["dropped_links"]:
                print(f"feeds: left out built-in app: link(s) {', '.join(fd['dropped_links'])}")
            print(f"feeds: {len(fd['news']['news'])} news, {len(fd['slides']['slides'])} slides, "
                  f"{len(fd['links']['links'])} links, {len(fd['patchnotes']['patchnotes'])} patch notes "
                  f"-> {a.out / API_PATH}")
            return 0
        if a.cmd == "releases-dir":
            print(releases_dir(a.repo))
            return 0
        if a.cmd == "readable-plan":  # tab-separated `<path under the host>\t<blob sha256>`
            for rel, sha in readable_plan(json.loads(a.manifest.read_text(encoding="utf-8"))):
                print(f"{rel}\t{sha}")
            return 0
        if a.cmd == "verify-readable":  # before manifest.json goes up
            host = conf_need(load_conf(a.conf), "host")
            n = verify_readable(host, json.loads(a.manifest.read_text(encoding="utf-8")))
            print(f"verified: {n} readable copy(ies) on {host} match their blobs")
            return 0
        if a.cmd == "status-schema-check":
            try:
                obj = json.loads(a.file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                raise ReleaseError(f"{a.file}: {e}") from None
            errs = validate_status(obj)
            for e in errs:
                print(f"{a.file.name}: {e}", file=sys.stderr)
            if errs:
                return 1
            print(f"{a.file.name}: status.json schema OK")
            return 0
        conf = load_conf(a.conf)
        if a.cmd == "conf-get":
            print(conf.get(a.key, ""))
        elif a.cmd == "launcher-plan":  # tab-separated `<local file>\t<path under the target>`, upload order
            for src, dst in launcher_plan(a.exe, a.latest, a.channel, conf_need(conf, "host")):
                print(f"{src}\t{dst}")
        elif a.cmd == "client":
            m = build_client(a.repo, conf, a.staging, a.channel, aio_client=a.aio_client, elvui_zip=a.elvui_zip,
                             allow_dirty=a.allow_dirty, live_check=not a.no_live_check, log=print,
                             client_rebuild=a.client_rebuild)
            print(f"manifest: {a.channel} client_patch {m['client_patch']}, {len(m['components'])} components "
                  f"-> {a.staging / a.channel / 'manifest.json'}")
        elif a.cmd == "republish":
            m = republish(a.src, a.staging, a.channel, conf, log=print)
            print(f"republish: {a.channel} client_patch {m['client_patch']} released {m['released']}")
        elif a.cmd == "verify-published":
            n = verify_published(conf_need(conf, "host"), a.channel, a.work, a.expect, a.readable)
            extra = ""
            if a.readable:
                extra = f", {len(readable_plan(json.loads((a.work / 'manifest.json').read_text())))} readable copy(ies) match their blobs"
            print(f"verified: {a.channel}/manifest.json is the file just built, {n} blob(s) match their hashes{extra}")
        elif a.cmd == "verify-launcher":
            host = conf_need(conf, "host")
            n = verify_launcher(host, a.exe, a.latest, a.channel)
            print(f"verified: {n} launcher file(s) on {host}/launcher/{a.channel}/ match their sha256")
    except ReleaseError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
