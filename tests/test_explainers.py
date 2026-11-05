"""Interactive HTML explainers: output parsing, hardening, the job and the API."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from commands.explainer_commands import (
    GenerateExplainerInput,
    generate_explainer_command,
    run_explainer,
)
from open_notebook.domain.notebook import Note, Notebook, Source
from open_notebook.exceptions import IncompleteGenerationError, InvalidInputError
from open_notebook.utils import explainer, note_files

DOC = (
    "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
    "<title>How &amp; why tides work</title><style>body{}</style></head>"
    "<body><h1>Tides</h1><p>The moon pulls the sea.</p>"
    "<script>document.body.dataset.ok='1'</script></body></html>"
)


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


@pytest.fixture(autouse=True)
def files_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(note_files, "NOTE_FILES_FOLDER", str(tmp_path))
    return tmp_path


# --- parsing and hardening ---------------------------------------------------


def test_extract_html_accepts_bare_fenced_and_chatty_replies():
    assert explainer.extract_html(DOC) == DOC
    assert explainer.extract_html(f"```html\n{DOC}\n```") == DOC
    assert explainer.extract_html(f"Sure! Here it is:\n\n{DOC}\n\nEnjoy.") == DOC


@pytest.mark.parametrize(
    "reply", ["", "No HTML here", "```html\n<!DOCTYPE html><html><body>cut"]
)
def test_extract_html_rejects_missing_or_cut_off_documents(reply):
    with pytest.raises(IncompleteGenerationError):
        explainer.extract_html(reply)


def test_harden_puts_the_no_network_csp_first_in_head():
    hardened = explainer.harden_html(DOC)
    head = hardened.index("<head>") + len("<head>")
    assert hardened[head:].startswith('<meta http-equiv="Content-Security-Policy"')
    assert "default-src 'none'" in hardened and "connect-src 'none'" in hardened
    # A document without <head> still gets one.
    assert "Content-Security-Policy" in explainer.harden_html(
        "<html><body>x</body></html>"
    )
    assert "<header>" in explainer.harden_html("<html><header>h</header></html>")


def test_title_and_text_skip_scripts_and_styles():
    assert explainer.html_title(DOC) == "How & why tides work"
    text = explainer.html_to_text(DOC)
    assert "The moon pulls the sea." in text and "Tides" in text
    assert "dataset" not in text and "body{}" not in text


def test_sources_block_shares_the_budget_and_skips_empty_sources():
    block = explainer.build_sources_block(
        [
            ("source:a", "Short", "tiny"),
            ("source:b", 'Big "one"', "x" * 50_000),
            ("source:c", "Empty", "  "),
        ],
        budget_chars=10_000,
    )
    assert block.count("<source ") == 2
    assert 'title="Big &quot;one&quot;"' in block
    assert explainer.TRUNCATION_NOTICE.strip() in block
    assert len(block) < 12_000


def test_sources_block_without_text_is_invalid_input():
    with pytest.raises(InvalidInputError):
        explainer.build_sources_block([("source:a", "A", "")], 1000)


# --- the job -----------------------------------------------------------------


def _notebook_with_sources():
    nb = Notebook(id="notebook:n1", name="Tides", description="Ocean basics")
    sources = [
        Source(id="source:s1", title="Moon", full_text="The moon pulls the sea.")
    ]
    return nb, sources


@pytest.mark.asyncio
async def test_run_explainer_saves_a_hardened_explainer_note(files_dir):
    nb, sources = _notebook_with_sources()
    seen: dict[str, str] = {}

    async def llm(system, human, max_tokens):
        seen.update(system=system, human=human)
        return f"```html\n{DOC}\n```"

    with (
        patch.object(Notebook, "get", new=AsyncMock(return_value=nb)),
        patch.object(Notebook, "get_sources", new=AsyncMock(return_value=sources)),
        patch.object(Note, "save", new=AsyncMock(return_value=None)) as save,
        patch.object(Note, "add_to_notebook", new=AsyncMock()) as link,
    ):
        note = await run_explainer(
            GenerateExplainerInput(notebook_id="notebook:n1", instructions="for kids"),
            llm,
        )

    save.assert_awaited_once()
    link.assert_awaited_once_with("notebook:n1")
    assert note.explainer is True and note.note_type == "ai"
    assert note.title == "How & why tides work"
    assert note.attachment_mime == "text/html"
    assert note.attachment_name == "How-why-tides-work.html"
    assert "The moon pulls the sea." in (note.content or "")
    stored = Path(files_dir, note.attachment_file or "").read_text()
    assert "Content-Security-Policy" in stored
    # Instructions go in the system prompt's focus block; sources are data blocks.
    assert "for kids" in seen["system"] and "DARK MODE BY DEFAULT" in seen["system"]
    assert '<source n="1" id="source:s1" title="Moon">' in seen["human"]


@pytest.mark.asyncio
async def test_failed_link_removes_the_note_and_file(files_dir):
    nb, sources = _notebook_with_sources()

    async def llm(*_):
        return DOC

    async def fake_save(self):
        self.id = "note:x"

    with (
        patch.object(Notebook, "get", new=AsyncMock(return_value=nb)),
        patch.object(Notebook, "get_sources", new=AsyncMock(return_value=sources)),
        patch.object(Note, "save", new=fake_save),
        patch.object(
            Note, "add_to_notebook", new=AsyncMock(side_effect=RuntimeError("db"))
        ),
        patch(
            "open_notebook.domain.base.ObjectModel.delete",
            new=AsyncMock(return_value=True),
        ),
    ):
        with pytest.raises(RuntimeError):
            await run_explainer(GenerateExplainerInput(notebook_id="notebook:n1"), llm)
    assert list(Path(files_dir).iterdir()) == []


@pytest.mark.asyncio
async def test_command_reports_failures_instead_of_raising():
    with patch(
        "commands.explainer_commands.run_explainer",
        new=AsyncMock(side_effect=IncompleteGenerationError("cut off")),
    ):
        out = await generate_explainer_command(
            GenerateExplainerInput(notebook_id="notebook:n1")
        )
    assert out.success is False and out.error_message == "cut off"


# --- API -----------------------------------------------------------------------


def test_create_explainer_submits_a_job(client):
    nb, sources = _notebook_with_sources()
    with (
        patch.object(Notebook, "get", new=AsyncMock(return_value=nb)),
        patch.object(Notebook, "get_sources", new=AsyncMock(return_value=sources)),
        patch(
            "api.routers.explainers.CommandService.submit_command_job",
            new=AsyncMock(return_value="command:j1"),
        ) as submit,
    ):
        response = client.post(
            "/api/notebooks/notebook:n1/explainers", json={"instructions": "  focus  "}
        )
    assert response.status_code == 200
    assert response.json() == {
        "job_id": "command:j1",
        "status": "queued",
        "notebook_id": "notebook:n1",
    }
    assert submit.await_args is not None
    args = submit.await_args.args
    assert args[1] == "generate_explainer"
    assert args[2] == {
        "notebook_id": "notebook:n1",
        "mode": "sources",
        "instructions": "focus",
    }


def test_create_explainer_needs_sources_and_a_known_mode(client):
    nb, _ = _notebook_with_sources()
    with (
        patch.object(Notebook, "get", new=AsyncMock(return_value=nb)),
        patch.object(Notebook, "get_sources", new=AsyncMock(return_value=[])),
    ):
        assert (
            client.post("/api/notebooks/notebook:n1/explainers", json={}).status_code
            == 400
        )
        assert (
            client.post(
                "/api/notebooks/notebook:n1/explainers", json={"mode": "repo"}
            ).status_code
            == 422
        )


def test_explainer_file_may_run_scripts_but_not_reach_the_network(client, files_dir):
    stored = note_files.write_note_file(DOC.encode(), ".html")
    note = Note(
        id="note:n1", title="t", content="text", note_type="ai", explainer=True,
        attachment_name="t.html", attachment_file=stored, attachment_mime="text/html",
        attachment_size=len(DOC),
    )  # fmt: skip
    with patch("api.routers.notes.Note.get", new=AsyncMock(return_value=note)):
        response = client.get("/api/notes/note:n1/file")
        listed = client.get("/api/notes/note:n1").json()
    csp = response.headers["content-security-policy"]
    assert csp.startswith("sandbox allow-scripts;") and "allow-same-origin" not in csp
    assert "default-src 'none'" in csp
    assert listed["explainer"] is True


def test_harden_strips_resource_hints_and_refresh():
    page = (
        "<!DOCTYPE html><html><head>"
        "<link rel='preconnect' href='https://x.evil'>"
        '<link rel="dns-prefetch" href="//leak.evil">'
        "<LINK REL=prefetch HREF=https://y.evil/a>"
        '<meta http-equiv="refresh" content="0;url=https://z.evil">'
        "<link rel='stylesheet' href='data:text/css,'>"
        "</head><body>ok</body></html>"
    )
    hardened = explainer.harden_html(page)
    for gone in ("x.evil", "leak.evil", "y.evil", "z.evil"):
        assert gone not in hardened
    assert "rel='stylesheet'" in hardened and "Content-Security-Policy" in hardened


# --- output budget ----------------------------------------------------------


def test_default_output_budget_fits_a_full_page_from_a_reasoning_model(monkeypatch):
    """Measured on a real 2-source notebook with Claude Haiku: a complete page took
    30,353 output tokens, 8,859 of them hidden reasoning that shares the budget. The
    old 16,000 default cut every such page off, so the default must leave headroom."""
    monkeypatch.delenv("OPEN_NOTEBOOK_EXPLAINER_MAX_TOKENS", raising=False)
    assert explainer.max_output_tokens() >= 48_000


@pytest.mark.parametrize(
    "value,expected",
    [
        ("20000", 20_000),
        ("", explainer.DEFAULT_MAX_TOKENS),
        ("lots", explainer.DEFAULT_MAX_TOKENS),
        ("0", explainer.DEFAULT_MAX_TOKENS),
        ("-5", explainer.DEFAULT_MAX_TOKENS),
    ],
)
def test_output_budget_env_override_ignores_bad_values(monkeypatch, value, expected):
    monkeypatch.setenv("OPEN_NOTEBOOK_EXPLAINER_MAX_TOKENS", value)
    assert explainer.max_output_tokens() == expected
