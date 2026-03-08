import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# We will use a highly conversational repo like AutoGPT for natural entity extraction
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_OWNER = "Significant-Gravitas"
REPO_NAME = "AutoGPT"
ISSUES_TO_FETCH = 5 # Small number for demonstration/prototyping

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'raw')

def fetch_issue(issue_number: int):
    headers = {
        "Accept": "application/vnd.github.v3+json",
        **({"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {})
    }
    
    # Fetch Issue
    issue_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues/{issue_number}"
    issue_resp = requests.get(issue_url, headers=headers)
    if issue_resp.status_code != 200:
        print(f"Failed to fetch issue {issue_number}: {issue_resp.status_code}")
        return None
        
    issue_data = issue_resp.json()
    
    # Fetch Comments
    comments_url = issue_data['comments_url']
    comments_resp = requests.get(comments_url, headers=headers)
    comments_data = comments_resp.json() if comments_resp.status_code == 200 else []
    
    return {
        "issue": issue_data,
        "comments": comments_data
    }

def process_into_artifacts(raw_data):
    """
    Convert raw GitHub JSON into our base 'Artifact' shape before LLM extraction.
    """
    artifacts = []
    issue = raw_data['issue']
    
    # Issue Body Artifact
    artifacts.append({
        "id": f"issue_{issue['number']}",
        "url": issue['html_url'],
        "type": "GitHubIssue",
        "content": f"Title: {issue['title']}\n\n{issue['body'] or ''}",
        "author_id": f"@{issue['user']['login']}",
        "created_at": issue['created_at']
    })
    
    # Comment Artifacts
    for comment in raw_data['comments']:
        artifacts.append({
            "id": f"comment_{comment['id']}",
            "url": comment['html_url'],
            "type": "GitHubComment",
            "content": comment['body'],
            "author_id": f"@{comment['user']['login']}",
            "created_at": comment['created_at']
        })
        
    return artifacts

def ingest_data():
    os.makedirs(DATA_DIR, exist_ok=True)
    
    print(f"Fetching issues from {REPO_OWNER}/{REPO_NAME}...")
    # For demonstration, we'll grab specific known AutoGPT issues with good discussion
    target_issues = [4130, 4128, 4122]
    
    all_artifacts = []
    
    for i in target_issues:
        print(f"Fetching Issue #{i}...")
        raw = fetch_issue(i)
        if raw:
            artifacts = process_into_artifacts(raw)
            all_artifacts.extend(artifacts)
            
    output_path = os.path.join(DATA_DIR, "artifacts.json")
    with open(output_path, 'w') as f:
        json.dump(all_artifacts, f, indent=2)
        
    print(f"Ingested {len(all_artifacts)} artifacts into {output_path}")

if __name__ == "__main__":
    ingest_data()
