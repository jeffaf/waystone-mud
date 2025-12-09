"""University commands for Waystone MUD.

Commands for interacting with the University system:
- Admission examinations
- Tuition payment
- Rank status
- Master interactions
"""

from waystone.game.commands.base import Command, CommandContext
from waystone.game.systems.university import (
    NINE_MASTERS,
    ArcanumRank,
    calculate_tuition,
    get_random_questions,
    get_university_status,
    rank_to_display,
    score_answer,
)
from waystone.network import colorize


class AdmitCommand(Command):
    """Request admission to the University."""

    name = "admit"
    aliases = ["admission", "apply"]
    help_text = "admit - Request admission to the University Arcanum"
    min_args = 0
    requires_character = True

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the admission request."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        # Check if in Hollows
        character = ctx.session.character
        if not character:
            await ctx.connection.send_line(colorize("Character not found.", "RED"))
            return

        current_room = ctx.engine.world.get(character.current_room_id)
        if not current_room or current_room.id != "university_hollows":
            await ctx.connection.send_line(
                colorize("You must be in the Hollows to request admission.", "YELLOW")
            )
            await ctx.connection.send_line("Go to the University and find the Hollows.")
            return

        # Get university status
        status = get_university_status(character.id)

        if status.arcanum_rank != ArcanumRank.NONE and status.tuition_paid:
            await ctx.connection.send_line(
                colorize("You are already admitted for this term.", "YELLOW")
            )
            await ctx.connection.send_line(
                f"Your current rank: {colorize(rank_to_display(status.arcanum_rank), 'CYAN')}"
            )
            return

        # Start admission examination
        await ctx.connection.send_line("")
        await ctx.connection.send_line(colorize("═" * 50, "YELLOW"))
        await ctx.connection.send_line(colorize("  UNIVERSITY ADMISSION EXAMINATION", "BOLD"))
        await ctx.connection.send_line(colorize("═" * 50, "YELLOW"))
        await ctx.connection.send_line("")
        await ctx.connection.send_line("The Masters have assembled to examine your worthiness.")
        await ctx.connection.send_line("Answer each question to the best of your ability.")
        await ctx.connection.send_line("")

        # Get 2 random questions (simplified admission for new players)
        questions = get_random_questions(2)
        total_score = 0

        for i, q in enumerate(questions, 1):
            master_id = list(NINE_MASTERS.keys())[i % len(NINE_MASTERS)]
            master = NINE_MASTERS[master_id]

            await ctx.connection.send_line(colorize(f"Master {master['name']} asks:", "CYAN"))
            await ctx.connection.send_line(f'  "{q["question"]}"')
            await ctx.connection.send_line("")

            # Get player's answer
            await ctx.connection.send("Your answer: ")
            answer = await ctx.connection.readline()

            if not answer:
                answer = ""

            # Score the answer
            rating, score = score_answer(q, answer)
            total_score += score

            # Show feedback
            if rating == "excellent":
                await ctx.connection.send_line(
                    colorize(f"  Master {master['name']} nods approvingly.", "GREEN")
                )
                status.modify_reputation(master_id, 5)
            elif rating == "good":
                await ctx.connection.send_line(
                    colorize(f"  Master {master['name']} considers your answer.", "YELLOW")
                )
                status.modify_reputation(master_id, 2)
            elif rating == "adequate":
                await ctx.connection.send_line(
                    colorize(f"  Master {master['name']} frowns slightly.", "YELLOW")
                )
            else:
                await ctx.connection.send_line(
                    colorize(f"  Master {master['name']} looks disappointed.", "RED")
                )
                status.modify_reputation(master_id, -3)

            await ctx.connection.send_line("")

        # Calculate admission score (0-100)
        admission_score = total_score // 2
        status.admission_score = admission_score

        # Determine result
        await ctx.connection.send_line(colorize("═" * 50, "YELLOW"))
        await ctx.connection.send_line(colorize("  EXAMINATION RESULTS", "BOLD"))
        await ctx.connection.send_line(colorize("═" * 50, "YELLOW"))
        await ctx.connection.send_line("")

        if admission_score >= 20:
            # Admitted
            if status.arcanum_rank == ArcanumRank.NONE:
                status.arcanum_rank = ArcanumRank.E_LIR
            status.current_term += 1

            # Calculate tuition
            tuition = calculate_tuition(
                status.arcanum_rank,
                admission_score,
                status.master_reputations,
            )
            status.tuition_amount = tuition

            await ctx.connection.send_line(
                colorize("The Masters have voted to ADMIT you.", "GREEN")
            )
            await ctx.connection.send_line("")
            await ctx.connection.send_line(
                f"Rank: {colorize(rank_to_display(status.arcanum_rank), 'CYAN')}"
            )
            await ctx.connection.send_line(f"Term: {status.current_term}")
            await ctx.connection.send_line("")

            # Show tuition
            talents = tuition // 100
            jots = tuition % 100
            tuition_str = f"{talents} talents, {jots} jots" if talents else f"{jots} jots"
            await ctx.connection.send_line(
                f"Your tuition for this term: {colorize(tuition_str, 'YELLOW')}"
            )
            await ctx.connection.send_line("")
            await ctx.connection.send_line(
                f"Use '{colorize('pay tuition', 'CYAN')}' to pay and begin your studies."
            )
        else:
            # Rejected
            await ctx.connection.send_line(
                colorize("The Masters have voted to REJECT your admission.", "RED")
            )
            await ctx.connection.send_line("Study harder and return next term to try again.")

        await ctx.connection.send_line("")


class TuitionCommand(Command):
    """Pay tuition or check tuition status."""

    name = "tuition"
    aliases = ["pay"]
    help_text = "tuition [pay] - Check or pay your University tuition"
    min_args = 0
    requires_character = True

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the tuition command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        character = ctx.session.character
        if not character:
            await ctx.connection.send_line(colorize("Character not found.", "RED"))
            return

        status = get_university_status(character.id)

        if status.arcanum_rank == ArcanumRank.NONE:
            await ctx.connection.send_line(
                colorize("You are not admitted to the University.", "YELLOW")
            )
            await ctx.connection.send_line(
                f"Go to the Hollows and use '{colorize('admit', 'CYAN')}' to apply."
            )
            return

        # Check if paying
        if ctx.args and ctx.args[0].lower() == "pay":
            if status.tuition_paid:
                await ctx.connection.send_line(
                    colorize("Your tuition is already paid for this term.", "GREEN")
                )
                return

            # Check if player has enough money
            if character.money < status.tuition_amount:
                talents = status.tuition_amount // 100
                jots = status.tuition_amount % 100
                tuition_str = f"{talents} talents, {jots} jots" if talents else f"{jots} jots"
                await ctx.connection.send_line(
                    colorize(f"You don't have enough money. Tuition is {tuition_str}.", "RED")
                )
                return

            # Pay tuition
            character.money -= status.tuition_amount
            status.tuition_paid = True

            await ctx.connection.send_line(
                colorize("You have paid your tuition for this term!", "GREEN")
            )
            await ctx.connection.send_line(
                f"You are now a full {colorize(rank_to_display(status.arcanum_rank), 'CYAN')} "
                "of the Arcanum."
            )
            await ctx.connection.send_line("")
            await ctx.connection.send_line(
                "You may now access University facilities appropriate to your rank."
            )
            return

        # Show tuition status
        await ctx.connection.send_line("")
        await ctx.connection.send_line(colorize("University Status", "BOLD"))
        await ctx.connection.send_line("─" * 30)
        await ctx.connection.send_line(
            f"Rank: {colorize(rank_to_display(status.arcanum_rank), 'CYAN')}"
        )
        await ctx.connection.send_line(f"Term: {status.current_term}")
        await ctx.connection.send_line(
            f"Tuition Paid: {colorize('Yes', 'GREEN') if status.tuition_paid else colorize('No', 'RED')}"
        )

        if not status.tuition_paid and status.tuition_amount > 0:
            talents = status.tuition_amount // 100
            jots = status.tuition_amount % 100
            tuition_str = f"{talents} talents, {jots} jots" if talents else f"{jots} jots"
            await ctx.connection.send_line(f"Amount Due: {colorize(tuition_str, 'YELLOW')}")
            await ctx.connection.send_line("")
            await ctx.connection.send_line(f"Use '{colorize('tuition pay', 'CYAN')}' to pay.")

        await ctx.connection.send_line("")


class RankCommand(Command):
    """Check your Arcanum rank and standing."""

    name = "rank"
    aliases = ["standing", "arcanum"]
    help_text = "rank - Check your Arcanum rank and standing with the Masters"
    min_args = 0
    requires_character = True

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the rank command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        character = ctx.session.character
        if not character:
            await ctx.connection.send_line(colorize("Character not found.", "RED"))
            return

        status = get_university_status(character.id)

        await ctx.connection.send_line("")
        await ctx.connection.send_line(colorize("═" * 40, "CYAN"))
        await ctx.connection.send_line(colorize("  ARCANUM STANDING", "BOLD"))
        await ctx.connection.send_line(colorize("═" * 40, "CYAN"))
        await ctx.connection.send_line("")

        if status.arcanum_rank == ArcanumRank.NONE:
            await ctx.connection.send_line(
                colorize("You are not a member of the Arcanum.", "YELLOW")
            )
            await ctx.connection.send_line("Visit the Hollows to apply for admission.")
            await ctx.connection.send_line("")
            return

        await ctx.connection.send_line(
            f"Rank: {colorize(rank_to_display(status.arcanum_rank), 'CYAN')}"
        )
        await ctx.connection.send_line(f"Term: {status.current_term}")
        await ctx.connection.send_line(f"Last Exam Score: {status.admission_score}%")
        await ctx.connection.send_line("")

        # Show master reputations
        await ctx.connection.send_line(colorize("Master Reputations:", "BOLD"))
        await ctx.connection.send_line("─" * 30)

        for master_id, master in NINE_MASTERS.items():
            rep = status.get_reputation(master_id)
            if rep > 20:
                rep_color = "GREEN"
                rep_text = "Favorable"
            elif rep > 0:
                rep_color = "CYAN"
                rep_text = "Neutral+"
            elif rep < -20:
                rep_color = "RED"
                rep_text = "Hostile"
            elif rep < 0:
                rep_color = "YELLOW"
                rep_text = "Wary"
            else:
                rep_color = "DIM"
                rep_text = "Neutral"

            await ctx.connection.send_line(
                f"  {master['name']:12} [{colorize(rep_text, rep_color)}] ({rep:+d})"
            )

        await ctx.connection.send_line("")
        avg_rep = status.average_reputation()
        await ctx.connection.send_line(f"Overall Standing: {avg_rep:+.1f}")
        await ctx.connection.send_line("")


class WorkCommand(Command):
    """Work a University job for money and experience."""

    name = "work"
    aliases = ["job"]
    help_text = "work <job> - Work a University job (scriv, medica, artificery)"
    min_args = 1
    requires_character = True

    JOBS = {
        "scriv": {
            "name": "Archives Scriv",
            "room": "university_archives",
            "pay": 25,  # 25 jots
            "description": "Copy and catalog books in the Archives",
            "requires_rank": ArcanumRank.E_LIR,
        },
        "medica": {
            "name": "Medica Assistant",
            "room": "university_medica",
            "pay": 100,  # 1 talent
            "description": "Assist Master Arwyl in the Medica",
            "requires_rank": ArcanumRank.E_LIR,
        },
        "artificery": {
            "name": "Artificery Helper",
            "room": "university_artificery",
            "pay": 50,  # 50 jots
            "description": "Help with basic tasks in the Artificery",
            "requires_rank": ArcanumRank.NONE,
        },
    }

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the work command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        character = ctx.session.character
        if not character:
            await ctx.connection.send_line(colorize("Character not found.", "RED"))
            return

        job_name = ctx.args[0].lower()

        if job_name not in self.JOBS:
            await ctx.connection.send_line(colorize(f"Unknown job: {job_name}", "RED"))
            await ctx.connection.send_line("Available jobs: scriv, medica, artificery")
            return

        job = self.JOBS[job_name]
        status = get_university_status(character.id)

        # Check rank requirement
        from waystone.game.systems.university import RANK_ORDER

        if RANK_ORDER.index(status.arcanum_rank) < RANK_ORDER.index(job["requires_rank"]):
            await ctx.connection.send_line(
                colorize(f"This job requires {rank_to_display(job['requires_rank'])} rank.", "RED")
            )
            return

        # Check if in correct room
        current_room = ctx.engine.world.get(character.current_room_id)
        if not current_room or current_room.id != job["room"]:
            await ctx.connection.send_line(
                colorize(f"You must be in the {job['name'].split()[0]} to work this job.", "YELLOW")
            )
            return

        # Work the job
        character.money += job["pay"]

        talents = job["pay"] // 100
        jots = job["pay"] % 100
        pay_str = f"{talents} talents, {jots} jots" if talents else f"{jots} jots"

        await ctx.connection.send_line("")
        await ctx.connection.send_line(f"You spend some time working as a {job['name']}.")
        await ctx.connection.send_line(job["description"] + ".")
        await ctx.connection.send_line("")
        await ctx.connection.send_line(f"You earn {colorize(pay_str, 'GREEN')}.")
        await ctx.connection.send_line("")

        # Small reputation boost
        if job_name == "scriv":
            status.modify_reputation("master_lorren", 1)
        elif job_name == "medica":
            status.modify_reputation("master_arwyl", 1)
        elif job_name == "artificery":
            status.modify_reputation("master_kilvin", 1)
