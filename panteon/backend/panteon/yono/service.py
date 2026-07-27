import time
import uuid
from typing import Optional, AsyncIterator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from panteon.core.database import is_sqlite
def _uid(val):
    if is_sqlite and val is not None:
        return str(val)
    return val

from panteon.yono.models import (
    LLMProvider, LLMModel, LLMExecution, Agent, AgentSession,
    Automation, AutomationExecution
)
from panteon.core.config import settings


class LLMOrchestrator:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_provider(self, provider_id: uuid.UUID) -> Optional[LLMProvider]:
        result = await self.db.execute(
            select(LLMProvider).where(LLMProvider.id == provider_id)
        )
        return result.scalar_one_or_none()

    async def list_providers(self) -> list[LLMProvider]:
        result = await self.db.execute(
            select(LLMProvider).where(LLMProvider.is_enabled == True)
        )
        return list(result.scalars().all())

    async def get_model(self, model_id: uuid.UUID) -> Optional[LLMModel]:
        result = await self.db.execute(
            select(LLMModel)
            .options(selectinload(LLMModel.provider))
            .where(LLMModel.id == model_id)
        )
        return result.scalar_one_or_none()

    async def list_models(
        self, provider_id: Optional[uuid.UUID] = None
    ) -> list[LLMModel]:
        query = select(LLMModel).options(selectinload(LLMModel.provider))
        if provider_id:
            query = query.where(LLMModel.provider_id == provider_id)
        query = query.where(LLMModel.is_enabled == True)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def execute_llm(
        self,
        model_id: uuid.UUID,
        prompt: str,
        system_prompt: Optional[str] = None,
        parameters: Optional[dict] = None,
        created_by: Optional[str] = None,
    ) -> LLMExecution:
        model = await self.get_model(model_id)
        if not model:
            raise ValueError(f"Model {model_id} not found")

        execution = LLMExecution(
            model_id=_uid(model_id),
            prompt=prompt,
            system_prompt=system_prompt,
            parameters=parameters or {},
            created_by=created_by,
            status="running",
        )
        self.db.add(execution)
        await self.db.flush()

        start_time = time.time()
        try:
            response = await self._call_provider(model, prompt, system_prompt, parameters)
            execution.response = response.get("content", "")
            execution.tokens_input = response.get("tokens_input", 0)
            execution.tokens_output = response.get("tokens_output", 0)
            execution.status = "completed"
        except Exception as e:
            execution.status = "failed"
            execution.error = str(e)
            raise
        finally:
            execution.latency_ms = int((time.time() - start_time) * 1000)
            execution.cost = (
                execution.tokens_input * model.cost_per_1k_input / 1000
                + execution.tokens_output * model.cost_per_1k_output / 1000
            )
            await self.db.flush()

        return execution

    async def _call_provider(
        self,
        model: LLMModel,
        prompt: str,
        system_prompt: Optional[str],
        parameters: Optional[dict],
    ) -> dict:
        provider = model.provider
        provider_type = provider.provider_type

        if provider_type == "openai":
            return await self._call_openai(model, prompt, system_prompt, parameters)
        elif provider_type == "anthropic":
            return await self._call_anthropic(model, prompt, system_prompt, parameters)
        elif provider_type == "google":
            return await self._call_google(model, prompt, system_prompt, parameters)
        else:
            raise ValueError(f"Unsupported provider type: {provider_type}")

    async def _call_openai(
        self, model: LLMModel, prompt: str, system_prompt: Optional[str], parameters: Optional[dict]
    ) -> dict:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await client.chat.completions.create(
            model=model.model_id,
            messages=messages,
            **parameters or {},
        )

        return {
            "content": response.choices[0].message.content,
            "tokens_input": response.usage.prompt_tokens,
            "tokens_output": response.usage.completion_tokens,
        }

    async def _call_anthropic(
        self, model: LLMModel, prompt: str, system_prompt: Optional[str], parameters: Optional[dict]
    ) -> dict:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        kwargs = {"model": model.model_id, "max_tokens": model.max_tokens, "messages": [{"role": "user", "content": prompt}]}
        if system_prompt:
            kwargs["system"] = system_prompt
        if parameters:
            kwargs.update(parameters)

        response = await client.messages.create(**kwargs)

        return {
            "content": response.content[0].text,
            "tokens_input": response.usage.input_tokens,
            "tokens_output": response.usage.output_tokens,
        }

    async def _call_google(
        self, model: LLMModel, prompt: str, system_prompt: Optional[str], parameters: Optional[dict]
    ) -> dict:
        import google.generativeai as genai

        genai.configure(api_key=settings.google_api_key)
        gemini_model = genai.GenerativeModel(model.model_id)

        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        response = await gemini_model.generate_content_async(full_prompt)

        return {
            "content": response.text,
            "tokens_input": response.usage_metadata.prompt_token_count,
            "tokens_output": response.usage_metadata.candidates_token_count,
        }


class AgentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = LLMOrchestrator(db)

    async def create_agent(
        self,
        name: str,
        display_name: str,
        system_prompt: str,
        model_id: Optional[uuid.UUID] = None,
        description: Optional[str] = None,
        tools: Optional[list] = None,
    ) -> Agent:
        agent = Agent(
            name=name,
            display_name=display_name,
            system_prompt=system_prompt,
            model_id=_uid(model_id),
            description=description,
            tools=tools or [],
        )
        self.db.add(agent)
        await self.db.flush()
        return agent

    async def get_agent(self, agent_id: uuid.UUID) -> Optional[Agent]:
        result = await self.db.execute(
            select(Agent).where(Agent.id == agent_id)
        )
        return result.scalar_one_or_none()

    async def list_agents(self) -> list[Agent]:
        result = await self.db.execute(
            select(Agent).where(Agent.is_enabled == True)
        )
        return list(result.scalars().all())

    async def chat(
        self,
        agent_id: uuid.UUID,
        message: str,
        user_id: Optional[str] = None,
        session_id: Optional[uuid.UUID] = None,
    ) -> dict:
        agent = await self.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if session_id:
            session = await self._get_session(session_id)
        else:
            session = await self._create_session(agent_id, user_id)

        session.messages.append({"role": "user", "content": message})

        response = await self.llm.execute_llm(
            model_id=agent.model_id,
            prompt=message,
            system_prompt=agent.system_prompt,
            created_by=user_id,
        )

        session.messages.append({"role": "assistant", "content": response.response})
        await self.db.flush()

        return {
            "session_id": session.id,
            "response": response.response,
            "tokens_input": response.tokens_input,
            "tokens_output": response.tokens_output,
        }

    async def _create_session(self, agent_id: uuid.UUID, user_id: Optional[str]) -> AgentSession:
        session = AgentSession(agent_id=_uid(agent_id), user_id=user_id)
        self.db.add(session)
        await self.db.flush()
        return session

    async def _get_session(self, session_id: uuid.UUID) -> Optional[AgentSession]:
        result = await self.db.execute(
            select(AgentSession).where(AgentSession.id == session_id)
        )
        return result.scalar_one_or_none()


class AutomationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_automation(
        self,
        name: str,
        display_name: str,
        trigger_type: str,
        trigger_config: dict,
        effects: list,
        description: Optional[str] = None,
        conditions: Optional[list] = None,
    ) -> Automation:
        automation = Automation(
            name=name,
            display_name=display_name,
            trigger_type=trigger_type,
            trigger_config=trigger_config,
            effects=effects,
            description=description,
            conditions=conditions or [],
        )
        self.db.add(automation)
        await self.db.flush()
        return automation

    async def get_automation(self, automation_id: uuid.UUID) -> Optional[Automation]:
        result = await self.db.execute(
            select(Automation).where(Automation.id == automation_id)
        )
        return result.scalar_one_or_none()

    async def list_automations(self, enabled_only: bool = True) -> list[Automation]:
        query = select(Automation)
        if enabled_only:
            query = query.where(Automation.is_enabled == True)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def trigger_automation(
        self, automation_id: uuid.UUID, trigger_data: Optional[dict] = None
    ) -> AutomationExecution:
        automation = await self.get_automation(automation_id)
        if not automation:
            raise ValueError(f"Automation {automation_id} not found")

        execution = AutomationExecution(
            automation_id=_uid(automation_id),
            trigger_data=trigger_data or {},
            status="running",
        )
        self.db.add(execution)
        automation.last_triggered_at = execution.triggered_at
        await self.db.flush()

        return execution
