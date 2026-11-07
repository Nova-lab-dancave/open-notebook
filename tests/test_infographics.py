"""Infographics: SVG extraction and sanitising, the job, the API, the file."""

import re
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from commands.infographic_commands import (
    GenerateInfographicInput,
    generate_infographic_command,
    run_infographic,
)
from open_notebook.domain.notebook import Note, Notebook, Source
from open_notebook.exceptions import IncompleteGenerationError
from open_notebook.utils import infographic, note_files

SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920">'
    "<title>Tides &amp; the moon</title>"
    '<defs><linearGradient id="g"><stop offset="0" stop-color="#fff"/>'
    "</linearGradient></defs>"
    '<rect width="1080" height="1920" fill="url(#g)"/>'
    '<text x="48" y="120" font-size="64">Tides<tspan x="48" dy="70">explained'
    "</tspan></text>"
    '<text x="48" y="400">The moon pulls the sea.</text>'
    "</svg>"
)


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


@pytest.fixture(autouse=True)
def files_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(note_files, "NOTE_FILES_FOLDER", str(tmp_path))
    return tmp_path


# --- extracting and sanitising ------------------------------------------------


def test_extract_svg_accepts_bare_fenced_and_chatty_replies():
    assert infographic.extract_svg(SVG) == SVG
    assert infographic.extract_svg(f"```svg\n{SVG}\n```") == SVG
    assert infographic.extract_svg(f"Here you go:\n\n{SVG}\n\nEnjoy!") == SVG


@pytest.mark.parametrize("reply", ["", "No image here", "```svg\n<svg><rect/>"])
def test_extract_svg_rejects_missing_or_cut_off_images(reply):
    with pytest.raises(IncompleteGenerationError):
        infographic.extract_svg(reply)


def test_sanitize_keeps_drawing_and_local_references():
    clean = infographic.sanitize_svg(SVG)
    assert 'fill="url(#g)"' in clean and "<linearGradient" in clean
    assert "explained</tspan>" in clean
    assert 'width="1080"' in clean and 'height="1920"' in clean


def test_sanitize_strips_everything_that_could_run_or_load():
    evil = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 100 100" '
        'onload="alert(1)">'
        "<script>alert(2)</script>"
        '<foreignObject><div xmlns="http://www.w3.org/1999/xhtml">x</div>'
        "</foreignObject>"
        '<a href="https://evil.example"><text>link</text></a>'
        '<image href="https://evil.example/p.png"/>'
        '<use xlink:href="https://evil.example/s.svg#x"/>'
        '<use href="#ok"/>'
        '<animate attributeName="href" to="javascript:alert(3)"/>'
        '<rect fill="url(https://evil.example/t)" style="fill:red"/>'
        '<circle style="background:url(https://evil.example)"/>'
        "<style>@import url(https://evil.example/x.css);</style>"
        "<style>.a{fill:url(#g)}</style>"
        "</svg>"
    )
    clean = infographic.sanitize_svg(evil)
    lowered = clean.lower()
    for bad in ("script", "alert", "foreignobject", "evil.example", "<a ", "<image"):
        assert bad not in lowered, bad
    assert "onload" not in lowered and "animate" not in lowered
    assert 'href="#ok"' in clean and ".a{fill:url(#g)}" in clean
    assert 'style="fill:red"' in clean  # harmless inline style kept


def test_sanitize_repairs_html_entities_and_bare_ampersands():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
        "<text>R&D&nbsp;costs &mdash; &bogus; &lt;5%</text></svg>"
    )
    clean = infographic.sanitize_svg(svg)
    assert infographic.svg_text(clean) == "R&D costs \u2014 &bogus; <5%"


def test_sanitize_refuses_entities_and_broken_xml():
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY a "aaaa">]>'
        '<svg xmlns="http://www.w3.org/2000/svg">&a;</svg>'
    )
    clean = infographic.sanitize_svg(bomb)  # DOCTYPE dropped, &a; kept as text
    assert "<!ENTITY" not in clean and "aaaa" not in clean
    with pytest.raises(IncompleteGenerationError):
        infographic.sanitize_svg("<svg><rect></svg>")
    with pytest.raises(IncompleteGenerationError):
        infographic.sanitize_svg("<html><body/></html>")


def test_sanitize_sets_a_size_from_the_aspect_when_missing():
    clean = infographic.sanitize_svg(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100%"><rect/></svg>',
        "landscape",
    )
    assert 'viewBox="0 0 1920 1080"' in clean
    assert 'width="1920"' in clean and 'height="1080"' in clean


def test_title_and_text():
    clean = infographic.sanitize_svg(SVG)
    assert infographic.svg_title(clean) == "Tides & the moon"
    assert infographic.svg_text(clean).splitlines() == [
        "Tides & the moon",
        "Tides explained",
        "The moon pulls the sea.",
    ]


def test_frontend_offers_exactly_the_backend_options():
    path = Path(__file__).parents[1] / "frontend/src/lib/infographic-options.ts"
    source = path.read_text()
    ids = set(re.findall(r"id: '([a-z-]+)'", source))
    expected = set(infographic.STYLES) | set(infographic.LAYOUTS)
    expected |= set(infographic.ASPECTS)
    assert ids == expected


# --- the job ------------------------------------------------------------------


def _notebook_with_sources():
    nb = Notebook(id="notebook:n1", name="Tides", description="Ocean basics")
    sources = [
        Source(id="source:s1", title="Moon", full_text="The moon pulls the sea.")
    ]
    return nb, sources


@pytest.mark.asyncio
async def test_run_infographic_saves_a_sanitised_svg_note(files_dir):
    nb, sources = _notebook_with_sources()
    seen: dict[str, str] = {}

    async def llm(system, human, max_tokens):
        seen.update(system=system, human=human)
        return f"```svg\n{SVG.replace('<rect', '<script>x()</script><rect')}\n```"

    with (
        patch.object(Notebook, "get", new=AsyncMock(return_value=nb)),
        patch.object(Notebook, "get_sources", new=AsyncMock(return_value=sources)),
        patch.object(Note, "save", new=AsyncMock(return_value=None)) as save,
        patch.object(Note, "add_to_notebook", new=AsyncMock()) as link,
    ):
        note = await run_infographic(
            GenerateInfographicInput(
                notebook_id="notebook:n1",
                style="chalkboard",
                layout="hub-spoke",
                aspect="square",
                instructions="for kids",
            ),
            llm,
        )

    save.assert_awaited_once()
    link.assert_awaited_once_with("notebook:n1")
    assert note.note_type == "ai" and not note.explainer
    assert note.title == "Tides & the moon"
    assert note.attachment_mime == "image/svg+xml"
    assert note.attachment_name == "Tides-the-moon.svg"
    assert "The moon pulls the sea." in (note.content or "")
    stored = Path(files_dir, note.attachment_file or "").read_text()
    assert stored.startswith("<svg") and "script" not in stored
    system = seen["system"]
    assert "STYLE: Chalkboard" in system and "LAYOUT: Hub and spoke" in system
    assert 'viewBox="0 0 1440 1440"' in system and "for kids" in system
    assert '<source n="1" id="source:s1" title="Moon">' in seen["human"]


@pytest.mark.asyncio
async def test_command_reports_failures_instead_of_raising():
    nb, sources = _notebook_with_sources()
    with (
        patch.object(Notebook, "get", new=AsyncMock(return_value=nb)),
        patch.object(Notebook, "get_sources", new=AsyncMock(return_value=sources)),
        patch(
            "commands.infographic_commands.default_explainer_llm",
            new=AsyncMock(return_value="sorry, no"),
        ),
    ):
        out = await generate_infographic_command(
            GenerateInfographicInput(notebook_id="notebook:n1")
        )
    assert out.success is False
    assert "did not return an SVG" in (out.error_message or "")


@pytest.mark.asyncio
async def test_unknown_option_fails_the_job():
    out = await generate_infographic_command(
        GenerateInfographicInput(notebook_id="notebook:n1", style="nope")
    )
    assert out.success is False and "Unknown infographic option" in (
        out.error_message or ""
    )


# --- the API ------------------------------------------------------------------


def test_create_infographic_submits_a_job(client):
    nb, sources = _notebook_with_sources()
    with (
        patch.object(Notebook, "get", new=AsyncMock(return_value=nb)),
        patch.object(Notebook, "get_sources", new=AsyncMock(return_value=sources)),
        patch(
            "api.routers.infographics.CommandService.submit_command_job",
            new=AsyncMock(return_value="command:j1"),
        ) as submit,
    ):
        response = client.post(
            "/api/notebooks/notebook:n1/infographics",
            json={"style": "pixel-art", "aspect": "landscape", "instructions": " x "},
        )
    assert response.status_code == 200
    assert response.json()["job_id"] == "command:j1"
    assert submit.await_args is not None
    args = submit.await_args.args
    assert args[1] == "generate_infographic"
    assert datetime.fromisoformat(args[2].pop("requested_at")).tzinfo is not None
    assert args[2] == {
        "notebook_id": "notebook:n1",
        "style": "pixel-art",
        "layout": "auto",
        "aspect": "landscape",
        "instructions": "x",
    }


def test_create_infographic_validates_options_and_sources(client):
    nb, sources = _notebook_with_sources()
    url = "/api/notebooks/notebook:n1/infographics"
    with (
        patch.object(Notebook, "get", new=AsyncMock(return_value=nb)),
        patch.object(Notebook, "get_sources", new=AsyncMock(return_value=[])),
    ):
        assert client.post(url, json={}).status_code == 400  # no sources
        assert client.post(url, json={"style": "nope"}).status_code == 400
        assert client.post(url, json={"layout": "nope"}).status_code == 400
        assert client.post(url, json={"aspect": "tall"}).status_code == 422


def test_infographic_jobs_use_their_own_command(client):
    nb, _ = _notebook_with_sources()
    rows = [
        {
            "id": "command:stuck",
            "status": "new",
            "args": {
                "notebook_id": "notebook:n1",
                "requested_at": "2020-01-01T00:00:00+00:00",
            },
            "result": None,
        }
    ]
    with (
        patch.object(Notebook, "get", new=AsyncMock(return_value=nb)),
        patch("api.generation_jobs.repo_query", new=AsyncMock(return_value=rows)) as q,
    ):
        response = client.get("/api/notebooks/notebook:n1/infographics/jobs")
    assert response.status_code == 200
    assert q.await_args is not None
    assert q.await_args.args[1]["name"] == "generate_infographic"
    # Queued for years: reported as failed (stale), which then ages out.
    assert response.json() == []


def test_infographic_file_is_served_locked_down(client, files_dir):
    raw = infographic.sanitize_svg(SVG).encode()
    stored = note_files.write_note_file(raw, ".svg")
    note = Note(
        id="note:n1", title="t", content="text", note_type="ai",
        attachment_name="t.svg", attachment_file=stored,
        attachment_mime="image/svg+xml", attachment_size=len(raw),
    )  # fmt: skip
    with patch("api.routers.notes.Note.get", new=AsyncMock(return_value=note)):
        response = client.get("/api/notes/note:n1/file")
        listed = client.get("/api/notes/note:n1").json()
    assert response.headers["content-type"].startswith("image/svg+xml")
    csp = response.headers["content-security-policy"]
    assert csp.startswith("sandbox;") and "default-src 'none'" in csp
    assert "script-src" not in csp
    assert listed["infographic"] is True and listed["explainer"] is False


def test_svg_is_still_not_uploadable(client):
    nb, _ = _notebook_with_sources()
    with patch.object(Notebook, "get", new=AsyncMock(return_value=nb)):
        response = client.post(
            "/api/notes/upload",
            files={"file": ("x.svg", SVG.encode(), "image/svg+xml")},
            data={"notebook_id": "notebook:n1"},
        )
    assert response.status_code == 415
