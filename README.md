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

- `main.py` — chooses the graph and starts the bot
- `factual_qa.py` — Stage 2 natural-language-to-SPARQL logic
- `SPARQL_setup.py` — RDFLib graph loading and SPARQL execution
- `speakeasy_client.py` — Speakeasy transport/polling
- `Test_Factual_QA.py` — tests the published Stage 2 example questions
- `Test_SPARQL.py` — original small-graph Stage 1 tests
- `small_graph.ttl` — tiny Stage 1 fallback graph
- `dataset/` — put the downloaded course dataset here
- `requirement.txt` — dependencies

## 1. Put the real graph in the repository

Your local folder should look like:

```
chatbot-ATAI/
├── main.py
├── factual_qa.py
├── SPARQL_setup.py
├── speakeasy_client.py
├── Test_Factual_QA.py
├── Test_SPARQL.py
├── small_graph.ttl
├── requirement.txt
└── dataset/
    ├── graph.nt
    ├── item_ratings.csv
    ├── plots.csv
    ├── user_comments.csv
    └── user_ratings.csv
```

Only `graph.nt` is needed for the Stage 2 factual approach.

## 2. Install dependencies on Windows PowerShell

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirement.txt
```

## 3. Test Stage 2 locally without Speakeasy

```powershell
.\.venv\Scripts\python.exe Test_Factual_QA.py
```

The test loads `dataset/graph.nt` and checks the published Stage 2 examples,
including The Handmaiden, Interstellar, Manchester by the Sea, Sofia Coppola,
There Will Be Blood, and The Father.

## 4. Run the bot locally with Speakeasy

Set the bot credentials in the current PowerShell session:

```powershell
$env:SPEAKEASY_USERNAME="TitaniumTwinklingSnake"
$env:SPEAKEASY_PASSWORD="YOUR_BOT_PASSWORD"
.\.venv\Scripts\python.exe main.py
```

Do not put the password in the repository.

When `dataset/graph.nt` exists, `main.py` automatically selects it. You should see:

```
Using knowledge graph: ...\dataset\graph.nt
Loading knowledge graph: ...\dataset\graph.nt
Loaded 2,413,825 triples.
...
Logged into Speakeasy.
Bot is running...
```

## 5. Example website questions

Send natural-language questions such as:

```
Please answer this question with a factual approach: Who wrote the screenplay for 'The Handmaiden'?
```

Expected style:

```
The factual answer is: Jeong Seo-kyeong and Park Chan-wook
```

The bot also still accepts the raw SPARQL queries used in Stage 1.

## Graph selection order

`main.py` uses:

1. `KNOWLEDGE_GRAPH_PATH`, if explicitly set.
2. `/space_mounts/atai-hs26/dataset/graph.nt` on Nuvolos.
3. `dataset/graph.nt` locally.
4. `small_graph.ttl` only as a final fallback.

If the small graph is selected, the program prints a warning because it is not
sufficient for realistic Stage 2 questions.

## Git

The `dataset/` contents and `.env` are ignored. Do not commit the large course
dataset or credentials.
