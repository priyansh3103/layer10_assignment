import os
import json
import instructor
from typing import Dict, Any
import sys
import time
import re

# Ensure schema is importable
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from schema.ontology import ExtractionPayload

from dotenv import load_dotenv
load_dotenv()

from groq import Groq

# Initialize Instructor patched Groq client
client = instructor.from_groq(
    Groq(api_key=os.environ.get("GROQ_API_KEY")),
    mode=instructor.Mode.TOOLS
)

MODEL = "llama-3.1-8b-instant"

MAX_CHARS = 4000


def clean_content(text: str) -> str:
    """Remove HTML comments and normalize whitespace."""
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    return "\n".join([line.strip() for line in text.splitlines() if line.strip()])


SYSTEM_PROMPT = """
You are a precise data extraction system mapping text into a Grounded Memory Graph.

STRUCTURAL RULES:
1. Return a single JSON object matching the `ExtractionPayload` schema.
2. `entities` and `claims` MUST be non-empty if the text contains useful information.
3. Every entity MUST have a non-empty `id`, `type`, and `name`.
4. Artifact IDs (e.g., issue_4128, comment_1544833388) are NOT entities. Never create entities for them.
5. Metadata lines starting with "Author:" or "Date:" are NOT entities.

ENTITY RULES:
1. Allowed entity types: Person, Repository, Issue, Component, Tool, File.
2. Never create entities whose IDs start with: issue_, comment_.
3. Do NOT create entities of type URL.

CLAIM RULES:
1. `subject_entity_id` and `object_entity_id` MUST correspond to IDs in the `entities` list.
2. `object_entity_id` must NOT be an artifact ID (starting with issue_ or comment_).
3. If a claim has no clear object, set `object_entity_id` to null. Do NOT use empty strings.
4. Do NOT create claims where `subject_entity_id` == `object_entity_id`.
5. Extract only factual software knowledge (e.g., who is working on what, dependency relations, bug reports).
6. `predicate` MUST be one of: authored, assigned_to, proposes_feature, reports_issue, suggests_change, removes_configuration, updates_component, depends_on, fixes_issue.

EVIDENCE RULES:
1. Every claim MUST have exactly one `Evidence` object.
2. The `excerpt` MUST be a direct, literal quote from the text.
"""


def extract_from_artifact(artifact: Dict[str, Any]) -> ExtractionPayload:
    """
    Pass artifact to LLM and enforce schema.
    """
    clean_text = clean_content(artifact["content"])[:MAX_CHARS]

    full_text_for_llm = (
        f"Author: {artifact['author_id']}\n"
        f"Date: {artifact['created_at']}\n\n"
        f"{clean_text}"
    )

    prompt = f"""
Analyze the following artifact and extract Entities, Claims, and Evidence.

ARTIFACT ID: {artifact['id']}

TEXT:
{full_text_for_llm}
"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            response_model=ExtractionPayload,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            max_retries=3
        )

        # Validate claims
        valid_claims = []
        ALLOWED_PREDICATES = {
            "authored", "assigned_to", "proposes_feature", "reports_issue",
            "suggests_change", "removes_configuration", "updates_component",
            "depends_on", "fixes_issue"
        }

        for claim in response.claims:
            # Filter predicates
            if claim.predicate not in ALLOWED_PREDICATES:
                continue

            # Normalize "null" string to None
            if claim.object_entity_id == "null":
                claim.object_entity_id = None

            if claim.subject_entity_id == "null":
                continue

            # Remove self-referential claims or artifact references in IDs
            FORBIDDEN_REF = ("issue_", "comment_")
            if (claim.subject_entity_id == claim.object_entity_id or 
                any(claim.subject_entity_id.startswith(p) for p in FORBIDDEN_REF)):
                continue

            # Discard claims referencing artifact IDs as objects
            if claim.object_entity_id and (
                claim.object_entity_id.startswith("issue_") or 
                claim.object_entity_id.startswith("comment_")
            ):
                continue

            valid_evidence = []

            for ev in claim.evidence:
                # Reject weak evidence (too short)
                if len(ev.excerpt.strip()) < 10:
                    continue

                ev.artifact_id = artifact["id"]

                start_idx = artifact["content"].find(ev.excerpt)

                if start_idx != -1:
                    ev.char_start = start_idx
                    ev.char_end = start_idx + len(ev.excerpt)
                    valid_evidence.append(ev)

            if valid_evidence:
                claim.evidence = valid_evidence
                valid_claims.append(claim)

        # Limit to 3 claims per artifact
        response.claims = valid_claims[:3]

        # Filter entities
        FORBIDDEN_PREFIXES = ("issue_", "comment_", "Person_", "person_", "Author", "author")
        filtered_entities = [
            e for e in response.entities 
            if e.type != "URL" and not any(e.id.startswith(p) for p in FORBIDDEN_PREFIXES)
        ]

        # remove duplicate entities per artifact
        unique_entities = {}
        for e in filtered_entities:
            unique_entities[e.id] = e

        response.entities = list(unique_entities.values())

        return response

    except Exception as e:
        print(f"Failed to extract from {artifact['id']}: {e}")
        return None


def run_pipeline():
    DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
    raw_path = os.path.join(DATA_DIR, 'raw', 'artifacts.json')
    out_path = os.path.join(DATA_DIR, 'extracted', 'payloads.json')
    lock_path = os.path.join(DATA_DIR, 'extraction.lock')

    if os.path.exists(lock_path):
        print(f"Extraction already in progress (lock exists at {lock_path}). Exiting.")
        return

    try:
        with open(lock_path, "w") as f:
            f.write(str(os.getpid()))

        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        if not os.path.exists(raw_path):
            print("No raw artifacts found. Run ingestion first.")
            return

        with open(raw_path, "r") as f:
            artifacts = json.load(f)

        if not os.environ.get("GROQ_API_KEY"):
            print("Skipping LLM extraction, GROQ_API_KEY not set.")
            return

        print(f"Starting extraction for {len(artifacts)} artifacts...")

        extracted_data = []

        # Resume previous progress
        if os.path.exists(out_path):
            try:
                with open(out_path, "r") as f:
                    extracted_data = json.load(f)
                    print(f"Loaded {len(extracted_data)} existing extractions.")
            except Exception:
                print("Failed to load previous payloads.")

        already_done = {item["artifact_id"] for item in extracted_data}
        
        for idx, art in enumerate(artifacts):

            if art["id"] in already_done:
                continue

            author = art.get("author_id", "").lower()

            # Skip bot artifacts
            if "[bot]" in author:
                print(f"Skipping bot artifact: {art['id']} ({art['author_id']})")
                continue

            print(f"Processing ({idx+1}/{len(artifacts)}): {art['id']}")

            payload = extract_from_artifact(art)

            if payload:
                extracted_data.append({
                    "artifact_id": art["id"],
                    "extracted": payload.model_dump()
                })

                with open(out_path, "w") as f:
                    json.dump(extracted_data, f, indent=2)

            print("Pacing... (5s)")
            time.sleep(5)

        print(f"Extraction complete. Total artifacts processed: {len(extracted_data)}")
    finally:
        if os.path.exists(lock_path):
            os.remove(lock_path)


if __name__ == "__main__":
    run_pipeline()