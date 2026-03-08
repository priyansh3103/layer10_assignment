import json
import os
from typing import List, Dict, Any

GRAPH_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'processed', 'memory_graph.json')

class RetrievalService:
    def __init__(self):
        self.graph = {"entities": [], "claims": []}
        self.entity_map = {}
        self.load_graph()

    def load_graph(self):
        if os.path.exists(GRAPH_PATH):
            with open(GRAPH_PATH, 'r') as f:
                self.graph = json.load(f)
        # Build entity map for fast name resolution
        self.entity_map = {e['id']: e for e in self.graph.get('entities', [])}

    def normalize_entity_id(self, x: str) -> str:
        """Unify handles, prefixes, and formatting (matches DedupService logic)."""
        if not x:
            return None
        return x.lower().replace("@", "").replace("person_", "").strip()

    def get_context_pack(self, query_entity: str = None) -> Dict[str, Any]:
        """
        Retrieves a 'Knowledge Pack' for a specific entity or the whole graph.
        This provides the grounded factual context for any RAG task.
        """
        # Normalize target entity for lookup if provided
        norm_query_entity = self.normalize_entity_id(query_entity) if query_entity else None

        # Filter entities and claims for specific context
        raw_claims = self.graph.get('claims', [])
        if norm_query_entity:
            raw_claims = [
                c for c in raw_claims 
                if (c['subject_entity_id'] and c['subject_entity_id'] == norm_query_entity) or 
                   (c['object_entity_id'] and c['object_entity_id'] == norm_query_entity)
            ]
        
        # Format claims with human-readable statements and evidence list
        formatted_claims = []
        entity_ids = set()
        for c in raw_claims:
            subj_id = c["subject_entity_id"]
            obj_id = c["object_entity_id"]
            
            # Resolve Names
            subj_name = self.entity_map.get(subj_id, {}).get("name", subj_id)
            obj_name = self.entity_map.get(obj_id, {}).get("name", obj_id) if obj_id else None
            
            # Build Readable Statement
            if obj_name:
                statement = f"{subj_name} {c['predicate']} {obj_name}"
            else:
                statement = f"{subj_name} {c['predicate']}"
            
            # Format Evidence
            evidence_list = [
                {"artifact": ev["artifact_id"], "quote": ev["excerpt"]}
                for ev in c.get("evidence", [])
            ]
            
            # Update entity set for the final pack
            if subj_id:
                entity_ids.add(subj_id)
            if obj_id:
                entity_ids.add(obj_id)
                
            formatted_claims.append({
                **c,
                "statement": statement,
                "evidence": evidence_list
            })
            
        if norm_query_entity:
            # For specific query, return only involved entities
            related_entities = [e for e in self.graph['entities'] if e['id'] in entity_ids]
        else:
            # For global query, return all entities
            related_entities = self.graph['entities']

        return {
            "entities": related_entities,
            "claims": formatted_claims
        }

    def search_entities(self, text: str) -> List[Dict[str, Any]]:
        """Finds entities by name, ID, or aliases (simple fuzzy search)."""
        search_text = text.lower()
        return [
            e for e in self.graph['entities']
            if search_text in e['id'].lower()
            or search_text in e['name'].lower()
            or search_text in " ".join(e.get("aliases", [])).lower()
        ]
    def parse_query(self, query: str) -> Dict[str, List[str]]:
        """
        Parses a natural language query into keywords and potential predicate hints.
        """
        # Cleanup: lower, remove punctuation (simple)
        text = query.lower()
        for char in "?!.,:;":
            text = text.replace(char, "")
        
        tokens = text.split()
        
        # Stopwords to ignore
        stopwords = {"who", "what", "the", "a", "an", "is", "was", "were", "where", "how", "did", "does", "of", "in", "to"}
        keywords = [t for t in tokens if t not in stopwords and len(t) > 2]
        
        return {"keywords": keywords}

    def search_claims(self, text: str):
        """
        Advanced claim search using query parsing, predicate mapping, and ranking.
        """
        parsed = self.parse_query(text)
        keywords = parsed["keywords"]
        
        if not keywords:
            return []

        # Predicate expansion map
        predicate_map = {
            "suggest": "suggests_change",
            "suggested": "suggests_change",
            "change": "suggests_change",
            "changes": "suggests_change",
            "propose": "proposes_feature",
            "proposed": "proposes_feature",
            "feature": "proposes_feature",
            "issue": "reports_issue",
            "reported": "reports_issue",
            "fix": "fixes_issue",
            "fixed": "fixes_issue"
        }

        # Identify target predicates from keywords
        target_predicates = set()
        for k in keywords:
            if k in predicate_map:
                target_predicates.add(predicate_map[k])

        scored_results = []

        for c in self.graph.get("claims", []):
            score = 0
            
            # 1. Predicate Match (High Boost)
            if c["predicate"] in target_predicates:
                score += 5
            
            # 2. Keyword Matches in metadata/evidence
            subj = c["subject_entity_id"]
            obj = c["object_entity_id"]
            subj_name = self.entity_map.get(subj, {}).get("name", "").lower()
            obj_name = self.entity_map.get(obj, {}).get("name", "").lower() if obj else ""
            predicate = c["predicate"].lower()
            
            evidence_text = " ".join([ev.get("excerpt", "").lower() for ev in c.get("evidence", [])])
            
            # Check keywords against all text fields
            searchable_blob = f"{subj_name} {obj_name} {predicate} {evidence_text}"
            
            for k in keywords:
                if k in searchable_blob:
                    score += 2
                    
            if score > 0:
                scored_results.append((score, c))

        # Sort by score descending
        scored_results.sort(key=lambda x: x[0], reverse=True)
        
        return [item[1] for item in scored_results]
if __name__ == "__main__":
    retrieval = RetrievalService()
    print(f"Retrieval engine online. Loaded {len(retrieval.graph['entities'])} potential memories.")
    
    # Test Normalization
    for variant in ["@BaseInfinity", "person_baseinfinity", "BaseInfinity"]:
        pack = retrieval.get_context_pack(variant)
        print(f"Pack for '{variant}': {len(pack['claims'])} facts found.")
    
    # Test Alias Search
    results = retrieval.search_entities("Boostrix")
    print(f"Search 'Boostrix' (alias test): {[e['id'] for e in results]}")
