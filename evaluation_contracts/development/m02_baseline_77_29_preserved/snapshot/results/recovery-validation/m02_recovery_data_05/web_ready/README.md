# M02 recovery05 DEVELOPMENT read-only web adapter

Run from repository root:

    python3 -B results/recovery-validation/m02_recovery_data_05/web_ready/server.py

Open http://127.0.0.1:8767 on the same Mac.

This is a separate presentation adapter, not the frozen original frontend/backend server. It does not modify that service, raw data, frozen rules, or prior measurement artifacts. The button recomputes M02 using the identical frozen evaluator and verified saved generated maps; it does not rerun model inference. Exactly BU03 recovery04, BU09 recovery05, BU07/17/20 recovery01, one each. All dependency, source and artifact hashes are checked on measure/download. Any mismatch blocks the operation. Server binds loopback only. CSV is byte-identical to independently verified original evidence.

Validated: HTTP page, evaluator endpoint, five BU scores, overall 77.28981596002805%, target75, CSV response SHA; repeated measurement no writes; 4 adapter tests PASS. Live browser click/render verification is pending: computer-use browser inventory is empty (Chrome unavailable). HTTP/API testing is not reported as live UI PASS.

Collector actual extension build/reload and foreground-target real-site verification remains TODO before OFFICIAL collection. DEVELOPMENT target met does not mean KTL OFFICIAL passed.
