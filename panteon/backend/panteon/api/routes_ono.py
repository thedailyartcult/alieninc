import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from panteon.core.database import get_db
from panteon.core.auth import get_current_user
from panteon.ono.service import LLMOrchestrator, AgentService, AutomationService
from panteon.api.schemas_ono import (
    LLMProviderCreate, LLMProviderResponse,
    LLMModelCreate, LLMModelResponse,
    LLMExecutionRequest, LLMExecutionResponse,
    AgentCreate, AgentResponse,
    AgentChatRequest, AgentChatResponse,
    AutomationCreate, AutomationResponse,
)

router = APIRouter(prefix="/ono", tags=["ONO"], dependencies=[Depends(get_current_user)])


@router.post("/providers", response_model=LLMProviderResponse)
async def create_provider(
    data: LLMProviderCreate,
    db: AsyncSession = Depends(get_db),
):
    from panteon.ono.models import LLMProvider
    provider = LLMProvider(
        name=data.name,
        provider_type=data.provider_type,
        base_url=data.base_url,
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
    from panteon.ono.models import LLMModel
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
