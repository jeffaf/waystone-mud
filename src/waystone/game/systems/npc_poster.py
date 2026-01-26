"""NPC Poster System for Waystone MUD.

Handles scheduled NPC posts to bulletin boards with character-appropriate
writing styles and content from the Kingkiller Chronicle world.

Phase 4 Implementation - BBS System
"""

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# Template Variables for Message Generation
# =============================================================================

DAYS_OF_SPAN = [
    "Luten",
    "Shuden",
    "Theden",
    "Feochen",
    "Orden",
    "Hepten",
    "Chaen",
    "Felling",
    "Reaving",
    "Cendling",
    "Mourning",
]

MONTHS = [
    "Thaw",
    "Equis",
    "Caitelyn",
    "Solace",
    "Lannis",
    "Reaping",
    "Fallow",
    "Dearth",
]

ITEMS_LOST = [
    "shoes",
    "keys",
    "cloak",
    "favorite pen",
    "hat",
    "student's name",
    "the thread of conversation",
    "sense of time",
    "copy ofErta",
]

SUBJECTS_ACADEMIC = [
    "Advanced Sympathy",
    "Artificing Fundamentals",
    "Sygaldry",
    "Alchemy",
    "Medica Practice",
    "Naming",
    "Rhetoric",
    "History",
    "Arithmetic",
]

MASTERS = [
    "Hemme",
    "Brandeur",
    "Arwyl",
    "Lorren",
    "Kilvin",
    "Elxa Dal",
    "Mandrag",
    "Elodin",
]

PRICES_TALENTS = ["2", "3", "4", "5", "6", "8"]
PRICES_JOTS = ["4", "6", "8", "12"]

LOCATIONS_UNIVERSITY = [
    "the Mews",
    "Anker's",
    "the Medica",
    "the Archives",
    "the Artificery",
    "the lecture hall",
    "the courtyard",
]


def _get_template_variables() -> dict[str, Any]:
    """Generate random template variables for message generation."""
    return {
        "day": random.choice(DAYS_OF_SPAN),
        "month": random.choice(MONTHS),
        "item": random.choice(ITEMS_LOST),
        "subject": random.choice(SUBJECTS_ACADEMIC),
        "master": random.choice(MASTERS),
        "price_1": random.choice(PRICES_TALENTS),
        "price_2": random.choice(PRICES_JOTS),
        "location": random.choice(LOCATIONS_UNIVERSITY),
        "action": random.choice(["Cancelled", "Relocated", "Postponed"]),
        "status": random.choice(["cancelled", "postponed", "moved"]),
        "number": random.randint(2, 12),
        "time": random.choice(["morning", "afternoon", "evening", "night"]),
    }


# =============================================================================
# Core Data Structures
# =============================================================================


@dataclass
class NPCPostTemplate:
    """Template for NPC posts with subject/body patterns.

    Supports format string variables like {day}, {item}, {subject} that are
    filled in at generation time for variety.
    """

    subject_patterns: list[str]
    body_patterns: list[str]

    def generate_subject(self, **kwargs: Any) -> str:
        """Generate a subject line from patterns."""
        pattern = random.choice(self.subject_patterns)
        try:
            return pattern.format(**kwargs)
        except KeyError:
            return pattern

    def generate_body(self, **kwargs: Any) -> str:
        """Generate a message body from patterns."""
        pattern = random.choice(self.body_patterns)
        try:
            return pattern.format(**kwargs)
        except KeyError:
            return pattern


@dataclass
class NPCPostingSchedule:
    """Schedule configuration for an NPC poster.

    Controls when NPCs post, how often, and to which boards.
    """

    npc_template_id: str
    npc_name: str
    board_id: str
    min_interval_hours: int = 24
    max_interval_hours: int = 72
    active_hours: tuple[int, int] = (6, 22)
    probability: float = 0.3
    templates: list[NPCPostTemplate] = field(default_factory=list)
    last_post_at: datetime | None = None
    next_post_after: datetime | None = None

    def should_post(self, current_time: datetime) -> bool:
        """Check if NPC should post at current time."""
        hour = current_time.hour
        if not (self.active_hours[0] <= hour < self.active_hours[1]):
            return False

        if self.next_post_after and current_time < self.next_post_after:
            return False

        return random.random() < self.probability

    def record_post(self, current_time: datetime) -> None:
        """Record that a post was made and schedule next possible post."""
        self.last_post_at = current_time
        interval = random.randint(self.min_interval_hours, self.max_interval_hours)
        self.next_post_after = current_time + timedelta(hours=interval)


# =============================================================================
# ELODIN - Master Namer
# =============================================================================
# Tone: Unpredictable, wise, occasionally maddening
# Style: Cryptic, whimsical, non-sequiturs, naming wisdom
# Boards: university_main
# Schedule: Random hours (any time), low probability (0.1)

ELODIN_TEMPLATES = [
    NPCPostTemplate(
        subject_patterns=[
            "Wind",
            "Doors",
            "Class {action}",
            "Stone and Moon",
            "Names",
            "A Thought",
            "Regarding Doors",
            "Silence",
            "The Sleeping Mind",
            "Keys",
            "A Question",
            "Fire",
            "Nothing",
        ],
        body_patterns=[
            # Cryptic wisdom about naming
            "The name of the wind is not a name.\n"
            "Think on this. Or don't.\n"
            "I certainly won't.\n\n"
            "(This message brought to you by the Department of Naming,\n"
            "which does not exist, officially.)",
            # Class cancellation
            "Today's Naming session is {status} because I have\n"
            "misplaced my {item}. Also because naming is not something\n"
            "you can schedule on a {day} afternoon.\n\n"
            "Those seeking enlightenment may find me on the roof\n"
            "of the Mews. Or perhaps I will find you.\n\n"
            "No, probably the roof thing.",
            # Philosophical musing
            "A stone knows its name. Does the wind?\n\n"
            "The wind knows nothing. That is its name.\n\n"
            "Do not reply to this message.",
            # Observation about students
            "I saw a student attempting to memorize today.\n"
            "How dreadfully sad.\n\n"
            "Memory is a poor substitute for understanding.\n"
            "Understanding is a poor substitute for knowing.\n"
            "Knowing requires no substitute.\n\n"
            "- E",
            # Four-plate door
            "The four-plate door does not want to be opened.\n"
            "This is obvious to anyone who has asked it nicely.\n\n"
            "Stop trying to pick the lock.\n"
            "There is no lock.",
            # Doors philosophical
            "I counted the doors in the Masters' Hall today.\n"
            "There were seventeen.\n"
            "Yesterday there were nineteen.\n\n"
            "Either I have miscounted, or the building is learning.\n"
            "I suspect the building.",
            # Wind observation
            "The wind is particularly chatty today.\n"
            "It keeps saying things I cannot repeat in polite company.\n\n"
            "Those wishing to eavesdrop may join me at the top of\n"
            "the Archives at sundown.\n\n"
            "Bring warm clothes. The wind is also rude.",
            # Sleeping mind
            "Your sleeping mind knows things your waking mind\n"
            "refuses to accept.\n\n"
            "Tonight, try sleeping with your eyes open.\n"
            "If you succeed, report to me immediately.\n"
            "If you fail, report to the Medica.\n\n"
            "Either way, you will have learned something.",
            # Random class location
            "Naming class will be held {location} today.\n"
            "Or perhaps not.\n\n"
            "The name of a thing is where it is.\n"
            "Find the class, and you have already passed.",
            # Fire
            "Fire is easier to name than wind.\n"
            "This is because fire wants to be known.\n\n"
            "Wind is shy.\n"
            "Stone is stubborn.\n"
            "Water is forgetful.\n\n"
            "Students are generally hopeless.",
            # Nothing
            "I have nothing to say today.\n\n"
            "Nothing is harder to say than something.\n"
            "Consider that your lesson.",
        ],
    ),
]


# =============================================================================
# AMBROSE JAKIS - Noble Student
# =============================================================================
# Tone: Aristocratic, dismissive of commoners, haughty, formal
# Style: Complaints, boasts, condescension
# Boards: university_main, eolian_performers
# Schedule: Afternoon (2pm-8pm), medium probability (0.3)

AMBROSE_TEMPLATES = [
    NPCPostTemplate(
        subject_patterns=[
            "Commoner Infestation",
            "Quality Standards",
            "Eolian Performance - {day}",
            "Re: Standards",
            "A Reminder of Propriety",
            "Regarding the Incident",
            "Talent Pipes",
            "An Announcement",
        ],
        body_patterns=[
            # Complaint about commoners
            "It has come to my attention that certain scholarship\n"
            "students have been using the Artificery as their personal\n"
            "workshop, leaving their crude projects scattered about\n"
            "like refuse.\n\n"
            "Those of proper breeding should not have to navigate\n"
            "around the detritus of the lower classes.\n\n"
            "This is beneath the standards of the Arcanum.\n\n"
            "                        - Ambrose Jakis\n"
            "                          House Jakis, Vintas",
            # Performance announcement
            "I shall be performing at the Eolian this {day} eve.\n"
            "Those of refined taste are welcome to attend.\n\n"
            "Naturally, the talent pipes shall be mine by evening's end.\n\n"
            "                        - Ambrose Jakis\n"
            "                          Patron of the Arts",
            # Passive-aggressive threat
            "To the individual who displaced my belongings\n"
            "from my usual table at the Eolian:\n\n"
            "You know who you are. Know also that House Jakis\n"
            "has a long memory and considerable influence.\n\n"
            "                        - A. Jakis",
            # General complaint
            "Another day, another commoner pretending to belong\n"
            "amongst their betters. How tiresome.\n\n"
            "Perhaps admissions should consider family lineage\n"
            "in addition to mere academic potential.\n\n"
            "                        - Ambrose Jakis\n"
            "                          Twelfth in line to the throne of Vintas",
            # Boast about performance
            "My performance at the Eolian last {day} was,\n"
            "as expected, a resounding success.\n\n"
            "Several nobles of considerable standing were in attendance\n"
            "and expressed their appreciation in the manner befitting\n"
            "true patrons of the arts.\n\n"
            "For those who missed it: your loss.\n\n"
            "                        - Ambrose Jakis",
            # Condescension about music
            "I have observed that certain 'musicians' believe\n"
            "technical proficiency can substitute for good breeding.\n\n"
            "One cannot simply learn refinement at the Eolian.\n"
            "It must be born into the blood.\n\n"
            "Something to consider before embarrassing yourselves\n"
            "at the next open performance night.\n\n"
            "                        - A. Jakis",
            # Announcement of importance
            "I shall be attending a private function in Imre this {day}.\n"
            "Those seeking my attention will have to wait.\n\n"
            "Not that I expect any of you to have matters\n"
            "worthy of my consideration.\n\n"
            "                        - Ambrose Jakis\n"
            "                          House Jakis",
            # Complaint about specific incident
            "The incident at the lecture hall yesterday was beneath\n"
            "the dignity of the Arcanum.\n\n"
            "I trust the responsible parties will be dealt with\n"
            "appropriately. My father sits on the Iron Hall,\n"
            "as I'm sure the Masters are aware.\n\n"
            "                        - A. Jakis",
        ],
    ),
]


# =============================================================================
# KILVIN - Master Artificer
# =============================================================================
# Tone: Terse, practical, safety-conscious
# Style: Workshop notices, equipment rules, safety reminders
# Boards: artificery_commissions
# Schedule: Morning (6am-10am), high probability (0.5)

KILVIN_TEMPLATES = [
    NPCPostTemplate(
        subject_patterns=[
            "Workshop Schedule",
            "SAFETY REMINDER",
            "Equipment Maintenance",
            "Sygaldry Supplies",
            "Commission Queue",
            "Lost: {item}",
            "URGENT: Safety Notice",
            "Forge Maintenance",
        ],
        body_patterns=[
            # Workshop closure
            "ATTENTION STUDENTS:\n\n"
            "The Artificery workshop will be closed on {day}\n"
            "for maintenance of the great forge.\n\n"
            "No exceptions will be made.\n"
            "Plan your projects accordingly.\n\n"
            "- Master Kilvin",
            # Safety notice - explosions
            "SAFETY NOTICE:\n\n"
            "I must remind all students that combining\n"
            "the runes for heat and containment on the\n"
            "same object without proper slippage calculations\n"
            "is FORBIDDEN.\n\n"
            "The scorch marks on the ceiling should serve\n"
            "as adequate reminder of why.\n\n"
            "- Master Kilvin",
            # Supplies available
            "The following sygaldry supplies are now available:\n\n"
            "  - Copper wire (grade A): {price_1} talents/span\n"
            "  - Iron blanks (small): {price_2} jots each\n"
            "  - Heat-source gems: BACKORDERED\n\n"
            "See Scriv Jaxim for purchases.\n\n"
            "- Master Kilvin",
            # Workshop rules
            "WORKSHOP RULES (Annual Reminder):\n\n"
            "1. No sympathy work near the coal bins.\n"
            "2. All bindings must be documented BEFORE creation.\n"
            "3. Exploded projects must be reported within the hour.\n"
            "4. The forge is not for cooking.\n"
            "5. Clean your workspace or lose your workspace.\n\n"
            "- Master Kilvin",
            # Equipment maintenance
            "EQUIPMENT MAINTENANCE SCHEDULE:\n\n"
            "The following equipment will be unavailable {day}:\n"
            "  - Large crucibles (#4-8)\n"
            "  - Precision grinder\n"
            "  - Drawing bench\n\n"
            "Plan accordingly or face my displeasure.\n\n"
            "- Master Kilvin",
            # Lost equipment
            "MISSING EQUIPMENT:\n\n"
            "The following item is unaccounted for:\n"
            "  - {item}\n\n"
            "Return it to my office immediately.\n"
            "No questions asked. Yet.\n\n"
            "- Master Kilvin",
            # Commission update
            "COMMISSION QUEUE UPDATE:\n\n"
            "Current wait time for new commissions: {number} span.\n"
            "Priority given to University contracts.\n\n"
            "Those seeking rush orders: speak with me directly.\n"
            "Bring coin and a compelling argument.\n\n"
            "- Master Kilvin",
            # Fire safety
            "FIRE SAFETY REMINDER:\n\n"
            "The Artificery has experienced {number} preventable fires\n"
            "this term alone.\n\n"
            "Remember:\n"
            "  - Bucket of sand within arm's reach. Always.\n"
            "  - Heat-sinks cooled before leaving.\n"
            "  - No sympathy links left active overnight.\n\n"
            "The next student to violate these rules will be\n"
            "removed from the Fishery. Permanently.\n\n"
            "- Master Kilvin",
        ],
    ),
]


# =============================================================================
# LORREN - Master Archivist
# =============================================================================
# Tone: Strict, formal, precise, bureaucratic
# Style: Policy updates, rules enforcement, overdue notices
# Boards: archives_research
# Schedule: Business hours (9am-5pm), medium probability (0.3)

LORREN_TEMPLATES = [
    NPCPostTemplate(
        subject_patterns=[
            "Archives Policy Update",
            "Overdue Materials",
            "Access Restrictions",
            "New Acquisitions",
            "SILENCE REMINDER",
            "Restricted Section Hours",
            "Missing Volume",
            "Catalogue Update",
        ],
        body_patterns=[
            # Policy update
            "ARCHIVES POLICY UPDATE:\n\n"
            "Effective immediately, all students must present their\n"
            "Archives tile before entering Stacks Level 2 and below.\n\n"
            "Those without proper authorization will be escorted out\n"
            "and their access privileges reviewed.\n\n"
            "                                        - Master Lorren\n"
            "                                          Master Archivist",
            # New acquisitions
            "NEW ACQUISITIONS - {month}:\n\n"
            "The Archives has acquired the following volumes:\n\n"
            "  - 'Principles of Sympathy' (4th ed.) - 3 copies\n"
            "  - 'Cealdish Mercantile Practices' - 1 copy\n"
            "  - 'Fauna of the Eld' (illustrated) - 1 copy\n\n"
            "See the acquisition desk for availability.\n\n"
            "                                        - Master Lorren",
            # Silence reminder
            "REMINDER:\n\n"
            "The Archives is a place of SILENCE.\n\n"
            "Whispering is not silence.\n"
            "Rustling is not silence.\n"
            "Thinking loudly is not silence.\n\n"
            "Violators will be removed.\n\n"
            "                                        - Master Lorren",
            # Missing volume
            "The following volume is MISSING:\n\n"
            "  'En Temerant Voistra' - Folio IV\n\n"
            "Any information regarding its whereabouts should be\n"
            "reported to a Scriv immediately.\n\n"
            "Remember: late returns are noted. Forever.\n\n"
            "                                        - Master Lorren",
            # Overdue materials
            "OVERDUE MATERIALS NOTICE:\n\n"
            "The following students have materials {number} days overdue:\n\n"
            "  (Names posted at the Tomes desk)\n\n"
            "Return all materials immediately or face suspension\n"
            "of Archives privileges.\n\n"
            "There are no extensions. There are no exceptions.\n\n"
            "                                        - Master Lorren",
            # Restricted section
            "RESTRICTED SECTION - HOURS CHANGE:\n\n"
            "Effective {day}, the Restricted Section will only be\n"
            "accessible during the following hours:\n\n"
            "  - Luten through Chaen: 2nd bell to 8th bell\n"
            "  - Felling and Reaving: CLOSED\n\n"
            "Re'lar status required. No exceptions.\n\n"
            "                                        - Master Lorren",
            # Catalogue system
            "CATALOGUE UPDATE:\n\n"
            "The cross-reference system for {subject} has been\n"
            "reorganized. Students seeking materials in this area\n"
            "should consult the updated indices at the Tomes desk.\n\n"
            "Previous reference numbers are no longer valid.\n"
            "Do not ask Scrivs to search by old numbers.\n"
            "They will not.\n\n"
            "                                        - Master Lorren",
            # Food and drink
            "REMINDER - FOOD AND DRINK:\n\n"
            "I have been informed that students have been\n"
            "smuggling sustenance into the Stacks.\n\n"
            "This practice will cease immediately.\n\n"
            "The books are older than your grandparents.\n"
            "They deserve more respect than your hunger.\n\n"
            "                                        - Master Lorren\n"
            "                                          Master Archivist",
        ],
    ),
]


# =============================================================================
# SIMMON - Friendly Student
# =============================================================================
# Tone: Friendly, enthusiastic, helpful, casual
# Style: Study groups, sales, social events
# Boards: artificery_commissions, eolian_performers, imre_marketplace
# Schedule: Evening (4pm-10pm), medium probability (0.4)

SIMMON_TEMPLATES = [
    NPCPostTemplate(
        subject_patterns=[
            "Equipment for Sale",
            "Study Group - {subject}",
            "Eolian Tonight?",
            "Lost: Brown Leather Pouch",
            "Seeking Tutor",
            "Free Help with {subject}",
            "Anyone for Corners?",
            "Looking for Materials",
            "Group Project Partners",
            "Extra Sympathy Lamps",
        ],
        body_patterns=[
            # Equipment sale
            "Hey everyone!\n\n"
            "I have the following items available for sale,\n"
            "all in excellent condition:\n\n"
            "  - Sympathy lamp (barely used)     - 3 talents\n"
            "  - Set of binding cables           - 1 talent, 2 jots\n"
            "  - Mommet-grade wax (2 blocks)     - 4 jots each\n\n"
            "Find me at the Artificery workshop most afternoons.\n\n"
            "                                        - Simmon",
            # Study group
            "Anyone interested in forming a study group for\n"
            "{subject}? Master {master}'s exams are notoriously\n"
            "difficult and I figure we could help each other out.\n\n"
            "Meeting at the Mews common room, {day} evening.\n"
            "Bring notes and snacks!\n\n"
            "                                        - Simmon",
            # Lost item
            "Has anyone seen a brown leather pouch?\n\n"
            "I think I left it {location} or possibly the\n"
            "lecture hall. Contains some personal items and\n"
            "about 8 jots.\n\n"
            "Reward for return! (More if the jots are still there.)\n\n"
            "                                        - Simmon\n"
            "                                          Usually at Mews",
            # Eolian invitation
            "Heading to the Eolian tonight if anyone wants\n"
            "to join! Supposedly there's a new performer from\n"
            "Atur trying for their pipes.\n\n"
            "First round's on me if you can beat me at corners.\n\n"
            "                                        - Sim",
            # Tutor request
            "Seeking tutor for {subject}.\n\n"
            "Willing to trade help with Alchemy or Artificery\n"
            "basics. I'm pretty good at both if I do say so myself.\n\n"
            "Find me at {location} most evenings.\n\n"
            "                                        - Simmon",
            # Free help
            "Struggling with {subject}? I've got some free time\n"
            "this {day} and I'm happy to help out.\n\n"
            "No charge - just pay it forward when you can!\n\n"
            "Meet me at {location} after 4th bell.\n\n"
            "                                        - Sim",
            # Corners invitation
            "Anyone up for a game of Corners at Anker's tonight?\n\n"
            "I've been practicing and I think I finally figured\n"
            "out Wilem's tell. (Don't tell him I said that!)\n\n"
            "Stakes are friendly - nothing above a jot.\n\n"
            "                                        - Simmon",
            # Looking for materials
            "Looking for the following materials if anyone has\n"
            "extras they'd like to sell:\n\n"
            "  - Copper filings (clean)\n"
            "  - Small heat-source gem\n"
            "  - Binding wire, any grade\n\n"
            "Working on a project and the Fishery is out of stock.\n"
            "Will pay fair prices!\n\n"
            "                                        - Simmon",
            # Group project
            "Need {number} more people for a group project in\n"
            "{subject}. Master {master} assigned it {day}.\n\n"
            "Looking for reliable folks who actually show up\n"
            "to meetings. Last time was... rough.\n\n"
            "Interested? Find me at the Mews!\n\n"
            "                                        - Sim",
            # Extra lamps
            "Got some extra sympathy lamps from a project that\n"
            "didn't pan out. Selling cheap!\n\n"
            "  - 3 basic lamps - {price_2} jots each\n"
            "  - 1 adjustable lamp - {price_1} talents\n\n"
            "First come, first served. Find me at the Fishery\n"
            "or leave a note at the Mews.\n\n"
            "                                        - Simmon",
        ],
    ),
]


# =============================================================================
# NPC Posting Schedules
# =============================================================================

NPC_POSTING_SCHEDULES: list[NPCPostingSchedule] = [
    # Elodin - University Main (random hours, low probability)
    NPCPostingSchedule(
        npc_template_id="elodin",
        npc_name="Master Elodin",
        board_id="university_main",
        min_interval_hours=48,
        max_interval_hours=168,  # Up to a week between posts
        active_hours=(2, 23),  # 2am to 11pm - very unpredictable
        probability=0.1,  # Low probability
        templates=ELODIN_TEMPLATES,
    ),
    # Ambrose - University Main
    NPCPostingSchedule(
        npc_template_id="ambrose",
        npc_name="Ambrose Jakis",
        board_id="university_main",
        min_interval_hours=24,
        max_interval_hours=72,
        active_hours=(14, 20),  # 2pm to 8pm
        probability=0.3,
        templates=AMBROSE_TEMPLATES,
    ),
    # Ambrose - Eolian Performers
    NPCPostingSchedule(
        npc_template_id="ambrose",
        npc_name="Ambrose Jakis",
        board_id="eolian_performers",
        min_interval_hours=72,
        max_interval_hours=168,
        active_hours=(14, 20),
        probability=0.3,
        templates=AMBROSE_TEMPLATES,
    ),
    # Kilvin - Artificery Commissions (morning, high probability)
    NPCPostingSchedule(
        npc_template_id="kilvin",
        npc_name="Master Kilvin",
        board_id="artificery_commissions",
        min_interval_hours=24,
        max_interval_hours=48,
        active_hours=(6, 10),  # 6am to 10am
        probability=0.5,  # High probability
        templates=KILVIN_TEMPLATES,
    ),
    # Lorren - Archives Research (business hours, medium probability)
    NPCPostingSchedule(
        npc_template_id="lorren",
        npc_name="Master Lorren",
        board_id="archives_research",
        min_interval_hours=24,
        max_interval_hours=72,
        active_hours=(9, 17),  # 9am to 5pm
        probability=0.3,
        templates=LORREN_TEMPLATES,
    ),
    # Simmon - Artificery Commissions (evening)
    NPCPostingSchedule(
        npc_template_id="simmon",
        npc_name="Simmon",
        board_id="artificery_commissions",
        min_interval_hours=24,
        max_interval_hours=72,
        active_hours=(16, 22),  # 4pm to 10pm
        probability=0.4,
        templates=SIMMON_TEMPLATES,
    ),
    # Simmon - Eolian Performers (evening)
    NPCPostingSchedule(
        npc_template_id="simmon",
        npc_name="Simmon",
        board_id="eolian_performers",
        min_interval_hours=48,
        max_interval_hours=96,
        active_hours=(16, 22),
        probability=0.4,
        templates=SIMMON_TEMPLATES,
    ),
    # Simmon - Imre Marketplace (evening)
    NPCPostingSchedule(
        npc_template_id="simmon",
        npc_name="Simmon",
        board_id="imre_marketplace",
        min_interval_hours=24,
        max_interval_hours=72,
        active_hours=(16, 22),
        probability=0.4,
        templates=SIMMON_TEMPLATES,
    ),
]


# =============================================================================
# NPC Poster Manager
# =============================================================================


async def check_npc_posts() -> int:
    """
    Check all NPC posting schedules and create posts as needed.

    Should be called periodically (e.g., every 30 minutes from game loop).

    Returns:
        Number of posts created
    """
    # Import here to avoid circular imports
    from waystone.database.engine import get_session
    from waystone.game.systems.bulletin import BoardManager

    posts_created = 0
    current_time = datetime.now(UTC)

    for schedule in NPC_POSTING_SCHEDULES:
        if not schedule.should_post(current_time):
            continue

        if not schedule.templates:
            logger.warning(
                "npc_poster.no_templates",
                npc=schedule.npc_name,
                board=schedule.board_id,
            )
            continue

        # Select a random template from the schedule's templates
        template = random.choice(schedule.templates)

        # Generate content with random variables
        variables = _get_template_variables()
        subject = template.generate_subject(**variables)
        body = template.generate_body(**variables)

        # Post message to the board
        try:
            async with get_session() as db:
                manager = BoardManager(db)
                await manager.post_npc_message(
                    board_id=schedule.board_id,
                    npc_author_id=schedule.npc_template_id,
                    author_name=schedule.npc_name,
                    subject=subject,
                    body=body,
                )

            schedule.record_post(current_time)
            posts_created += 1

            logger.info(
                "npc_poster.post_created",
                npc=schedule.npc_name,
                board=schedule.board_id,
                subject=subject,
            )
        except Exception as e:
            logger.error(
                "npc_poster.post_failed",
                npc=schedule.npc_name,
                board=schedule.board_id,
                error=str(e),
            )

    return posts_created


def generate_sample_post(npc_id: str) -> tuple[str, str, str] | None:
    """
    Generate a sample post for testing/preview purposes.

    Args:
        npc_id: The NPC template ID (elodin, ambrose, kilvin, lorren, simmon)

    Returns:
        Tuple of (npc_name, subject, body) or None if NPC not found
    """
    npc_map = {
        "elodin": ("Master Elodin", ELODIN_TEMPLATES),
        "ambrose": ("Ambrose Jakis", AMBROSE_TEMPLATES),
        "kilvin": ("Master Kilvin", KILVIN_TEMPLATES),
        "lorren": ("Master Lorren", LORREN_TEMPLATES),
        "simmon": ("Simmon", SIMMON_TEMPLATES),
    }

    if npc_id not in npc_map:
        return None

    npc_name, templates = npc_map[npc_id]
    template = random.choice(templates)
    variables = _get_template_variables()

    subject = template.generate_subject(**variables)
    body = template.generate_body(**variables)

    return (npc_name, subject, body)


# =============================================================================
# Sample Output Generation (for testing)
# =============================================================================

if __name__ == "__main__":
    """Generate sample posts for each NPC when run directly."""
    print("=" * 70)
    print("NPC PERSONALITY TEMPLATE - SAMPLE OUTPUTS")
    print("=" * 70)

    for npc_id in ["elodin", "ambrose", "kilvin", "lorren", "simmon"]:
        print(f"\n{'=' * 70}")
        print(f" {npc_id.upper()} - Sample Posts")
        print("=" * 70)

        for i in range(3):
            result = generate_sample_post(npc_id)
            if result:
                npc_name, subject, body = result
                print(f"\n--- Sample {i + 1} ---")
                print(f"From: {npc_name}")
                print(f"Subject: {subject}")
                print("-" * 40)
                print(body)
                print()
