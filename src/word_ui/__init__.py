"""UI workspace APIs for chat-first document operations."""

from .preview import DocxPreviewRenderer, PreviewRenderError
from .workspace import WordUIWorkspace

__all__ = ["DocxPreviewRenderer", "PreviewRenderError", "WordUIWorkspace"]
