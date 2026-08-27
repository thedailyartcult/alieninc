import asyncio
import json
import os
import time
import uuid
from typing import Optional, AsyncIterator

OPENCODE_BIN = os.environ.get("OPENCODE_BIN", "/root/.opencode/bin/opencode")
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
from panteon.yono.secrets import decrypt_secret


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

    async def list_executions(self, limit: int = 50) -> list[LLMExecution]:
        result = await self.db.execute(
            select(LLMExecution)
            .order_by(LLMExecution.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def execute_llm_with_tools(
        self,
        model_id: uuid.UUID,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        tools: Optional[list[dict]] = None,
        created_by: Optional[str] = None,
    ) -> dict:
        """
        Execute LLM with tool-calling support (Palantir AIP Query Layer).
        
        Returns dict with:
        - content: str (text response if no tool calls)
        - tool_calls: list[dict] (tool calls if LLM wants to invoke tools)
        - tokens_input: int
        - tokens_output: int
        """
        model = await self.get_model(model_id)
        if not model:
            raise ValueError(f"Model {model_id} not found")

        provider = model.provider
        provider_type = provider.provider_type

        if provider_type == "google":
            return await self._call_google_with_tools(model, messages, system_prompt, tools)
        elif provider_type == "openai":
            return await self._call_openai_with_tools(model, messages, system_prompt, tools)
        elif provider_type == "anthropic":
            return await self._call_anthropic_with_tools(model, messages, system_prompt, tools)
        elif provider_type == "opencode":
            return await self._call_opencode_with_tools(model, messages, system_prompt, tools)
        else:
            raise ValueError(f"Unsupported provider type: {provider_type}")

    async def _call_google_with_tools(
        self, model: LLMModel, messages: list[dict], system_prompt: Optional[str], tools: Optional[list]
    ) -> dict:
        import google.generativeai as genai
        from google.generativeai.types import generation_types

        genai.configure(api_key=settings.google_api_key)
        gemini_model = genai.GenerativeModel(model.model_id)

        # Convert messages to Gemini format
        history = []
        contents = []

        # Build content from messages
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            content = msg.get("content", "")
            if not content and msg.get("tool_calls"):
                content = "[Tool calls requested]"
            if content:
                contents.append({"role": role, "parts": [content]})

        # Convert tools to Gemini format
        gemini_tools = None
        if tools:
            def _strip_defaults(schema):
                if isinstance(schema, dict):
                    return {k: _strip_defaults(v) for k, v in schema.items() if k != "default"}
                if isinstance(schema, list):
                    return [_strip_defaults(item) for item in schema]
                return schema

            function_declarations = []
            for tool in tools:
                func_def = {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": _strip_defaults(tool.get("parameters", {})),
                }
                function_declarations.append(func_def)
            gemini_tools = [{"function_declarations": function_declarations}]

        # Build generation config
        gen_config = {}
        if system_prompt:
            # Gemini uses system_instruction for system prompts
            gemini_model = genai.GenerativeModel(
                model.model_id,
                system_instruction=system_prompt,
            )

        try:
            response = await gemini_model.generate_content_async(
                contents,
                tools=gemini_tools,
                **gen_config,
            )

            # Parse response
            content = ""
            tool_calls = []

            for part in response.parts:
                if hasattr(part, "text") and part.text:
                    content += part.text
                elif hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    tool_calls.append({
                        "id": f"call_{uuid.uuid4().hex[:8]}",
                        "type": "function",
                        "function": {
                            "name": fc.name,
                            "arguments": json.dumps(dict(fc.args)) if fc.args else "{}",
                        },
                    })

            tokens_in = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
            tokens_out = response.usage_metadata.candidates_token_count if response.usage_metadata else 0

            return {
                "content": content,
                "tool_calls": tool_calls,
                "tokens_input": tokens_in,
                "tokens_output": tokens_out,
            }

        except Exception as e:
            return {
                "content": f"Error: {str(e)}",
                "tool_calls": [],
                "tokens_input": 0,
                "tokens_output": 0,
            }

    async def _call_openai_with_tools(
        self, model: LLMModel, messages: list[dict], system_prompt: Optional[str], tools: Optional[list]
    ) -> dict:
        from openai import AsyncOpenAI

        client = self._openai_client(model.provider)

        # Build messages with system prompt
        api_messages = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})
        api_messages.extend(messages)

        # Build tools for OpenAI format
        api_tools = None
        if tools:
            api_tools = [{"type": "function", "function": t} for t in tools]

        kwargs = {"model": model.model_id, "messages": api_messages}
        if api_tools:
            kwargs["tools"] = api_tools

        response = await client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        content = choice.message.content or ""
        tool_calls = []

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                })

        return {
            "content": content,
            "tool_calls": tool_calls,
            "tokens_input": response.usage.prompt_tokens,
            "tokens_output": response.usage.completion_tokens,
        }

    async def stream_llm_with_tools(
        self,
        model_id: uuid.UUID,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        tools: Optional[list[dict]] = None,
    ):
        """Streaming variant of execute_llm_with_tools (OpenAI-compatible paths).

        Yields ("delta", str) events as content tokens arrive, then a final
        ("done", result_dict) event shaped exactly like execute_llm_with_tools.
        Raises ValueError for providers/models that cannot stream so callers
        can fall back to the buffered path.
        """
        model = await self.get_model(model_id)
        if not model:
            raise ValueError(f"Model {model_id} not found")
        provider_type = model.provider.provider_type
        if provider_type == "openai":
            async for ev in self._call_openai_with_tools_stream(model, messages, system_prompt, tools):
                yield ev
        else:
            raise ValueError(f"Streaming unsupported for provider type: {provider_type}")

    async def _call_openai_with_tools_stream(
        self, model: LLMModel, messages: list[dict], system_prompt: Optional[str], tools: Optional[list]
    ):
        from openai import AsyncOpenAI

        client = self._openai_client(model.provider)

        api_messages = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})
        api_messages.extend(messages)

        kwargs = {"model": model.model_id, "messages": api_messages}
        if tools:
            kwargs["tools"] = [{"type": "function", "function": t} for t in tools]

        # Some OpenAI-compatible servers reject stream_options; degrade gracefully.
        try:
            stream = await client.chat.completions.create(
                stream=True, stream_options={"include_usage": True}, **kwargs
            )
        except Exception:
            stream = await client.chat.completions.create(stream=True, **kwargs)

        # Defensive: some OpenAI-compatible servers ignore stream=True and return
        # a completed ChatCompletion. Convert it instead of crashing on async-for.
        if not hasattr(stream, "__aiter__"):
            choice = stream.choices[0] if getattr(stream, "choices", None) else None
            msg = getattr(choice, "message", None)
            usage = getattr(stream, "usage", None)
            content = getattr(msg, "content", "") or ""
            if content:
                yield ("delta", content)
            result = {
                "content": content,
                "tokens_input": int(getattr(usage, "prompt_tokens", 0) or 0),
                "tokens_output": int(getattr(usage, "completion_tokens", 0) or 0),
                "tool_calls": [
                    {"id": tc.id or f"call_{uuid.uuid4().hex[:8]}", "type": "function",
                     "function": {"name": tc.function.name,
                                  "arguments": tc.function.arguments or "{}"}}
                    for tc in (getattr(msg, "tool_calls", None) or [])
                ],
            }
            yield ("done", result)
            return

        content_parts: list[str] = []
        tc_acc: dict[int, dict] = {}
        tokens_in = tokens_out = 0

        try:
            async for chunk in stream:
                if getattr(chunk, "usage", None):
                    tokens_in = chunk.usage.prompt_tokens or 0
                    tokens_out = chunk.usage.completion_tokens or 0
                if not getattr(chunk, "choices", None):
                    continue
                delta = chunk.choices[0].delta
                if delta is None:
                    continue
                text = getattr(delta, "content", None)
                if text:
                    content_parts.append(text)
                    yield ("delta", text)
                frags = getattr(delta, "tool_calls", None)
                if frags:
                    for frag in frags:
                        slot = tc_acc.setdefault(frag.index, {"id": "", "name": "", "arguments": ""})
                        if frag.id:
                            slot["id"] = frag.id
                        if frag.function:
                            if frag.function.name:
                                slot["name"] += frag.function.name
                            if frag.function.arguments:
                                slot["arguments"] += frag.function.arguments
        finally:
            close = getattr(stream, "close", None)
            if close:
                try:
                    await close()
                except Exception:
                    pass

        tool_calls = [
            {
                "id": slot["id"] or f"call_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {
                    "name": slot["name"],
                    "arguments": slot["arguments"] or "{}",
                },
            }
            for _, slot in sorted(tc_acc.items())
        ]
        yield ("done", {
            "content": "".join(content_parts),
            "tool_calls": tool_calls,
            "tokens_input": tokens_in,
            "tokens_output": tokens_out,
        })

    async def _call_anthropic_with_tools(
        self, model: LLMModel, messages: list[dict], system_prompt: Optional[str], tools: Optional[list]
    ) -> dict:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=settings.anthropic_api_key)

        # Build tools for Anthropic format
        api_tools = None
        if tools:
            api_tools = []
            for t in tools:
                api_tools.append({
                    "name": t["name"],
                    "description": t["description"],
                    "input_schema": t.get("parameters", {}),
                })

        kwargs = {
            "model": model.model_id,
            "max_tokens": model.max_tokens,
            "messages": messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if api_tools:
            kwargs["tools"] = api_tools

        response = await client.messages.create(**kwargs)

        content = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": json.dumps(block.input),
                    },
                })

        return {
            "content": content,
            "tool_calls": tool_calls,
            "tokens_input": response.usage.input_tokens,
            "tokens_output": response.usage.output_tokens,
        }

    def _openai_client(self, provider):
        """Build an AsyncOpenAI client from the stored YONO provider config.

        Uses the provider's stored base_url + decrypted api_key when present,
        falling back to settings.openai_api_key.
        """
        from openai import AsyncOpenAI

        api_key = settings.openai_api_key
        if provider.api_key_encrypted:
            try:
                api_key = decrypt_secret(provider.api_key_encrypted)
            except Exception:
                api_key = settings.openai_api_key
        kwargs = {}
        if provider.base_url:
            kwargs["base_url"] = provider.base_url
        return AsyncOpenAI(api_key=api_key, **kwargs)

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
        elif provider_type == "opencode":
            return await self._call_opencode(model, prompt, system_prompt, parameters)
        else:
            raise ValueError(f"Unsupported provider type: {provider_type}")

    async def _call_openai(
        self, model: LLMModel, prompt: str, system_prompt: Optional[str], parameters: Optional[dict]
    ) -> dict:
        from openai import AsyncOpenAI

        client = self._openai_client(model.provider)
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

    async def _call_opencode(
        self, model: LLMModel, prompt: str, system_prompt: Optional[str], parameters: Optional[dict]
    ) -> dict:
        import subprocess

        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        cmd = [OPENCODE_BIN, "run", full_prompt, "--model", model.model_id]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

        if proc.returncode != 0:
            raise RuntimeError(f"opencode failed: {stderr.decode().strip()[:500]}")

        return {
            "content": stdout.decode().strip(),
            "tokens_input": 0,
            "tokens_output": 0,
        }

    async def _call_opencode_with_tools(
        self, model: LLMModel, messages: list[dict], system_prompt: Optional[str], tools: Optional[list]
    ) -> dict:

        tool_schema = ""
        if tools:
            tool_schema = "\n\nYou have access to the following tools. To use a tool, output EXACTLY this format on its own line (no other text around it):\n\n```tool_call\n{\"name\": \"tool_name\", \"args\": {\"arg1\": \"value1\"}}\n```\n\nAvailable tools:\n"
            for t in tools:
                tool_schema += f"- **{t['name']}**: {t.get('description', '')}\n"
                if t.get("parameters", {}).get("properties"):
                    tool_schema += f"  Parameters: {json.dumps(t['parameters']['properties'])}\n"

        messages_text = ""
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "tool":
                tool_result = msg.get("content", "")
                messages_text += f"\n[Tool Result]: {tool_result}\n"
            elif role == "assistant" and msg.get("tool_calls"):
                messages_text += f"\n[Assistant requested tools]\n"
            elif content:
                messages_text += f"\n[{role.capitalize()}]: {content}\n"

        full_prompt = f"{system_prompt or ''}{tool_schema}\n\nConversation:\n{messages_text}\n\nRespond now."

        cmd = [OPENCODE_BIN, "run", full_prompt, "--model", model.model_id]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

        if proc.returncode != 0:
            raise RuntimeError(f"opencode failed: {stderr.decode().strip()[:500]}")

        response_text = stdout.decode().strip()

        tool_calls = []
        import re
        for match in re.finditer(r"```tool_call\s*\n(\{.*?\})\s*\n```", response_text, re.DOTALL):
            try:
                tc = json.loads(match.group(1))
                tool_calls.append({
                    "id": f"call_{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc.get("args", {})),
                    },
                })
            except (json.JSONDecodeError, KeyError):
                pass

        clean_response = re.sub(r"```tool_call\s*\n\{.*?\}\s*\n```", "", response_text, flags=re.DOTALL).strip()

        return {
            "content": clean_response,
            "tool_calls": tool_calls,
            "tokens_input": 0,
            "tokens_output": 0,
        }


class AgentService:
    """
    Palantir AIP-style agent service.
    
    Architecture:
    1. Context Layer — deterministic ontology data injection
    2. Query/Reasoning Layer — LLM with ontology tools
    3. Action Layer — governed ontology mutations
    4. Governance Layer — permission checks on every operation
    5. Audit Layer — full lineage trail
    """
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
        allowed_object_types: Optional[list] = None,
        writable_object_types: Optional[list] = None,
        allowed_actions: Optional[list] = None,
        ontology_context_config: Optional[dict] = None,
    ) -> Agent:
        agent = Agent(
            name=name,
            display_name=display_name,
            system_prompt=system_prompt,
            model_id=_uid(model_id),
            description=description,
            tools=tools or [],
            allowed_object_types=allowed_object_types or [],
            writable_object_types=writable_object_types or [],
            allowed_actions=allowed_actions or [],
            ontology_context_config=ontology_context_config or {},
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
        auto_execute: bool = False,
    ) -> dict:
        """
        Palantir AIP-style chat with ontology integration.
        
        Flow:
        1. Load agent + session
        2. Build ontology context (governed)
        3. Build system prompt with context
        4. Tool-calling loop: LLM reasons → calls tools → gets results → repeats
        5. Final response with audit trail
        """
        agent = await self.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if session_id:
            session = await self._get_session(session_id)
            if not session:
                session = await self._create_session(agent_id, user_id)
        else:
            session = await self._create_session(agent_id, user_id)

        # ── Layer 1: Context Injection ────────────────────────────────
        from panteon.yono.governance import GovernanceLayer
        governance = GovernanceLayer(self.db, agent)

        ontology_context = await governance.build_context()

        # ── Build system prompt with ontology context ─────────────────
        system_prompt = agent.system_prompt
        if ontology_context:
            system_prompt = f"{agent.system_prompt}\n\n{ontology_context}"

        # ── Layer 2: Prepare tool-calling ─────────────────────────────
        from panteon.yono.ontology_tools import get_tool_definitions, OntologyToolExecutor
        tool_defs = governance.filter_tool_list(get_tool_definitions())
        tool_executor = OntologyToolExecutor(self.db, agent.id)

        # ── Build conversation history ────────────────────────────────
        messages = []
        if session.messages:
            messages.extend(session.messages)
        messages.append({"role": "user", "content": message})

        # ── Layer 3: Tool-calling loop ────────────────────────────────
        total_tokens_in = 0
        total_tokens_out = 0
        tool_calls_log = []
        final_response = ""

        for iteration in range(agent.max_iterations or 10):
            # Call LLM with tools
            llm_result = await self.llm.execute_llm_with_tools(
                model_id=agent.model_id,
                messages=messages,
                system_prompt=system_prompt,
                tools=tool_defs if tool_defs else None,
                created_by=user_id,
            )

            total_tokens_in += llm_result.get("tokens_input", 0)
            total_tokens_out += llm_result.get("tokens_output", 0)

            # Check if LLM wants to call tools
            tool_calls = llm_result.get("tool_calls", [])
            if not tool_calls:
                # No tool calls — this is the final response
                final_response = llm_result.get("content", "")
                messages.append({"role": "assistant", "content": final_response})
                break

            # Execute each tool call
            messages.append({
                "role": "assistant",
                "content": llm_result.get("content", ""),
                "tool_calls": tool_calls,
            })

            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, KeyError):
                    args = {}

                tool_result, log_entry = await self._exec_tool_call(
                    governance=governance,
                    executor=tool_executor,
                    agent=agent,
                    auto_execute=auto_execute,
                    tool_name=tool_name,
                    args=args,
                )
                tool_calls_log.append(log_entry)

                # History carries a SLIMMED copy of the result: full payloads
                # are re-sent to the LLM on every subsequent leg and dominate
                # prefill on multi-tool chats.
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(self._slim_for_history(tool_result)),
                })

        # ── Layer 4: Persist session ──────────────────────────────────
        session.messages = messages
        await self.db.flush()

        await self._audit_chat(
            session, agent, user_id, tool_calls_log, total_tokens_in, total_tokens_out
        )

        return {
            "session_id": session.id,
            "response": final_response,
            "tokens_input": total_tokens_in,
            "tokens_output": total_tokens_out,
            "tool_calls": tool_calls_log,
            "iterations": min(iteration + 1, agent.max_iterations or 10),
        }

    @staticmethod
    def _shrink_for_ui(value, depth: int = 0):
        """Compact copy of a tool result safe to ship to the panel."""
        if depth > 4:
            return "…"
        if isinstance(value, dict):
            return {k: AgentService._shrink_for_ui(v, depth + 1) for k, v in list(value.items())[:30]}
        if isinstance(value, (list, tuple)):
            return [AgentService._shrink_for_ui(v, depth + 1) for v in list(value)[:8]]
        if isinstance(value, str) and len(value) > 300:
            return value[:300] + "…"
        return value

    @staticmethod
    def _slim_for_history(value, depth: int = 0):
        """Compact copy of a tool result safe to keep in LLM message history.

        Full tool payloads (e.g. recent_objects rows) are re-uploaded as prompt
        context on every subsequent leg; at ~6 tok/s decode that prefill cost
        compounds fast. Bounds: 20 keys / 12 items / 500-char strings / depth 3.
        """
        if depth > 3:
            return "…"
        if isinstance(value, dict):
            return {k: AgentService._slim_for_history(v, depth + 1) for k, v in list(value.items())[:20]}
        if isinstance(value, (list, tuple)):
            return [AgentService._slim_for_history(v, depth + 1) for v in value[:12]]
        if isinstance(value, str) and len(value) > 500:
            return value[:500] + "…"
        return value

    async def _exec_tool_call(
        self,
        *,
        governance,
        executor,
        agent,
        auto_execute: bool,
        tool_name: str,
        args: dict,
    ) -> tuple[dict, dict]:
        """Governed execution of one requested tool call.

        Returns (tool_result, ui_log_entry). Shared by chat() and chat_stream().
        """
        # ── Governance checks ─────────────────────────────────
        denial: Optional[str] = None

        if tool_name in ("query_objects", "get_object", "get_object_links",
                         "search_objects", "find_objects"):
            type_name = args.get("type_name", "")
            if type_name and not governance.check_read(type_name).allowed:
                denial = governance.check_read(type_name).reason

        elif tool_name == "recent_objects":
            requested = args.get("type_names") or []
            readable = [t for t in requested if governance.check_read(t).allowed]
            if requested and not readable:
                denial = (
                    f"None of the requested types are readable. "
                    f"Allowed: {agent.allowed_object_types}"
                )
            elif len(readable) != len(requested):
                # Narrow silently to permitted types instead of failing.
                args["type_names"] = readable
                args["_narrowed_from"] = requested

        elif tool_name == "execute_action":
            action_name = args.get("action_name", "")
            if action_name and not governance.check_action(action_name).allowed:
                denial = governance.check_action(action_name).reason

        # recent_objects/get_ontology_graph/find_objects without a
        # type scope already intersect allowed types executor-side.

        if denial is not None:
            return {"error": denial}, {
                "tool": tool_name,
                "args": args,
                "denied": True,
                "reason": denial,
            }

        # ── Execute (actions propose-by-default) ──────────────
        if tool_name == "execute_action" and not auto_execute:
            tool_result = await executor.propose_action(args)
        else:
            tool_result = await executor.execute(tool_name, args)

        log_entry = {
            "tool": tool_name,
            "args": {k: v for k, v in args.items() if not k.startswith("_")},
            "result_summary": str(tool_result)[:200],
            "result": self._shrink_for_ui(tool_result),
        }
        if (tool_name == "execute_action" and isinstance(tool_result, dict)
                and tool_result.get("status") == "proposed"):
            log_entry["proposed"] = True
            log_entry["proposal_id"] = tool_result.get("proposal_id")
        return tool_result, log_entry

    async def _audit_chat(self, session, agent, user_id, tool_calls_log, tokens_in, tokens_out):
        """Fire-and-forget lineage audit for a finished chat (never raises)."""
        try:
            from panteon.core.lineage_service import LineageService
            lineage = LineageService(self.db)
            node = await lineage.get_or_create_node(
                node_type="agent_session",
                node_id=str(session.id),
                name=f"Query Session: {agent.display_name}",
                description=f"Chat session with {agent.display_name}",
            )
            await lineage.record_event(
                node_id=node.id,
                event_type="agent_chat",
                actor=user_id,
                details={
                    "agent_id": str(agent.id),
                    "agent_name": agent.name,
                    "tool_calls": len(tool_calls_log),
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                },
            )
        except Exception:
            pass

    async def chat_stream(
        self,
        agent_id: uuid.UUID,
        message: str,
        user_id: Optional[str] = None,
        session_id: Optional[uuid.UUID] = None,
        auto_execute: bool = False,
    ):
        """Streaming variant of chat(): an async generator of SSE-ready events.

        Yields dicts:
          {"type":"delta","text":str}   — assistant content token
          {"type":"tool","entry":dict}  — executed/denied tool call (UI log entry)
          {"type":"status","text":str}  — leg transitions
          {"type":"done","payload":...} — same shape as chat()'s return value
        Non-streamable providers automatically fall back to buffered legs.
        """
        agent = await self.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if session_id:
            session = await self._get_session(session_id)
            if not session:
                session = await self._create_session(agent_id, user_id)
        else:
            session = await self._create_session(agent_id, user_id)

        from panteon.yono.governance import GovernanceLayer
        governance = GovernanceLayer(self.db, agent)

        ontology_context = await governance.build_context()

        system_prompt = agent.system_prompt
        if ontology_context:
            system_prompt = f"{agent.system_prompt}\n\n{ontology_context}"

        from panteon.yono.ontology_tools import get_tool_definitions, OntologyToolExecutor
        tool_defs = governance.filter_tool_list(get_tool_definitions())
        tool_executor = OntologyToolExecutor(self.db, agent.id)

        messages = []
        if session.messages:
            messages.extend(session.messages)
        messages.append({"role": "user", "content": message})

        yield {"type": "status", "text": "consulting ontology"}

        total_tokens_in = 0
        total_tokens_out = 0
        tool_calls_log = []
        final_response = ""
        iteration = 0

        for iteration in range(agent.max_iterations or 10):
            yield {"type": "status", "text": f"thinking · leg {iteration + 1}"}

            llm_result = None
            streamed = False
            try:
                aiter = self.llm.stream_llm_with_tools(
                    model_id=agent.model_id,
                    messages=messages,
                    system_prompt=system_prompt,
                    tools=tool_defs if tool_defs else None,
                ).__aiter__()
                while True:
                    try:
                        kind, chunk = await aiter.__anext__()
                    except StopAsyncIteration:
                        break
                    if kind == "delta":
                        yield {"type": "delta", "text": chunk}
                    elif kind == "done":
                        llm_result = chunk
                if llm_result is None:
                    raise RuntimeError("stream produced no result")
                streamed = True
            except ValueError:
                streamed = False

            if not streamed:
                llm_result = await self.llm.execute_llm_with_tools(
                    model_id=agent.model_id,
                    messages=messages,
                    system_prompt=system_prompt,
                    tools=tool_defs if tool_defs else None,
                    created_by=user_id,
                )

            total_tokens_in += llm_result.get("tokens_input", 0)
            total_tokens_out += llm_result.get("tokens_output", 0)

            tool_calls = llm_result.get("tool_calls") or []
            if not tool_calls:
                final_response = llm_result.get("content", "")
                messages.append({"role": "assistant", "content": final_response})
                break

            messages.append({
                "role": "assistant",
                "content": llm_result.get("content", ""),
                "tool_calls": tool_calls,
            })

            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, KeyError):
                    args = {}

                yield {"type": "status", "text": f"running {tool_name}"}

                tool_result, log_entry = await self._exec_tool_call(
                    governance=governance,
                    executor=tool_executor,
                    agent=agent,
                    auto_execute=auto_execute,
                    tool_name=tool_name,
                    args=args,
                )
                tool_calls_log.append(log_entry)
                yield {"type": "tool", "entry": log_entry}

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(self._slim_for_history(tool_result)),
                })

        # ── Persist + audit (parity with chat()) ─────────────────────
        session.messages = messages
        await self.db.flush()
        await self._audit_chat(
            session, agent, user_id, tool_calls_log, total_tokens_in, total_tokens_out
        )

        yield {
            "type": "done",
            "payload": {
                "session_id": session.id,
                "response": final_response,
                "tokens_input": total_tokens_in,
                "tokens_output": total_tokens_out,
                "tool_calls": tool_calls_log,
                "iterations": min(iteration + 1, agent.max_iterations or 10),
            },
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
