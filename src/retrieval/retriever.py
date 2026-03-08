import json
import os
import numpy as np
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

GRAPH_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "data",
    "processed",
    "memory_graph.json",
)


class RetrievalService:

    def __init__(self):

        self.graph = {"entities": [], "claims": []}
        self.entity_map = {}

        self.model = None
        self.claim_embeddings = None
        self.claim_texts = []

        self.load_graph()
        self.build_embedding_index()

    # -------------------------------------------------------
    # Load graph
    # -------------------------------------------------------

    def load_graph(self):

        if os.path.exists(GRAPH_PATH):
            with open(GRAPH_PATH, "r") as f:
                self.graph = json.load(f)

        self.entity_map = {
            e["id"]: e for e in self.graph.get("entities", [])
        }

    # -------------------------------------------------------
    # Embedding Index
    # -------------------------------------------------------

    def build_embedding_index(self):

        claims = self.graph.get("claims", [])

        if not claims:
            return

        print("Building embedding index...")

        self.model = SentenceTransformer(
            "sentence-transformers/all-MiniLM-L6-v2"
        )

        texts = []

        for c in claims:

            subj = self.entity_map.get(
                c["subject_entity_id"], {}
            ).get("name", c["subject_entity_id"])

            obj = (
                self.entity_map.get(
                    c["object_entity_id"], {}
                ).get("name", c["object_entity_id"])
                if c["object_entity_id"]
                else ""
            )

            text = f"{subj} {c['predicate']} {obj}"
            texts.append(text)

        self.claim_texts = texts
        self.claim_embeddings = self.model.encode(texts)

        print(f"Indexed {len(texts)} claims.")

    # -------------------------------------------------------
    # Normalization
    # -------------------------------------------------------

    def normalize_entity_id(self, x: str):

        if not x:
            return None

        return (
            x.lower()
            .replace("@", "")
            .replace("person_", "")
            .strip()
        )

    # -------------------------------------------------------
    # Entity Search
    # -------------------------------------------------------

    def search_entities(self, text: str):

        text = text.lower()

        return [
            e
            for e in self.graph["entities"]
            if text in e["id"].lower()
            or text in e["name"].lower()
            or text
            in " ".join(e.get("aliases", [])).lower()
        ]

    # -------------------------------------------------------
    # Predicate Mapping
    # -------------------------------------------------------

    def map_predicates(self, keywords):

        predicate_map = {

            # assignment
            "assign": "assigned_to",
            "assigned": "assigned_to",
            "owner": "assigned_to",

            # fixes
            "fix": "fixes_issue",
            "fixed": "fixes_issue",
            "resolve": "fixes_issue",
            "resolved": "fixes_issue",
            "repair": "fixes_issue",

            # issues
            "issue": "reports_issue",
            "report": "reports_issue",
            "reported": "reports_issue",
            "bug": "reports_issue",

            # suggestions
            "suggest": "suggests_change",
            "suggested": "suggests_change",
            "change": "suggests_change",
            "changes": "suggests_change",
            "improve": "suggests_change",
            "improvement": "suggests_change",

            # features
            "feature": "proposes_feature",
            "propose": "proposes_feature",
            "proposed": "proposes_feature",
            "add": "proposes_feature",

            # updates
            "update": "updates_component",
            "updated": "updates_component",
            "modify": "updates_component",
            "modified": "updates_component",

            # dependency
            "depend": "depends_on",
            "depends": "depends_on",
            "dependency": "depends_on",

            # authorship
            "author": "authored",
            "authored": "authored",
            "created": "authored",
        }

        preds = set()

        for k in keywords:
            if k in predicate_map:
                preds.add(predicate_map[k])

        return preds

    # -------------------------------------------------------
    # Query parsing
    # -------------------------------------------------------

    def parse_query(self, query):

        text = query.lower()

        for char in "?!.,:;":
            text = text.replace(char, "")

        tokens = text.split()

        stopwords = {
            "who",
            "what",
            "the",
            "a",
            "an",
            "is",
            "was",
            "were",
            "where",
            "how",
            "did",
            "does",
            "of",
            "in",
            "to",
        }

        keywords = [
            t for t in tokens if t not in stopwords and len(t) > 2
        ]

        return keywords

    # -------------------------------------------------------
    # Embedding search
    # -------------------------------------------------------

    def embedding_search(self, query):

        if self.claim_embeddings is None:
            return []

        query_vec = self.model.encode([query])

        scores = cosine_similarity(
            query_vec, self.claim_embeddings
        )[0]

        top_idx = np.argsort(scores)[::-1][:10]

        return [
            (scores[i], self.graph["claims"][i])
            for i in top_idx
        ]

    # -------------------------------------------------------
    # Claim search
    # -------------------------------------------------------

    def search_claims(self, query):

        keywords = self.parse_query(query)

        target_preds = self.map_predicates(keywords)

        embedding_hits = self.embedding_search(query)

        scored = []

        for c in self.graph["claims"]:

            score = 0

            subj = c["subject_entity_id"]
            obj = c["object_entity_id"]

            subj_name = self.entity_map.get(
                subj, {}
            ).get("name", "").lower()

            obj_name = (
                self.entity_map.get(
                    obj, {}
                ).get("name", "").lower()
                if obj
                else ""
            )

            predicate = c["predicate"].lower()

            evidence_text = " ".join(
                ev.get("excerpt", "").lower()
                for ev in c.get("evidence", [])
            )

            blob = f"{subj_name} {obj_name} {predicate} {evidence_text}"

            # strong entity boost
            if query.lower() in subj_name:
                score += 10

            if query.lower() in obj_name:
                score += 10

            # predicate boost
            if predicate in target_preds:
                score += 6

            # keyword matches
            for k in keywords:
                if k in blob:
                    score += 2

            # confidence bonus
            score += c.get("confidence", 0)

            if score > 0:
                scored.append((score, c))

        # include embedding hits
        for sim, claim in embedding_hits:
            scored.append((sim * 3, claim))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = []

        seen = set()

        for score, c in scored:

            cid = c["id"]

            if cid not in seen:
                results.append(c)
                seen.add(cid)

            if len(results) >= 10:
                break

        return results

    # -------------------------------------------------------
    # Context Pack
    # -------------------------------------------------------

    def get_context_pack(self, query):

        entity_hits = self.search_entities(query)

        claims = []
        fallback_used = False
        entity_name = None

        # If query matches entity
        if entity_hits:

            entity_id = entity_hits[0]["id"]
            entity_name = entity_hits[0]["name"]

            claims = [
                c for c in self.graph["claims"]
                if c["subject_entity_id"] == entity_id
                or c["object_entity_id"] == entity_id
            ]

            # If entity has no claims → fallback
            if not claims:
                fallback_used = True
                claims = self.search_claims(query)

        else:
            claims = self.search_claims(query)

        entity_ids = set()
        formatted_claims = []

        for c in claims:

            subj = c["subject_entity_id"]
            obj = c["object_entity_id"]

            subj_name = self.entity_map.get(subj, {}).get("name", subj)
            obj_name = self.entity_map.get(obj, {}).get("name", obj) if obj else None

            if obj_name:
                statement = f"{subj_name} {c['predicate']} {obj_name}"
            else:
                statement = f"{subj_name} {c['predicate']}"

            evidence = [
                {"artifact": ev["artifact_id"], "quote": ev["excerpt"]}
                for ev in c.get("evidence", [])
            ]

            entity_ids.add(subj)
            if obj:
                entity_ids.add(obj)

            formatted_claims.append({
                **c,
                "statement": statement,
                "evidence": evidence
            })

        related_entities = [
            e for e in self.graph["entities"] if e["id"] in entity_ids
        ]

        return {
            "entities": related_entities,
            "claims": formatted_claims,
            "fallback_used": fallback_used,
            "entity_name": entity_name
        }