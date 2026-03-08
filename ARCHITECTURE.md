# Layer10 Memory Graph: Detailed Architecture & Features

This document describes the design, components, and features of the organizational memory system in detail. For a short overview and reproduction steps, see [README.md](README.md).

---

# System Architecture

Pipeline overview:

```
Raw Artifacts (GitHub Issues + Comments)
        ↓
Stratified Extraction
        ↓
payloads.json
        ↓
Thread-Level Extraction
        ↓
thread_payloads.json
        ↓
Deduplication + Canonicalization
        ↓
memory_graph.json
        ↓
Retrieval Context Packs
        ↓
Interactive Visualization (Streamlit)
```

---

# Processing Stages

## 1. Ingestion

GitHub artifacts (issues and comments) are retrieved using the GitHub API.

Each artifact is converted into a normalized internal structure:

| Field       | Description    |
|------------|----------------|
| `id`       | Artifact ID    |
| `author`   | Author handle  |
| `content`  | Text content   |
| `timestamp`| When created (stored as `created_at` in the schema) |

These artifacts form the raw dataset used for extraction.

---

## 2. Stratified Extraction

The system performs **two extraction passes**.

### Artifact-Level Extraction

Each artifact is processed independently by the LLM to extract:

- **entities**
- **atomic claims**
- **supporting evidence**

**Output:** `payloads.json`

This stage focuses on **local facts** expressed in individual messages.

---

### Thread-Level Extraction

Full issue threads are then analyzed to extract:

- architectural discussions
- design decisions
- long-range dependencies

**Output:** `thread_payloads.json`

This stage captures **cross-message reasoning** that artifact-level extraction may miss.

---

## 3. Deduplication and Canonicalization

The deduplication stage constructs a **canonical memory graph**. It implements **entity canonicalization**, **claim deduplication** (with evidence aggregation), **conflicts and revisions**, and **audit logging** for reversibility.

---

### Evidence deduplication

When merging claims that have the same subject, predicate, and object, evidence from duplicates is aggregated into a **support set**. Duplicate evidence (same `artifact_id` and `excerpt`) is not added twice to the same claim. Optionally, a content-hash–based evidence dedup could be added to collapse identical excerpts across artifacts.

---

### Entity canonicalization

Handles and aliases are normalized:

- `@Boostrix` → `boostrix`
- `person_BaseInfinity` → `baseinfinity`

Entities representing the same actor are merged into a single canonical entity.  
Aliases are preserved for search.

---

### Claim deduplication

Claims asserting the same fact are merged.

**Matching key:** `subject + predicate + object`

Duplicate claims contribute additional evidence.

---

### Support Sets

Multiple artifacts supporting the same claim are aggregated into a **support set**.

**Example:** Instead of storing multiple duplicate claims:

- Boostrix suggests_change memory config changes  
- Boostrix suggests_change memory config changes  
- Boostrix suggests_change memory config changes  

The system stores a **single canonical claim** with multiple evidence sources.

This produces **consensus-weighted organizational knowledge**.

---

### Temporal Revision Detection

The system supports evolving knowledge.

Claims contain:

- `valid_from`
- `valid_to`

If a later claim contradicts an earlier one (same subject and predicate, different object), the existing claim’s `valid_to` is set to the new claim’s `valid_from`.

**Example** (from the graph):

| Property    | Value                    |
|------------|---------------------------|
| `predicate`| assigned_to              |
| `valid_from` | 2023-05-11T18:29:38Z   |
| `valid_to`   | 2023-05-13T22:50:56Z   |

This allows queries for both **current facts** and **historical decisions**. Future work would add automatic contradiction detection.

---

### Audit Logging

All entity and claim merges are recorded.

Example audit entry:

```json
{
  "timestamp": "...",
  "source": "@Boostrix",
  "target": "boostrix"
}
```

This ensures the system remains **auditable**. Reversibility (e.g. undoing merges using the audit log) is planned as future work.

---

# Memory Graph Schema

The system uses a **reified claim model**.

Instead of storing facts as direct edges, each fact becomes a **Claim node**.  
This allows attaching metadata such as:

- evidence
- confidence
- temporal validity
- provenance

---

## Entity Nodes

Entities represent stable objects in the system.

**Examples:** Person, Repository, Issue, Component, Tool, File

Example:

```json
{
  "id": "boostrix",
  "type": "Person",
  "name": "Boostrix"
}
```

---

## Claim Nodes

Facts extracted from artifacts.

**Structure:** `(subject_entity_id, predicate, object_entity_id)`

**Example:** Boostrix → suggests_change → memory config changes

Claims store:

- `predicate`
- `confidence`
- `valid_from`
- `valid_to`
- `evidence[]`

---

## Evidence

Every claim includes at least one evidence snippet.

**Evidence fields:**

| Field         | Description        |
|---------------|--------------------|
| `artifact_id` | Source artifact    |
| `excerpt`     | Quoted text        |
| `char_start`  | Start offset       |
| `char_end`    | End offset         |

**Example:**

- `artifact_id`: comment_1563628611  
- `excerpt`: "@Boostrix sounds good, I fixed the conflicts…"

This ensures every stored fact remains **verifiable**.

---

## Ontology and Contract

The extraction system follows a strict schema contract.

**Entities must include:**

- `id`
- `type`
- `name`
- `aliases`

**Claims must include:**

- `subject_entity_id`
- `predicate`
- `object_entity_id`
- `confidence`
- `evidence`

**Extraction rules:**

- Artifacts cannot become entities (artifact identifiers are never promoted to entities).
- Claims must reference valid entities (unknown entities are discarded).
- Every claim must contain at least one evidence excerpt.

This contract ensures high-precision memory construction and is enforced by the pipeline (see Extraction Quality Controls below).

---

### Permissions

In a production deployment, **memory retrieval is constrained by access to underlying sources**. The graph stores claims and evidence with `artifact_id` pointing to the source. At retrieval time, the service obtains the set of artifact IDs the requesting user is allowed to see (e.g. via Slack/Jira/email ACLs) and **filters** the result so that only claims (or evidence) whose `artifact_id` is in that set are returned. The graph itself remains global; the **retrieval layer** applies a per-request visibility filter so that users only see memory grounded in sources they can access.

---

### Observability

The design supports **observability** by (1) **provenance**—every claim and evidence item carries `artifact_id` and excerpt so that what is served is traceable to the source; (2) **audit log**—entity and claim merges are recorded with timestamp and merge key; (3) **retrieval logging**—in production, logging which claims and evidence are returned per query supports debugging, evaluation, and compliance. Metrics (e.g. graph size, confidence distribution, retrieval latency) can be exposed for monitoring and regression testing.

---

# Extraction Quality Controls

To prevent hallucinated knowledge:

### Artifact Filtering

Artifact identifiers (issue IDs, comment IDs) are **never promoted to entities**.

---

### Entity Validation

Claims referencing unknown entities are automatically discarded.

---

### Two-Pass Entity Collection

The system first collects **all entities** before processing claims.

This prevents dropping claims referencing entities discovered later in the dataset.

---

### Schema Enforcement

Extraction outputs must match the schema before entering the graph pipeline.

This guarantees **structural integrity of the memory graph**.

---

# Retrieval System

The system exposes a **RetrievalService** that produces **Context Packs**.

A context pack contains:

- **entities**
- **claims**
- **evidence**
- **human-readable statements**

**Example output:**

- **Statement:** Boostrix suggests_change memory config changes  
- **Evidence:** Artifact: comment_1563628611 — "@Boostrix sounds good, I fixed the conflicts…"

This allows downstream agents to reason over **grounded facts instead of raw text**.

---

# Hybrid Retrieval

Retrieval uses a hybrid strategy:

### Entity-first retrieval

Direct entity lookup returns all claims referencing that entity.

---

### Keyword search

Predicate-aware matching using a predicate synonym map.

**Examples:**

- `suggest` → `suggests_change`
- `fix` → `fixes_issue`
- `assign` → `assigned_to`

---

### Embedding search

Semantic retrieval uses **sentence-transformers/all-MiniLM-L6-v2** to retrieve conceptually related claims.

---

### Semantic Fallback

If an entity exists but has **no direct claims**, the system falls back to semantic retrieval while informing the user.

This avoids returning empty results while preserving transparency.

---

# Visualization

Two visualization modes are provided.

## Streamlit Memory Explorer

Run:

```bash
streamlit run src/retrieval/app.py
```

**Features:**

- natural language query interface
- entity lookup
- evidence browsing
- interactive knowledge graph

The graph view shows relationships between contributors, repositories, and features. Screenshots and a video of the query search and knowledge graph are in the `visualization/` folder (e.g. `query_search.png`, `knowledge_graph.mov`).

**Using the UI:**

- Use the **Search** tab to ask questions (e.g. “Who suggested configuration changes?”) or look up entities (e.g. “@BaseInfinity”).
- Use the **Knowledge Graph** tab to see an interactive visualization of the retrieved context.
- Review the **Fact Stream** for grounded evidence excerpts associated with each decision.

---

## Neo4j Graph Exploration

Start Neo4j:

```bash
docker run --name layer10-neo4j -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password -d neo4j:5
```

- **Browser UI:** http://localhost:7474  
- **Bolt:** bolt://localhost:7687  

Then:

1. Open http://localhost:7474 and log in (e.g. username `neo4j`, password `password`, or your `.env` credentials).
2. Run this Cypher query to visualize the graph:

```cypher
MATCH (n)
OPTIONAL MATCH (n)-[r]->(m)
RETURN n, r, m
```

3. Use the **Graph** tab to drag nodes, zoom into clusters, and click nodes or edges to inspect properties (e.g. claim statements, confidence scores, evidence excerpts).

---

# System Metrics

**Dataset processed:** 45 GitHub artifacts

**Graph size:**

- 273 canonical entities  
- 92 unified claims  
- 70+ evidence excerpts  

Every claim in the graph is **directly grounded in artifact evidence**.

---

# Example Query

**Query:** Who suggested configuration changes?

**Result:**

- **Statement:** Boostrix suggests_change memory config changes  
- **Evidence:** Artifact: comment_1563628611 — "@Boostrix sounds good, I fixed the conflicts…"

---

# Layer10 Production Adaptation

This section expands on how the prototype would be adapted for Layer10’s target environment: **email**, **Slack/Teams**, **docs**, and **structured systems** like **Jira/Linear**, based on the extraction, dedup, memory graph, and retrieval design already described above.

---

## Additional sources and ontology extension

The current corpus is **GitHub issues and comments**. For Layer10 we would add ingestors for email, Slack/Teams, internal docs, and Jira/Linear. The **ontology** would extend with entity types (e.g. `Channel`, `Thread`, `Project`, `Sprint`, `Document`, `Ticket`) and predicates (e.g. `mentioned_in`, `replied_to`, `blocked_by`, `owned_by`) while keeping the same extraction contract: required fields, evidence per claim, and valid-entity references. Artifact types in the schema already include `Email`, `SlackMessage`; we would add `JiraIssue`, `LinearIssue`, `Doc`, etc., so every evidence pointer has a clear source kind.

---

## Unstructured and structured fusion

**Connecting chat/email to tickets and components:** Ingest unstructured sources (Slack, email, docs) and structured sources (Jira, Linear) into the same artifact model. Use the same **entity canonicalization** and **claim dedup** so that e.g. “#PROJ-123” in Slack and the Jira issue PROJ-123 resolve to the same Issue entity. Claims then link discussions to work items: “Person X mentioned Issue Y in Slack” (evidence: Slack message), “Issue Y assigned_to Person X” (evidence: Jira). Thread-level extraction can emit claims that tie a Slack thread to a Jira ticket or doc, so chat and email are explicitly connected to tickets, projects, and components in the graph.

---

## Long-term memory and drift

**Durable vs ephemeral:** Only ingested, persisted artifacts feed the graph; live buffers or unsaved drafts stay ephemeral. **Preventing drift:** (1) **Temporal validity** (`valid_from` / `valid_to`) already marks superseded facts. (2) **Golden tier:** Treat claims with multiple independent sources as higher trust; optionally require ≥2 sources before promoting to “durable” memory. (3) **Decay or review:** Optional confidence decay over time or periodic human review of high-impact claims so stale or disputed facts can be demoted.

---

## Grounding, safety, and permissions

**Provenance and citations:** Every claim already carries evidence (artifact id, excerpt, offsets); retrieval returns this for citation. For Layer10 we would add resolvable links (Slack permalink, Jira URL, doc link) per evidence. **Deletions/redactions:** When a source is deleted or redacted, mark affected evidence as stale or soft-delete claims with no reachable source; retrieval filters out stale evidence by default; auditors can still see what was there. **Permissions** (see Memory Graph Schema): retrieval is filtered by access to underlying sources—only return claims whose evidence’s `artifact_id` is in the set of artifacts the user can access (e.g. from Slack/Jira/email ACLs).

---

## Operational reality

- **Streaming ingestion:** Move from batch to **event-driven updates via Change Data Capture** from Slack/Jira/email so the graph updates incrementally as new messages or tickets arrive.
- **Scaling and cost:** Re-extract only when artifacts change; use smaller models for simple extraction and larger ones for thread-level reasoning; cache embeddings. Dedup and retrieval can run incrementally; retrieval can be scaled with caching or a separate vector index.
- **Incremental updates:** Ingest only new or updated artifacts, run extraction, and merge into the existing graph (the dedup service already supports merge-into-canonical). Full re-runs only when ontology or dedup rules change.
- **Evaluation and regression:** Maintain a golden set of artifacts with hand-labeled entities/claims; run extraction and compare precision/recall. After prompt or model changes, re-run on the golden set and alert on regressions. Optionally snapshot graph metrics (entity/claim counts, confidence distribution) in CI or nightly jobs.

---

## Cross-source linking and reversibility

**Cross-source linking:** Merge claims from Slack, Jira, email, and docs into one graph using the same entity canonicalization and claim dedup (subject + predicate + object). Evidence from different sources attaches to the same canonical claim; the retrieval layer still enforces per-source permissions. **Reversibility:** The pipeline already records an **audit log** (entity and claim merges with timestamp and merge key). Future work would add **undo merges** (e.g. re-split entities or claims using the log) and expose **why a merge happened** in the UI or API for full auditability.

---

# Reproducibility (Summary)

See [README.md](README.md) for:

- **Setup:** `pip install -r requirements.txt`, `.env` configuration  
- **Run pipeline:** extraction → dedup → neo4j ingest → generate samples  
- **Launch UI:** `streamlit run src/retrieval/app.py`  
- **Outputs:** `data/processed/memory_graph.json`, `outputs/sample_context_packs.json`, etc.

---

# Assessment Context

Built for the **Layer10 Take-Home Assessment**.

This prototype demonstrates how organizational knowledge can be:

- extracted from collaboration artifacts  
- structured into a canonical graph  
- deduplicated and versioned  
- retrieved with evidence grounding  
- visualized interactively  

while maintaining **complete traceability to original artifacts**.
