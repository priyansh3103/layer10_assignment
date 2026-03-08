from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Union
from datetime import datetime
from uuid import uuid4

# ---------------------------------------------------------
# Core Graph Ontology Data Models
# ---------------------------------------------------------

class Entity(BaseModel):
    """
    A canonical real-world object (Person, Issue, Component, Repository, Package, API).
    """
    id: str = Field(description="A unique, natural identifier for the entity (e.g., 'React DOM', '@gnoff', '#28271', etc.).")
    type: Literal["Person", "Issue", "Component", "Repository", "Tool", "File"]
    name: str = Field(description="Primary display name for the entity.")
    aliases: List[str] = Field(default_factory=list, description="Other names or handles this entity might go by.")

class Artifact(BaseModel):
    """
    A source document from which facts are extracted.
    """
    id: str = Field(description="Unique ID for this source document (e.g., 'github_issue_456', 'slack_msg_789').")
    url: Optional[str] = Field(default=None, description="URL back to the original source.")
    type: Literal["GitHubIssue", "GitHubComment", "Email", "SlackMessage"]
    content: str = Field(description="The full raw text of the document.")
    author_id: str = Field(description="The Entity ID of the Person who authored this artifact.")
    created_at: str = Field(description="ISO-8601 timestamp of when this artifact was created.")

class Evidence(BaseModel):
    """
    Grounding pointer tying a claim to a specific span in an artifact.
    """
    id: str = Field(default_factory=lambda: f"ev_{uuid4().hex[:8]}", description="Unique ID for this evidence node.")
    artifact_id: str = Field(description="The ID of the Artifact this evidence comes from.")
    excerpt: str = Field(description="The exact text quote supporting the claim.")
    char_start: Optional[int] = Field(default=None, description="Start index of excerpt in artifact.")
    char_end: Optional[int] = Field(default=None, description="End index of excerpt in artifact.")

class Claim(BaseModel):
    """
    A first-class fact extracted from an artifact.
    Forms the core of the Memory Graph.
    """
    id: str = Field(default_factory=lambda: f"claim_{uuid4().hex[:8]}", description="Unique identifier for the claim.")
    subject_entity_id: str = Field(description="Entity ID of the subject (e.g., 'issue_123').")
    predicate: str = Field(description="The relationship type (e.g., 'assigned_to', 'blocks', 'depends_on', 'mentioned', 'resolved_by').")
    object_entity_id: Optional[str] = Field(default=None, description="Entity ID of the object (e.g., 'person_alice').")
    
    # Time awareness
    valid_from: str = Field(description="ISO-8601 timestamp when this fact became true (usually derived from Artifact.created_at).")
    valid_to: Optional[str] = Field(default=None, description="ISO-8601 timestamp when this fact became false. Null if currently true.")
    
    confidence: float = Field(default=1.0, description="Confidence score from the extraction (0.0 to 1.0).")
    
    # Grounding
    evidence: List[Evidence] = Field(default_factory=list, description="List of evidence supporting this claim.")

# ---------------------------------------------------------
# Extraction Payload Types (What the LLM targets)
# ---------------------------------------------------------

class ExtractionPayload(BaseModel):
    """
    The strict schema the LLM must return when analyzing an artifact.
    """
    entities: List[Entity] = Field(description="All distinct entities mentioned or participating in the text.")
    claims: List[Claim] = Field(description="The factual claims explicitly stated in the text.")
