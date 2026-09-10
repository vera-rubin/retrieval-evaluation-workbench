"""Inspect actual pinned-tokenizer chunk coverage without loading model weights."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
PINS={'transformers':'4.57.1','tokenizers':'0.22.1'}
TOKENIZER_FILES={'config.json','tokenizer.json','tokenizer_config.json','special_tokens_map.json','vocab.txt'}

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def guard(started):
 if time.monotonic()-started>120:raise RuntimeError('TOKENIZER_INSPECTION_TIME_LIMIT')
 if 'torch' in sys.modules:raise RuntimeError('Torch import is prohibited in this tokenizer-only inspection')

def require_coverage(summary):
 for key in ('matches_retained_indexed_chunks','all_nonempty_fields_have_exact_full_coverage','local_manifest_matches_retained_run'):
  if summary.get(key) is not True:raise RuntimeError('TOKENIZER_COVERAGE_CHECK_FAILED: '+key)

def inspect(artifacts):
 started=time.monotonic()
 os.environ.update(USE_TORCH='0',USE_TF='0',USE_FLAX='0',TOKENIZERS_PARALLELISM='false',
                   OMP_NUM_THREADS='2',MKL_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',
                   HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_IMPLICIT_TOKEN='1',HF_HUB_DISABLE_TELEMETRY='1')
 sys.path.insert(0,str(ROOT))
 site=artifacts/'site'
 if not site.is_dir():raise RuntimeError('SELECTED_DEPENDENCY_SITE_NOT_STAGED')
 sys.path.insert(0,str(site))
 for name,expected in PINS.items():
  if importlib.metadata.version(name)!=expected:raise RuntimeError('PINNED_TOKENIZER_DEPENDENCY_DIFFERS: '+name)
 from transformers import AutoTokenizer
 from hippo_eval.contracts import load_json,digest
 from hippo_eval.retrieval import MODEL_SPECS,tokenizer_chunks,_check_records,_rss_bytes
 guard(started)
 corpus_path=ROOT/'fixtures/corpus.json'
 corpus=load_json(corpus_path)
 records=_check_records(corpus['records'])
 if len(records)!=300:raise RuntimeError('Inspection is bounded to the established 300-record corpus')
 indexable={rid:r for rid,r in records.items() if r['body'] is not None}
 total_chars=sum(len(record[field]) for record in indexable.values() for field in ('title','body'))
 if total_chars>2_000_000:raise RuntimeError('TOKENIZER_INSPECTION_TEXT_SIZE_LIMIT')
 reference_path=ROOT/'results/release-heldout/run.json.gz'
 reference=load_json(reference_path)
 queries_path=ROOT/'fixtures/queries.json'
 queries=load_json(queries_path)
 if digest({'corpus':corpus,'queries':queries})!=reference['identity']['fixture_digest']:
  raise RuntimeError('CURRENT_FIXTURES_DIFFER_FROM_RETAINED_RUN')
 for module in ('hippo_eval/retrieval.py','hippo_eval/contracts.py'):
  if sha(ROOT/module)!=reference['identity']['source_files'][module]:
   raise RuntimeError('CURRENT_CHUNK_HELPER_SOURCE_DIFFERS_FROM_RETAINED_RUN')
 reference_methods={m['name']:m for m in reference['methods']}
 config=reference['configuration']
 if config['chunk_tokens']!=240 or config['overlap_tokens']!=32:raise RuntimeError('Reference configuration differs from established 240/32 protocol')
 output={'schema':'retrieval-tokenizer-coverage/v1','created_at':datetime.now(timezone.utc).isoformat(),
         'execution':'actual pinned-tokenizer-only inspection; no model weights loaded, no forward pass, no retrieval scoring',
         'source_files':{'scripts/inspect_chunk_coverage.py':sha(Path(__file__)),
                         'hippo_eval/retrieval.py':sha(ROOT/'hippo_eval/retrieval.py'),
                         'hippo_eval/contracts.py':sha(ROOT/'hippo_eval/contracts.py')},
         'corpus_sha256':sha(corpus_path),'queries_sha256':sha(queries_path),'reference_raw_sha256':sha(reference_path),
         'fixture_and_helper_identities_match_retained_run':True,
         'configuration':{'chunk_tokens_including_special_tokens':240,'overlap_content_tokens':32,'truncation':False},
         'dependencies':{name:importlib.metadata.version(name) for name in PINS},
         'python':sys.version,'corpus_records':len(records),'excluded_null_body_records':len(records)-len(indexable),
         'indexable_records':len(indexable),'candidate_fields':2*len(indexable),
         'nonempty_candidate_fields':sum(bool(record[field].strip()) for record in indexable.values() for field in ('title','body')),
         'total_source_characters':total_chars,'models':[]}
 peak_rss=0
 for key,spec in MODEL_SPECS.items():
  model_dir=artifacts/'models'/key
  manifest_path=model_dir/'manifest.json'
  if not manifest_path.is_file():raise RuntimeError('PINNED_TOKENIZER_MANIFEST_NOT_STAGED: '+key)
  manifest=load_json(manifest_path)
  if manifest['model_id']!=spec['model_id'] or manifest['revision']!=spec['revision']:raise RuntimeError('PINNED_MODEL_REVISION_DIFFERS: '+key)
  retained=reference_methods[key]['identity']
  if manifest['model_id']!=retained['model_id'] or manifest['revision']!=retained['revision']:raise RuntimeError('RETAINED_MODEL_IDENTITY_DIFFERS: '+key)
  manifest_files={item['path']:item for item in manifest['files']}
  if not {'config.json','tokenizer.json','tokenizer_config.json'}.issubset(manifest_files):raise RuntimeError('Incomplete tokenizer artifacts')
  verified=[]
  for name in sorted(TOKENIZER_FILES.intersection(manifest_files)):
   actual=sha(model_dir/name)
   if actual!=manifest_files[name]['sha256'] or actual!=retained['artifact_hashes'][name]:raise RuntimeError('TOKENIZER_ASSET_HASH_DIFFERS: '+name)
   verified.append({'file':name,'sha256':actual,'bytes':(model_dir/name).stat().st_size,'git_blob_id':manifest_files[name].get('git_blob_id')})
  tokenizer=AutoTokenizer.from_pretrained(str(model_dir),use_fast=True,trust_remote_code=False,local_files_only=True)
  if not tokenizer.is_fast or type(tokenizer).__name__!=retained['tokenizer_class']:raise RuntimeError('TOKENIZER_CLASS_DIFFERS')
  rows=[];chunks_all=[];model_started=time.monotonic()
  for rid,record in sorted(indexable.items()):
   for field in ('title','body'):
    text=record[field]
    chunks=tokenizer_chunks(text,tokenizer,240,32,rid,field)
    token_count=len(tokenizer(text,add_special_tokens=False,truncation=False,verbose=False)['input_ids'])
    covered_until=0;coverage=True
    for chunk in chunks:
     if chunk['char_start']>covered_until:coverage=False
     covered_until=max(covered_until,chunk['char_end'])
     if text[chunk['char_start']:chunk['char_end']]!=chunk['text']:raise RuntimeError('SOURCE_SUBSTRING_MISMATCH')
     if text.encode('utf-8')[chunk['byte_start']:chunk['byte_end']]!=chunk['text'].encode('utf-8'):raise RuntimeError('SOURCE_UTF8_OFFSET_MISMATCH')
     if chunk['token_count']>240:raise RuntimeError('CHUNK_TOKEN_BUDGET_EXCEEDED')
    coverage=coverage and (covered_until==len(text) or not text.strip())
    rows.append({'record_id':rid,'field':field,'source_characters':len(text),'source_utf8_bytes':len(text.encode('utf-8')),
                 'source_field_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest(),'nonempty':bool(text.strip()),
                 'content_tokens_without_special_tokens':token_count,'chunks':len(chunks),
                 'chunk_token_counts':[chunk['token_count'] for chunk in chunks],
                 'whole_nonempty_field_covered_by_exact_substrings':coverage})
    chunks_all.extend(chunks)
    guard(started)
   current_rss=_rss_bytes();peak_rss=max(peak_rss,current_rss)
   if current_rss>2*1024**3:raise RuntimeError('TOKENIZER_INSPECTION_RSS_LIMIT')
  by_record=Counter()
  for row in rows:by_record[row['record_id']]+=row['chunks']
  summary={'model_key':key,'model_id':spec['model_id'],'revision':spec['revision'],
           'tokenizer_class':type(tokenizer).__name__,'special_tokens_per_single_sequence':tokenizer.num_special_tokens_to_add(pair=False),
           'verified_tokenizer_assets':verified,'local_manifest_sha256':sha(manifest_path),
           'local_manifest_matches_retained_run':sha(manifest_path)==retained['model_manifest_sha256'],
           'candidate_fields':len(rows),'nonempty_fields':sum(row['nonempty'] for row in rows),
           'indexed_fields':sum(row['chunks']>0 for row in rows),'indexed_records':sum(count>0 for count in by_record.values()),
           'chunks':len(chunks_all),'matches_retained_indexed_chunks':len(chunks_all)==reference_methods[key]['measurements']['indexed_chunks'],
           'multi_chunk_fields':sum(row['chunks']>1 for row in rows),'multi_chunk_bodies':sum(row['field']=='body' and row['chunks']>1 for row in rows),
           'multi_chunk_titles':sum(row['field']=='title' and row['chunks']>1 for row in rows),'maximum_chunks_per_field':max(row['chunks'] for row in rows),
           'field_chunk_histogram':dict(sorted(Counter(row['chunks'] for row in rows).items())),
           'record_chunk_histogram':dict(sorted(Counter(by_record.values()).items())),
           'maximum_content_tokens_per_field':max(row['content_tokens_without_special_tokens'] for row in rows),
           'maximum_chunk_tokens':max(chunk['token_count'] for chunk in chunks_all),
           'all_nonempty_fields_have_exact_full_coverage':all(row['whole_nonempty_field_covered_by_exact_substrings'] for row in rows if row['nonempty']),
           'multi_chunk_details':[row for row in rows if row['chunks']>1],
           'chunk_metadata_digest':digest([{key:value for key,value in chunk.items() if key!='text'} for chunk in chunks_all]),
           'field_details':rows,'elapsed_seconds':time.monotonic()-model_started}
  require_coverage(summary)
  output['models'].append(summary)
  del tokenizer
 guard(started)
 for model in output['models']:
  for asset in model['verified_tokenizer_assets']:
   if sha(artifacts/'models'/model['model_key']/asset['file'])!=asset['sha256']:
    raise RuntimeError('TOKENIZER_ASSETS_CHANGED_DURING_INSPECTION')
 output['runtime_checks']={'torch_imported': 'torch' in sys.modules,'model_forward_passes':0,
                            'tokenizer_parallelism':'disabled','compute_environment_thread_limit':2,
                            'peak_sampled_rss_bytes':peak_rss,'elapsed_seconds':time.monotonic()-started}
 return output

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--artifacts',type=Path,default=ROOT/'.artifacts')
 parser.add_argument('--out',type=Path,required=True,help='New compact coverage receipt')
 parser.add_argument('--details-out',type=Path,help='Optional new full per-field receipt')
 args=parser.parse_args()
 for destination in (args.out,args.details_out):
  if destination is not None and destination.exists():raise RuntimeError('Preserve existing tokenizer inspection receipt; select a new output')
 if args.details_out is not None and args.details_out.resolve()==args.out.resolve():
  raise RuntimeError('Compact and full-detail outputs must be different files')
 result=inspect(args.artifacts.expanduser().resolve())
 if args.details_out is not None:
  args.details_out.parent.mkdir(parents=True,exist_ok=True)
  args.details_out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
 compact=dict(result)
 compact['models']=[{key:value for key,value in model.items() if key!='field_details'} for model in result['models']]
 compact['detail_scope']='Per-field rows omitted from this compact receipt; --details-out writes full observed details.'
 args.out.parent.mkdir(parents=True,exist_ok=True)
 args.out.write_text(json.dumps(compact,indent=2)+'\n',encoding='utf-8',newline='\n')
 print(json.dumps({'indexable_records':result['indexable_records'],'nonempty_fields':result['nonempty_candidate_fields'],
                   'models':[{key:model[key] for key in ('model_key','chunks','multi_chunk_fields','multi_chunk_bodies','multi_chunk_titles','maximum_chunks_per_field','field_chunk_histogram','all_nonempty_fields_have_exact_full_coverage')} for model in result['models']],
                   'runtime_checks':result['runtime_checks']},indent=2))
