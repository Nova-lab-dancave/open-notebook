"""
Tests for Show Metadata and artwork of the Podcast Feed (#31, spec #37, ticket #43).

Seam: the HTTP API through the FastAPI test client against the real app. The
settings record is the real `PodcastFeedSettings`; only the database boundary
is faked (a one-record in-memory store). Artwork files are real files under a
temporary podcasts folder, and test images are generated with the sizes the
test names, so dimensions come from the test, not from the code under test.
"""

import io
import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from open_notebook.domain.podcast_feed import PodcastFeedSettings

PASSWORD = "app-password"
AUTH = {"Authorization": f"Bearer {PASSWORD}"}
TOKEN = "tok-abc123"
PUBLIC_URL = "https://lab.example.ts.net:8502"
ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
SETTINGS = "/api/podcasts/feed-settings"
ARTWORK = "/api/podcasts/feed-settings/artwork"
FEED = f"/api/podcasts/feed/{TOKEN}/feed.xml"
NOT_FOUND = {"detail": "Not found"}


def image_bytes(fmt="PNG", size=(1400, 1400), color="navy"):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


def upload(client, data, name="cover.png", content_type="image/png", headers=AUTH):
    return client.post(
        ARTWORK, files={"file": (name, data, content_type)}, headers=headers
    )


@pytest.fixture
def client(monkeypatch):
    """The real app with OPEN_NOTEBOOK_PASSWORD set (rebuilds the middleware)."""
    from api.main import app

    monkeypatch.setenv("OPEN_NOTEBOOK_PASSWORD", PASSWORD)
    app.middleware_stack = None
    try:
        yield TestClient(app)
    finally:
        monkeypatch.setenv("OPEN_NOTEBOOK_PASSWORD", "")
        app.middleware_stack = None


@pytest.fixture(autouse=True)
def environment(monkeypatch, tmp_path):
    monkeypatch.setenv("OPEN_NOTEBOOK_PUBLIC_URL", PUBLIC_URL)
    monkeypatch.delenv("API_URL", raising=False)
    monkeypatch.setattr(
        "open_notebook.podcasts.audio_paths.PODCASTS_FOLDER", str(tmp_path)
    )
    with patch("open_notebook.podcasts.models.repo_query", AsyncMock(return_value=[])):
        yield


@pytest.fixture
def db():
    """Fake database for the settings record, starting with TOKEN saved."""
    store: dict = {"feed_token": TOKEN}

    async def fake_query(query, params=None):
        return [dict(store)] if store else []

    async def fake_upsert(table, id, data, add_timestamp=False):
        store.update(data)
        return [dict(store)]

    PodcastFeedSettings.clear_instance()
    with (
        patch("open_notebook.domain.base.repo_query", fake_query),
        patch("open_notebook.domain.base.repo_upsert", fake_upsert),
    ):
        yield store
    PodcastFeedSettings.clear_instance()


def channel(client):
    feed = client.get(FEED)  # no password header: the token is the credential
    assert feed.status_code == 200
    found = ET.fromstring(feed.content).find("channel")
    assert found is not None
    return found


class TestShowMetadataDefaults:
    def test_reading_and_editing_need_the_app_password(self, client, db):
        assert client.get(SETTINGS).status_code == 401
        assert client.put(SETTINGS, json={"title": "X"}).status_code == 401
        assert (
            client.post(ARTWORK, files={"file": ("a.png", image_bytes())}).status_code
            == 401
        )
        assert client.get(ARTWORK).status_code == 401
        assert "show_title" not in db

    def test_unset_fields_show_the_defaults(self, client, db):
        body = client.get(SETTINGS, headers=AUTH).json()

        assert body == {
            "title": "Open Notebook Podcasts",
            "author": "Open Notebook",
            "description": "Podcast episodes generated in Open Notebook.",
            "language": "en",
            "has_artwork": False,
            "artwork_version": None,
        }

    def test_the_feed_uses_the_defaults_until_edited(self, client, db):
        ch = channel(client)

        assert ch.findtext("title") == "Open Notebook Podcasts"
        assert ch.findtext(f"{ITUNES}author") == "Open Notebook"
        assert ch.find(f"{ITUNES}image") is None


class TestEditingShowMetadata:
    def test_edits_are_stored_returned_and_appear_in_the_feed(self, client, db):
        response = client.put(
            SETTINGS,
            json={
                "title": "Dan's Lab Radio",
                "author": "Dan",
                "description": "Notes from the lab.",
                "language": "pt-BR",
            },
            headers=AUTH,
        )

        assert response.status_code == 200
        assert response.json()["title"] == "Dan's Lab Radio"
        assert client.get(SETTINGS, headers=AUTH).json()["language"] == "pt-BR"
        ch = channel(client)
        assert ch.findtext("title") == "Dan's Lab Radio"
        assert ch.findtext(f"{ITUNES}author") == "Dan"
        assert ch.findtext("description") == "Notes from the lab."
        assert ch.findtext("language") == "pt-BR"

    def test_a_field_left_out_keeps_its_value(self, client, db):
        client.put(SETTINGS, json={"title": "Lab Radio", "author": "Dan"}, headers=AUTH)

        client.put(SETTINGS, json={"author": "Daniel"}, headers=AUTH)

        body = client.get(SETTINGS, headers=AUTH).json()
        assert (body["title"], body["author"]) == ("Lab Radio", "Daniel")

    def test_a_blank_value_goes_back_to_the_default(self, client, db):
        client.put(SETTINGS, json={"title": "Lab Radio"}, headers=AUTH)

        client.put(SETTINGS, json={"title": "   "}, headers=AUTH)

        assert (
            client.get(SETTINGS, headers=AUTH).json()["title"]
            == "Open Notebook Podcasts"
        )

    def test_values_are_trimmed(self, client, db):
        client.put(
            SETTINGS,
            json={"title": "  Lab Radio \n", "language": " en-GB "},
            headers=AUTH,
        )

        body = client.get(SETTINGS, headers=AUTH).json()
        assert (body["title"], body["language"]) == ("Lab Radio", "en-GB")

    def test_markup_in_text_cannot_break_the_feed(self, client, db):
        client.put(SETTINGS, json={"title": 'A & B <script>"x"</script>'}, headers=AUTH)

        assert channel(client).findtext("title") == 'A & B <script>"x"</script>'

    @pytest.mark.parametrize(
        "body,keyword",
        [
            ({"title": "t" * 256}, "title"),
            ({"author": "a" * 256}, "author"),
            ({"description": "d" * 4001}, "description"),
            ({"language": "english"}, "language"),
            ({"language": "en_US"}, "language"),
            ({"language": "e"}, "language"),
        ],
    )
    def test_invalid_values_are_refused_with_the_field_named(
        self, client, db, body, keyword
    ):
        response = client.put(SETTINGS, json=body, headers=AUTH)

        assert response.status_code == 400
        assert keyword in response.json()["detail"].lower()

    def test_limits_are_inclusive(self, client, db):
        response = client.put(
            SETTINGS,
            json={
                "title": "t" * 255,
                "author": "a" * 255,
                "description": "d" * 4000,
                "language": "zh-Hans-CN",
            },
            headers=AUTH,
        )

        assert response.status_code == 200

    def test_a_refused_edit_changes_nothing(self, client, db):
        client.put(SETTINGS, json={"title": "Before"}, headers=AUTH)

        response = client.put(
            SETTINGS, json={"title": "After", "language": "nope!"}, headers=AUTH
        )

        assert response.status_code == 400
        assert client.get(SETTINGS, headers=AUTH).json()["title"] == "Before"


class TestArtworkUpload:
    def test_a_square_png_is_accepted_and_goes_in_the_feed(self, client, db, tmp_path):
        response = upload(client, image_bytes("PNG", (1400, 1400)))

        assert response.status_code == 200
        body = response.json()
        assert body["has_artwork"] is True and body["artwork_version"]
        assert (tmp_path / "feed" / "artwork.png").read_bytes() == image_bytes(
            "PNG", (1400, 1400)
        )
        image = channel(client).find(f"{ITUNES}image")
        assert image is not None
        assert image.attrib["href"] == (
            f"{PUBLIC_URL}/api/podcasts/feed/{TOKEN}/artwork.png?v={body['artwork_version']}"
        )

    def test_a_square_jpeg_at_the_top_of_the_range_is_accepted(
        self, client, db, tmp_path
    ):
        response = upload(
            client, image_bytes("JPEG", (3000, 3000)), "cover.jpg", "image/jpeg"
        )

        assert response.status_code == 200
        assert (tmp_path / "feed" / "artwork.jpg").exists()
        href = channel(client).find(f"{ITUNES}image").attrib["href"]  # type: ignore[union-attr]
        assert "/artwork.jpg?v=" in href

    def test_the_format_comes_from_the_file_not_its_name(self, client, db, tmp_path):
        upload(client, image_bytes("JPEG", (1500, 1500)), "cover.png", "image/png")

        assert (tmp_path / "feed" / "artwork.jpg").exists()
        assert not (tmp_path / "feed" / "artwork.png").exists()

    @pytest.mark.parametrize("size", [(1400, 1400), (3000, 3000)])
    def test_both_ends_of_the_size_range_are_accepted(self, client, db, size):
        assert upload(client, image_bytes("PNG", size)).status_code == 200

    @pytest.mark.parametrize("size", [(1399, 1399), (3001, 3001)])
    def test_one_pixel_outside_the_range_is_refused(self, client, db, size):
        assert upload(client, image_bytes("PNG", size)).status_code == 400

    def test_replacing_artwork_removes_the_old_file_and_changes_the_url(
        self, client, db, tmp_path
    ):
        first = upload(client, image_bytes("PNG", (1400, 1400), "navy")).json()
        second = upload(
            client, image_bytes("JPEG", (1600, 1600), "red"), "c.jpg", "image/jpeg"
        ).json()

        assert not (tmp_path / "feed" / "artwork.png").exists()
        assert (tmp_path / "feed" / "artwork.jpg").exists()
        assert first["artwork_version"] != second["artwork_version"]

    def test_same_format_replacement_overwrites_in_place(self, client, db, tmp_path):
        upload(client, image_bytes("PNG", (1400, 1400), "navy"))
        upload(client, image_bytes("PNG", (1500, 1500), "red"))

        assert (tmp_path / "feed" / "artwork.png").read_bytes() == image_bytes(
            "PNG", (1500, 1500), "red"
        )
        assert [p.name for p in (tmp_path / "feed").iterdir()] == ["artwork.png"]


def _corrupt_png():
    return image_bytes("PNG", (1400, 1400))[:200]  # valid header, cut off


REFUSALS = {
    "text_file": (b"just some text, not an image", "not a png or jpeg"),
    "gif": (image_bytes("GIF", (1400, 1400)), "got gif"),
    "not_square": (image_bytes("PNG", (1400, 1500)), "square"),
    "too_small": (image_bytes("PNG", (800, 800)), "at least 1400"),
    "too_large": (image_bytes("PNG", (3200, 3200)), "at most 3000"),
    "empty": (b"", "empty"),
    "over_10mb": (b"\x89PNG\r\n\x1a\n" + b"0" * (10 * 1024 * 1024 + 1), "10 mb"),
    "truncated": (_corrupt_png(), "could not read"),
}


class TestArtworkRefusals:
    @pytest.mark.parametrize("case", REFUSALS)
    def test_refused_with_a_clear_400(self, client, db, case):
        data, keyword = REFUSALS[case]

        response = upload(client, data)

        assert response.status_code == 400
        assert keyword in response.json()["detail"].lower()

    def test_every_refusal_has_its_own_message(self, client, db):
        details = [
            upload(client, data).json()["detail"] for data, _ in REFUSALS.values()
        ]

        assert len(set(details)) == len(REFUSALS)

    @pytest.mark.parametrize("case", REFUSALS)
    def test_a_refused_upload_stores_nothing(self, client, db, tmp_path, case):
        upload(client, REFUSALS[case][0])

        assert not (tmp_path / "feed").exists()
        assert not client.get(SETTINGS, headers=AUTH).json()["has_artwork"]

    def test_a_refused_upload_keeps_the_existing_artwork(self, client, db, tmp_path):
        good = upload(client, image_bytes("PNG", (1400, 1400))).json()

        upload(client, REFUSALS["not_square"][0])

        assert (
            client.get(SETTINGS, headers=AUTH).json()["artwork_version"]
            == good["artwork_version"]
        )
        assert (tmp_path / "feed" / "artwork.png").exists()

    def test_a_request_without_a_file_is_refused(self, client, db):
        response = client.post(ARTWORK, headers=AUTH)

        assert response.status_code == 422


class TestArtworkRoutes:
    def test_the_feed_artwork_url_serves_the_image_to_a_podcast_app(self, client, db):
        data = image_bytes("PNG", (1400, 1400))
        upload(client, data)
        href = channel(client).find(f"{ITUNES}image").attrib["href"]  # type: ignore[union-attr]

        response = client.get(href.removeprefix(PUBLIC_URL))  # no password: token only

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.headers["content-length"] == str(len(data))
        assert response.content == data

    def test_jpeg_is_served_as_jpeg(self, client, db):
        upload(client, image_bytes("JPEG", (1400, 1400)), "c.jpg", "image/jpeg")

        response = client.get(f"/api/podcasts/feed/{TOKEN}/artwork.jpg")

        assert response.headers["content-type"] == "image/jpeg"

    def test_head_works(self, client, db):
        data = image_bytes("PNG", (1400, 1400))
        upload(client, data)

        head = client.head(f"/api/podcasts/feed/{TOKEN}/artwork.png")

        assert head.status_code == 200
        assert head.headers["content-length"] == str(len(data))
        assert head.content == b""

    def test_the_app_can_preview_the_artwork_with_its_password(self, client, db):
        data = image_bytes("PNG", (1400, 1400))
        upload(client, data)

        response = client.get(ARTWORK, headers=AUTH)

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.content == data

    def test_previewing_with_no_artwork_is_a_404(self, client, db):
        assert client.get(ARTWORK, headers=AUTH).status_code == 404

    @pytest.mark.parametrize(
        "path",
        [
            "/api/podcasts/feed/not-the-token/artwork.png",
            f"/api/podcasts/feed/{TOKEN}/artwork.jpg",  # stored one is png
            f"/api/podcasts/feed/{TOKEN}/artwork.gif",
        ],
    )
    def test_every_miss_is_the_one_uniform_404(self, client, db, path):
        upload(client, image_bytes("PNG", (1400, 1400)))

        response = client.get(path)

        assert response.status_code == 404
        assert response.json() == NOT_FOUND

    @pytest.mark.parametrize("name", ["artwork", "cover.png", "artwork.png.bak"])
    def test_other_file_names_match_no_route(self, client, db, name):
        # These never reach the token check, so there is nothing to probe.
        upload(client, image_bytes("PNG", (1400, 1400)))

        assert client.get(f"/api/podcasts/feed/{TOKEN}/{name}").status_code == 404

    def test_a_huge_image_header_is_refused_before_anything_is_decoded(
        self, client, db
    ):
        # 15000 x 15000 one-bit PNG: tiny file, 225 million pixels (Pillow's bomb limit).
        buffer = io.BytesIO()
        Image.new("1", (15000, 15000)).save(buffer, format="PNG")

        response = upload(client, buffer.getvalue())

        assert response.status_code == 400
        assert "at most 3000" in response.json()["detail"].lower()

    def test_no_artwork_yet_is_the_same_404(self, client, db):
        response = client.get(f"/api/podcasts/feed/{TOKEN}/artwork.png")

        assert response.status_code == 404
        assert response.json() == NOT_FOUND

    def test_a_file_that_vanished_from_disk_is_the_same_404_and_leaves_the_feed_intact(
        self, client, db, tmp_path
    ):
        upload(client, image_bytes("PNG", (1400, 1400)))
        (tmp_path / "feed" / "artwork.png").unlink()

        assert client.get(f"/api/podcasts/feed/{TOKEN}/artwork.png").json() == NOT_FOUND
        assert (
            channel(client).find(f"{ITUNES}image") is None
        )  # never advertise a dead URL
