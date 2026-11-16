"""Independent evidence-only recomputation; no model/GT loader or central scorer."""
import csv
import io
from collections import Counter


def recalculate_csv(text):
    rows = list(csv.DictReader(io.StringIO(text)))
    def check(condition, message):
        if not condition:
            raise ValueError(message)
    check(len(rows) == 20 and len({r['event_id'] for r in rows}) == 20, 'Exactly 20 distinct targets required')
    check(all(r['event_id'].strip() and r['is_target'] == 'True' and (r['held_out'] == 'True' or (r['held_out'] == '' and r.get('evaluation_eligibility') == 'USER_AUTHORIZED_DEVELOPMENT_EXISTING_LOCKED_TARGETS' and r.get('held_out_evidence_status') == 'INSUFFICIENT_NOT_BLOCKING_FOR_THIS_DEVELOPMENT'))
              and r['run_mode'] == 'DEVELOPMENT' for r in rows), 'Context/non-held-out row in evidence')
    check(Counter(r['expected_label'] for r in rows) == {'KEEP': 10, 'REMOVE': 10}, '10/10 labels required')
    # Independently validate the allowed metadata values, never category quotas.
    check(all(r['remove_category'] in {'duplicate', 'noise', 'repeated_action', 'irrelevant_action'}
              for r in rows if r['expected_label'] == 'REMOVE' and r.get('evaluation_eligibility') != 'USER_AUTHORIZED_DEVELOPMENT_EXISTING_LOCKED_TARGETS'), 'Invalid REMOVE category')
    counts = dict(TP=0, FP=0, FN=0, TN=0)
    table = {('REMOVE', 'REMOVE'): 'TP', ('KEEP', 'REMOVE'): 'FP',
             ('REMOVE', 'KEEP'): 'FN', ('KEEP', 'KEEP'): 'TN'}
    for row in rows:
        check(row['expected_label'] != 'KEEP' or row['remove_category'] == '', 'KEEP category must be empty')
        key = (row['expected_label'], row['predicted_label'])
        check(key in table and table[key] == row['classification'], 'Confusion cell mismatch')
        counts[table[key]] += 1
    tp, fp, fn, tn = (counts[k] for k in ('TP', 'FP', 'FN', 'TN'))
    check(tp + fp + fn + tn == 20 and tp + fn == 10 and tn + fp == 10, 'Confusion denominator mismatch')
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    # Separately derived from the CSV binary labels; category never changes TP.
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0
    return dict(counts, precision=precision, recall=recall, f1=f1, passed=f1 >= .79)
