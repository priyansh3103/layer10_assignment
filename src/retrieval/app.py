import streamlit as st
import pandas as pd
from retriever import RetrievalService
from annotated_text import annotated_text
from streamlit_agraph import agraph, Node, Edge, Config

# Page Config
st.set_page_config(page_title="Layer10 | Grounded Memory", layout="wide", page_icon="🧠")

# Custom CSS for Premium Look
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

# Initialize Backend
@st.cache_resource
def get_retriever():
    return RetrievalService()

retriever = get_retriever()
graph_data = retriever.get_context_pack()

# Sidebar / Stats
with st.sidebar:
    st.image("https://img.icons8.com/isometric/512/brain.png", width=100)
    st.markdown("# System Stats")
    st.markdown(f"""
        <div class="card">
            <div class="stat-val">{len(graph_data['entities'])}</div>
            <div class="stat-label">Identified Entities</div>
        </div>
        <div class="card">
            <div class="stat-val">{len(graph_data['claims'])}</div>
            <div class="stat-label">Grounded Facts</div>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    st.info("This graph was built from 45 AutoGPT artifacts using Llama 3.3 70B.")

# Main Header
st.markdown('<div class="stHeader">Memory Explorer</div>', unsafe_allow_html=True)
st.markdown("Search across people, pull requests, and features mentioned in the organizational memory.")

tab1, tab2 = st.tabs(["Search and Activity", "Knowledge Graph"])

with tab1:
    # Search
    search_query = st.text_input("Search entities OR ask a question (e.g. Who suggested configuration changes?)", "")

    if search_query:
        results = retriever.search_entities(search_query)

        if not results:

            # fallback to claim search
            claim_hits = retriever.search_claims(search_query)

            if not claim_hits:
                st.warning("No matching entities or claims found.")
            else:
                st.subheader("Matching Facts")

                for claim in claim_hits:
                    pack = retriever.get_context_pack(claim["subject_entity_id"])

                    for c in pack["claims"]:
                        st.markdown(f"**{c['statement']}**")

                        for ev in c["evidence"]:
                            st.caption(f"Artifact: {ev['artifact']}")
                            st.markdown(f"> {ev['quote']}")
        else:
            for ent in results:
                display_name = f"{ent['type']}: {ent['name']} ({ent['id']})"
                with st.expander(display_name, expanded=True):
                    pack = retriever.get_context_pack(ent['id'])
                    
                    if not pack['claims']:
                        st.write("No specific claims found for this entity.")
                    else:
                        for claim in pack['claims']:
                            st.markdown(f"Statement: **{claim['statement']}**")
                            
                            # Show Evidence
                            for ev in claim['evidence']:
                                st.caption(f"Evidence from Artifact: {ev['artifact']}")
                                st.markdown(f"> \"{ev['quote']}\"")
                    st.markdown("---")
    else:
        # Default View: Show summary table
        st.subheader("Global Fact Stream")
        claim_rows = []
        for c in graph_data['claims'][:15]: 
            claim_rows.append({
                "Statement": c['statement'],
                "Confidence": f"{c.get('confidence', 1.0)*100:.0f}%",
                "Evidence Sample": c['evidence'][0]['quote'] if c['evidence'] else "N/A"
            })
        df = pd.DataFrame(claim_rows)
        st.table(df)

with tab2:
    st.subheader("Interactive Graph Visualization")
    st.info("Explore the relationships between users, pull requests, and repositories.")
    
    nodes = []
    edges = []
    
    # Map colors to entity types
    color_map = {
        "Person": "#58a6ff",
        "Issue": "#d73a49",
        "Repository": "#238636",
        "Component": "#d29922",
        "Package": "#f0883e",
        "API": "#bc8cff",
        "URL": "#8b949e"
    }

    # Add Nodes
    for ent in graph_data['entities']:
        nodes.append(Node(
            id=ent['id'], 
            label=ent['name'], 
            size=20, 
            color=color_map.get(ent['type'], "#ffffff")
        ))
    
    # Add Edges (Only bidirectional claims with target entities)
    for c in graph_data['claims']:
        if c.get('object_entity_id'):
            edges.append(Edge(
                source=c['subject_entity_id'], 
                target=c['object_entity_id'], 
                label=c['predicate']
            ))

    config = Config(
        width=1000, 
        height=600, 
        directed=True, 
        nodeHighlightBehavior=True, 
        highlightColor="#F7A7A6", 
        collapsible=True,
        node={'labelProperty': 'label'},
        link={'labelProperty': 'label', 'renderLabel': True}
    )

    agraph(nodes=nodes, edges=edges, config=config)

# Footer
st.markdown("---")
st.markdown("Built for Layer10 Take-home Assessment | High-Grounding Memory System")
