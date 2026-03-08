Layer10 Memory Graph: High-Grounding Organizational Memory

This repository contains a production-prototype memory system that converts raw organizational artifacts (GitHub issues and discussions) into a grounded knowledge graph of decisions, features, and contributors.

The goal is to build auditable organizational memory: every stored fact must be traceable to source evidence.

The system extracts structured knowledge from GitHub artifacts, deduplicates it, builds a canonical memory graph, and exposes retrieval through a queryable context pack API and visualization UI.



System Architecture

Pipeline overview:

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

Stages:
	1.	Ingestion
	•	Pulls GitHub issue threads and comments.
	2.	Stratified Extraction
	•	Stage 1 extracts atomic claims from artifacts.
	•	Stage 2 analyzes full threads to capture architectural decisions.
	3.	Deduplication
	•	Entity canonicalization
	•	Claim merging
	•	Evidence aggregation
	4.	Memory Graph Storage
	•	Neo4j for graph exploration
	•	JSON memory graph for RAG-style retrieval
	5.	Retrieval
	•	Produces Context Packs containing facts + evidence.
	6.	Visualization
	•	Streamlit UI for interactive exploration.

⸻

Memory Graph Schema

The graph uses a reified claim model.

Instead of storing facts as direct edges, we represent each fact as a Claim node.

This allows attaching metadata such as:
	•	evidence
	•	confidence
	•	temporal validity
	•	provenance

Entity Nodes

Stable objects in the system.

Examples:
	•	Person
	•	Repository
	•	Issue
	•	Component
	•	Tool

Example:

{
  "id": "boostrix",
  "type": "Person",
  "name": "Boostrix"
}


⸻

Claim Nodes

Facts extracted from artifacts.

Structure:

(subject_entity_id, predicate, object_entity_id)

Example:

Boostrix → suggests_change → memory config changes

Claims store:
	•	predicate
	•	confidence
	•	valid_from
	•	valid_to

⸻

Evidence

Every claim must include supporting evidence.

Evidence fields:

artifact_id
excerpt
char_start
char_end

Example:

artifact_id: comment_1563628611
excerpt: "@Boostrix sounds good, I fixed the conflicts..."
char_start: 0
char_end: 110

This ensures that every stored fact is fully auditable.

⸻

Core Concepts

Ontology and Contract

The extraction system follows a strict schema contract.

Entities must include:

id
type
name
aliases

Claims must include:

subject_entity_id
predicate
object_entity_id
confidence
evidence

Extraction rules:
	•	Artifacts cannot become entities.
	•	Claims must reference valid entities.
	•	Every claim must contain at least one evidence excerpt.

This contract ensures high-precision memory construction.

⸻

Extraction Quality Controls

To prevent hallucinated facts, several safeguards were implemented.

Artifact Filtering

Artifact identifiers (issue IDs, comment IDs) are never promoted to entities.

Entity Validation

Claims referencing unknown entities are automatically discarded.

Two-Pass Extraction

The system first collects all entities across artifacts before processing claims.

This prevents losing claims referencing entities defined later in the dataset.

Schema Enforcement

Extraction outputs must match the schema before entering the graph pipeline.

⸻

Deduplication Strategy

The system implements three levels of deduplication.

Level 1 — Evidence Deduplication

Duplicate evidence excerpts are removed based on content hash.

⸻

Level 2 — Entity Canonicalization

Handles and aliases are normalized:

@Boostrix → boostrix
person_BaseInfinity → baseinfinity

Aliases are merged into a single canonical entity.

⸻

Level 3 — Claim Deduplication

Claims asserting the same fact are merged.

Matching key:

subject + predicate + object

Evidence from duplicates forms a Support Set.

Example:

Instead of storing:

Boostrix suggests_change memory config changes
Boostrix suggests_change memory config changes
Boostrix suggests_change memory config changes

The system stores one claim node with multiple evidence sources.

This produces consensus-weighted organizational memory.

⸻

Long-Term Correctness

Organizational knowledge evolves.

Claims include temporal metadata:

valid_from
valid_to

Example:

Boostrix suggests_change memory config changes
valid_from: 2023-05-25
valid_to: null

If a design decision changes:

valid_to: timestamp

This allows queries for:
	•	current facts
	•	historical decisions

Future work would add automatic contradiction detection.

⸻

Retrieval

The RetrievalService produces Knowledge Context Packs.

A context pack contains:

entities
claims
evidence
human-readable statements

Example output:

Statement:

Boostrix suggests_change memory config changes

Evidence:

Artifact: comment_1563628611
"@Boostrix sounds good, I fixed the conflicts..."

This format allows downstream agents to reason while maintaining evidence grounding.

⸻

Example Query

Query:

Who suggested configuration changes?

Result:

Boostrix suggests_change memory config changes

Evidence:

Artifact: comment_1563628611
"@Boostrix sounds good, i fixed the conflicts..."

The system surfaces both the fact and the original quote for verification.

⸻

Visualization

An interactive UI is provided using Streamlit.

Features:
	•	entity search
	•	natural language query support
	•	evidence browsing
	•	interactive knowledge graph

Run:

streamlit run src/retrieval/app.py

The graph view shows relationships between contributors, repositories, and features.

Screenshot available in:

visualization/graph_screenshot.png


⸻

System Metrics

Dataset processed:
	•	45 GitHub artifacts

Graph size:
	•	23 canonical entities
	•	22 unified claims
	•	70+ evidence excerpts

All claims in the graph are directly grounded in artifact evidence.

⸻

Layer10 Adaptation

In a production environment (Layer10), the system would extend to additional sources:
	•	Slack
	•	Discord
	•	Jira
	•	Email threads
	•	Internal documentation

Key improvements:

RBAC Filtering

Claims are filtered based on user access to underlying artifacts.

Golden Tier Memory

Only claims with multiple independent evidence sources become trusted organizational facts.

Streaming Ingestion

Move from batch processing to event-driven updates via Change Data Capture.

Cross-Source Linking

Merge claims extracted from multiple collaboration tools.

⸻

Reproducibility

Follow these steps to set up the environment, run the processing pipeline, and visualize the resulting organizational memory graph.


Getting Started

To set up the project locally, clone the repository and follow the environment setup instructions:

```bash
git clone <your-repository-url>
cd layer10_assignment
```


1. Environment Setup

Install the required Python dependencies:

pip install -r requirements.txt

The system requires a running Neo4j instance. Configure the connection details in a .env file in the root directory:

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
GROQ_API_KEY=your_api_key_here

⸻

2. Run the Processing Pipeline

Execute the following scripts in order to transform raw source data into a unified memory graph.

# Step A: Perform LLM-based extraction of artifacts and threads
# This requires a valid GROQ_API_KEY in your .env file
python src/extraction/llm_extractor.py
python src/extraction/thread_extraction.py

# Step B: Deduplicate and canonicalize the extracted artifacts
python src/dedup/dedup_service.py

# Step C: Ingest the unified graph into Neo4j for storage and exploration
python src/ingestion/neo4j_ingest.py

# Step D: Generate sample context packs for retrieval verification
python src/generate_samples.py

⸻

3. Visualization and Exploration

The system provides two primary ways to interact with the organizational memory.

Option A: Memory Explorer (Streamlit UI)

The Streamlit application is optimized for natural language search and evidence browsing.

Run the application:

streamlit run src/retrieval/app.py

In the UI:
- Use the Search tab to ask questions (for example, "Who suggested configuration changes?") or lookup specific entities (for example, "@BaseInfinity").
- Use the Knowledge Graph tab to see a local interactive visualization of the retrieved context.
- Review the Fact Stream for grounded evidence excerpts associated with each decision.

Option B: Graph Analysis (Neo4j Browser)

For a highly interactive, full-scale exploration of the knowledge graph, use the Neo4j Browser.

1. Open the Neo4j Browser in your web browser: http://localhost:7474
2. Log in using the credentials defined in your .env file.
3. To visualize the entire organizational memory graph, run the following Cypher command in the query bar:

MATCH (n)
OPTIONAL MATCH (n)-[r]->(m)
RETURN n, r, m
LIMIT 500

4. Use the Graph tab to drag nodes, zoom into clusters, and click on nodes or edges to inspect their properties (for example, claim statements, confidence scores, and evidence excerpts).

⸻

Outputs for Review

Serialized graph:
data/processed/memory_graph.json
outputs/memory_graph.json

Sample retrieval context packs:
data/processed/sample_context_packs.json
outputs/sample_context_packs.json

Neo4j Browser:
http://localhost:7474

⸻

Built for Layer10 Take-Home Assessment.

This system demonstrates how organizational memory can be structured, grounded, deduplicated, and queried at scale while preserving absolute traceability to original artifacts.