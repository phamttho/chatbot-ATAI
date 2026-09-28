# ATAI Stage 1 — Speakeasy + SPARQL

This version keeps the team's working Speakeasy implementation as the baseline and hardens it for the Stage 1 online setup check.

## Files

- `main.py` — starts the bot
- `speakeasy_client.py` — Speakeasy transport/polling
- `SPARQL_setup.py` — loads the RDF graph and executes plain SPARQL
- `Test_SPARQL.py` — local smoke tests
- `small_graph.ttl` — tiny local test graph only
- `requirement.txt` — Python dependencies

## Local test

```bash
pip install -r requirement.txt
python Test_SPARQL.py
```

## Run against Speakeasy

Set the bot credentials as environment variables rather than putting passwords in Git:

```bash
export SPEAKEASY_USERNAME='YOUR_BOT_USERNAME'
export SPEAKEASY_PASSWORD='YOUR_BOT_PASSWORD'
python main.py
```

For the real course knowledge graph, set its path before starting the bot:

```bash
export KNOWLEDGE_GRAPH_PATH='/path/to/the/provided/course/graph.ttl'
python main.py
```

`small_graph.ttl` is only for local testing and must not be mistaken for the evaluation knowledge graph.

## Important

The current HTTP routes are retained because this exact client has already been demonstrated working with Speakeasy. If the official course `Speakeasy-Python-Client-Library` becomes available, compare/adapt the transport layer while leaving the SPARQL agent logic independent.
