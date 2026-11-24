"""Provider-neutral boundary for a future RAG/LLM attachment.

Providers run server-side. Retrieval must enforce scope, and responses must cite
stable evidence IDs. Source text is untrusted data, never system instructions.
"""
from dataclasses import asdict, dataclass
from typing import Protocol


@dataclass(frozen=True)
class Evidence:
    id: str
    tool: str
    team: str | None
    text: str
    filename: str
    page: int
    reviewed: bool


class AssistantProvider(Protocol):
    def answer(self, *, question: str, evidence: list[dict]) -> dict:
        """Retrieve/rerank supplied evidence and return {answer, citations: [id]}.

        A provider can attach embeddings, a vector database and an LLM here.
        Do not retrieve outside the supplied authorized evidence scope.
        """
        ...


def corpus(workspace, tool, team=None):
    for document in workspace.snapshot()['documents']:
        for page in document['pages']:
            if team and page.get('team') != team:
                continue
            for index, comment in enumerate(page['comments']):
                if comment.get('text', '').strip():
                    yield asdict(Evidence(
                        id=f"{tool}:{document['id']}:{page['number']}:{index}",
                        tool=tool, team=page.get('team'), text=comment['text'],
                        filename=document['filename'], page=page['number'],
                        reviewed=bool(page.get('verified'))))
