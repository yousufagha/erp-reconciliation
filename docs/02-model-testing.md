# Testing the model path on your Mac

**Outcome:** measure how well a free model reads the documents that have no text layer
(phone photos, scanner batches), against the same answers as everything else, so a paid
model is proposed on evidence.

**Cost:** free. Gemini API free tier (Google), Tesseract (Apache 2.0), everything else open
source. The free tier's terms say Google uses submitted content to improve its products and
that you should not submit confidential information. Use it on `corpus/` only, never on
client paperwork.

**Why on the Mac:** the cloud workspace this was built in cannot reach Google's API or
download models (its network allowlist blocks them).

Install and check one thing at a time. Stop at any step that does not produce the check
shown, rather than debugging further.

## 1. Python environment

```bash
cd ~/code/erp-reconciliation
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -e ".[dev,gemini]"
pytest -q
```

Check: `37 passed, 6 skipped` (the six that need Tesseract wait for step 2).

## 2. Tesseract (the independent reading used for grounding)

```bash
brew install tesseract
uv pip install -e ".[ocr]"        # the Python wrapper, pytesseract
tesseract --version
pytest -q
```

Check: a version prints and `pytest -q` shows `43 passed`. Without Tesseract every model reading is
held, by design: a value that cannot be found on the page is never accepted.

## 3. Gemini key

Create a key in Google AI Studio (https://aistudio.google.com) with your Google account, then:

```bash
export GEMINI_API_KEY="paste-key-here"
pile read corpus/synthetic/scenario_aug2026 -o /tmp/one.json && grep -c '"model_read": true' /tmp/one.json
```

Check: a number above zero. If the call fails, the documents are held with the error in
their notes (`model call failed ...`) and nothing is passed off as read. Open
`/tmp/one.json` and search for `model call failed` to see the reason.

The SDK call in `src/pile/model_read.py` was written from Google's documentation and checked
against the installed SDK's source (google-genai 2.25: `client.interactions.create(model=,
input=, response_format=)`, `output_text`), but it has never been run against the API; this
step is its first live run. Free-tier request limits are shown in
AI Studio, not in Google's docs.

## 4. The evaluation

```bash
pile eval corpus/synthetic/scenario_aug2026 corpus/public/invoice2data \
  --json results/$(date +%F)-gemini.json > results/$(date +%F)-gemini.txt
git add results && git commit -m "Gemini free tier evaluation"
```

Compare with `results/2026-09-26-no-model.txt`. What to look at:

- `image_photo`, `pdf_scan` and `image` rows under "by format": the documents only the model can read
- `gate:` line: how much it let through and how much of that was right
- `reconciliation:` precision: the no-model run over-reports goods owed because three
  delivery records sit in unread images; a working model path should close that gap

To try a different model: `export PILE_MODEL=gemini-3.5-flash-lite` and rerun step 4.

Calls are spaced 5 seconds apart and abandoned after 90 seconds (`PILE_MODEL_MIN_INTERVAL`,
`PILE_MODEL_TIMEOUT`). Refused calls (HTTP 429, 500, 503) are retried up to three times with
backoff. Any call that still fails is listed under "model calls failed" in the evaluation
output, and its document is held, never passed off as read.

First live run (26 Sep): the phone photos read 100%; the scanned batch and the public PNGs
failed during the long run but the scan read fine on its own the next day, which points to
the free tier's per-minute limit. Pacing was added after that run.
