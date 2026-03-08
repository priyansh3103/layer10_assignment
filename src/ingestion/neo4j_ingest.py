import json
import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

DATA_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'processed', 'memory_graph.json')

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
            # 1. Clear existing data
            session.run("MATCH (n) DETACH DELETE n")
            
            # 2. Ingest Explicit Entities
            print(f"Ingesting {len(graph['entities'])} explicit entities...")
            for ent in graph['entities']:
                session.run("""
                    MERGE (e:Entity {id: $id})
                    SET e.name = $name,
                        e.type = $type,
                        e.aliases = $aliases
                """, id=ent['id'], name=ent['name'], type=ent['type'], aliases=ent.get('aliases', []))

            # 3. Ingest Claims (with implicit entity creation to prevent data loss)
            print(f"Ingesting {len(graph['claims'])} claims...")
            for claim in graph['claims']:
                # Subject node
                session.run("MERGE (e:Entity {id: $id})", id=claim['subject_entity_id'])
                
                # Object node (optional)
                if claim['object_entity_id']:
                    session.run("MERGE (e:Entity {id: $id})", id=claim['object_entity_id'])
                
                # Claim node
                obj_id = claim['object_entity_id'] or "null"
                claim_node_id = f"claim_{claim['subject_entity_id']}_{claim['predicate']}_{obj_id}"
                
                if claim['object_entity_id']:
                    session.run("""
                        MATCH (s:Entity {id: $s_id})
                        MATCH (o:Entity {id: $o_id})
                        MERGE (c:Claim {id: $c_id})
                        SET c.predicate = $pred,
                            c.confidence = $conf,
                            c.valid_from = $v_from
                        MERGE (s)-[:HAS_FACT]->(c)
                        MERGE (c)-[:TARGETS]->(o)
                    """, s_id=claim['subject_entity_id'], 
                         o_id=claim['object_entity_id'], 
                         c_id=claim_node_id, 
                         pred=claim['predicate'],
                         conf=claim.get('confidence', 1.0),
                         v_from=claim.get('valid_from'))
                else:
                    session.run("""
                        MATCH (s:Entity {id: $s_id})
                        MERGE (c:Claim {id: $c_id})
                        SET c.predicate = $pred,
                            c.confidence = $conf,
                            c.valid_from = $v_from
                        MERGE (s)-[:HAS_FACT]->(c)
                    """, s_id=claim['subject_entity_id'], 
                         c_id=claim_node_id, 
                         pred=claim['predicate'],
                         conf=claim.get('confidence', 1.0),
                         v_from=claim.get('valid_from'))

                # 4. Ingest Evidence (with global uniqueness)
                for idx, ev in enumerate(claim.get('evidence', [])):
                    raw_id = ev.get('id', f'ev_{idx}').replace(' ', '_')
                    unique_ev_id = f"{ev['artifact_id']}_{raw_id}"
                    
                    session.run("""
                        MATCH (c:Claim {id: $c_id})
                        MERGE (e:Evidence {id: $e_id})
                        SET e.artifact_id = $art_id,
                            e.excerpt = $excerpt
                        MERGE (c)-[:SUPPORTED_BY]->(e)
                    """, c_id=claim_node_id, e_id=unique_ev_id, art_id=ev['artifact_id'], excerpt=ev['excerpt'])

        print("Neo4j Ingestion Complete.")

if __name__ == "__main__":
    # Get credentials from env
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
    
    ingestor = Neo4jIngestor(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    try:
        ingestor.ingest()
    finally:
        ingestor.close()
