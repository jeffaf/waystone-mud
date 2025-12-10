"""Social emote commands for Waystone MUD.

Fun pre-defined emotes for player expression and social interaction.
Because what's a MUD without being able to fart at your friends?
"""

from uuid import UUID

import structlog
from sqlalchemy import select

from waystone.database.engine import get_session
from waystone.database.models import Character
from waystone.network import colorize

from .base import Command, CommandContext

logger = structlog.get_logger(__name__)


# Emote definitions: (self_message, room_message, targeted_self, targeted_room, targeted_victim)
# Use {name} for character name, {target} for target name
EMOTES: dict[str, dict[str, str]] = {
    "laugh": {
        "self": "You laugh heartily!",
        "room": "{name} laughs heartily!",
        "target_self": "You laugh at {target}!",
        "target_room": "{name} laughs at {target}!",
        "target_victim": "{name} laughs at you!",
    },
    "giggle": {
        "self": "You giggle mischievously.",
        "room": "{name} giggles mischievously.",
        "target_self": "You giggle at {target}.",
        "target_room": "{name} giggles at {target}.",
        "target_victim": "{name} giggles at you.",
    },
    "chuckle": {
        "self": "You chuckle softly to yourself.",
        "room": "{name} chuckles softly.",
        "target_self": "You chuckle at {target}.",
        "target_room": "{name} chuckles at {target}.",
        "target_victim": "{name} chuckles at you.",
    },
    "grin": {
        "self": "You grin from ear to ear.",
        "room": "{name} grins from ear to ear.",
        "target_self": "You grin at {target}.",
        "target_room": "{name} grins at {target}.",
        "target_victim": "{name} grins at you.",
    },
    "smile": {
        "self": "You smile warmly.",
        "room": "{name} smiles warmly.",
        "target_self": "You smile at {target}.",
        "target_room": "{name} smiles at {target}.",
        "target_victim": "{name} smiles at you.",
    },
    "smirk": {
        "self": "You smirk knowingly.",
        "room": "{name} smirks knowingly.",
        "target_self": "You smirk at {target}.",
        "target_room": "{name} smirks at {target}.",
        "target_victim": "{name} smirks at you. How annoying.",
    },
    "wave": {
        "self": "You wave cheerfully.",
        "room": "{name} waves cheerfully.",
        "target_self": "You wave at {target}.",
        "target_room": "{name} waves at {target}.",
        "target_victim": "{name} waves at you!",
    },
    "bow": {
        "self": "You bow gracefully.",
        "room": "{name} bows gracefully.",
        "target_self": "You bow to {target}.",
        "target_room": "{name} bows to {target}.",
        "target_victim": "{name} bows to you respectfully.",
    },
    "curtsy": {
        "self": "You curtsy elegantly.",
        "room": "{name} curtsies elegantly.",
        "target_self": "You curtsy to {target}.",
        "target_room": "{name} curtsies to {target}.",
        "target_victim": "{name} curtsies to you.",
    },
    "nod": {
        "self": "You nod thoughtfully.",
        "room": "{name} nods thoughtfully.",
        "target_self": "You nod at {target}.",
        "target_room": "{name} nods at {target}.",
        "target_victim": "{name} nods at you.",
    },
    "shake": {
        "self": "You shake your head.",
        "room": "{name} shakes their head.",
        "target_self": "You shake your head at {target}.",
        "target_room": "{name} shakes their head at {target}.",
        "target_victim": "{name} shakes their head at you disapprovingly.",
    },
    "shrug": {
        "self": "You shrug indifferently.",
        "room": "{name} shrugs indifferently.",
        "target_self": "You shrug at {target}.",
        "target_room": "{name} shrugs at {target}.",
        "target_victim": "{name} shrugs at you. Whatever!",
    },
    "wink": {
        "self": "You wink suggestively.",
        "room": "{name} winks suggestively.",
        "target_self": "You wink at {target}.",
        "target_room": "{name} winks at {target}.",
        "target_victim": "{name} winks at you. ;)",
    },
    "dance": {
        "self": "You bust out your best dance moves!",
        "room": "{name} starts dancing! Look at those moves!",
        "target_self": "You dance with {target}!",
        "target_room": "{name} dances with {target}!",
        "target_victim": "{name} grabs you and starts dancing!",
    },
    "boogie": {
        "self": "You get down and boogie!",
        "room": "{name} gets down and boogies! Disco never died!",
        "target_self": "You boogie with {target}!",
        "target_room": "{name} boogies with {target}!",
        "target_victim": "{name} boogies in your direction!",
    },
    "facepalm": {
        "self": "You facepalm in exasperation.",
        "room": "{name} facepalms in exasperation.",
        "target_self": "You facepalm at {target}'s antics.",
        "target_room": "{name} facepalms at {target}'s antics.",
        "target_victim": "{name} facepalms at your antics. Really?",
    },
    "cry": {
        "self": "You burst into tears!",
        "room": "{name} bursts into tears!",
        "target_self": "You cry on {target}'s shoulder.",
        "target_room": "{name} cries on {target}'s shoulder.",
        "target_victim": "{name} cries on your shoulder. There, there.",
    },
    "pout": {
        "self": "You pout dramatically.",
        "room": "{name} pouts dramatically.",
        "target_self": "You pout at {target}.",
        "target_room": "{name} pouts at {target}.",
        "target_victim": "{name} pouts at you. Aww...",
    },
    "sigh": {
        "self": "You sigh heavily.",
        "room": "{name} sighs heavily.",
        "target_self": "You sigh at {target}.",
        "target_room": "{name} sighs at {target}.",
        "target_victim": "{name} sighs at you. What did you do?",
    },
    "yawn": {
        "self": "You yawn sleepily.",
        "room": "{name} yawns sleepily.",
        "target_self": "You yawn at {target}. How rude!",
        "target_room": "{name} yawns at {target}. How rude!",
        "target_victim": "{name} yawns at you. Am I boring you?!",
    },
    "stretch": {
        "self": "You stretch luxuriously.",
        "room": "{name} stretches luxuriously.",
        "target_self": "You stretch towards {target}.",
        "target_room": "{name} stretches towards {target}.",
        "target_victim": "{name} stretches in your direction.",
    },
    "hug": {
        "self": "You hug yourself. Aww.",
        "room": "{name} hugs themselves. They look like they need it.",
        "target_self": "You hug {target} warmly.",
        "target_room": "{name} hugs {target} warmly.",
        "target_victim": "{name} wraps you in a warm hug!",
    },
    "poke": {
        "self": "You poke yourself. Ouch?",
        "room": "{name} pokes themselves. Weird.",
        "target_self": "You poke {target}.",
        "target_room": "{name} pokes {target}.",
        "target_victim": "{name} pokes you! Hey!",
    },
    "slap": {
        "self": "You slap yourself. Wake up!",
        "room": "{name} slaps themselves. That's one way to wake up.",
        "target_self": "You slap {target}! DRAMA!",
        "target_room": "{name} slaps {target}! The scandal!",
        "target_victim": "{name} slaps you! How dare they!",
    },
    "highfive": {
        "self": "You high-five the air. Awkward.",
        "room": "{name} high-fives the air. So lonely.",
        "target_self": "You high-five {target}!",
        "target_room": "{name} high-fives {target}!",
        "target_victim": "{name} high-fives you! Up top!",
    },
    "fistbump": {
        "self": "You fistbump the air. Cool.",
        "room": "{name} fistbumps the air. Stay cool.",
        "target_self": "You fistbump {target}!",
        "target_room": "{name} fistbumps {target}!",
        "target_victim": "{name} fistbumps you! Respect.",
    },
    "applaud": {
        "self": "You applaud yourself. Someone has to!",
        "room": "{name} applauds themselves. Self-love is important.",
        "target_self": "You applaud {target}!",
        "target_room": "{name} applauds {target}!",
        "target_victim": "{name} applauds you! Bravo!",
    },
    "cheer": {
        "self": "You cheer enthusiastically!",
        "room": "{name} cheers enthusiastically!",
        "target_self": "You cheer for {target}!",
        "target_room": "{name} cheers for {target}!",
        "target_victim": "{name} cheers for you! Woo!",
    },
    "fart": {
        "self": "You let one rip. *PFFFTTT* Ahhh, relief!",
        "room": "{name} farts loudly! *PFFFTTT* Everyone pretends not to notice.",
        "target_self": "You fart in {target}'s direction!",
        "target_room": "{name} farts in {target}'s direction! Chemical warfare!",
        "target_victim": "{name} farts in your direction! THE HORROR!",
    },
    "burp": {
        "self": "You let out a massive burp. *BUUURRRP* Excuse you!",
        "room": "{name} burps thunderously! *BUUURRRP* Classy.",
        "target_self": "You burp at {target}. Charming!",
        "target_room": "{name} burps at {target}. How romantic!",
        "target_victim": "{name} burps in your face! EW!",
    },
    "sniff": {
        "self": "You sniff the air curiously.",
        "room": "{name} sniffs the air curiously.",
        "target_self": "You sniff {target}. Hmm...",
        "target_room": "{name} sniffs {target}. Personal space?",
        "target_victim": "{name} sniffs you. Okay then...",
    },
    "flex": {
        "self": "You flex your muscles impressively!",
        "room": "{name} flexes their muscles! Check out those gains!",
        "target_self": "You flex at {target}!",
        "target_room": "{name} flexes at {target}! Gun show!",
        "target_victim": "{name} flexes at you! Impressive... or not.",
    },
    "strut": {
        "self": "You strut around confidently!",
        "room": "{name} struts around like they own the place!",
        "target_self": "You strut past {target}.",
        "target_room": "{name} struts past {target} showing off.",
        "target_victim": "{name} struts past you. What swagger!",
    },
    "flip": {
        "self": "You flip your hair dramatically!",
        "room": "{name} flips their hair dramatically! Fabulous!",
        "target_self": "You flip your hair at {target}.",
        "target_room": "{name} flips their hair at {target}.",
        "target_victim": "{name} flips their hair at you. So dismissive!",
    },
    "eyeroll": {
        "self": "You roll your eyes so hard you see your brain.",
        "room": "{name} rolls their eyes dramatically.",
        "target_self": "You roll your eyes at {target}.",
        "target_room": "{name} rolls their eyes at {target}.",
        "target_victim": "{name} rolls their eyes at you. How rude!",
    },
    "glare": {
        "self": "You glare at nothing in particular.",
        "room": "{name} glares menacingly at nothing.",
        "target_self": "You glare at {target}!",
        "target_room": "{name} glares at {target}!",
        "target_victim": "{name} glares at you! If looks could kill...",
    },
    "cackle": {
        "self": "You cackle maniacally! Mwahahaha!",
        "room": "{name} cackles maniacally! Mwahahaha!",
        "target_self": "You cackle at {target}!",
        "target_room": "{name} cackles at {target}! Creepy...",
        "target_victim": "{name} cackles at you! Unsettling!",
    },
    "snore": {
        "self": "Zzzzz... You're asleep standing up!",
        "room": "{name} starts snoring! Zzzzzz...",
        "target_self": "You pretend to snore at {target}.",
        "target_room": "{name} pretends to snore at {target}.",
        "target_victim": "{name} pretends to snore. Are you THAT boring?",
    },
    "panic": {
        "self": "You run around in circles panicking!",
        "room": "{name} runs around in circles panicking! AAAH!",
        "target_self": "You panic at {target}!",
        "target_room": "{name} panics at {target}!",
        "target_victim": "{name} panics at the sight of you!",
    },
    "flail": {
        "self": "You flail your arms wildly!",
        "room": "{name} flails their arms wildly!",
        "target_self": "You flail at {target}!",
        "target_room": "{name} flails at {target}!",
        "target_victim": "{name} flails in your direction! Watch out!",
    },
    "moonwalk": {
        "self": "You moonwalk backwards like a legend!",
        "room": "{name} moonwalks backwards! Smooth criminal!",
        "target_self": "You moonwalk past {target}.",
        "target_room": "{name} moonwalks past {target}. Too cool.",
        "target_victim": "{name} moonwalks past you. Iconic.",
    },
    "dab": {
        "self": "You dab. Is it 2016?",
        "room": "{name} dabs. It's not 2016 anymore!",
        "target_self": "You dab at {target}.",
        "target_room": "{name} dabs at {target}. Cringe.",
        "target_victim": "{name} dabs at you. Really?",
    },
    "peace": {
        "self": "You flash a peace sign. ✌️",
        "room": "{name} flashes a peace sign. ✌️",
        "target_self": "You flash a peace sign at {target}.",
        "target_room": "{name} flashes a peace sign at {target}.",
        "target_victim": "{name} flashes you a peace sign. ✌️",
    },
    "think": {
        "self": "You stroke your chin thoughtfully. Hmm...",
        "room": "{name} strokes their chin thoughtfully. Deep in thought.",
        "target_self": "You think about {target}.",
        "target_room": "{name} seems to be thinking about {target}.",
        "target_victim": "{name} seems to be thinking about you. Uh oh.",
    },
    "brb": {
        "self": "You announce you'll be right back!",
        "room": "{name} will be right back!",
        "target_self": "You tell {target} you'll be right back.",
        "target_room": "{name} tells {target} they'll be right back.",
        "target_victim": "{name} tells you they'll be right back.",
    },
    "afk": {
        "self": "You go AFK momentarily.",
        "room": "{name} goes AFK. Don't touch their stuff!",
        "target_self": "You tell {target} you're going AFK.",
        "target_room": "{name} tells {target} they're going AFK.",
        "target_victim": "{name} tells you they're going AFK.",
    },
}


class SocialEmoteCommand(Command):
    """Base class for social emote commands."""

    emote_name: str = ""

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the social emote."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to emote.", "RED")
            )
            return

        emote_data = EMOTES.get(self.emote_name)
        if not emote_data:
            await ctx.connection.send_line(colorize("Unknown emote.", "RED"))
            return

        try:
            async with get_session() as session:
                # Get character
                result = await session.execute(
                    select(Character).where(Character.id == UUID(ctx.session.character_id))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                # Check for target
                target_char = None
                if ctx.args:
                    target_name = ctx.args[0]
                    result = await session.execute(
                        select(Character).where(Character.name.ilike(target_name))
                    )
                    target_char = result.scalar_one_or_none()

                if target_char:
                    # Targeted emote
                    self_msg = emote_data["target_self"].format(
                        name=character.name, target=target_char.name
                    )
                    room_msg = emote_data["target_room"].format(
                        name=character.name, target=target_char.name
                    )
                    victim_msg = emote_data["target_victim"].format(
                        name=character.name, target=target_char.name
                    )

                    # Send to self
                    await ctx.connection.send_line(colorize(self_msg, "MAGENTA"))

                    # Send to target if online
                    target_session = ctx.engine.character_to_session.get(str(target_char.id))
                    if target_session and target_session.connection:
                        await target_session.connection.send_line(colorize(victim_msg, "MAGENTA"))

                    # Broadcast to room (excluding self and target)
                    exclude_ids = {ctx.session.id}
                    if target_session:
                        exclude_ids.add(target_session.id)

                    for session_id in list(exclude_ids):
                        ctx.engine.broadcast_to_room(
                            character.current_room_id,
                            colorize(room_msg, "MAGENTA"),
                            exclude=ctx.session.id,
                        )
                        break  # Only broadcast once

                else:
                    # Non-targeted emote
                    self_msg = emote_data["self"].format(name=character.name)
                    room_msg = emote_data["room"].format(name=character.name)

                    # Send to self
                    await ctx.connection.send_line(colorize(self_msg, "MAGENTA"))

                    # Broadcast to room
                    ctx.engine.broadcast_to_room(
                        character.current_room_id,
                        colorize(room_msg, "MAGENTA"),
                        exclude=ctx.session.id,
                    )

        except Exception as e:
            logger.error("social_emote_failed", emote=self.emote_name, error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Emote failed. Please try again.", "RED"))


# Generate command classes for each emote
def _create_emote_command(emote_name: str) -> type[SocialEmoteCommand]:
    """Factory to create emote command classes."""

    class_name = f"{emote_name.capitalize()}Command"
    emote_data = EMOTES[emote_name]

    return type(
        class_name,
        (SocialEmoteCommand,),
        {
            "name": emote_name,
            "aliases": [],
            "help_text": f"{emote_name} [target] - {emote_data['self'][:40]}...",
            "extended_help": f"""Express yourself with the {emote_name} emote!

WITHOUT TARGET:
  {emote_data['self']}

WITH TARGET:
  {emote_name} <player> - {emote_data['target_self'].replace('{name}', 'You').replace('{target}', '<player>')}

The target will see a special message just for them!""",
            "emote_name": emote_name,
            "min_args": 0,
        },
    )


# Create all emote command classes
EmoteCommands: list[type[SocialEmoteCommand]] = [
    _create_emote_command(emote_name) for emote_name in EMOTES.keys()
]


class EmotesCommand(Command):
    """List all available social emotes."""

    name = "emotes"
    aliases = ["socials"]
    help_text = "emotes - List all available social emotes"
    extended_help = """Display all available pre-defined social emotes.

These are fun shortcuts for expressing yourself! Each emote can
optionally target another player for a personalized message.

EXAMPLES:
  laugh          - Laugh by yourself
  laugh Rya      - Laugh at Rya
  fart           - Let one rip
  fart Botty     - Chemical warfare on Botty

For custom emotes, use: emote <action>
  Example: emote does a backflip"""
    min_args = 0
    requires_character = False

    async def execute(self, ctx: CommandContext) -> None:
        """List all emotes."""
        await ctx.connection.send_line(colorize("\n╔═══ Social Emotes ═══╗", "CYAN"))
        await ctx.connection.send_line(
            "Use any of these commands, optionally with a target player.\n"
        )

        # Group emotes by category
        categories = {
            "Expressions": ["laugh", "giggle", "chuckle", "grin", "smile", "smirk", "cackle"],
            "Greetings": ["wave", "bow", "curtsy", "nod", "peace"],
            "Gestures": ["shake", "shrug", "wink", "eyeroll", "glare", "facepalm", "think"],
            "Emotions": ["cry", "pout", "sigh", "panic", "flail"],
            "Physical": ["yawn", "stretch", "snore", "sniff"],
            "Social": ["hug", "poke", "slap", "highfive", "fistbump", "applaud", "cheer"],
            "Dance": ["dance", "boogie", "moonwalk", "dab", "strut", "flex", "flip"],
            "Bodily": ["fart", "burp"],
            "Status": ["brb", "afk"],
        }

        for category, emote_list in categories.items():
            valid_emotes = [e for e in emote_list if e in EMOTES]
            if valid_emotes:
                await ctx.connection.send_line(colorize(f"\n{category}:", "YELLOW"))
                await ctx.connection.send_line(f"  {', '.join(valid_emotes)}")

        await ctx.connection.send_line(colorize("\n╚══════════════════════╝", "CYAN"))
        await ctx.connection.send_line(
            "\nType " + colorize("help <emote>", "GREEN") + " for details on specific emotes."
        )
