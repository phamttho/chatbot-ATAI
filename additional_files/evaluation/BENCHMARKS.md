# Local benchmark results

These are the initial small development runs. Use the [requirements-based evaluation](quality/RESULTS.md) for the larger, independently verified comparison.

Measured on NVIDIA GB10 using local Transformers inference and the supplied 2,413,825-triple graph. The original Speakeasy integration was neither modified nor contacted. Models were downloaded from public Hugging Face repositories; inference and graph execution were local. See [environment.json](results/environment.json) for versions, graph hash, and exact model snapshots.

## Original dataset: fixed 24-case sample

All implementations used the same seed-42 sample from the original 300-case file. The full 300-case dataset was not run. Ordinary factual checks require a graph route and expected keywords, so they do not establish answer completeness. Guardrail behavior checks routing and refusal text availability rather than using a semantic judge.

| Implementation | Factual (4) | Guardrails (16) | Movie discussion (4) | Overall | Label accuracy | Mean / p95 |
|---|---:|---:|---:|---:|---:|---:|
| Original Qwen 2.5 1.5B + rules | 1/4 | 16/16 | 4/4 | 21/24 | 100.0% | 0.46s / 1.63s |
| LLM-first Qwen 3.5 0.8B | 0/4 | 10/16 | 0/4 | 10/24 | 75.0% | 0.48s / 0.67s |
| LLM-first Qwen 3.5 4B | 4/4 | 16/16 | 0/4 | 20/24 | 100.0% | 1.38s / 3.42s |

The four discussion/recommendation cases are deliberately unsupported by the new factual-QA agent. They receive a safe redirection and remain failures in the table; they are not counted as successful generated answers. The baseline supports free-form generation, so its broader overall score is higher despite its lower graph-grounded factual coverage.

## Requirements suite: 13 development cases

This separate suite contains the six supplied factual examples, Inception's cinematographer and director, plus five supplied guardrail examples. The graph was checked directly to confirm the complete expected factual answer sets. Exact unordered answer sets are required for all eight factual questions; both applicable labels are required for the novel/crime and injection/homework cases. These are development examples, not an unseen test set.

| Implementation | Complete factual answers (8) | Guardrails incl. mixed labels (5) | Overall | Mean / p95 |
|---|---:|---:|---:|---:|
| Original Qwen 2.5 1.5B + rules | 7/8 | 3/5 | 10/13 | 0.07s / 0.14s |
| LLM-first Qwen 3.5 0.8B | 0/8 | 3/5 | 3/13 | 0.53s / 0.71s |
| LLM-first Qwen 3.5 4B | 8/8 | 5/5 | 13/13 | 3.00s / 5.36s |

## Findings and limits

- The original system returned Robert Elswit for Inception's cinematographer through its LLM fallback. The graph contains Wally Pfister. The new 4B agent retrieves Wally Pfister through SPARQL and never fills missing graph answers from model memory.
- With these prompts and deterministic greedy decoding, the requested 0.8B model did not complete a factual query successfully. Minimal-prompt probes also produced malformed SPARQL. This motivated the small 4B comparison; it does not establish that every possible 0.8B prompting or fine-tuning strategy would fail.
- The 4B model is the working default. `--model Qwen/Qwen3.5-0.8B` remains available. One model call classifies a request; a second generates SPARQL only for safe factual questions. Final factual wording uses a template, retaining every returned answer.
- Any blocked label takes precedence over a safe portion of a mixed message. A regression test covers safe + toxic outputs. Multi-label guardrails are exposed in the API, alongside a primary label for compatibility with the original cases.
- Small development samples, repeated during implementation, do not establish held-out factuality or adversarial robustness. The requirements suite overlaps the original sample on the cinematographer question; the two tables must not be added as independent observations.
- Latencies exclude startup/download time and include HTTP round trips. Models were warmed by preceding development requests. Some development requests overlapped on the same GPU, so these timings are indicative rather than controlled performance comparisons. No full-load throughput or concurrent-serving benchmark was performed. The Qwen 3.5 runtime used the portable PyTorch linear-attention fallback, without optional custom CUDA kernels. MPS was not tested.
- Lexical entity retrieval can miss descriptions or select the wrong entity when names are ambiguous. Queries support a single relation in either direction and date-ordered inverse lookups, not arbitrary multi-hop reasoning, counts, embeddings, or recommendations.

## Reproduce

See [the root README](../../README.md) for installation and HTTP commands and [the evaluation README](README.md) for score definitions. Raw requests, model outputs, generated queries, responses, errors, and case IDs are saved in `results/baseline*.jsonl`, `results/qwen08*.jsonl`, and `results/qwen4*.jsonl`, with matching summaries. Each summary records the case-file SHA-256. The original source and case file remain intact.

All 19 automated tests passed; these use fake model outputs and a small temporary RDF graph to test behavior independently of model quality. The live benchmark tables above are the model-quality checks.

Model reference: [official Qwen 3.5 0.8B model card](https://huggingface.co/Qwen/Qwen3.5-0.8B).
