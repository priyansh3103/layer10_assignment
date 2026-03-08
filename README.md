# Layer10 Memory Graph: High-Grounding Organizational Memory

This repository implements a **production-style prototype organizational memory system** that converts raw collaboration artifacts (GitHub issues and discussions) into a **grounded knowledge graph** of contributors, design decisions, and architectural changes.

The system emphasizes **auditability and grounding**: every stored fact must be traceable to **original source evidence**. Raw artifacts are transformed through a multi-stage pipeline that: (1) extracts structured knowledge using LLMs, (2) deduplicates and canonicalizes entities and claims, (3) constructs a canonical **organizational memory graph**, and (4) enables **hybrid retrieval and evidence-grounded reasoning**. The resulting system allows users and downstream agents to query organizational knowledge **without hallucination risk**, since every result is backed by verifiable evidence.

**For the full design, component details, and feature writeup, see [ARCHITECTURE.md](ARCHITECTURE.md).**

---

## Components (Overview)

| Component | Purpose |
|-----------|---------|
| **Ingestion** | Fetches GitHub issues and comments via API; normalizes to internal artifact format. |
| **Stratified extraction** | Two passes: (1) artifact-level entities/claims/evidence → `payloads.json`; (2) thread-level architectural decisions → `thread_payloads.json`. |
| **Deduplication** | Entity canonicalization, claim merging, evidence aggregation, temporal revision, audit logging. |
| **Memory graph** | Reified claim model (entities + claims + evidence) stored as `memory_graph.json` and optionally in Neo4j. |
| **Retrieval** | Hybrid retrieval (entity-first, keyword, embedding) producing **context packs** (entities, claims, evidence, statements). |
| **Visualization** | Streamlit Memory Explorer (query + evidence + graph) and Neo4j Browser for full-graph exploration. |

For detailed design, schema, quality controls, retrieval strategies, and Layer10 adaptation notes, see **[ARCHITECTURE.md](ARCHITECTURE.md)**.

**Pipeline stages:**

1. **Ingestion** — Pulls GitHub issue threads and comments.
2. **Stratified extraction** — Stage 1 extracts atomic claims from artifacts; stage 2 analyzes full threads to capture architectural decisions.
3. **Deduplication** — Entity canonicalization, claim merging, evidence aggregation.
4. **Memory graph storage** — Neo4j for graph exploration; JSON memory graph for RAG-style retrieval.
5. **Retrieval** — Produces context packs containing facts + evidence.
6. **Visualization** — Streamlit UI for interactive exploration; Neo4j Browser for full-graph analysis.

---

## Repository Structure

```
layer10_assignment/
├── data/
│   ├── raw/           # artifacts.json (ingested GitHub data)
│   ├── extracted/     # payloads.json, thread_payloads.json
│   └── processed/     # memory_graph.json, sample_context_packs.json
├── outputs/           # Copies of processed graph and sample packs for review
├── visualization/     # Screenshots and video of Streamlit query search and knowledge graph
├── schema/            # ontology.py (entity/claim schema)
├── src/
│   ├── extraction/    # llm_extractor.py, thread_extraction.py
│   ├── dedup/         # dedup_service.py
│   ├── ingestion/     # github_ingest.py, neo4j_ingest.py
│   ├── retrieval/     # app.py (Streamlit), retriever.py
│   └── generate_samples.py
├── requirements.txt
├── docker-compose.yml # Optional Neo4j
├── README.md
└── ARCHITECTURE.md    # Detailed design and features
```

---

## Reproducibility

Follow these steps to set up the environment, run the processing pipeline, and visualize the resulting organizational memory graph.

### Start Neo4j (Docker)

The system requires a running Neo4j instance. The easiest way to start one is using Docker:

```bash
docker run \
  --name layer10-neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  -d neo4j:5
```

- **Bolt endpoint:** bolt://localhost:7687  
- **Browser UI:** http://localhost:7474  
- **Default credentials:** username `neo4j`, password `password`

### 1. Environment setup

```bash
git clone <your-repository-url>
cd layer10_assignment
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
GROQ_API_KEY=your_api_key
```

### 2. Run the processing pipeline

Execute the following scripts in order to transform raw source data into a unified memory graph:

```bash
# Step A: LLM-based extraction (requires GROQ_API_KEY in .env)
python src/extraction/llm_extractor.py
python src/extraction/thread_extraction.py

# Step B: Deduplicate and canonicalize
python src/dedup/dedup_service.py

# Step C: Ingest into Neo4j for graph exploration
python src/ingestion/neo4j_ingest.py

# Step D: Generate sample context packs for retrieval verification
python src/generate_samples.py
```

### 3. Visualization and exploration

The system provides two ways to interact with the organizational memory.

**Option A: Memory Explorer (Streamlit UI)**

The Streamlit app is optimized for natural language search and evidence browsing. Run:

```bash
streamlit run src/retrieval/app.py
```

In the UI:

- Use the **Search** tab to ask questions (e.g. “Who suggested configuration changes?”) or look up entities (e.g. “@BaseInfinity”).
- Use the **Knowledge Graph** tab to see an interactive visualization of the retrieved context.
- Review the **Fact Stream** for grounded evidence excerpts associated with each decision.

The graph view shows relationships between contributors, repositories, and features. Screenshots and a video are in `visualization/` (e.g. `query_search.png`, `knowledge_graph.mov`).

**Option B: Graph analysis (Neo4j Browser)**

For full-scale exploration of the knowledge graph:

1. Open **http://localhost:7474** in your browser.
2. Log in with the credentials from your `.env` file (or the defaults above).
3. In the query bar, run:

```cypher
MATCH (n)
OPTIONAL MATCH (n)-[r]->(m)
RETURN n, r, m
```

4. Use the **Graph** tab to drag nodes, zoom into clusters, and click nodes or edges to inspect properties (e.g. claim statements, confidence scores, evidence excerpts).

### Outputs for review

- **Serialized graph:** `data/processed/memory_graph.json`, `outputs/memory_graph.json`
- **Sample retrieval packs:** `data/processed/sample_context_packs.json`, `outputs/sample_context_packs.json`
- **Neo4j Browser:** http://localhost:7474 (after running the pipeline and Neo4j)

---

**Built for the Layer10 Take-Home Assessment.** This prototype demonstrates how organizational knowledge can be extracted from collaboration artifacts, structured into a canonical graph, deduplicated and versioned, retrieved with evidence grounding, and visualized interactively—while maintaining **complete traceability to original artifacts**. For metrics, example queries, and production adaptation ideas, see [ARCHITECTURE.md](ARCHITECTURE.md).
