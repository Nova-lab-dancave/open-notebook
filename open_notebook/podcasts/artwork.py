"""Podcast Feed artwork: validation and storage (see CONTEXT.md, Show Metadata).

Apple Podcasts wants square PNG or JPEG artwork between 1400 and 3000 pixels.
The upload is checked with Pillow, which reads only the header to get the
format and size, and `verify()` to catch a truncated or damaged file. The
original bytes are stored untouched; nothing is re-encoded.
"""

import hashlib
import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image, UnidentifiedImageError

from open_notebook.exceptions import InvalidInputError
from open_notebook.podcasts.audio_paths import podcasts_root

MIN_PIXELS = 1400
MAX_PIXELS = 3000
MAX_BYTES = 10 * 1024 * 1024

# Pillow format name -> (file extension, media type)
FORMATS = {"PNG": (".png", "image/png"), "JPEG": (".jpg", "image/jpeg")}
MEDIA_TYPES = {ext: media for ext, media in FORMATS.values()}


@dataclass(frozen=True)
class Artwork:
    extension: str  # ".png" or ".jpg"
    media_type: str
    version: str  # short content hash; changes whenever the image does


def artwork_dir() -> Path:
    """Folder holding the artwork, inside the podcasts root (never under episodes/)."""
    return podcasts_root() / "feed"


def artwork_path(extension: str) -> Path:
    return artwork_dir() / f"artwork{extension}"


def validate_artwork(data: bytes) -> Artwork:
    """Check an uploaded image; raise InvalidInputError with a specific reason."""
    if not data:
        raise InvalidInputError("The artwork file is empty.")
    if len(data) > MAX_BYTES:
        raise InvalidInputError("The artwork file is too large (10 MB at most).")

    try:
        image = Image.open(io.BytesIO(data))
    except UnidentifiedImageError:
        raise InvalidInputError("The artwork is not a PNG or JPEG image.")
    except Image.DecompressionBombError:
        raise InvalidInputError(
            f"The artwork must be at most {MAX_PIXELS}x{MAX_PIXELS} pixels."
        )
    except (OSError, ValueError, SyntaxError):
        raise InvalidInputError(
            "Could not read the artwork; the image file looks damaged."
        )

    if image.format not in FORMATS:
        raise InvalidInputError(
            f"The artwork must be a PNG or JPEG image (got {image.format})."
        )

    width, height = image.size
    if width != height:
        raise InvalidInputError(
            f"The artwork must be square (this one is {width}x{height} pixels)."
        )
    if width < MIN_PIXELS:
        raise InvalidInputError(
            f"The artwork must be at least {MIN_PIXELS}x{MIN_PIXELS} pixels "
            f"(this one is {width}x{height})."
        )
    if width > MAX_PIXELS:
        raise InvalidInputError(
            f"The artwork must be at most {MAX_PIXELS}x{MAX_PIXELS} pixels "
            f"(this one is {width}x{height})."
        )

    try:
        image.verify()
    except Exception:
        raise InvalidInputError(
            "Could not read the artwork; the image file looks damaged."
        )

    extension, media_type = FORMATS[image.format]
    return Artwork(
        extension=extension,
        media_type=media_type,
        version=hashlib.sha256(data).hexdigest()[:12],
    )


def save_artwork(data: bytes, artwork: Artwork) -> None:
    """Write the file (atomically), then remove a leftover of the other format."""
    folder = artwork_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = artwork_path(artwork.extension)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, target)
    for extension in MEDIA_TYPES:
        if extension != artwork.extension:
            artwork_path(extension).unlink(missing_ok=True)


def current_artwork(extension: Optional[str]) -> Optional[tuple[Path, str]]:
    """The stored artwork file and its media type, or None if there is none.

    Only a known extension is accepted and the path is built from a fixed
    name, so a bad record value can never point outside the artwork folder.
    A record whose file vanished counts as no artwork.
    """
    if extension not in MEDIA_TYPES:
        return None
    path = artwork_path(extension)  # type: ignore[arg-type]
    if not path.is_file():
        return None
    return path, MEDIA_TYPES[extension]  # type: ignore[index]
