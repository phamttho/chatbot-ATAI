"""Local HTTP transport shared by the legacy baseline and the LLM-first agent."""
import argparse
import os
import sys
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'additional_files/src/chatbot'))


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class LegacyAdapter:
    def __init__(self, graph):
        from factual_qa import FactualQAAgent
        from stage3_agent import Stage3Agent
        self.agent = Stage3Agent(FactualQAAgent(graph))
        if self.agent.llm is None:
            raise RuntimeError('Baseline requires its original Qwen model; refusing a silently degraded benchmark.')
        self.model_name = self.agent.llm.model_name
        self.device = self.agent.llm.device
        self.revision = getattr(self.agent.llm.model.config, '_commit_hash', None)

    def chat(self, message):
        import stage3_agent
        from unittest.mock import patch
        labels, calls, graph_calls = [], [], []
        classifier = stage3_agent.classify_message
        generate = self.agent.llm._generate
        run_query = self.agent.factual_agent._run_query
        def trace_query(query, *args, **kwargs):
            answers, error = run_query(query, *args, **kwargs)
            graph_calls.append((query, answers))
            return answers, error
        def classify(*args, **kwargs):
            label = classifier(*args, **kwargs)
            labels.append(label)
            return label
        def traced(*args, **kwargs):
            calls.append(1)
            return generate(*args, **kwargs)
        with patch.object(stage3_agent, 'classify_message', classify), patch.object(self.agent.llm, '_generate', traced), patch.object(self.agent.factual_agent, '_run_query', trace_query):
            answer = self.agent.handle_message(message)
        return dict(answer=answer, labels=labels[:1], category=labels[0] if labels else None,
                    route=self.agent.last_route, llm_calls=len(calls), query=graph_calls[-1][0] if graph_calls else None,
                    answers=graph_calls[-1][1] if graph_calls and self.agent.last_route == 'knowledge_graph' else [])


def create_app(agent, engine):
    app = FastAPI(title='Local movie knowledge graph assistant')
    # Model decoding and legacy tracing are deliberately serialized.
    lock = threading.Lock()
    @app.get('/health')
    def health():
        return dict(status='ready', engine=engine, model=agent.model_name, device=agent.device,
                    revision=getattr(agent, 'revision', None),
                    version=getattr(agent, 'version', None),
                    source_hashes=getattr(agent, 'source_hashes', None))
    @app.post('/chat')
    def chat(request: ChatRequest):
        if not request.message.strip():
            raise HTTPException(422, 'message must not be blank')
        started = time.perf_counter()
        with lock:
            result = agent.chat(request.message)
        return dict(result, latency_ms=round((time.perf_counter()-started)*1000, 2))
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=['legacy', 'llm'], default='llm')
    parser.add_argument('--graph', type=Path, default=Path(os.environ.get('KNOWLEDGE_GRAPH_PATH', ROOT/'additional_files/data/graph.nt')))
    parser.add_argument('--model', help='Hugging Face model ID or local snapshot directory')
    parser.add_argument('--device', choices=['auto', 'cuda', 'mps', 'cpu'], default='auto')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    if args.engine == 'legacy':
        if args.model:
            os.environ['MOVIE_LLM_MODEL'] = args.model
        agent = LegacyAdapter(args.graph)
    else:
        from movie_agent import MovieAgent
        agent = MovieAgent(args.graph, args.model or os.environ.get('MOVIE_LLM_MODEL', 'Qwen/Qwen3.5-4B'), args.device)
    import uvicorn
    uvicorn.run(create_app(agent, args.engine), host=args.host, port=args.port)
