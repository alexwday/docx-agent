from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from tests.unit.helpers import build_sample_document, paragraph_texts


def test_insert_and_delete_paragraphs(make_service, tmp_path):
    service = make_service(tmp_path)
    target = tmp_path / "edit.docx"
    build_sample_document(target)

    inserted = service.insert_paragraphs(
        str(target),
        after_paragraph_index=1,
        paragraphs=[{"text": "Inserted one"}, {"text": "Inserted two"}],
    )
    assert inserted["status"] == "ok"
    assert inserted["inserted_count"] == 2

    deleted = service.delete_paragraph_range(str(target), 2, 3)
    assert deleted["status"] == "ok"
    assert deleted["deleted_count"] == 2


def test_search_and_replace_limit(make_service, tmp_path):
    service = make_service(tmp_path)
    target = tmp_path / "replace.docx"
    build_sample_document(target)

    replaced = service.search_and_replace(
        str(target),
        find_text="Instruction",
        replace_text="Generated",
        max_replacements=2,
    )
    assert replaced["status"] == "ok"
    assert replaced["replacements"] == 2

    lines = paragraph_texts(target)
    assert any("Generated" in line for line in lines)


def test_concurrency_locking_insert(make_service, tmp_path):
    service = make_service(tmp_path)
    target = tmp_path / "concurrent.docx"
    build_sample_document(target)

    def worker(text: str):
        return service.insert_paragraphs(
            str(target),
            after_paragraph_index=1,
            paragraphs=[{"text": text}],
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(worker, "T1 line").result()
        second = executor.submit(worker, "T2 line").result()

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    lines = paragraph_texts(target)
    assert "T1 line" in lines
    assert "T2 line" in lines
