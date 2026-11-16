# M05 DB / Export Evidence Recovery

Task: M05-EVIDENCE-RECOVERY-01  
Audit generated: 2026-11-12T04:25:02.196059+00:00  
Repository: /Users/sooeunkim/workspace/RainbowKTL

## Decision

Measurement remains **BLOCKED**. Missing evidence is not a finding that raw417 is contaminated. This is a separate recovery report, not a replacement for the original lock, manifest, evidence gap report, or independent approval.

No prediction, scoring, F1, evaluation-result reading, recollection, relabeling, rule/config changes, data modification, credential changes, or server writes were performed. Only this new audit directory was created. The check of 75 non-result protected files matched the earlier audit exactly. Five pre-existing result-content files were deliberately excluded from rehashing to avoid reading prediction/results.

## Useful newly recovered corroboration

The nine surviving source CSV files have filesystem birth times that match the nine DBeaver CSV export messages to the same second, when the epoch-based filesystem times are rendered at UTC+09:00. The file type and order also match. This strengthens the candidate relationship between each existing raw/source-metadata file and the prior export occurrence.

It is not an exact historical receipt: the debug records contain no output hash, row count, SQL text, or session ID. Filesystem birthtime can be preserved/copied or altered. The stored debug timestamp lacks an explicit offset. The current file SHA-256 identifies the bytes available now, not the bytes at export time.

| Existing file | Rows now | Export log timestamp (no offset) | Observed birthtime UTC |
|---|---:|---|---|
| m05_heldout_raw_01/sessions.csv | 1 | 2026-11-11 21:15:59.296 | 2026-11-11T12:15:59.297495+00:00 |
| m05_heldout_raw_01/events.csv | 203 | 2026-11-11 21:16:11.784 | 2026-11-11T12:16:11.784726+00:00 |
| m05_heldout_raw_01/tasks.csv | 152 | 2026-11-11 21:16:21.501 | 2026-11-11T12:16:21.501860+00:00 |
| m05_heldout_raw_02/sessions.csv | 1 | 2026-11-11 21:39:19.267 | 2026-11-11T12:39:19.267491+00:00 |
| m05_heldout_raw_02/events.csv | 147 | 2026-11-11 21:39:27.500 | 2026-11-11T12:39:27.500156+00:00 |
| m05_heldout_raw_02/tasks.csv | 104 | 2026-11-11 21:39:36.629 | 2026-11-11T12:39:36.629969+00:00 |
| m05_heldout_raw_03/sessions.csv | 1 | 2026-11-11 22:34:10.777 | 2026-11-11T13:34:10.777777+00:00 |
| m05_heldout_raw_03/events.csv | 67 | 2026-11-11 22:34:18.365 | 2026-11-11T13:34:18.365511+00:00 |
| m05_heldout_raw_03/tasks.csv | 57 | 2026-11-11 22:34:25.882 | 2026-11-11T13:34:25.882430+00:00 |

Current raw session IDs:
- raw01: a901242f-3b9f-472d-ac88-5ba8215ca827, events203.
- raw02: 44e0ee56-29e0-4993-af4c-520b93e26cd2, events147.
- raw03: e91bbeec-405d-4ff8-8966-315320ce00e4, events67.

The corresponding Downloads filenames are still absent. A bounded filename search requested Downloads, Desktop, Documents and Trash and reported no matching paths, but exited with status1 while stderr was suppressed. Its folder-by-folder read coverage is therefore unverified, especially for protected folders. It is not an exhaustive absence check and does not prove that no backup or copy exists. Query results and predictions were not read.

## Source DB identity and export/activity time

DBeaver's debug log records a connection to `ingest_backend_db` at 2026-11-11 21:13:50 local-display time, MariaDB 11.4.10-MariaDB-ubu2404, MariaDB Connector/J 3.5.2, with SQL editor Script-35. It records all nine export-file opens and stream closes. This establishes client-observed DB product and export occurrences, not server completeness.

The activity file has `APP_OPEN startTime=1793682874963`. Adding each logged elapsed millisecond value recovers export-start UTC times:
- raw01 candidate exports: 12:15:58.908Z, 12:16:11.268Z, 12:16:21.136Z.
- raw02 candidates: 12:39:18.919Z, 12:39:27.072Z, 12:39:36.398Z.
- raw03 candidates: 13:34:10.530Z, 13:34:18.122Z, 13:34:25.759Z.

These agree with the debug export times after a +09:00 display conversion, allowing for the transfer-start/file-open delay. They are derived from existing client source records, not a certification of server clock or log continuity. `RESULT_SET_REFRESH` in that file is generic DB UI activity. It must not be reported as an evaluation/prediction-result view.

## SQL and export settings

- Checked 40 saved SQL scripts and 14 Eclipse local-history files for the three session IDs and `2026-11-11`: no matches.
- Current Script-35.sql filters at `2026-10-14 22:35:35.878`. Its persisted bytes are not the executed Nov11 SQL. Unsaved/in-memory SQL may differ.
- Recovered current transfer settings: SINGLE_QUERY, fetchSize10000, queryRowCount=true, fetchedRowsOnly=false, selectedColumnsOnly=false, selectedRowsOnly=false; UTF-8, no BOM, CSV header=top, delimiter=comma, escape=quotes, valueFormat=UI.
- The settings are not bound to the historical export tasks, so they cannot certify that no WHERE/LIMIT/filter or truncation applied then. The consumer-side `enableQmLogging=false` setting is not proof of Query Manager/global access-log configuration.
- The live Query Manager could not be inspected: `cua.getApp("DBeaver")` failed with `Sky Computer Use service startup request failed`. No UI state was obtained and no query was rerun. Keeping DBeaver open may preserve existing in-memory history.

## Access attempts and blockers

1. `127.0.0.1:3307`: no listener observed. The earlier tunnel is not currently available; no MySQL SQL was attempted this time.
2. Existing Rainbow SSH endpoint `rainbow01@125.177.146.253:2241`: one BatchMode/StrictHostKeyChecking=yes probe requesting only date/hostname/user failed with `Permission denied (publickey,password)`. Authentication failed before remote commands or SQL. No alternate account/key retry, credential prompt, tunnel restart, key enrollment, or settings change was attempted.
3. The observed DBeaver process had only its local management listener, with no established DB TCP connection shown.
4. Shell history shows local port3307 was used for both Rainbow and another project. A future working listener must be identified before querying; the port number is not proof of the source DB.

A server operator can restore the already-approved source connection or provide a preserved read-only export of the needed records. Do not send passwords or private keys in chat. This report neither performs nor authorizes a new privilege grant.

## Prediction/access and use-history limits

The available shell history has1609 lines, no extended timestamp prefixes, and zero lines mentioning the specific M05 entry points searched. Four `backend.server` lines exist, but do not identify requests or inputs. This shell history is incomplete and cannot cover tool/subprocess/direct adapter/external execution or result views. Its raw content was not copied into the report.

`results/development/m05_full_context` is absent now. This is a path-existence observation only. No results or predictions were read. No exhaustive job/access registry, server query log, server backup, ingest ack/drop/retry log, binlog, retention/rotation policy, or training/development input ledger was recovered. Label author/time and prior-use completeness remain unresolved by this audit.

## Minimum next evidence

- Inspect existing DBeaver Query Manager history before closing/restarting the application. Capture executed SQL, timestamps, connection identity and export mapping without rerunning.
- Restore an authorized read-only Rainbow connection or have the server operator provide the preserved DB/log evidence. Confirm endpoint identity first.
- Reconcile session event/task counts and IDs against the original server snapshot, query/filters, deleted/late-arriving events, ingest receipts and source preservation policy.
- Obtain prediction execution and artifact read/view/download coverage from collection start2026-11-11T12:09:46.818Z through lock2026-11-11T13:47:09.237438Z. DBeaver export logs cannot substitute for it.
- If the original sources do not exist or cannot be obtained, keep UNKNOWN/BLOCKED. Do not invent retrospective logs, empty runs/views, false prior-use declarations or label timestamps.

## Source hashes and machine-readable audit

Full source paths, hashes, file metadata, safe exact log extracts, derived activity timestamps, search scope, access failures and 75-file preservation checks are in `db_export_recovery.json`.

- /Users/sooeunkim/Library/DBeaverData/workspace6/.metadata/dbeaver-debug.log
  SHA-256: d502d5da3f85c826e6180e42ab03defa0f910ba7373293c15abd570db83839f9
- /Users/sooeunkim/Library/DBeaverData/workspace6/.metadata/.activity-logs/1793682890_896792f8-9e57-44bd-baf1-e5d39a37f407.log
  SHA-256: 383ba410fd7a8b12dd3998a3f2a64e97c295850e584c1810ba17f6e2ec7785be
- /Users/sooeunkim/Library/DBeaverData/workspace6/.metadata/.plugins/org.jkiss.dbeaver.data.transfer.ui/dialog_settings.xml
  SHA-256: 0ea4d0d92a914b0e0eeb0bb75645bc1b085d7250942ca6d02c6d6bebac6e90b2
- /Users/sooeunkim/Library/DBeaverData/workspace6/General/Scripts/Script-35.sql
  SHA-256: aed36b4700cc56e253979b7552f6a309cb6193baef289c635b3a659b524d9f66
- /Users/sooeunkim/Library/DBeaverData/workspace6/General/.dbeaver/data-sources.json
  SHA-256: 1f67eddcae3b3a7c3fe352612c524476b090f640d7efa1ef043950da478c1fee
- /Users/sooeunkim/.zsh_history
  SHA-256: cae4f0c94993f47326ed0fc911882065ba8cbf06daa825f5f0cc78b1be47a10c
