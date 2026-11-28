"""Offline tests for the RunPod orchestration guardrails (no external data)."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import run_task2 as runner


class TestTask2Guards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.id = 'pytest-dev__pytest-1234'
        self.request_id = 'my-control-attempt'
        req = self.root / 'grading_requests'
        req.mkdir(parents=True)
        (req / f'{self.id}.controls.json').write_text(json.dumps({'request_id': self.request_id}))
        self.grade = self.root / '.grader_store/results' / self.request_id
        (self.grade/'base_control').mkdir(parents=True)
        (self.grade/'gold_control').mkdir(parents=True)

    def write(self, name, body):
        p=self.grade/name
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(body))

    def test_control_must_have_done(self):
        ok, why=runner.controls_ok(self.root,self.id)
        self.assertFalse(ok)
        self.assertIn('missing',why)

    def test_positive_and_failed_controls(self):
        self.write('done.json', {'instance_id':self.id})
        self.write('base_control/outcome.json', {'report':{'resolved':False,'tests_status':{'FAIL_TO_PASS':{'failure':['test_bug']}}}})
        self.write('gold_control/outcome.json', {'report':{'resolved':True}})
        self.assertTrue(runner.controls_ok(self.root,self.id)[0])
        self.write('gold_control/outcome.json', {'report':{'resolved':False}})
        self.assertFalse(runner.controls_ok(self.root,self.id)[0])

    def test_grader_infrastructure_failure(self):
        self.write('done.json', {'setup_error':'image could not be pulled'})
        self.assertFalse(runner.controls_ok(self.root,self.id)[0])

    def test_help_stage_names_are_present(self):
        # This validates the wrapper surface without invoking any run.
        self.assertTrue(callable(runner.main))
        self.assertIn('source_only', runner.ARMS)
        self.assertIn('selective_stale', runner.ARMS)


if __name__ == '__main__':
    unittest.main()
