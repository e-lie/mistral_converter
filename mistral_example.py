import base64
import os
from mistralai.client import Mistral

api_key = os.environ["MISTRAL_API_KEY"]

client = Mistral(api_key=api_key)

def encode_file(file_path):
    with open(file_path, "rb") as pdf_file:
        return base64.b64encode(pdf_file.read()).decode('utf-8')

file_path = "path/to/Du mode dexistence des objets techniques (Gilbert Simondon) (z-library.sk, 1lib.sk, z-lib.sk).pdf"
base64_file = encode_file(file_path)

ocr_response = client.ocr.process(
    document={
      "type": "document_url",
      "document_url": f"data:application/pdf;base64,{base64_file}"
    },
    model="mistral-ocr-latest",
	include_image_base64=True,
	include_blocks=True
)
