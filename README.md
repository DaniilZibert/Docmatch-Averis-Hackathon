# averis-hackaton — shipping document verification

From an operations inbox to a discrepancy report: classify every email, and for
document-check requests compare the draft **Bill of Lading** against the **Shipping
Instruction** it is supposed to match, flagging exactly which of the seven shipment
fields disagree — or escalating to a human when the documents cannot be read.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env          # add your ANTHROPIC_API_KEY

pytest -q                     # contract tests
python -m src.pipeline        # process all 520 emails -> submission.json
```

Scoring against the organizers' self-eval server (their docker bundle must be running):

```bash
python scripts/run_self_eval.py
```

## Layout

| path | what |
|---|---|
| `src/models.py` | the shared data contract between both work streams |
| `src/pipeline.py` | classify → extract → compare → `submission.json` |
| `src/classifier.py`, `src/extractor/` | email categorisation and field extraction |
| `src/normalize.py`, `src/comparator.py` | value normalisation and the SI/BL comparison |
| `src/api/`, `src/db/` | service layer, human-review queue |
| `data/` | the participant dataset: 520 emails, 250 SI/BL attachments |
| `docs/use-case.pdf` | the original problem statement |

## Working on this

Read **[CLAUDE.md](CLAUDE.md)** first — it holds the task description, the contract
rules, who owns which files, and the dataset facts worth knowing. The fuller plan
(architecture, AWS deployment, day-by-day schedule) lives in the Claude project
"hackaton" as `hackathon-plan.md` and `hackathon-tasks.md`.
