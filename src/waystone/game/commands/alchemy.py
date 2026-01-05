"""Alchemy crafting commands for Waystone MUD."""

from uuid import UUID

import structlog
from sqlalchemy import select

from waystone.database.engine import get_session
from waystone.database.models import Character
from waystone.game.systems.magic.alchemy import (
    brew_potion,
    calculate_success_chance,
    check_medica_location,
    check_tools,
    get_character_alchemy_skill,
    get_recipe,
    load_alchemy_recipes,
)
from waystone.network import colorize

from .base import Command, CommandContext

logger = structlog.get_logger(__name__)


class BrewCommand(Command):
    """Brew an alchemical potion or concoction."""

    name = "brew"
    aliases = ["craft", "alchemy"]
    help_text = "brew <recipe> - Brew a potion using alchemy"
    extended_help = """
Alchemy allows you to create potions, salves, and other concoctions.

Usage:
  brew <recipe>     - Attempt to brew a specific recipe
  brew list         - Show available recipes
  brew info <recipe> - Show details about a recipe

Requirements:
  - You must have the required ingredients in your inventory
  - Higher Alchemy skill increases success chance
  - Tools like an alembic provide bonuses
  - The Medica provides +10% success bonus

Example:
  brew health_potion
  brew list
  brew info healing_salve
"""
    min_args = 1
    requires_character = True

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the brew command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to brew potions.", "RED")
            )
            return

        subcommand = ctx.args[0].lower()

        if subcommand == "list":
            await self._show_recipes(ctx)
        elif subcommand == "info" and len(ctx.args) > 1:
            await self._show_recipe_info(ctx, ctx.args[1])
        else:
            await self._brew_recipe(ctx, subcommand)

    async def _show_recipes(self, ctx: CommandContext) -> None:
        """Show available alchemy recipes."""
        try:
            async with get_session() as session:
                result = await session.execute(
                    select(Character).where(Character.id == UUID(ctx.session.character_id))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                skill_level = get_character_alchemy_skill(character)
                recipes = load_alchemy_recipes()

                await ctx.connection.send_line(colorize("\n╔═══ Alchemy Recipes ═══╗", "CYAN"))
                await ctx.connection.send_line(
                    f"Your Alchemy skill: {colorize(str(skill_level), 'GREEN')}"
                )
                await ctx.connection.send_line("")

                if not recipes:
                    await ctx.connection.send_line("No recipes available.")
                    return

                # Group by difficulty
                by_difficulty = {"easy": [], "medium": [], "hard": [], "master": []}
                for recipe in recipes.values():
                    difficulty = recipe.difficulty
                    if difficulty in by_difficulty:
                        by_difficulty[difficulty].append(recipe)

                for difficulty, recipe_list in by_difficulty.items():
                    if recipe_list:
                        color = {
                            "easy": "GREEN",
                            "medium": "YELLOW",
                            "hard": "ORANGE",
                            "master": "RED",
                        }.get(difficulty, "WHITE")
                        await ctx.connection.send_line(colorize(f"  [{difficulty.upper()}]", color))
                        for recipe in sorted(recipe_list, key=lambda r: r.skill_required):
                            status = ""
                            if recipe.skill_required > skill_level:
                                status = colorize(" [LOCKED]", "DIM")
                            elif recipe.illegal:
                                status = colorize(" [ILLEGAL]", "RED")
                            elif recipe.dangerous:
                                status = colorize(" [DANGER]", "ORANGE")

                            await ctx.connection.send_line(
                                f"    {recipe.id}: {recipe.name} "
                                f"(skill {recipe.skill_required}){status}"
                            )

                await ctx.connection.send_line(colorize("\n╚═══════════════════════╝", "CYAN"))
                await ctx.connection.send_line(
                    "Use " + colorize("brew info <recipe>", "CYAN") + " for details."
                )

        except Exception as e:
            logger.error("brew_list_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Failed to list recipes.", "RED"))

    async def _show_recipe_info(self, ctx: CommandContext, recipe_id: str) -> None:
        """Show detailed recipe information."""
        recipe = get_recipe(recipe_id)
        if not recipe:
            await ctx.connection.send_line(colorize(f"Unknown recipe: {recipe_id}", "RED"))
            await ctx.connection.send_line("Use 'brew list' to see available recipes.")
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

                has_alembic, has_mortar = await check_tools(character.id, session)

                # Get current room for medica check
                room_id = character.current_room_id
                in_medica = check_medica_location(room_id)

                success_chance = calculate_success_chance(
                    character, recipe, has_alembic, has_mortar, in_medica
                )

                await ctx.connection.send_line(colorize(f"\n╔═══ {recipe.name} ═══╗", "CYAN"))
                await ctx.connection.send_line(f"  {recipe.description}")
                await ctx.connection.send_line("")

                difficulty_color = {
                    "easy": "GREEN",
                    "medium": "YELLOW",
                    "hard": "ORANGE",
                    "master": "RED",
                }.get(recipe.difficulty, "WHITE")
                await ctx.connection.send_line(
                    f"  Difficulty: {colorize(recipe.difficulty.title(), difficulty_color)}"
                )
                await ctx.connection.send_line(f"  Skill Required: {recipe.skill_required}")
                await ctx.connection.send_line(f"  Base Success: {recipe.base_success_chance}%")
                await ctx.connection.send_line(
                    f"  Your Success Chance: {colorize(f'{success_chance}%', 'GREEN')}"
                )
                await ctx.connection.send_line("")
                await ctx.connection.send_line(colorize("  Ingredients:", "YELLOW"))

                for ing in recipe.ingredients:
                    item_name = ing.item_id.replace("_", " ").title()
                    await ctx.connection.send_line(f"    - {ing.quantity}x {item_name}")

                output_name = recipe.output_item.replace("_", " ").title()
                await ctx.connection.send_line("")
                await ctx.connection.send_line(
                    f"  Creates: {colorize(f'{recipe.output_quantity}x {output_name}', 'GREEN')}"
                )

                # Show bonuses
                await ctx.connection.send_line("")
                await ctx.connection.send_line(colorize("  Your Bonuses:", "YELLOW"))
                await ctx.connection.send_line(
                    f"    Alembic: {colorize('+5%', 'GREEN') if has_alembic else colorize('No', 'DIM')}"
                )
                await ctx.connection.send_line(
                    f"    Mortar & Pestle: {colorize('+3%', 'GREEN') if has_mortar else colorize('No', 'DIM')}"
                )
                await ctx.connection.send_line(
                    f"    Medica Location: {colorize('+10%', 'GREEN') if in_medica else colorize('No', 'DIM')}"
                )

                if recipe.dangerous:
                    await ctx.connection.send_line("")
                    await ctx.connection.send_line(
                        colorize("  ⚠️ WARNING: Dangerous recipe - mishaps may cause injury!", "RED")
                    )

                if recipe.illegal:
                    await ctx.connection.send_line("")
                    await ctx.connection.send_line(
                        colorize("  ⚠️ WARNING: Creating this item is illegal!", "RED")
                    )

                await ctx.connection.send_line(
                    colorize("\n╚" + "═" * (len(recipe.name) + 8) + "╝", "CYAN")
                )

        except Exception as e:
            logger.error("brew_info_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Failed to get recipe info.", "RED"))

    async def _brew_recipe(self, ctx: CommandContext, recipe_id: str) -> None:
        """Attempt to brew a recipe."""
        recipe = get_recipe(recipe_id)
        if not recipe:
            await ctx.connection.send_line(colorize(f"Unknown recipe: {recipe_id}", "RED"))
            await ctx.connection.send_line("Use 'brew list' to see available recipes.")
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

                await ctx.connection.send_line(
                    colorize(f"\nAttempting to brew {recipe.name}...", "CYAN")
                )

                # Perform the brew
                brew_result = await brew_potion(
                    character, recipe_id, character.current_room_id, session
                )

                if brew_result.success:
                    await ctx.connection.send_line(colorize(f"\n✨ {brew_result.message}", "GREEN"))
                else:
                    if brew_result.mishap:
                        await ctx.connection.send_line(
                            colorize(f"\n💥 {brew_result.message}", "RED")
                        )
                        # Apply mishap damage
                        character.current_hp = max(
                            1, character.current_hp - brew_result.mishap_damage
                        )
                        await session.commit()
                    else:
                        await ctx.connection.send_line(
                            colorize(f"\n❌ {brew_result.message}", "YELLOW")
                        )

                # Show XP gain
                if brew_result.xp_gained > 0:
                    await ctx.connection.send_line(
                        colorize(f"  +{brew_result.xp_gained} Alchemy XP", "CYAN")
                    )

                if brew_result.ranked_up:
                    await ctx.connection.send_line(
                        colorize("  🎉 Your Alchemy skill has improved!", "GREEN")
                    )

                logger.info(
                    "brew_attempt",
                    character_id=ctx.session.character_id,
                    recipe=recipe_id,
                    success=brew_result.success,
                    xp_gained=brew_result.xp_gained,
                )

        except Exception as e:
            logger.error("brew_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Brewing failed due to an error.", "RED"))


class RecipesCommand(Command):
    """List available alchemy recipes (shortcut for 'brew list')."""

    name = "recipes"
    aliases = []
    help_text = "recipes - List available alchemy recipes"
    min_args = 0
    requires_character = True

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the recipes command."""
        # Delegate to brew list
        brew_cmd = BrewCommand()
        ctx.args = ["list"]
        await brew_cmd.execute(ctx)
