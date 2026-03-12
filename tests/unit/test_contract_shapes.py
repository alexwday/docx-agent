from __future__ import annotations

from docx import Document


def test_success_and_error_shape(make_service, tmp_path):
    service = make_service(tmp_path)
    target = tmp_path / "shape.docx"
    Document().save(str(target))

    ok_result = service.get_document_info(str(target))
    assert ok_result["status"] == "ok"
    assert ok_result["contract_version"] == "v1"

    error_result = service.get_document_info(str(tmp_path / "missing.docx"))
    assert error_result["status"] == "error"
    assert error_result["contract_version"] == "v1"
    assert "error_code" in error_result
    assert "message" in error_result


def test_save_as(make_service, tmp_path):
    service = make_service(tmp_path)
    source = tmp_path / "source.docx"
    out = tmp_path / "out.docx"
    Document().save(str(source))

    result = service.save_as(str(source), str(out))
    assert result["status"] == "ok"
    assert out.exists()
