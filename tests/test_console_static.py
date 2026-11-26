"""The Console's static files (P1-T28a): packaged, served, offline, routes consistent."""

from __future__ import annotations

import _socket
import re
import socket
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from vnstratlab.app.server import STATIC_DIR, create_app

STATIC_FILES = sorted(p for p in STATIC_DIR.rglob("*") if p.is_file())
TEXT_FILES = [p for p in STATIC_FILES if p.suffix in {".html", ".css", ".js", ".svg"}]
JS_FILES = sorted(STATIC_DIR.glob("js/*.js"))
ORDER_WORDS = re.compile(r"đặt lệnh|place.?order|buy now|sell now|mua ngay|bán ngay", re.I)


@pytest.fixture(autouse=True)
def _loopback_only(no_network: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows asyncio's self-pipe connects to 127.0.0.1; allow exactly that (as test_serve)."""
    refuse = socket.socket.connect

    def connect(self: socket.socket, address: Any) -> None:
        if isinstance(address, tuple) and address[0] == "127.0.0.1":
            _socket.socket.connect(self, address)
        else:
            refuse(self, address)

    monkeypatch.setattr(socket.socket, "connect", connect)


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path), base_url="http://127.0.0.1:8000")


def test_static_assets_are_served(client: TestClient) -> None:
    assert client.get("/").status_code == 200
    for path in STATIC_FILES:
        rel = path.relative_to(STATIC_DIR).as_posix()
        assert client.get(f"/{rel}").status_code == 200, rel
    assert {p.suffix for p in STATIC_FILES} == {".html", ".css", ".js", ".woff2", ".svg", ".txt"}


@pytest.mark.parametrize("path", TEXT_FILES, ids=lambda p: p.name)
def test_no_external_urls(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    # an XML namespace id is not a request
    text = text.replace('xmlns="http://www.w3.org/2000/svg"', "")
    assert not re.search(r"https?://|//cdn\.", text), path.name


def test_fonts_are_bundled_with_licence() -> None:
    css = (STATIC_DIR / "css" / "console.css").read_text(encoding="utf-8")
    fonts = re.findall(r'url\("\.\./(fonts/[^"]+)"\)', css)
    assert {Path(f).name for f in fonts} == {"Geist-Variable.woff2", "GeistMono-Variable.woff2"}
    for font in fonts:
        assert (STATIC_DIR / font).stat().st_size > 10_000, font
    assert "SIL OPEN FONT LICENSE" in (STATIC_DIR / "fonts" / "OFL.txt").read_text(encoding="utf-8")
    assert (STATIC_DIR / "buffalo.svg").is_file()


@pytest.mark.parametrize("path", JS_FILES, ids=lambda p: p.name)
def test_no_innerhtml_with_data(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    banned = r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\("
    assert not re.search(banned, text), path.name


def test_index_references_only_local_assets() -> None:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    refs = re.findall(r'(?:href|src)="([^"#][^"]*)"', html)
    local = [r for r in refs if not r.startswith("data:")]
    assert "css/console.css" in local
    assert "js/theme.js" in local
    assert "js/main.js" in local
    for ref in local:
        assert (STATIC_DIR / ref).is_file(), ref


def test_js_imports_resolve() -> None:
    for path in STATIC_DIR.glob("js/*.js"):
        for target in re.findall(r'from "\./([\w-]+\.js)"', path.read_text(encoding="utf-8")):
            assert (STATIC_DIR / "js" / target).is_file(), f"{path.name} imports {target}"


def test_nav_routes_exist_in_router() -> None:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    routes = re.findall(r'data-route="([\w-]+)"', html)
    assert routes == [
        "tong-quan",
        "huong-dan",
        "runs",
        "du-lieu",
        "ket-qua",
        "chien-luoc",
        "cau-hinh",
    ]
    main = (STATIC_DIR / "js" / "main.js").read_text(encoding="utf-8")
    for route in routes:
        assert f'"{route}"' in main, route
    assert 'lang="vi"' in html
    assert "Chỉ khuyến nghị — không đặt lệnh" in html


def test_guide_data_has_six_pipeline_steps() -> None:
    text = (STATIC_DIR / "js" / "guide-data.js").read_text(encoding="utf-8")
    ids = re.findall(r'^\s+id: "(\w+)"', text, re.M)
    assert ids == ["ingest", "rebuild", "features", "strategies", "simulator", "report"]
    assert text.count("command:") == 6
    assert text.count("watch: [") == 6


def test_mock_fixture_mode_and_post_guard_header() -> None:
    util = (STATIC_DIR / "js" / "util.js").read_text(encoding="utf-8")
    assert 'get("mock") === "1"' in util
    assert '"X-Vnstratlab": "1"' in util
    assert (STATIC_DIR / "js" / "mock.js").is_file()


def test_no_order_ui() -> None:
    for path in TEXT_FILES:
        text = path.read_text(encoding="utf-8")
        # the only allowed mention is the "recommend only" disclaimer itself
        text = text.replace("không đặt lệnh", "").replace("không bao giờ đặt lệnh", "")
        assert not ORDER_WORDS.search(text), path.name
