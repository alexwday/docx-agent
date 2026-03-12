"""Main orchestration workflows for section planning and application."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import openai
from docx import Document

from word_engine import WordDocumentService

logger = logging.getLogger(__name__)


class WordAgent:
    """Template fill orchestration using the local DOCX engine."""

    def __init__(
        self,
        service: WordDocumentService | None = None,
        model: str = "gpt-4.1",
        api_key: str | None = None,
    ) -> None:
        self.service = service or WordDocumentService()
        self.model = model
        self._client = openai.OpenAI(api_key=api_key)

    # ── LLM helpers ──────────────────────────────────────────────────

    def _llm_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
    ) -> str | None:
        """Call the OpenAI chat completions API. Returns text or None on error."""
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
            )
            return response.choices[0].message.content
        except Exception:
            logger.exception("OpenAI API call failed")
            return None

    def _read_docx_text(self, file_path: str, max_chars: int = 8000) -> str:
        """Read raw text from a .docx file, truncated to max_chars."""
        try:
            doc = Document(file_path)
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            return text[:max_chars]
        except Exception:
            return ""

    # ── Core workflows ───────────────────────────────────────────────

    def plan_template_fill(
        self,
        target_doc: str,
        support_docs: list[str],
        objective: str,
    ) -> dict[str, Any]:
        outline_response = self.service.get_document_outline(target_doc)
        if outline_response["status"] != "ok":
            return {
                "status": "error",
                "contract_version": outline_response["contract_version"],
                "error_code": outline_response.get("error_code"),
                "message": outline_response.get("message"),
            }

        headings = outline_response["headings"]

        # Try LLM-generated per-section instructions
        llm_instructions = self._generate_plan_instructions(headings, objective)

        section_plan = []
        for i, heading in enumerate(headings):
            instruction = (
                llm_instructions[i]
                if llm_instructions and i < len(llm_instructions)
                else f"{objective} for section '{heading['text']}'"
            )
            section_plan.append(
                {
                    "heading_text": heading["text"],
                    "selector": {
                        "mode": "heading_exact",
                        "value": heading["text"],
                        "occurrence": 1,
                    },
                    "instruction": instruction,
                }
            )

        return {
            "status": "ok",
            "contract_version": outline_response["contract_version"],
            "section_plan": section_plan,
            "support_docs": support_docs,
            "objective": objective,
        }

    def _generate_plan_instructions(
        self,
        headings: list[dict[str, Any]],
        objective: str,
    ) -> list[str] | None:
        """Ask the LLM to produce a specific instruction per heading. Returns None on failure."""
        heading_list = "\n".join(f"- {h['text']}" for h in headings)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a document planning assistant. Given an objective and a list of "
                    "section headings, produce one specific content instruction per section. "
                    "Return ONLY the instructions, one per line, in the same order as the headings. "
                    "No numbering, no heading names, just the instruction text."
                ),
            },
            {
                "role": "user",
                "content": f"Objective: {objective}\n\nSection headings:\n{heading_list}",
            },
        ]
        text = self._llm_chat(messages, temperature=0.4)
        if text is None:
            return None
        lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
        if len(lines) != len(headings):
            # Mismatch — fall back
            return None
        return lines

    def generate_section_content(
        self,
        section_plan_item: dict[str, Any],
        context_bundle: dict[str, Any],
    ) -> dict[str, Any]:
        objective = context_bundle.get("objective", "Generate concise content")
        heading = section_plan_item.get("heading_text", "Section")
        instruction = section_plan_item.get("instruction", objective)
        support_docs = context_bundle.get("support_docs", [])

        # Gather support doc context
        context_text = ""
        for doc_path in support_docs:
            snippet = self._read_docx_text(doc_path)
            if snippet:
                name = Path(doc_path).name
                context_text += f"\n--- {name} ---\n{snippet}\n"

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a professional document content writer. Write clear, well-structured "
                    "content for a specific section of a document. Output ONLY the body paragraphs "
                    "(no heading). Separate distinct paragraphs with a blank line."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Document objective: {objective}\n"
                    f"Section heading: {heading}\n"
                    f"Specific instruction: {instruction}\n"
                    + (f"\nReference material:\n{context_text}" if context_text else "")
                    + "\n\nWrite the content for this section now."
                ),
            },
        ]

        text = self._llm_chat(messages, temperature=0.7)
        if text is None:
            # Fallback to stub behavior
            refs = (
                ", ".join(Path(item).name for item in support_docs)
                if support_docs
                else "no external docs"
            )
            paragraphs = [
                f"{heading}: {objective}.",
                f"Draft generated using {refs}.",
                "Review and refine wording for final publication.",
            ]
            return {
                "status": "ok",
                "contract_version": "v1",
                "paragraphs": paragraphs,
            }

        # Split LLM output into paragraphs on blank lines
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [text.strip()]

        return {
            "status": "ok",
            "contract_version": "v1",
            "paragraphs": paragraphs,
        }

    def generate_session_title(self, user_messages: list[str]) -> str | None:
        """Generate a short 3-8 word session title from the first user messages.

        Returns None on failure so callers can silently skip.
        """
        combined = "\n".join(user_messages[:3])
        messages = [
            {
                "role": "system",
                "content": (
                    "Generate a short title (3-8 words) that summarizes the topic of this conversation. "
                    "Return ONLY the title text, no quotes, no punctuation at the end, no explanation."
                ),
            },
            {
                "role": "user",
                "content": combined,
            },
        ]
        title = self._llm_chat(messages, temperature=0.3)
        if title is None:
            return None
        title = title.strip().strip('"').strip("'").rstrip(".")
        if not title or len(title) > 100:
            return None
        return title

    def chat(self, messages: list[dict[str, str]], system_context: str = "") -> str:
        """LLM chat completion for conversational responses."""
        system_msg = (
            "You are a helpful document assistant called WordAgent. You help users create, "
            "edit, and manage Word documents. Be concise and friendly."
        )
        if system_context:
            system_msg += f"\n\nCurrent session context:\n{system_context}"

        llm_messages: list[dict[str, str]] = [{"role": "system", "content": system_msg}]
        llm_messages.extend(messages)

        text = self._llm_chat(llm_messages, temperature=0.7)
        if text is None:
            return "I'm having trouble connecting to the language model right now. Please try again shortly."
        return text

    def apply_section_plan(self, target_doc: str, section_plan: list[dict[str, Any]]) -> dict[str, Any]:
        applied = []
        failed = []
        for item in section_plan:
            content = item.get("paragraphs", [])
            result = self.service.replace_section_content(
                file_path=target_doc,
                selector=item["selector"],
                new_paragraphs=content,
                preserve_style=True,
                dry_run=False,
            )
            if result["status"] == "ok":
                applied.append({"heading_text": item.get("heading_text"), "result": result})
            else:
                failed.append({"heading_text": item.get("heading_text"), "result": result})

        status = "ok" if not failed else "error"
        return {
            "status": status,
            "contract_version": "v1",
            "applied_count": len(applied),
            "failed_count": len(failed),
            "applied": applied,
            "failed": failed,
        }

    def validate_document_result(self, target_doc: str, expected_sections: list[str]) -> dict[str, Any]:
        outline_response = self.service.get_document_outline(target_doc)
        if outline_response["status"] != "ok":
            return outline_response

        headings = {item["text"] for item in outline_response["headings"]}
        missing = [section for section in expected_sections if section not in headings]
        return {
            "status": "ok" if not missing else "error",
            "contract_version": "v1",
            "missing_sections": missing,
            "all_expected_present": not missing,
        }
