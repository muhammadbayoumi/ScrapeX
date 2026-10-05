"""tools/vendor_tanstack.py: what it refuses, and the three rewrites it makes.

The tool runs against npm's tarballs, and a test cannot reach npm. So each case
builds a small tarball of its own, pins that tarball's own integrity, and hands
it to the tool in place of the real packages: the rules under test are the
tool's, whatever the bytes.
"""
from __future__ import annotations

import io
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import vendor_tanstack as tool  # noqa: E402

# It writes the extension's vendored modules, and it holds the vendor README to the
# versions it pins: a change to either must run it.
pytestmark = [pytest.mark.extension, pytest.mark.docs]

MIT = "MIT License\n\nCopyright (c) 2021 Tanner Linsley\n"


def _tarball(files: dict[str, str], licence: str = MIT) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, text in {**files, "package/LICENSE": licence}.items():
            data = text.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _package(name: str, data: bytes, *, entries=("index.js",), dist="package/dist"):
    return tool.Package(name=name, npm=f"@test/{name}", version="1.0.0",
                        tarball=f"https://registry.invalid/{name}.tgz",
                        integrity=tool.integrity_of(data), dist=dist, entries=entries)


@pytest.fixture
def packages(monkeypatch):
    """Two packages shaped like the real pair: a core that imports the store by name."""
    store = _tarball({
        "package/dist/index.js": 'import { atom } from "./atom.js";\nexport { atom };\n',
        "package/dist/atom.js": "export const atom = 1;\n//# sourceMappingURL=atom.js.map\n",
    })
    core = _tarball({
        "package/dist/index.js": (
            '/**\n * import { constructTable } from "@tanstack/table-core"\n */\n'
            'import { build } from "./core/build.js";\nexport { build };\n'),
        "package/dist/core/build.js": (
            'import { atom } from "@tanstack/store";\n'
            'export function build() {\n'
            '  if (process.env.NODE_ENV === "development") console.warn("dev");\n'
            '  return atom;\n}\n'),
        "package/dist/unused.js": "export const nobody = 'imports me';\n",
    })
    chosen = (_package("table-core", core), _package("store", store))
    monkeypatch.setattr(tool, "PACKAGES", chosen)
    return {"table-core": core, "store": store}


def test_it_keeps_only_what_the_entries_reach_and_makes_the_three_rewrites(packages):
    files = tool.build(packages)

    assert sorted(files) == [
        "store/LICENSE", "store/atom.js", "store/index.js",
        "table-core/LICENSE", "table-core/core/build.js", "table-core/index.js",
    ], "unused.js is reached by no entry and must not be vendored"
    build = files["table-core/core/build.js"]
    assert 'from "../../store/index.js"' in build, build
    assert '"@tanstack/store"' not in build
    assert 'if ("production" === "development")' in build
    assert "process" not in build
    assert "sourceMappingURL" not in files["store/atom.js"]
    # The JSDoc example names a bare package and is prose, so it is left as written.
    assert '"@tanstack/table-core"' in files["table-core/index.js"]
    assert files["store/LICENSE"] == MIT


def test_a_tarball_npm_did_not_publish_is_refused(packages):
    packages["store"] = packages["store"] + b"tampered"

    with pytest.raises(tool.VendorError, match="did not publish"):
        tool.build(packages)


def test_an_import_no_vendored_package_answers_is_refused(packages, monkeypatch):
    core = _tarball({"package/dist/index.js": 'import lodash from "lodash";\n'})
    monkeypatch.setattr(tool, "PACKAGES", (_package("table-core", core),
                                           tool.PACKAGES[1]))
    packages["table-core"] = core

    with pytest.raises(tool.VendorError, match="'lodash'"):
        tool.build(packages)


def test_a_dynamic_import_is_refused(packages, monkeypatch):
    core = _tarball({"package/dist/index.js": 'export const later = () => import("./x.js");\n'})
    monkeypatch.setattr(tool, "PACKAGES", (_package("table-core", core),
                                           tool.PACKAGES[1]))
    packages["table-core"] = core

    with pytest.raises(tool.VendorError, match="dynamic import"):
        tool.build(packages)


def test_a_module_the_closure_names_and_the_tarball_lacks_is_refused(packages, monkeypatch):
    core = _tarball({"package/dist/index.js": 'import { x } from "./gone.js";\n'})
    monkeypatch.setattr(tool, "PACKAGES", (_package("table-core", core),
                                           tool.PACKAGES[1]))
    packages["table-core"] = core

    with pytest.raises(tool.VendorError, match=r"gone\.js is imported but not in the tarball"):
        tool.build(packages)


def test_it_writes_both_copies_byte_for_byte_with_lf(packages, tmp_path):
    files = tool.build(packages)
    one, two = tmp_path / "engine" / "tanstack", tmp_path / "extension" / "tanstack"
    # A stale file from an earlier version must not survive a re-vendor.
    (one / "table-core").mkdir(parents=True)
    (one / "table-core" / "stale.js").write_text("old", encoding="utf-8")

    tool.write(files, (one, two))

    for root in (one, two):
        written = {p.relative_to(root).as_posix(): p.read_bytes()
                   for p in root.rglob("*") if p.is_file()}
        assert sorted(written) == sorted(files)
        assert all(b"\r\n" not in data for data in written.values())
    assert not (one / "table-core" / "stale.js").exists()


def test_main_refuses_and_writes_nothing_when_a_rule_is_broken(packages, tmp_path,
                                                              monkeypatch, capsys):
    packages["store"] = packages["store"] + b"tampered"
    paths = {}
    for name, data in packages.items():
        paths[name] = tmp_path / f"{name}.tgz"
        paths[name].write_bytes(data)
    destination = tmp_path / "out"
    monkeypatch.setattr(tool, "DESTINATIONS", (destination,))

    code = tool.main([f"--tarball={name}={path}" for name, path in paths.items()])

    assert code == 1
    assert "refused:" in capsys.readouterr().out
    assert not destination.exists()


def test_main_rejects_a_tarball_for_a_package_it_does_not_vendor(tmp_path):
    with pytest.raises(SystemExit) as stopped:
        tool.main([f"--tarball=lodash={tmp_path / 'x.tgz'}"])
    assert stopped.value.code == 2


def test_the_pinned_packages_are_the_ones_the_readme_records():
    """The README states the versions and integrities a reviewer checks against;
    the tool pins them. Two places, one fact each: they must agree."""
    readme = (ROOT / "scrapex" / "webui" / "static" / "vendor" / "README.md").read_text(
        encoding="utf-8")
    real = list(tool.PACKAGES)
    assert {p.npm for p in real} == {"@tanstack/table-core", "@tanstack/store",
                                     "@tanstack/virtual-core"}
    for package in real:
        assert f"`{package.npm}` | {package.version} |" in readme, package.npm
        assert f"`{package.integrity}`" in readme, package.npm
