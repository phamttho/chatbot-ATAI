# Local movie knowledge graph assistant

`python main.py` starts the Qwen3.5-4B movie agent on Speakeasy,
using the credentials already configured in the root `main.py`. The local HTTP
entry point (`python local.py`) runs the same agent without connecting to Speakeasy.

To run the Speakeasy bot from the project directory:

```bash
source .venv/bin/activate
python main.py
```

Keep the terminal running while the bot polls its assigned rooms. Press Ctrl+C
to stop it. `MOVIE_LLM_MODEL` overrides the default model, `KNOWLEDGE_GRAPH_PATH`
overrides the graph, and `SPEAKEASY_BASE_URL` overrides the service URL. The
Speakeasy message timeout defaults to 30 seconds and can be overridden with
`MESSAGE_TIMEOUT_SECONDS`. Historical benchmark source snapshots remain intact;
the original agent remains available through `local.py --engine legacy`.

The Speakeasy runtime is kept in `additional_files/src/chatbot/`: `main.py`,
`speakeasy_client.py`, `movie_agent.py`, `model_runtime.py`, and `graph_store.py`.
The local HTTP server and legacy implementation live in
`additional_files/evaluation/`; `python local.py` remains the local entry point.

## Install

Use Python 3.11+ and a virtual environment. Install the CUDA-enabled PyTorch build
appropriate for your device first, then:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --no-build-isolation -r requirements.txt
```

The single `requirements.txt` includes `flash-linear-attention` and
`causal-conv1d` for Qwen3.5's optimized CUDA kernels. Building
`causal-conv1d` from source requires a CUDA toolkit (`nvcc`) compatible with
the installed PyTorch build. Restart the bot after installing. The first request
can include Triton kernel compilation; measure subsequent requests for steady
inference latency. This requirements file targets the CUDA deployment.

Tested on NVIDIA GB10 with PyTorch 2.12.0+cu130 and Transformers 5.12.1; exact
package versions used for the benchmarks are in
`additional_files/evaluation/results/environment.json`. The working environment
on this machine reuses the preinstalled CUDA packages via a local `.pth` file;
that machine-specific setup is not needed with a normal PyTorch installation.
CUDA is preferred automatically, then MPS, then CPU. `--device` overrides this
for the new implementation. The GB10 needs a PyTorch build supporting its GPU
architecture; an older CUDA wheel may not work. BF16 is used on supported CUDA
GPUs; MPS and CPU use float32 for compatibility. MPS was not benchmarked here.

## Serve and ask questions

```bash
.venv/bin/python local.py --engine llm --model Qwen/Qwen3.5-4B --port 8001
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Who directed Inception?"}'
```

The working default is Qwen 3.5 4B: the requested 0.8B model was tested first
and struggled with SPARQL generation. Use `--model Qwen/Qwen3.5-0.8B` to
reproduce that smaller-model configuration. The first launch downloads public model weights. Subsequent runs use the
Hugging Face cache. Use a local model directory and `HF_HUB_OFFLINE=1` to prevent
network downloads. Inference and graph queries run locally; no hosted inference
API or account is required. HTTP binds to loopback by default. Swagger API docs
are at `/docs`. Responses include labels, route, answer, generated SPARQL, graph
values, candidate entities, raw model outputs, model-call count, and latency.

To compare the original system on the same API:

```bash
.venv/bin/python local.py --engine legacy --port 8000
```

The baseline uses its original `Qwen/Qwen2.5-1.5B-Instruct` and unchanged agent
code. It requires a successfully loaded model rather than silently benchmarking
a degraded fallback. `--model` can override it for a separate experiment.

## Evaluation of the updated system

The updated system supports article-free titles and graph aliases, bounded fuzzy
name matching, custom user tags and ratings, distinct counts, and numeric user
rating and release-date filters. It uses a structured model plan compiled into
validated SPARQL. Release-date filters work without a named film and compare
calendar dates consistently across RDF date/dateTime values. Quoted titles and
literal punctuation-bearing titles such as `&ME` survive stop-word filtering.
Successful factual answers contain graph values directly, without “The factual
answer is:”. Speakeasy replies display all applicable classification labels;
unsafe, prompt-injection, and out-of-scope requests stop before factual planning
and querying. A safe movie request with an insult retains both
`[safe_in_scope] + [toxic]` labels and answers the movie request, with a brief
respectful-conversation reminder in Speakeasy replies; insults alone
still receive the respectful-conversation response. See the
[reported-question and Evaluation 3 checks](additional_files/evaluation/release_dates_v3/README.md).
In v4.6, a separate safe movie question combined with an unrelated task retains
both `[safe_in_scope] + [out_of_scope]` labels while refusing the combined request
before planning or graph retrieval. Merely framing general research as film
preparation still receives `[out_of_scope]` alone. All 72 automated tests passed.
The earlier release-date revision passed all 50 automated tests, all 20 focused live checks,
and the complete 243-case regression run: 96/96 factual, 100/100 guardrail and
47/47 capability cases. These are regression/development results. Restart an
already-running `python main.py` process to load the changes.

The v4.1 [composable movie-selection revision](additional_files/evaluation/movie_selection_v4/README.md)
also supports whole-year questions, counting matching movies, earliest/latest
matches with all ties, negated director conditions, and combined filters. It
passed **60/60** automated tests, **20/20** pasted-query/variant checks, and the
full **243/243** existing regression run. For example, the supplied graph has
**217** movie records released in 2010. Large Speakeasy lists show a labelled
25-title preview and the full match count; HTTP results retain every value.

The [v4.2 count/display update](additional_files/evaluation/count_format_v4_2/README.md)
enforces numeric answers to explicit “How many movies/films” requests before
query execution, including movie counts by director. Displayed lists now use
**at most 10 comma-separated values**, with complete results retained in API
metadata. It passed 66 automated tests and 10 focused live checks. An additional
243 saved responses were replayed offline to verify formatting; this was not a
new live-model benchmark. Restart an existing `python main.py` process to load it.

The latest [v4.3 recommendation update](additional_files/evaluation/recommendations_v4_3/README.md)
uses Qwen directly for safe movie recommendations and movie discussion after
guardrail classification. Factual questions keep the validated graph workflow.
Six focused live checks passed; no broad benchmark was rerun for this change.
Questions about ambiguous names request clarification; unknown ratings never
qualify for a rating filter. The Qwen 3.5 4B model remains unchanged.

The original suite contains **96 factual questions and 100 guardrail cases**.
The [v4.5 scope clarification](additional_files/evaluation/film_research_scope_v4_5/README.md)
keeps general history/science research out of scope even when framed as film
preparation. The current Qwen 3.5 4B model produced the expected labels on all
12 focused live cases; 11/12 intents matched, with one plot-summary routing
limitation. All 71 automated tests passed. Restart running processes to load it.

The capability extension adds **47 factual cases**: three user regressions and
44 additional graph-derived cases covering omitted articles, quoted misspellings,
tag/cast counts, tag/rating lookups, and numeric comparisons/negation. The new
gold answers are independently checked using RDFLib before inference.

With the updated server on port 8001, run all 243 cases:

```bash
.venv/bin/python additional_files/evaluation/capabilities_v2/run_evaluation.py \
  --systems updated --updated-url http://127.0.0.1:8001 \
  --output-dir "additional_files/evaluation/capabilities_v2/results_$(date +%Y%m%d_%H%M%S)"
```

See [capability evaluation instructions](additional_files/evaluation/capabilities_v2/README.md)
for comparing all three implementations and reproducing the previous version.
The [verified capability-update results](additional_files/evaluation/capabilities_v2/results_final_verified/RESULTS.md)
report 96/96 original factual passes, 46/47 capability passes, and 90/100 strict
guardrail passes. All 40 automated tests passed. The original factual suite was
used for regression debugging; the additional capability cases were evaluated
after the implementation was fixed.

Historical scores and their frozen source hashes remain in
[the original results](additional_files/evaluation/quality/RESULTS.md).
The subsequent [prompt clarification regression run](additional_files/evaluation/capabilities_v2/results_prompt_clarification_20261106/RESULTS.md)
passed 242/243 cases (99.6%): 96/96 factual, 100/100 guardrails, and 46/47
capability cases. It fixes the prior label and trilogy failures, but introduces
one observed long-entity-ID copying failure. All 40 code tests and 12 separate
new guardrail boundary checks passed. These are development and regression
results, not a production accuracy estimate.
The historical `quality/run_comparison.py` deliberately rejects changed agent
sources; use the capability runner for the updated code rather than rewriting
that historical manifest.

## Evaluate small subsets

The full [corrected 3,000-case benchmark](additional_files/evaluation/corrected_3k/results_completed_20261106/BENCHMARK.md)
has completed: **2,966/3,000 (98.87%)** passed complete-answer and executed-query
grounding checks. Mean HTTP latency was **3.558s**, p95 **4.109s**. The 3,000
questions span 1,548 films; every intended film and reference answer set was
independently validated with RDFLib before inference. The suite preserves the
original relation coverage and records 101 deterministic replacements for
ambiguous, duplicate or unusable records. See the [suite instructions](additional_files/evaluation/corrected_3k/README.md)
and [34-failure breakdown](additional_files/evaluation/corrected_3k/results_completed_20261106/FAILURES.md).
This is factual coverage across shared templates; guardrails are measured by
the separate suites above. That 3,000-case result belongs to its saved source
version before the release-date/retrieval fixes; the latest revision has separate
regression results linked above.

```bash
# Fixed-seed sample: 24 of the original 300 cases, including factual and guardrail cases.
.venv/bin/python additional_files/evaluation/local_eval.py \
  --url http://127.0.0.1:8001 --per-group 4 \
  --output additional_files/evaluation/results/my_run

# A few specific cases.
.venv/bin/python additional_files/evaluation/local_eval.py \
  --url http://127.0.0.1:8001 --ids F01,F18,U02,T02

# Separate, small suite based on the supplied requirements (13 cases).
.venv/bin/python additional_files/evaluation/local_eval.py \
  --url http://127.0.0.1:8001 \
  --cases additional_files/evaluation/requirements_cases.jsonl --all \
  --output additional_files/evaluation/results/my_requirements
```

Use `--all` on the original case file only when you actually want all 300 cases.
The runner writes each result immediately to JSONL and writes summary JSON at
the end. It preserves selected IDs, seed, dataset hash, server metadata, response,
errors, classification and behavior scores, and latency. Use distinct output
prefixes to preserve experiments. See
[the earlier smoke-test report](additional_files/evaluation/BENCHMARKS.md) for measured results.

## New architecture

1. Qwen classifies intent and all applicable guardrail labels. Blocked requests
   receive fixed refusals; mixed requests can carry multiple labels.
2. For safe factual requests, a lexical index retrieves graph entity candidates
   using full labels, graph aliases, omitted articles, and bounded fuzzy matching
   for quoted names or a trailing name. Release years help disambiguate titles.
3. A second Qwen call returns a structured plan: operation, entity, property,
   relation direction, and optionally date ordering or a numeric comparison.
   The graph context includes the custom `atai:tag` and `atai:rating` properties.
4. Python validates the plan and builds SPARQL from narrow templates. Supported
   operations are one-edge lookups in either direction, earliest/latest inverse
   lookups, distinct counts, numeric rating filters, and movie release-date
   filters. The validator rejects
   arbitrary joins, remote services, updates, unknown IDs, and invalid parameters.
5. Oxigraph executes the validated query. Graph labels, dates, and counts are
   formatted directly. Complete answers remain in metadata; displayed lists
   contain at most ten comma-separated values. Equally plausible names
   request clarification rather than accepting the model's arbitrary choice.

Safe recommendations and movie discussion are generated directly by Qwen, with
one title and a brief reason when one movie is requested. The API identifies
these as `movie_discussion` with `answer_source: language_model`; they are not
presented as graph-verified factual answers. Unsafe, prompt-injection, and out-of-scope labels stop generation and
return the existing conversation stoppers. Toxicity alongside a safe movie request
is labelled while the movie request is answered. There is no embedding-based or
personalized recommendation subsystem, arbitrary multi-hop reasoning, or conversational memory. Fuzzy
matching is bounded and can still miss names; a structured plan can still select
the wrong relation. Model safety classification is measured by evaluation rather
than assumed reliable.

## Tests

```bash
.venv/bin/python -m unittest discover -s additional_files/tests -v
```

The new contract tests use a tiny temporary graph and fake model outputs, covering
complete multi-answer retrieval, inverse/date-ordered queries, refusal routing,
query isolation, failure handling, and HTTP validation. Model quality is checked
separately by the saved live benchmarks.
