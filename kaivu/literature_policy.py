from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


LITERATURE_INGEST_MODES = {"auto", "autonomous", "guided", "review_gated"}
LITERATURE_TARGET_SCOPES = {"personal", "project", "group", "public"}
HIGH_LEVELS = {"high", "critical"}
LOW_CONFIDENCE_LEVELS = {"low", "very_low", "uncertain"}
REVIEW_ROLES = {"curator", "admin", "principal_investigator", "pi"}


@dataclass(frozen=True, slots=True)
class LiteratureIngestPolicy:
    mode: str
    target_scope: str
    write_target: str
    requires_confirmation: bool
    needs_review: bool
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def decide_literature_ingest_policy(
    *,
    source_type: str = "",
    title: str = "",
    target_scope: str = "project",
    user_mode: str = "auto",
    impact_level: str = "medium",
    conflict_level: str = "low",
    confidence: str = "medium",
    group_role: str = "",
) -> LiteratureIngestPolicy:
    """Choose whether a literature source should be ingested directly, digested, or gated.

    The default is intentionally autonomous for research momentum, but sources that can
    rewrite shared group knowledge, official reviews, or controversial claims move into
    a confirmation/proposal lane.
    """
    normalized_mode = _normalize(user_mode, allowed=LITERATURE_INGEST_MODES, fallback="auto")
    normalized_scope = _normalize(target_scope, allowed=LITERATURE_TARGET_SCOPES, fallback="project")
    normalized_impact = _normalize_level(impact_level, fallback="medium")
    normalized_conflict = _normalize_level(conflict_level, fallback="low")
    normalized_confidence = _normalize_level(confidence, fallback="medium")
    normalized_role = str(group_role or "").strip().lower()
    normalized_source_type = str(source_type or "").strip().lower()

    reasons: list[str] = []
    mode = "autonomous" if normalized_mode == "auto" else normalized_mode

    if normalized_mode == "auto":
        reasons.append("default autonomous ingest keeps literature intake compounding")

    shared_scope = normalized_scope in {"group", "public"}
    role_can_review = normalized_role in REVIEW_ROLES
    if shared_scope and not role_can_review:
        mode = "review_gated"
        reasons.append(f"{normalized_scope} scope requires curator/admin review")
    elif shared_scope and normalized_mode == "auto":
        mode = "guided"
        reasons.append(f"{normalized_scope} scope should expose digest before shared write")

    if normalized_impact in HIGH_LEVELS:
        if shared_scope:
            mode = "review_gated"
        elif mode == "autonomous":
            mode = "guided"
        reasons.append(f"{normalized_impact} impact source should be explicitly checked")

    if normalized_conflict in HIGH_LEVELS:
        if shared_scope:
            mode = "review_gated"
        elif mode == "autonomous":
            mode = "guided"
        reasons.append(f"{normalized_conflict} conflict source may change controversy/mechanism pages")

    needs_review = normalized_confidence in LOW_CONFIDENCE_LEVELS or normalized_conflict in HIGH_LEVELS
    if normalized_confidence in LOW_CONFIDENCE_LEVELS:
        if shared_scope:
            mode = "review_gated"
        elif mode == "autonomous":
            mode = "guided"
        reasons.append(f"{normalized_confidence} confidence source should not silently update synthesis")

    if normalized_mode == "guided" and mode != "review_gated":
        reasons.append("caller requested guided ingest")
    if normalized_mode == "review_gated":
        reasons.append("caller requested review-gated ingest")
    if normalized_source_type in {"web", "article"} and normalized_confidence == "medium":
        needs_review = True
        reasons.append("web/article sources are provisional unless independently corroborated")

    if not reasons:
        reasons.append("no risk signals detected")

    write_target = {
        "autonomous": "raw_source",
        "guided": "digest_draft",
        "review_gated": "ingest_proposal",
    }.get(mode, "digest_draft")
    return LiteratureIngestPolicy(
        mode=mode,
        target_scope=normalized_scope,
        write_target=write_target,
        requires_confirmation=mode in {"guided", "review_gated"},
        needs_review=needs_review or mode in {"guided", "review_gated"},
        reasons=list(dict.fromkeys(reasons)),
    )


def render_literature_ingest_digest(
    *,
    title: str,
    source_type: str,
    content: str,
    policy: LiteratureIngestPolicy,
) -> str:
    excerpt = str(content).strip().replace("\r\n", "\n")
    if len(excerpt) > 4000:
        excerpt = excerpt[:4000].rstrip() + "\n\n[truncated for digest]"
    return "\n".join(
        [
            f"# Literature Ingest Digest: {title}",
            "",
            "## Policy",
            "",
            f"- Mode: {policy.mode}",
            f"- Target scope: {policy.target_scope}",
            f"- Write target: {policy.write_target}",
            f"- Requires confirmation: {str(policy.requires_confirmation).lower()}",
            f"- Needs review: {str(policy.needs_review).lower()}",
            *[f"- Reason: {reason}" for reason in policy.reasons],
            "",
            "## Curator Checklist",
            "",
            "- Confirm whether this source should update paper/concept/mechanism/controversy pages.",
            "- Mark any claims that should remain provisional.",
            "- Identify conflicts with existing review records before promotion.",
            "",
            "## Source",
            "",
            f"- Source type: {source_type}",
            "",
            "## Content Excerpt",
            "",
            excerpt,
            "",
        ]
    )


def _normalize(value: str, *, allowed: set[str], fallback: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    return normalized if normalized in allowed else fallback


def _normalize_level(value: str, *, fallback: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "very low": "very_low",
        "very-low": "very_low",
        "med": "medium",
        "normal": "medium",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in {"very_low", "low", "medium", "high", "critical"} else fallback


