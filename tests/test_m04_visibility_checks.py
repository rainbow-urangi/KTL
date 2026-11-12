"""Exercise the real independent visibility predicate with synthetic DOM only."""
import json
import shutil
import subprocess
import unittest
from unittest.mock import patch

from backend.m04.checks import RuntimeChecks, prepare_contract


NODE = shutil.which('node')
LOCATOR = dict(by='css selector', value='.synthetic-dialog')
NODE_DOM = r"""const request=JSON.parse(require('fs').readFileSync(0,'utf8'));
const nodes=Object.fromEntries(Object.entries(request.nodes).map(([key,state])=>[key,{
  ...state,
  getClientRects(){return this.noRects?[]:[{}];}
}]));
for(const node of Object.values(nodes)) node.parentElement=nodes[node.parent]||null;
global.document={querySelectorAll(){return request.selected.map(id=>nodes[id]);}};
global.getComputedStyle=node=>({visibility:'visible',opacity:'1',...node.style});
const result=Function(request.script).apply(null,request.args);
process.stdout.write(JSON.stringify({result}));"""


def predicate(script, args, nodes, selected):
    payload = dict(script=script, args=list(args), nodes=nodes, selected=selected)
    result = subprocess.run([NODE, '-e', NODE_DOM], input=json.dumps(payload),
                            capture_output=True, encoding='utf-8', check=True)
    returned = json.loads(result.stdout)
    if set(returned) != {'result'} or type(returned['result']) is not bool:
        raise AssertionError('The visibility predicate must return only a boolean')
    return returned['result']


@unittest.skipUnless(NODE, 'Node is required to execute the fixed DOM predicate')
class VisibilityChecksTests(unittest.TestCase):
    def checker(self, expected, *, nodes=None, selected=None):
        condition = dict(kind='visible', target=LOCATOR, expected=expected)
        source = dict(scenario_id='VISIBILITY-SYNTHETIC', steps=[dict(
            order=1, action='verify', target=LOCATOR['value'], expected_result='Dialog visibility')],
            execution_contract=dict(version=1, scenario_id='VISIBILITY-SYNTHETIC', steps=[dict(
                order=1, action='verify', target=LOCATOR, checks=[condition])]))
        checker = RuntimeChecks(prepare_contract(source))
        checker._js = lambda driver, script, *args: predicate(
            script, args, {'dialog': {}} if nodes is None else nodes,
            ['dialog'] if selected is None else selected)
        return checker, condition

    def check(self, expected, **state):
        checker, condition = self.checker(expected, **state)
        return checker._simple(object(), condition)

    def test_one_visible_match_passes_and_missing_match_does_not(self):
        self.assertTrue(self.check(True))
        self.assertFalse(self.check(True, selected=[]))

    def test_positive_visibility_rejects_ambiguous_selector(self):
        for second in ({}, dict(noRects=True)):
            with self.subTest(second=second):
                self.assertFalse(self.check(True, nodes=dict(dialog={}, other=second),
                                            selected=['dialog', 'other']))

    def test_negative_visibility_requires_every_match_to_be_hidden(self):
        for selected in (['hidden', 'visible'], ['visible', 'hidden']):
            with self.subTest(selected=selected):
                self.assertFalse(self.check(False, nodes=dict(hidden=dict(noRects=True), visible={}),
                                            selected=selected))

    def test_negative_visibility_accepts_absence_and_all_hidden_matches(self):
        self.assertTrue(self.check(False, selected=[]))
        self.assertTrue(self.check(False, nodes=dict(
            a=dict(noRects=True), b=dict(style=dict(visibility='hidden')),
            c=dict(style=dict(opacity='0'))), selected=['a', 'b', 'c']))

    def test_zero_opacity_on_element_or_ancestor_is_not_visible(self):
        for nodes in (dict(dialog=dict(style=dict(opacity='0'))),
                      dict(dialog=dict(parent='container'), container=dict(style=dict(opacity='0'))),
                      dict(dialog=dict(parent='container'), container=dict(parent='root'),
                           root=dict(style=dict(opacity='0')))):
            with self.subTest(nodes=nodes):
                self.assertFalse(self.check(True, nodes=nodes))
                self.assertTrue(self.check(False, nodes=nodes))

    def test_partial_opacity_and_visible_override_remain_supported(self):
        self.assertTrue(self.check(True, nodes=dict(dialog=dict(style=dict(opacity='0.5')))))
        # CSS visibility can be restored on a child; ancestor opacity cannot.
        self.assertTrue(self.check(True, nodes=dict(dialog=dict(parent='container'),
                                                   container=dict(style=dict(visibility='hidden')))))

    def test_no_layout_hidden_and_collapsed_elements_fail_positive_visibility(self):
        for node in (dict(noRects=True), dict(style=dict(visibility='hidden')),
                     dict(style=dict(visibility='collapse'))):
            with self.subTest(node=node):
                self.assertFalse(self.check(True, nodes=dict(dialog=node)))

    def test_runtime_records_failure_when_later_match_is_still_visible(self):
        checker, _ = self.checker(False, nodes=dict(hidden=dict(noRects=True), visible={}),
                                  selected=['hidden', 'visible'])
        driver = object()
        checker.raw_execute = lambda *args: None
        checker.begin(1, [driver])
        with patch('backend.m04.checks.time.monotonic', side_effect=[0, 3]):
            passed, error, evidence = checker.finish([driver])
        self.assertFalse(passed)
        self.assertEqual(error, '독립 기대 결과 검사 실패: visible')
        self.assertEqual(evidence, [dict(check_index=1, kind='visible', status='FAIL')])

    def test_runtime_records_only_boolean_outcome_for_unique_visible_match(self):
        checker, _ = self.checker(True)
        driver = object()
        checker.raw_execute = lambda *args: None
        checker.begin(1, [driver])
        passed, error, evidence = checker.finish([driver])
        self.assertTrue(passed)
        self.assertIsNone(error)
        self.assertEqual(evidence, [dict(check_index=1, kind='visible', status='PASS')])


if __name__ == '__main__':
    unittest.main()
