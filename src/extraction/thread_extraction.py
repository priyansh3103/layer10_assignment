import os
import json
import time
from typing import List, Dict, Any
from dotenv import load_dotenv
import instructor
from groq import Groq
from pydantic import BaseModel, Field

# Add project root to path to import local modules
import sys
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(project_root)

from schema.ontology import Entity, Claim, Evidence, ExtractionPayload

load_dotenv()

client = instructor.from_groq(Groq(), mode=instructor.Mode.JSON)

SYSTEM_PROMPT = """
You are a high-level knowledge architect analyzing software engineering discussion threads.
A thread is a collection of an Issue and its subsequent Comments.

YOUR GOAL:
Extract high-level design decisions, feature proposals, bug reports, and architectural dependencies that emerge across the entire thread.

ENTITY RULES:
1. Allowed types: Person, Repository, Issue, Component, Tool, File.
2. Focus on global entities (e.g., the library being used, the main component being discussed).

CLAIM RULES:
1. Focus on SUBSTANTIAL claims only (Proposals, Decisions, Dependencies).
2. `predicate` MUST be one of: proposes_feature, reports_issue, suggests_change, removes_configuration, updates_component, depends_on, fixes_issue.
3. Every claim MUST be grounded in the text via literal excerpts.
4. Set `object_entity_id` to null if there is no clear object.
5. If subject_entity_id == object_entity_id, discard the claim.
"""

def extract_from_thread(thread_text: str, artifact_id: str) -> ExtractionPayload:
    """Extract structured data from a combined thread text."""
    try:
        # Limited to first 6000 chars for threads to stay within bounds
        cleaned_text = thread_text.strip()[:6000]
        
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            response_model=ExtractionPayload,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"THREAD CONTENT:\n{cleaned_text}"}
            ],
            temperature=0.1
        )

        # Basic filtering (similar to artifact-level)
        valid_claims = []
        for claim in response.claims:
            # Remove self-referential claims or artifact references in IDs
            FORBIDDEN_REF = ("issue_", "comment_")
            if (claim.subject_entity_id == claim.object_entity_id or 
                any(claim.subject_entity_id.startswith(p) for p in FORBIDDEN_REF)):
                continue
            
            if claim.object_entity_id == "null":
                claim.object_entity_id = None
                
            if claim.object_entity_id and (
                claim.object_entity_id.startswith("issue_") or 
                claim.object_entity_id.startswith("comment_")
            ):
                continue
                
            valid_evidence = []
            for ev in claim.evidence:
                if len(ev.excerpt.strip()) >= 10:
                    ev.artifact_id = artifact_id
                    valid_evidence.append(ev)
            
            if valid_evidence:
                claim.evidence = valid_evidence
                valid_claims.append(claim)
        
        response.claims = valid_claims[:5] # A bit more for threads
        
        # Filter entities
        FORBIDDEN_PREFIXES = ("issue_", "comment_", "Person_", "person_", "Author", "author")
        filtered_entities = [
            e for e in response.entities 
            if e.type != "URL" and not any(e.id.startswith(p) for p in FORBIDDEN_PREFIXES)
        ]

        # remove duplicate entities per thread
        unique_entities = {}
        for e in filtered_entities:
            unique_entities[e.id] = e

        response.entities = list(unique_entities.values())

        return response
    except Exception as e:
        print(f"Error extracting from thread {artifact_id}: {e}")
        return None

def run_thread_pipeline():
    DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
    raw_path = os.path.join(DATA_DIR, 'raw', 'artifacts.json')
    out_path = os.path.join(DATA_DIR, 'extracted', 'thread_payloads.json')

    if not os.path.exists(raw_path):
        print("No raw artifacts found.")
        return

    with open(raw_path, "r") as f:
        artifacts = json.load(f)

    # Group by Issue (Thread)
    # Artifacts have ids like issue_4130 or comment_1545026604
    # We need to find which comments belong to which issues.
    # For GitHub, comments usually come after the issue in the list 
    # but a better way is to group them by the issue ID they relate to.
    # In our provided artifacts.json, they are likely sequential or have some relation.
    # Let's simple group by the FIRST issue we see until the next issue.
    
    threads = {}
    current_issue_id = None
    
    for art in artifacts:
        if art["id"].startswith("issue_"):
            current_issue_id = art["id"]
            threads[current_issue_id] = [art]
        elif art["id"].startswith("comment_") and current_issue_id:
            threads[current_issue_id].append(art)

    print(f"Found {len(threads)} issue threads.")
    
    thread_payloads = []
    
    for issue_id, arts in threads.items():
        print(f"Processing thread: {issue_id} ({len(arts)} items)")
        
        combined_text = ""
        for a in arts:
            combined_text += f"\n---\nAUTHOR: {a.get('author_id')}\nCONTENT:\n{a.get('content')}\n"
        
        payload = extract_from_thread(combined_text, issue_id)
        if payload:
            thread_payloads.append({
                "thread_id": issue_id,
                "extracted": payload.model_dump()
            })
            
            # Save progressively
            with open(out_path, "w") as f:
                json.dump(thread_payloads, f, indent=2)
        
        print("Pacing... (5s)")
        time.sleep(5)

    print(f"Thread extraction complete. Saved to {out_path}")

if __name__ == "__main__":
    run_thread_pipeline()
