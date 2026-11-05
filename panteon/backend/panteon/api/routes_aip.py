import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from panteon.core.database import get_db
from panteon.core.auth import SupabaseUser, get_current_user
from panteon.aip.logic_service import WorkflowEngine
from panteon.aip.rag_service import RagService
from panteon.aip.guard_service import GuardService
from panteon.aip.prompt_service import PromptService

router = APIRouter(prefix="/aip")


class WorkflowCreate(BaseModel):
    name: str
    description: Optional[str] = None
    nodes: Optional[list] = None
    edges: Optional[list] = None
    workspace_id: Optional[str] = None


class WorkflowExecute(BaseModel):
    input_data: Optional[dict] = None


class DocumentIngest(BaseModel):
    title: str
    content: str
    source_type: str = "text"
    source_url: Optional[str] = None
    workspace_id: Optional[str] = None
    collection: str = "default"


class GuardEvaluate(BaseModel):
    text: str
    workspace_id: Optional[str] = None


class PolicyCreate(BaseModel):
    name: str
    policy_type: str
    config: dict
    severity: str = "warning"
    workspace_id: Optional[str] = None


class PromptCreate(BaseModel):
    name: str
    description: Optional[str] = None
    workspace_id: Optional[str] = None
    tags: Optional[list[str]] = None


class VersionCreate(BaseModel):
    template: str
    model_id: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 1000
    variables: Optional[list] = None
    changelog: Optional[str] = None


class EvaluationCreate(BaseModel):
    test_input: str
    expected_output: Optional[str] = None
    evaluation_type: str = "manual"


class RenderRequest(BaseModel):
    variables: Optional[dict] = None


# ================================================================
# AIP Logic — Workflows
# ================================================================

@router.post("/workflows", tags=["AIP Logic"])
async def create_workflow(
    data: WorkflowCreate,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        svc = WorkflowEngine(db)
        wf = await svc.create_workflow(
            name=data.name,
            description=data.description,
            nodes=data.nodes,
            edges=data.edges,
            workspace_id=data.workspace_id,
            created_by=_user.email,
        )
        return {"id": str(wf.id), "name": wf.name, "status": wf.status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/workflows", tags=["AIP Logic"])
async def list_workflows(
    workspace_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = WorkflowEngine(db)
    return await svc.list_workflows(workspace_id, status, limit)


@router.get("/workflows/{workflow_id}", tags=["AIP Logic"])
async def get_workflow(
    workflow_id: str,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = WorkflowEngine(db)
    result = await svc.get_workflow(workflow_id)
    if not result:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return result


@router.post("/workflows/{workflow_id}/execute", tags=["AIP Logic"])
async def execute_workflow(
    workflow_id: str,
    data: WorkflowExecute,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        svc = WorkflowEngine(db)
        return await svc.execute_workflow(
            workflow_id=workflow_id,
            input_data=data.input_data,
            triggered_by=_user.email,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflows/{workflow_id}/runs", tags=["AIP Logic"])
async def get_workflow_runs(
    workflow_id: str,
    limit: int = Query(default=20, le=100),
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = WorkflowEngine(db)
    return await svc.get_workflow_runs(workflow_id, limit)


# ================================================================
# AIP RAG — Documents & Knowledge
# ================================================================

@router.post("/rag/documents", tags=["AIP RAG"])
async def ingest_document(
    data: DocumentIngest,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = RagService(db)
    doc = await svc.ingest_document(
        title=data.title,
        content=data.content,
        source_type=data.source_type,
        source_url=data.source_url,
        workspace_id=data.workspace_id,
        collection=data.collection,
        created_by=_user.email,
    )
    return {"id": str(doc.id), "title": doc.title, "status": doc.status, "chunk_count": doc.chunk_count}


@router.get("/rag/documents", tags=["AIP RAG"])
async def list_documents(
    workspace_id: Optional[str] = None,
    collection: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = RagService(db)
    return await svc.list_documents(workspace_id, collection, status, limit)


@router.get("/rag/documents/{document_id}", tags=["AIP RAG"])
async def get_document(
    document_id: str,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = RagService(db)
    result = await svc.get_document(document_id)
    if not result:
        raise HTTPException(status_code=404, detail="Document not found")
    return result


@router.get("/rag/search", tags=["AIP RAG"])
async def search_documents(
    query: str = Query(..., min_length=2),
    workspace_id: Optional[str] = None,
    collection: Optional[str] = None,
    limit: int = Query(default=20, le=100),
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = RagService(db)
    return await svc.search(query, workspace_id, collection, limit)


@router.post("/rag/documents/{document_id}/extract-knowledge", tags=["AIP RAG"])
async def extract_knowledge(
    document_id: str,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        svc = RagService(db)
        return await svc.extract_knowledge(document_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/rag/entities", tags=["AIP RAG"])
async def list_entities(
    workspace_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = RagService(db)
    return await svc.list_entities(workspace_id, entity_type, limit)


@router.get("/rag/entity-graph", tags=["AIP RAG"])
async def get_entity_graph(
    workspace_id: Optional[str] = None,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = RagService(db)
    return await svc.get_entity_graph(workspace_id)


# ================================================================
# AIP Guard — Safety Policies
# ================================================================

@router.post("/guard/evaluate-input", tags=["AIP Guard"])
async def evaluate_input(
    data: GuardEvaluate,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = GuardService(db)
    return await svc.evaluate_input(
        text=data.text,
        workspace_id=data.workspace_id,
        user_email=_user.email,
    )


@router.post("/guard/evaluate-output", tags=["AIP Guard"])
async def evaluate_output(
    data: GuardEvaluate,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = GuardService(db)
    return await svc.evaluate_output(
        text=data.text,
        workspace_id=data.workspace_id,
        user_email=_user.email,
    )


@router.post("/guard/policies", tags=["AIP Guard"])
async def create_policy(
    data: PolicyCreate,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        svc = GuardService(db)
        policy = await svc.create_policy(
            name=data.name,
            policy_type=data.policy_type,
            config=data.config,
            severity=data.severity,
            workspace_id=data.workspace_id,
            created_by=_user.email,
        )
        return {"id": str(policy.id), "name": policy.name, "policy_type": policy.policy_type}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/guard/policies", tags=["AIP Guard"])
async def list_policies(
    workspace_id: Optional[str] = None,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = GuardService(db)
    return await svc.list_policies(workspace_id)


@router.get("/guard/events", tags=["AIP Guard"])
async def list_guard_events(
    workspace_id: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = GuardService(db)
    return await svc.list_events(workspace_id, severity, limit)


# ================================================================
# AIP Prompts — Prompt Studio
# ================================================================

@router.post("/prompts", tags=["AIP Prompts"])
async def create_prompt(
    data: PromptCreate,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = PromptService(db)
    prompt = await svc.create_prompt(
        name=data.name,
        description=data.description,
        workspace_id=data.workspace_id,
        created_by=_user.email,
    )
    return {"id": str(prompt.id), "name": prompt.name, "current_version": prompt.current_version}


@router.get("/prompts", tags=["AIP Prompts"])
async def list_prompts(
    workspace_id: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = PromptService(db)
    return await svc.list_prompts(workspace_id, limit)


@router.get("/prompts/{prompt_id}", tags=["AIP Prompts"])
async def get_prompt(
    prompt_id: str,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = PromptService(db)
    result = await svc.get_prompt(prompt_id)
    if not result:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return result


@router.post("/prompts/{prompt_id}/versions", tags=["AIP Prompts"])
async def create_version(
    prompt_id: str,
    data: VersionCreate,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        svc = PromptService(db)
        version = await svc.create_version(
            prompt_id=prompt_id,
            template=data.template,
            model_id=data.model_id,
            temperature=data.temperature,
            max_tokens=data.max_tokens,
            variables=data.variables,
            changelog=data.changelog,
            created_by=_user.email,
        )
        return {"id": str(version.id), "version": version.version, "is_active": version.is_active}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/prompts/versions/{version_id}", tags=["AIP Prompts"])
async def get_version(
    version_id: str,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = PromptService(db)
    result = await svc.get_version(version_id)
    if not result:
        raise HTTPException(status_code=404, detail="Prompt version not found")
    return result


@router.post("/prompts/versions/{version_id}/evaluate", tags=["AIP Prompts"])
async def evaluate_version(
    version_id: str,
    data: EvaluationCreate,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        svc = PromptService(db)
        evaluation = await svc.evaluate(
            version_id=version_id,
            test_input=data.test_input,
            expected_output=data.expected_output,
            evaluation_type=data.evaluation_type,
            created_by=_user.email,
        )
        return {
            "id": str(evaluation.id),
            "score": evaluation.score,
            "latency_ms": evaluation.latency_ms,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/prompts/versions/{version_id}/render", tags=["AIP Prompts"])
async def render_version(
    version_id: str,
    data: RenderRequest,
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        svc = PromptService(db)
        return await svc.render_prompt(version_id, data.variables)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/prompts/versions/{version_id}/evaluations", tags=["AIP Prompts"])
async def list_evaluations(
    version_id: str,
    limit: int = Query(default=50, le=200),
    _user: SupabaseUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = PromptService(db)
    return await svc.list_evaluations(version_id, limit)
