# Usage: make <ocr|fix|epub|convert> PDF=path/to/book.pdf [ARGS="--title ..."]
RUN = uv run --env-file .env mistral-converter
OCR_JSON = $(PDF:.pdf=.ocr.json)

.PHONY: ocr fix epub convert

ocr:
	@test -n "$(PDF)" || { echo "PDF is required"; exit 1; }
	$(RUN) ocr "$(PDF)"

fix:
	@test -n "$(PDF)" || { echo "PDF is required"; exit 1; }
	$(RUN) fix "$(OCR_JSON)" $(ARGS)

epub:
	@test -n "$(PDF)" || { echo "PDF is required"; exit 1; }
	$(RUN) epub "$(OCR_JSON)" $(ARGS)

convert:
	@test -n "$(PDF)" || { echo "PDF is required"; exit 1; }
	$(RUN) convert "$(PDF)" $(ARGS)
