# Repository rules

Before evaluation changes, read `R&D_COMPLIANCE.md` and follow its source-document priority.

V6.2 is frozen. Never retrain it, change boundary logic or prototype clustering,
regenerate its output, or modify approved artifacts without explicit user instruction.
Approved counts: 32,273 events; 5,167 latent segments; 563 latent workflows;
1,619 process instances; 12 process models.

Ground Truth is evaluation-only. Never pass it to a model, generator, or training job.
Missing evidence must not become a zero score or a fabricated successful result.
Failed execution attempts remain in the denominator. Auxiliary process evidence
must never automatically count as a direct match.

Run `python3 -m unittest discover -s tests -v` after evaluation/backend changes.
Use only temporary synthetic fixtures in tests, never as official KTL evidence.

## Data Policy

The datasets under `data/reference/v6_2_source/` are historical reference data
used to reproduce and validate the approved V6.2 model.

They are NOT the default input for future model training or evaluation.

Future model training and inference must assume that new CSV datasets
will be supplied under `data/training/raw/`.

Do not hard-code logic against the current V6.2 source dataset.

All loaders, preprocessing pipelines, and inference APIs must support
new incoming CSV datasets that follow the defined schema.