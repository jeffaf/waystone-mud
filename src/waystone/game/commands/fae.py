"""Fae realm commands for Waystone MUD.

Handles:
- Entering the Fae realm through the Greystones
- Speaking with the Cthaeh (accepting the curse)
- Viewing curse status and current bidding
"""

from uuid import UUID

import structlog
from sqlalchemy import select

from waystone.database.engine import get_session
from waystone.database.models import Character
from waystone.game.systems.cthaeh import (
    accept_curse,
    assign_new_bidding,
    format_curse_status,
    load_cthaeh_status,
)
from waystone.network import colorize

from .base import Command, CommandContext

logger = structlog.get_logger(__name__)

# Rooms where Fae entry is possible
FAE_GATEWAY_ROOMS = ["greystones"]

# Room where Cthaeh can be spoken to
CTHAEH_ROOM = "fae_cthaeh_clearing"


class EnterFaeCommand(Command):
    """
    Enter the Fae realm through the Greystones.

    Can only be used at the Greystones location during twilight.
    """

    name = "enter"
    aliases = ["step"]
    help_text = "enter fae - Step through the Greystones into the Fae realm"
    min_args = 1

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the enter fae command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        if not ctx.args or ctx.args[0].lower() not in ["fae", "stones", "gateway"]:
            await ctx.connection.send_line(colorize("Enter what?", "YELLOW"))
            return

        try:
            async with get_session() as session:
                result = await session.execute(
                    select(Character).where(Character.id == UUID(ctx.session.character_id))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                # Check if at a gateway location
                if character.current_room_id not in FAE_GATEWAY_ROOMS:
                    await ctx.connection.send_line(
                        colorize("There is no gateway to the Fae here.", "YELLOW")
                    )
                    return

                # Move to the Fae realm
                old_room_id = character.current_room_id
                character.current_room_id = "fae_twilight_forest"
                await session.commit()

                # Dramatic entry message
                await ctx.connection.send_line("")
                await ctx.connection.send_line(
                    colorize("You step between the standing stones...", "MAGENTA")
                )
                await ctx.connection.send_line("")
                await ctx.connection.send_line(
                    colorize(
                        "The world twists. Colors bleed. Time stretches like warm taffy.",
                        "MAGENTA",
                    )
                )
                await ctx.connection.send_line("")
                await ctx.connection.send_line(
                    colorize(
                        "When your vision clears, you stand in a forest of eternal twilight.",
                        "MAGENTA",
                    )
                )
                await ctx.connection.send_line("")

                # Show the new room
                room = ctx.engine.rooms.get("fae_twilight_forest")
                if room:
                    await ctx.connection.send_line(colorize(room.name, "CYAN"))
                    await ctx.connection.send_line(room.description.strip())

                logger.info(
                    "entered_fae_realm",
                    character_id=str(character.id),
                    character_name=character.name,
                    from_room=old_room_id,
                )

        except Exception as e:
            logger.error("enter_fae_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Something prevents you from entering...", "RED")
            )


class SpeakCthaehCommand(Command):
    """
    Speak with the Cthaeh and potentially accept its curse.

    This is a major decision with permanent consequences.
    """

    name = "speak"
    aliases = ["talk"]
    help_text = "speak cthaeh - Speak with the Cthaeh (WARNING: Permanent consequences)"
    min_args = 1

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the speak cthaeh command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        target = " ".join(ctx.args).lower()

        # Only handle cthaeh - let other speak commands go elsewhere
        if target not in ["cthaeh", "tree", "oracle", "it", "voice"]:
            # Check if there's an NPC to talk to
            await ctx.connection.send_line(colorize(f"Speak to whom? '{target}'?", "YELLOW"))
            return

        try:
            async with get_session() as session:
                result = await session.execute(
                    select(Character).where(Character.id == UUID(ctx.session.character_id))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                # Check if in Cthaeh's clearing
                if character.current_room_id != CTHAEH_ROOM:
                    await ctx.connection.send_line(
                        colorize("The Cthaeh is not here.", "YELLOW")
                    )
                    return

                # Check if already cursed
                status = load_cthaeh_status(character)

                if status.cursed:
                    # Already cursed - give cryptic dialogue and bidding
                    await self._handle_cursed_dialogue(ctx, character, session)
                else:
                    # Not cursed - offer the curse
                    await self._offer_curse(ctx, character, session)

        except Exception as e:
            logger.error("speak_cthaeh_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("The tree remains silent.", "RED")
            )

    async def _offer_curse(
        self, ctx: CommandContext, character: Character, session
    ) -> None:
        """Offer the curse to an uncursed character."""
        await ctx.connection.send_line("")
        await ctx.connection.send_line(
            colorize(
                "A voice drifts from the tree, soft as falling leaves, sharp as broken glass.",
                "MAGENTA",
            )
        )
        await ctx.connection.send_line("")
        await ctx.connection.send_line(
            colorize('"Ah. Another seeker. How... delightful."', "WHITE")
        )
        await ctx.connection.send_line("")
        await ctx.connection.send_line(
            colorize(
                '"I can give you power. The strength to overcome your enemies."',
                "WHITE",
            )
        )
        await ctx.connection.send_line(
            colorize('"All I ask in return is... service. Small tasks."', "WHITE")
        )
        await ctx.connection.send_line(
            colorize('"Nothing you wouldn\'t do anyway, given enough time."', "WHITE")
        )
        await ctx.connection.send_line("")
        await ctx.connection.send_line(
            colorize("The butterflies swirl faster, red and black and terrible.", "MAGENTA")
        )
        await ctx.connection.send_line("")
        await ctx.connection.send_line(
            colorize("Type 'embrace curse' to accept the Cthaeh's gift.", "YELLOW")
        )
        await ctx.connection.send_line(
            colorize("WARNING: This choice is PERMANENT and cannot be undone.", "RED")
        )

    async def _handle_cursed_dialogue(
        self, ctx: CommandContext, character: Character, session
    ) -> None:
        """Handle dialogue for already-cursed characters."""
        status = load_cthaeh_status(character)

        await ctx.connection.send_line("")
        await ctx.connection.send_line(
            colorize('"Ah, my little shadow returns..."', "WHITE")
        )
        await ctx.connection.send_line("")

        # Check if they can receive a new bidding
        if status.can_receive_new_bidding():
            # Assign a new bidding
            new_status = assign_new_bidding(character, ctx.engine)
            if new_status:
                await session.commit()
                await ctx.connection.send_line(
                    colorize('"I have a task for you..."', "WHITE")
                )
                await ctx.connection.send_line("")
                await ctx.connection.send_line(
                    colorize(
                        f'"Kill {new_status.target_display_name}. Do this, and I shall be... pleased."',
                        "RED",
                    )
                )
                await ctx.connection.send_line("")
                await ctx.connection.send_line(
                    colorize(
                        "You have 24 hours to complete this bidding.",
                        "YELLOW",
                    )
                )
        elif status.has_active_bidding():
            # Remind them of current target
            await ctx.connection.send_line(
                colorize(
                    f'"Have you forgotten? {status.target_display_name} still breathes..."',
                    "WHITE",
                )
            )
            await ctx.connection.send_line("")
            remaining = status.target_expires_at - __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            )
            hours = int(remaining.total_seconds() / 3600)
            minutes = int((remaining.total_seconds() % 3600) / 60)
            await ctx.connection.send_line(
                colorize(f"Time remaining: {hours}h {minutes}m", "YELLOW")
            )
        else:
            # On cooldown
            await ctx.connection.send_line(
                colorize('"Rest now. I will call upon you soon enough..."', "WHITE")
            )


class AcceptCurseCommand(Command):
    """
    Accept the Cthaeh's curse.

    This is permanent and grants combat bonuses in exchange for service.
    """

    name = "embrace"
    aliases = ["acceptcurse"]
    help_text = "embrace curse - Accept the Cthaeh's curse (PERMANENT)"
    min_args = 1

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the embrace curse command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        if not ctx.args or ctx.args[0].lower() != "curse":
            await ctx.connection.send_line(colorize("Embrace what?", "YELLOW"))
            return

        try:
            async with get_session() as session:
                result = await session.execute(
                    select(Character).where(Character.id == UUID(ctx.session.character_id))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                # Must be in Cthaeh's clearing
                if character.current_room_id != CTHAEH_ROOM:
                    await ctx.connection.send_line(
                        colorize("The Cthaeh is not here.", "YELLOW")
                    )
                    return

                # Check if already cursed
                status = load_cthaeh_status(character)
                if status.cursed:
                    await ctx.connection.send_line(
                        colorize(
                            '"You already bear my mark, little shadow..."',
                            "WHITE",
                        )
                    )
                    return

                # Accept the curse
                accept_curse(character)
                await session.commit()

                # Dramatic acceptance message
                await ctx.connection.send_line("")
                await ctx.connection.send_line(
                    colorize("You speak the words of acceptance.", "MAGENTA")
                )
                await ctx.connection.send_line("")
                await ctx.connection.send_line(
                    colorize(
                        "The Cthaeh's laughter echoes through the clearing - a sound like breaking glass.",
                        "MAGENTA",
                    )
                )
                await ctx.connection.send_line("")
                await ctx.connection.send_line(
                    colorize('"It is done. You are mine now."', "WHITE")
                )
                await ctx.connection.send_line("")
                await ctx.connection.send_line(
                    colorize(
                        "Cold spreads through your chest. Something has changed. Something is... different.",
                        "MAGENTA",
                    )
                )
                await ctx.connection.send_line("")
                await ctx.connection.send_line(
                    colorize("You feel stronger. Faster. More dangerous.", "GREEN")
                )
                await ctx.connection.send_line(
                    colorize("  +15% damage in combat", "GREEN")
                )
                await ctx.connection.send_line(
                    colorize("  +10% critical chance", "GREEN")
                )
                await ctx.connection.send_line(
                    colorize("  +3 to Strength, Dexterity, Constitution", "GREEN")
                )
                await ctx.connection.send_line("")
                await ctx.connection.send_line(
                    colorize(
                        '"Return to me when you are ready for your first task..."',
                        "WHITE",
                    )
                )
                await ctx.connection.send_line("")
                await ctx.connection.send_line(
                    colorize("Type 'curse' to view your curse status at any time.", "YELLOW")
                )

                logger.info(
                    "cthaeh_curse_accepted_by_player",
                    character_id=str(character.id),
                    character_name=character.name,
                )

        except Exception as e:
            logger.error("accept_curse_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Something went wrong...", "RED")
            )


class CurseCommand(Command):
    """
    View your Cthaeh curse status.

    Shows buffs/debuffs, current bidding, and completion history.
    """

    name = "curse"
    aliases = ["bidding", "cthaeh"]
    help_text = "curse - View your Cthaeh curse status and current bidding"
    min_args = 0

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the curse status command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        try:
            async with get_session() as session:
                result = await session.execute(
                    select(Character).where(Character.id == UUID(ctx.session.character_id))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                # Get formatted status
                lines = format_curse_status(character)

                await ctx.connection.send_line("")
                await ctx.connection.send_line(colorize("=== Cthaeh Curse Status ===", "MAGENTA"))
                for line in lines:
                    # Color code based on content
                    if "DEBUFF" in line:
                        await ctx.connection.send_line(colorize(line, "RED"))
                    elif "Bonus" in line or "+3" in line:
                        await ctx.connection.send_line(colorize(line, "GREEN"))
                    elif "CURRENT BIDDING" in line or "Target:" in line:
                        await ctx.connection.send_line(colorize(line, "YELLOW"))
                    elif "whispers" in line:
                        await ctx.connection.send_line(colorize(line, "CYAN"))
                    else:
                        await ctx.connection.send_line(line)
                await ctx.connection.send_line("")

        except Exception as e:
            logger.error("curse_status_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Could not retrieve curse status.", "RED")
            )


class LeaveFaeCommand(Command):
    """
    Leave the Fae realm and return to the mortal world.

    Can only be used in the Twilight Forest near the gateway.
    """

    name = "leavefae"
    aliases = ["return"]
    help_text = "leavefae - Return to the mortal world through the gateway"
    min_args = 0

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the leave fae command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        try:
            async with get_session() as session:
                result = await session.execute(
                    select(Character).where(Character.id == UUID(ctx.session.character_id))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                # Must be in Fae twilight forest (near the gateway)
                if character.current_room_id != "fae_twilight_forest":
                    await ctx.connection.send_line(
                        colorize(
                            "You cannot find the way back from here. The gateway shimmers only in the Twilight Forest.",
                            "YELLOW",
                        )
                    )
                    return

                # Return to mortal world
                character.current_room_id = "greystones"
                await session.commit()

                # Dramatic exit message
                await ctx.connection.send_line("")
                await ctx.connection.send_line(
                    colorize("You step toward the shimmering gateway...", "MAGENTA")
                )
                await ctx.connection.send_line("")
                await ctx.connection.send_line(
                    colorize(
                        "Reality twists and reforms. The eternal twilight fades.",
                        "MAGENTA",
                    )
                )
                await ctx.connection.send_line("")
                await ctx.connection.send_line(
                    colorize(
                        "You stand once more among the Greystones, in the mortal world.",
                        "MAGENTA",
                    )
                )
                await ctx.connection.send_line("")

                # Show the new room
                room = ctx.engine.rooms.get("greystones")
                if room:
                    await ctx.connection.send_line(colorize(room.name, "CYAN"))
                    await ctx.connection.send_line(room.description.strip())

                logger.info(
                    "left_fae_realm",
                    character_id=str(character.id),
                    character_name=character.name,
                )

        except Exception as e:
            logger.error("leave_fae_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Something prevents you from leaving...", "RED")
            )
