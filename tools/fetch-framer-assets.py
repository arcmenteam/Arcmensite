#!/usr/bin/env python3
"""Archive every Framer-hosted asset referenced by the mirrored pages.

Usage:
    python tools/fetch-framer-assets.py [outdir]      # default: assets-source

Scans the mirrored HTML pages in the repo root and downloads the ORIGINAL of
every framerusercontent.com asset they reference. The original is the base URL
with no ?scale-down-to/width/height query string: that is the full-resolution
file as uploaded. Framer's per-breakpoint variants are deliberately not
archived, since they are re-derivable from the original at build time.

Safe to re-run. Files that already exist and pass verification are skipped, so
an interrupted run resumes where it stopped.
"""

import collections
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
REFERER = "https://www.arcmen.in/"
URL_RE = re.compile(r"https://framerusercontent\.com/[A-Za-z0-9_\-./]+"
                    r"(?:\?[A-Za-z0-9_\-=&%.]*)?")

IMAGE_EXT = {"png", "jpg", "jpeg", "webp", "avif", "gif", "svg"}
VIDEO_EXT = {"mp4", "webm", "mov"}
FONT_EXT = {"woff", "woff2", "ttf", "otf"}

MAGIC = {
    "png": b"\x89PNG\r\n\x1a\n",
    "jpg": b"\xff\xd8\xff",
    "jpeg": b"\xff\xd8\xff",
    "gif": b"GIF8",
    "woff2": b"wOF2",
    "woff": b"wOFF",
}


def pages_in(root):
    """The mirrored pages, home first, then sections, albums and posts."""
    found = []
    for name in sorted(os.listdir(root)):
        if name.endswith(".html"):
            found.append(name)
    for sub in ("albums", "blog"):
        d = os.path.join(root, sub)
        if os.path.isdir(d):
            found += [f"{sub}/{n}" for n in sorted(os.listdir(d))
                      if n.endswith(".html")]
    found.sort(key=lambda p: (p != "index.html", p))
    return found


def kind_of(url):
    ext = url.rsplit(".", 1)[-1].lower()
    if ext in IMAGE_EXT:
        return "images"
    if ext in VIDEO_EXT:
        return "video"
    if ext in FONT_EXT:
        return "fonts"
    return None


def collect(root):
    """Map every referenced asset to the pages that use it."""
    assets = collections.defaultdict(
        lambda: {"pages": set(), "declared_w": 0, "declared_h": 0, "variants": 0})
    for page in pages_in(root):
        html = io.open(os.path.join(root, page), encoding="utf-8",
                       errors="replace").read()
        for raw in URL_RE.findall(html):
            url = raw.replace("&amp;", "&")
            base, _, query = url.partition("?")
            if base.endswith(".mjs") or kind_of(base) is None:
                continue  # runtime modules and searchIndex JSON are not archived
            entry = assets[base]
            entry["pages"].add(page)
            if query:
                entry["variants"] += 1
                for param, field in (("width", "declared_w"),
                                     ("height", "declared_h")):
                    m = re.search(param + r"=(\d+)", query)
                    if m:
                        entry[field] = max(entry[field], int(m.group(1)))
    return assets


def verify(path, url):
    """Return (ok, detail). Images are opened properly; others check magic.

    Extensions are not trusted: a handful of Framer uploads are named .jpg but
    hold PNG data. For images the real test is whether PIL can decode the whole
    file, so the magic table is only consulted for fonts and video.
    """
    ext = url.rsplit(".", 1)[-1].lower()
    size = os.path.getsize(path)
    if size == 0:
        return False, "empty file"
    head = io.open(path, "rb").read(12)
    if ext in IMAGE_EXT and ext != "svg":
        try:
            from PIL import Image
            with Image.open(path) as im:
                im.load()
                return True, f"{im.width}x{im.height} {im.format}"
        except Exception as exc:  # truncated or corrupt download
            return False, f"{type(exc).__name__}: {str(exc)[:60]}"
    if ext in MAGIC and not head.startswith(MAGIC[ext]):
        return False, f"bad magic {head[:4].hex()}"
    if ext in VIDEO_EXT and b"ftyp" not in head:
        return False, f"bad magic {head[:8].hex()}"
    return True, ""


def fetch(url, dest, tries=4):
    """Download one asset with retries. Returns (status, bytes, detail)."""
    if os.path.exists(dest):
        ok, detail = verify(dest, url)
        if ok:
            return "skipped", os.path.getsize(dest), detail
        os.remove(dest)  # partial from an interrupted run

    tmp = dest + ".part"
    last = ""
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Referer": REFERER,
                              "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=90) as resp:
                declared = resp.headers.get("Content-Length")
                data = resp.read()
            if declared and len(data) != int(declared):
                raise IOError(f"short read {len(data)}/{declared}")
            with io.open(tmp, "wb") as fh:
                fh.write(data)
            ok, detail = verify(tmp, url)
            if not ok:
                raise IOError(detail)
            os.replace(tmp, dest)
            return "downloaded", len(data), detail
        except Exception as exc:
            last = f"{type(exc).__name__}: {str(exc)[:70]}"
            if os.path.exists(tmp):
                os.remove(tmp)
            if attempt < tries - 1:
                time.sleep(1.5 * (attempt + 1))
    return "failed", 0, last


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    outdir = os.path.join(root, sys.argv[1] if len(sys.argv) > 1
                          else "assets-source")

    assets = collect(root)
    for folder in ("images", "video", "fonts"):
        os.makedirs(os.path.join(outdir, folder), exist_ok=True)

    jobs = []
    for url, meta in sorted(assets.items()):
        folder = kind_of(url)
        name = url.rsplit("/", 1)[-1]
        jobs.append((url, folder, name, os.path.join(outdir, folder, name), meta))

    counts = collections.Counter(j[1] for j in jobs)
    print(f"{len(jobs)} unique assets referenced by {len(pages_in(root))} pages: "
          + ", ".join(f"{n} {k}" for k, n in sorted(counts.items())))
    print(f"archiving originals into {os.path.relpath(outdir, root)}/\n")

    results = {}

    def run(job):
        url, folder, name, dest, _ = job
        status, size, detail = fetch(url, dest)
        results[url] = (status, size, detail)
        flag = {"downloaded": "+", "skipped": "=", "failed": "!"}[status]
        print(f" {flag} {human(size):>9}  {name[:46]:46} {detail[:28]}",
              flush=True)

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(run, jobs))

    manifest = []
    for url, folder, name, dest, meta in jobs:
        status, size, detail = results[url]
        real_w = real_h = 0
        if "x" in detail.split(" ")[0] and detail[0].isdigit():
            dims = detail.split(" ")[0].split("x")
            real_w, real_h = int(dims[0]), int(dims[1])
        manifest.append({
            "url": url,
            "local": f"{folder}/{name}",
            "kind": folder,
            "bytes": size,
            "width": real_w,
            "height": real_h,
            "framer_max_variant": [meta["declared_w"], meta["declared_h"]],
            "status": status,
            "pages": sorted(meta["pages"]),
        })

    manifest.sort(key=lambda m: (m["kind"], m["local"]))
    with io.open(os.path.join(outdir, "manifest.json"), "w",
                 encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)
        fh.write("\n")

    # Which images belong to which page, so the rebuild knows what to group.
    by_page = collections.defaultdict(list)
    for m in manifest:
        for page in m["pages"]:
            by_page[page].append(m["local"])
    with io.open(os.path.join(outdir, "by-page.json"), "w",
                 encoding="utf-8") as fh:
        json.dump({k: sorted(v) for k, v in sorted(by_page.items())}, fh, indent=1)
        fh.write("\n")

    tally = collections.Counter(m["status"] for m in manifest)
    total = sum(m["bytes"] for m in manifest)
    print("\n" + "-" * 62)
    print(f"downloaded {tally['downloaded']}   already present {tally['skipped']}"
          f"   failed {tally['failed']}")
    for folder in ("images", "video", "fonts"):
        part = [m for m in manifest if m["kind"] == folder]
        if part:
            print(f"  {folder:7} {len(part):4} files  {human(sum(m['bytes'] for m in part)):>10}")
    print(f"  {'TOTAL':7} {len(manifest):4} files  {human(total):>10}")

    failures = [m for m in manifest if m["status"] == "failed"]
    if failures:
        print("\nfailed (re-run to retry):")
        for m in failures:
            print(f"  {m['local']}  {results[m['url']][2]}")

    shrunk = [m for m in manifest
              if m["kind"] == "images" and m["width"]
              and m["framer_max_variant"][0] > m["width"]]
    if shrunk:
        print(f"\nnote: {len(shrunk)} images are referenced at a larger size than "
              "the original actually is")
    print("\nmanifest.json + by-page.json written alongside the files")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
