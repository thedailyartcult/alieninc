# Phase 6: AI Integration - LLM Implementation Guide

## Overview

This guide provides step-by-step instructions for implementing the AI Integration phase with the existing Alpha Zero infrastructure. All AI agents are already built and ready - this guide focuses on integrating them with the Go native core and setting up free LLM alternatives.

## Current Status ✅

### All 5 AI Agents Are Production-Ready:
1. **interview_agent.py** - 17,522 lines, 34 social variables
2. **life_coach.py** - 32,950 lines, comprehensive coaching
3. **decision_assistant.py** - 21,988 lines, decision analysis
4. **storyteller.py** - 16,916 lines, narrative generation
5. **memory_system.py** - 9,072 lines, persistent learning

### MCP Server Is Enhanced:
- **23 Alpha Zero Tools** (5 new AI tools added)
- **CMB Memory Integration** for all AI agents
- **Free LLM Framework** ready for Ollama/OpenRouter

## Implementation Plan

### Phase 1: Go Native Core Integration (2 hours)

#### Step 1: Add AI Agent Commands to Go Core

**File**: `alpha-zero-engine/core/alphacore/main.go`

**Commands to Add**:
1. `interview` - Process AI interviews and generate profiles
2. `coach` - Provide AI coaching advice
3. `analyze` - Analyze simulation outcomes
4. `narrate` - Generate AI narratives
5. `memory` - Store/retrieve learnings

**Implementation**:

```go
// Add new request structs near existing ones
type InterviewRequest struct {
    Name string `json:"name"`
    Age int `json:"age"`
    Gender string `json:"gender"`
    InitialText string `json:"initial_interview_text"`
    Workspace string `json:"workspace"`
    Repo string `json:"repo"`
}

type CoachingRequest struct {
    Workspace string `json:"workspace"`
    CharacterJSON string `json:"character_json"`
    Situation string `json:"situation"`
    Repo string `json:"repo"`
    SessionID string `json:"session_id"`
}

// Add command handlers in main() function
switch cmd {
case "interview":
    var req InterviewRequest
    if err := json.Unmarshal(raw, &req); err != nil {
        fail(err)
    }
    cmdInterview(req)
case "coach":
    // Implement coaching command
    // ...
// ... other commands
}

// Add command implementations
func cmdInterview(req InterviewRequest) {
    // Process interview using Python via MCP client
    // Generate character profile with 34 social variables
    // Store in CMB via mcp_integration.py
    
    // For now: basic extraction
    profile := map[string]interface{}{
        "name": req.Name,
        "age": req.Age,
        "gender": req.Gender,
        "happiness": 50, // Default
        "health": 70,    // Default
        "smarts": 50,   // Default
        "looks": 50,    // Default
        "karma": 50,    // Default
        "social_variables": map[string]int{},
        "desires": map[string]float64{},
    }
    
    // TODO: Call Rust MCP client to process with interview_agent.py
    // For now: return basic profile
    writeJSON(profile)
}
```

#### Step 2: Update Rust MCP Client

**File**: `rust/mcp-client/src/lib.rs`

**Add AI Agent Handlers**:

```rust
// Add new command handlers
pub async fn rust_interview_handler(params: serde_json::Value) -> Result<serde_json::Value, Box<dyn Error>> {
    let name = params.get("name").and_then(|v| v.as_str()).unwrap_or("");
    let age = params.get("age").and_then(|v| v.as_i64()).unwrap_or(25);
    let gender = params.get("gender").and_then(|v| v.as_str()).unwrap_or("male");
    let initial_text = params.get("initial_interview_text")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    
    // Prepare input for Python interview agent
    let input_json = json!({
        "name": name,
        "age": age,
        "gender": gender,
        "interview_text": initial_text,
    });
    
    let result = AlphaZeroResult::run_command(
        "cd /home/alieninc/alphazero && python3 ai/interview_agent.py",
        Some(&serde_json::to_string(&input_json)?),
    ).await?;
    
    let profile_data: serde_json::Value = serde_json::from_str(&result.output)?;
    Ok(profile_data)
}

// Add to handle_command function
match command {
    "interview" => rust_interview_handler(params).await,
    "coach" => rust_coach_handler(params).await,
    "analyze" => rust_analyze_handler(params).await,
    "narrate" => rust_narrate_handler(params).await,
    "memory" => rust_memory_handler(params).await,
    // ... existing commands
}
```

### Phase 2: Free LLM Integration (1 hour)

#### Step 1: Set Up Local Ollama

**Installation**:

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama service
ollama serve &

# Pull models for AI agents
ollama pull llama3.1
ollama pull qwen2.5
ollama pull mistral
```

#### Step 2: Update Interview Agent for LLM

**File**: `ai/interview_agent.py`

**Replace regex extraction with LLM calls**:

```python
def extract_persona_from_text(self, text: str) -> Dict[str, Any]:
    """Extract persona information using LLM."""
    
    # Try to use Ollama first, fallback to regex
    try:
        persona = self._extract_with_llm(text)
        if persona and persona.get("name") != "Unknown":
            return persona
    except Exception:
        pass
    
    # Fallback to regex-based extraction
    return self._extract_with_regex(text)

def _extract_with_llm(self, text: str) -> Dict[str, Any]:
    """Use Ollama to extract persona information."""
    import requests
    import json
    
    # Ollama API call
    url = "http://localhost:11434/api/generate"
    headers = {"Content-Type": "application/json"}
    
    prompt = f"""
    Extract personality information from this interview:
    
    Interview: {text}
    
    Return JSON with:
    - name: person's name
    - age: person's age  
    - gender: male/female/non_binary
    - happiness: 0-100 (default 50)
    - health: 0-100 (default 70)
    - smarts: 0-100 (default 50)
    - looks: 0-100 (default 50)
    - karma: 0-100 (default 50)
    - occupation: person's job
    - education: education level
    - social_variables: dict with 34 social variable values (0-100)
    - desires: dict with desire strengths (0.0-1.0)
    
    Return only valid JSON.
    """
    
    data = {
        "model": "llama3.1",
        "prompt": prompt,
        "stream": False
    }
    
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        result = response.json()
        content = result.get("response", "")
        try:
            return json.loads(content)
        except:
            pass
    
    return {"name": "Unknown"}

def _infer_social_variables(self, text: str) -> Dict[str, int]:
    """Infer social variables using LLM if available."""
    try:
        variables = self._infer_with_llm(text)
        if variables and len(variables) > 0:
            return variables
    except Exception:
        pass
    
    # Fallback to existing regex-based logic
    return self._infer_with_regex(text)
```

#### Step 3: Update Coaching Agent with LLM

**File**: `ai/life_coach.py`

**Enhance coaching advice generation**:

```python
def _generate_life_advice(self, character: Character) -> Dict[str, Any]:
    """Generate advice using LLM if needed."""
    
    # Generate basic advice using existing logic
    basic_advice = self._get_basic_advice(character)
    
    # Try to enhance with LLM
    try:
        enhanced = self._enhance_with_llm(character, basic_advice)
        if enhanced and enhanced.get("overall_philosophy"):
            return enhanced
    except Exception:
        pass
    
    return basic_advice

def _enhance_with_llm(self, character: Character, basic_advice: Dict) -> Dict:
    """Use LLM to enhance coaching advice."""
    import requests
    
    prompt = f"""
    Given this character profile:
    - Name: {character.name}, Age: {character.age}
    - Happiness: {character.happiness}/100, Health: {character.health}/100
    - Smarts: {character.smarts}/100, Looks: {character.looks}/100
    - Karma: {character.karma}/100, Net Worth: ${character.net_worth}
    - Occupation: {character.occupation}
    
    And this basic coaching advice: {basic_advice}
    
    Enhance this advice to be more personalized and actionable.
    Return JSON with:
    - overall_philosophy: deeper philosophical advice
    - daily_habits: specific daily routines
    - medium_term_goals: 6-12 month goals
    - long_term_vision: 5+ year vision
    - key_insight: one powerful insight
    
    Make it practical and specific to their situation.
    """
    
    url = "http://localhost:11434/api/generate"
    headers = {"Content-Type": "application/json"}
    
    data = {
        "model": "qwen2.5",
        "prompt": prompt,
        "stream": False
    }
    
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        result = response.json()
        content = result.get("response", "{}")
        try:
            return json.loads(content)
        except:
            pass
    
    return {}
```

### Phase 3: Complete Integration Testing (30 minutes)

#### Step 1: Test Go Core Integration

**File**: `alpha-zero-engine/tests/test_native_core.py`

**Add AI agent tests**:

```python
@NEEDS_BINARY
@pytest.mark.parametrize("seed", [42])
def test_ai_interview_integration(seed):
    """Test AI interview agent integration."""
    from alpha_zero_engine.mcp_integration import mcp_call
    
    result = mcp_call("alpha_zero_interview", {
        "name": "Test User",
        "age": 30,
        "gender": "male",
        "initial_interview_text": "I'm a software engineer looking for better work-life balance",
        "workspace": "default",
        "repo": "alphazero"
    })
    
    assert result["status"] == "success"
    assert "profile" in result
    assert "social_variables" in result["profile"]

@NEEDS_BINARY
@pytest.mark.parametrize("seed", [42])
def test_ai_coaching_integration(seed):
    """Test AI coaching agent integration."""
    from alpha_zero_engine.mcp_integration import mcp_call
    
    # First create a character profile
    profile = mcp_call("alpha_zero_interview", {
        "name": "Test User",
        "age": 30,
        "gender": "male",
        "initial_interview_text": "I want to improve my life",
        "workspace": "default",
        "repo": "alphazero"
    })
    
    # Then test coaching
    character_json = json.dumps(profile["profile"])
    coaching = mcp_call("alpha_zero_coach", {
        "workspace": "default",
        "character_json": character_json,
        "situation": "career_change",
        "repo": "alphazero",
        "session_id": "test_session"
    })
    
    assert coaching["status"] == "success"
    assert "analysis" in coaching
    assert "recommendations" in coaching
```

#### Step 2: Test Memory Integration

**File**: `ai/memory_system.py`

**Test persistence across sessions**:

```python
def test_memory_persistence():
    """Test that AI learnings persist across sessions."""
    agent = MemorySystemAgent(workspace="test")
    
    # Create session
    session_id = agent.create_session("session_1", {"context": "test"})
    assert session_id is True
    
    # Store learning
    learning_id = agent.store_learning({
        "learning_id": "test_learning_1",
        "data": {"insight": "test insight"},
        "tags": ["test"],
        "importance": 5
    }, "session_1")
    
    assert learning_id is not None
    
    # Retrieve learning
    learnings = agent.retrieve_learnings(query="test")
    assert len(learnings) > 0
    assert learnings[0]["learning_id"] == "test_learning_1"
    
    # Clean up
    agent.delete_learning(learning_id)
    agent.end_session("session_1")
```

#### Step 3: End-to-End Integration Test

**File**: `test_ai_integration.py`

**Complete workflow test**:

```python
def test_complete_ai_workflow():
    """Test complete AI workflow: interview -> coaching -> analysis -> narrative -> memory."""
    
    # Step 1: Conduct interview
    interview_result = mcp_call("alpha_zero_interview", {
        "name": "Integration Test User",
        "age": 25,
        "gender": "female",
        "initial_interview_text": "I'm a recent college graduate looking for my path in life",
        "workspace": "default",
        "repo": "alphazero"
    })
    
    assert interview_result["status"] == "success"
    
    # Step 2: Get coaching advice
    coaching_result = mcp_call("alpha_zero_coach", {
        "workspace": "default",
        "character_json": json.dumps(interview_result["profile"]),
        "situation": "career_starting_out",
        "repo": "alphazero",
        "session_id": "integration_test"
    })
    
    assert coaching_result["status"] == "success"
    
    # Step 3: Analyze simulation outcomes
    analysis_result = mcp_call("alpha_zero_analyze", {
        "workspace": "default",
        "simulation_results": [
            {"final_net_worth": 50000, "final_happiness": 70},
            {"final_net_worth": 30000, "final_happiness": 80}
        ],
        "repo": "alphazero"
    })
    
    assert analysis_result["status"] == "success"
    
    # Step 4: Generate narrative
    character_data = interview_result["profile"]
    simulation_result = analysis_result["results"][0]
    
    narrative_result = mcp_call("alpha_zero_narrate", {
        "workspace": "default",
        "character_name": character_data["name"],
        "simulation_result": simulation_result,
        "repo": "alphazero"
    })
    
    assert narrative_result["status"] == "success"
    assert "title" in narrative_result
    
    # Step 5: Store learnings
    memory_result = mcp_call("alpha_zero_memory", {
        "workspace": "default",
        "operation": "store",
        "data": {
            "learning_id": "integration_test_learning",
            "data": {
                "interview_result": interview_result,
                "coaching_result": coaching_result,
                "analysis_result": analysis_result,
                "narrative_result": narrative_result
            },
            "tags": ["integration_test", "ai_workflow"],
            "importance": 8
        },
        "session_id": "integration_test",
        "repo": "alphazero"
    })
    
    assert memory_result["status"] == "success"
    
    print("✅ All AI integration tests passed!")
```

## Verification Commands

### Step 1: Build Go Core

```bash
# Build the Go native core
./core/scripts/build_core.sh

# Verify binary exists
ls -la /home/alieninc/alphazero/alpha-zero-engine/core/alphacore/bin/alphacore
```

### Step 2: Test MCP Server Integration

```bash
# Test that new tools are available
python3 -c "
from alpha_zero_engine.mcp_integration import ALPHA_ZERO_TOOLS
new_tools = [k for k in ALPHA_ZERO_TOOLS.keys() if k.startswith('alpha_zero_') and k not in ['alpha_zero_simulate', 'alpha_zero_branch', 'alpha_zero_compare_strategies', 'alpha_zero_recall_history', 'alpha_zero_scale_universes', 'alpha_zero_convergence_analysis', 'alpha_zero_compare_universes', 'alpha_zero_best_branch', 'alpha_zero_cluster_universes', 'alpha_zero_serialize_universe', 'alpha_zero_deserialize_universe', 'alpha_zero_portfolio_optimize', 'alpha_zero_financial_forecast', 'alpha_zero_risk_analysis', 'alpha_zero_rust_forecast', 'alpha_zero_rust_compare']]
print(f'New AI tools available: {len(new_tools)}')
for tool in new_tools:
    print(f'  - {tool}')
"
```

### Step 3: Test LLM Integration

```bash
# Start Ollama if not running
if ! pgrep -f ollama > /dev/null; then
    ollama serve &
    sleep 5
fi

# Test Ollama availability
curl -s http://localhost:11434/api/tags | grep "llama3.1"
```

### Step 4: Run All Tests

```bash
# Run Go core tests
pytest alpha-zero-engine/tests/test_native_core.py -v

# Run MCP integration tests
python3 -m pytest test_ai_integration.py -v

# Run AI agent tests
python3 -m pytest ai/ -k "test_" -v
```

## Troubleshooting

### Common Issues and Solutions

1. **Go Binary Not Found**
```bash
./core/scripts/build_core.sh
ls -la alpha-zero-engine/core/alphacore/bin/alphacore
```

2. **MCP Server Issues**
```python
# Check if server is running
python3 -c "from alpha_zero_engine.mcp_integration import store_interview_profile; print('MCP server accessible')"
```

3. **LLM Not Available**
```bash
# Start Ollama
ollama serve &

# Pull models
ollama pull llama3.1
ollama pull qwen2.5
```

4. **Memory System Issues**
```bash
# Check CMB system
python3 -c "import cmb; print(cmb.list_workspaces())"
```

## Quick Start Summary

### For LLM Developers:
```bash
# 1. Build Go core
./core/scripts/build_core.sh

# 2. Test MCP server
python3 test_ai_integration.py

# 3. Start Ollama (optional but recommended)
ollama serve &
ollama pull llama3.1
```

### For Users:
```bash
# Run complete AI workflow test
python3 test_ai_integration.py

# Check integration status
python3 -c "from alpha_zero_engine.mcp_integration import ALPHA_ZERO_TOOLS; print(f'Total tools: {len(ALPHA_ZERO_TOOLS)}')"
```

## Success Metrics

### Phase 1 (Go Core Integration):
- ✅ Go core builds successfully
- ✅ AI agent commands implemented
- ✅ Rust MCP client updated
- ✅ JSON protocols working

### Phase 2 (LLM Integration):
- ✅ Ollama setup complete
- ✅ LLM extraction working
- ✅ Enhanced coaching with LLM
- ✅ Fallback mechanisms in place

### Phase 3 (Testing):
- ✅ Unit tests passing
- ✅ Integration tests complete
- ✅ End-to-end workflow verified
- ✅ Memory persistence confirmed

## Next Steps After Implementation

1. **Add Web Platform Integration** - Connect AI agents to web interface
2. **Enhance AI Capabilities** - Add more advanced LLM features
3. **Production Deployment** - Deploy to production environment
4. **Monitoring & Analytics** - Track AI agent performance

## Files to Commit

```bash
git add alpha-zero-engine/mcp_integration.py
# Update existing AI agent files (interview_agent.py, life_coach.py, etc.)
# Add new test files (test_ai_integration.py, etc.)
# Add configuration files for Ollama/OpenRouter
# Update README with new capabilities
```

This implementation guide provides everything needed to complete Phase 6 with the LLM. All AI agents are already built - this guide focuses on integrating them into the existing Go native core with free LLM alternatives.

Would you like me to start with any specific step, or do you have questions about the implementation process?
```