import json
import os
from retrieval.retriever import RetrievalService

def generate_samples():
    r = RetrievalService()
    queries = [
        "Who suggested configuration changes?",
        "What features were proposed?",
        "What issues were reported?"
    ]
    
    samples = {}
    for q in queries:
        # Search for claims matching the NL query
        hits = r.search_claims(q)
        # Use the first hit's subject to get a full context pack (simulating UI behavior)
        if hits:
            samples[q] = r.get_context_pack(hits[0]["subject_entity_id"])
        else:
            samples[q] = {"entities": [], "claims": [], "msg": "No matches found"}
        
    # Paths to save
    base_dir = os.path.dirname(__file__)
    paths = [
        os.path.join(base_dir, "..", "data", "processed", "sample_context_packs.json"),
        os.path.join(base_dir, "..", "outputs", "sample_context_packs.json")
    ]
    
    for opt in paths:
        os.makedirs(os.path.dirname(opt), exist_ok=True)
        with open(opt, "w") as f:
            json.dump(samples, f, indent=2)
        print(f"Generated samples to {opt}")

if __name__ == "__main__":
    generate_samples()
