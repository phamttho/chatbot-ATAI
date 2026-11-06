# Local movie knowledge graph assistant

`python main.py` starts the Qwen3.5-4B movie agent on Speakeasy,
using the credentials already configured in the root `main.py`. The local HTTP
entry point (`python local.py`) runs the same agent without connecting to Speakeasy.
Legacy and local-API support files are kept in `additional_files/evaluation/`;
the Speakeasy deployment uses the active agent modules in `additional_files/src/chatbot/`.

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

## Install

Use Python 3.11+ and a virtual environment. Install the CUDA-enabled PyTorch build
appropriate for your device first, then:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Tested on NVIDIA GB10 with PyTorch 2.12.0+cu130 and Transformers 5.12.1; exact
package versions used for the benchmarks are in
`additional_files/evaluation/results/environment.json`. The working environment
on this machine reuses the preinstalled CUDA packages via a local `.pth` file;
that machine-specific setup is not needed with a normal PyTorch installation.
CUDA is preferred automatically, then MPS, then CPU. `--device` overrides this
for the new implementation. The GB10 needs a PyTorch build supporting its GPU
architecture; an older CUDA wheel may not work. BF16 is used on CUDA GPUs that
support it, and FP16 on other CUDA GPUs. MPS and CPU use float32 for compatibility.
MPS was not benchmarked here.

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

## Evaluation

The saved Qwen 3.5 4B benchmark scored **2,966/3,000 (98.87%)** on complete
answers and query grounding. See the [benchmark report](additional_files/evaluation/BENCHMARK.md).
It was run against an earlier saved source revision, so it is a historical
benchmark rather than a measurement of every later code change.

For a quick local HTTP evaluation, start `local.py` and run `local_eval.py` with
the retained `test_cases.jsonl` dataset. Results can be saved under
`additional_files/evaluation/`.

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
presented as graph-verified factual answers. Blocked labels stop generation and
return the existing conversation stoppers. There is no embedding-based or
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
