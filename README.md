# ATAI Stage 2 — Natural-language factual QA

This version extends the working Stage 1 bot with the factual part of Evaluation 2.
Embedding questions were removed from the Stage 2 scope in the October 6, 2026
course update, so this implementation focuses on natural-language factual questions.

## What changed

The bot now supports both:

1. Plain SPARQL queries from Stage 1.
2. Natural-language factual movie questions for Stage 2.

For Stage 2 the pipeline is:

```
English question
    -> identify the named entity
    -> identify the requested KG relation
    -> construct SPARQL
    -> execute it with RDFLib
    -> verbalize the answer
```

Generated SPARQL is printed in the terminal to make debugging easy.

## Files

- `src/chatbot/main.py` — chooses the graph and starts the bot
- `src/chatbot/factual_qa.py` — Stage 2 natural-language-to-SPARQL logic
- `src/chatbot/knowledge_graph.py` — RDFLib graph loading and SPARQL execution
- `src/chatbot/speakeasy_client.py` — Speakeasy transport/polling
- `tests/Test_Factual_QA.py` — tests the published Stage 2 example questions
- `tests/Test_SPARQL.py` — original small-graph Stage 1 tests
- `examples/small_graph.ttl` — tiny Stage 1 fallback graph
- `data/` — downloaded course dataset
- `requirements.txt` — dependencies

## 1. Put the real graph in the repository

Your local folder should look like:

```
chatbot-ATAI/
├── src/
│   └── chatbot/
│       ├── main.py
│       ├── factual_qa.py
│       ├── knowledge_graph.py
│       └── speakeasy_client.py
├── tests/
│   ├── Test_Factual_QA.py
│   └── Test_SPARQL.py
├── examples/
│   └── small_graph.ttl
├── requirements.txt
└── data/
    ├── graph.nt
    ├── item_ratings.csv
    ├── plots.csv
    ├── user_comments.csv
    └── user_ratings.csv
```

Only `graph.nt` is needed for the Stage 2 factual approach.

## 2. Install dependencies in a Bash terminal

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## 3. Test Stage 2 locally without Speakeasy

```bash
.venv/bin/python tests/Test_Factual_QA.py
```

The test loads `data/graph.nt` and checks the published Stage 2 examples,
including The Handmaiden, Interstellar, Manchester by the Sea, Sofia Coppola,
There Will Be Blood, and The Father.

## 4. Run the bot locally with Speakeasy

Set the bot credentials in the current terminal session:

```bash
export SPEAKEASY_USERNAME="TitaniumTwinklingSnake"
export SPEAKEASY_PASSWORD="DipInJKw"
.venv/bin/python src/chatbot/main.py
```

Do not put the password in the repository.

When `data/graph.nt` exists, `main.py` automatically selects it. You should see:

```text
Using knowledge graph: .../data/graph.nt
Loading knowledge graph: .../data/graph.nt
Loaded 2,413,825 triples.
...
Logged into Speakeasy.
Bot is running...
```

## 5. Example website questions

Send natural-language questions such as:

```text
Please answer this question with a factual approach: Who wrote the screenplay for 'The Handmaiden'?
```

Expected style:

```text
The factual answer is: Jeong Seo-kyeong and Park Chan-wook
```

The bot also still accepts the raw SPARQL queries used in Stage 1.

## Graph selection order

`main.py` uses:

1. `KNOWLEDGE_GRAPH_PATH`, if explicitly set.
2. `/space_mounts/atai-hs26/dataset/graph.nt` on Nuvolos.
3. `data/graph.nt` locally.
4. `examples/small_graph.ttl` only as a final fallback.

If the small graph is selected, the program prints a warning because it is not
sufficient for realistic Stage 2 questions.

## Git

The `data/` contents and `.env` are ignored. Do not commit the large course
dataset or credentials.
