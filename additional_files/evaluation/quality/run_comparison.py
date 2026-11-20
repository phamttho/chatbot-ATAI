"""Run identical frozen suites on the original and new local API servers."""
import argparse
from pathlib import Path
import runpy
import sys
from run_suite import verify_frozen

HERE=Path(__file__).resolve().parent


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--old-url',default='http://127.0.0.1:8000')
 p.add_argument('--new-url',default='http://127.0.0.1:8001')
 p.add_argument('--output-dir',type=Path,default=HERE/'results')
 args=p.parse_args();verify_frozen()
 for name in ['baseline','qwen4']:
  for suite in ['guardrails','factual']:
   if (args.output_dir/(name+'_'+suite+'.jsonl')).exists():p.error('Use a fresh output directory to preserve previous results')
 for name,url in [('baseline',args.old_url),('qwen4',args.new_url)]:
  for suite in ['guardrails','factual']:
   print('START',name,suite,flush=True)
   sys.argv=['run_suite.py','--suite',suite,'--url',url,'--output',str(args.output_dir/(name+'_'+suite))]
   runpy.run_path(str(HERE/'run_suite.py'),run_name='__main__')
   print('DONE',name,suite,flush=True)

if __name__=='__main__':main()
