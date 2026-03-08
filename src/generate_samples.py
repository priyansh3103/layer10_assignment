import json
import os
from retrieval.retriever import RetrievalService


def generate_samples():

    r = RetrievalService()

    queries = [

        "Who suggested configuration changes?",
        "What features were proposed for AutoGPT?",
        "What issues were fixed in the project?",
        "What discussions involve Boostrix?"

    ]

    samples = {}

    for q in queries:

        hits = r.search_claims(q)

        if hits:

            # use the first hit to generate a context pack
            samples[q] = r.get_context_pack(
                hits[0]["subject_entity_id"]
            )

        else:

            samples[q] = {
                "entities": [],
                "claims": [],
                "msg": "No matches found"
            }

    base_dir = os.path.dirname(__file__)

    paths = [
        os.path.join(base_dir, "..", "data", "processed", "sample_context_packs.json"),
        os.path.join(base_dir, "..", "outputs", "sample_context_packs.json")
    ]

    for p in paths:

        os.makedirs(os.path.dirname(p), exist_ok=True)

        with open(p, "w") as f:
            json.dump(samples, f, indent=2)

        print(f"Generated samples → {p}")


if __name__ == "__main__":
    generate_samples()