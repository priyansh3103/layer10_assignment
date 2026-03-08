import os
import json
from typing import List, Dict, Any, Tuple
from datetime import datetime
import sys

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from schema.ontology import Entity, Claim

class DedupService:
    def __init__(self):
        # We store canonical entities by their lowercase ID
        self.canonical_entities: Dict[str, Entity] = {}
        # We store accepted claims by a deterministic key: subj|pred|obj
        self.canonical_claims: Dict[str, Claim] = {}

    def _normalize_entity_id(self, x: str) -> str:
        """Helper to unify handles, prefixes, and formatting."""
        if not x:
            return None
        # Remove @ and person_ prefixes, lowercase, and strip
        return x.lower().replace("@", "").replace("person_", "").strip()
        
    def canonicalize_entity(self, new_entity: Entity) -> Entity:
        """
        Entity Cannonicalization (Level 2 Dedup)
        Merges entities with identical normalized IDs or names.
        """
        norm_id = self._normalize_entity_id(new_entity.id)
        if not norm_id:
            return None
            
        new_entity.id = norm_id # Force normalized ID string
        
        if norm_id in self.canonical_entities:
            existing = self.canonical_entities[norm_id]
            # Merge aliases
            for alias in new_entity.aliases:
                if alias not in existing.aliases:
                    existing.aliases.append(alias)
            return existing
            
        # Register new entity
        self.canonical_entities[norm_id] = new_entity
        return new_entity

    def add_claim(self, new_claim: Claim):
        """
        Claim Deduplication (Level 3 Dedup)
        Merges claims asserting the same fact (matching subj, pred, obj).
        Creates a Support Set by merging Evidence.
        """
        subj_id = self._normalize_entity_id(new_claim.subject_entity_id)
        obj_id = self._normalize_entity_id(new_claim.object_entity_id)
        
        # PROBLEM 1: Phantom Claim Subjects
        # Skip if the subject doesn't exist in our canonical entity list
        if subj_id not in self.canonical_entities:
            print(f"Skipping phantom claim: Subject '{subj_id}' not found in entities.")
            return
            
        # Update the claim object with normalized IDs for consistency in final JSON
        new_claim.subject_entity_id = subj_id
        new_claim.object_entity_id = obj_id # may be None

        # Build key for merging
        key_obj = obj_id or "null"
        key = f"{subj_id}|{new_claim.predicate.lower()}|{key_obj}"
        
        if key in self.canonical_claims:
            existing = self.canonical_claims[key]
            # Support Set: Append new evidence
            existing_evidence = {(ev.artifact_id, ev.excerpt) for ev in existing.evidence}
            for ev in new_claim.evidence:
                if (ev.artifact_id, ev.excerpt) not in existing_evidence:
                    existing.evidence.append(ev)
            # Update confidence (max)
            existing.confidence = max(existing.confidence, new_claim.confidence)
        else:
            self.canonical_claims[key] = new_claim

def process_all_data():
    DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
    payloads_path = os.path.join(DATA_DIR, 'extracted', 'payloads.json')
    thread_payloads_path = os.path.join(DATA_DIR, 'extracted', 'thread_payloads.json')
    output_path = os.path.join(DATA_DIR, 'processed', 'memory_graph.json')
    
    service = DedupService()
    
    all_data = []
    if os.path.exists(payloads_path):
        with open(payloads_path, 'r') as f:
            all_data.extend(json.load(f))
    if os.path.exists(thread_payloads_path):
        with open(thread_payloads_path, 'r') as f:
            all_data.extend(json.load(f))

    # Pass 1: Collect all Entities
    print(f"Pass 1: Collecting entities from {len(all_data)} items...")
    for item in all_data:
        extracted = item.get('extracted', {})
        for e_dict in extracted.get('entities', []):
            try:
                service.canonicalize_entity(Entity(**e_dict))
            except Exception as e:
                print(f"Entity error: {e}")

    # Pass 2: Process all Claims
    print(f"Pass 2: Processing grounding claims...")
    for item in all_data:
        extracted = item.get('extracted', {})
        for c_dict in extracted.get('claims', []):
            try:
                service.add_claim(Claim(**c_dict))
            except Exception as e:
                print(f"Claim error: {e}")
            
    # Final Graph Preparation
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    graph = {
        "schema_version": "1.0",
        "generated_at": datetime.utcnow().isoformat(),
        "entities": [e.model_dump() for e in service.canonical_entities.values()],
        "claims": [c.model_dump() for c in service.canonical_claims.values()]
    }
    
    with open(output_path, "w") as f:
        json.dump(graph, f, indent=2)
        
    print(f"Deduplication Complete.")
    print(f"Canonical Entities: {len(graph['entities'])}")
    print(f"Unified Claims (Support Sets): {len(graph['claims'])}")
    print(f"Saved to: {output_path}")

if __name__ == "__main__":
    process_all_data()
