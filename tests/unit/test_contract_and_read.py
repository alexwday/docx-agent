from __future__ import annotations

from docx import Document

from tests.unit.helpers import build_sample_document


def test_create_document_and_get_info(make_service, tmp_path):
    service = make_service(tmp_path)
    target = tmp_path / "created.docx"

    created = service.create_document(str(target), title="Demo", author="Agent")
    assert created["status"] == "ok"
    assert created["contract_version"] == "v1"

    info = service.get_document_info(str(target))
    assert info["status"] == "ok"
    assert info["metadata"]["title"] == "Demo"
    assert info["metadata"]["author"] == "Agent"


def test_outline_and_find_text(make_service, tmp_path):
    service = make_service(tmp_path)
    target = tmp_path / "outline.docx"
    build_sample_document(target)

    outline = service.get_document_outline(str(target))
    assert outline["status"] == "ok"
    assert [item["text"] for item in outline["headings"]] == ["Section A", "Section B"]

    found = service.find_text(str(target), "Instruction", match_case=True, whole_word=False)
    assert found["status"] == "ok"
    assert found["total_matches"] == 3


def test_get_paragraph_text_range_error(make_service, tmp_path):
    service = make_service(tmp_path)
    target = tmp_path / "range.docx"
    build_sample_document(target)

    result = service.get_paragraph_text(str(target), 999)
    assert result["status"] == "error"
    assert result["error_code"] == "PARAGRAPH_INDEX_OUT_OF_RANGE"


def test_list_available_documents(make_service, tmp_path):
    service = make_service(tmp_path)
    doc1 = tmp_path / "a.docx"
    doc2 = tmp_path / "b.docx"
    Document().save(str(doc1))
    Document().save(str(doc2))

    listed = service.list_available_documents(str(tmp_path))
    assert listed["status"] == "ok"
    assert len(listed["files"]) == 2
