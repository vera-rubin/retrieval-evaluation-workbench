"""Recompute compact report tables from exact public raw observations."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hippo_eval.contracts import load_json, write_json
from hippo_eval.metrics import score_bundle

def summarize(path):
    bundle = load_json(path)
    corpus = load_json(ROOT / 'fixtures/corpus.json')
    queries = load_json(ROOT / 'fixtures/queries.json')
    analysis = score_bundle(bundle, corpus, queries)
    if not analysis['valid']:
        raise ValueError('Raw result contract invalid: ' + str(path))
    return {'raw_file': str(path.relative_to(ROOT)).replace('\\','/'),
            'raw_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'source_identity':bundle['identity'], 'split':bundle['split'],
            'configuration':bundle['configuration'], 'resource':bundle.get('resource'),
            'analysis':analysis,
            'measurements':{m['name']:m['measurements'] for m in bundle['methods']}}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('runs', nargs='+', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    write_json(args.out, {'schema':'release-result-summary/v1',
                         'purpose':'New standalone re-evaluation; known splits; no retuning',
                         'runs':[summarize(p.resolve()) for p in args.runs]})
    print('Recomputed',len(args.runs),'valid raw bundles')
