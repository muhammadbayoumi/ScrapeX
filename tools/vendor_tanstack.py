"""Vendor TanStack Table and TanStack Virtual into both shipped surfaces.

The grid renders through TanStack Table (state and row models) and TanStack
Virtual (which rows are on screen). Both ship as ES modules only, and neither
can be loaded by a browser exactly as npm publishes it:

  * table-core imports its one dependency by bare name, ``"@tanstack/store"``,
    and a browser resolves a bare name only through an import map or a bundler.
    An external import map is not supported by the HTML spec and an inline one
    is an inline script, which the extension's MV3 policy refuses.
  * table-core and virtual-core read ``process.env.NODE_ENV`` with no guard,
    so in a page, where ``process`` does not exist, they throw on the first
    table they build.

So this tool takes the published tarballs, checks each against the integrity
npm records for it, keeps only the modules the grid's entry points reach, and
makes exactly three rewrites, all in the vendored text and none in behaviour:

  1. ``"@tanstack/store"`` becomes the relative path of the vendored store.
  2. ``process.env.NODE_ENV`` becomes ``"production"``: what a bundler does.
  3. A trailing ``//# sourceMappingURL=`` line goes, because the maps are not
     vendored and a dangling one is a failed request in every devtools session.

Anything else that would not load in a page (another bare specifier, a
dynamic ``import()``, a module the closure names that the tarball lacks) stops
the tool instead of being written. So does a module path that climbs out of its
package: nothing is written outside the two copies.

Usage:
    python tools/vendor_tanstack.py
    python tools/vendor_tanstack.py --tarball table-core=path/to/table-core.tgz ...

Without ``--tarball`` each package is downloaded from the registry URL pinned
below. Either way the bytes must match the pinned integrity, so a local
tarball is a convenience, never a way around the check.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import posixpath
import re
import shutil
import tarfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Both copies, as the engine's templates and the extension's pages load them.
DESTINATIONS = (
    ROOT / "scrapex" / "webui" / "static" / "vendor" / "tanstack",
    ROOT / "extension" / "vendor" / "tanstack",
)


@dataclass(frozen=True)
class Package:
    name: str          # the directory it is vendored under
    npm: str           # the npm package name
    version: str
    integrity: str     # npm's dist.integrity for that exact tarball
    dist: str          # the directory inside the tarball that holds the modules
    entries: tuple[str, ...]  # the modules the grid imports, relative to dist

    @property
    def tarball(self) -> str:
        """The registry URL, read from `npm` and `version`, so a new pin is the
        version and the integrity and nothing else."""
        return (f"https://registry.npmjs.org/{self.npm}/-/"
                f"{self.npm.rpartition('/')[2]}-{self.version}.tgz")


PACKAGES = (
    Package(
        name="table-core", npm="@tanstack/table-core", version="9.2.5",
        integrity="sha512-HCMUpaEBEBS9AkV44sdTDmNgFrAA6H4NAnUgwuoWN7IkPgwXWlf3bfZ0moyxLwZqQXdpNQZdEl7LMW4rqm9zQQ==",
        dist="package/dist",
        entries=("index.js", "store-reactivity-bindings.js"),
    ),
    Package(
        name="store", npm="@tanstack/store", version="0.11.2",
        integrity="sha512-sJ4mjol8uQsHV0gOJzzjwXfh2Fwm+Sz0+8deqiTm4jGbMdjzNSW+xZCFm0kUa870uhd8yi+DpKnZb5Kc4apa0Q==",
        dist="package/dist",
        entries=("index.js",),
    ),
    Package(
        name="virtual-core", npm="@tanstack/virtual-core", version="3.17.11",
        integrity="sha512-+ILjvtHup6Y2hzQ6YzwMgX1Q+oQpxEGOXCEsCNaPoIP0VxMbizIBTmYTDtkerkIQS8/CbP1BRuyt8V/8BCsy1g==",
        dist="package/dist/esm",
        entries=("index.js",),
    ),
)

#: The one bare specifier the vendored code may name, and which package answers it.
BARE = {"@tanstack/store": "store"}

# Static `import ... from "x"`, `export ... from "x"` and side-effect `import "x"`.
SPECIFIER = re.compile(r'''(?:\bfrom\s*|\bimport\s*)(["'])([^"']+)\1''')
DYNAMIC_IMPORT = re.compile(r"\bimport\s*\(")
NODE_ENV = "process.env.NODE_ENV"
SOURCE_MAP = re.compile(r"\n?//# sourceMappingURL=[^\n]*\s*$")


class VendorError(Exception):
    """Something in a tarball would not load in a page, or is not what npm published."""


def integrity_of(data: bytes) -> str:
    """npm's `sha512-<base64>` form, for comparing against `dist.integrity`."""
    return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()


def verify(package: Package, data: bytes) -> None:
    got = integrity_of(data)
    if got != package.integrity:
        raise VendorError(
            f"{package.npm}@{package.version}: the tarball's integrity is {got}, "
            f"npm records {package.integrity}. Refusing to vendor bytes npm did not publish.")


def read_tarball(package: Package, data: bytes) -> dict[str, str]:
    """Every .js module under the package's dist, keyed by its path relative to dist."""
    modules: dict[str, str] = {}
    prefix = package.dist.rstrip("/") + "/"
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile() or not member.name.startswith(prefix):
                continue
            relative = member.name[len(prefix):]
            if not relative.endswith(".js"):
                continue
            handle = archive.extractfile(member)
            if handle is None:
                raise VendorError(f"{package.npm}: {member.name} could not be read")
            modules[relative] = handle.read().decode("utf-8")
    return modules


def read_licence(data: bytes) -> str:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        member = archive.getmember("package/LICENSE")
        handle = archive.extractfile(member)
        if handle is None:
            raise VendorError("the tarball has no readable package/LICENSE")
        return handle.read().decode("utf-8")


BLOCK_COMMENT = re.compile(r"/\*[\s\S]*?\*/")
LINE_COMMENT = re.compile(r"^\s*//[^\n]*$", re.MULTILINE)


def code_only(source: str) -> str:
    """The source without its comments, for reading what it IMPORTS.

    The dist's JSDoc carries usage examples ("import ... from
    '@tanstack/table-core'"), and those are prose, not imports.
    """
    return LINE_COMMENT.sub("", BLOCK_COMMENT.sub("", source))


def specifiers(source: str) -> list[str]:
    return [match.group(2) for match in SPECIFIER.finditer(code_only(source))]


def closure(package: Package, modules: dict[str, str]) -> list[str]:
    """The modules the entries reach, in a stable order, and nothing else."""
    seen: list[str] = []
    pending = list(package.entries)
    while pending:
        path = pending.pop(0)
        if path in seen:
            continue
        # A module is written at `<package>/<path>`, so a path that climbs out of
        # dist lands outside its package, and past the destination if it climbs on.
        normal = posixpath.normpath(path)
        if normal == ".." or normal.startswith(("../", "/")):
            raise VendorError(f"{package.npm}: {path} lies outside {package.dist}, so it "
                              "would be written outside the package")
        if path not in modules:
            raise VendorError(f"{package.npm}: {path} is imported but not in the tarball")
        seen.append(path)
        source = modules[path]
        if DYNAMIC_IMPORT.search(code_only(source)):
            raise VendorError(
                f"{package.npm}: {path} uses a dynamic import(), which this tool cannot "
                "resolve ahead of time")
        for spec in specifiers(source):
            if spec.startswith("."):
                pending.append(posixpath.normpath(posixpath.join(posixpath.dirname(path), spec)))
            elif spec not in BARE:
                raise VendorError(
                    f"{package.npm}: {path} imports the bare name {spec!r}, which no "
                    "vendored package answers")
    return sorted(seen)


def rewrite(package: Package, path: str, source: str) -> str:
    """The three documented rewrites, and only those."""
    def relative_to(target_package: str) -> str:
        here = posixpath.dirname(posixpath.join(package.name, path))
        target = posixpath.join(target_package, "index.js")
        rel = posixpath.relpath(target, here or ".")
        return rel if rel.startswith(".") else "./" + rel

    def swap(match: re.Match) -> str:
        quote, spec = match.group(1), match.group(2)
        if spec in BARE:
            return match.group(0).replace(quote + spec + quote, quote + relative_to(BARE[spec]) + quote)
        return match.group(0)

    source = SPECIFIER.sub(swap, source)
    source = source.replace(NODE_ENV, '"production"')
    return SOURCE_MAP.sub("\n", source)


def build(tarballs: dict[str, bytes]) -> dict[str, str]:
    """Every file to write, keyed by its path under a destination, from verified tarballs."""
    files: dict[str, str] = {}
    for package in PACKAGES:
        data = tarballs[package.name]
        verify(package, data)
        modules = read_tarball(package, data)
        for path in closure(package, modules):
            out = rewrite(package, path, modules[path])
            leftover = [s for s in specifiers(out) if not s.startswith(".")]
            if leftover or "process.env" in code_only(out):
                raise VendorError(f"{package.npm}: {path} still names {leftover or 'process.env'}")
            files[f"{package.name}/{path}"] = out
        files[f"{package.name}/LICENSE"] = read_licence(data)
    return files


def write(files: dict[str, str], destinations: tuple[Path, ...]) -> None:
    # Every target is checked before anything is removed, so a refusal leaves both
    # copies as they were.
    for destination in destinations:
        root = destination.resolve()
        outside = [relative for relative in files
                   if root not in (destination / relative).resolve().parents]
        if outside:
            raise VendorError(f"{', '.join(outside)} would be written outside "
                              f"{destination}; nothing was written")
    for destination in destinations:
        if destination.exists():
            shutil.rmtree(destination)
        for relative, text in files.items():
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            # newline="\n": the repository stores LF, and the two copies must be
            # the same bytes on every machine that runs this.
            target.write_text(text, encoding="utf-8", newline="\n")


def download(package: Package) -> bytes:
    with urllib.request.urlopen(package.tarball, timeout=60) as response:
        return response.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "--tarball", action="append", default=[], metavar="NAME=PATH",
        help="use a local tarball for a package (still checked against its pinned integrity)")
    args = parser.parse_args(argv)
    local: dict[str, Path] = {}
    for item in args.tarball:
        name, _, path = item.partition("=")
        if name not in {p.name for p in PACKAGES} or not path:
            parser.error(f"--tarball wants NAME=PATH with NAME one of "
                         f"{', '.join(p.name for p in PACKAGES)}; got {item!r}")
        local[name] = Path(path)
    tarballs = {
        p.name: local[p.name].read_bytes() if p.name in local else download(p)
        for p in PACKAGES
    }
    try:
        files = build(tarballs)
        write(files, DESTINATIONS)
    except VendorError as error:
        print(f"refused: {error}")
        return 1
    for destination in DESTINATIONS:
        print(f"wrote {len(files)} files to {destination.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
