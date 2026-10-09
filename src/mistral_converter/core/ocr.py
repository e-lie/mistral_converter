import base64
import os
from pathlib import Path

from mistralai.client import Mistral


def ocr_document(source: Path) -> tuple[Path, Path]:
    """Run Mistral OCR on a PDF and write the response JSON and Markdown next to it."""
    client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])

    base64_file = base64.b64encode(source.read_bytes()).decode("utf-8")
    response = client.ocr.process(
        document={
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{base64_file}",
        },
        model="mistral-ocr-latest",
        include_image_base64=True,
        include_blocks=True,
    )

    json_path = source.with_suffix(".ocr.json")
    md_path = source.with_suffix(".md")
    json_path.write_text(response.model_dump_json(indent=2), encoding="utf-8")
    md_path.write_text(
        "\n\n".join(page.markdown for page in response.pages), encoding="utf-8"
    )
    return json_path, md_path
