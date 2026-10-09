import base64
import os
from typing import Protocol

from mistralai.client import Mistral


class MistralApi(Protocol):
    """The Mistral calls the converter relies on; replaceable in tests."""

    def ocr(self, pdf: bytes) -> dict:
        """OCR response of a PDF, as a JSON-compatible dict."""

    def chat_json(self, model: str, prompt: str) -> str:
        """Raw JSON text answered by a chat model."""


class MistralClient:
    def __init__(self, api_key: str | None = None):
        self._client = Mistral(api_key=api_key or os.environ["MISTRAL_API_KEY"])

    def ocr(self, pdf: bytes) -> dict:
        response = self._client.ocr.process(
            document={
                "type": "document_url",
                "document_url": f"data:application/pdf;base64,{base64.b64encode(pdf).decode('utf-8')}",
            },
            model="mistral-ocr-latest",
            include_image_base64=True,
            include_blocks=True,
        )
        return response.model_dump(mode="json")

    def chat_json(self, model: str, prompt: str) -> str:
        response = self._client.chat.complete(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content
