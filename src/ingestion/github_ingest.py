import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

REPO_OWNER = "Significant-Gravitas"
REPO_NAME = "AutoGPT"

# Increase data volume
ISSUE_RANGE = range(4100, 4150)

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'raw')
ARTIFACT_PATH = os.path.join(DATA_DIR, "artifacts.json")


def load_existing_artifacts():

    if not os.path.exists(ARTIFACT_PATH):
        return []

    with open(ARTIFACT_PATH) as f:
        return json.load(f)


def fetch_issue(issue_number):

    headers = {
        "Accept": "application/vnd.github.v3+json",
        **({"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {})
    }

    issue_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues/{issue_number}"

    issue_resp = requests.get(issue_url, headers=headers)

    if issue_resp.status_code != 200:
        print(f"Skipping issue {issue_number}")
        return None

    issue_data = issue_resp.json()

    comments_url = issue_data["comments_url"]

    comments_resp = requests.get(comments_url, headers=headers)

    comments_data = comments_resp.json() if comments_resp.status_code == 200 else []

    return {
        "issue": issue_data,
        "comments": comments_data
    }


def process_into_artifacts(raw_data):

    artifacts = []

    issue = raw_data["issue"]

    artifacts.append({
        "id": f"issue_{issue['number']}",
        "url": issue["html_url"],
        "type": "GitHubIssue",
        "content": f"Title: {issue['title']}\n\n{issue['body'] or ''}",
        "author_id": f"@{issue['user']['login']}",
        "created_at": issue["created_at"]
    })

    for comment in raw_data["comments"]:

        artifacts.append({
            "id": f"comment_{comment['id']}",
            "url": comment["html_url"],
            "type": "GitHubComment",
            "content": comment["body"],
            "author_id": f"@{comment['user']['login']}",
            "created_at": comment["created_at"]
        })

    return artifacts


def ingest_data():

    os.makedirs(DATA_DIR, exist_ok=True)

    existing_artifacts = load_existing_artifacts()

    existing_ids = {a["id"] for a in existing_artifacts}

    print(f"Existing artifacts: {len(existing_artifacts)}")

    new_artifacts = []

    for issue_number in ISSUE_RANGE:

        print(f"Fetching Issue #{issue_number}")

        raw = fetch_issue(issue_number)

        if not raw:
            continue

        artifacts = process_into_artifacts(raw)

        for a in artifacts:

            if a["id"] not in existing_ids:
                new_artifacts.append(a)

    merged = existing_artifacts + new_artifacts

    with open(ARTIFACT_PATH, "w") as f:
        json.dump(merged, f, indent=2)

    print(f"Added {len(new_artifacts)} new artifacts")
    print(f"Total artifacts: {len(merged)}")


if __name__ == "__main__":
    ingest_data()