# T201 — AI Quote Assistant: Complete Development Plan

**Module:** M15 · **Owner:** Agent 1 (CTO / Opus 4.8) · **Support:** Agent 3 (Gemini)
**Deps:** T106 ✅ (Quote Engine) · **Unblocks:** T202 (AI Copilot), T304/T305/T306 (Vision/OCR/Sales Coach)
**Bounded Context:** `services/ai-service` · **Phase:** 2

---

## Executive Summary

T201 builds the **AI Quote Assistant** — the flagship AI feature of TradeQuote AI. A contractor speaks or types a job description (e.g., *"I need 12 LED lights, replace panel, install breaker"*), and the system:

1. **Transcribes** voice → text (Whisper / Google STT)
2. **Extracts** structured scope (trade, materials, labor, tasks)
3. **Matches** items against the tenant's pricebook
4. **Generates** line items with proper pricing (minor units / basis points)
5. **Creates** a draft quote via `quote-service` with `created_via: "voice"`

This is the core differentiator — *"the Canva of Trade Quotes"* — turning a 30-minute quoting process into 2 minutes.

---

## User Review Required

> [!IMPORTANT]
> **LLM Provider Selection:** The tech stack specifies both Anthropic Claude and OpenAI. This plan uses **OpenAI Whisper** for speech-to-text and **Anthropic Claude** (claude-sonnet-4-20250514) for NLP scope extraction. Confirm these choices or specify alternatives.

> [!IMPORTANT]
> **API Key Management:** The `.env.example` already declares `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and `GEMINI_API_KEY`. This plan assumes they are available at runtime. Confirm no vault/secrets-manager integration is needed for MVP.

> [!WARNING]
> **Audio Upload Size Limit:** Whisper supports up to 25 MB per request (~25 min of audio). This plan sets a **10 MB / 5 min cap** for MVP. Larger recordings will need chunked transcription (post-MVP).

---

## Open Questions

> [!IMPORTANT]
> **Q1: Pricebook Matching Strategy** — When the LLM extracts a material like *"200A panel"*, should the AI service call the `pricebook-service` HTTP API directly (service-to-service), or should it query pricebook items via the database (shared read-model)? **Recommendation:** HTTP call to `pricebook-service` (preserves bounded-context isolation, consistent with architecture). This introduces a sync service-to-service call — the T307b audit flagged this pattern as needing an ADR. **Should we write ADR-0003 for this?**

> [!IMPORTANT]
> **Q2: Scope Writer** — T201 description includes "scope/proposal writing." Should the scope-writing feature (generating professional scope-of-work text from structured data) be part of T201, or deferred to T202 (AI Copilot)? **Recommendation:** Include a basic `POST /v1/ai/scope-writer` endpoint in T201 since it shares the LLM infrastructure, but keep it minimal — T202 will add the full copilot capabilities.

> [!IMPORTANT]
> **Q3: Web UI** — Should T201 include a web UI (voice record button + AI quote creation flow in `apps/web`), or only the backend API? **Recommendation:** Backend API only in T201; web UI as a follow-up task (T201b), mirroring the T204/T204b pattern.

---

## Architecture Design

### System Flow

```mermaid
sequenceDiagram
    participant Client as Web/Mobile Client
    participant GW as API Gateway
    participant AI as AI Service (T201)
    participant STT as Whisper API
    participant LLM as Claude API
    participant PB as Pricebook Service
    participant QS as Quote Service

    Client->>GW: POST /v1/ai/voice-to-quote<br/>(audio file + customer_id)
    GW->>AI: Forward (x-tenant-id, x-user-id)
    AI->>STT: Transcribe audio
    STT-->>AI: Raw transcript text
    AI->>LLM: Extract structured scope<br/>(trade, materials, labor, tasks)
    LLM-->>AI: Structured JSON
    AI->>PB: GET /v1/pricebook?search=<item><br/>(per extracted item)
    PB-->>AI: Matching pricebook items
    AI->>QS: POST /v1/quotes<br/>(created_via: "voice", line_items)
    QS-->>AI: Created quote
    AI-->>GW: Quote + AI metadata
    GW-->>Client: 201 Created
```

### Alternative Flow (Text Input)

```mermaid
sequenceDiagram
    participant Client as Web/Mobile Client
    participant GW as API Gateway
    participant AI as AI Service (T201)
    participant LLM as Claude API
    participant PB as Pricebook Service
    participant QS as Quote Service

    Client->>GW: POST /v1/ai/text-to-quote<br/>(text description + customer_id)
    GW->>AI: Forward (x-tenant-id, x-user-id)
    AI->>LLM: Extract structured scope
    LLM-->>AI: Structured JSON
    AI->>PB: GET /v1/pricebook?search=<item>
    PB-->>AI: Matching items
    AI->>QS: POST /v1/quotes<br/>(created_via: "voice", line_items)
    QS-->>AI: Created quote
    AI-->>GW: Quote + AI metadata
    GW-->>Client: 201 Created
```

---

## Proposed Changes

### Component 1: AI Service Backend (`services/ai-service/`)

This is the primary deliverable. Build the full service from the current README-only state.

#### [NEW] `services/ai-service/pyproject.toml`

Standard uv/Poetry project config with dependencies:
- `fastapi`, `uvicorn`, `pydantic`
- `httpx` (for calling Whisper API, Claude API, pricebook-service, quote-service)
- `anthropic` (Claude SDK for scope extraction)
- `openai` (Whisper API for transcription)
- `python-multipart` (for file uploads)
- `sqlalchemy`, `psycopg2-binary` (for AI usage tracking persistence)
- Dev: `pytest`, `pytest-asyncio`, `ruff`, `mypy`, `httpx` (test client)

Includes mandatory `[tool.ruff]`, `[tool.mypy]`, and `[tool.ruff.lint.flake8-bugbear]` sections per conventions §7.

#### [NEW] `services/ai-service/main.py`

FastAPI app with `/health` endpoint. Port **8008** (next available after esign-service on 8007).

#### [NEW] `services/ai-service/app/domain/`

**`models.py`** — Domain entities:
```python
class TranscriptionResult:
    """Value object: raw STT output."""
    text: str
    language: str
    duration_seconds: float
    confidence: float

class ExtractedScope:
    """Value object: LLM-extracted structured scope."""
    trade: str                    # "electrical" | "plumbing" | "hvac" | "solar" | ...
    summary: str                  # One-line job summary
    tasks: list[ExtractedTask]    # Individual work items
    notes: str | None             # Additional context

class ExtractedTask:
    """A single task extracted from the job description."""
    description: str
    category: str                 # "material" | "labor" | "equipment"
    item_name: str                # e.g., "200A panel", "LED recessed light"
    quantity: float
    unit: str                     # "each", "ft", "hr", "sqft"
    
class PricebookMatch:
    """A matched pricebook item for an extracted task."""
    pricebook_item_id: UUID
    name: str
    kind: str
    unit_cost_minor: int
    unit: str
    confidence: float             # 0.0-1.0 match confidence

class QuoteAssistantResult:
    """Complete result of voice/text-to-quote pipeline."""
    transcript: TranscriptionResult | None
    scope: ExtractedScope
    matches: list[PricebookMatch]
    unmatched_items: list[ExtractedTask]
    quote_id: UUID
    model_id: str
    tokens_used: int
```

**`events.py`** — Domain events (mirrors `packages/types`):
```python
@dataclass
class AiQuoteDrafted:
    quote_id: UUID
    model_id: str
    input_kind: Literal["voice", "text"]
    tokens_used: int

@dataclass  
class AiUsageRecorded:
    feature: Literal["voice", "scope_writer"]
    model_id: str
    tokens_used: int
    cost_minor: int
```

**`errors.py`** — Domain-specific errors:
```python
class TranscriptionError(Exception): ...
class ScopeExtractionError(Exception): ...
class PricebookMatchError(Exception): ...
class AudioTooLargeError(Exception): ...
class UnsupportedAudioFormatError(Exception): ...
```

**`protocols.py`** — Repository/adapter protocols:
```python
class TranscriptionService(Protocol):
    def transcribe(self, audio_bytes: bytes, mime_type: str) -> TranscriptionResult: ...

class ScopeExtractor(Protocol):
    def extract_scope(self, text: str, trade_hint: str | None = None) -> ExtractedScope: ...

class PricebookMatcher(Protocol):
    def match_items(self, tenant_id: UUID, tasks: list[ExtractedTask]) -> list[PricebookMatch]: ...

class QuoteCreator(Protocol):
    def create_quote(self, tenant_id: UUID, user_id: UUID | None, ...) -> QuoteCreatedResult: ...

class AiUsageRepository(Protocol):
    def record_usage(self, tenant_id: UUID, usage: AiUsageRecorded) -> None: ...
```

#### [NEW] `services/ai-service/app/application/`

**`voice_to_quote.py`** — Primary use case:
```python
class VoiceToQuoteUseCase:
    """Orchestrates: audio → transcribe → extract scope → match pricebook → create quote."""
    
    def __init__(
        self,
        transcription: TranscriptionService,
        extractor: ScopeExtractor,
        matcher: PricebookMatcher,
        quote_creator: QuoteCreator,
        usage_repo: AiUsageRepository,
    ): ...
    
    def execute(
        self,
        tenant_id: UUID,
        user_id: UUID | None,
        audio_bytes: bytes,
        mime_type: str,
        customer_id: UUID,
        property_id: UUID | None = None,
        trade_hint: str | None = None,
        tax_rate_bps: int = 0,
        default_markup_bps: int = 3000,  # 30% default contractor markup
    ) -> QuoteAssistantResult: ...
```

**`text_to_quote.py`** — Text input variant (skips transcription):
```python
class TextToQuoteUseCase:
    """Orchestrates: text → extract scope → match pricebook → create quote."""
    
    def execute(
        self,
        tenant_id: UUID,
        user_id: UUID | None,
        text: str,
        customer_id: UUID,
        property_id: UUID | None = None,
        trade_hint: str | None = None,
        tax_rate_bps: int = 0,
        default_markup_bps: int = 3000,
    ) -> QuoteAssistantResult: ...
```

**`scope_writer.py`** — Scope-of-work text generator (basic for T201):
```python
class ScopeWriterUseCase:
    """Generates professional scope-of-work text from structured scope data."""
    
    def execute(self, scope: ExtractedScope, tone: str = "professional") -> str: ...
```

#### [NEW] `services/ai-service/app/infrastructure/`

**`whisper_adapter.py`** — OpenAI Whisper STT adapter:
```python
class WhisperTranscriptionService:
    """Implements TranscriptionService using OpenAI Whisper API."""
    
    def __init__(self, api_key: str): ...
    
    def transcribe(self, audio_bytes: bytes, mime_type: str) -> TranscriptionResult:
        # Uses openai.audio.transcriptions.create()
        # Supports: wav, mp3, mp4, m4a, webm, ogg
        # Returns: text, language, duration
```

**`claude_adapter.py`** — Anthropic Claude scope extraction adapter:
```python
class ClaudeScopeExtractor:
    """Implements ScopeExtractor using Anthropic Claude API."""
    
    SYSTEM_PROMPT = """You are an expert trade estimator assistant...
    Given a job description from a contractor, extract:
    1. Trade category (electrical/plumbing/hvac/solar/roofing/...)
    2. Individual tasks with materials, labor, and equipment
    3. Quantities and units
    4. Any special notes or conditions
    
    Output as structured JSON matching the ExtractedScope schema..."""
    
    def extract_scope(self, text: str, trade_hint: str | None = None) -> ExtractedScope:
        # Uses anthropic.messages.create()
        # Model: claude-sonnet-4-20250514 (fast + cost-effective for extraction)
        # Temperature: 0.1 (deterministic extraction)
        # Structured output via tool_use or JSON mode
```

**`pricebook_client.py`** — HTTP client for pricebook-service:
```python
class HttpPricebookMatcher:
    """Implements PricebookMatcher by calling pricebook-service via HTTP."""
    
    def __init__(self, pricebook_service_url: str): ...
    
    def match_items(self, tenant_id: UUID, tasks: list[ExtractedTask]) -> list[PricebookMatch]:
        # GET /v1/pricebook?search=<item_name>&kind=<category>
        # Fuzzy matching: exact SKU > name contains > description contains
        # Returns best match per task, with confidence score
```

**`quote_client.py`** — HTTP client for quote-service:
```python
class HttpQuoteCreator:
    """Implements QuoteCreator by calling quote-service via HTTP."""
    
    def __init__(self, quote_service_url: str): ...
    
    def create_quote(
        self, tenant_id: UUID, user_id: UUID | None,
        customer_id: UUID, title: str, line_items: list[LineItemCreate],
        created_via: str = "voice", tax_rate_bps: int = 0,
    ) -> QuoteCreatedResult:
        # POST /v1/quotes with initial_line_items
        # Forwards x-tenant-id and x-user-id headers
```

**`db.py`** — Database session + RLS helper (standard pattern):
```python
# tenant_session(tenant_id) context manager
# SET LOCAL app.current_tenant = '<tenant_id>'
```

**`usage_repository.py`** — AI usage tracking persistence:
```python
class SqlAlchemyAiUsageRepository:
    """Persists AI usage records for billing/analytics."""
    # Writes to ai_usage_log table (new migration)
```

#### [NEW] `services/ai-service/app/interface/`

**`routes.py`** — FastAPI routes:

```python
router = APIRouter(prefix="/v1/ai", tags=["ai"])

@router.post("/voice-to-quote", response_model=VoiceToQuoteResponse, status_code=201)
async def voice_to_quote(
    audio: UploadFile,
    customer_id: UUID = Form(...),
    property_id: UUID | None = Form(None),
    trade_hint: str | None = Form(None),
    tax_rate_bps: int = Form(0),
    default_markup_bps: int = Form(3000),
    x_tenant_id: str | None = Header(None),
    x_user_id: str | None = Header(None),
) -> VoiceToQuoteResponse: ...

@router.post("/text-to-quote", response_model=TextToQuoteResponse, status_code=201)
async def text_to_quote(
    body: TextToQuoteRequest,
    x_tenant_id: str | None = Header(None),
    x_user_id: str | None = Header(None),
) -> TextToQuoteResponse: ...

@router.post("/scope-writer", response_model=ScopeWriterResponse)
async def write_scope(
    body: ScopeWriterRequest,
    x_tenant_id: str | None = Header(None),
) -> ScopeWriterResponse: ...

@router.get("/usage", response_model=list[AiUsageResponse])
async def get_usage(
    x_tenant_id: str | None = Header(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[AiUsageResponse]: ...
```

**`schemas.py`** — Pydantic DTOs:

```python
class TextToQuoteRequest(BaseModel):
    text: str = Field(..., min_length=10, max_length=10000)
    customer_id: UUID
    property_id: UUID | None = None
    trade_hint: str | None = None
    tax_rate_bps: int = Field(0, ge=0)
    default_markup_bps: int = Field(3000, ge=0)

class ExtractedTaskResponse(BaseModel):
    description: str
    category: str
    item_name: str
    quantity: float
    unit: str
    pricebook_item_id: UUID | None    # null if unmatched
    match_confidence: float | None

class VoiceToQuoteResponse(BaseModel):
    quote_id: UUID
    transcript: str
    language: str
    trade: str
    summary: str
    tasks: list[ExtractedTaskResponse]
    unmatched_count: int
    model_id: str
    tokens_used: int

class TextToQuoteResponse(BaseModel):
    quote_id: UUID
    trade: str
    summary: str
    tasks: list[ExtractedTaskResponse]
    unmatched_count: int
    model_id: str
    tokens_used: int

class ScopeWriterRequest(BaseModel):
    trade: str
    summary: str
    tasks: list[dict]             # Simplified task list
    tone: str = "professional"

class ScopeWriterResponse(BaseModel):
    scope_text: str
    model_id: str
    tokens_used: int

class AiUsageResponse(BaseModel):
    id: UUID
    feature: str
    model_id: str
    tokens_used: int
    cost_minor: int
    created_at: datetime
```

#### [NEW] `services/ai-service/app/config.py`

```python
class Settings(BaseSettings):
    # Service
    port: int = 8008
    
    # AI providers
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    whisper_model: str = "whisper-1"
    claude_model: str = "claude-sonnet-4-20250514"
    
    # Upstream services
    pricebook_service_url: str = "http://localhost:8003"
    quote_service_url: str = "http://localhost:8004"
    
    # Limits
    max_audio_size_bytes: int = 10 * 1024 * 1024  # 10 MB
    max_audio_duration_seconds: int = 300           # 5 min
    
    # Database
    database_url: str = "postgresql://tradequote:tradequote@localhost:5432/tradequote"
    
    # Feature flags
    feature_ai_voice: bool = True
```

---

### Component 2: Database Migration

#### [NEW] `infra/db/migrations/0009_ai_service.sql`

```sql
-- AI usage tracking table
CREATE TABLE ai_usage_log (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL REFERENCES tenant(id),
    feature     text NOT NULL,         -- 'voice', 'scope_writer', 'copilot', 'vision', 'ocr'
    model_id    text NOT NULL,         -- e.g., 'whisper-1', 'claude-sonnet-4-20250514'
    input_kind  text NOT NULL,         -- 'voice', 'text', 'image'
    tokens_used integer NOT NULL DEFAULT 0,
    cost_minor  bigint NOT NULL DEFAULT 0,  -- cost in cents
    metadata    jsonb,                 -- additional context (quote_id, duration, etc.)
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- RLS
ALTER TABLE ai_usage_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY ai_usage_log_tenant_isolation ON ai_usage_log
    USING (tenant_id = app_current_tenant());
CREATE POLICY ai_usage_log_insert ON ai_usage_log
    FOR INSERT WITH CHECK (tenant_id = app_current_tenant());

-- Indexes
CREATE INDEX idx_ai_usage_log_tenant ON ai_usage_log(tenant_id);
CREATE INDEX idx_ai_usage_log_feature ON ai_usage_log(tenant_id, feature);
CREATE INDEX idx_ai_usage_log_created ON ai_usage_log(tenant_id, created_at);
```

---

### Component 3: API Gateway Wiring

#### [MODIFY] [config.ts](file:///d:/TradeQuote%20AI/apps/api-gateway/src/config.ts)

Add `AI_SERVICE_URL` to the env schema and Config type:
```diff
  ESIGN_SERVICE_URL: z.string().url().default("http://localhost:8007"),
+ AI_SERVICE_URL: z.string().url().default("http://localhost:8008"),
```

#### [MODIFY] [server.ts](file:///d:/TradeQuote%20AI/apps/api-gateway/src/server.ts)

Register the AI service proxy route:
```diff
  registerServiceProxy(app, { prefix: "/v1/sign", upstream: cfg.esignServiceUrl });
+ registerServiceProxy(app, { prefix: "/v1/ai", upstream: cfg.aiServiceUrl });
```

---

### Component 4: Domain Events Extension

#### [MODIFY] [events.ts](file:///d:/TradeQuote%20AI/packages/types/src/events.ts)

No changes needed — `ai.quote.drafted` and `ai.usage.recorded` events with their payload types are **already defined** in the canonical registry. The AI service will produce events matching these existing types.

---

### Component 5: LLM Prompt Engineering

#### [NEW] `services/ai-service/app/infrastructure/prompts/`

**`scope_extraction.py`** — The core prompt for converting free-text to structured scope:

```python
SCOPE_EXTRACTION_SYSTEM = """You are an expert trade estimator assistant for {trade} contractors.

Given a job description (transcribed from voice or typed), extract structured information.

RULES:
1. Identify the primary trade: electrical, plumbing, hvac, solar, roofing, flooring, 
   landscaping, painting, cleaning, general
2. Break down into individual tasks — each task is one billable line item
3. For each task, determine:
   - category: "material" (physical item), "labor" (work hours), "equipment" (tools/machines)
   - item_name: the specific item or service (match common trade terminology)
   - quantity: numeric amount (default 1 if unclear)
   - unit: "each", "ft", "lf" (linear foot), "sqft", "hr", "day", "lot"
4. Include labor for installation/removal when materials are mentioned
5. Include standard consumables (wire, fittings, connectors) when applicable
6. Flag any safety/permit requirements in notes

OUTPUT FORMAT: JSON matching this schema exactly:
{
  "trade": "electrical",
  "summary": "Panel upgrade and LED lighting installation",
  "tasks": [
    {
      "description": "200A electrical panel",
      "category": "material",
      "item_name": "200A main breaker panel",
      "quantity": 1,
      "unit": "each"
    },
    {
      "description": "Panel installation labor",
      "category": "labor", 
      "item_name": "Panel installation",
      "quantity": 4,
      "unit": "hr"
    }
  ],
  "notes": "Permit required for panel upgrade. Verify existing wiring capacity."
}"""
```

**`scope_writer.py`** — Prompt for generating professional scope-of-work text:

```python
SCOPE_WRITER_SYSTEM = """You are a professional trade proposal writer. 
Given a structured scope, generate a clear, professional scope-of-work paragraph 
that a homeowner would understand. Use {tone} language.

Include: what work will be done, key materials, and any important notes.
Do NOT include pricing. Keep it concise (2-4 paragraphs max)."""
```

---

### Component 6: Test Suite

#### [NEW] `services/ai-service/tests/`

**Test Structure:**
```
tests/
├── conftest.py              # Shared fixtures, fake adapters
├── test_voice_to_quote.py   # VoiceToQuoteUseCase with fakes
├── test_text_to_quote.py    # TextToQuoteUseCase with fakes
├── test_scope_writer.py     # ScopeWriterUseCase with fakes
├── test_scope_extraction.py # Claude prompt output parsing
├── test_pricebook_matching.py # PricebookMatcher logic
├── test_routes.py           # FastAPI route integration tests
├── test_schemas.py          # DTO validation
├── test_tenant_isolation.py # Multi-tenancy enforcement
└── test_usage_tracking.py   # AI usage logging
```

**Testing Strategy:**
- **Domain logic** tested against **in-memory fakes** (no external APIs needed)
- `FakeTranscriptionService` — returns canned transcripts
- `FakeScopeExtractor` — returns pre-built `ExtractedScope` objects
- `FakePricebookMatcher` — returns mock pricebook matches
- `FakeQuoteCreator` — validates input, returns mock quote IDs
- `FakeAiUsageRepository` — in-memory list
- **No live API calls in CI** — external services are fully stubbed
- Target: **≥80% coverage** on `domain/` and `application/` layers

**Key Test Cases:**
1. Voice-to-quote happy path (audio → transcript → scope → matches → quote)
2. Text-to-quote happy path (text → scope → matches → quote)
3. Audio too large (>10MB) → 413 error
4. Unsupported audio format → 400 error
5. Empty/inaudible transcript → graceful error
6. Partial pricebook match (some items matched, some not)
7. Zero pricebook matches → still creates quote with custom line items
8. Tenant isolation (tenant A can't see tenant B's usage)
9. Missing `x-tenant-id` → 401
10. Scope extraction from different trades (electrical, plumbing, HVAC)
11. Money values are always integer minor units (never floats)
12. Domain events emitted correctly (`ai.quote.drafted`, `ai.usage.recorded`)

---

## File Inventory Summary

| Action     | File                                               | Component          |
|------------|----------------------------------------------------|--------------------|
| **[NEW]**  | `services/ai-service/pyproject.toml`               | AI Service         |
| **[NEW]**  | `services/ai-service/main.py`                      | AI Service         |
| **[NEW]**  | `services/ai-service/app/__init__.py`              | AI Service         |
| **[NEW]**  | `services/ai-service/app/config.py`                | AI Service         |
| **[NEW]**  | `services/ai-service/app/domain/__init__.py`       | AI Service         |
| **[NEW]**  | `services/ai-service/app/domain/models.py`         | AI Service         |
| **[NEW]**  | `services/ai-service/app/domain/events.py`         | AI Service         |
| **[NEW]**  | `services/ai-service/app/domain/errors.py`         | AI Service         |
| **[NEW]**  | `services/ai-service/app/domain/protocols.py`      | AI Service         |
| **[NEW]**  | `services/ai-service/app/application/__init__.py`  | AI Service         |
| **[NEW]**  | `services/ai-service/app/application/voice_to_quote.py` | AI Service    |
| **[NEW]**  | `services/ai-service/app/application/text_to_quote.py`  | AI Service    |
| **[NEW]**  | `services/ai-service/app/application/scope_writer.py`    | AI Service    |
| **[NEW]**  | `services/ai-service/app/infrastructure/__init__.py`     | AI Service    |
| **[NEW]**  | `services/ai-service/app/infrastructure/db.py`           | AI Service    |
| **[NEW]**  | `services/ai-service/app/infrastructure/whisper_adapter.py` | AI Service |
| **[NEW]**  | `services/ai-service/app/infrastructure/claude_adapter.py`  | AI Service |
| **[NEW]**  | `services/ai-service/app/infrastructure/pricebook_client.py`| AI Service |
| **[NEW]**  | `services/ai-service/app/infrastructure/quote_client.py`    | AI Service |
| **[NEW]**  | `services/ai-service/app/infrastructure/usage_repository.py`| AI Service |
| **[NEW]**  | `services/ai-service/app/infrastructure/prompts/`           | AI Service |
| **[NEW]**  | `services/ai-service/app/infrastructure/prompts/scope_extraction.py` | AI Service |
| **[NEW]**  | `services/ai-service/app/infrastructure/prompts/scope_writer.py`     | AI Service |
| **[NEW]**  | `services/ai-service/app/interface/__init__.py`    | AI Service         |
| **[NEW]**  | `services/ai-service/app/interface/routes.py`      | AI Service         |
| **[NEW]**  | `services/ai-service/app/interface/schemas.py`     | AI Service         |
| **[NEW]**  | `services/ai-service/tests/conftest.py`            | Tests              |
| **[NEW]**  | `services/ai-service/tests/test_voice_to_quote.py` | Tests             |
| **[NEW]**  | `services/ai-service/tests/test_text_to_quote.py`  | Tests             |
| **[NEW]**  | `services/ai-service/tests/test_scope_writer.py`   | Tests             |
| **[NEW]**  | `services/ai-service/tests/test_scope_extraction.py` | Tests           |
| **[NEW]**  | `services/ai-service/tests/test_pricebook_matching.py` | Tests         |
| **[NEW]**  | `services/ai-service/tests/test_routes.py`         | Tests              |
| **[NEW]**  | `services/ai-service/tests/test_schemas.py`        | Tests              |
| **[NEW]**  | `services/ai-service/tests/test_tenant_isolation.py` | Tests            |
| **[NEW]**  | `services/ai-service/tests/test_usage_tracking.py` | Tests              |
| **[NEW]**  | `infra/db/migrations/0009_ai_service.sql`          | Database           |
| **[MODIFY]** | `apps/api-gateway/src/config.ts`                 | Gateway            |
| **[MODIFY]** | `apps/api-gateway/src/server.ts`                 | Gateway            |
| **[NEW]**  | `docs/modules/M15-ai-quote-assistant.md`           | Documentation      |
| **[NEW]**  | `docs/modules/M15-ai-quote-assistant-plan.md`      | Documentation      |

---

## API Contract (OpenAPI Summary)

### `POST /v1/ai/voice-to-quote`
- **Content-Type:** `multipart/form-data`
- **Body:** `audio` (file, required), `customer_id` (UUID), `property_id` (UUID, opt), `trade_hint` (string, opt), `tax_rate_bps` (int), `default_markup_bps` (int)
- **Response:** `201 Created` → `VoiceToQuoteResponse`
- **Errors:** `400` (bad format), `401` (no tenant), `413` (too large), `422` (validation), `502` (upstream AI/service failure)

### `POST /v1/ai/text-to-quote`
- **Content-Type:** `application/json`
- **Body:** `TextToQuoteRequest`
- **Response:** `201 Created` → `TextToQuoteResponse`

### `POST /v1/ai/scope-writer`
- **Content-Type:** `application/json`
- **Body:** `ScopeWriterRequest`
- **Response:** `200 OK` → `ScopeWriterResponse`

### `GET /v1/ai/usage`
- **Response:** `200 OK` → `list[AiUsageResponse]`

---

## Idempotency & Error Handling

- **Idempotency:** All AI-billing endpoints require an `x-idempotency-key` header (per conventions §2 and architecture doc). The AI service deduplicates on this key + tenant_id in the `ai_usage_log` table.
- **Retries:** Upstream calls (Whisper, Claude) use exponential backoff (1s, 2s, 4s, max 3 retries).
- **Circuit Breaker:** If Whisper or Claude are down, return `503 Service Unavailable` with a human-readable message rather than hanging.
- **Cost Control:** Log every API call's token count and estimated cost to `ai_usage_log`. Add a configurable per-tenant daily spending cap (env var, enforced at the use-case layer).

---

## Verification Plan

### Automated Tests

```bash
# Run from services/ai-service/
cd services/ai-service
uv sync
uv run ruff check app tests
uv run mypy app
uv run pytest tests/ -v --tb=short

# Run conventions guard
cd ../../
python scripts/check_conventions.py

# Run gateway tests (to verify new /v1/ai proxy)
cd apps/api-gateway
pnpm test
```

### Manual Verification

1. Start the AI service: `cd services/ai-service && uv run uvicorn main:app --port 8008`
2. Test text-to-quote via curl:
   ```bash
   curl -X POST http://localhost:8008/v1/ai/text-to-quote \
     -H "Content-Type: application/json" \
     -H "x-tenant-id: 00000000-0000-0000-0000-000000000001" \
     -d '{"text": "Install 12 LED recessed lights and replace the electrical panel with a 200A", "customer_id": "00000000-0000-0000-0000-000000000099"}'
   ```
3. Verify the response includes structured scope extraction and a created quote ID
4. Verify `ai_usage_log` has a row for the request

### Quality Gates Checklist

- [ ] ✅ Product — Voice/text→quote workflow complete
- [ ] ✅ Architecture — Clean Architecture, Protocol-based DI, bounded context isolation
- [ ] ✅ Security — No JWT decode, header-trust only, tenant isolation via RLS
- [ ] ✅ Performance — <5s for text-to-quote, <15s for voice-to-quote (incl. transcription)
- [ ] ✅ API — OpenAPI contract, proper status codes, idempotency
- [ ] ✅ Database — Migration with RLS, proper indexes
- [ ] ✅ AI — Prompt engineering, structured output, cost tracking
- [ ] ✅ Code Review — ruff/mypy clean, conventions guard passes
- [ ] ✅ QA — ≥80% test coverage on domain/application layers
