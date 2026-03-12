"""Word MCP server runtime and tool registration."""

from __future__ import annotations

from typing import Any

from word_engine import WordDocumentService

try:
    from fastmcp import FastMCP
except ImportError:  # pragma: no cover
    FastMCP = None


SERVICE = WordDocumentService()


def _create_mcp() -> Any:
    if FastMCP is None:
        raise RuntimeError(
            "fastmcp is not installed. Install optional dependency with: pip install -e '.[mcp]'"
        )

    mcp = FastMCP("docx-agent-word-mcp-server")

    @mcp.tool()
    def create_document(
        file_path: str,
        template_path: str | None = None,
        title: str | None = None,
        author: str | None = None,
    ) -> dict[str, Any]:
        return SERVICE.create_document(file_path, template_path, title, author)

    @mcp.tool()
    def copy_document(source_path: str, destination_path: str | None = None) -> dict[str, Any]:
        return SERVICE.copy_document(source_path, destination_path)

    @mcp.tool()
    def get_document_info(file_path: str) -> dict[str, Any]:
        return SERVICE.get_document_info(file_path)

    @mcp.tool()
    def get_document_outline(file_path: str) -> dict[str, Any]:
        return SERVICE.get_document_outline(file_path)

    @mcp.tool()
    def get_paragraph_text(file_path: str, paragraph_index: int) -> dict[str, Any]:
        return SERVICE.get_paragraph_text(file_path, paragraph_index)

    @mcp.tool()
    def find_text(
        file_path: str,
        query: str,
        match_case: bool = False,
        whole_word: bool = False,
    ) -> dict[str, Any]:
        return SERVICE.find_text(file_path, query, match_case, whole_word)

    @mcp.tool()
    def insert_paragraphs(
        file_path: str,
        after_paragraph_index: int,
        paragraphs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return SERVICE.insert_paragraphs(file_path, after_paragraph_index, paragraphs)

    @mcp.tool()
    def delete_paragraph_range(file_path: str, start_index: int, end_index: int) -> dict[str, Any]:
        return SERVICE.delete_paragraph_range(file_path, start_index, end_index)

    @mcp.tool()
    def search_and_replace(
        file_path: str,
        find_text: str,
        replace_text: str,
        max_replacements: int | None = None,
    ) -> dict[str, Any]:
        return SERVICE.search_and_replace(file_path, find_text, replace_text, max_replacements)

    @mcp.tool()
    def replace_section_content(
        file_path: str,
        selector: dict[str, Any],
        new_paragraphs: list[str | dict[str, Any]],
        preserve_style: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        return SERVICE.replace_section_content(
            file_path=file_path,
            selector=selector,
            new_paragraphs=new_paragraphs,
            preserve_style=preserve_style,
            dry_run=dry_run,
        )

    @mcp.tool()
    def save_as(file_path: str, output_path: str) -> dict[str, Any]:
        return SERVICE.save_as(file_path, output_path)

    @mcp.tool()
    def convert_to_pdf(file_path: str, output_path: str | None = None) -> dict[str, Any]:
        return SERVICE.convert_to_pdf(file_path, output_path)

    @mcp.tool()
    def get_document_comments(file_path: str) -> dict[str, Any]:
        return SERVICE.get_document_comments(file_path)

    @mcp.tool()
    def get_document_footnotes(file_path: str) -> dict[str, Any]:
        return SERVICE.get_document_footnotes(file_path)

    @mcp.tool()
    def list_available_documents(directory: str = ".") -> dict[str, Any]:
        return SERVICE.list_available_documents(directory)

    return mcp


def main() -> None:
    mcp = _create_mcp()
    mcp.run()


if __name__ == "__main__":
    main()
