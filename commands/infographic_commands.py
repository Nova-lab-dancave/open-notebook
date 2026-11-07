"""Generate a static SVG infographic from a notebook's sources.

The image is saved as a note with an ``image/svg+xml`` attachment; see
``open_notebook/utils/infographic.py`` for the styles, layouts and safety model.
"""

import time
from typing import Awaitable, Callable, Optional

from ai_prompter import Prompter
from loguru import logger
from surreal_commands import CommandInput, CommandOutput, command

from commands.explainer_commands import default_explainer_llm
from open_notebook.domain.notebook import Note, Notebook
from open_notebook.exceptions import OpenNotebookError
from open_notebook.utils.explainer import build_sources_block
from open_notebook.utils.infographic import (
    ASPECTS,
    DEFAULT_ASPECT,
    DEFAULT_LAYOUT,
    DEFAULT_STYLE,
    LAYOUTS,
    MAX_INSTRUCTIONS_CHARS,
    STYLES,
    SVG_MIME,
    context_chars,
    extract_svg,
    max_output_tokens,
    sanitize_svg,
    svg_text,
    svg_title,
)
from open_notebook.utils.note_files import remove_note_file, store_note_file

MAX_TITLE_CHARS = 200

# async (system, human, max_tokens) -> reply text
InfographicLLM = Callable[[str, str, int], Awaitable[str]]


class GenerateInfographicInput(CommandInput):
    notebook_id: str
    style: str = DEFAULT_STYLE
    layout: str = DEFAULT_LAYOUT
    aspect: str = DEFAULT_ASPECT
    instructions: Optional[str] = None
    # ISO time the API queued the job (the notes pane lists and ages jobs by it).
    requested_at: Optional[str] = None


class GenerateInfographicOutput(CommandOutput):
    success: bool
    notebook_id: str
    note_id: Optional[str] = None
    title: Optional[str] = None
    processing_time: float = 0.0
    error_message: Optional[str] = None


async def run_infographic(
    data: GenerateInfographicInput, llm: Optional[InfographicLLM] = None
) -> Note:
    """Draw the infographic and save it as a note in the notebook."""
    llm = llm or default_explainer_llm
    style = STYLES.get(data.style)
    layout = LAYOUTS.get(data.layout)
    size = ASPECTS.get(data.aspect)
    if not style or not layout or not size:
        raise ValueError(
            f"Unknown infographic option: {data.style}/{data.layout}/{data.aspect}"
        )

    notebook = await Notebook.get(data.notebook_id)
    sources = await notebook.get_sources(include_full_text=True)
    block = build_sources_block(
        [(str(s.id), s.title or "Untitled source", s.full_text or "") for s in sources],
        context_chars(),
    )

    width, height = size
    system = Prompter(prompt_template="infographic/system").render(
        data={
            "width": width,
            "height": height,
            "style_name": style.name,
            "style_guidance": style.guidance,
            "layout_name": layout.name,
            "layout_guidance": layout.guidance,
            "instructions": (data.instructions or "").strip()[:MAX_INSTRUCTIONS_CHARS],
        }
    )
    human = (
        f"Notebook title: {notebook.name}\n"
        f"Notebook description: {notebook.description or '(none)'}\n\n"
        f"<sources>\n{block}\n</sources>\n\n"
        "Draw the complete SVG infographic now."
    )

    reply = await llm(system, human, max_output_tokens())
    svg = sanitize_svg(extract_svg(reply), data.aspect)

    title = (svg_title(svg) or f"Infographic: {notebook.name}")[:MAX_TITLE_CHARS]
    content = svg_text(svg) or title
    raw = svg.encode("utf-8")

    stored = await store_note_file(raw, ".svg")
    note = Note(
        title=title,
        content=content,
        note_type="ai",
        attachment_name=_file_name(title),
        attachment_file=stored,
        attachment_mime=SVG_MIME,
        attachment_size=len(raw),
    )
    try:
        await note.save()
        await note.add_to_notebook(data.notebook_id)
    except Exception:
        if note.id:
            try:
                await note.delete()  # also removes the stored file
            except Exception as e:
                logger.warning(f"Failed to remove orphan infographic note: {e}")
        remove_note_file(stored)
        raise
    return note


def _file_name(title: str) -> str:
    safe = "".join(c if c.isalnum() or c in " -_" else " " for c in title)
    safe = "-".join(safe.split())[:80].strip("-")
    return f"{safe or 'infographic'}.svg"


@command("generate_infographic", app="open_notebook", retry={"max_attempts": 1})
async def generate_infographic_command(
    input_data: GenerateInfographicInput,
) -> GenerateInfographicOutput:
    """Generate one infographic. Not retried automatically (avoids duplicate
    notes); the user starts a new one from the UI instead."""
    start = time.time()
    try:
        note = await run_infographic(input_data)
        logger.info(f"Infographic {note.id} created for {input_data.notebook_id}")
        return GenerateInfographicOutput(
            success=True,
            notebook_id=input_data.notebook_id,
            note_id=str(note.id),
            title=note.title,
            processing_time=time.time() - start,
        )
    except (OpenNotebookError, ValueError) as e:
        logger.warning(f"Infographic generation failed: {e}")
        message = str(e)
    except Exception as e:
        logger.exception(e)
        message = "Infographic generation failed unexpectedly. Check the worker logs."
    return GenerateInfographicOutput(
        success=False,
        notebook_id=input_data.notebook_id,
        processing_time=time.time() - start,
        error_message=message,
    )
