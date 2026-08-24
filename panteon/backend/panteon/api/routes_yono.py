import json
import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from panteon.core.database import get_db
from panteon.core.auth import get_current_user
from panteon.yono.service import LLMOrchestrator, AgentService, AutomationService
from panteon.yono.secrets import encrypt_secret
from panteon.yono.sc_agent_seed import SC_YONO_AGENT_NAME
from panteon.api.schemas_yono import (
    LLMProviderCreate, LLMProviderResponse,
    LLMModelCreate, LLMModelResponse,
    LLMExecutionRequest, LLMExecutionResponse,
    AgentCreate, AgentResponse,
    AgentChatRequest, AgentChatResponse,
    AutomationCreate, AutomationResponse,
    PanelChatRequest,
)

router = APIRouter(prefix="/yono", tags=["YONO"], dependencies=[Depends(get_current_user)])


@router.post("/providers", response_model=LLMProviderResponse)
async def create_provider(
    data: LLMProviderCreate,
    db: AsyncSession = Depends(get_db),
):
    from panteon.yono.models import LLMProvider
    provider = LLMProvider(
        name=data.name,
        provider_type=data.provider_type,
        base_url=data.base_url,
        api_key_encrypted=encrypt_secret(data.api_key) if data.api_key else None,
    )
    db.add(provider)
    await db.flush()
    return provider


@router.get("/providers", response_model=list[LLMProviderResponse])
async def list_providers(db: AsyncSession = Depends(get_db)):
    service = LLMOrchestrator(db)
    return await service.list_providers()


@router.post("/models", response_model=LLMModelResponse)
async def create_model(
    data: LLMModelCreate,
    db: AsyncSession = Depends(get_db),
):
    from panteon.yono.models import LLMModel
    model = LLMModel(
        provider_id=data.provider_id,
        model_id=data.model_id,
        display_name=data.display_name,
        capabilities=data.capabilities or [],
        max_tokens=data.max_tokens,
        cost_per_1k_input=data.cost_per_1k_input,
        cost_per_1k_output=data.cost_per_1k_output,
    )
    db.add(model)
    await db.flush()
    return model


@router.get("/models", response_model=list[LLMModelResponse])
async def list_models(
    provider_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    service = LLMOrchestrator(db)
    return await service.list_models(provider_id)


@router.post("/execute", response_model=LLMExecutionResponse)
async def execute_llm(
    data: LLMExecutionRequest,
    db: AsyncSession = Depends(get_db),
):
    service = LLMOrchestrator(db)
    try:
        execution = await service.execute_llm(
            model_id=data.model_id,
            prompt=data.prompt,
            system_prompt=data.system_prompt,
            parameters=data.parameters,
        )
        return execution
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executions", response_model=list[LLMExecutionResponse])
async def list_executions(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    service = LLMOrchestrator(db)
    return await service.list_executions(limit)


@router.post("/agents", response_model=AgentResponse)
async def create_agent(
    data: AgentCreate,
    db: AsyncSession = Depends(get_db),
):
    service = AgentService(db)
    agent = await service.create_agent(
        name=data.name,
        display_name=data.display_name,
        system_prompt=data.system_prompt,
        model_id=data.model_id,
        description=data.description,
        tools=data.tools,
        allowed_object_types=data.allowed_object_types,
        writable_object_types=data.writable_object_types,
        allowed_actions=data.allowed_actions,
        ontology_context_config=data.ontology_context_config,
    )
    return agent


@router.get("/agents", response_model=list[AgentResponse])
async def list_agents(db: AsyncSession = Depends(get_db)):
    service = AgentService(db)
    return await service.list_agents()


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    service = AgentService(db)
    agent = await service.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/agents/chat", response_model=AgentChatResponse)
async def chat_with_agent(
    data: AgentChatRequest,
    db: AsyncSession = Depends(get_db),
):
    service = AgentService(db)
    try:
        result = await service.chat(
            agent_id=data.agent_id,
            message=data.message,
            session_id=data.session_id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/automations", response_model=AutomationResponse)
async def create_automation(
    data: AutomationCreate,
    db: AsyncSession = Depends(get_db),
):
    service = AutomationService(db)
    automation = await service.create_automation(
        name=data.name,
        display_name=data.display_name,
        trigger_type=data.trigger_type,
        trigger_config=data.trigger_config,
        effects=data.effects,
        description=data.description,
        conditions=data.conditions,
    )
    return automation


@router.get("/automations", response_model=list[AutomationResponse])
async def list_automations(
    enabled_only: bool = True,
    db: AsyncSession = Depends(get_db),
):
    service = AutomationService(db)
    return await service.list_automations(enabled_only)


@router.post("/automations/{automation_id}/trigger")
async def trigger_automation(
    automation_id: uuid.UUID,
    trigger_data: dict | None = None,
    db: AsyncSession = Depends(get_db),
):
    service = AutomationService(db)
    try:
        execution = await service.trigger_automation(automation_id, trigger_data)
        return {"execution_id": execution.id, "status": execution.status}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── YONO Panel (Spinal Cracker floating AIP assistant) ───────────────────

async def _resolve_panel_agent(db: AsyncSession):
    from panteon.yono.models import Agent
    row = await db.execute(
        select(Agent).where(Agent.name == SC_YONO_AGENT_NAME, Agent.is_enabled == True)  # noqa: E712
    )
    return row.scalar_one_or_none()


@router.get("/panel/status")
async def panel_status(db: AsyncSession = Depends(get_db)):
    """Bootstrap payload for the Spinal Cracker floating panel."""
    from panteon.spinal_craker.models import ActionExecution

    agent = await _resolve_panel_agent(db)
    open_count = 0
    if agent:
        row = await db.execute(
            select(ActionExecution)
            .where(ActionExecution.status == "proposed")
        )
        open_count = len(list(row.scalars().all()))
    model = None
    if agent and agent.model_id:
        from panteon.yono.models import LLMModel
        mrow = await db.execute(select(LLMModel).where(LLMModel.id == agent.model_id))
        m = mrow.scalar_one_or_none()
        if m:
            model = {"model_id": m.model_id, "display_name": m.display_name}
    return {
        "seeded": agent is not None,
        "agent": None if not agent else {
            "id": str(agent.id),
            "name": agent.name,
            "display_name": agent.display_name,
            "allowed_object_types": agent.allowed_object_types or [],
            "writable_object_types": agent.writable_object_types or [],
            "allowed_actions": agent.allowed_actions or [],
        },
        "model": model,
        "open_proposals": open_count,
    }


@router.post("/panel/chat", response_model=AgentChatResponse)
async def panel_chat(
    data: PanelChatRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Chat with the seeded Spinal Cracker YONO agent.

    Actions are PROPOSED (sc_action_executions status='proposed') unless
    auto_execute=true is explicitly passed for the session.
    """
    agent = await _resolve_panel_agent(db)
    if not agent:
        raise HTTPException(
            status_code=503,
            detail="YONO panel agent not seeded yet — restart panteon.service",
        )
    service = AgentService(db)
    try:
        result = await service.chat(
            agent_id=agent.id,
            message=data.message,
            session_id=data.session_id,
            auto_execute=data.auto_execute,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    result["agent"] = {
        "id": str(agent.id),
        "name": agent.name,
        "display_name": agent.display_name,
    }
    return result


@router.post("/panel/chat/stream")
async def panel_chat_stream(
    data: PanelChatRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Token-streaming variant of /panel/chat (Server-Sent Events).

    Event payloads are single-line JSON dicts:
      {"type":"status","text":...} | {"type":"delta","text":...}
      {"type":"tool","entry":...}  | {"type":"done","payload":<chat() shape>}
      {"type":"error","message":...}
    """
    agent = await _resolve_panel_agent(db)
    if not agent:
        raise HTTPException(
            status_code=503,
            detail="YONO panel agent not seeded yet — restart panteon.service",
        )
    service = AgentService(db)

    async def sse():
        try:
            async for evt in service.chat_stream(
                agent_id=agent.id,
                message=data.message,
                session_id=data.session_id,
                auto_execute=data.auto_execute,
            ):
                yield f"data: {json.dumps(evt, default=str)}\n\n"
        except ValueError as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/panel/history")
async def panel_history(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Replay a stored panel conversation (user/assistant turns only).

    The tool-calling internals stay server-side; the client gets just the
    renderable bubbles so a page refresh can restore the transcript.
    """
    service = AgentService(db)
    session = await service._get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    out = []
    for msg in (session.messages or [])[-40:]:
        role = msg.get("role")
        content = msg.get("content") or ""
        if role not in ("user", "assistant") or not content.strip():
            continue
        if len(content) > 4000:
            content = content[:4000] + "…"
        out.append({"role": role, "content": content})
    return {
        "session_id": str(session.id),
        "agent_id": str(session.agent_id),
        "messages": out,
    }


async def _get_proposal(execution_id: uuid.UUID, db: AsyncSession):
    from panteon.spinal_craker.models import ActionExecution
    row = await db.execute(
        select(ActionExecution).where(ActionExecution.id == execution_id)
    )
    execution = row.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return execution


def _proposal_out(execution, action_name: str) -> dict:
    params = execution.parameters or {}
    return {
        "proposal_id": str(execution.id),
        "action_name": action_name,
        "arguments": params.get("arguments", {}),
        "status": execution.status,
        "executed_by": execution.executed_by,
        "executed_at": execution.executed_at.isoformat() if execution.executed_at else None,
    }


@router.get("/proposals")
async def list_proposals(
    status: str = "proposed",
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List YONO action proposals (default: still-open ones), newest first."""
    from panteon.spinal_craker.models import ActionExecution, ActionType

    limit = max(1, min(limit, 200))
    rows = await db.execute(
        select(ActionExecution, ActionType.name)
        .join(ActionType, ActionExecution.action_type_id == ActionType.id)
        .where(ActionType.name.in_(["kriegspiel_run_battle"]))
        .where(ActionExecution.status == status)
        .order_by(ActionExecution.executed_at.desc())
        .limit(limit)
    )
    return [_proposal_out(execution, name) for execution, name in rows.all()]


@router.post("/proposals/{execution_id}/confirm")
async def confirm_proposal(
    execution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Execute a proposed action exactly once (Propose + Confirm flow)."""
    from datetime import datetime

    from panteon.spinal_craker.models import ActionExecution

    execution = await _get_proposal(execution_id, db)
    if execution.status != "proposed":
        raise HTTPException(
            status_code=409,
            detail=f"Proposal is not open (status={execution.status})",
        )

    params = execution.parameters or {}
    action_name = params.get("action_name", "")
    args = params.get("arguments", {}) or {}
    result_payload: dict = {"note": "recorded; no external effect wired"}
    error_text: str | None = None

    if action_name == "kriegspiel_run_battle":
        battlefield = args.get("battlefield")
        if not battlefield:
            execution.status = "failed"
            execution.error = "missing required parameter 'battlefield'"
            execution.completed_at = datetime.utcnow()
            await db.flush()
            raise HTTPException(status_code=422, detail=execution.error)
        report = {
            "battlefield": battlefield,
            "scenarios_run": int(args.get("scenarios", args.get("scenarios_run", 500))),
        }
        if args.get("seed") is not None:
            report["seed"] = int(args["seed"])
        try:
            from panteon.api import routes_sims
            gateway_report = await routes_sims._gateway(
                "POST", "kriegspiel/run", json_body=report)
        except HTTPException as exc:
            gateway_report = None
            error_text = f"gateway: {exc.detail}"
        if gateway_report is not None:
            try:
                from panteon.war_ontology import emit_battle_report
                ontology_summary = await emit_battle_report(db, gateway_report, mode="battle")
            except Exception as exc:  # noqa: BLE001 — ontology never breaks the sim
                ontology_summary = {"emitted": False, "error": str(exc)[:300]}
            result_payload = {
                "note": "kriegspiel run executed via sims gateway",
                "report": {k: gateway_report.get(k) for k in (
                    "battlefield", "scenarios_run", "red_wins", "blue_wins",
                    "stalemates", "decisive_battles", "convergence_rate", "seed")},
                "ontology": ontology_summary,
            }

    if error_text:
        execution.status = "failed"
        execution.error = error_text[:500]
    else:
        execution.status = "succeeded"
        execution.result = result_payload
    execution.completed_at = datetime.utcnow()
    await db.flush()
    out = _proposal_out(execution, action_name)
    out["result"] = None if error_text else result_payload
    out["error"] = error_text
    return out


@router.post("/proposals/{execution_id}/reject")
async def reject_proposal(
    execution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Close a proposal without executing it."""
    from datetime import datetime

    from panteon.spinal_craker.models import ActionExecution

    execution = await _get_proposal(execution_id, db)
    if execution.status != "proposed":
        raise HTTPException(
            status_code=409,
            detail=f"Proposal is not open (status={execution.status})",
        )
    params = execution.parameters or {}
    execution.status = "rejected"
    execution.result = {"note": "rejected by operator in YONO panel"}
    execution.completed_at = datetime.utcnow()
    await db.flush()
    return _proposal_out(execution, params.get("action_name", ""))

