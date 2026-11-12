# Track B — M06 frozen-output web development

Development complete; independent Verification pending. This is not a final model freeze or official measurement.

## Scope and source

Read repository AGENTS.md, R&D_COMPLIANCE.md and FINAL PDF p.10 directly via PDFKit. FINAL specifies engine workflow embeddings and cluster labels, Euclidean Si/Mij DBI, sklearn cross-check and DBI <=1.0. Historical OFFICIAL restrictions are stale relative to FINAL but were not changed: this task adds DEVELOPMENT only and preserves existing endpoints/default execution behavior.

Persisted source is /Users/sooeunkim/Documents/Codex/2026-11-03/task-5/MODEL-VAL-01. Byte-identical repository copies are under data/development/current_site_unseen_validation_v1/m06_frozen_output:

- predictions.json: 96a5cffd393ea47f478f27c7fda0e4a58b2dc00d6e409d8475e2385b22dbcc1a
- workflow_embeddings.npy (source unseen_workflow_embeddings.npy): 2c0e08051831498effbac58830bb8de3037dd1d779ae45eca18cb6144c352179

Manifest records both hashes, source paths and persisted order. NPY row i aligns with predictions.workflows[i].workflow_instance_id and predictions.cluster_labels[i]. No regeneration, label remapping or clustering. GT is not read by this module.

## Implementation / reproduction

backend/m06_candidate.py validates hashes, dimensions, unique workflow IDs and lengths, calls native M06Evaluator and sklearn on identical float64 values, and produces deterministic long-format CSV. The 1e-8 absolute/relative numeric tolerance is explicit: sklearn's pairwise Euclidean dot-product identity differs from direct math.dist by cancellation roundoff. Neither DBI is rounded for threshold comparison.

Existing POST /api/evaluations/m06/run?mode=DEVELOPMENT accepts the additive dataset_id=v1_2_1_unseen_m06_development. Missing dataset_id retains legacy runner behavior; REFERENCE/OFFICIAL paths unchanged. The DEVELOPMENT M06 page defaults to the frozen artifact selection, exposes counts/dimensions, formula, source hashes, sklearn result and evidence download; legacy selection is retained. Selecting frozen data never invokes EvaluationModelRunner.

CSV record types: workflow_coordinate (row_index, workflow_id, cluster, dimension, value), centroid_coordinate, cluster_pair (distance Mij and ratio), cluster_summary (Si, count, maximum ratio). This allows full recalculation from the CSV, not only mean(max_ratio). The result JSON retains compact summary rows to avoid rendering 49,977 rows in the browser. Evidence hash and record count appear in result/manifest. Original NPY dtype is converted to Python/float64 values consistently for both calculators.

## Actual DEVELOPMENT HTTP result

Run DEV-M06-20261105T093002-1954be1c5517 under results/development:

- workflows 22; dimensions 1152; clusters 21
- DBI 0.3182056481321067
- sklearn DBI 0.3182056530904802 (absolute difference 4.9583734895719545e-09)
- threshold <=1.0 met; official_pass=null
- 20 singleton clusters disclosed, without adding a new pass criterion
- evidence 49,977 rows; SHA256 d56963cdf45e8ae86284d2101939e9e5fb7f4004380c13742183711d78e6665e

A local ephemeral HTTP server received the actual POST and GET evidence.csv, both 200. Download bytes matched the result hash; CSV cluster_summary average exactly matched DBI. Script/log: /tmp/m06_webcheck.py and /tmp/m06_webcheck.log. The HTTP server was shut down after checking.

## Development tests

- python3 -m unittest discover -s tests -v: 274 tests PASS (18.365s), /tmp/m06_tests.log.
- node --check frontend/app.js: PASS.
- node tests/test_frontend.cjs: 24 mode/page DOM checks PASS, /tmp/m06_frontend.log.
- New temporary synthetic fixtures test deterministic calculation/CSV, numeric cross-check, evidence export hash, model runner never invoked, tamper/malformed bundle and duplicate-ID rejection. These fixtures are not KTL evidence.

No model weights, threshold, features, architecture, frozen source files or cluster labels were modified. No OFFICIAL result or ten-unit selection was created. Shared server/frontend updates preserve pre-existing M02 and concurrent M03 work.

## Independent Verification / integration caveats

1. Verify exact source copies/row order, full CSV coordinate reconstruction and centroid/Si/Mij/native/sklearn agreement, deterministic bytes, HTTP download/hash and nonofficial status. Native calculation uses generic dimensions/counts, no reference numbers hard-coded.
2. Review 1e-8 numerical tolerance and 20 singleton clusters as disclosed measurement context. No cluster tuning is authorized.
3. Shared backend/server.py is listed in the prior M02 frozen abstraction dependency manifest. Consequently M02 candidate readiness currently reports ERROR: Frozen abstraction dependency changed: backend/server.py. Do not bypass or rewrite that old freeze. Track A must validate its final combined dependencies as part of its authorized recovery verification. This task deliberately did not edit M02 contracts/manifests.
4. Existing OFFICIAL M06 provider/UI description still has historical V6.2 constraints; formal OFFICIAL contract migration is outside this DEVELOPMENT connection and requires coordinated approval. This result is not official readiness or a model freeze.
5. No full visual browser QA was performed; DOM rendering and actual HTTP/API/CSV were tested. Independent Verification remains pending.
