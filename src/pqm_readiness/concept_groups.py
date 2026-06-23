"""HNDL-relevant OpenAlex concept groups for stratified sampling."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConceptGroup:
    name: str
    openalex_id: str
    label: str


HNDL_CONCEPT_GROUPS: tuple[ConceptGroup, ...] = (
    ConceptGroup("cybersecurity", "C38652104", "Computer security"),
    ConceptGroup("cryptography", "C178489894", "Cryptography"),
    ConceptGroup("quantum_computing", "C58053490", "Quantum computer"),
    ConceptGroup("aerospace", "C146978453", "Aerospace engineering"),
    ConceptGroup("telecommunications", "C76155785", "Telecommunications"),
    ConceptGroup("artificial_intelligence", "C154945302", "Artificial intelligence"),
    ConceptGroup("semiconductors", "C108225325", "Semiconductor"),
    ConceptGroup("control_systems", "C133731056", "Control engineering"),
)

CONCEPT_GROUP_BY_NAME = {group.name: group for group in HNDL_CONCEPT_GROUPS}


def resolve_concept_groups(names: list[str] | None = None) -> list[ConceptGroup]:
    if not names:
        return list(HNDL_CONCEPT_GROUPS)
    missing = [name for name in names if name not in CONCEPT_GROUP_BY_NAME]
    if missing:
        available = ", ".join(CONCEPT_GROUP_BY_NAME)
        raise ValueError(f"Unknown concept groups {missing}. Available: {available}")
    return [CONCEPT_GROUP_BY_NAME[name] for name in names]
