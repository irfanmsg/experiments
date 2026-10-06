"""Stream quality selects the renderer's resolution, up to UHD 4K."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request

from app import main


@pytest.mark.parametrize("quality,size", [
    ("full_hd", (1920, 1080)), ("qhd", (2560, 1440)), ("uhd", (3840, 2160)),
    ("hd", (1280, 720)), ("standard", (640, 360)), (None, (1280, 720)),
    ("8k", None),
])
def test_stream_quality_launches_requested_resolution(quality, size, tmp_path, monkeypatch):
    project = tmp_path / "scene"
    project.mkdir()
    (project / "all_styles.usda").write_text("#usda 1.0\n")
    monkeypatch.setattr(main, "UPLOADS", tmp_path)
    monkeypatch.setattr(main, "OUTPUT", tmp_path)
    for name in ("_stream_process", "_stream_project", "_stream_style", "_stream_quality"):
        monkeypatch.setattr(main, name, None)
    monkeypatch.setattr(main, "_stream_physics", False)
    launches = []
    monkeypatch.setattr(main.subprocess, "Popen", lambda command, **kwargs:
                        launches.append(command) or SimpleNamespace(poll=lambda: None))
    body = {"style": "all_styles", "physics": True}
    if quality is not None:
        body["quality"] = quality

    async def receive():
        return {"type": "http.request", "body": json.dumps(body).encode()}

    request = Request({"type": "http", "scheme": "http", "server": ("example.test", 8000),
                       "path": "/", "headers": []}, receive)
    if size is None:
        with pytest.raises(HTTPException) as error:
            asyncio.run(main.start_stream("scene", request))
        assert error.value.status_code == 400
        assert not launches
        return
    result = asyncio.run(main.start_stream("scene", request))
    command = launches[0]
    assert command[command.index("--width") + 1] == str(size[0])
    assert command[command.index("--height") + 1] == str(size[1])
    assert "--physics" in command
    assert result["quality"] == (quality or "hd")
    assert result["style"] == "all_styles" and result["physics"] is True
