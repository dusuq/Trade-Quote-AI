"""HTTP routes for the AI Quote Assistant.

Every route trusts the gateway's `x-tenant-id` header and never decodes a JWT
(conventions §1). There are no public routes on this service.

**Transaction discipline (ADR-0003 rule 3):** the quote pipeline makes
blocking calls to an LLM and two upstream services, so it must not run inside
an open database transaction. Each route therefore reads spend-to-date in one
short transaction, runs the pipeline with nothing open, then writes usage in
another. `_run_metered` encapsulates that so no route can get it wrong.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, UploadFile, status

from app.application.copilot_missing import FindMissingItemsUseCase
from app.application.copilot_pricing import AnalyzePricingUseCase
from app.application.copilot_rewrite import RewriteUseCase
from app.application.line_items import DEFAULT_MARKUP_BPS
from app.application.scope_writer import ScopeWriterUseCase
from app.application.text_to_quote import TextToQuoteUseCase
from app.application.voice_to_quote import VoiceToQuoteUseCase
from app.config import settings
from app.domain.errors import (
    AudioTooLargeError,
    CopilotAnalysisError,
    DailySpendCapExceededError,
    QuoteNotFoundError,
    ScopeExtractionError,
    TranscriptionError,
    UnsupportedAudioFormatError,
    UpstreamServiceError,
)
from app.infrastructure.db import tenant_session
from app.infrastructure.usage_repository import (
    BufferedAiUsageRepository,
    SqlAlchemyAiUsageRepository,
)
from app.interface.deps import deps
from app.interface.schemas import (
    AiUsageResponse,
    AnalyzePricingRequest,
    MissingItemsRequest,
    MissingItemsResponse,
    PricingAnalysisResponse,
    QuoteDraftResponse,
    RewriteRequest,
    RewriteResponse,
    ScopeWriterRequest,
    ScopeWriterResponse,
    TextToQuoteRequest,
    to_missing_items_response,
    to_pricing_analysis_response,
    to_quote_draft_response,
    to_rewrite_response,
)

router = APIRouter(prefix="/v1/ai", tags=["ai"])


def _require_tenant(x_tenant_id: str | None) -> uuid.UUID:
    if not x_tenant_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing tenant context")
    try:
        return uuid.UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid tenant id") from exc


def _optional_actor(x_user_id: str | None) -> uuid.UUID | None:
    if not x_user_id:
        return None
    try:
        return uuid.UUID(x_user_id)
    except ValueError:
        return None


def _run_metered[T](
    tenant_id: uuid.UUID, work: Callable[[BufferedAiUsageRepository], T]
) -> T:
    """Read the spend cap, run `work` with no transaction open, persist usage.

    The three phases are deliberately separate — see the module docstring.
    """
    with tenant_session(tenant_id) as session:
        spend_today = SqlAlchemyAiUsageRepository(session).spend_today_minor(tenant_id)

    usage_repo = BufferedAiUsageRepository(spend_today)
    result = work(usage_repo)  # network + model calls happen here, unwrapped

    if usage_repo.pending:
        with tenant_session(tenant_id) as session:
            repository = SqlAlchemyAiUsageRepository(session)
            for usage in usage_repo.pending:
                repository.record(tenant_id, usage)
    return result


def _translate(exc: Exception) -> HTTPException:
    """Map a domain error to its HTTP status."""
    if isinstance(exc, AudioTooLargeError):
        return HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(exc))
    if isinstance(exc, UnsupportedAudioFormatError):
        return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    if isinstance(exc, DailySpendCapExceededError):
        return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc))
    if isinstance(exc, QuoteNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "quote not found")
    if isinstance(exc, ScopeExtractionError | CopilotAnalysisError):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    if isinstance(exc, TranscriptionError | UpstreamServiceError):
        # The request was fine; something we depend on wasn't. 502 says that
        # honestly instead of blaming the caller.
        return HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    raise exc


@router.post("/text-to-quote", response_model=QuoteDraftResponse, status_code=status.HTTP_201_CREATED)
def text_to_quote(
    body: TextToQuoteRequest,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> QuoteDraftResponse:
    tenant_id = _require_tenant(x_tenant_id)
    actor_id = _optional_actor(x_user_id)

    def work(usage_repo: BufferedAiUsageRepository) -> QuoteDraftResponse:
        use_case = TextToQuoteUseCase(
            deps.extractor(),
            deps.matcher(),
            deps.quote_creator(),
            usage_repo,
            daily_cap_minor=settings.daily_spend_cap_minor,
        )
        result, _events = use_case.execute(
            tenant_id=tenant_id,
            user_id=actor_id,
            text=body.text,
            customer_id=body.customer_id,
            property_id=body.property_id,
            title=body.title,
            trade_hint=body.trade_hint,
            tax_rate_bps=body.tax_rate_bps,
            default_markup_bps=body.default_markup_bps,
        )
        # TODO(outbox): publish _events once a transactional outbox exists
        # (same TODO carried by proposal-service and esign-service).
        return to_quote_draft_response(result)

    try:
        return _run_metered(tenant_id, work)
    except Exception as exc:
        raise _translate(exc) from exc


@router.post(
    "/voice-to-quote", response_model=QuoteDraftResponse, status_code=status.HTTP_201_CREATED
)
async def voice_to_quote(
    audio: UploadFile = File(...),
    customer_id: uuid.UUID = Form(...),
    property_id: uuid.UUID | None = Form(default=None),
    title: str | None = Form(default=None),
    trade_hint: str | None = Form(default=None),
    tax_rate_bps: int = Form(default=0),
    default_markup_bps: int = Form(default=DEFAULT_MARKUP_BPS),
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> QuoteDraftResponse:
    tenant_id = _require_tenant(x_tenant_id)
    actor_id = _optional_actor(x_user_id)

    if not settings.feature_ai_voice:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "voice input is disabled")

    audio_bytes = await audio.read()
    mime_type = audio.content_type or "application/octet-stream"

    def work(usage_repo: BufferedAiUsageRepository) -> QuoteDraftResponse:
        text_use_case = TextToQuoteUseCase(
            deps.extractor(),
            deps.matcher(),
            deps.quote_creator(),
            usage_repo,
            daily_cap_minor=settings.daily_spend_cap_minor,
        )
        use_case = VoiceToQuoteUseCase(
            deps.transcription(),
            text_use_case,
            max_audio_bytes=settings.max_audio_size_bytes,
        )
        result, _events = use_case.execute(
            tenant_id=tenant_id,
            user_id=actor_id,
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            customer_id=customer_id,
            property_id=property_id,
            title=title,
            trade_hint=trade_hint,
            tax_rate_bps=tax_rate_bps,
            default_markup_bps=default_markup_bps,
        )
        return to_quote_draft_response(result)

    try:
        return _run_metered(tenant_id, work)
    except Exception as exc:
        raise _translate(exc) from exc


@router.post("/scope-writer", response_model=ScopeWriterResponse)
def write_scope(
    body: ScopeWriterRequest,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> ScopeWriterResponse:
    tenant_id = _require_tenant(x_tenant_id)
    actor_id = _optional_actor(x_user_id)

    def work(usage_repo: BufferedAiUsageRepository) -> ScopeWriterResponse:
        use_case = ScopeWriterUseCase(
            deps.narrator(), usage_repo, daily_cap_minor=settings.daily_spend_cap_minor
        )
        scope_text, usage, _event = use_case.execute(
            tenant_id=tenant_id,
            user_id=actor_id,
            scope=body.to_scope(),
            tone=body.tone,
        )
        return ScopeWriterResponse(
            scope_text=scope_text, model_id=usage.model_id, tokens_used=usage.tokens_used
        )

    try:
        return _run_metered(tenant_id, work)
    except Exception as exc:
        raise _translate(exc) from exc


def _require_copilot() -> None:
    if not settings.feature_copilot:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "copilot is disabled")


@router.post("/copilot/analyze-pricing", response_model=PricingAnalysisResponse)
def analyze_pricing(
    body: AnalyzePricingRequest,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> PricingAnalysisResponse:
    """Analyze a quote's pricing against the pricebook and flag margin issues."""
    _require_copilot()
    tenant_id = _require_tenant(x_tenant_id)
    actor_id = _optional_actor(x_user_id)

    def work(usage_repo: BufferedAiUsageRepository) -> PricingAnalysisResponse:
        use_case = AnalyzePricingUseCase(
            deps.quote_reader(),
            deps.matcher(),
            deps.copilot_analyzer(),
            usage_repo,
            daily_cap_minor=settings.daily_spend_cap_minor,
        )
        result, _events = use_case.execute(
            tenant_id=tenant_id, user_id=actor_id, quote_id=body.quote_id
        )
        return to_pricing_analysis_response(body.quote_id, result)

    try:
        return _run_metered(tenant_id, work)
    except Exception as exc:
        raise _translate(exc) from exc


@router.post("/copilot/missing-items", response_model=MissingItemsResponse)
def find_missing_items(
    body: MissingItemsRequest,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> MissingItemsResponse:
    """Detect missing materials, labor, or equipment for this trade and scope."""
    _require_copilot()
    tenant_id = _require_tenant(x_tenant_id)
    actor_id = _optional_actor(x_user_id)

    def work(usage_repo: BufferedAiUsageRepository) -> MissingItemsResponse:
        use_case = FindMissingItemsUseCase(
            deps.quote_reader(),
            deps.copilot_analyzer(),
            usage_repo,
            daily_cap_minor=settings.daily_spend_cap_minor,
        )
        result, _events = use_case.execute(
            tenant_id=tenant_id,
            user_id=actor_id,
            quote_id=body.quote_id,
            job_description=body.job_description,
        )
        return to_missing_items_response(body.quote_id, result)

    try:
        return _run_metered(tenant_id, work)
    except Exception as exc:
        raise _translate(exc) from exc


@router.post("/copilot/rewrite", response_model=RewriteResponse)
def rewrite_text(
    body: RewriteRequest,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> RewriteResponse:
    """Rewrite descriptions or scope text in a professional (or given) tone."""
    _require_copilot()
    tenant_id = _require_tenant(x_tenant_id)
    actor_id = _optional_actor(x_user_id)

    def work(usage_repo: BufferedAiUsageRepository) -> RewriteResponse:
        use_case = RewriteUseCase(
            deps.text_rewriter(), usage_repo, daily_cap_minor=settings.daily_spend_cap_minor
        )
        result, _events = use_case.execute(
            tenant_id=tenant_id,
            user_id=actor_id,
            texts=body.texts,
            tone=body.tone,
            context_hint=body.context_hint,
        )
        return to_rewrite_response(result)

    try:
        return _run_metered(tenant_id, work)
    except Exception as exc:
        raise _translate(exc) from exc


@router.get("/usage", response_model=list[AiUsageResponse])
def list_usage(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    x_tenant_id: str | None = Header(default=None),
) -> list[AiUsageResponse]:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as session:
        records = SqlAlchemyAiUsageRepository(session).list_for_tenant(
            tenant_id, skip=skip, limit=limit
        )
        return [
            AiUsageResponse(
                id=record.id,
                feature=record.feature.value,
                model_id=record.model_id,
                input_kind=record.input_kind,
                tokens_used=record.tokens_used,
                cost_minor=record.cost_minor,
                created_at=record.created_at,
            )
            for record in records
        ]
