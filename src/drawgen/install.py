"""Fetch a pinned, checksum-verified draw.io Desktop into drawgen's cache.

draw.io Desktop (Apache-2.0, github.com/jgraph/drawio-desktop) is the only
exact renderer for draw.io diagrams. Shipping it inside the package would mean
a 150 MB Electron app per platform in every install, so instead it is
downloaded once, on request, as the vendor's own portable build, and verified
against the SHA-256 the release publishes. find_drawio() looks here after PATH
and the usual install locations.

Bumping the version: take the names and `digest` values from
`gh api repos/jgraph/drawio-desktop/releases/tags/v<version>`.
"""
from __future__ import annotations

import hashlib
import os
import platform
import shutil
import stat
import sys
import urllib.request
import zipfile

VERSION = "31.7.0"
BASE = f"https://github.com/jgraph/drawio-desktop/releases/download/v{VERSION}/"

# (system, machine) -> (asset, sha256, path of the executable inside the cache dir)
ASSETS: dict[tuple[str, str], tuple[str, str, str]] = {
    ("Windows", "x64"): (f"draw.io-{VERSION}-windows.zip",
                         "72074548c40970825d8d18085d2537f4b64d8270c4aa24a527be2877e8053b54",
                         "draw.io.exe"),
    ("Darwin", "x64"): (f"draw.io-x64-{VERSION}.zip",
                        "be4efa8757f83c748f7123bc045b33fe374883fa0f935403d943d74fd742ab26",
                        "draw.io.app/Contents/MacOS/draw.io"),
    ("Darwin", "arm64"): (f"draw.io-arm64-{VERSION}.zip",
                          "49d9e72d3649c8d355652b8596b5015622e69c4f06dc11a513da10cbaa7864e4",
                          "draw.io.app/Contents/MacOS/draw.io"),
    ("Linux", "x64"): (f"drawio-x86_64-{VERSION}.AppImage",
                       "6a304fed85da0d3db0ba4b8dc5dad8779ff02318c56e45bcc2dd64f4ddf91645",
                       f"drawio-x86_64-{VERSION}.AppImage"),
    ("Linux", "arm64"): (f"drawio-arm64-{VERSION}.AppImage",
                         "dec2d0663db45d1ae736bbbc0569ff00e961a38da7e58564839f9ac830fedf90",
                         f"drawio-arm64-{VERSION}.AppImage"),
}


def cache_root() -> str:
    env = os.environ.get("DRAWGEN_CACHE")
    if env:
        return env
    if platform.system() == "Windows":
        return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "drawgen")
    if platform.system() == "Darwin":
        return os.path.expanduser("~/Library/Caches/drawgen")
    return os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "drawgen")


def _machine() -> str:
    m = platform.machine().lower()
    return "arm64" if m in ("arm64", "aarch64") else "x64"


def _asset():
    key = (platform.system(), _machine())
    if key not in ASSETS:
        raise RuntimeError(f"no pinned draw.io build for {key[0]} {key[1]}; install draw.io yourself "
                           "and set DRAWIO_BIN")
    return ASSETS[key]


def install_dir() -> str:
    return os.path.join(cache_root(), f"drawio-{VERSION}")


def cached_executable() -> str | None:
    try:
        _, _, rel = _asset()
    except RuntimeError:
        return None
    path = os.path.join(install_dir(), rel)
    return path if os.path.exists(path) else None


def install(progress=lambda msg: print(msg, file=sys.stderr)) -> str:
    """Download, verify and unpack draw.io; return the executable. Idempotent."""
    existing = cached_executable()
    if existing:
        progress(f"draw.io {VERSION} is already installed: {existing}")
        return existing
    asset, sha, rel = _asset()
    dest = install_dir()
    os.makedirs(cache_root(), exist_ok=True)
    partial = os.path.join(cache_root(), asset + ".part")
    progress(f"downloading {BASE + asset}")
    digest = hashlib.sha256()
    with urllib.request.urlopen(BASE + asset, timeout=60) as resp, open(partial, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done, last = 0, -10
        while chunk := resp.read(1 << 20):
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            pct = int(done * 100 / total) if total else 0
            if pct >= last + 10:
                progress(f"  {pct}% of {total // (1 << 20)} MB")
                last = pct
    if digest.hexdigest() != sha:
        os.remove(partial)
        raise RuntimeError(f"checksum mismatch for {asset}: expected {sha}, got {digest.hexdigest()}. "
                           "Nothing was installed.")
    staging = dest + ".staging"
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging)
    if asset.endswith(".zip"):
        with zipfile.ZipFile(partial) as z:
            z.extractall(staging)
            # zipfile drops the executable bit; restore it where the zip recorded one.
            for info in z.infolist():
                mode = info.external_attr >> 16
                if mode & 0o111:
                    os.chmod(os.path.join(staging, info.filename), mode & 0o777)
        os.remove(partial)
    else:
        target = os.path.join(staging, rel)
        os.replace(partial, target)
        os.chmod(target, os.stat(target).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    exe = os.path.join(staging, rel)
    if not os.path.exists(exe):
        # Some zips wrap everything in one folder; find the executable rather than guess.
        name = os.path.basename(rel)
        for root, _, files in os.walk(staging):
            if name in files:
                found = os.path.relpath(os.path.join(root, name), staging)
                raise RuntimeError(f"unexpected layout: executable at {found}, expected {rel}; "
                                   "update ASSETS in install.py")
        raise RuntimeError(f"{rel} not found in {asset}")
    shutil.rmtree(dest, ignore_errors=True)
    os.replace(staging, dest)
    final = os.path.join(dest, rel)
    progress(f"installed draw.io {VERSION}: {final}")
    return final


def uninstall() -> bool:
    if os.path.isdir(install_dir()):
        shutil.rmtree(install_dir())
        return True
    return False
