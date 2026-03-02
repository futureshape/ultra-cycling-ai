# Server & Agent Architecture

## Overview

The ultra-cycling-ai server is a Python/FastAPI backend that acts as a real-time AI coaching assistant for ultra-endurance cycling. It receives route data and periodic ride telemetry ("ticks"), runs an OpenAI-powered agent with tool-calling capabilities, and returns calm, structured advice focused on ride completion rather than race performance.

```
┌──────────────┐         ┌─────────────────────────────────────────────┐
│  Karoo App   │  HTTP   │              FastAPI Backend                │
│  (or replay  │────────▶│                                             │
│   script)    │◀────────│  ┌───────┐  ┌───────┐  ┌───────┐          │
└──────────────┘         │  │  API  │─▶│ Agent │─▶│  LLM  │          │
                         │  │Routes │  │Runner │  │Client │          │
                         │  └───┬───┘  └───┬───┘  └───────┘          │
                         │      │          │                           │
                         │      ▼          ▼                           │
                         │  ┌───────┐  ┌───────────────┐              │
                         │  │SQLite │  │  Tool Registry │              │
                         │  │  DB   │  │  (4 tools)     │              │
                         │  └───────┘  └───────────────┘              │
                         │      ▲          │                           │
                         │      │          ▼                           │
                         │  ┌───────────────────┐                     │
                         │  │  Memory Layer      │                     │
                         │  │  (RideState +      │                     │
                         │  │   IntakeLedger)    │                     │
                         │  └───────────────────┘                     │
                         └─────────────────────────────────────────────┘
```

## Request Flow

### 1. Route Bootstrap (`POST /route/bootstrap`)

Before a ride begins, the route geometry is uploaded once:

1. Client sends GPX data or GeoJSON.
2. Server stores the route in the `routes` table with an assigned `route_id`.
3. Returns the `route_id` for use in subsequent tick calls.

### 2. Tick Processing (`POST /ride/{ride_id}/tick`)

During a ride, the client sends compact tick payloads every 2–5 minutes:

1. **Persist** — The tick payload is stored in the `ticks` table. Any inline intake events are written to `intake_events`.
2. **Update memory** — `RideState` (sliding window of recent ticks, running totals) and `IntakeLedger` (fuel/hydration log) are updated in-memory.
3. **Cooldown check** — If every advice category is still in cooldown, the agent short-circuits and returns `{"no_advice": true}` without calling the LLM.
4. **Context building** — A compact user message is assembled from: current position, recent averages, ride summary, intake summary, and which categories are on cooldown.
5. **LLM tool-call loop** — The context is sent to OpenAI along with the system prompt and tool definitions. If the model requests a tool call, the tool is dispatched and its result fed back. This loops up to 3 rounds.
6. **Response parsing** — The LLM's final JSON response is parsed into an `AdviceResponse` (or `no_advice`). If advice is given, it's persisted to `advice_log` and the category cooldown is updated.

### 3. Intake Logging (`POST /ride/{ride_id}/intake`)

A convenience endpoint for logging eat/drink events outside the normal tick cycle. Events are written directly to `intake_events` and picked up by the `IntakeLedger` on the next tick.

## Package Structure

```
src/ultra_cycling_ai/
├── main.py              # FastAPI app, lifespan (DB init, registry setup)
├── config.py            # Pydantic Settings from .env
│
├── api/
│   ├── schemas.py       # Request/response Pydantic models
│   └── routes.py        # Endpoint handlers
│
├── agent/
│   ├── runner.py        # Core agent loop: tick → context → LLM → advice
│   ├── system_prompt.py # LLM system prompt (personality, rules, JSON schema)
│   ├── context.py       # Builds the compact user message for the LLM
│   └── cooldown.py      # Per-category cooldown tracker
│
├── tools/
│   ├── registry.py      # Tool base class, ToolRegistry, factory
│   ├── route_analysis.py  # Climb/segment lookahead (placeholder)
│   ├── poi_search.py      # Nearby POI search (placeholder)
│   ├── weather.py         # Weather forecast (placeholder)
│   └── daylight.py        # Sunrise/sunset (placeholder)
│
├── memory/
│   ├── ride_state.py    # Sliding window of ticks + running totals
│   └── intake_ledger.py # Fuel/hydration event log + hourly summaries
│
├── llm/
│   └── openai_client.py # Async OpenAI wrapper with retries
│
└── db/
    ├── engine.py        # SQLite async connection + schema migrations
    └── models.py        # CRUD helpers (raw SQL via aiosqlite)
```

## Agent Design

### System Prompt

The agent is instructed to behave as an ultra-endurance cycling coach with five ordered priorities:

1. **Sustainable pacing** — prevent going too hard too early
2. **Fuel and hydration** — remind the rider to eat and drink regularly
3. **Fatigue prevention** — watch for declining performance
4. **Risk reduction** — flag weather, nightfall, terrain hazards
5. **Mental stability** — calm encouragement during low points

The prompt enforces 2–3 sentence maximum advice, JSON-only output, and a `{"no_advice": true}` response when no intervention is needed.

### Tool-Calling Loop

The agent uses OpenAI function-calling to invoke tools before making a decision. The loop works as follows:

```
Send messages + tool definitions to OpenAI
  ↓
Model returns tool_call?
  ├── YES → Dispatch tool, append result, loop (max 3 rounds)
  └── NO  → Parse final JSON → AdviceResponse or no_advice
```

Tools available (all currently return mock data):

| Tool | Purpose | Key Inputs |
|------|---------|------------|
| `route_analysis` | Climb/gradient lookahead | `route_id`, `current_distance_km`, `lookahead_km` |
| `poi_search` | Find nearby food/water/shelter | `lat`, `lon`, `radius_km`, `categories` |
| `weather_forecast` | Temperature, wind, precipitation | `lat`, `lon`, `hours_ahead` |
| `daylight` | Sunrise/sunset, hours remaining | `lat`, `lon`, `date` |

### Cooldown System

Each advice category (`fuel`, `pacing`, `fatigue`, `terrain`, `environment`, `morale`) has an independent cooldown timer. When advice is given, the LLM specifies a `cooldown_minutes` value (default 15). The backend suppresses that category until the cooldown expires. If all categories are in cooldown, the LLM is not called at all — saving tokens and latency.

### Memory Layer

**RideState** (`memory/ride_state.py`):
- Holds the last 10 ticks in a sliding `deque`
- Tracks running totals: elapsed time, distance, elevation gain
- Exposes a `summary()` dict injected into LLM context

**IntakeLedger** (`memory/intake_ledger.py`):
- Stores all eat/drink events with timestamps
- Provides queries: `eat_count_last(60)`, `drink_count_last(60)`, `time_since_last_eat()`, `time_since_last_drink()`
- Exposes a `summary()` dict injected into LLM context

Both are in-memory, keyed by `ride_id`. State is rebuilt from the DB if needed (not yet implemented).

## Data Model (SQLite)

| Table | Key Columns | Purpose |
|-------|-------------|---------|
| `routes` | `route_id`, `gpx_geojson`, `climb_segments` | Stored route geometry |
| `rides` | `ride_id`, `route_id`, `status` | Active ride sessions |
| `ticks` | `ride_id`, `timestamp`, `payload` (JSON) | Raw tick history |
| `intake_events` | `ride_id`, `event_type`, `detail`, `timestamp` | Eat/drink log |
| `advice_log` | `ride_id`, `category`, `priority`, `message`, `cooldown_minutes` | Advice audit trail |

## Advice Response Contract

Every tick response is one of:

```json
{
  "advice": {
    "priority": "low | medium | high",
    "category": "fuel | pacing | fatigue | terrain | environment | morale",
    "message": "2–3 sentence guidance",
    "cooldown_minutes": 15
  },
  "no_advice": false
}
```

or:

```json
{
  "advice": null,
  "no_advice": true
}
```

## Testing Without Karoo

Two CLI scripts substitute for the Karoo device:

- **`scripts/import_gpx.py`** — Parses a GPX file (tracks + waypoints) into GeoJSON and POSTs to `/route/bootstrap`.
- **`scripts/replay_fit.py`** — Parses a FIT activity file, groups records into tick-sized windows, and POSTs them to `/ride/{ride_id}/tick` at configurable playback speed (e.g. 10x).

Usage:
```bash
python scripts/import_gpx.py route.gpx --route-id my-route
python scripts/replay_fit.py ride.fit --route-id my-route --speed-multiplier 10
```

## Configuration

All config via environment variables (or `.env` file):

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENAI_API_KEY` | (required) | OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o` | Model to use for chat completions |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/ride.db` | SQLite database path |
| `TICK_INTERVAL_SECONDS` | `120` | Expected tick interval |
| `DEFAULT_COOLDOWN_MINUTES` | `15` | Default advice cooldown per category |

## Future Work

- **Implement real tools** — Replace placeholder mock data with actual route geometry analysis, Overpass/Google Places POI search, Open-Meteo weather API, and astral daylight calculations.
- **Rebuild memory from DB** — On server restart, reconstruct `RideState` and `IntakeLedger` from persisted ticks and intake events.
- **Multi-day fatigue scoring** — Track cumulative fatigue across sleep breaks.
- **Heat stress modelling** — Combine weather data with rider effort to flag heat risk.
- **Karoo extension** — Build the Android app in the `karoo/` directory.
