#!/usr/bin/env python3
"""Task 2 RunPod orchestrator for Xiangrui's upstream DocAgent paired-runs package.

Does not change upstream code, prompts, memory builder, or grading policy.
Stages never label an ungraded prediction resolved. Re-runs use upstream resume.

Examples (from any directory):
  python3 run_task2.py preflight
  python3 run_task2.py smoke
  python3 run_task2.py prepare
  python3 run_task2.py controls --route github_actions --push
  python3 run_task2.py all --route github_actions --push
  python3 run_task2.py status
  python3 run_task2.py package

Requires a writable DocAgent fork with .github/workflows/swebench-grade.yml
for remote grading. On ordinary GitHub-hosted runners Docker disk/CPU may be
insufficient; remote grading can finish with an infrastructure error. Local
Docker grading is supported on a separate suitable machine.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_DOCAGENT = Path(os.environ.get('DOCAGENT_UPSTREAM_DIR', '/workspace/docagent-task1/DocAgent'))
DEFAULT_OUTPUT = Path(os.environ.get('DOCAGENT_TASK2_OUT', '/workspace/docagent-task2'))
ARMS = ('source_only', 'static_stale', 'selective_stale')


class Blocked(Exception):
    pass


def jload(p: Path):
    return json.loads(p.read_text(encoding='utf-8'))


def call(argv, cwd=None, check=True):
    print('\n$ ' + ' '.join(map(str, argv)), flush=True)
    p = subprocess.run(list(map(str, argv)), cwd=cwd, text=True)
    if check and p.returncode:
        raise Blocked(f'Exit code {p.returncode}: {argv[0]} (inspect output above)')
    return p.returncode


def git(repo, *args):
    p = subprocess.run(['git', '-C', str(repo), *args], text=True, capture_output=True)
    return p.stdout.strip() if p.returncode == 0 else None


def frozen(out):
    p = out / 'prepared/frozen.json'
    if not p.is_file():
        raise Blocked(f'No frozen manifest at {p}; run prepare first')
    return jload(p), p


def prepared_issues(manifest):
    return [(i['instance_id'], i['status']) for i in manifest['issues']]


def grade_marker(out, instance_id, control):
    return out / 'grading_requests' / f"{instance_id}.{'controls' if control else 'attempts'}.json"


def grade_result_path(out, instance_id, control):
    marker = grade_marker(out, instance_id, control)
    if not marker.exists():
        return None
    request_id = jload(marker)['request_id']
    return out / '.grader_store' / 'results' / request_id


def controls_ok(out, instance_id):
    root = grade_result_path(out, instance_id, True)
    if not root or not (root / 'done.json').exists():
        return False, 'official control results missing'
    done = jload(root / 'done.json')
    if done.get('setup_error'):
        return False, f"official grader setup_error: {done['setup_error']}"
    base = root / 'base_control/outcome.json'
    gold = root / 'gold_control/outcome.json'
    if not base.is_file() or not gold.is_file():
        return False, 'base/gold outcome.json missing'
    b, g = jload(base), jload(gold)
    base_report = b.get('report') or {}
    gold_report = g.get('report') or {}
    tests = (base_report.get('tests_status') or {}).get('FAIL_TO_PASS') or {}
    if not tests.get('failure'):
        return False, 'base control did not fail any designated FAIL_TO_PASS tests'
    if base_report.get('resolved') is True:
        return False, 'base control unexpectedly resolved'
    if gold_report.get('resolved') is not True:
        return False, 'reference patch did not officially resolve the instance'
    return True, 'official base failed and gold resolved'


def model_endpoint_check(backend_path):
    from urllib.request import urlopen
    from urllib.parse import urlparse
    d = jload(backend_path)
    settings = d.get('settings', {})
    print('Backend:', d.get('name'), 'model:', settings.get('model'))
    if settings.get('api_style') != 'ollama':
        return 'not checked (non-Ollama endpoint)'
    url = settings.get('base_url', 'http://127.0.0.1:11434').rstrip('/')
    hostname = urlparse(url).hostname
    # Only contact local Ollama by default; never expose keys or remote URLs.
    if hostname not in ('127.0.0.1', 'localhost', '::1'):
        return 'not checked (non-loopback Ollama address)'
    try:
        with urlopen(url + '/api/tags', timeout=8) as resp:
            models = json.load(resp).get('models', [])
        configured = settings.get('model')
        found = any(m.get('name') == configured or m.get('model') == configured for m in models)
        return f"Ollama reachable; configured model {'found' if found else 'NOT FOUND'}: {configured}"
    except Exception as exc:
        return f'Ollama unreachable: {type(exc).__name__}: {exc}'


def preflight(args, require_model=False):
    repo = args.docagent
    print('DocAgent checkout:', repo)
    checks = {
        'git_worktree': (repo / '.git').exists(),
        'task2_bench': (repo / 'experiments/paired_runs/bench.py').is_file(),
        'task2_grader': (repo / 'experiments/grader/remote_grade.py').is_file(),
        'released_helper': (repo / 'skills/docagent/scripts/docagent.py').is_file(),
        'workflow_file': (repo / '.github/workflows/swebench-grade.yml').is_file(),
    }
    for k, value in checks.items():
        print(f"{'OK' if value else 'MISSING'} {k}")
    print('DocAgent SHA:', git(repo, 'rev-parse', 'HEAD'))
    print('Origin:', git(repo, 'remote', 'get-url', 'origin'))
    print('Python:', sys.version.split()[0])
    print('CPU logical:', os.cpu_count())
    try:
        disk = shutil.disk_usage(args.out)
        print('Output disk free GiB:', round(disk.free / 2**30, 1))
    except OSError:
        pass
    print('Docker CLI:', shutil.which('docker') or 'not installed')
    print('Docker server: verify separately via docker info; do not assume nested Docker works')
    print('GPU:')
    call(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'], check=False) if shutil.which('nvidia-smi') else print('No nvidia-smi detected')
    backend = args.backend
    if backend.is_file():
        print(model_endpoint_check(backend))
    else:
        print('Missing backend config:', backend)
    if not all(checks[k] for k in ('git_worktree', 'task2_bench', 'task2_grader', 'released_helper')):
        raise Blocked('DocAgent checkout is incomplete')
    if args.route == 'github_actions' and args.push:
        origin = git(repo, 'remote', 'get-url', 'origin') or ''
        if 'xiangruiSun/DocAgent' in origin:
            raise Blocked('Original upstream DocAgent origin is read-only for this user; switch to a writable fork.')
        if not checks['workflow_file']:
            raise Blocked('Remote grading workflow is missing in DocAgent checkout')
    if require_model:
        model_status = model_endpoint_check(backend) if backend.is_file() else 'missing backend config'
        if 'NOT FOUND' in model_status or 'unreachable' in model_status or 'missing backend' in model_status:
            raise Blocked('Live model endpoint is not ready: ' + model_status)
    print('Preflight inspections complete. This is NOT a successful official grading check.')


def bench(args, *rest):
    script = args.docagent / 'experiments/paired_runs/bench.py'
    return call([sys.executable, script, *rest], cwd=args.docagent)


def smoke(args):
    bench(args, 'smoke', '--backend', 'fake')


def prepare(args):
    if (args.out / 'prepared/frozen.json').exists():
        m, _ = frozen(args.out)
        print('Prepared manifest already exists; refusing to overwrite it.')
        print('Issues:', prepared_issues(m))
        return
    args.out.mkdir(parents=True, exist_ok=True)
    if not args.study.is_file():
        raise Blocked(f'Study file does not exist: {args.study}')
    study = jload(args.study)
    target = int(study['tier']['held_out'])
    print('Target held-out issues:', target, '+ one disjoint pilot')
    # Do not let caches accidentally collide across separate studies on RunPod.
    cfg = {**study, 'cache_dir': str(args.out / '.cache'),
           'grader_store': str(args.out / '.grader_store')}
    local_study = args.out / 'study.frozen_input.json'
    local_study.write_text(json.dumps(cfg, indent=2) + '\n', encoding='utf-8')
    bench(args, 'prepare', '--config', str(local_study), '--out', str(args.out / 'prepared'))
    m, _ = frozen(args.out)
    pilots = [i for i in m['issues'] if i['status'] == 'pilot']
    heldouts = [i for i in m['issues'] if i['status'] == 'held_out']
    print('Prepared', len(pilots), 'pilot and', len(heldouts), 'held-out issues')
    # Human relevance annotation is a separate evaluator-side task.
    template = {}
    for issue in m['issues']:
        drift_path = args.out / 'prepared' / issue['instance_id'] / 'drift.json'
        drift = jload(drift_path) if drift_path.is_file() else []
        template[issue['instance_id']] = {
            'claim_ids': [], 'paths': [], '_candidate_claims': [
                {'claim_id': d.get('claim_id'), 'path': d.get('path'),
                 'symbol': d.get('symbol'), 'status': d.get('status')} for d in drift],
            '_instruction': 'Independently annotate task-relevant claim_ids and source paths from allowed pre-fix source; do not inspect gold patch.'
        }
    (args.out / 'relevance.review_template.json').write_text(json.dumps(template, indent=2) + '\n', encoding='utf-8')
    print('Human relevance review template:', args.out / 'relevance.review_template.json')
    print('After independent annotations, write a sanitized relevance.json (ONLY claim_ids and paths) at:', args.out / '.grader_store/relevance.json')
    if len(pilots) != 1 or len(heldouts) != target:
        raise Blocked('Prepared cohort does not meet the prespecified complete tier. '
                      'Preserve candidate log; choose a smaller complete tier before seeing outcomes.')


def guard_controls(args, ids):
    errors = []
    for instance in ids:
        ok, detail = controls_ok(args.out, instance)
        print(f"{'PASS' if ok else 'BLOCKED'} controls [{instance}]: {detail}")
        if not ok:
            errors.append(instance)
    if errors:
        raise Blocked('Do not run live solver on issues without official passing base/gold controls: '+', '.join(errors))


def grade_one(args, iid, controls=False):
    flags = ['grade', '--manifest', str(args.out / 'prepared/frozen.json'),
             '--instance-id', iid, '--workers', '1', '--route', args.route]
    if controls:
        flags += ['--controls']
    if args.route == 'github_actions' and args.push:
        flags += ['--push', '--wait-s', str(args.wait_s)]
    return bench(args, *flags)


def grade_many(args, ids, controls=False):
    errors = []
    for instance in ids:
        try:
            grade_one(args, instance, controls=controls)
        except Blocked as exc:
            print('PENDING/BLOCKED:', instance, str(exc))
            errors.append(instance)
    if errors:
        raise Blocked('Some grading is not completed: '+', '.join(errors)+'; rerun the same stage to resume')
    if controls:
        guard_controls(args, ids)
    else:
        errors = []
        for iid in ids:
            root = grade_result_path(args.out, iid, False)
            if not root or not (root / 'done.json').is_file():
                errors.append(f'{iid}: no official done.json')
                continue
            done = jload(root/'done.json')
            if done.get('setup_error'):
                errors.append(f"{iid}: {done['setup_error']}")
        if errors:
            raise Blocked('Grading report incomplete: '+'; '.join(errors))


def all_issue_groups(args):
    m, _ = frozen(args.out)
    pilots = [i['instance_id'] for i in m['issues'] if i['status']=='pilot']
    heldouts = [i['instance_id'] for i in m['issues'] if i['status']=='held_out']
    return pilots, heldouts


def run_pilot(args):
    pilots, _ = all_issue_groups(args)
    if len(pilots) != 1:
        raise Blocked('Expected one pilot')
    guard_controls(args, pilots)
    bench(args, 'pilot', '--config', str(args.out/'study.frozen_input.json'),
          '--backend', str(args.backend), '--out', str(args.out/'prepared'))
    # At least one gradeable patch is necessary before held-out execution.
    pilot_rows=[]
    for arm in ARMS:
        pilot_rows.extend((args.out/'runs'/pilots[0]/arm).glob('*/summary.json'))
    if len(pilot_rows) < 3 or not all(jload(p).get('is_live') is True for p in pilot_rows):
        raise Blocked('Pilot did not complete all three REAL backend sessions')
    if not any(jload(p).get('patch',{}).get('bytes',0)>0 for p in pilot_rows):
        raise Blocked('Pilot produced no gradeable diff in any arm; do not run held-out yet')


def run_heldout(args):
    _, heldouts = all_issue_groups(args)
    if not heldouts:
        raise Blocked('No held-out issues in frozen manifest')
    guard_controls(args, heldouts)
    # Validate that the pilot was graded before running held-out issues.
    pilots, _ = all_issue_groups(args)
    for iid in pilots:
        r = grade_result_path(args.out, iid, False)
        if not r or not (r/'done.json').is_file() or jload(r/'done.json').get('setup_error'):
            raise Blocked('Pilot official grading not complete; run grade-pilot first')
    # A human must mark relevant paths before claims about exploration.
    relevance = args.out/'.grader_store/relevance.json'
    if not relevance.is_file() or not jload(relevance):
        raise Blocked('Independent issue relevance annotation missing. Prepare created relevance.review_template.json; copy only reviewed claim_ids and paths to .grader_store/relevance.json')
    bench(args, 'run', '--manifest', str(args.out/'prepared/frozen.json'),
          '--backend', str(args.backend), '--resume', '--batch')


def report(args):
    bench(args, 'report', '--manifest', str(args.out/'prepared/frozen.json'),
          '--out', str(args.out/'report'))
    print('Report:', args.out/'report/summary.md')


def status(args):
    m, _ = frozen(args.out)
    for issue in m['issues']:
        iid = issue['instance_id']
        control, desc = controls_ok(args.out, iid)
        print('\n', iid, issue['status'], 'controls=', control, desc)
        for arm in ARMS:
            rows = list((args.out/'runs'/iid/arm).glob('*/summary.json'))
            if not rows:
                print(' ', arm, 'MISSING')
            else:
                x = jload(sorted(rows)[0])
                print(' ', arm, x['status'], 'live=', x.get('is_live'), 'patch_bytes=',x.get('patch',{}).get('bytes'))
        r=grade_result_path(args.out,iid,False)
        print(' Official grading:', 'AVAILABLE' if r and (r/'done.json').exists() else 'PENDING')


def package(args):
    m, _ = frozen(args.out)
    archive = args.out.parent / (args.out.name + '_submission.zip')
    wanted = ['prepared', 'runs', 'grading_requests', 'report', 'study.frozen_input.json']
    allowed = []
    for section in wanted:
        src = args.out/section
        if src.is_file(): allowed.append(src)
        elif src.is_dir(): allowed.extend(p for p in src.rglob('*') if p.is_file())
    results = args.out/'.grader_store/results'
    if results.is_dir(): allowed.extend(p for p in results.rglob('*') if p.is_file())
    # Exclude evaluator-only files and heavyweight cached source snapshots.
    forbidden = ('evaluator_only', 'reference_patch', 'test_patch', 'gold_patch', '/.cache/', 'api_key', 'secret')
    allowed = [p for p in allowed if not any(x in p.as_posix().lower() for x in forbidden)]
    if archive.exists():
        raise Blocked(f'Archive already exists: {archive}; rename it to avoid overwriting')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(set(allowed)):
            z.write(p, p.relative_to(args.out))
        z.writestr('SUBMISSION_README.txt',
                   'Task 2 artifacts. Official grader output and per-issue report must be checked.\n'
                   'Hidden reference patch/test patch intentionally excluded.\n'
                   f'DocAgent HEAD: {git(args.docagent,"rev-parse","HEAD")}\n'
                   f'Issue count: {len(m["issues"])}\n')
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise Blocked('ZIP integrity failed')
    print('Submission ZIP:', archive)
    print('Size bytes:', archive.stat().st_size)


def main():
    p=argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('stage', choices=('preflight','smoke','prepare','controls','pilot','grade-pilot','heldout','grade-heldout','report','status','package','all'))
    p.add_argument('--docagent',type=Path,default=DEFAULT_DOCAGENT)
    p.add_argument('--out',type=Path,default=DEFAULT_OUTPUT)
    p.add_argument('--study',type=Path,default=HERE/'study.task2.json')
    p.add_argument('--backend',type=Path,default=HERE/'backend.qwen3-coder-30b.json')
    p.add_argument('--route',choices=('github_actions','local'),default='github_actions')
    p.add_argument('--push',action='store_true',help='explicitly enable publishing requests to a writable grading branch')
    p.add_argument('--wait-s',type=float,default=0,help='seconds to wait for remote grading in each stage')
    args=p.parse_args()
    args.docagent=args.docagent.expanduser().resolve()
    args.out=args.out.expanduser().resolve()
    args.study=args.study.expanduser().resolve()
    args.backend=args.backend.expanduser().resolve()
    args.out.mkdir(parents=True,exist_ok=True)
    try:
        if args.stage=='preflight':preflight(args)
        elif args.stage=='smoke':smoke(args)
        elif args.stage=='prepare':prepare(args)
        elif args.stage=='controls':
            a,b=all_issue_groups(args);grade_many(args,a+b,controls=True)
        elif args.stage=='pilot':run_pilot(args)
        elif args.stage=='grade-pilot':
            a,b=all_issue_groups(args);grade_many(args,a)
        elif args.stage=='heldout':run_heldout(args)
        elif args.stage=='grade-heldout':
            a,b=all_issue_groups(args);grade_many(args,b)
        elif args.stage=='report':report(args)
        elif args.stage=='status':status(args)
        elif args.stage=='package':package(args)
        elif args.stage=='all':
            preflight(args,require_model=True)
            smoke(args)
            prepare(args)
            a,b=all_issue_groups(args)
            grade_many(args,a+b,controls=True)
            run_pilot(args)
            grade_many(args,a)
            run_heldout(args)
            grade_many(args,b)
            report(args)
            package(args)
        return 0
    except Blocked as exc:
        print('\nBLOCKED: '+str(exc),file=sys.stderr)
        print('Resume with the same output folder; no successful Agent attempt is overwritten.',file=sys.stderr)
        return 2


if __name__=='__main__':
    sys.exit(main())
