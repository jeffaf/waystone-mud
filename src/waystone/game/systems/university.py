"""University system for Waystone MUD.

Handles:
- Arcanum ranks and progression (E'lir, Re'lar, El'the)
- Admission examinations
- Tuition calculation and payment
- Master reputation tracking
- University jobs
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

if TYPE_CHECKING:
    from waystone.database.models import Character

logger = structlog.get_logger(__name__)


class ArcanumRank(str, Enum):
    """Arcanum membership ranks."""

    NONE = "none"  # Not admitted
    E_LIR = "e_lir"  # First rank - "listener"
    RE_LAR = "re_lar"  # Second rank - "speaker"
    EL_THE = "el_the"  # Third rank - "seer"


RANK_ORDER = [ArcanumRank.NONE, ArcanumRank.E_LIR, ArcanumRank.RE_LAR, ArcanumRank.EL_THE]


def rank_to_display(rank: ArcanumRank) -> str:
    """Convert rank enum to display string."""
    return {
        ArcanumRank.NONE: "Non-Arcanum",
        ArcanumRank.E_LIR: "E'lir",
        ArcanumRank.RE_LAR: "Re'lar",
        ArcanumRank.EL_THE: "El'the",
    }.get(rank, "Unknown")


def rank_from_string(rank_str: str) -> ArcanumRank:
    """Convert string to ArcanumRank enum."""
    normalized = rank_str.lower().replace("'", "_").replace("-", "_")
    for rank in ArcanumRank:
        if rank.value == normalized or rank.name.lower() == normalized:
            return rank
    return ArcanumRank.NONE


@dataclass
class MasterReputation:
    """Tracks a player's reputation with a specific Master."""

    master_id: str
    reputation: int = 0  # -100 to +100
    interactions: int = 0

    def modify(self, amount: int) -> int:
        """Modify reputation, clamping to valid range."""
        self.reputation = max(-100, min(100, self.reputation + amount))
        self.interactions += 1
        return self.reputation


@dataclass
class UniversityStatus:
    """Complete University status for a character."""

    character_id: UUID
    arcanum_rank: ArcanumRank = ArcanumRank.NONE
    current_term: int = 0
    tuition_paid: bool = False
    tuition_amount: int = 0  # In jots
    master_reputations: dict[str, MasterReputation] = field(default_factory=dict)
    admission_score: int = 0  # Last admission exam score

    def get_reputation(self, master_id: str) -> int:
        """Get reputation with a specific master."""
        if master_id not in self.master_reputations:
            self.master_reputations[master_id] = MasterReputation(master_id=master_id)
        return self.master_reputations[master_id].reputation

    def modify_reputation(self, master_id: str, amount: int) -> int:
        """Modify reputation with a specific master."""
        if master_id not in self.master_reputations:
            self.master_reputations[master_id] = MasterReputation(master_id=master_id)
        return self.master_reputations[master_id].modify(amount)

    def total_reputation(self) -> int:
        """Get sum of all master reputations."""
        return sum(m.reputation for m in self.master_reputations.values())

    def average_reputation(self) -> float:
        """Get average reputation across all masters."""
        if not self.master_reputations:
            return 0.0
        return self.total_reputation() / len(self.master_reputations)


# Nine Masters and their domains
NINE_MASTERS = {
    "master_lorren": {"name": "Lorren", "title": "Chancellor", "domain": "Archives"},
    "master_kilvin": {"name": "Kilvin", "title": "Artificer", "domain": "Artificery"},
    "master_arwyl": {"name": "Arwyl", "title": "Physician", "domain": "Medica"},
    "elodin": {"name": "Elodin", "title": "Namer", "domain": "Naming"},
    "master_hemme": {"name": "Hemme", "title": "Rhetorician", "domain": "Sympathy"},
    "master_mandrag": {"name": "Mandrag", "title": "Alchemist", "domain": "Alchemy"},
    "master_elxa_dal": {"name": "Elxa Dal", "title": "Sympathist", "domain": "Sympathy"},
    "master_brandeur": {"name": "Brandeur", "title": "Rhetorician", "domain": "Rhetoric"},
    "master_herma": {"name": "Herma", "title": "Historian", "domain": "History"},
}


# Admission exam questions by category
# Keywords are checked as substrings - more keywords = more forgiving
ADMISSION_QUESTIONS = {
    "sympathy": [
        {
            "question": "What is the First Law of Sympathy?",
            "excellent": ["similarity", "like affects like", "similar things", "similars"],
            "good": ["connection", "linked", "related", "alike", "same"],
            "hint": "It relates to similarity between objects.",
        },
        {
            "question": "What is slippage in sympathy?",
            "excellent": ["energy loss", "inefficiency", "wasted energy", "lost energy"],
            "good": ["loss", "waste", "heat", "escape", "leak", "inefficient"],
            "hint": "It has to do with energy transfer.",
        },
        {
            "question": "What is the Alar?",
            "excellent": ["belief", "riding crop of mind", "mental discipline", "willpower"],
            "good": ["concentration", "focus", "will", "mind", "mental", "thought"],
            "hint": "It is a mental faculty essential for sympathy.",
        },
    ],
    "history": [
        {
            "question": "Who founded the University?",
            "excellent": ["teccam", "old masters"],
            "good": ["ancients", "founders", "wise", "scholars"],
            "hint": "There is a statue in the courtyard.",
        },
        {
            "question": "What is the Arcanum?",
            "excellent": ["arcane studies", "advanced magic", "higher learning", "arcane arts"],
            "good": ["magic", "school", "university", "sympathy", "arcanist", "naming"],
            "hint": "It is the magical branch of the University.",
        },
    ],
    "artificery": [
        {
            "question": "What is sygaldry?",
            "excellent": ["rune magic", "inscribed bindings", "permanent sympathy", "rune craft"],
            "good": ["runes", "symbols", "writing", "sigil", "inscrib", "engrav", "carv", "etch"],
            "hint": "It involves inscribing things onto objects.",
        },
        {
            "question": "What powers a sympathy lamp?",
            "excellent": ["heat absorption", "temperature differential", "thermal energy"],
            "good": ["heat", "fire", "warmth", "cold", "temperature", "thermal"],
            "hint": "It relates to temperature.",
        },
    ],
    "naming": [
        {
            "question": "What is the difference between knowing a name and calling it?",
            "excellent": ["calling invokes power", "knowing is understanding", "deep knowledge"],
            "good": ["power", "control", "understanding", "invoke", "command", "speak"],
            "hint": "One is knowledge, the other is action.",
        },
    ],
    "alchemy": [
        {
            "question": "What is the purpose of a retort in alchemy?",
            "excellent": ["distillation", "separating substances", "purification"],
            "good": ["mixing", "heating", "processing", "separate", "distill", "purif", "refin"],
            "hint": "It is used to separate things.",
        },
    ],
}


def get_random_questions(count: int = 5) -> list[dict[str, Any]]:
    """Get random admission questions from different categories."""
    import random

    all_questions: list[dict[str, Any]] = []
    for category, questions in ADMISSION_QUESTIONS.items():
        for q in questions:
            all_questions.append({**q, "category": category})

    random.shuffle(all_questions)
    return all_questions[:count]


def score_answer(question: dict[str, Any], answer: str) -> tuple[str, int]:
    """
    Score an answer to an admission question.

    Returns:
        Tuple of (rating, score) where rating is 'excellent', 'good', 'adequate', or 'poor'
    """
    answer_lower = answer.lower()

    # Check for excellent answers
    for keyword in question.get("excellent", []):
        if keyword.lower() in answer_lower:
            return ("excellent", 100)

    # Check for good answers
    for keyword in question.get("good", []):
        if keyword.lower() in answer_lower:
            return ("good", 70)

    # Check for adequate answers (at least some relevant content)
    if len(answer) > 10:
        return ("adequate", 40)

    return ("poor", 10)


def calculate_tuition(
    rank: ArcanumRank,
    admission_score: int,
    master_reputations: dict[str, MasterReputation],
    previous_term_score: int = 50,
) -> int:
    """
    Calculate tuition for a term.

    Base tuition is rank-based:
    - E'lir: 10 talents (1000 jots)
    - Re'lar: 20 talents (2000 jots)
    - El'the: 30 talents (3000 jots)

    Modifiers:
    - Admission score: -50% to +200%
    - Master reputations: -30% to +30% total
    - Previous term performance: -20% to +20%

    Returns:
        Tuition amount in jots
    """
    # Base tuition by rank
    base_tuition = {
        ArcanumRank.NONE: 500,  # First admission
        ArcanumRank.E_LIR: 1000,
        ArcanumRank.RE_LAR: 2000,
        ArcanumRank.EL_THE: 3000,
    }.get(rank, 1000)

    # Admission score modifier (-50% to +200%)
    # Score 100 = -50%, Score 50 = +100%, Score 0 = +200%
    admission_modifier = 2.5 - (admission_score / 50)
    admission_modifier = max(0.5, min(3.0, admission_modifier))

    # Master reputation modifier (-30% to +30%)
    total_rep = sum(m.reputation for m in master_reputations.values())
    avg_rep = total_rep / max(1, len(master_reputations))
    # avg_rep -100 = +30%, avg_rep 0 = 0%, avg_rep +100 = -30%
    rep_modifier = 1.0 - (avg_rep / 333.33)
    rep_modifier = max(0.7, min(1.3, rep_modifier))

    # Previous term modifier (-20% to +20%)
    # Score 100 = -20%, Score 50 = 0%, Score 0 = +20%
    term_modifier = 1.0 + ((50 - previous_term_score) / 250)
    term_modifier = max(0.8, min(1.2, term_modifier))

    # Calculate final tuition
    final_tuition = base_tuition * admission_modifier * rep_modifier * term_modifier

    # Round to nearest 10 jots
    final_tuition = int(round(final_tuition / 10) * 10)

    # Minimum 0, no maximum (rejection is signaled by very high amount)
    return max(0, final_tuition)


def can_access_room(rank: ArcanumRank, room_requires: str | None) -> bool:
    """Check if a rank can access a room with rank requirements."""
    if not room_requires:
        return True

    required_rank = rank_from_string(room_requires)
    current_idx = RANK_ORDER.index(rank)
    required_idx = RANK_ORDER.index(required_rank)

    return current_idx >= required_idx


def can_promote(character: "Character", current_rank: ArcanumRank) -> tuple[bool, str]:
    """
    Check if a character can be promoted to the next rank.

    Requirements vary by rank:
    - To E'lir: Pass admission exam
    - To Re'lar: Be E'lir, have 3+ terms, avg rep > 0, sympathy skill > 30
    - To El'the: Be Re'lar, have 6+ terms, avg rep > 20, sympathy skill > 60

    Returns:
        Tuple of (can_promote, reason)
    """
    if current_rank == ArcanumRank.EL_THE:
        return (False, "Already at highest rank.")

    # For now, just check if they've paid tuition
    # More complex requirements would check term count, skills, etc.
    return (True, "Eligible for promotion.")


def load_university_status(character: "Character") -> UniversityStatus:
    """Load university status from a Character model."""
    status = UniversityStatus(character_id=character.id)

    # Load rank from character
    status.arcanum_rank = rank_from_string(character.arcanum_rank)

    # Load other data from JSON field
    data = character.university_data or {}
    status.current_term = data.get("current_term", 0)
    status.tuition_paid = data.get("tuition_paid", False)
    status.tuition_amount = data.get("tuition_amount", 0)
    status.admission_score = data.get("admission_score", 0)

    # Load master reputations
    for master_id, rep_data in data.get("master_reputations", {}).items():
        status.master_reputations[master_id] = MasterReputation(
            master_id=master_id,
            reputation=rep_data.get("reputation", 0),
            interactions=rep_data.get("interactions", 0),
        )

    return status


def save_university_status(character: "Character", status: UniversityStatus) -> None:
    """Save university status to a Character model."""
    from sqlalchemy.orm.attributes import flag_modified

    # Save rank
    character.arcanum_rank = status.arcanum_rank.value

    # Save other data to JSON field
    character.university_data = {
        "current_term": status.current_term,
        "tuition_paid": status.tuition_paid,
        "tuition_amount": status.tuition_amount,
        "admission_score": status.admission_score,
        "master_reputations": {
            master_id: {
                "reputation": rep.reputation,
                "interactions": rep.interactions,
            }
            for master_id, rep in status.master_reputations.items()
        },
    }

    # Flag JSON as modified so SQLAlchemy tracks the change
    flag_modified(character, "university_data")


# Legacy cache for backward compatibility during transition
_university_status_cache: dict[UUID, UniversityStatus] = {}


def get_university_status(character_id: UUID) -> UniversityStatus:
    """Get or create university status for a character (legacy cache method)."""
    if character_id not in _university_status_cache:
        _university_status_cache[character_id] = UniversityStatus(character_id=character_id)
    return _university_status_cache[character_id]


def clear_university_cache() -> None:
    """Clear the university status cache (for testing)."""
    _university_status_cache.clear()
