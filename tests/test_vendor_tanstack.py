"""tools/vendor_tanstack.py: what it refuses, and the three rewrites it makes.

The tool runs against npm's tarballs, and a test cannot reach npm. So each case
builds a small tarball of its own, pins that tarball's own integrity, and hands
it to the tool in place of the real packages: the rules under test are the
tool's, whatever the bytes.
"""
from __future__ import annotations

import dataclasses
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
                        integrity=tool.integrity_of(data), dist=dist, entries=entries)


def _tree(root: Path) -> dict[str, bytes]:
    """Every file under `root`, with its bytes: what a run left on disk."""
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*")) if path.is_file()}


def _arguments(tarballs: dict[str, bytes], directory: Path) -> list[str]:
    """main()'s `--tarball` arguments for these bytes, each written under `directory`."""
    arguments = []
    for name, data in tarballs.items():
        path = directory / f"{name}.tgz"
        path.write_bytes(data)
        arguments.append(f"--tarball={name}={path}")
    return arguments


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
            # Not ASCII, as seven of the real modules are not: what a copy's bytes
            # are then depends on the encoding it was written in.
            "// The store is read by name — the one bare import.\n"
            'import { atom } from "@tanstack/store";\n'
            'export function build() {\n'
            '  if (process.env.NODE_ENV === "development") console.warn("dev");\n'
            '  return atom;\n}\n'),
        "package/dist/unused.js": "export const nobody = 'imports me';\n",
    })
    chosen = (_package("table-core", core), _package("store", store))
    monkeypatch.setattr(tool, "PACKAGES", chosen)
    return {"table-core": core, "store": store}


@pytest.fixture
def destinations(tmp_path, monkeypatch):
    """main()'s two copies, moved under tmp_path and holding a file from the version
    before, and npm out of reach. EVERY main() TEST TAKES IT: main() writes
    DESTINATIONS, which are the two real vendored trees, and downloads every
    package it is not handed a tarball for."""
    roots = (tmp_path / "engine" / "tanstack", tmp_path / "extension" / "tanstack")
    for root in roots:
        (root / "table-core").mkdir(parents=True)
        (root / "table-core" / "stale.js").write_text("the version before\n", encoding="utf-8")
    monkeypatch.setattr(tool, "ROOT", tmp_path)
    monkeypatch.setattr(tool, "DESTINATIONS", roots)

    def offline(package):
        pytest.fail(f"main() went to npm for {package.npm}")

    monkeypatch.setattr(tool, "download", offline)
    return roots


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


@pytest.mark.parametrize("read", ["process.env.DEBUG", 'process.env["NODE_ENV"]'])
def test_a_process_env_read_the_rewrite_does_not_replace_is_refused(packages, monkeypatch,
                                                                     read):
    """The rewrite replaces `process.env.NODE_ENV` as written and nothing else, and
    any other read of `process` throws in a page. Only the check after the
    rewrites refuses it."""
    core = _tarball({"package/dist/index.js": f"export const debug = {read};\n"})
    monkeypatch.setattr(tool, "PACKAGES", (_package("table-core", core),
                                           tool.PACKAGES[1]))
    packages["table-core"] = core

    with pytest.raises(tool.VendorError,
                       match=r"^@test/table-core: index\.js still names process\.env$"):
        tool.build(packages)


def test_it_writes_both_copies_byte_for_byte_with_lf(packages, tmp_path):
    files = tool.build(packages)
    one, two = tmp_path / "engine" / "tanstack", tmp_path / "extension" / "tanstack"
    # A stale file from an earlier version must not survive a re-vendor.
    (one / "table-core").mkdir(parents=True)
    (one / "table-core" / "stale.js").write_text("old", encoding="utf-8")

    tool.write(files, (one, two))

    expected = {name: text.encode("utf-8") for name, text in files.items()}
    for root in (one, two):
        written = _tree(root)
        assert written == expected, root
        assert all(b"\r\n" not in data for data in written.values())
    assert not (one / "table-core" / "stale.js").exists()


def test_write_refuses_a_path_outside_its_destinations_and_writes_nothing(destinations,
                                                                         tmp_path):
    """THE SECOND WALL, for a path build() let through. Each target is resolved
    the way this machine writes it, and all of them are checked before either
    copy is touched."""
    before = _tree(tmp_path)

    with pytest.raises(tool.VendorError,
                       match=r"^table-core/\.\./\.\./escape\.js would be written outside"):
        tool.write({"table-core/index.js": "export {};\n",
                    "table-core/../../escape.js": "export {};\n"}, destinations)

    assert _tree(tmp_path) == before


def test_main_refuses_a_module_outside_its_package_and_writes_nothing(packages, destinations,
                                                                      tmp_path, monkeypatch,
                                                                      capsys):
    """A tarball entry whose name climbs out of dist, imported by the entry
    module, is refused before anything is written: unchecked, it lands one level
    above each copy."""
    core = _tarball({
        "package/dist/index.js": 'import { x } from "../../escape.js";\nexport { x };\n',
        "package/dist/../../escape.js": "export const x = 1;\n",
    })
    monkeypatch.setattr(tool, "PACKAGES", (_package("table-core", core),
                                           tool.PACKAGES[1]))
    packages["table-core"] = core
    arguments = _arguments(packages, tmp_path)
    before = _tree(tmp_path)

    code = tool.main(arguments)

    assert code == 1
    assert capsys.readouterr().out == (
        "refused: @test/table-core: ../../escape.js lies outside package/dist, so it "
        "would be written outside the package\n")
    assert _tree(tmp_path) == before


def test_main_refuses_and_writes_nothing_when_a_rule_is_broken(packages, destinations,
                                                              tmp_path, capsys):
    packages["store"] = packages["store"] + b"tampered"
    arguments = _arguments(packages, tmp_path)
    before = _tree(tmp_path)

    code = tool.main(arguments)

    assert code == 1
    assert "refused:" in capsys.readouterr().out
    # Both copies still hold the version before: a refusal removes nothing.
    assert _tree(tmp_path) == before


def test_main_writes_both_copies_where_destinations_names(packages, destinations,
                                                          tmp_path, capsys):
    code = tool.main(_arguments(packages, tmp_path))

    assert code == 0
    expected = {name: text.encode("utf-8") for name, text in tool.build(packages).items()}
    assert [_tree(root) for root in destinations] == [expected, expected]
    assert capsys.readouterr().out == "".join(
        f"wrote {len(expected)} files to {root.relative_to(tmp_path)}\n" for root in destinations)


def test_main_rejects_a_tarball_for_a_package_it_does_not_vendor(destinations, tmp_path):
    with pytest.raises(SystemExit) as stopped:
        tool.main([f"--tarball=lodash={tmp_path / 'x.tgz'}"])
    assert stopped.value.code == 2


def test_a_new_pin_downloads_the_version_it_names(monkeypatch):
    """The README's update step changes a version and an integrity, and that is
    the whole edit: a URL holding its own copy of the version fetched the old
    tarball, and the integrity check then blamed npm for it."""
    asked = []

    def urlopen(url, timeout):
        asked.append(url)
        return io.BytesIO(b"tarball")

    monkeypatch.setattr(tool.urllib.request, "urlopen", urlopen)
    unscoped = tool.Package(name="left-pad", npm="left-pad", version="1.3.0", integrity="",
                            dist="package", entries=("index.js",))

    for package in (*tool.PACKAGES, unscoped):
        assert tool.download(dataclasses.replace(package, version="99.0.0")) == b"tarball"

    assert asked == [
        "https://registry.npmjs.org/@tanstack/table-core/-/table-core-99.0.0.tgz",
        "https://registry.npmjs.org/@tanstack/store/-/store-99.0.0.tgz",
        "https://registry.npmjs.org/@tanstack/virtual-core/-/virtual-core-99.0.0.tgz",
        "https://registry.npmjs.org/left-pad/-/left-pad-99.0.0.tgz",
    ]


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
