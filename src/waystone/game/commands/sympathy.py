"""Sympathy magic commands for Waystone MUD."""

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from waystone.database.engine import get_session
from waystone.database.models import Character, ItemInstance
from waystone.game.systems.magic.sympathy import (
    HEAT_SOURCE_ENERGY,
    BindingType,
    EnergySource,
    HeatSourceType,
    apply_backlash,
    check_for_backlash,
    create_binding,
    create_energy_source,
    execute_damage_transfer,
    execute_heat_transfer,
    execute_kinetic_transfer,
    format_bindings_display,
    format_sympathy_status,
    get_active_bindings,
    get_character_alar,
    get_max_bindings,
    get_sympathy_rank,
    release_all_bindings,
    release_binding,
)
from waystone.network import colorize

from .base import Command, CommandContext

logger = structlog.get_logger(__name__)


# Track active energy sources per character
_active_energy_sources: dict[str, EnergySource] = {}


class BindCommand(Command):
    """Create a sympathetic binding between objects."""

    name = "bind"
    aliases = ["link"]
    help_text = "bind <type> <source> <target> - Create a sympathetic binding"
    extended_help = """Sympathy is the art of creating links between objects to transfer energy.

BINDING TYPES:
  heat    - Transfer heat between objects (useful for warming/cooling)
  kinetic - Transfer force/motion (push objects remotely)
  damage  - Combat binding to harm enemies through linked objects
  light   - Create or redirect light sources
  dowse   - Locate similar objects (finding things)

REQUIREMENTS:
  1. You must HOLD a heat source first (torch, candle, body heat)
  2. Source and target must have some similarity for best efficiency
  3. Your Alar (willpower) limits how many bindings you can maintain

EXAMPLES:
  bind heat coin torch     - Link coin to torch for heat transfer
  bind damage coin rat     - Link coin to rat for combat
  bind kinetic stone door  - Link stone to door to push it

WARNING: Using body heat is dangerous! Risk of backlash increases."""
    min_args = 3

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the bind command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        binding_type_str = ctx.args[0].lower()
        source_name = ctx.args[1].lower()
        target_name = " ".join(ctx.args[2:]).lower()

        # Parse binding type
        binding_type_map = {
            "heat": BindingType.HEAT_TRANSFER,
            "kinetic": BindingType.KINETIC_TRANSFER,
            "damage": BindingType.DAMAGE_TRANSFER,
            "light": BindingType.LIGHT_BINDING,
            "dowse": BindingType.DOWSING,
        }

        binding_type = binding_type_map.get(binding_type_str)
        if not binding_type:
            valid_types = ", ".join(binding_type_map.keys())
            await ctx.connection.send_line(
                colorize(f"Invalid binding type. Valid types: {valid_types}", "YELLOW")
            )
            return

        try:
            async with get_session() as session:
                # Get character with inventory
                result = await session.execute(
                    select(Character)
                    .where(Character.id == UUID(ctx.session.character_id))
                    .options(joinedload(Character.items).joinedload(ItemInstance.template))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                # Check for active energy source
                energy_source = _active_energy_sources.get(ctx.session.character_id)
                if not energy_source:
                    await ctx.connection.send_line(
                        colorize(
                            "You need an active heat source! Use 'hold <item>' to designate one.",
                            "YELLOW",
                        )
                    )
                    return

                if energy_source.is_depleted:
                    await ctx.connection.send_line(
                        colorize("Your heat source is depleted! Hold a new one.", "YELLOW")
                    )
                    return

                # Find source item in inventory
                source_item = None
                for item in character.items:
                    if item.room_id is None and source_name in item.template.name.lower():
                        source_item = item
                        break

                if not source_item:
                    await ctx.connection.send_line(
                        colorize(f"You don't have '{source_name}' in your inventory.", "YELLOW")
                    )
                    return

                # Find target - could be item in room, another player, or NPC
                target_id = None
                target_material = "iron"  # Default

                # Check room items
                room = ctx.engine.world.get(character.current_room_id)
                if room:
                    room_items_result = await session.execute(
                        select(ItemInstance)
                        .where(ItemInstance.room_id == character.current_room_id)
                        .options(joinedload(ItemInstance.template))
                    )
                    room_items = room_items_result.scalars().all()

                    for item in room_items:
                        if target_name in item.template.name.lower():
                            target_id = str(item.id)
                            props = item.template.properties or {}
                            target_material = props.get("material", "iron")
                            break

                # Check other players in room
                if not target_id and room:
                    for player_id in room.players:
                        if player_id != ctx.session.character_id:
                            player_result = await session.execute(
                                select(Character).where(Character.id == UUID(player_id))
                            )
                            player = player_result.scalar_one_or_none()
                            if player and target_name in player.name.lower():
                                target_id = str(player.id)
                                target_material = "human"
                                break

                if not target_id:
                    await ctx.connection.send_line(
                        colorize(f"Cannot find '{target_name}' to target.", "YELLOW")
                    )
                    return

                # Get source material
                source_props = source_item.template.properties or {}
                source_material = source_props.get("material", "iron")

                # Check for consanguinity (items from same source)
                consanguinity = source_props.get("consanguinity_link", False)

                # Create the binding
                binding, message = await create_binding(
                    caster=character,
                    binding_type=binding_type,
                    source_id=str(source_item.id),
                    target_id=target_id,
                    source_material=source_material,
                    target_material=target_material,
                    energy_source=energy_source,
                    consanguinity=consanguinity,
                    engine=ctx.engine,
                )

                await session.commit()

                if binding:
                    await ctx.connection.send_line(colorize(message, "GREEN"))

                    # Show binding info
                    efficiency_pct = int(binding.efficiency * 100)
                    await ctx.connection.send_line(
                        colorize(
                            f"Link: {source_item.template.name} -> {target_name} ({efficiency_pct}%)",
                            "CYAN",
                        )
                    )
                else:
                    await ctx.connection.send_line(colorize(message, "YELLOW"))

        except Exception as e:
            logger.error("bind_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to create binding. Please try again.", "RED")
            )


class ReleaseCommand(Command):
    """Release active sympathetic bindings."""

    name = "release"
    aliases = ["unbind"]
    help_text = "release [all|number] - Release bindings (default: all)"
    min_args = 0

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the release command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        bindings = get_active_bindings(ctx.session.character_id)

        if not bindings:
            await ctx.connection.send_line(colorize("You have no active bindings.", "DIM"))
            return

        # Release all or specific binding
        if not ctx.args or ctx.args[0].lower() == "all":
            count = release_all_bindings(ctx.session.character_id)
            await ctx.connection.send_line(
                colorize(f"You release {count} binding(s). Your mind clears.", "GREEN")
            )
        else:
            try:
                binding_num = int(ctx.args[0]) - 1
                if 0 <= binding_num < len(bindings):
                    binding = bindings[binding_num]
                    success, message = release_binding(ctx.session.character_id, binding.binding_id)
                    color = "GREEN" if success else "YELLOW"
                    await ctx.connection.send_line(colorize(message, color))
                else:
                    await ctx.connection.send_line(
                        colorize(
                            f"Invalid binding number. You have {len(bindings)} binding(s).",
                            "YELLOW",
                        )
                    )
            except ValueError:
                await ctx.connection.send_line(colorize("Usage: release [all|number]", "YELLOW"))


class BindingsCommand(Command):
    """Show active sympathetic bindings."""

    name = "bindings"
    aliases = ["links"]
    help_text = "bindings - Show your active sympathetic bindings"
    min_args = 0

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the bindings command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        display = format_bindings_display(ctx.session.character_id)
        await ctx.connection.send_line(display)


class SympathyCommand(Command):
    """Show sympathy skill status."""

    name = "sympathy"
    aliases = ["sym"]
    help_text = "sympathy - Show your sympathy skill and status"
    extended_help = """Display your sympathy skill rank and current status.

SYMPATHY RANKS:
  Untrained     - 30% efficiency cap
  E'lir         - 50% efficiency cap (requires 100 XP)
  Re'lar        - 65% efficiency cap (requires 300 XP)
  El'the        - 80% efficiency cap (requires 700 XP)
  Master        - 90% efficiency cap (requires 1500 XP)
  Arcane Master - 95% efficiency cap (requires 3000 XP)

Shows: Your current rank, efficiency cap, active bindings,
max bindings allowed, and current heat source.

RELATED COMMANDS:
  hold <source> - Set heat source
  bind          - Create a binding
  bindings      - List active bindings
  release       - Release bindings"""
    min_args = 0

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the sympathy command."""
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

                status = format_sympathy_status(character)
                await ctx.connection.send_line(status)

                # Show active bindings summary
                bindings = get_active_bindings(ctx.session.character_id)
                alar = get_character_alar(character)
                max_bindings = get_max_bindings(alar)

                await ctx.connection.send_line(f"  Active Bindings: {len(bindings)}/{max_bindings}")

                # Show active energy source
                energy_source = _active_energy_sources.get(ctx.session.character_id)
                if energy_source:
                    energy_pct = int(
                        (energy_source.remaining_energy / max(1, energy_source.max_energy)) * 100
                    )
                    await ctx.connection.send_line(
                        f"  Heat Source: {energy_source.source_type.value} ({energy_pct}% remaining)"
                    )
                else:
                    await ctx.connection.send_line(
                        colorize("  Heat Source: None (use 'hold <item>')", "DIM")
                    )

        except Exception as e:
            logger.error("sympathy_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Failed to get sympathy status.", "RED"))


class HoldCommand(Command):
    """Designate a heat source for sympathy."""

    name = "hold"
    aliases = ["heatsource"]
    help_text = "hold <item|body> - Designate a heat source for sympathy"
    extended_help = """Designate a heat source to power your sympathetic bindings.

HEAT SOURCES (by power):
  candle   - 50 energy   (weak but safe)
  torch    - 150 energy  (common choice)
  brazier  - 500 energy  (powerful)
  bonfire  - 1500 energy (very powerful)
  body     - 100 energy  (DANGEROUS! 2.5x backlash risk)
  sun      - 2000 energy (outdoors only, during day)

USAGE:
  hold torch   - Use a torch from your inventory
  hold candle  - Use a candle
  hold body    - Use your own body heat (risky!)

The heat source must be in your inventory (except body/sun).
More powerful sources allow stronger bindings but deplete faster."""
    min_args = 1

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the hold command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        source_name = " ".join(ctx.args).lower()

        try:
            # Special case: body heat
            if source_name == "body":
                energy_source = create_energy_source(HeatSourceType.BODY)
                _active_energy_sources[ctx.session.character_id] = energy_source

                await ctx.connection.send_line(
                    colorize(
                        "You focus on drawing from your own body heat.\n"
                        "WARNING: This is extremely dangerous and can cause severe backlash!",
                        "RED",
                    )
                )
                return

            async with get_session() as session:
                # Get character with inventory
                result = await session.execute(
                    select(Character)
                    .where(Character.id == UUID(ctx.session.character_id))
                    .options(joinedload(Character.items).joinedload(ItemInstance.template))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                # Find heat source item in inventory
                heat_item = None
                for item in character.items:
                    if item.room_id is None and source_name in item.template.name.lower():
                        item_props = item.template.properties or {}
                        if item_props.get("heat_source"):
                            heat_item = item
                            break

                if not heat_item:
                    await ctx.connection.send_line(
                        colorize(
                            f"You don't have a heat source named '{source_name}'.\n"
                            "Try 'hold body' to use body heat (dangerous!) or get a candle/torch.",
                            "YELLOW",
                        )
                    )
                    return

                # Determine heat type
                heat_props = heat_item.template.properties or {}
                heat_type_str = heat_props.get("heat_type", "candle")
                try:
                    heat_type = HeatSourceType(heat_type_str)
                except ValueError:
                    heat_type = HeatSourceType.CANDLE

                # Create energy source
                energy_source = create_energy_source(heat_type, str(heat_item.id))
                _active_energy_sources[ctx.session.character_id] = energy_source

                energy_per_turn = HEAT_SOURCE_ENERGY.get(heat_type.value, 50)
                await ctx.connection.send_line(
                    colorize(
                        f"You hold the {heat_item.template.name} ready for sympathetic work.\n"
                        f"Energy output: {energy_per_turn}/turn | "
                        f"Remaining: {energy_source.remaining_energy}",
                        "GREEN",
                    )
                )

        except Exception as e:
            logger.error("hold_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Failed to hold heat source.", "RED"))


class PushCommand(Command):
    """Use kinetic sympathy to push an object."""

    name = "push"
    aliases = []
    help_text = "push [force] - Push target through active kinetic binding"
    min_args = 0

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the push command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        # Parse optional force amount (target is determined by active binding)
        force_amount = 50  # Default force
        if ctx.args:
            try:
                force_amount = int(ctx.args[0])
            except ValueError:
                pass

        bindings = get_active_bindings(ctx.session.character_id)

        # Find a kinetic binding targeting this
        kinetic_binding = None
        for binding in bindings:
            if binding.binding_type == BindingType.KINETIC_TRANSFER:
                kinetic_binding = binding
                break

        if not kinetic_binding:
            await ctx.connection.send_line(
                colorize(
                    "You need an active kinetic binding! Use 'bind kinetic <source> <target>' first.",
                    "YELLOW",
                )
            )
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

                success, actual_force, message = await execute_kinetic_transfer(
                    kinetic_binding, force_amount, character, session
                )

                await session.commit()

                color = "GREEN" if success else "YELLOW"
                await ctx.connection.send_line(colorize(message, color))

                if success:
                    # Broadcast to room
                    ctx.engine.broadcast_to_room(
                        character.current_room_id,
                        colorize(
                            f"\n{character.name} gestures and something shifts through sympathetic force!",
                            "CYAN",
                        ),
                        exclude=ctx.session.id,
                    )

        except Exception as e:
            logger.error("push_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Failed to push.", "RED"))


class HeatCommand(Command):
    """Use heat sympathy to transfer heat."""

    name = "heat"
    aliases = ["warm", "freeze"]
    help_text = "heat [amount] - Transfer heat through active binding"
    min_args = 0

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the heat command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        # Parse optional heat amount (target is determined by active binding)
        heat_amount = 100  # Default heat transfer
        if ctx.args:
            try:
                heat_amount = int(ctx.args[0])
            except ValueError:
                pass

        bindings = get_active_bindings(ctx.session.character_id)

        # Find a heat binding
        heat_binding = None
        for binding in bindings:
            if binding.binding_type == BindingType.HEAT_TRANSFER:
                heat_binding = binding
                break

        if not heat_binding:
            await ctx.connection.send_line(
                colorize(
                    "You need an active heat binding! Use 'bind heat <source> <target>' first.",
                    "YELLOW",
                )
            )
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

                success, actual_transfer, message = await execute_heat_transfer(
                    heat_binding, heat_amount, character, session
                )

                await session.commit()

                color = "GREEN" if success else "YELLOW"
                await ctx.connection.send_line(colorize(message, color))

                if success:
                    ctx.engine.broadcast_to_room(
                        character.current_room_id,
                        colorize(
                            f"\n{character.name} concentrates, and heat flows through an invisible link.",
                            "CYAN",
                        ),
                        exclude=ctx.session.id,
                    )

        except Exception as e:
            logger.error("heat_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Failed to transfer heat.", "RED"))


class CastCommand(Command):
    """Use sympathy in combat to deal damage."""

    name = "cast"
    aliases = []
    help_text = "cast damage <target> - Attack with sympathetic damage"
    min_args = 2

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the cast command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        cast_type = ctx.args[0].lower()
        target_name = " ".join(ctx.args[1:]).lower()

        if cast_type != "damage":
            await ctx.connection.send_line(colorize("Usage: cast damage <target>", "YELLOW"))
            return

        bindings = get_active_bindings(ctx.session.character_id)

        # Find a damage binding
        damage_binding = None
        for binding in bindings:
            if binding.binding_type == BindingType.DAMAGE_TRANSFER:
                damage_binding = binding
                break

        if not damage_binding:
            await ctx.connection.send_line(
                colorize(
                    "You need an active damage binding! Use 'bind damage <source> <target>' first.",
                    "YELLOW",
                )
            )
            return

        try:
            async with get_session() as session:
                # Get caster
                caster_result = await session.execute(
                    select(Character).where(Character.id == UUID(ctx.session.character_id))
                )
                caster = caster_result.scalar_one_or_none()

                if not caster:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                # Get target character
                room = ctx.engine.world.get(caster.current_room_id)
                target = None

                if room:
                    for player_id in room.players:
                        if player_id != ctx.session.character_id:
                            target_result = await session.execute(
                                select(Character).where(Character.id == UUID(player_id))
                            )
                            potential_target = target_result.scalar_one_or_none()
                            if potential_target and target_name in potential_target.name.lower():
                                target = potential_target
                                break

                if not target:
                    await ctx.connection.send_line(
                        colorize(f"Cannot find target '{target_name}'.", "YELLOW")
                    )
                    return

                # Calculate base damage based on sympathy rank
                sympathy_rank = get_sympathy_rank(caster)
                base_damage = 10 + (sympathy_rank * 5)

                # Check for backlash risk
                energy_source = _active_energy_sources.get(ctx.session.character_id)
                if energy_source:
                    energy_pct = damage_binding.energy_source.remaining_energy / max(
                        1, damage_binding.energy_source.max_energy
                    )
                    using_body = energy_source.source_type == HeatSourceType.BODY

                    backlash = check_for_backlash(
                        1.0 - energy_pct,  # Risk increases as energy depletes
                        using_body,
                        sympathy_rank,
                    )

                    if backlash:
                        await apply_backlash(backlash, caster, session, ctx.engine)
                        await session.commit()
                        return

                # Execute the damage transfer
                success, actual_damage, message = await execute_damage_transfer(
                    damage_binding, base_damage, caster, target, session
                )

                await session.commit()

                if success:
                    await ctx.connection.send_line(colorize(message, "GREEN"))

                    # Broadcast attack
                    ctx.engine.broadcast_to_room(
                        caster.current_room_id,
                        colorize(
                            f"\n{caster.name} channels sympathetic energy at {target.name}!\n"
                            f"{target.name} takes {actual_damage} damage! "
                            f"({target.current_hp}/{target.max_hp} HP)",
                            "RED",
                        ),
                        exclude=ctx.session.id,
                    )

                    # Check for death
                    if target.current_hp <= 0:
                        from waystone.game.systems.death import handle_player_death

                        await handle_player_death(
                            target.id,
                            caster.current_room_id,
                            ctx.engine,
                            session,
                        )
                else:
                    await ctx.connection.send_line(colorize(message, "YELLOW"))

        except Exception as e:
            logger.error("cast_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Failed to cast.", "RED"))
