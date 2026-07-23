import uuid
import hashlib
import re
from datetime import datetime
from typing import Optional
from sqlalchemy import select, func, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from panteon.aip.models import (
    RagDocument, RagChunk, KnowledgeEntity, KnowledgeRelation,
    DOC_STATUSES, CHUNK_STATUSES,
)
from panteon.core.database import is_sqlite
import structlog

logger = structlog.get_logger()


def _uid(val) -> str:
    if is_sqlite and val is not None:
        return str(val)
    return val


class RagService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ================================================================
    # DOCUMENT INGESTION
    # ================================================================

    async def ingest_document(
        self,
        title: str,
        content: str,
        source_type: str = "text",
        source_url: Optional[str] = None,
        workspace_id: Optional[str] = None,
        collection: str = "default",
        created_by: Optional[str] = None,
    ) -> RagDocument:
        content_hash = self._hash_content(content)

        existing = await self.db.execute(
            select(RagDocument).where(RagDocument.content_hash == content_hash)
        )
        if existing.scalar_one_or_none():
            logger.info("duplicate_document_skipped", title=title)

        doc = RagDocument(
            title=title,
            content=content,
            content_hash=content_hash,
            source_type=source_type,
            source_url=source_url,
            workspace_id=workspace_id,
            collection=collection,
            status="pending",
            created_by=created_by,
        )
        self.db.add(doc)
        await self.db.flush()

        try:
            chunks = self._chunk_text(content)
            for idx, chunk_text in enumerate(chunks):
                chunk = RagChunk(
                    document_id=_uid(doc.id),
                    content=chunk_text,
                    chunk_index=idx,
                    token_count=len(chunk_text.split()),
                    embedding_text=chunk_text,
                    status="pending",
                    metadata_json={"document_title": title, "chunk_index": idx},
                )
                self.db.add(chunk)

            doc.chunk_count = len(chunks)
            doc.status = "processed"
            doc.processed_at = datetime.utcnow()
            await self.db.flush()
            logger.info("document_ingested", document_id=str(doc.id), chunks=len(chunks))

        except Exception as e:
            doc.status = "failed"
            await self.db.flush()
            logger.error("document_ingestion_failed", document_id=str(doc.id), error=str(e))

        return doc

    # ================================================================
    # LIST / GET
    # ================================================================

    async def list_documents(
        self,
        workspace_id: Optional[str] = None,
        collection: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        query = select(RagDocument)
        if workspace_id:
            query = query.where(RagDocument.workspace_id == workspace_id)
        if collection:
            query = query.where(RagDocument.collection == collection)
        if status:
            query = query.where(RagDocument.status == status)
        query = query.order_by(desc(RagDocument.created_at)).limit(limit)

        result = await self.db.execute(query)
        return [self._doc_to_dict(d) for d in result.scalars().all()]

    async def get_document(self, document_id: str) -> Optional[dict]:
        result = await self.db.execute(
            select(RagDocument)
            .options(selectinload(RagDocument.chunks))
            .where(RagDocument.id == _uid(document_id))
        )
        doc = result.scalar_one_or_none()
        if not doc:
            return None
        return self._doc_to_dict(doc, include_chunks=True)

    # ================================================================
    # SEARCH
    # ================================================================

    async def search(
        self,
        query: str,
        workspace_id: Optional[str] = None,
        collection: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        if not query or len(query.strip()) < 2:
            return []

        keywords = query.strip().split()
        conditions = []
        for kw in keywords:
            pattern = f"%{kw}%"
            conditions.append(RagChunk.content.like(pattern))

        chunk_query = select(RagChunk).where(or_(*conditions))
        chunk_query = chunk_query.order_by(desc(RagChunk.created_at)).limit(limit)

        result = await self.db.execute(chunk_query)
        chunks = result.scalars().all()

        results = []
        seen_docs = set()
        for chunk in chunks:
            doc_result = await self.db.execute(
                select(RagDocument).where(RagDocument.id == _uid(chunk.document_id))
            )
            doc = doc_result.scalar_one_or_none()
            if not doc:
                continue
            if workspace_id and doc.workspace_id != workspace_id:
                continue
            if collection and doc.collection != collection:
                continue
            if str(doc.id) in seen_docs:
                continue
            seen_docs.add(str(doc.id))
            results.append({
                "document_id": str(doc.id),
                "title": doc.title,
                "collection": doc.collection,
                "chunk_id": str(chunk.id),
                "chunk_index": chunk.chunk_index,
                "content_preview": chunk.content[:300],
                "token_count": chunk.token_count,
            })

        logger.info("rag_search", query=query, results=len(results))
        return results

    # ================================================================
    # KNOWLEDGE EXTRACTION
    # ================================================================

    async def extract_knowledge(self, document_id: str) -> dict:
        result = await self.db.execute(
            select(RagDocument).where(RagDocument.id == _uid(document_id))
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise ValueError("Document not found")

        content = doc.content
        workspace_id = doc.workspace_id

        person_patterns = [
            r'(?:Mr\.|Mrs\.|Ms\.|Dr\.|Prof\.)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*',
            r'[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?',
        ]
        org_patterns = [
            r'[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*\s+(?:Inc|Corp|Ltd|LLC|Co|Group|Foundation|Institute|University|Association)',
            r'(?:Google|Microsoft|Apple|Amazon|Meta|Tesla|OpenAI|Anthropic)',
        ]
        location_patterns = [
            r'(?:New York|Los Angeles|San Francisco|Chicago|Houston|London|Paris|Berlin|Tokyo|Beijing|Sydney)',
            r'(?:California|Texas|New York|Florida|Washington)\s*(?:State)?',
            r'(?:USA|UK|Germany|France|Japan|China|Australia|Canada|Brazil|India)',
        ]
        date_patterns = [
            r'\d{4}-\d{2}-\d{2}',
            r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}',
            r'\d{1,2}/\d{1,2}/\d{4}',
        ]

        extracted = {"persons": set(), "organizations": set(), "locations": set(), "dates": set()}

        for pattern in person_patterns:
            for match in re.finditer(pattern, content):
                extracted["persons"].add(match.group().strip())

        for pattern in org_patterns:
            for match in re.finditer(pattern, content):
                extracted["organizations"].add(match.group().strip())

        for pattern in location_patterns:
            for match in re.finditer(pattern, content):
                extracted["locations"].add(match.group().strip())

        for pattern in date_patterns:
            for match in re.finditer(pattern, content):
                extracted["dates"].add(match.group().strip())

        entities_created = {}
        for entity_type, names in [
            ("person", extracted["persons"]),
            ("organization", extracted["organizations"]),
            ("location", extracted["locations"]),
            ("date", extracted["dates"]),
        ]:
            for name in names:
                existing = await self.db.execute(
                    select(KnowledgeEntity).where(
                        KnowledgeEntity.name == name,
                        KnowledgeEntity.entity_type == entity_type,
                        KnowledgeEntity.workspace_id == workspace_id if workspace_id else True,
                    )
                )
                entity = existing.scalar_one_or_none()
                if entity:
                    source_ids = entity.source_document_ids or []
                    if str(doc.id) not in source_ids:
                        source_ids.append(str(doc.id))
                        entity.source_document_ids = source_ids
                        entity.updated_at = datetime.utcnow()
                else:
                    entity = KnowledgeEntity(
                        name=name,
                        entity_type=entity_type,
                        workspace_id=workspace_id,
                        source_document_ids=[str(doc.id)],
                    )
                    self.db.add(entity)
                await self.db.flush()
                entities_created[f"{entity_type}:{name}"] = str(entity.id)

        relations_created = 0
        entity_ids = list(entities_created.values())
        if len(entity_ids) >= 2:
            for i, eid_a in enumerate(entity_ids[:10]):
                for eid_b in entity_ids[i + 1:i + 4]:
                    rel_exists = await self.db.execute(
                        select(KnowledgeRelation).where(
                            KnowledgeRelation.source_entity_id == _uid(eid_a),
                            KnowledgeRelation.target_entity_id == _uid(eid_b),
                        )
                    )
                    if not rel_exists.scalar_one_or_none():
                        rel = KnowledgeRelation(
                            source_entity_id=_uid(eid_a),
                            target_entity_id=_uid(eid_b),
                            relation_type="co_occurs",
                            confidence=0.7,
                            source_document_ids=[str(doc.id)],
                        )
                        self.db.add(rel)
                        relations_created += 1
            await self.db.flush()

        logger.info(
            "knowledge_extracted",
            document_id=str(doc.id),
            entities=len(entities_created),
            relations=relations_created,
        )
        return {
            "entities_created": len(entities_created),
            "relations_created": relations_created,
            "persons": list(extracted["persons"]),
            "organizations": list(extracted["organizations"]),
            "locations": list(extracted["locations"]),
            "dates": list(extracted["dates"]),
        }

    # ================================================================
    # KNOWLEDGE GRAPH
    # ================================================================

    async def list_entities(
        self,
        workspace_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        query = select(KnowledgeEntity)
        if workspace_id:
            query = query.where(KnowledgeEntity.workspace_id == workspace_id)
        if entity_type:
            query = query.where(KnowledgeEntity.entity_type == entity_type)
        query = query.order_by(desc(KnowledgeEntity.created_at)).limit(limit)

        result = await self.db.execute(query)
        return [
            {
                "id": str(e.id),
                "name": e.name,
                "entity_type": e.entity_type,
                "workspace_id": e.workspace_id,
                "description": e.description,
                "attributes": e.attributes or {},
                "source_document_ids": e.source_document_ids or [],
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in result.scalars().all()
        ]

    async def get_entity_graph(self, workspace_id: Optional[str] = None) -> dict:
        entity_query = select(KnowledgeEntity)
        if workspace_id:
            entity_query = entity_query.where(KnowledgeEntity.workspace_id == workspace_id)
        entity_result = await self.db.execute(entity_query)
        entities = entity_result.scalars().all()

        entity_ids = [str(e.id) for e in entities]

        if not entity_ids:
            return {"nodes": [], "edges": [], "stats": {"node_count": 0, "edge_count": 0}}

        rel_query = select(KnowledgeRelation).where(
            or_(
                KnowledgeRelation.source_entity_id.in_([_uid(eid) for eid in entity_ids]),
                KnowledgeRelation.target_entity_id.in_([_uid(eid) for eid in entity_ids]),
            )
        )
        rel_result = await self.db.execute(rel_query)
        relations = rel_result.scalars().all()

        nodes = [
            {
                "id": str(e.id),
                "name": e.name,
                "type": e.entity_type,
            }
            for e in entities
        ]

        edges = [
            {
                "source": str(r.source_entity_id),
                "target": str(r.target_entity_id),
                "type": r.relation_type,
                "confidence": r.confidence,
            }
            for r in relations
        ]

        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "entity_types": list({e.entity_type for e in entities}),
            },
        }

    # ================================================================
    # HELPERS
    # ================================================================

    def _chunk_text(self, text: str, max_tokens: int = 500) -> list[str]:
        if not text:
            return []

        words = text.split()
        chunks = []
        current_chunk = []
        current_count = 0

        for word in words:
            current_chunk.append(word)
            current_count += 1
            if current_count >= max_tokens:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_count = 0

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks

    def _hash_content(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _doc_to_dict(self, doc: RagDocument, include_chunks: bool = False) -> dict:
        result = {
            "id": str(doc.id),
            "title": doc.title,
            "content_hash": doc.content_hash,
            "source_type": doc.source_type,
            "source_url": doc.source_url,
            "workspace_id": doc.workspace_id,
            "collection": doc.collection,
            "status": doc.status,
            "metadata_json": doc.metadata_json or {},
            "chunk_count": doc.chunk_count or 0,
            "created_by": doc.created_by,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "processed_at": doc.processed_at.isoformat() if doc.processed_at else None,
        }
        if include_chunks and doc.chunks:
            result["chunks"] = [
                {
                    "id": str(c.id),
                    "content": c.content,
                    "chunk_index": c.chunk_index,
                    "token_count": c.token_count,
                    "status": c.status,
                    "metadata_json": c.metadata_json or {},
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in sorted(doc.chunks, key=lambda c: c.chunk_index)
            ]
        return result
