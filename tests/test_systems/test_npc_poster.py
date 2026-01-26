"""Tests for the NPC Poster system."""

from datetime import UTC, datetime, timedelta

import pytest

from waystone.database.engine import get_session
from waystone.database.models.bulletin import BoardMessage, BulletinBoard
from waystone.database.seed_boards import seed_bulletin_boards
from waystone.game.systems.npc_poster import (
    NPCPostingSchedule,
    NPCPostTemplate,
    check_npc_posts,
    generate_sample_post,
)


@pytest.mark.asyncio
async def test_generate_sample_posts():
    """Test sample post generation for each NPC."""
    npc_ids = ["elodin", "ambrose", "kilvin", "lorren", "simmon"]

    for npc_id in npc_ids:
        result = generate_sample_post(npc_id)
        assert result is not None, f"Failed to generate sample for {npc_id}"

        npc_name, subject, body = result
        assert npc_name, f"Missing NPC name for {npc_id}"
        assert subject, f"Missing subject for {npc_id}"
        assert body, f"Missing body for {npc_id}"
        assert len(subject) > 0, f"Empty subject for {npc_id}"
        assert len(body) > 0, f"Empty body for {npc_id}"


def test_generate_sample_post_invalid_npc():
    """Test that invalid NPC IDs return None."""
    result = generate_sample_post("invalid_npc")
    assert result is None


def test_npc_posting_schedule_should_post():
    """Test the should_post logic for NPCPostingSchedule."""
    template = NPCPostTemplate(
        subject_patterns=["Test Subject"],
        body_patterns=["Test Body"],
    )

    schedule = NPCPostingSchedule(
        npc_template_id="test_npc",
        npc_name="Test NPC",
        board_id="test_board",
        min_interval_hours=1,
        max_interval_hours=2,
        active_hours=(8, 17),  # 8am to 5pm
        probability=1.0,  # Always post when conditions met
        templates=[template],
    )

    # Create a base time for consistent testing
    base_time = datetime.now(UTC)

    # Test during active hours - should post
    active_time = base_time.replace(hour=12, minute=0, second=0, microsecond=0)
    assert schedule.should_post(active_time) is True

    # Test outside active hours - should not post
    inactive_time = base_time.replace(hour=22, minute=0, second=0, microsecond=0)
    assert schedule.should_post(inactive_time) is False

    # Test with next_post_after in future - should not post
    schedule.next_post_after = active_time + timedelta(hours=1)
    assert schedule.should_post(active_time) is False


def test_npc_posting_schedule_record_post():
    """Test that record_post updates the schedule correctly."""
    schedule = NPCPostingSchedule(
        npc_template_id="test_npc",
        npc_name="Test NPC",
        board_id="test_board",
        min_interval_hours=1,
        max_interval_hours=2,
        templates=[],
    )

    current_time = datetime.now(UTC)
    schedule.record_post(current_time)

    assert schedule.last_post_at == current_time
    assert schedule.next_post_after is not None
    assert schedule.next_post_after > current_time


def test_npc_post_template_generate():
    """Test template generation with variables."""
    template = NPCPostTemplate(
        subject_patterns=["Test {day}", "Another {item}"],
        body_patterns=["Body with {subject} and {master}"],
    )

    variables = {
        "day": "Luten",
        "item": "shoes",
        "subject": "Sympathy",
        "master": "Kilvin",
    }

    subject = template.generate_subject(**variables)
    body = template.generate_body(**variables)

    # Subject should be one of the patterns with variables filled
    assert "Luten" in subject or "shoes" in subject

    # Body should have variables filled
    assert "Sympathy" in body
    assert "Kilvin" in body


@pytest.mark.asyncio
async def test_check_npc_posts_integration(db_session):
    """Test the full NPC posting integration with database."""
    # Seed the boards
    await seed_bulletin_boards()

    # Run the check (most NPCs won't post due to probability/timing)
    posts_created = await check_npc_posts()

    # Verify it ran without error (may create 0 posts due to probability)
    assert posts_created >= 0

    # Check that the database structure is correct
    async with get_session() as session:
        # Verify boards exist
        from sqlalchemy import func, select

        board_count = await session.execute(select(func.count(BulletinBoard.id)))
        assert board_count.scalar() == 7

        # If any posts were created, verify they have correct structure
        message_count = await session.execute(select(func.count(BoardMessage.id)))
        total_messages = message_count.scalar()

        if total_messages > 0:
            # Get a sample message
            message = await session.execute(select(BoardMessage).limit(1))
            msg = message.scalar_one()

            assert msg.npc_author_id in [
                "elodin",
                "ambrose",
                "kilvin",
                "lorren",
                "simmon",
            ]
            assert msg.author_name in [
                "Master Elodin",
                "Ambrose Jakis",
                "Master Kilvin",
                "Master Lorren",
                "Simmon",
            ]
            assert len(msg.subject) > 0
            assert len(msg.body) > 0


@pytest.mark.asyncio
async def test_npc_posts_respect_board_ids(db_session):
    """Test that NPCs only post to their designated boards."""
    from waystone.game.systems.npc_poster import NPC_POSTING_SCHEDULES

    # Seed the boards
    await seed_bulletin_boards()

    # Verify schedules point to valid boards
    valid_board_ids = {
        "university_main",
        "university_admissions",
        "archives_research",
        "artificery_commissions",
        "eolian_performers",
        "imre_marketplace",
        "imre_courier",
    }

    for schedule in NPC_POSTING_SCHEDULES:
        assert schedule.board_id in valid_board_ids, (
            f"{schedule.npc_name} posts to invalid board: {schedule.board_id}"
        )
