import uuid
import re
from datetime import datetime
from typing import Optional
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from panteon.aip.models import (
    GuardPolicy, GuardEvent,
    GUARD_POLICY_TYPES, GUARD_SEVERITY,
)
from panteon.core.database import is_sqlite
import structlog

logger = structlog.get_logger()


def _uid(val) -> str:
    if is_sqlite and val is not None:
        return str(val)
    return val


class GuardService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ================================================================
    # POLICY MANAGEMENT
    # ================================================================

    async def create_policy(
        self,
        name: str,
        policy_type: str,
        config: dict,
        severity: str = "warning",
        workspace_id: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> GuardPolicy:
        if policy_type not in GUARD_POLICY_TYPES:
            raise ValueError(f"Invalid policy type: {policy_type}. Must be one of {GUARD_POLICY_TYPES}")
        if severity not in GUARD_SEVERITY:
            raise ValueError(f"Invalid severity: {severity}. Must be one of {GUARD_SEVERITY}")

        policy = GuardPolicy(
            name=name,
            policy_type=policy_type,
            config=config,
            severity=severity,
            workspace_id=workspace_id,
            created_by=created_by,
        )
        self.db.add(policy)
        await self.db.flush()
        logger.info("guard_policy_created", policy_id=str(policy.id), policy_type=policy_type)
        return policy

    async def list_policies(self, workspace_id: Optional[str] = None) -> list[dict]:
        query = select(GuardPolicy)
        if workspace_id:
            query = query.where(GuardPolicy.workspace_id == workspace_id)
        query = query.order_by(desc(GuardPolicy.created_at))

        result = await self.db.execute(query)
        return [self._policy_to_dict(p) for p in result.scalars().all()]

    # ================================================================
    # INPUT EVALUATION
    # ================================================================

    async def evaluate_input(
        self,
        text: str,
        workspace_id: Optional[str] = None,
        user_email: Optional[str] = None,
    ) -> dict:
        query = select(GuardPolicy).where(GuardPolicy.is_enabled == True)
        if workspace_id:
            query = query.where(GuardPolicy.workspace_id == workspace_id)
        result = await self.db.execute(query)
        policies = result.scalars().all()

        if not policies:
            return {"decision": "pass", "text": text, "checks": [], "events": []}

        checks = []
        events = []
        blocked = False

        for policy in policies:
            if policy.policy_type not in ("pii_detection", "toxicity_filter", "topic_restriction"):
                continue

            check_result = await self._run_policy_check(policy, text)
            checks.append(check_result)

            if check_result["triggered"]:
                event = await self._create_event(
                    policy_id=str(policy.id),
                    event_type="input_blocked" if check_result["blocked"] else "input_warning",
                    severity=policy.severity,
                    input_text=text[:500],
                    details=check_result.get("details", {}),
                    action_taken="blocked" if check_result["blocked"] else "logged",
                    user_email=user_email,
                    workspace_id=workspace_id,
                )
                events.append(self._event_to_dict(event))
                if check_result["blocked"]:
                    blocked = True

        decision = "block" if blocked else "pass"
        processed_text = "" if blocked else text

        await self.db.flush()
        logger.info("guard_input_evaluated", decision=decision, checks=len(checks), events=len(events))
        return {
            "decision": decision,
            "text": processed_text,
            "checks": checks,
            "events": events,
        }

    # ================================================================
    # OUTPUT EVALUATION
    # ================================================================

    async def evaluate_output(
        self,
        text: str,
        workspace_id: Optional[str] = None,
        user_email: Optional[str] = None,
    ) -> dict:
        query = select(GuardPolicy).where(GuardPolicy.is_enabled == True)
        if workspace_id:
            query = query.where(GuardPolicy.workspace_id == workspace_id)
        result = await self.db.execute(query)
        policies = result.scalars().all()

        if not policies:
            return {"decision": "pass", "text": text, "checks": [], "events": []}

        checks = []
        events = []
        blocked = False

        for policy in policies:
            if policy.policy_type not in ("output_validation", "pii_detection", "toxicity_filter"):
                continue

            check_result = await self._run_policy_check(policy, text)
            checks.append(check_result)

            if check_result["triggered"]:
                event = await self._create_event(
                    policy_id=str(policy.id),
                    event_type="output_blocked" if check_result["blocked"] else "output_warning",
                    severity=policy.severity,
                    input_text=text[:500],
                    details=check_result.get("details", {}),
                    action_taken="blocked" if check_result["blocked"] else "logged",
                    user_email=user_email,
                    workspace_id=workspace_id,
                )
                events.append(self._event_to_dict(event))
                if check_result["blocked"]:
                    blocked = True

        decision = "block" if blocked else "pass"
        processed_text = "" if blocked else text

        await self.db.flush()
        logger.info("guard_output_evaluated", decision=decision, checks=len(checks), events=len(events))
        return {
            "decision": "pass" if not blocked else "block",
            "text": processed_text,
            "checks": checks,
            "events": events,
        }

    # ================================================================
    # EVENTS
    # ================================================================

    async def list_events(
        self,
        workspace_id: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        query = select(GuardEvent)
        if workspace_id:
            query = query.where(GuardEvent.workspace_id == workspace_id)
        if severity:
            query = query.where(GuardEvent.severity == severity)
        query = query.order_by(desc(GuardEvent.created_at)).limit(limit)

        result = await self.db.execute(query)
        return [self._event_to_dict(e) for e in result.scalars().all()]

    # ================================================================
    # POLICY CHECKS
    # ================================================================

    async def _run_policy_check(self, policy: GuardPolicy, text: str) -> dict:
        config = policy.config or {}

        if policy.policy_type == "pii_detection":
            return self._check_pii(text, config)
        elif policy.policy_type == "toxicity_filter":
            return self._check_toxicity(text, config)
        elif policy.policy_type == "topic_restriction":
            allowed_topics = config.get("allowed_topics", [])
            return self._check_topic(text, allowed_topics)
        elif policy.policy_type == "output_validation":
            max_length = config.get("max_length", 10000)
            required_patterns = config.get("required_patterns", [])
            return self._check_output_validation(text, max_length, required_patterns)
        else:
            return {"policy_id": str(policy.id), "policy_type": policy.policy_type, "triggered": False}

    def _check_pii(self, text: str, config: Optional[dict] = None) -> dict:
        patterns = {
            "email": r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            "phone": r'(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}',
            "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
            "credit_card": r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b',
            "ip_address": r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
        }

        config = config or {}
        enabled_types = config.get("pii_types", list(patterns.keys()))
        findings = {}

        for pii_type, pattern in patterns.items():
            if pii_type not in enabled_types:
                continue
            matches = re.findall(pattern, text)
            if matches:
                findings[pii_type] = {"count": len(matches), "examples": matches[:3]}

        blocked = config.get("block_on_match", True)
        triggered = len(findings) > 0
        severity = "blocked" if blocked and triggered else "warning" if triggered else "info"

        return {
            "policy_type": "pii_detection",
            "triggered": triggered,
            "blocked": blocked and triggered,
            "findings": findings,
            "details": {"pii_types_detected": list(findings.keys()), "total_matches": sum(f["count"] for f in findings.values())},
        }

    def _check_toxicity(self, text: str, config: Optional[dict] = None) -> dict:
        default_blocklist = [
            "kill yourself", "go die", "you're worthless",
            "hate speech", "violent content",
        ]
        config = config or {}
        blocklist = config.get("blocked_keywords", default_blocklist)
        case_sensitive = config.get("case_sensitive", False)

        check_text = text if case_sensitive else text.lower()
        findings = []

        for keyword in blocklist:
            check_keyword = keyword if case_sensitive else keyword.lower()
            if check_keyword in check_text:
                findings.append(keyword)

        blocked = config.get("block_on_match", True)
        triggered = len(findings) > 0

        return {
            "policy_type": "toxicity_filter",
            "triggered": triggered,
            "blocked": blocked and triggered,
            "findings": findings,
            "details": {"keywords_matched": findings, "match_count": len(findings)},
        }

    def _check_topic(self, text: str, allowed_topics: list[str]) -> dict:
        if not allowed_topics:
            return {"policy_type": "topic_restriction", "triggered": False, "blocked": False}

        text_lower = text.lower()
        matched_topics = []
        for topic in allowed_topics:
            if topic.lower() in text_lower:
                matched_topics.append(topic)

        triggered = len(matched_topics) == 0 and len(allowed_topics) > 0
        blocked = triggered

        return {
            "policy_type": "topic_restriction",
            "triggered": triggered,
            "blocked": blocked,
            "details": {
                "allowed_topics": allowed_topics,
                "matched_topics": matched_topics,
                "within_scope": not triggered,
            },
        }

    def _check_output_validation(
        self,
        text: str,
        max_length: int = 10000,
        required_patterns: Optional[list[str]] = None,
    ) -> dict:
        required_patterns = required_patterns or []
        findings = {}

        if len(text) > max_length:
            findings["length"] = {"actual": len(text), "max": max_length}

        for i, pattern in enumerate(required_patterns):
            try:
                if not re.search(pattern, text):
                    findings[f"pattern_{i}"] = {"pattern": pattern, "matched": False}
            except re.error:
                pass

        triggered = len(findings) > 0

        return {
            "policy_type": "output_validation",
            "triggered": triggered,
            "blocked": triggered,
            "details": findings,
        }

    # ================================================================
    # EVENT CREATION
    # ================================================================

    async def _create_event(
        self,
        policy_id: str,
        event_type: str,
        severity: str,
        input_text: Optional[str] = None,
        details: Optional[dict] = None,
        action_taken: Optional[str] = None,
        user_email: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> GuardEvent:
        event = GuardEvent(
            policy_id=_uid(policy_id),
            event_type=event_type,
            severity=severity,
            input_text=input_text,
            details=details or {},
            action_taken=action_taken,
            user_email=user_email,
            workspace_id=workspace_id,
        )
        self.db.add(event)
        await self.db.flush()
        return event

    # ================================================================
    # SERIALIZATION
    # ================================================================

    def _policy_to_dict(self, p: GuardPolicy) -> dict:
        return {
            "id": str(p.id),
            "name": p.name,
            "description": p.description,
            "policy_type": p.policy_type,
            "config": p.config or {},
            "severity": p.severity,
            "is_enabled": p.is_enabled,
            "workspace_id": p.workspace_id,
            "applies_to": p.applies_to or [],
            "created_by": p.created_by,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }

    def _event_to_dict(self, e: GuardEvent) -> dict:
        return {
            "id": str(e.id),
            "policy_id": str(e.policy_id) if e.policy_id else None,
            "event_type": e.event_type,
            "severity": e.severity,
            "input_text": e.input_text,
            "output_text": e.output_text,
            "details": e.details or {},
            "action_taken": e.action_taken,
            "user_email": e.user_email,
            "workspace_id": e.workspace_id,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
