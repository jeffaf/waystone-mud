"""Alchemy crafting system for Waystone MUD.

Implements potion brewing and alchemical crafting based on
the Kingkiller Chronicle universe.
"""

import pathlib
import random
from dataclasses import dataclass
from uuid import UUID

import structlog
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waystone.database.models import Character
from waystone.database.models.item import ItemInstance
from waystone.game.character.skills import gain_skill_xp

logger = structlog.get_logger(__name__)

# Skill name used for alchemy
ALCHEMY_SKILL = "alchemy"

# Maximum success chance cap
MAX_SUCCESS_CHANCE = 95

# Bonus from tools
TOOL_BONUSES = {
    "alembic": 5,
    "mortar_pestle": 3,
}

# Bonus from being in a special location (like the Medica)
MEDICA_ROOMS = ["university_medica", "medica_main", "medica_lab"]
MEDICA_BONUS = 10


@dataclass
class AlchemyIngredient:
    """Represents an ingredient requirement in a recipe."""

    item_id: str
    quantity: int


@dataclass
class AlchemyRecipe:
    """Represents an alchemy recipe."""

    id: str
    name: str
    description: str
    difficulty: str
    skill_required: int
    base_success_chance: int
    ingredients: list[AlchemyIngredient]
    output_item: str
    output_quantity: int
    xp_reward: int
    fail_xp: int
    dangerous: bool = False
    illegal: bool = False


@dataclass
class BrewResult:
    """Result of an alchemy brewing attempt."""

    success: bool
    message: str
    item_created: str | None = None
    xp_gained: int = 0
    ranked_up: bool = False
    mishap: bool = False
    mishap_damage: int = 0


# Cache for loaded recipes
_recipe_cache: dict[str, AlchemyRecipe] | None = None


def _get_recipe_path() -> pathlib.Path:
    """Get the path to the alchemy recipes YAML file."""
    return (
        pathlib.Path(__file__).parent.parent.parent.parent.parent
        / "data"
        / "config"
        / "alchemy_recipes.yaml"
    )


def load_alchemy_recipes() -> dict[str, AlchemyRecipe]:
    """Load alchemy recipes from YAML configuration.

    Returns:
        Dictionary mapping recipe ID to AlchemyRecipe objects
    """
    global _recipe_cache

    if _recipe_cache is not None:
        return _recipe_cache

    recipe_path = _get_recipe_path()
    if not recipe_path.exists():
        logger.warning("alchemy_recipes_not_found", path=str(recipe_path))
        return {}

    with open(recipe_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    recipes: dict[str, AlchemyRecipe] = {}

    if not data or "recipes" not in data:
        return recipes

    for recipe_data in data["recipes"]:
        ingredients = [
            AlchemyIngredient(item_id=ing["item"], quantity=ing["quantity"])
            for ing in recipe_data.get("ingredients", [])
        ]

        recipe = AlchemyRecipe(
            id=recipe_data["id"],
            name=recipe_data["name"],
            description=recipe_data.get("description", ""),
            difficulty=recipe_data.get("difficulty", "medium"),
            skill_required=recipe_data.get("skill_required", 0),
            base_success_chance=recipe_data.get("base_success_chance", 50),
            ingredients=ingredients,
            output_item=recipe_data["output"]["item"],
            output_quantity=recipe_data["output"].get("quantity", 1),
            xp_reward=recipe_data.get("xp_reward", 20),
            fail_xp=recipe_data.get("fail_xp", 5),
            dangerous=recipe_data.get("dangerous", False),
            illegal=recipe_data.get("illegal", False),
        )
        recipes[recipe.id] = recipe

    _recipe_cache = recipes
    logger.info("alchemy_recipes_loaded", count=len(recipes))
    return recipes


def get_recipe(recipe_id: str) -> AlchemyRecipe | None:
    """Get a specific recipe by ID.

    Args:
        recipe_id: The recipe identifier

    Returns:
        AlchemyRecipe if found, None otherwise
    """
    recipes = load_alchemy_recipes()
    return recipes.get(recipe_id)


def get_available_recipes(alchemy_skill: int) -> list[AlchemyRecipe]:
    """Get recipes available at a given skill level.

    Args:
        alchemy_skill: Character's alchemy skill level

    Returns:
        List of recipes the character can attempt
    """
    recipes = load_alchemy_recipes()
    return [r for r in recipes.values() if r.skill_required <= alchemy_skill]


def get_character_alchemy_skill(character: Character) -> int:
    """Get character's alchemy skill level.

    Args:
        character: The character to check

    Returns:
        Alchemy skill level (0 if untrained)
    """
    if not character.skills or ALCHEMY_SKILL not in character.skills:
        return 0

    skill_data = character.skills.get(ALCHEMY_SKILL, {})
    # Skill level is rank * 10 + xp/10 (approximate)
    rank: int = skill_data.get("rank", 0)
    xp: int = skill_data.get("xp", 0)
    return rank * 10 + min(xp // 10, 9)


def calculate_success_chance(
    character: Character,
    recipe: AlchemyRecipe,
    has_alembic: bool = False,
    has_mortar: bool = False,
    in_medica: bool = False,
) -> int:
    """Calculate the success chance for brewing a recipe.

    Args:
        character: The brewing character
        recipe: The recipe being attempted
        has_alembic: Whether character has an alembic
        has_mortar: Whether character has mortar and pestle
        in_medica: Whether character is in the Medica

    Returns:
        Success chance as a percentage (0-95)
    """
    skill_level = get_character_alchemy_skill(character)

    # Base chance + skill bonus
    skill_diff = skill_level - recipe.skill_required
    chance = recipe.base_success_chance + int(skill_diff * 1.5)

    # Tool bonuses
    if has_alembic:
        chance += TOOL_BONUSES["alembic"]
    if has_mortar:
        chance += TOOL_BONUSES["mortar_pestle"]

    # Location bonus
    if in_medica:
        chance += MEDICA_BONUS

    # Cap at maximum
    return max(0, min(MAX_SUCCESS_CHANCE, chance))


async def check_ingredients(
    character_id: UUID,
    recipe: AlchemyRecipe,
    session: AsyncSession,
) -> tuple[bool, str, dict[str, list[ItemInstance]]]:
    """Check if a character has the required ingredients.

    Args:
        character_id: Character's UUID
        recipe: The recipe to check
        session: Database session

    Returns:
        Tuple of (has_all, message, ingredient_items)
        - has_all: Whether all ingredients are present
        - message: Error message if missing ingredients
        - ingredient_items: Dict mapping item_id to list of ItemInstance objects
    """
    ingredient_items: dict[str, list[ItemInstance]] = {}
    missing: list[str] = []

    for ingredient in recipe.ingredients:
        # Find items of this type owned by character
        result = await session.execute(
            select(ItemInstance).where(
                ItemInstance.owner_id == character_id,
                ItemInstance.template_id == ingredient.item_id,
            )
        )
        items = list(result.scalars().all())

        # Calculate total quantity
        total_qty = sum(item.quantity for item in items)

        if total_qty < ingredient.quantity:
            item_name = ingredient.item_id.replace("_", " ").title()
            missing.append(f"{ingredient.quantity}x {item_name} (have {total_qty})")
        else:
            ingredient_items[ingredient.item_id] = items

    if missing:
        return False, "Missing ingredients: " + ", ".join(missing), {}

    return True, "", ingredient_items


async def consume_ingredients(
    recipe: AlchemyRecipe,
    ingredient_items: dict[str, list[ItemInstance]],
    session: AsyncSession,
) -> None:
    """Consume ingredients from character's inventory.

    Args:
        recipe: The recipe being crafted
        ingredient_items: Dict of item instances to consume from
        session: Database session
    """
    for ingredient in recipe.ingredients:
        items = ingredient_items.get(ingredient.item_id, [])
        remaining = ingredient.quantity

        for item in items:
            if remaining <= 0:
                break

            if item.quantity <= remaining:
                # Consume entire stack
                remaining -= item.quantity
                await session.delete(item)
            else:
                # Partial consumption
                item.quantity -= remaining
                remaining = 0

    await session.flush()


async def check_tools(
    character_id: UUID,
    session: AsyncSession,
) -> tuple[bool, bool]:
    """Check what alchemy tools a character has.

    Args:
        character_id: Character's UUID
        session: Database session

    Returns:
        Tuple of (has_alembic, has_mortar)
    """
    result = await session.execute(
        select(ItemInstance.template_id).where(
            ItemInstance.owner_id == character_id,
            ItemInstance.template_id.in_(["alembic", "mortar_pestle"]),
        )
    )
    tools = set(result.scalars().all())

    return "alembic" in tools, "mortar_pestle" in tools


def check_medica_location(room_id: str) -> bool:
    """Check if a room is in the Medica.

    Args:
        room_id: Room identifier

    Returns:
        True if room is a Medica location
    """
    return room_id in MEDICA_ROOMS or "medica" in room_id.lower()


async def brew_potion(
    character: Character,
    recipe_id: str,
    room_id: str,
    session: AsyncSession,
) -> BrewResult:
    """Attempt to brew a potion.

    Args:
        character: The brewing character
        recipe_id: ID of the recipe to brew
        room_id: Current room ID
        session: Database session

    Returns:
        BrewResult with outcome details
    """
    # Get recipe
    recipe = get_recipe(recipe_id)
    if not recipe:
        return BrewResult(
            success=False,
            message=f"Unknown recipe: {recipe_id}",
        )

    # Check skill requirement
    skill_level = get_character_alchemy_skill(character)
    if skill_level < recipe.skill_required:
        return BrewResult(
            success=False,
            message=f"You need Alchemy skill {recipe.skill_required} to brew {recipe.name}. "
            f"Your current skill is {skill_level}.",
        )

    # Check ingredients
    has_ingredients, missing_msg, ingredient_items = await check_ingredients(
        character.id, recipe, session
    )
    if not has_ingredients:
        return BrewResult(success=False, message=missing_msg)

    # Check tools
    has_alembic, has_mortar = await check_tools(character.id, session)

    # Check location
    in_medica = check_medica_location(room_id)

    # Calculate success chance
    success_chance = calculate_success_chance(character, recipe, has_alembic, has_mortar, in_medica)

    # Roll for success
    roll = random.randint(1, 100)
    success = roll <= success_chance

    # Consume ingredients (always, even on failure)
    await consume_ingredients(recipe, ingredient_items, session)

    # Determine XP
    xp_amount = recipe.xp_reward if success else recipe.fail_xp

    # Grant skill XP
    _, ranked_up = await gain_skill_xp(character, ALCHEMY_SKILL, xp_amount, session)

    if success:
        # Create output item
        new_item = ItemInstance(
            template_id=recipe.output_item,
            owner_id=character.id,
            quantity=recipe.output_quantity,
        )
        session.add(new_item)
        await session.commit()

        item_name = recipe.output_item.replace("_", " ").title()
        return BrewResult(
            success=True,
            message=f"Success! You have crafted {recipe.output_quantity}x {item_name}.",
            item_created=recipe.output_item,
            xp_gained=xp_amount,
            ranked_up=ranked_up,
        )
    else:
        # Check for mishap on dangerous recipes
        mishap = False
        mishap_damage = 0
        if recipe.dangerous and random.randint(1, 100) <= 10:
            mishap = True
            mishap_damage = random.randint(5, 15)

        await session.commit()

        if mishap:
            return BrewResult(
                success=False,
                message=f"The brewing fails and the mixture reacts violently! "
                f"You take {mishap_damage} damage from the mishap.",
                xp_gained=xp_amount,
                ranked_up=ranked_up,
                mishap=True,
                mishap_damage=mishap_damage,
            )

        return BrewResult(
            success=False,
            message="The brewing fails. Your ingredients are ruined, "
            "but you learn from the experience.",
            xp_gained=xp_amount,
            ranked_up=ranked_up,
        )


def format_recipe_list(recipes: list[AlchemyRecipe], skill_level: int) -> list[str]:
    """Format a list of recipes for display.

    Args:
        recipes: List of recipes to format
        skill_level: Character's current skill level

    Returns:
        List of formatted strings
    """
    lines = []
    for recipe in sorted(recipes, key=lambda r: r.skill_required):
        status = ""
        if recipe.skill_required > skill_level:
            status = " [LOCKED]"
        elif recipe.illegal:
            status = " [ILLEGAL]"
        elif recipe.dangerous:
            status = " [DANGEROUS]"

        lines.append(f"  {recipe.id}: {recipe.name} ({recipe.difficulty}){status}")

    return lines


def format_recipe_detail(recipe: AlchemyRecipe) -> list[str]:
    """Format detailed recipe information.

    Args:
        recipe: Recipe to format

    Returns:
        List of formatted strings
    """
    lines = [
        f"=== {recipe.name} ===",
        f"  {recipe.description}",
        f"  Difficulty: {recipe.difficulty.title()}",
        f"  Skill Required: {recipe.skill_required}",
        f"  Base Success: {recipe.base_success_chance}%",
        "",
        "  Ingredients:",
    ]

    for ing in recipe.ingredients:
        item_name = ing.item_id.replace("_", " ").title()
        lines.append(f"    - {ing.quantity}x {item_name}")

    output_name = recipe.output_item.replace("_", " ").title()
    lines.append("")
    lines.append(f"  Creates: {recipe.output_quantity}x {output_name}")

    if recipe.dangerous:
        lines.append("")
        lines.append("  WARNING: Dangerous recipe - mishaps may cause injury!")

    if recipe.illegal:
        lines.append("")
        lines.append("  WARNING: Creating this item is illegal!")

    return lines
