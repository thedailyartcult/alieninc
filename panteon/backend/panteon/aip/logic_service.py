import uuid
import time
from datetime import datetime
from typing import Optional
from collections import defaultdict, deque
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from panteon.aip.models import Workflow, WorkflowRun, WORKFLOW_STATUSES, NODE_TYPES, RUN_STATUSES
from panteon.core.database import is_sqlite
import structlog

logger = structlog.get_logger()


def _uid(val) -> str:
    if is_sqlite and val is not None:
        return str(val)
    return val


class WorkflowEngine:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ================================================================
    # WORKFLOW CRUD
    # ================================================================

    async def create_workflow(
        self,
        name: str,
        description: Optional[str] = None,
        nodes: Optional[list] = None,
        edges: Optional[list] = None,
        workspace_id: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> Workflow:
        nodes = nodes or []
        edges = edges or []

        for node in nodes:
            node_type = node.get("type", "")
            if node_type not in NODE_TYPES:
                raise ValueError(f"Invalid node type: {node_type}. Must be one of {NODE_TYPES}")
            if "id" not in node:
                raise ValueError("Each node must have an 'id' field")

        node_ids = {n["id"] for n in nodes}
        for edge in edges:
            if "source" not in edge or "target" not in edge:
                raise ValueError("Each edge must have 'source' and 'target' fields")
            if edge["source"] not in node_ids:
                raise ValueError(f"Edge source '{edge['source']}' references unknown node")
            if edge["target"] not in node_ids:
                raise ValueError(f"Edge target '{edge['target']}' references unknown node")

        workflow = Workflow(
            name=name,
            description=description,
            nodes=nodes,
            edges=edges,
            workspace_id=workspace_id,
            status="draft",
            created_by=created_by,
        )
        self.db.add(workflow)
        await self.db.flush()
        logger.info("workflow_created", workflow_id=str(workflow.id), name=name)
        return workflow

    # ================================================================
    # EXECUTION
    # ================================================================

    async def execute_workflow(
        self,
        workflow_id: str,
        input_data: Optional[dict] = None,
        triggered_by: Optional[str] = None,
    ) -> dict:
        result = await self.db.execute(
            select(Workflow).where(Workflow.id == _uid(workflow_id))
        )
        workflow = result.scalar_one_or_none()
        if not workflow:
            raise ValueError("Workflow not found")

        nodes = workflow.nodes or []
        edges = workflow.edges or []

        if not nodes:
            raise ValueError("Workflow has no nodes")

        sorted_node_ids = self._topological_sort(nodes, edges)

        run = WorkflowRun(
            workflow_id=_uid(workflow_id),
            status="running",
            input_data=input_data or {},
            started_at=datetime.utcnow(),
            triggered_by=triggered_by,
        )
        self.db.add(run)
        await self.db.flush()

        start_time = time.time()
        node_results = {}
        context = {"input": input_data or {}, "node_results": {}}

        try:
            node_map = {n["id"]: n for n in nodes}

            for node_id in sorted_node_ids:
                node = node_map[node_id]
                node_start = time.time()

                try:
                    output = await self._process_node(node, context)
                    node_results[node_id] = {
                        "status": "completed",
                        "output": output,
                        "duration_ms": int((time.time() - node_start) * 1000),
                    }
                    context["node_results"][node_id] = output
                except Exception as e:
                    node_results[node_id] = {
                        "status": "failed",
                        "error": str(e),
                        "duration_ms": int((time.time() - node_start) * 1000),
                    }
                    logger.error("node_execution_failed", node_id=node_id, error=str(e))
                    raise RuntimeError(f"Node '{node_id}' failed: {e}")

            run.status = "completed"
            run.node_results = self._sanitize_for_json(node_results)
            run.output_data = self._sanitize_for_json(context["node_results"])
            run.completed_at = datetime.utcnow()
            run.duration_ms = int((time.time() - start_time) * 1000)
            await self.db.flush()

            logger.info("workflow_completed", run_id=str(run.id), duration_ms=run.duration_ms)
            return self._run_to_dict(run)

        except Exception as e:
            run.status = "failed"
            run.node_results = self._sanitize_for_json(node_results)
            run.error = str(e)
            run.completed_at = datetime.utcnow()
            run.duration_ms = int((time.time() - start_time) * 1000)
            await self.db.flush()
            logger.error("workflow_failed", run_id=str(run.id), error=str(e))
            return self._run_to_dict(run)

    # ================================================================
    # LIST / GET
    # ================================================================

    async def list_workflows(
        self,
        workspace_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        query = select(Workflow)
        if workspace_id:
            query = query.where(Workflow.workspace_id == workspace_id)
        if status:
            query = query.where(Workflow.status == status)
        query = query.order_by(desc(Workflow.created_at)).limit(limit)

        result = await self.db.execute(query)
        workflows = []
        for w in result.scalars().all():
            run_count_result = await self.db.execute(
                select(func.count(WorkflowRun.id)).where(WorkflowRun.workflow_id == w.id)
            )
            run_count = run_count_result.scalar() or 0
            workflows.append(self._workflow_to_dict(w, run_count=run_count))
        return workflows

    async def get_workflow(self, workflow_id: str) -> Optional[dict]:
        result = await self.db.execute(
            select(Workflow).where(Workflow.id == _uid(workflow_id))
        )
        w = result.scalar_one_or_none()
        if not w:
            return None
        return self._workflow_to_dict(w)

    async def get_workflow_runs(
        self,
        workflow_id: str,
        limit: int = 20,
    ) -> list[dict]:
        result = await self.db.execute(
            select(WorkflowRun)
            .where(WorkflowRun.workflow_id == _uid(workflow_id))
            .order_by(desc(WorkflowRun.created_at))
            .limit(limit)
        )
        return [self._run_to_dict(r) for r in result.scalars().all()]

    # ================================================================
    # TOPOLOGICAL SORT
    # ================================================================

    def _topological_sort(self, nodes: list, edges: list) -> list[str]:
        adjacency = defaultdict(list)
        in_degree = defaultdict(int)
        node_ids = [n["id"] for n in nodes]

        for nid in node_ids:
            in_degree[nid] = 0

        for edge in edges:
            adjacency[edge["source"]].append(edge["target"])
            in_degree[edge["target"]] += 1

        queue = deque([nid for nid in node_ids if in_degree[nid] == 0])
        sorted_ids = []

        while queue:
            current = queue.popleft()
            sorted_ids.append(current)
            for neighbor in adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(sorted_ids) != len(node_ids):
            raise ValueError("Workflow graph contains a cycle")

        return sorted_ids

    # ================================================================
    # NODE PROCESSORS
    # ================================================================

    async def _process_node(self, node: dict, context: dict) -> dict:
        node_type = node.get("type", "")
        node_config = node.get("config", {})
        node_id = node.get("id", "unknown")

        if node_type == "input":
            return {"type": "input", "data": context.get("input", {})}

        elif node_type == "llm_call":
            prompt = node_config.get("prompt", "")
            model = node_config.get("model", "gpt-4")
            rendered = prompt
            for key, val in context.get("input", {}).items():
                rendered = rendered.replace(f"{{{{{key}}}}}", str(val))
            for nid, nout in context.get("node_results", {}).items():
                if isinstance(nout, dict):
                    for k, v in nout.items():
                        rendered = rendered.replace(f"{{{{{nid}.{k}}}}}", str(v))
            return {
                "type": "llm_call",
                "model": model,
                "prompt": rendered,
                "response": f"[Simulated LLM response for node '{node_id}' with model '{model}']",
                "tokens_used": len(rendered.split()) * 2,
            }

        elif node_type == "condition":
            expression = node_config.get("expression", "True")
            condition_result = self._evaluate_condition(expression, context)
            return {
                "type": "condition",
                "expression": expression,
                "result": condition_result,
                "branch": "true" if condition_result else "false",
            }

        elif node_type == "transform":
            field_mappings = node_config.get("field_mappings", {})
            input_source = node_config.get("source", "input")
            source_data = context.get("input", {}) if input_source == "input" else context.get("node_results", {}).get(input_source, {})
            transformed = {}
            if isinstance(source_data, dict):
                for target_field, source_field in field_mappings.items():
                    if isinstance(source_field, str) and source_field in source_data:
                        transformed[target_field] = source_data[source_field]
                    else:
                        transformed[target_field] = source_field
            return {"type": "transform", "data": transformed}

        elif node_type == "rag_query":
            query_text = node_config.get("query", "")
            collection = node_config.get("collection", "default")
            for key, val in context.get("input", {}).items():
                query_text = query_text.replace(f"{{{{{key}}}}}", str(val))
            return {
                "type": "rag_query",
                "query": query_text,
                "collection": collection,
                "results": [],
                "message": f"RAG query for '{query_text}' in collection '{collection}' (simulated)",
            }

        elif node_type == "output":
            collect_from = node_config.get("collect_from", [])
            collected = {}
            if isinstance(collect_from, list):
                for source_id in collect_from:
                    if source_id in context.get("node_results", {}):
                        collected[source_id] = context["node_results"][source_id]
            if not collect_from:
                collected = context.get("node_results", {})
            return {"type": "output", "data": collected}

        elif node_type == "api_call":
            url = node_config.get("url", "")
            method = node_config.get("method", "GET")
            return {
                "type": "api_call",
                "url": url,
                "method": method,
                "response": {"status": 200, "body": f"[Simulated API response from {url}]"},
            }

        else:
            return {"type": node_type, "status": "passthrough", "node_id": node_id}

    def _evaluate_condition(self, expression: str, context: dict) -> bool:
        safe_vars = {"True": True, "False": False, "None": None, "true": True, "false": False, "null": None}

        for key, val in context.get("input", {}).items():
            safe_vars[key] = val

        try:
            return bool(eval(expression, {"__builtins__": {}}, safe_vars))
        except Exception:
            return False

    # ================================================================
    # SERIALIZATION
    # ================================================================

    def _workflow_to_dict(self, w: Workflow, run_count: int = 0) -> dict:
        return {
            "id": str(w.id),
            "name": w.name,
            "description": w.description,
            "workspace_id": w.workspace_id,
            "status": w.status,
            "nodes": w.nodes or [],
            "edges": w.edges or [],
            "variables": w.variables or {},
            "config": w.config or {},
            "created_by": w.created_by,
            "created_at": w.created_at.isoformat() if w.created_at else None,
            "updated_at": w.updated_at.isoformat() if w.updated_at else None,
            "run_count": run_count,
        }

    def _sanitize_for_json(self, obj, _depth=0, _seen=None):
        if _depth > 10:
            return "<max_depth>"
        if _seen is None:
            _seen = set()
        obj_id = id(obj)
        if obj_id in _seen:
            return "<circular>"
        _seen.add(obj_id)
        if isinstance(obj, dict):
            result = {k: self._sanitize_for_json(v, _depth + 1, _seen) for k, v in obj.items()}
            _seen.discard(obj_id)
            return result
        if isinstance(obj, (list, tuple)):
            result = [self._sanitize_for_json(v, _depth + 1, _seen) for v in obj]
            _seen.discard(obj_id)
            return result
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        _seen.discard(obj_id)
        return str(obj)

    def _run_to_dict(self, r: WorkflowRun) -> dict:
        return {
            "id": str(r.id),
            "workflow_id": str(r.workflow_id),
            "status": r.status,
            "input_data": r.input_data or {},
            "output_data": r.output_data or {},
            "node_results": r.node_results or {},
            "error": r.error,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "duration_ms": r.duration_ms,
            "triggered_by": r.triggered_by,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
