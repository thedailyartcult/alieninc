# Phase 6: AI Integration — LLM-Powered Features

## Overview

**Status**: ✅ COMPLETE — all phases implemented, tested, and committed on `master`

Commit trail (do NOT re-implement these; they are done and verified):
- `f27af7683` — core integration: 5 Go alphacore AI commands, Rust mcp-client bridge, fixed interview_agent syntax error, Ollama LLM merge (OLLAMA_DISABLE=1), fixed decision_assistant recursion, memory_system 16 helpers + CMB durability, mcp_server.py handlers wired
- `9989ccb83` — web platform: /api/ai/interview|coach|analyze|narrate|memory routes + AI Agents dashboard tab
- `522abdda5` — AI pipeline: ai/pipeline.py (interview → simulate → analyze → coach → narrate → memory), /api/ai/pipeline route + dashboard button

This phase implements comprehensive AI-powered features for the Alpha Zero multiverse simulation platform. The goal is to integrate 5 AI agents that enhance user experience with personality profiling, life coaching, decision analysis, narrative generation, and persistent learning.

## Current State

### ✅ COMPLETED - Infrastructure
- **5 AI Agents Implemented** (all production-ready)
- **23 Alpha Zero MCP Tools** (5 new AI tools added)
- **CMB Memory Integration** (all agent data persists across sessions)
- **Free LLM Framework** (ready for Ollama/OpenRouter integration)

### AI Agent Stack
1. **interview_agent.py** - Personality profiler (34 social variables)
2. **life_coach.py** - Life coaching and recommendations
3. **decision_assistant.py** - Simulation outcome analysis
4. **storyteller.py** - Narrative generation from simulation data
5. **memory_system.py** - Persistent learning across sessions

## Architecture

### Core Components
- **Go Native Core**: `alpha-zero-engine/core/alphacore/main.go` (593 lines)
- **Rust MCP Client**: `rust/mcp-client/src/lib.rs`
- **MCP Server**: `alpha-zero-engine/mcp_integration.py` (650 lines)
- **Web Platform**: `alpha-zero-engine/web/`

### Integration Points
1. **Character Profiling** - 34 social variables across 5 layers
2. **Memory Persistence** - CMB system for cross-session learning
3. **API Commands** - JSON-based protocol for Go native core
4. **Async Operations** - Rust MCP client with async handlers

## New MCP Tools (5 Added)

### 1. alpha_zero_interview
**Purpose**: Conduct AI personality interviews and generate character profiles

**Parameters**:
- `name` (string): Character name
- `age` (integer): Starting age
- `gender` (string): Gender (male, female, non_binary)
- `initial_interview_text` (string): Initial interview message
- `workspace` (string): CMB workspace
- `repo` (string): Repository scope

**Returns**: Character profile with 34 social variables

### 2. alpha_zero_coach
**Purpose**: Provide AI life coaching advice based on character state

**Parameters**:
- `workspace` (string): CMB workspace
- `character_json` (string): Character state as JSON
- `situation` (string): Life situation to provide coaching for
- `repo` (string): Repository scope
- `session_id` (string): Session ID

**Returns**: Coaching analysis, recommendations, and action plans

### 3. alpha_zero_analyze
**Purpose**: Analyze simulation outcomes and provide strategic decision guidance

**Parameters**:
- `workspace` (string): CMB workspace
- `simulation_results` (array): Array of simulation result objects
- `repo` (string): Repository scope

**Returns**: Path analysis, risk assessment, recommendations

### 4. alpha_zero_narrate
**Purpose**: Generate compelling narratives from simulation data

**Parameters**:
- `workspace` (string): CMB workspace
- `character_name` (string): Character name
- `simulation_result` (object): Single simulation result object
- `repo` (string): Repository scope

**Returns**: Character narratives with stories and insights

### 5. alpha_zero_memory
**Purpose**: Store, retrieve, and manage AI learnings with retention policies

**Parameters**:
- `workspace` (string): CMB workspace
- `operation` (string): Operation type ('store', 'retrieve', 'update', 'delete', 'create_session')
- `data` (object): Data payload for the operation
- `query` (string): Search query for retrieval
- `session_id` (string): Session ID
- `repo` (string): Repository scope

**Returns**: Learning management with persistence across sessions

## Implementation Plan

### Phase 6.1: Go Native Core Integration
1. **Add AI agent commands** to `alphacore/main.go`
2. **Implement command handlers** for interview, coach, analyze, narrate, memory
3. **Add JSON request/response protocols** for each new command
4. **Test parity** with existing Python implementations

**New Commands to Add**:
- `interview` - Process character interviews and generate profiles
- `coach` - Provide coaching advice based on character state
- `analyze` - Analyze simulation outcomes and decisions
- `narrate` - Generate narratives from simulation data
- `memory` - Store/retrieve learnings across sessions

### Phase 6.2: Rust MCP Client Updates
1. **Add handlers** in `rust/mcp-client/src/lib.rs`
2. **Implement async command processing** for AI agents
3. **Add JSON serialization** for Go-Python communication
4. **Update Cargo.toml** with new dependencies

### Phase 6.3: Free LLM Integration
1. **Set up local Ollama** instance
2. **Integrate OpenRouter API** as fallback
3. **Update interview_agent.py** to use LLM for extraction
4. **Enhance coaching agents** with LLM-powered advice

## Code Examples

### New Go Command Structure
```go
type InterviewRequest struct {
    Name string `json:"name"`
    Age int `json:"age"`
    Gender string `json:"gender"`
    InitialInterviewText string `json:"initial_interview_text"`
}

type CoachingRequest struct {
    Workspace string `json:"workspace"`
    CharacterJSON string `json:"character_json"`
    Situation string `json:"situation"`
}

func cmdInterview(req InterviewRequest) {
    // Process interview and generate character profile
    // Later: integrate with LLM via API call
    // Return character JSON
}

func cmdCoach(req CoachingRequest) {
    // Generate coaching advice based on character state
    // Integrate with existing Python coaching logic
    // Return recommendations JSON
}
```

### New MCP Tool Example
```python
ALPHA_ZERO_TOOLS["alpha_zero_interview"] = {
    "description": "Conduct AI personality interview and generate character profile with 34 social variables.",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Character name"},
            "age": {"type": "integer", "description": "Starting age"},
            "gender": {"type": "string", "description": "Gender (male, female, non_binary)"},
            "initial_interview_text": {"type": "string", "description": "Initial interview message"},
            "workspace": {"type": "string", "description": "CMB workspace"},
            "repo": {"type": "string", "description": "Repository scope"},
        },
    },
}
```

## Testing Strategy

### Unit Tests
1. **Go Core Tests**: `tests/test_native_core.py` - parity testing
2. **MCP Client Tests**: Rust unit tests for new handlers
3. **Integration Tests**: End-to-end AI agent integration
4. **LLM Fallback Tests**: Mock LLM API responses

### Test Scenarios
- Interview extraction accuracy
- Coaching recommendation relevance
- Decision analysis validity
- Narrative coherence
- Memory retention across sessions

## Free LLM Setup

### Local Option: Ollama
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull models for AI agents
ollama pull llama3.1
ollama pull qwen2.5
```

### Cloud Option: OpenRouter
```python
# Example integration for interview agent
import requests

def extract_persona_with_llm(interview_text):
    headers = {
        "Authorization": "Bearer YOUR_OPENROUTER_KEY",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "openrouter/quwen/qwen2.5-32b",
        "messages": [{"role": "user", "content": interview_text}],
        "temperature": 0.7
    }
    
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload
    )
    
    return response.json()
```

## Development Workflow

### 1. Setup
```bash
# Build Go native core
./core/scripts/build_core.sh

# Update Rust MCP client
# cargo build --release
```

### 2. Implementation
```bash
# Add AI commands to alphacore/main.go
# Update mcp_integration.py with new tools
# Enhance AI agents with LLM integration
```

### 3. Testing
```bash
# Run Go parity tests
pytest tests/test_native_core.py

# Run MCP integration tests
# cargo test --lib

# Run end-to-end integration tests
python -m pytest tests/ -v
```

### 4. Verification
```bash
# Verify Go binary builds
./bin/alphacore forecast < test_input.json

# Test MCP server integration
python -c "from alpha_zero_engine.mcp_integration import ALPHA_ZERO_TOOLS; print(len(ALPHA_ZERO_TOOLS))"
```

## Quality Metrics

### Performance
- **Response Time**: < 100ms for AI agent operations
- **Memory Usage**: < 50MB per agent instance
- **Throughput**: 1000+ concurrent users

### Reliability
- **Uptime**: > 99.9%
- **Accuracy**: > 95% for AI agent outputs
- **Retention**: 100% for cross-session learning

### Scalability
- **Horizontal Scaling**: Add multiple Go core instances
- **Vertical Scaling**: Optimize AI agent resource usage
- **Distributed Processing**: Split heavy computations across nodes

## Documentation

### API Reference
- [MCP Tool Documentation](#mcp-tool-definitions)
- [Go Command Reference](#go-command-reference)
- [AI Agent API](#ai-agent-api)
- [Integration Guide](#integration-guide)

### Architecture Diagrams
- System overview with AI agents
- Data flow between Go core and AI agents
- CMB memory integration architecture
- MCP server tool registry

## Troubleshooting

### Common Issues
1. **Go Binary Not Found**: Run `./core/scripts/build_core.sh`
2. **MCP Server Connection**: Check workspace configuration
3. **LLM API Keys**: Set environment variables correctly
4. **Memory Storage**: Verify CMB system is running

### Debug Commands
```bash
# Check Go binary
_find_binary()

# Test MCP server
python -c "from alpha_zero_engine.mcp_integration import ALPHA_ZERO_TOOLS; print(ALPHA_ZERO_TOOLS.keys())"

# Verify CMB integration
python -c "import cmb; print(cmb.list_workspaces())"
```

## Next Steps

### Immediate Actions (ALL DONE — see commits above)
1. ✅ **Build Go native core** with AI agent command support
2. ✅ **Add Rust MCP client handlers** for new commands
3. ✅ **Integrate free LLM** for interview extraction
4. ✅ **Update web platform** with AI agent UI
5. ✅ **Run comprehensive tests** to verify integration

### Long-term Roadmap
1. **Add more AI agents** (financial advisor, health coach, mentor)
2. **Implement advanced ML** for better predictions
3. **Add real-time AI** for interactive experiences
4. **Create AI agent marketplace** for custom solutions
5. **Production deployment** + monitoring/analytics (guide's next steps 3-4)

## Success Criteria

### Phase 6.1 (Go Core Integration) - DONE ✅ (commit f27af7683)
- ✅ All 5 AI agent commands implemented in Go
- ✅ JSON protocol compatibility verified
- ✅ Parity testing completed
- ✅ Performance benchmarks met

### Phase 6.2 (MCP Client Updates) - DONE ✅ (commit f27af7683)
- ✅ AI agent MCP tools added
- ✅ Rust client handlers ready
- ✅ Async operations implemented
- ✅ Testing framework established

### Phase 6.3 (LLM Integration) - DONE ✅ (commit f27af7683)
- ✅ Free LLM framework prepared
- ✅ Local Ollama setup documentation
- ✅ OpenRouter API integration plan
- ✅ Fallback mechanism designed

### Web Platform Integration - DONE ✅ (commit 9989ccb83)
- ✅ /api/ai/interview|coach|analyze|narrate|memory Flask routes
- ✅ AI Agents dashboard tab
- ✅ 6 web route tests (in test_ai_integration.py)

### AI Pipeline - DONE ✅ (commit 522abdda5)
- ✅ ai/pipeline.py end-to-end workflow (persona → simulate → analyze → coach → narrate → memory)
- ✅ /api/ai/pipeline route + "Full AI Pipeline" dashboard button
- ✅ Pipeline integration test

### Complete Integration - DONE ✅ (verified)
- ✅ All AI agents working with Go native core
- ✅ Cross-session learning persistent
- ✅ Web platform AI features complete
- ✅ End-to-end testing successful (21 AI tests + 26 engine tests pass)
- ⏳ Production deployment ready (NOT deployed yet — roadmap item 5)

### KNOWN FAILURES (pre-existing, unrelated to Phase 6 — do not chase)
- `test_event_balance.py::test_full_life_balance_avg_lifespan` — avg lifespan 55.1 vs 60 threshold (simulation balance issue)
- `test_infra.py::test_run_log` — needs Redis on 127.0.0.1:6379 (test env issue)

### Test commands (exact)
```bash
PATH=/tmp/opencode/go/bin:$PATH /tmp/opencode/az-venv/bin/python -m pytest test_ai_integration.py -q
OLLAMA_DISABLE=1 PATH=/tmp/opencode/go/bin:$PATH /tmp/opencode/az-venv/bin/python -m pytest test_ai_integration.py alpha-zero-engine/tests/ -q
# Rust: cd rust/mcp-client && RUSTUP_HOME=/tmp/opencode/rustup CARGO_HOME=/tmp/opencode/cargo PATH=/tmp/opencode/cargo/bin:$PATH cargo test
# Go build: cd alpha-zero-engine/core/alphacore && PATH=/tmp/opencode/go/bin:$PATH go build -o ../bin/alphacore .
```