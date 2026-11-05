"""Generate an interactive HTML explainer from a notebook's sources.

The page is saved as a note with an HTML attachment flagged ``explainer``
(migration 104); see ``open_notebook/utils/explainer.py`` for the safety model.
"""

import time
from typing import Awaitable, Callable, Optional

from ai_prompter import Prompter
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
from surreal_commands import CommandInput, CommandOutput, command

from open_notebook.ai.provision import provision_langchain_model
from open_notebook.domain.notebook import Note, Notebook
from open_notebook.exceptions import OpenNotebookError
from open_notebook.utils.error_classifier import classify_error
from open_notebook.utils.explainer import (
    MAX_INSTRUCTIONS_CHARS,
    build_sources_block,
    context_chars,
    extract_html,
    harden_html,
    html_title,
    html_to_text,
    max_output_tokens,
)
from open_notebook.utils.note_files import remove_note_file, store_note_file
from open_notebook.utils.text_utils import clean_thinking_content, extract_text_content

MAX_TITLE_CHARS = 200

# async (system, human, max_tokens) -> reply text
ExplainerLLM = Callable[[str, str, int], Awaitable[str]]


class GenerateExplainerInput(CommandInput):
    notebook_id: str
    mode: str = "sources"
    instructions: Optional[str] = None
    # ISO time the API queued the job; lets the notes pane list and age jobs
    # (surreal-commands records carry no timestamps of their own).
    requested_at: Optional[str] = None


class GenerateExplainerOutput(CommandOutput):
    success: bool
    notebook_id: str
    note_id: Optional[str] = None
    title: Optional[str] = None
    processing_time: float = 0.0
    error_message: Optional[str] = None


async def default_explainer_llm(system: str, human: str, max_tokens: int) -> str:
    """One call to the default chat model (large-context model for big inputs)."""
    payload = [SystemMessage(content=system), HumanMessage(content=human)]
    try:
        model = await provision_langchain_model(
            str(payload), None, "chat", max_tokens=max_tokens
        )
        response = await model.ainvoke(payload)
    except OpenNotebookError:
        raise
    except Exception as e:
        exc_class, message = classify_error(e)
        raise exc_class(message) from e
    return clean_thinking_content(extract_text_content(response.content))


async def run_explainer(
    data: GenerateExplainerInput, llm: ExplainerLLM = default_explainer_llm
) -> Note:
    """Build the explainer and save it as a note in the notebook."""
    if data.mode != "sources":
        raise ValueError(f"Unsupported explainer mode: {data.mode}")

    notebook = await Notebook.get(data.notebook_id)
    sources = await notebook.get_sources(include_full_text=True)
    block = build_sources_block(
        [(str(s.id), s.title or "Untitled source", s.full_text or "") for s in sources],
        context_chars(),
    )

    instructions = (data.instructions or "").strip()[:MAX_INSTRUCTIONS_CHARS]
    system = Prompter(prompt_template="explainer/system").render(
        data={"instructions": instructions}
    )
    human = (
        f"Notebook title: {notebook.name}\n"
        f"Notebook description: {notebook.description or '(none)'}\n\n"
        f"<sources>\n{block}\n</sources>\n\n"
        "Write the complete HTML explainer now."
    )

    reply = await llm(system, human, max_output_tokens())
    html = harden_html(extract_html(reply))

    title = (html_title(html) or f"Explainer: {notebook.name}")[:MAX_TITLE_CHARS]
    content = html_to_text(html) or title
    file_name = _file_name(title)
    raw = html.encode("utf-8")

    stored = await store_note_file(raw, ".html")
    note = Note(
        title=title,
        content=content,
        note_type="ai",
        explainer=True,
        attachment_name=file_name,
        attachment_file=stored,
        attachment_mime="text/html",
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
                logger.warning(f"Failed to remove orphan explainer note: {e}")
        remove_note_file(stored)
        raise
    return note


def _file_name(title: str) -> str:
    safe = "".join(c if c.isalnum() or c in " -_" else " " for c in title)
    safe = "-".join(safe.split())[:80].strip("-")
    return f"{safe or 'explainer'}.html"


@command("generate_explainer", app="open_notebook", retry={"max_attempts": 1})
async def generate_explainer_command(
    input_data: GenerateExplainerInput,
) -> GenerateExplainerOutput:
    """Generate one explainer. Not retried automatically (avoids duplicate notes);
    the user starts a new one from the UI instead."""
    start = time.time()
    try:
        note = await run_explainer(input_data)
        logger.info(f"Explainer {note.id} created for {input_data.notebook_id}")
        return GenerateExplainerOutput(
            success=True,
            notebook_id=input_data.notebook_id,
            note_id=str(note.id),
            title=note.title,
            processing_time=time.time() - start,
        )
    except (OpenNotebookError, ValueError) as e:
        logger.warning(f"Explainer generation failed: {e}")
        message = str(e)
    except Exception as e:
        logger.exception(e)
        message = "Explainer generation failed unexpectedly. Check the worker logs."
    return GenerateExplainerOutput(
        success=False,
        notebook_id=input_data.notebook_id,
        processing_time=time.time() - start,
        error_message=message,
    )
