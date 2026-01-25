"""Seed data for bulletin boards.

This module provides the function to initialize predefined bulletin boards
in the database. It can be run multiple times safely (idempotent).
"""

from typing import Any

import structlog
from sqlalchemy import select

from waystone.database.engine import get_session
from waystone.database.models.bulletin import BoardAccessLevel, BulletinBoard

logger = structlog.get_logger(__name__)


# Board definitions matching the architecture spec
BOARD_DEFINITIONS: list[dict[str, Any]] = [
    # University Boards
    {
        "id": "university_main",
        "name": "University Notice Board",
        "description": (
            "The main notice board of the University, covered with announcements, "
            "schedules, and official postings. Scraps of parchment flutter in the breeze."
        ),
        "room_id": "university_courtyard",
        "read_level": BoardAccessLevel.PUBLIC,
        "post_level": BoardAccessLevel.STUDENT,
        "max_messages": 50,
        "allow_anonymous": False,
    },
    {
        "id": "university_admissions",
        "name": "Admissions Board",
        "description": (
            "A board dedicated to admissions information, tuition announcements, "
            "and enrollment notices. Official seals mark the most important postings."
        ),
        "room_id": "university_hollows",
        "read_level": BoardAccessLevel.PUBLIC,
        "post_level": BoardAccessLevel.MASTER,
        "max_messages": 30,
        "allow_anonymous": False,
    },
    {
        "id": "archives_research",
        "name": "Research Requests",
        "description": (
            "A board for posting and claiming research requests in the Archives. "
            "Carefully cataloged notices describe texts sought and found."
        ),
        "room_id": "university_archives",
        "read_level": BoardAccessLevel.STUDENT,
        "post_level": BoardAccessLevel.ADVANCED,
        "max_messages": 40,
        "allow_anonymous": False,
    },
    {
        "id": "artificery_commissions",
        "name": "Artificer's Guild Board",
        "description": (
            "Commission requests and sale postings for artificed items. "
            "Notices describe sympathy lamps, heat funnels, and other wonders."
        ),
        "room_id": "university_artificery",
        "read_level": BoardAccessLevel.PUBLIC,
        "post_level": BoardAccessLevel.STUDENT,
        "max_messages": 40,
        "allow_anonymous": False,
    },
    # Imre Boards
    {
        "id": "eolian_performers",
        "name": "Eolian Performance Board",
        "description": (
            "A tastefully decorated board listing upcoming performances and "
            "audition times. Silver pins mark featured performers."
        ),
        "room_id": "imre_eolian",
        "read_level": BoardAccessLevel.PUBLIC,
        "post_level": BoardAccessLevel.PUBLIC,
        "max_messages": 30,
        "allow_anonymous": False,
        "attribute_requirement": '{"charisma": 12}',  # Must have CHA 12+ to post
    },
    {
        "id": "imre_marketplace",
        "name": "Imre Marketplace Board",
        "description": (
            "A weathered board full of buy/sell notices and wanted postings. "
            "The edges are frayed from constant use."
        ),
        "room_id": "imre_main_square",
        "read_level": BoardAccessLevel.PUBLIC,
        "post_level": BoardAccessLevel.PUBLIC,
        "max_messages": 60,
        "allow_anonymous": False,
    },
    {
        "id": "imre_courier",
        "name": "Courier Board",
        "description": (
            "Delivery notices and messages for travelers. "
            "Anonymous postings are common here for those seeking discretion."
        ),
        "room_id": "imre_main_gate",
        "read_level": BoardAccessLevel.PUBLIC,
        "post_level": BoardAccessLevel.PUBLIC,
        "max_messages": 40,
        "allow_anonymous": True,
    },
]


async def seed_bulletin_boards() -> int:
    """Initialize predefined boards in the database.

    This function creates the 7 predefined bulletin boards if they don't
    already exist. It's safe to run multiple times.

    Returns:
        Number of boards created (0 if all already existed)
    """
    created = 0

    try:
        async with get_session() as session:
            for board_def in BOARD_DEFINITIONS:
                # Check if board already exists
                result = await session.execute(
                    select(BulletinBoard).where(BulletinBoard.id == board_def["id"])
                )
                existing = result.scalar_one_or_none()

                if existing:
                    logger.debug(
                        "board_already_exists",
                        board_id=board_def["id"],
                        board_name=board_def["name"],
                    )
                    continue

                # Create the board
                board = BulletinBoard(
                    id=board_def["id"],
                    name=board_def["name"],
                    description=board_def["description"],
                    room_id=board_def["room_id"],
                    read_level=board_def["read_level"],
                    post_level=board_def["post_level"],
                    max_messages=board_def.get("max_messages", 50),
                    allow_anonymous=board_def.get("allow_anonymous", False),
                    is_active=True,
                    attribute_requirement=board_def.get("attribute_requirement"),
                )
                session.add(board)
                created += 1

                logger.info(
                    "board_created",
                    board_id=board.id,
                    board_name=board.name,
                    room_id=board.room_id,
                )

            await session.commit()

    except Exception as e:
        logger.error(
            "seed_boards_failed",
            error=str(e),
            exc_info=True,
        )
        raise

    logger.info(
        "seed_boards_complete",
        boards_created=created,
        total_boards=len(BOARD_DEFINITIONS),
    )
    return created


async def get_board_count() -> int:
    """Get the current number of bulletin boards in the database."""
    try:
        async with get_session() as session:
            from sqlalchemy import func

            result = await session.execute(select(func.count(BulletinBoard.id)))
            return result.scalar() or 0
    except Exception as e:
        logger.error("get_board_count_failed", error=str(e))
        return 0
