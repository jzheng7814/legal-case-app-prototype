from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Protocol, Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.db.models import (
    ChecklistRun,
    ChecklistRunItem,
    ChecklistRunStatus,
    ChecklistTemplate,
    ChecklistTemplateItem,
    ChecklistTemplateStatus,
    DocumentSet,
    DocumentSetDocument,
    DocumentSetType,
    DocumentSource,
    User,
)
from app.db.session import session_scope
from app.schemas.checklists import ChecklistCollection, ChecklistExtractionPayload, ChecklistItemResult
from app.utils.cases import normalize_case_id

logger = logging.getLogger(__name__)

DocumentChecklistPayload = ChecklistCollection


@dataclass(frozen=True)
class StoredDocumentChecklist:
    """Container for a stored checklist record."""

    signature: str
    items: DocumentChecklistPayload


class DocumentChecklistStore(Protocol):
    """Interface that supports persisting checklist results."""

    def get(self, case_id: str, *, signature: Optional[str] = None) -> Optional[StoredDocumentChecklist]:
        """Return the stored checklist for a case, optionally validating a signature."""

    def set(
        self,
        case_id: str,
        *,
        signature: str,
        items: DocumentChecklistPayload,
        documents_payloads: Optional[Sequence[Dict[str, str]]] = None,
    ) -> None:
        """Persist a checklist for a case."""

    def clear(self, case_id: str) -> None:
        """Remove cached checklist data for a case."""


class DatabaseDocumentChecklistStore(DocumentChecklistStore):
    """Database-backed checklist persistence built on the relational schema."""

    def __init__(self, item_definitions: Dict[str, str]) -> None:
        self._item_definitions = dict(item_definitions)
        self._default_user_email = "checklists@legalcase.app"
        self._default_user_name = "Checklist Automation"
        self._template_slug = "document-checklist"
        self._template_version = 1

    def get(self, case_id: str, *, signature: Optional[str] = None) -> Optional[StoredDocumentChecklist]:
        normalized = normalize_case_id(case_id)
        with session_scope() as session:
            document_set = self._find_document_set(session, normalized, signature)
            if document_set is None:
                return None
            template = self._ensure_default_template(session)
            user = self._ensure_default_user(session)
            run = self._find_latest_run(session, document_set.id, template.id, user.id)
            if run is None:
                return None

            results_by_key = {item.template_item.item_key: item for item in run.items}
            checklist_items: list[ChecklistItemResult] = []
            for template_item in template.items:
                stored_item = results_by_key.get(template_item.item_key)
                if stored_item is None:
                    continue
                extraction = ChecklistExtractionPayload.model_validate(stored_item.payload)
                checklist_items.append(
                    ChecklistItemResult(item_name=template_item.display_name, extraction=extraction)
                )
            return StoredDocumentChecklist(signature=document_set.doc_hash, items=ChecklistCollection(items=checklist_items))

    def set(
        self,
        case_id: str,
        *,
        signature: str,
        items: DocumentChecklistPayload,
        documents_payloads: Optional[Sequence[Dict[str, str]]] = None,
    ) -> None:
        normalized = normalize_case_id(case_id)
        with session_scope() as session:
            user = self._ensure_default_user(session)
            template = self._ensure_default_template(session)
            document_set = self._ensure_document_set(session, normalized, signature, documents_payloads)
            if document_set is None:
                logger.warning("Skipping checklist persistence for case %s; document set missing.", normalized)
                return
            if document_set.id is None:
                session.flush([document_set])

            now = datetime.now(timezone.utc)
            run = ChecklistRun(
                user_id=user.id,
                template_id=template.id,
                document_set_id=document_set.id,
                status=ChecklistRunStatus.COMPLETED,
                started_at=now,
                completed_at=now,
                model_name=None,
                prompt_hash=self._build_prompt_hash(signature, template),
                error_reason=None,
            )
            session.add(run)

            results_by_key = {self._slugify(result.item_name): result for result in items.items}
            for template_item in template.items:
                result = results_by_key.get(template_item.item_key)
                extraction = (
                    result.extraction if result else ChecklistExtractionPayload(reasoning="", extracted=[])
                )
                run.items.append(
                    ChecklistRunItem(
                        template_item_id=template_item.id,
                        payload=extraction.model_dump(mode="json"),
                        confidence=None,
                        notes=None,
                    )
                )

    def clear(self, case_id: str) -> None:
        normalized = normalize_case_id(case_id)
        with session_scope() as session:
            template = self._ensure_default_template(session)
            user = self._ensure_default_user(session)
            doc_set_ids = session.execute(
                select(DocumentSet.id).where(
                    DocumentSet.case_identifier == normalized,
                    DocumentSet.type == DocumentSetType.CLEARINGHOUSE,
                    DocumentSet.user_id.is_(None),
                )
            ).scalars().all()
            if not doc_set_ids:
                return
            session.execute(
                delete(ChecklistRun).where(
                    ChecklistRun.document_set_id.in_(doc_set_ids),
                    ChecklistRun.user_id == user.id,
                    ChecklistRun.template_id == template.id,
                )
            )

    def _ensure_default_user(self, session) -> User:
        stmt = select(User).where(User.email == self._default_user_email)
        user = session.execute(stmt).scalars().first()
        if user is None:
            user = User(
                email=self._default_user_email,
                full_name=self._default_user_name,
                role="system",
                is_active=True,
            )
            session.add(user)
            session.flush([user])
        return user

    def _ensure_default_template(self, session) -> ChecklistTemplate:
        stmt = (
            select(ChecklistTemplate)
            .where(
                ChecklistTemplate.slug == self._template_slug,
                ChecklistTemplate.version == self._template_version,
            )
            .options(selectinload(ChecklistTemplate.items))
        )
        template = session.execute(stmt).scalars().first()
        if template is None:
            template = ChecklistTemplate(
                slug=self._template_slug,
                version=self._template_version,
                status=ChecklistTemplateStatus.PUBLISHED,
                name="Document Checklist",
                description="LLM-generated checklist for clearinghouse documents",
                owner_user_id=self._ensure_default_user(session).id,
                parent_template_id=None,
                is_builtin=True,
            )
            session.add(template)
            session.flush([template])
        self._sync_template_items(session, template)
        session.refresh(template)
        return template

    def _sync_template_items(self, session, template: ChecklistTemplate) -> None:
        existing = {item.item_key: item for item in template.items}
        for order, (name, description) in enumerate(self._item_definitions.items()):
            key = self._slugify(name)
            item = existing.get(key)
            if item is None:
                item = ChecklistTemplateItem(
                    template_id=template.id,
                    item_key=key,
                    display_name=name,
                    item_order=order,
                    prompt=description,
                    metadata_json={"description": description},
                )
                session.add(item)
                template.items.append(item)
            else:
                item.display_name = name
                item.item_order = order
                item.prompt = description
                item.metadata_json = {"description": description}

    def _find_document_set(self, session, case_id: str, signature: Optional[str]) -> Optional[DocumentSet]:
        stmt = (
            select(DocumentSet)
            .where(
                DocumentSet.case_identifier == case_id,
                DocumentSet.type == DocumentSetType.CLEARINGHOUSE,
                DocumentSet.user_id.is_(None),
            )
            .options(selectinload(DocumentSet.documents))
            .order_by(DocumentSet.updated_at.desc())
        )
        if signature:
            stmt = stmt.where(DocumentSet.doc_hash == signature)
        return session.execute(stmt).scalars().first()

    def _find_latest_run(
        self,
        session,
        document_set_id: int,
        template_id: int,
        user_id: int,
    ) -> Optional[ChecklistRun]:
        stmt = (
            select(ChecklistRun)
            .where(
                ChecklistRun.document_set_id == document_set_id,
                ChecklistRun.template_id == template_id,
                ChecklistRun.user_id == user_id,
                ChecklistRun.status == ChecklistRunStatus.COMPLETED,
            )
            .options(selectinload(ChecklistRun.items).selectinload(ChecklistRunItem.template_item))
            .order_by(ChecklistRun.completed_at.desc().nullslast(), ChecklistRun.id.desc())
        )
        return session.execute(stmt).scalars().first()

    def _ensure_document_set(
        self,
        session,
        case_id: str,
        signature: str,
        payloads: Optional[Sequence[Dict[str, str]]],
    ) -> Optional[DocumentSet]:
        stmt = (
            select(DocumentSet)
            .where(
                DocumentSet.case_identifier == case_id,
                DocumentSet.doc_hash == signature,
                DocumentSet.type == DocumentSetType.CLEARINGHOUSE,
                DocumentSet.user_id.is_(None),
            )
            .options(selectinload(DocumentSet.documents))
        )
        document_set = session.execute(stmt).scalars().first()
        if document_set:
            return document_set
        if not payloads:
            return None

        document_set = DocumentSet(
            type=DocumentSetType.CLEARINGHOUSE,
            case_identifier=case_id,
            user_id=None,
            doc_hash=signature,
            title=f"Case {case_id} documents",
            description="Checklist persistence snapshot",
        )
        session.add(document_set)
        for position, payload in enumerate(payloads):
            metadata = {
                "title": payload.get("title"),
                "type": payload.get("type"),
                "content": payload.get("text"),
            }
            document_set.documents.append(
                DocumentSetDocument(
                    source=DocumentSource.CLEARINGHOUSE,
                    remote_document_id=str(payload.get("id")),
                    manual_document_id=None,
                    position=position,
                    display_name=payload.get("title"),
                    doc_type=payload.get("type"),
                    metadata_json=metadata,
                )
            )
        return document_set

    def _build_prompt_hash(self, signature: str, template: ChecklistTemplate) -> str:
        digest = hashlib.sha256()
        digest.update(signature.encode("utf-8"))
        digest.update(template.slug.encode("utf-8"))
        digest.update(str(template.version).encode("utf-8"))
        return digest.hexdigest()

    @staticmethod
    def _slugify(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        return slug or "item"
