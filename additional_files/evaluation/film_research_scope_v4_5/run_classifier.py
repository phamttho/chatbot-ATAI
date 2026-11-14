"""Live scope classification checks; loads the model without the full graph."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src/chatbot'))
from model_runtime import ModelRuntime
from movie_agent import CLASSIFY, parse_plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='Qwen/Qwen3.5-4B')
    parser.add_argument('--device', default='auto')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    runtime = ModelRuntime(args.model, args.device)
    results = []
    for line in (root / 'cases.jsonl').read_text().splitlines():
        case = json.loads(line)
        raw = runtime.generate(CLASSIFY, case['input'], max_new_tokens=100)
        try:
            plan = parse_plan(raw)
            passed = (set(plan['labels']) == set(case['expected_labels'])
                      and plan['intent'] == case['expected_intent'])
        except (ValueError, KeyError, TypeError):
            passed = False
        result = dict(case=case, output=raw, passed=passed)
        results.append(result)
        print(json.dumps(result), flush=True)
    (root / 'classifier_results.jsonl').write_text(
        ''.join(json.dumps(r) + '\n' for r in results))
    print(f"Passed {sum(r['passed'] for r in results)}/{len(results)}")
    return 0 if all(r['passed'] for r in results) else 1


if __name__ == '__main__':
    sys.exit(main())
