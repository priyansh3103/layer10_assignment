import os
import json
import re
import uuid
import time
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from schema.ontology import ExtractionPayload, Entity, Claim, Evidence

from dotenv import load_dotenv
load_dotenv()

from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

MODEL = "llama-3.1-8b-instant"

MAX_CHARS = 800
MAX_RETRIES = 3

PRONOUNS = {"i","you","they","them","someone","we","he","she"}

USELESS_ENTITIES = {
    "people",
    "evening",
    "variable",
    "solution",
    "error"
}

ALLOWED_TYPES = {"Person","Issue","Component","Repository","Tool","File"}

ALLOWED_PREDICATES = {
    "authored",
    "assigned_to",
    "proposes_feature",
    "reports_issue",
    "suggests_change",
    "removes_configuration",
    "updates_component",
    "depends_on",
    "fixes_issue"
}

SYSTEM_PROMPT = """
Extract software knowledge.

Return JSON only.

Format:

{
 "entities":[{"name":"string","type":"Person|Issue|Component|Repository|Tool|File"}],
 "claims":[
   {
     "subject":"entity name",
     "predicate":"predicate",
     "object":"entity name or null",
     "excerpt":"direct quote"
   }
 ]
}

Allowed predicates:

authored
assigned_to
proposes_feature
reports_issue
suggests_change
removes_configuration
updates_component
depends_on
fixes_issue
"""


def normalize_name(name):

    if not name:
        return None

    name = name.lower().strip()

    name = name.replace("@","")

    return name


def make_entity_id(name):

    return re.sub(r"[^a-z0-9_]", "_", name.lower())


def repair_json(text):

    if not text:
        return None

    text = text.replace("```json","").replace("```","")

    start = text.find("{")

    if start == -1:
        return None

    text = text[start:]

    open_braces = text.count("{")
    close_braces = text.count("}")

    if close_braces < open_braces:
        text += "}"*(open_braces-close_braces)

    try:
        return json.loads(text)
    except:
        return None


def call_llm(prompt):

    for attempt in range(MAX_RETRIES):

        try:

            r = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role":"system","content":SYSTEM_PROMPT},
                    {"role":"user","content":prompt}
                ],
                temperature=0
            )

            return r.choices[0].message.content

        except Exception as e:

            print("Retrying:",e)

            time.sleep(2**attempt)

    return None


def clean_text(text):

    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)

    return " ".join(text.split())


def extract_entities(raw_entities):

    entities = {}

    for e in raw_entities:

        name = normalize_name(e.get("name"))

        if not name:
            continue

        # remove pronouns
        if name in PRONOUNS:
            continue

        # remove sentence-like garbage entities
        if len(name.split()) > 5:
            continue

        etype = e.get("type")

        if etype not in ALLOWED_TYPES:
            continue

        eid = make_entity_id(name)

        entities[eid] = Entity(
            id=eid,
            name=name,
            type=etype,
            aliases=[]
        )

    return entities


def extract_claims(raw_claims, entities, artifact):

    claims = []

    for c in raw_claims:

        subj = normalize_name(c.get("subject"))

        if not subj:
            continue

        pred = c.get("predicate")

        if pred not in ALLOWED_PREDICATES:
            continue

        obj = normalize_name(c.get("object"))

        subj_id = make_entity_id(subj)

        if subj_id not in entities:
            continue

        obj_id = None

        if obj and obj != "null":

            obj_id = make_entity_id(obj)

            if obj_id not in entities:
                obj_id = None

        excerpt = c.get("excerpt")

        if not excerpt or len(excerpt) < 10:
            continue

        start = artifact["content"].find(excerpt)

        if start == -1:
            continue

        evidence = Evidence(
            id=str(uuid.uuid4()),
            artifact_id=artifact["id"],
            excerpt=excerpt,
            char_start=start,
            char_end=start+len(excerpt)
        )

        claim = Claim(
            id=str(uuid.uuid4()),
            subject_entity_id=subj_id,
            predicate=pred,
            object_entity_id=obj_id,
            valid_from=artifact["created_at"],
            valid_to=None,
            confidence=0.8,
            evidence=[evidence]
        )

        claims.append(claim)

    return claims


def filter_useless_entities(entities, claims):

    used = set()

    for c in claims:
        used.add(c.subject_entity_id)
        if c.object_entity_id:
            used.add(c.object_entity_id)

    filtered = []

    for e in entities:

        if e.name in USELESS_ENTITIES and e.id not in used:
            continue

        filtered.append(e)

    return filtered


def extract_from_artifact(artifact):

    text = clean_text(artifact["content"])[:MAX_CHARS]

    prompt = f"""
TEXT:

{text}

Extract entities and claims.
"""

    raw = call_llm(prompt)

    data = repair_json(raw)

    if not data:

        print("JSON parse failed")

        return None

    entities = extract_entities(data.get("entities",[]))

    claims = extract_claims(data.get("claims",[]), entities, artifact)

    entity_list = list(entities.values())

    entity_list = filter_useless_entities(entity_list, claims)

    return ExtractionPayload(
        entities=entity_list,
        claims=claims[:4]
    )


def run_pipeline():

    DATA_DIR = os.path.join(os.path.dirname(__file__), "..","..","data")

    raw_path = os.path.join(DATA_DIR,"raw","artifacts.json")

    out_path = os.path.join(DATA_DIR,"extracted","payloads.json")

    with open(raw_path) as f:
        artifacts = json.load(f)

    results = []

    for art in artifacts:

        author = art.get("author_id","").lower()

        if "[bot]" in author:
            continue

        print("Processing",art["id"])

        payload = extract_from_artifact(art)

        if payload:

            results.append({
                "artifact_id":art["id"],
                "extracted":payload.model_dump()
            })

            with open(out_path,"w") as f:
                json.dump(results,f,indent=2)

        time.sleep(1)

    print("Extraction finished")


if __name__ == "__main__":

    run_pipeline()