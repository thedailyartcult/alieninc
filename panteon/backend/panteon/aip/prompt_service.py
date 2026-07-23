import uuid
import time
from datetime import datetime
from typing import Optional
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from panteon.aip.models import Prompt, PromptVersion, PromptEvaluation
from panteon.core.database import is_sqlite
import structlog

logger = structlog.get_logger()


def _uid(val) -> str:
    if is_sqlite and val is not None:
        return str(val)
    return val


class PromptService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ================================================================
    # PROMPT CRUD
    # ================================================================

    async def create_prompt(
        self,
        name: str,
        description: Optional[str] = None,
        workspace_id: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> Prompt:
        prompt = Prompt(
            name=name,
            description=description,
            workspace_id=workspace_id,
            current_version=1,
            created_by=created_by,
        )
        self.db.add(prompt)
        await self.db.flush()

        initial_version = PromptVersion(
            prompt_id=_uid(prompt.id),
            version=1,
            template="",
            temperature=0.7,
            max_tokens=1000,
            variables=[],
            changelog="Initial version",
            is_active=True,
            created_by=created_by,
        )
        self.db.add(initial_version)
        await self.db.flush()

        logger.info("prompt_created", prompt_id=str(prompt.id), name=name)
        return prompt

    # ================================================================
    # VERSIONING
    # ================================================================

    async def create_version(
        self,
        prompt_id: str,
        template: str,
        model_id: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        variables: Optional[list] = None,
        changelog: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> PromptVersion:
        result = await self.db.execute(
            select(Prompt).where(Prompt.id == _uid(prompt_id))
        )
        prompt = result.scalar_one_or_none()
        if not prompt:
            raise ValueError("Prompt not found")

        current_max = await self.db.execute(
            select(func.max(PromptVersion.version)).where(PromptVersion.prompt_id == _uid(prompt_id))
        )
        next_version = (current_max.scalar() or 0) + 1

        prev_active = await self.db.execute(
            select(PromptVersion).where(
                PromptVersion.prompt_id == _uid(prompt_id),
                PromptVersion.is_active == True,
            )
        )
        for v in prev_active.scalars().all():
            v.is_active = False

        version = PromptVersion(
            prompt_id=_uid(prompt_id),
            version=next_version,
            template=template,
            model_id=model_id,
            temperature=temperature,
            max_tokens=max_tokens,
            variables=variables or [],
            changelog=changelog,
            is_active=True,
            created_by=created_by,
        )
        self.db.add(version)
        prompt.current_version = next_version
        prompt.updated_at = datetime.utcnow()
        await self.db.flush()

        logger.info("prompt_version_created", prompt_id=prompt_id, version=next_version)
        return version

    # ================================================================
    # LIST / GET
    # ================================================================

    async def list_prompts(
        self,
        workspace_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        query = select(Prompt)
        if workspace_id:
            query = query.where(Prompt.workspace_id == workspace_id)
        query = query.order_by(desc(Prompt.updated_at)).limit(limit)

        result = await self.db.execute(query.options(selectinload(Prompt.versions)))
        prompts = []
        for p in result.scalars().all():
            latest = None
            if p.versions:
                sorted_versions = sorted(p.versions, key=lambda v: v.version, reverse=True)
                latest_v = sorted_versions[0]
                latest = {
                    "version": latest_v.version,
                    "template_preview": (latest_v.template or "")[:200],
                    "model_id": latest_v.model_id,
                    "created_at": latest_v.created_at.isoformat() if latest_v.created_at else None,
                }
            prompts.append(self._prompt_to_dict(p, latest_version=latest))
        return prompts

    async def get_prompt(self, prompt_id: str) -> Optional[dict]:
        result = await self.db.execute(
            select(Prompt)
            .options(selectinload(Prompt.versions))
            .where(Prompt.id == _uid(prompt_id))
        )
        p = result.scalar_one_or_none()
        if not p:
            return None
        return self._prompt_to_dict(p, include_versions=True)

    async def get_version(self, version_id: str) -> Optional[dict]:
        result = await self.db.execute(
            select(PromptVersion)
            .options(selectinload(PromptVersion.evaluations))
            .where(PromptVersion.id == _uid(version_id))
        )
        v = result.scalar_one_or_none()
        if not v:
            return None
        return self._version_to_dict(v, include_evaluations=True)

    # ================================================================
    # EVALUATION
    # ================================================================

    async def evaluate(
        self,
        version_id: str,
        test_input: str,
        expected_output: Optional[str] = None,
        evaluation_type: str = "manual",
        created_by: Optional[str] = None,
    ) -> PromptEvaluation:
        result = await self.db.execute(
            select(PromptVersion).where(PromptVersion.id == _uid(version_id))
        )
        version = result.scalar_one_or_none()
        if not version:
            raise ValueError("Prompt version not found")

        start_time = time.time()

        rendered = self._render_template(version.template, {})

        simulated_response = (
            f"[Simulated LLM response for prompt version {version.version}] "
            f"Input received: '{test_input[:100]}'. "
            f"Model: {version.model_id or 'default'}. "
            f"Temperature: {version.temperature}."
        )

        latency_ms = int((time.time() - start_time) * 1000)

        score = 0.0
        if expected_output:
            score = self._compute_similarity(rendered, expected_output, simulated_response)

        evaluation = PromptEvaluation(
            version_id=_uid(version_id),
            test_input=test_input,
            expected_output=expected_output,
            actual_output=simulated_response,
            score=score,
            latency_ms=latency_ms,
            tokens_used=len(simulated_response.split()) * 2,
            evaluation_type=evaluation_type,
            created_by=created_by,
        )
        self.db.add(evaluation)
        await self.db.flush()

        logger.info("prompt_evaluated", version_id=version_id, score=score, latency_ms=latency_ms)
        return evaluation

    # ================================================================
    # RENDERING
    # ================================================================

    async def render_prompt(self, version_id: str, variables: Optional[dict] = None) -> dict:
        result = await self.db.execute(
            select(PromptVersion).where(PromptVersion.id == _uid(version_id))
        )
        version = result.scalar_one_or_none()
        if not version:
            raise ValueError("Prompt version not found")

        rendered = self._render_template(version.template, variables or {})

        return {
            "version_id": str(version.id),
            "version": version.version,
            "model_id": version.model_id,
            "temperature": version.temperature,
            "max_tokens": version.max_tokens,
            "rendered_prompt": rendered,
            "variables_used": list((variables or {}).keys()),
        }

    # ================================================================
    # EVALUATION LISTING
    # ================================================================

    async def list_evaluations(
        self,
        version_id: str,
        limit: int = 50,
    ) -> list[dict]:
        result = await self.db.execute(
            select(PromptEvaluation)
            .where(PromptEvaluation.version_id == _uid(version_id))
            .order_by(desc(PromptEvaluation.created_at))
            .limit(limit)
        )
        return [self._evaluation_to_dict(e) for e in result.scalars().all()]

    # ================================================================
    # HELPERS
    # ================================================================

    def _render_template(self, template: str, variables: dict) -> str:
        if not template:
            return ""
        rendered = template
        for key, value in variables.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
        return rendered

    def _compute_similarity(self, rendered: str, expected: str, actual: str) -> float:
        if not expected:
            return 0.0

        expected_words = set(expected.lower().split())
        actual_words = set(actual.lower().split())

        if not expected_words:
            return 0.0

        intersection = expected_words & actual_words
        union = expected_words | actual_words

        jaccard = len(intersection) / max(len(union), 1)
        length_ratio = min(len(actual), len(expected)) / max(len(expected), 1)

        score = round((jaccard * 0.7 + length_ratio * 0.3) * 100, 2)
        return min(score, 100.0)

    def _prompt_to_dict(self, p: Prompt, latest_version: Optional[dict] = None, include_versions: bool = False) -> dict:
        result = {
            "id": str(p.id),
            "name": p.name,
            "description": p.description,
            "workspace_id": p.workspace_id,
            "current_version": p.current_version,
            "tags": p.tags or [],
            "created_by": p.created_by,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }
        if latest_version:
            result["latest_version"] = latest_version
        if include_versions and p.versions:
            result["versions"] = [
                self._version_to_dict(v) for v in sorted(p.versions, key=lambda v: v.version)
            ]
        return result

    def _version_to_dict(self, v: PromptVersion, include_evaluations: bool = False) -> dict:
        result = {
            "id": str(v.id),
            "prompt_id": str(v.prompt_id),
            "version": v.version,
            "template": v.template,
            "model_id": v.model_id,
            "temperature": v.temperature,
            "max_tokens": v.max_tokens,
            "variables": v.variables or [],
            "changelog": v.changelog,
            "is_active": v.is_active,
            "created_by": v.created_by,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
        if include_evaluations and v.evaluations:
            result["evaluations"] = [
                self._evaluation_to_dict(e) for e in v.evaluations
            ]
        return result

    def _evaluation_to_dict(self, e: PromptEvaluation) -> dict:
        return {
            "id": str(e.id),
            "version_id": str(e.version_id),
            "test_input": e.test_input,
            "expected_output": e.expected_output,
            "actual_output": e.actual_output,
            "score": e.score,
            "latency_ms": e.latency_ms,
            "tokens_used": e.tokens_used,
            "evaluation_type": e.evaluation_type,
            "notes": e.notes,
            "created_by": e.created_by,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
