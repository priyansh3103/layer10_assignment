import os
import json
import re
import time
import uuid
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..",".."))

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

MODEL = "llama-3.1-8b-instant"

MAX_CHARS = 2500

ALLOWED_TYPES = {
    "Person","Issue","Component","Repository","Tool","File"
}

ALLOWED_PREDICATES = {
    "authored",
    "assigned_to",
    "proposes_feature",
    "reports_issue",
    "suggests_change",
    "fixes_issue",
    "updates_component",
    "depends_on",
    "removes_configuration"
}

SYSTEM_PROMPT = """
You analyze entire GitHub engineering discussions.

Extract meaningful architectural decisions, issues, or engineering changes.

Return JSON only.

{
 "entities":[{"name":"string","type":"Person|Issue|Component|Repository|Tool|File"}],
 "claims":[
   {
     "subject_entity_id":"entity",
     "predicate":"predicate",
     "object_entity_id":"entity or null",
     "evidence_excerpt":"quote"
   }
 ]
}

Use ONLY these predicates:

authored
assigned_to
proposes_feature
reports_issue
suggests_change
fixes_issue
updates_component
depends_on
removes_configuration

Ignore links as entities.
"""


def normalize_name(name):

    if not name:
        return None

    name = name.strip().replace("@","").lower()

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

        print("LLM error:",e)
        return None


def build_threads(artifacts):

    threads = {}
    current_issue = None

    for art in artifacts:

        if art["id"].startswith("issue_"):
            current_issue = art["id"]
            threads[current_issue] = [art]

        elif art["id"].startswith("comment_") and current_issue:
            threads[current_issue].append(art)

    return threads


def clean_entities(raw_entities):

    entities = {}

    for e in raw_entities:

        name = e.get("name")

        if not name:
            continue

        if name.startswith("http"):
            continue

        etype = e.get("type")

        if etype not in ALLOWED_TYPES:
            continue

        if "PR #" in name:
            etype = "Issue"

        norm = normalize_name(name)

        eid = make_entity_id(norm)

        entities[eid] = {
            "id":eid,
            "name":norm,
            "type":etype,
            "aliases":[]
        }

    return entities


def clean_claims(raw_claims, entities):

    entity_ids = set(entities.keys())

    claims = []

    for c in raw_claims:

        subj = normalize_name(c.get("subject_entity_id"))
        pred = c.get("predicate")
        obj = normalize_name(c.get("object_entity_id"))
        excerpt = c.get("evidence_excerpt")

        if not subj or pred not in ALLOWED_PREDICATES:
            continue

        subj_id = make_entity_id(subj)

        if subj_id not in entity_ids:
            continue

        obj_id = None

        if obj:
            temp = make_entity_id(obj)
            if temp in entity_ids:
                obj_id = temp

        if not excerpt or len(excerpt) < 10:
            continue

        claims.append({
            "id":str(uuid.uuid4()),
            "subject_entity_id":subj_id,
            "predicate":pred,
            "object_entity_id":obj_id,
            "evidence_excerpt":excerpt
        })

    return claims


def expand_relationships(claims, entities):
    """
    Improvement: create additional relationships from
    entity co-occurrence inside evidence excerpts.
    """

    entity_names = {v["name"]:k for k,v in entities.items()}

    extra_claims = []

    for claim in claims:

        excerpt = claim["evidence_excerpt"].lower()

        mentioned = []

        for name,eid in entity_names.items():
            if name in excerpt:
                mentioned.append(eid)

        for i in range(len(mentioned)):
            for j in range(i+1,len(mentioned)):

                extra_claims.append({
                    "id":str(uuid.uuid4()),
                    "subject_entity_id":mentioned[i],
                    "predicate":"depends_on",
                    "object_entity_id":mentioned[j],
                    "evidence_excerpt":excerpt
                })

    claims.extend(extra_claims)

    return claims


def run_thread_pipeline():

    DATA_DIR = os.path.join(os.path.dirname(__file__), "..","..","data")

    raw_path = os.path.join(DATA_DIR,"raw","artifacts.json")

    out_path = os.path.join(DATA_DIR,"extracted","thread_payloads.json")

    with open(raw_path) as f:
        artifacts = json.load(f)

    threads = build_threads(artifacts)

    results = []

    for issue_id,items in threads.items():

        combined = ""

        for a in items:
            combined += f"\nAUTHOR:{a.get('author_id')}\n{a.get('content')}\n"

        combined = re.sub(r'\s+',' ',combined)[:MAX_CHARS]

        prompt = f"""
THREAD DISCUSSION:

{combined}

Extract architectural knowledge.
"""

        raw = call_llm(prompt)

        data = repair_json(raw)

        if not data:
            print("Thread extraction failed:",issue_id)
            continue

        entities = clean_entities(data.get("entities",[]))

        claims = clean_claims(data.get("claims",[]), entities)

        # NEW IMPROVEMENT
        claims = expand_relationships(claims, entities)

        results.append({
            "thread_id":issue_id,
            "extracted":{
                "entities":list(entities.values()),
                "claims":claims
            }
        })

        with open(out_path,"w") as f:
            json.dump(results,f,indent=2)

        print("Thread processed:",issue_id)

        time.sleep(2)

    print("Thread extraction complete")


if __name__ == "__main__":
    run_thread_pipeline()