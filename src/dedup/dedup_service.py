import os
import json
from typing import Dict
from datetime import datetime
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from schema.ontology import Entity, Claim


STOP_ENTITIES = {
    "this","that","the","it","something","anything",
    "someone","everyone","people","thing","me","you","we",
    "before","after","here","there"
}


class DedupService:

    def __init__(self):

        self.canonical_entities: Dict[str, Entity] = {}
        self.canonical_claims: Dict[str, Claim] = {}

        # audit logs
        self.audit_log = {
            "entity_merges": [],
            "claim_merges": []
        }


    def _normalize_entity_id(self, x: str):

        if not x:
            return None

        x = x.lower()
        x = x.replace("@", "")
        x = x.replace("person_", "")
        x = x.strip()

        if x in STOP_ENTITIES:
            return None

        return x


    def canonicalize_entity(self, new_entity: Entity):

        norm_id = self._normalize_entity_id(new_entity.id)

        if not norm_id:
            return None

        new_entity.id = norm_id

        if norm_id in self.canonical_entities:

            existing = self.canonical_entities[norm_id]

            # merge aliases
            for alias in new_entity.aliases:
                if alias not in existing.aliases:
                    existing.aliases.append(alias)

            # audit merge
            self.audit_log["entity_merges"].append({
                "timestamp": datetime.utcnow().isoformat(),
                "source": new_entity.name,
                "target": existing.name
            })

            return existing

        self.canonical_entities[norm_id] = new_entity
        return new_entity


    def add_claim(self, new_claim: Claim):

        subj = self._normalize_entity_id(new_claim.subject_entity_id)
        obj = self._normalize_entity_id(new_claim.object_entity_id)

        if not subj:
            return

        if subj not in self.canonical_entities:
            return

        new_claim.subject_entity_id = subj
        new_claim.object_entity_id = obj

        key_obj = obj if obj else "null"

        key = f"{subj}|{new_claim.predicate.lower()}|{key_obj}"

        if key in self.canonical_claims:

            existing = self.canonical_claims[key]

            existing_pairs = {(e.artifact_id, e.excerpt) for e in existing.evidence}

            for ev in new_claim.evidence:

                pair = (ev.artifact_id, ev.excerpt)

                if pair not in existing_pairs:
                    existing.evidence.append(ev)

            evidence_count = len(existing.evidence)

            existing.confidence = min(
                1.0,
                0.6 + 0.1 * evidence_count
            )

            self.audit_log["claim_merges"].append({
                "timestamp": datetime.utcnow().isoformat(),
                "key": key
            })

        else:

            # conflict detection
            for existing_key, existing_claim in list(self.canonical_claims.items()):

                if existing_claim.subject_entity_id == subj \
                and existing_claim.predicate == new_claim.predicate \
                and existing_claim.object_entity_id != obj:

                    try:
                        existing_time = datetime.fromisoformat(existing_claim.valid_from.replace("Z",""))
                        new_time = datetime.fromisoformat(new_claim.valid_from.replace("Z",""))

                        if new_time > existing_time:
                            existing_claim.valid_to = new_claim.valid_from

                    except Exception:
                        pass

            self.canonical_claims[key] = new_claim


def process_all_data():

    DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data')

    payloads_path = os.path.join(DATA_DIR, 'extracted', 'payloads.json')
    thread_payloads_path = os.path.join(DATA_DIR, 'extracted', 'thread_payloads.json')
    raw_artifacts_path = os.path.join(DATA_DIR, 'raw', 'artifacts.json')

    output_path = os.path.join(DATA_DIR, 'processed', 'memory_graph.json')

    # Build thread_id -> created_at from raw artifacts (issue = thread root)
    thread_created_at = {}
    if os.path.exists(raw_artifacts_path):
        with open(raw_artifacts_path) as f:
            for art in json.load(f):
                if art.get("id", "").startswith("issue_"):
                    thread_created_at[art["id"]] = art.get("created_at", "2020-01-01T00:00:00Z")

    service = DedupService()

    all_data = []

    if os.path.exists(payloads_path):
        with open(payloads_path) as f:
            all_data.extend(json.load(f))

    if os.path.exists(thread_payloads_path):
        with open(thread_payloads_path) as f:
            all_data.extend(json.load(f))


    print("Pass 1: Processing entities")

    for item in all_data:

        extracted = item.get("extracted", {})

        for e in extracted.get("entities", []):

            try:
                service.canonicalize_entity(Entity(**e))
            except Exception as err:
                print("Entity error:", err)


    print("Pass 2: Processing claims")

    for item in all_data:

        extracted = item.get("extracted", {})

        for c in extracted.get("claims", []):

            try:
                if "thread_id" in item:
                    # Thread-level claim: convert evidence_excerpt -> full Claim shape
                    thread_id = item["thread_id"]
                    excerpt = c.get("evidence_excerpt") or ""
                    if len(excerpt) < 10:
                        continue
                    full_claim = {
                        "id": c.get("id"),
                        "subject_entity_id": c.get("subject_entity_id"),
                        "predicate": c.get("predicate"),
                        "object_entity_id": c.get("object_entity_id"),
                        "valid_from": thread_created_at.get(thread_id, "2020-01-01T00:00:00Z"),
                        "valid_to": None,
                        "confidence": 0.8,
                        "evidence": [
                            {
                                "artifact_id": thread_id,
                                "excerpt": excerpt,
                                "char_start": None,
                                "char_end": None,
                            }
                        ],
                    }
                    service.add_claim(Claim(**full_claim))
                else:
                    # Artifact-level claim: already has valid_from and evidence
                    service.add_claim(Claim(**c))
            except Exception as err:
                print("Claim error:", err)


    graph = {
        "schema_version": "1.1",
        "generated_at": datetime.utcnow().isoformat(),
        "entities": [e.model_dump() for e in service.canonical_entities.values()],
        "claims": [c.model_dump() for c in service.canonical_claims.values()],
        "audit_log": service.audit_log
    }


    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(graph, f, indent=2)


    print("Dedup complete")
    print("Entities:", len(graph["entities"]))
    print("Claims:", len(graph["claims"]))
    print("Saved:", output_path)


if __name__ == "__main__":
    process_all_data()