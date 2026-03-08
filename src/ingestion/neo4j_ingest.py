import json
import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

DATA_PATH = os.path.join(
    os.path.dirname(__file__),
    '..', '..', 'data', 'processed', 'memory_graph.json'
)


class Neo4jIngestor:

    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def ingest(self):

        if not os.path.exists(DATA_PATH):
            print(f"No graph data found at {DATA_PATH}")
            return

        with open(DATA_PATH, 'r') as f:
            graph = json.load(f)

        with self.driver.session() as session:

            print("Preparing database...")

            # Clear existing graph
            session.run("MATCH (n) DETACH DELETE n")

            # Create indexes for speed
            session.run("CREATE INDEX entity_id IF NOT EXISTS FOR (e:Entity) ON (e.id)")
            session.run("CREATE INDEX claim_id IF NOT EXISTS FOR (c:Claim) ON (c.id)")
            session.run("CREATE INDEX evidence_id IF NOT EXISTS FOR (e:Evidence) ON (e.id)")

            # -----------------------------
            # ENTITIES
            # -----------------------------

            print(f"Ingesting {len(graph['entities'])} entities...")

            for ent in graph["entities"]:

                session.run(
                    """
                    MERGE (e:Entity {id: $id})
                    SET e.name = $name,
                        e.type = $type,
                        e.aliases = $aliases
                    """,
                    id=ent["id"],
                    name=ent.get("name"),
                    type=ent.get("type"),
                    aliases=ent.get("aliases", [])
                )

            # -----------------------------
            # CLAIMS
            # -----------------------------

            print(f"Ingesting {len(graph['claims'])} claims...")

            for claim in graph["claims"]:

                subj_id = claim["subject_entity_id"]
                obj_id = claim.get("object_entity_id")

                predicate = claim["predicate"]

                claim_node_id = claim.get(
                    "id",
                    f"claim_{subj_id}_{predicate}_{obj_id or 'null'}"
                )

                # Ensure subject exists
                session.run(
                    "MERGE (:Entity {id: $id})",
                    id=subj_id
                )

                # Ensure object exists
                if obj_id:
                    session.run(
                        "MERGE (:Entity {id: $id})",
                        id=obj_id
                    )

                if obj_id:

                    session.run(
                        """
                        MATCH (s:Entity {id: $s_id})
                        MATCH (o:Entity {id: $o_id})

                        MERGE (c:Claim {id: $c_id})
                        SET c.predicate = $pred,
                            c.confidence = $conf,
                            c.valid_from = $v_from,
                            c.valid_to = $v_to

                        MERGE (s)-[:HAS_FACT]->(c)
                        MERGE (c)-[:TARGETS]->(o)
                        """,
                        s_id=subj_id,
                        o_id=obj_id,
                        c_id=claim_node_id,
                        pred=predicate,
                        conf=claim.get("confidence", 1.0),
                        v_from=claim.get("valid_from"),
                        v_to=claim.get("valid_to")
                    )

                else:

                    session.run(
                        """
                        MATCH (s:Entity {id: $s_id})

                        MERGE (c:Claim {id: $c_id})
                        SET c.predicate = $pred,
                            c.confidence = $conf,
                            c.valid_from = $v_from,
                            c.valid_to = $v_to

                        MERGE (s)-[:HAS_FACT]->(c)
                        """,
                        s_id=subj_id,
                        c_id=claim_node_id,
                        pred=predicate,
                        conf=claim.get("confidence", 1.0),
                        v_from=claim.get("valid_from"),
                        v_to=claim.get("valid_to")
                    )

                # -----------------------------
                # EVIDENCE
                # -----------------------------

                for idx, ev in enumerate(claim.get("evidence", [])):

                    raw_id = ev.get("id", f"ev_{idx}")
                    raw_id = raw_id.replace(" ", "_")

                    evidence_id = f"{ev['artifact_id']}_{raw_id}"

                    session.run(
                        """
                        MATCH (c:Claim {id: $c_id})

                        MERGE (e:Evidence {id: $e_id})
                        SET e.artifact_id = $artifact_id,
                            e.excerpt = $excerpt,
                            e.char_start = $start,
                            e.char_end = $end

                        MERGE (c)-[:SUPPORTED_BY]->(e)
                        """,
                        c_id=claim_node_id,
                        e_id=evidence_id,
                        artifact_id=ev["artifact_id"],
                        excerpt=ev.get("excerpt"),
                        start=ev.get("char_start"),
                        end=ev.get("char_end")
                    )

        print("Neo4j ingestion complete.")


if __name__ == "__main__":

    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

    ingestor = Neo4jIngestor(
        NEO4J_URI,
        NEO4J_USER,
        NEO4J_PASSWORD
    )

    try:
        ingestor.ingest()
    finally:
        ingestor.close()