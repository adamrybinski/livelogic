# LiveLogic - Neuro-Symbolic "Thinking Out Loud" Reasoning Agent

A voice-enabled reasoning agent that combines **LiveKit** for real-time voice, **DSPy** for structured LLM orchestration, and **Clingo** (Answer Set Programming) as the ground-truth symbolic solver.

## Mission

LiveLogic delivers mathematically sound security policy advice with full auditability, explainability, and formal proof traces — not probabilistic guesses.

> Unlike traditional LLM agents that can hallucinate policy permissions, LiveLogic converts natural language into first-order logic. It achieves 100% reasoning accuracy within the defined policy bounds by offloading decision-making to a symbolic solver (Clingo), using the LLM only as a linguistic interface.

## Architecture

```
User Voice → LiveKit Agent (Deepgram STT + Cartesia/OpenAI TTS)
                                → FastAPI Reasoner
                                → DSPy Extractor → Session State (SQLite) → Clingo Solver
                                → DSPy Critic (on UNSAT) → DSPy Translator → TTS + Live Trace UI
```

### Neuro-Symbolic Pipeline

1. **Extract**: Transcript → DSPy → valid ASP facts
2. **Solve**: Accumulated facts + security.lp → Clingo (multi-model, unsat cores)
3. **Critique**: UNSAT → human-readable conflict explanation with suggested retraction
4. **Translate**: Answer sets → natural language with step-by-step reasoning

### Key Features

- **State Accumulation**: Per-session fact storage in SQLite with LRU eviction (max 50 facts)
- **Conflict Detection**: Two-phase consistency checks (syntactic + Clingo UNSAT)
- **Fact Retraction**: Dedicated endpoint for corrections/interruptions
- **Proactive Contradiction Alerts**: "Earlier you mentioned X. New fact Y makes this impossible."
- **Full Audit Trail**: Every turn logged with input/output JSON traces

## Domain: Security Operations (Incident Triage)

Handles voice queries like "Was this access pattern a policy violation?" by reasoning over:
- User roles and permissions (RBAC)
- Firewall rules and forbidden subnets
- Resource access events with temporal constraints
- Explicit deny rules

Returns grounded yes/no answers with formal proof traces.

## Quick Start

### Prerequisites

- Python 3.11+
- Clingo (ASP solver)
- OpenAI API key (for DSPy)

### Install

```bash
# Install Clingo
apt-get install clingo  # Debian/Ubuntu
# or: brew install clingo  # macOS

# Install Python dependencies
pip install -r requirements.txt

# Set your OpenAI API key
export OPENAI_API_KEY="sk-..."
```

### Run the Reasoner

```bash
uvicorn reasoner.app.main:app --reload --port 8000
```

### Run Tests

```bash
python tests/test_clingo.py
```

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/reason` | Submit transcript for reasoning |
| POST | `/retract` | Retract a previously added fact |
| GET | `/trace/{session_id}` | Get full reasoning trace |
| GET | `/sessions/{session_id}/state` | Get current session state |
| GET | `/health` | Health check |

### Example Request

```bash
curl -X POST http://localhost:8000/reason \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-1",
    "transcript": "User John accessed the database server at 3 AM. John is an analyst."
  }'
```

## Project Structure

```
├── reasoner/
│   ├── asp/
│   │   └── security.lp          # ASP knowledge base
│   ├── app/
│   │   ├── clingo_reasoner.py   # Async Clingo wrapper
│   │   ├── dspy_pipeline.py     # DSPy signatures + validation
│   │   ├── orchestrator.py      # Session state + pipeline
│   │   └── main.py              # FastAPI service
│   └── data/                    # SQLite session store (auto-created)
├── agent/
│   └── livekit_agent.py         # LiveKit voice agent (Phase 2)
├── frontend/                    # React Live Trace UI (Phase 2)
├── shared/                      # Shared types and utilities
├── tests/
│   └── test_clingo.py           # ClingoReasoner tests
├── Dockerfile
├── requirements.txt
└── README.md
```

## Roadmap

- [x] Phase 1: Formal Logic Engine (Symbolic Core + DSPy Bridge + FastAPI)
- [ ] Phase 2: High-Accuracy Voice & Live Trace UI
- [ ] Phase 3: Portfolio & Polish (DSPy evals, fallbacks, deployment)

## License

MIT
