# LiveLogic - Neuro-Symbolic Reasoning Agents

LiveLogic is a voice-enabled reasoning agents system that combines **LiveKit** for real-time voice, **DSPy** for structured LLM orchestration, **Clingo** (Answer Set Programming) as the ground-truth symbolic solver, and a **Next.js React UI**.

## Mission

LiveLogic delivers mathematically sound security policy conversations with full auditability, explainability, and formal proof traces — not probabilistic guesses.

> Unlike traditional LLM agents that can hallucinate answers and actions, LiveLogic converts natural language into first-order logic. It achieves 100% reasoning accuracy within the defined policy bounds by delegating decision-making to a symbolic solver (Clingo), using the LLM only as a linguistic interface.

## Architectures

### Core Neuro-Symbolic Pipeline (Reasoner)

```
User Input → DSPy Extractor → Session State (SQLite) → Clingo Solver
                                        → DSPy Critic (on UNSAT) → DSPy Translator → Output + Live Trace
```

1. **Extract**: Natural language → DSPy → valid ASP facts
2. **Solve**: Accumulated facts and rules → Clingo (multi-model, unsat cores)
3. **Critique**: UNSAT → human-readable conflict explanation with suggested retraction
4. **Translate**: Answer sets → natural language with step-by-step reasoning

### Voice Pipeline

```
Browser (localhost:3000)
    ↓ WebRTC
LiveKit
    ↓ 
Python Agent
    ↓ Voice API or Chat API
    ↓
    DSPy → Clingo → Voice API or Chat API → Browser
```

## Key Features

### Core Reasoner
- **State Accumulation**: Per-session fact storage in SQLite with LRU eviction (max 50 facts)
- **Conflict Detection**: Two-phase consistency checks (syntactic + Clingo UNSAT)
- **Fact Retraction**: Dedicated endpoint for corrections
- **Proactive Contradiction Alerts**
- **Full Audit Trail**: JSON traces

### Voice UI Demo
- Real-time voice-to-voice
- Built-in search tools
- Audio visualizers and chat transcript
- Next.js React frontend with shadcn/ui

## Domain: Security Operations (Incident Triage)

Handles queries like "Was this access pattern a policy violation?" reasoning over:
- User roles and permissions (RBAC)
- Resource access events with temporal constraints
- Explicit deny rules
- Session state (active users, resources)
- Time windows (e.g., "within last 24 hours")
- Multi-step reasoning (e.g., "Does this user have access to this resource?")
- Multi-model answers (e.g., "Which of these users could have accessed this resource?")
- Formal proof traces
- Policy conflict detection

Returns answers grounded in formal logic proof traces.

## Quickstart: Grok Voice Agent UI Demo

### Prerequisites
- [LiveKit Cloud account](https://cloud.livekit.io)
- [LLM API key] eg. Grok (https://console.x.ai) with Grok Voice API access
- Python 3.11+, Node.js/pnpm
- Clingo
### 1. Install dependencies
```bash
# Backend
uv pip install livekit-agents[xai,silero,turn-detector] livekit-plugins-noise-cancellation python-dotenv

# Frontend
cd agent-ui
pnpm install
```

### 2. Download models
```bash
uv run grok_voice_agent_api.py download-files
```

### 3. Start
**Recommended: One-command**
```bash
./start.sh
```

**Or separate:**
- Frontend: `cd agent-ui && pnpm dev` (http://localhost:3000)
- Backend: `uv run grok_voice_agent_api.py dev`

### 4. Test
1. Open http://localhost:3000
2. Click "Start call"
3. Ask: "What is Elon Musk's most recent X post?"

## Environment Variables

Copy `.env.example` to `.env.local` and fill:
| Variable | Description |
|----------|-------------|
| `LIVEKIT_API_KEY` | LiveKit API key |
| `LIVEKIT_API_SECRET` | LiveKit API secret |
| `LIVEKIT_URL` | LiveKit URL (wss://...) |
| `XAI_API_KEY` | xAI API key |

## Core Reasoner (Standalone)

### Install extras
```bash
pip install -r requirements.txt  # DSPy, etc.
export OPENAI_API_KEY="sk-..."  # or other LLM
# Install Clingo: brew install clingo / apt-get install clingo
```

### Run
```bash
uvicorn reasoner.app.main:app --reload --port 8000
```

### API Endpoints
| Method | Path | Description |
|--------|------|-------------|
| POST | `/reason` | Submit transcript |
| POST | `/retract` | Retract fact |
| GET | `/trace/{session_id}` | Get trace |
| GET | `/sessions/{session_id}/state` | Session state |
| GET | `/health` | Health |

**Example:**
```bash
curl -X POST http://localhost:8000/reason -H "Content-Type: application/json" -d '{\"session_id\": "demo-1", "transcript\": "User John accessed DB at 3AM. John is analyst."}'
```

## Available Commands
```bash
uv run grok_voice_agent_api.py dev     # Voice agent dev
uv run grok_voice_agent_api.py console # Local console test
uv run grok_voice_agent_api.py download-files
python tests/test_clingo.py            # Core tests
```

## Project Structure
```
├── grok_voice_agent_api.py      # LiveKit + Grok agent
├── start.sh                     # Start script
├── agent/                       # Agent code
├── agent-ui/                    # Next.js UI (full app)
├── reasoner/                    # Core engine
│   ├── app/                     # FastAPI + DSPy + Clingo
│   └── asp/security.lp          # Policy rules
├── shared/                      # Utils
├── tests/                       # Tests
├── requirements.txt
├── pyproject.toml
└── README.md
```

## Roadmap
- [x] Phase 1: Formal Logic Engine (DSPy + Clingo + FastAPI)
- [x] Phase 2: Voice UI (LiveKit + Grok + Next.js)
- [ ] Phase 3: Full integration (Voice → Reasoner pipeline)
- [ ] Phase 4: Polish, evals, production deploy

## Documentation
- [LiveKit Agents](https://docs.livekit.io/agents)
- [xAI Grok Voice](https://docs.livekit.io/agents/integrations/xai)
- [DSPy](https://dspy.ai)
- [Clingo ASP](https://potassco.org/clingo)

## License
MIT
