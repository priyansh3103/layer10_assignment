import streamlit as st
import pandas as pd
from retriever import RetrievalService
from streamlit_agraph import agraph, Node, Edge, Config

# -----------------------------
# Page Config
# -----------------------------

st.set_page_config(
    page_title="Layer10 | Grounded Memory",
    layout="wide",
    page_icon="🧠"
)

# -----------------------------
# Styling
# -----------------------------

st.markdown("""
<style>
.main {
    background-color: #0e1117;
}
.stHeader {
    background: linear-gradient(90deg, #00C9FF 0%, #92FE9D 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800;
    font-size: 3rem !important;
}
.card {
    padding: 1.5rem;
    border-radius: 10px;
    background-color: #161b22;
    border: 1px solid #30363d;
    margin-bottom: 1rem;
}
.stat-val {
    font-size: 2rem;
    font-weight: bold;
    color: #58a6ff;
}
.stat-label {
    color: #8b949e;
    font-size: 0.9rem;
}
</style>
""", unsafe_allow_html=True)

# -----------------------------
# Load Retrieval Engine
# -----------------------------

@st.cache_resource
def get_retriever():
    return RetrievalService()

retriever = get_retriever()

graph = retriever.graph

# -----------------------------
# Sidebar
# -----------------------------

with st.sidebar:

    st.image("https://img.icons8.com/isometric/512/brain.png", width=100)

    st.markdown("# System Stats")

    st.markdown(f"""
    <div class="card">
        <div class="stat-val">{len(graph['entities'])}</div>
        <div class="stat-label">Identified Entities</div>
    </div>

    <div class="card">
        <div class="stat-val">{len(graph['claims'])}</div>
        <div class="stat-label">Grounded Facts</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    st.info(
        "This knowledge graph was extracted from AutoGPT GitHub discussions."
    )

# -----------------------------
# Header
# -----------------------------

st.markdown('<div class="stHeader">Memory Explorer</div>', unsafe_allow_html=True)

st.markdown(
    "Search across people, repositories, pull requests, and system discussions."
)

tab1, tab2 = st.tabs(["Search & Context", "Knowledge Graph"])

# ----------------------------------------------------
# TAB 1 — Search / Retrieval
# ----------------------------------------------------

with tab1:

    query = st.text_input(
        "Ask a question or search the memory graph",
        placeholder="Example: Who suggested configuration changes?"
    )

    if query:

        pack = retriever.get_context_pack(query)

        # fallback warning
        if pack.get("fallback_used"):
            st.warning(
                f'No direct grounded claims found for entity "{pack.get("entity_name")}". '
                "Showing semantically related discussions instead."
            )

        if not pack["claims"]:
            st.warning("No grounded facts found.")
        else:

            st.subheader("Retrieved Knowledge")

            for claim in pack["claims"]:

                st.markdown(f"### {claim['statement']}")
                st.caption(f"Confidence: {claim['confidence']*100:.0f}%")

                for ev in claim["evidence"]:
                    st.caption(f"Artifact: {ev['artifact']}")
                    st.markdown(f"> {ev['quote']}")

                st.markdown("---")

    else:

        st.subheader("Recent Facts")

        rows = []

        for c in retriever.get_context_pack("autogpt")["claims"][:15]:

            rows.append({
                "Statement": c["statement"],
                "Confidence": f"{c.get('confidence',0)*100:.0f}%",
                "Evidence": c["evidence"][0]["quote"] if c["evidence"] else ""
            })

        df = pd.DataFrame(rows)

        st.table(df)

# ----------------------------------------------------
# TAB 2 — Knowledge Graph
# ----------------------------------------------------

with tab2:

    st.subheader("Interactive Knowledge Graph")

    nodes = []
    edges = []

    color_map = {
        "Person": "#58a6ff",
        "Issue": "#d73a49",
        "Repository": "#238636",
        "Component": "#d29922",
        "Tool": "#f0883e",
        "File": "#bc8cff"
    }

    # Nodes
    for ent in graph["entities"]:

        nodes.append(Node(
            id=ent["id"],
            label=ent["name"],
            size=20,
            color=color_map.get(ent["type"], "#cccccc")
        ))

    # Edges (from raw graph)
    for claim in graph["claims"]:

        subj = claim["subject_entity_id"]
        obj = claim.get("object_entity_id")

        if obj:

            edges.append(Edge(
                source=subj,
                target=obj,
                label=claim["predicate"]
            ))

    config = Config(
        width=1000,
        height=650,
        directed=True,
        nodeHighlightBehavior=True,
        highlightColor="#F7A7A6",
        collapsible=True,
        node={'labelProperty': 'label'},
        link={'labelProperty': 'label', 'renderLabel': True}
    )

    agraph(nodes=nodes, edges=edges, config=config)

# -----------------------------
# Footer
# -----------------------------

st.markdown("---")

st.markdown(
    "Built for Layer10 Take-home Assessment | Evidence-Grounded Memory Graph"
)