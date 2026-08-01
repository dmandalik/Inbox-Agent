"""Custom labels: store CRUD, assignment, auto-apply, and the API."""

from __future__ import annotations

import pytest

from inbox_agent.labeling import auto_apply
from inbox_agent.llm import LLMClient
from inbox_agent.models import Email
from inbox_agent.store import open_repository
from inbox_agent.summarize import Summarizer


def _email(mid, subject="hi", body="hello"):
    return Email(
        message_id=mid,
        thread_id="t-" + mid,
        date="2026-06-15T09:00:00+00:00",
        from_addr="a@x.example.com",
        from_name="Sender",
        subject=subject,
        body=body,
    )


# --- store --------------------------------------------------------------
def test_label_crud_and_assignment():
    repo = open_repository(":memory:")
    repo.add_many([_email("m1"), _email("m2")])
    repo.create_label("L1", "Finance", "#22aa55", "money and bills")

    assert repo.list_labels()[0]["name"] == "Finance"
    repo.set_email_label("m1", "L1", True)
    assert repo.labels_for("m1") == ["L1"]
    assert repo.label_counts() == {"L1": 1}

    repo.set_email_label("m1", "L1", False)
    assert repo.labels_for("m1") == []


def test_update_and_delete_label_cascades():
    repo = open_repository(":memory:")
    repo.add_many([_email("m1")])
    repo.create_label("L1", "Finance", "#22aa55", "money")
    repo.set_email_label("m1", "L1", True)

    repo.update_label("L1", name="Money", color="#000000")
    assert repo.get_label("L1")["name"] == "Money"

    repo.delete_label("L1")
    assert repo.get_label("L1") is None
    assert repo.labels_for("m1") == []  # assignment removed with the label


def test_update_unknown_label_raises():
    repo = open_repository(":memory:")
    with pytest.raises(KeyError):
        repo.update_label("nope", name="x")


# --- auto-apply ---------------------------------------------------------
class ScriptedLLM(LLMClient):
    model = "fake"

    def __init__(self, reply='["Finance"]'):
        self.reply = reply

    def complete(self, *, system, user, max_tokens=512):
        return self.reply


def test_auto_apply_assigns_matching_labels():
    repo = open_repository(":memory:")
    repo.add_many([_email("m1"), _email("m2")])
    repo.set_summary("m1", "an invoice is due")  # pre-seed so summarizer needs no LLM
    repo.set_summary("m2", "lunch tomorrow?")
    repo.create_label("L1", "Finance", "#22aa55", "money, bills, invoices")

    report = auto_apply(repo, ScriptedLLM('["Finance"]'), Summarizer(repo, ScriptedLLM()))
    assert report["labelled"] == 2
    assert repo.labels_for("m1") == ["L1"]


def test_auto_apply_noop_without_instructions():
    repo = open_repository(":memory:")
    repo.add_many([_email("m1")])
    repo.create_label("L1", "Finance", "#22aa55", "")  # no instructions
    report = auto_apply(repo, ScriptedLLM(), Summarizer(repo, ScriptedLLM()))
    assert report["labelled"] == 0


# --- API ----------------------------------------------------------------
fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from inbox_agent.config import get_settings  # noqa: E402
from inbox_agent.synthetic import generate_corpus  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "api.db"
    repo = open_repository(str(db))
    repo.add_many(generate_corpus())
    repo.close()
    monkeypatch.setenv("DB_PATH", str(db))
    get_settings.cache_clear()
    from inbox_agent import api

    monkeypatch.setattr(api, "_chat_client", lambda: ScriptedLLM('["Finance"]'))
    yield TestClient(api.app)
    get_settings.cache_clear()


def test_create_assign_and_filter_by_label(client):
    label = client.post("/api/labels", json={"name": "Finance", "color": "#22aa55"}).json()
    lid = label["id"]
    target = client.get("/api/emails").json()["emails"][0]["id"]
    client.post(f"/api/emails/{target}/labels", json={"label_id": lid, "on": True})

    listed = client.get("/api/emails", params={"label": lid}).json()
    assert listed["count"] == 1
    assert listed["emails"][0]["id"] == target
    assert lid in listed["emails"][0]["labels"]

    labels = client.get("/api/labels").json()["labels"]
    assert labels[0]["count"] == 1


def test_delete_label(client):
    lid = client.post("/api/labels", json={"name": "Temp"}).json()["id"]
    assert client.delete(f"/api/labels/{lid}").status_code == 200
    assert client.get("/api/labels").json()["labels"] == []


def test_apply_labels_endpoint_uses_instructions(client):
    client.post("/api/labels", json={"name": "Finance", "instructions": "money and bills"})
    r = client.post("/api/labels/apply")
    assert r.status_code == 200
    assert r.json()["labelled"] >= 1
