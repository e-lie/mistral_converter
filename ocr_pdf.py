import base64
import os
import sys
from pathlib import Path

from mistralai.client import Mistral


def main():
    pdf_path = Path(sys.argv[1])
    client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])

    base64_file = base64.b64encode(pdf_path.read_bytes()).decode("utf-8")
    response = client.ocr.process(
        document={
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{base64_file}",
        },
        model="mistral-ocr-latest",
        include_image_base64=True,
        include_blocks=True,
    )

    json_path = pdf_path.with_suffix(".ocr.json")
    md_path = pdf_path.with_suffix(".md")
    json_path.write_text(response.model_dump_json(indent=2), encoding="utf-8")
    md_path.write_text(
        "\n\n".join(page.markdown for page in response.pages), encoding="utf-8"
    )
    print(f"{json_path}\n{md_path}")


if __name__ == "__main__":
    main()
