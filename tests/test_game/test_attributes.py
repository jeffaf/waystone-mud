"""Tests for character attributes and derived stats system."""

from sqlalchemy.ext.asyncio import AsyncSession

from waystone.database.models import Character, CharacterBackground
from waystone.game.character.attributes import (
    apply_attribute_bonuses,
    calculate_derived_stats,
    calculate_modifiers,
    get_background_bonuses,
    get_modifier,
    get_total_attributes_with_equipment,
)


class TestAttributeModifiers:
    """Tests for D&D-style attribute modifier calculations."""

    def test_modifier_average_value(self):
        """Test modifier for average attribute (10-11)."""
        assert get_modifier(10) == 0
        assert get_modifier(11) == 0

    def test_modifier_high_values(self):
        """Test modifiers for high attributes."""
        assert get_modifier(12) == 1
        assert get_modifier(14) == 2
        assert get_modifier(16) == 3
        assert get_modifier(18) == 4
        assert get_modifier(20) == 5

    def test_modifier_low_values(self):
        """Test modifiers for low attributes."""
        assert get_modifier(8) == -1
        assert get_modifier(6) == -2
        assert get_modifier(4) == -3
        assert get_modifier(2) == -4
        assert get_modifier(1) == -5  # (1 - 10) // 2 = -9 // 2 = -5

    def test_modifier_exceptional_values(self):
        """Test modifiers for exceptional attributes."""
        assert get_modifier(22) == 6
        assert get_modifier(24) == 7
        assert get_modifier(30) == 10

    def test_modifier_formula(self):
        """Verify modifier follows (value - 10) // 2 formula."""
        for value in range(1, 31):
            expected = (value - 10) // 2
            assert get_modifier(value) == expected


class TestBackgroundBonuses:
    """Tests for character background attribute bonuses."""

    def test_scholar_bonuses(self):
        """Scholar gets +2 INT from years of study."""
        bonuses = get_background_bonuses(CharacterBackground.SCHOLAR)
        assert bonuses == {"intelligence": 2}

    def test_merchant_bonuses(self):
        """Merchant gets +1 CHA, +1 WIS from negotiation."""
        bonuses = get_background_bonuses(CharacterBackground.MERCHANT)
        assert bonuses == {"charisma": 1, "wisdom": 1}

    def test_performer_bonuses(self):
        """Performer gets +2 CHA from social grace."""
        bonuses = get_background_bonuses(CharacterBackground.PERFORMER)
        assert bonuses == {"charisma": 2}

    def test_wayfarer_bonuses(self):
        """Wayfarer gets +1 DEX, +1 CON from travel."""
        bonuses = get_background_bonuses(CharacterBackground.WAYFARER)
        assert bonuses == {"dexterity": 1, "constitution": 1}

    def test_noble_bonuses(self):
        """Noble gets +1 INT, +1 CHA from education."""
        bonuses = get_background_bonuses(CharacterBackground.NOBLE)
        assert bonuses == {"intelligence": 1, "charisma": 1}

    def test_commoner_bonuses(self):
        """Commoner gets +1 CON, +1 STR from labor."""
        bonuses = get_background_bonuses(CharacterBackground.COMMONER)
        assert bonuses == {"constitution": 1, "strength": 1}


class TestCalculateModifiers:
    """Tests for calculating all character modifiers."""

    async def test_all_average_attributes(self, test_character):
        """Test character with all attributes at 10."""
        mods = calculate_modifiers(test_character)
        assert mods.strength == 0
        assert mods.dexterity == 0
        assert mods.constitution == 0
        assert mods.intelligence == 0
        assert mods.wisdom == 0
        assert mods.charisma == 0

    async def test_varied_attributes(self, db_session: AsyncSession, test_user):
        """Test character with varied attribute values."""
        character = Character(
            user_id=test_user.id,
            name="VariedChar",
            background=CharacterBackground.SCHOLAR,
            current_room_id="test_room",
            strength=8,  # -1 mod
            dexterity=14,  # +2 mod
            constitution=12,  # +1 mod
            intelligence=18,  # +4 mod
            wisdom=10,  # 0 mod
            charisma=16,  # +3 mod
        )
        db_session.add(character)
        await db_session.commit()
        await db_session.refresh(character)

        mods = calculate_modifiers(character)
        assert mods.strength == -1
        assert mods.dexterity == 2
        assert mods.constitution == 1
        assert mods.intelligence == 4
        assert mods.wisdom == 0
        assert mods.charisma == 3


class TestDerivedStats:
    """Tests for derived stat calculations."""

    async def test_hp_calculation_level_1(self, test_character):
        """Test HP calculation: 10 + (CON mod * level) + level."""
        test_character.level = 1
        test_character.constitution = 14  # +2 mod
        stats = calculate_derived_stats(test_character)
        # 10 + (2 * 1) + 1 = 13
        assert stats["max_hp"] == 13

    async def test_hp_calculation_level_5(self, test_character):
        """Test HP calculation at higher level."""
        test_character.level = 5
        test_character.constitution = 16  # +3 mod
        stats = calculate_derived_stats(test_character)
        # 10 + (3 * 5) + 5 = 30
        assert stats["max_hp"] == 30

    async def test_hp_calculation_low_con(self, test_character):
        """Test HP calculation with low constitution."""
        test_character.level = 3
        test_character.constitution = 8  # -1 mod
        stats = calculate_derived_stats(test_character)
        # 10 + (-1 * 3) + 3 = 10
        assert stats["max_hp"] == 10

    async def test_mp_calculation_level_1(self, test_character):
        """Test MP (Alar) calculation: 5 + (INT mod * level) + (WIS mod * level // 2)."""
        test_character.level = 1
        test_character.intelligence = 16  # +3 mod
        test_character.wisdom = 14  # +2 mod
        stats = calculate_derived_stats(test_character)
        # 5 + (3 * 1) + (2 * 1 // 2) = 5 + 3 + 1 = 9
        assert stats["max_mp"] == 9

    async def test_mp_calculation_level_5(self, test_character):
        """Test MP calculation at higher level."""
        test_character.level = 5
        test_character.intelligence = 18  # +4 mod
        test_character.wisdom = 16  # +3 mod
        stats = calculate_derived_stats(test_character)
        # 5 + (4 * 5) + (3 * 5 // 2) = 5 + 20 + 7 = 32
        assert stats["max_mp"] == 32

    async def test_mp_calculation_low_mental_stats(self, test_character):
        """Test MP calculation with low mental attributes."""
        test_character.level = 2
        test_character.intelligence = 8  # -1 mod
        test_character.wisdom = 8  # -1 mod
        stats = calculate_derived_stats(test_character)
        # 5 + (-1 * 2) + (-1 * 2 // 2) = 5 + (-2) + (-1) = 2
        assert stats["max_mp"] == 2

    async def test_attack_bonus_melee(self, test_character):
        """Test melee attack bonus equals STR modifier."""
        test_character.strength = 16  # +3 mod
        stats = calculate_derived_stats(test_character)
        assert stats["attack_bonus"] == 3

    async def test_attack_bonus_ranged(self, test_character):
        """Test ranged attack bonus equals DEX modifier."""
        test_character.dexterity = 18  # +4 mod
        stats = calculate_derived_stats(test_character)
        assert stats["ranged_attack_bonus"] == 4

    async def test_defense_calculation(self, test_character):
        """Test defense: 10 + DEX modifier."""
        test_character.dexterity = 14  # +2 mod
        stats = calculate_derived_stats(test_character)
        assert stats["defense"] == 12

    async def test_defense_low_dex(self, test_character):
        """Test defense with low dexterity."""
        test_character.dexterity = 6  # -2 mod
        stats = calculate_derived_stats(test_character)
        assert stats["defense"] == 8

    async def test_carry_capacity(self, test_character):
        """Test carry capacity: 10 + (STR * 5) pounds."""
        test_character.strength = 14
        stats = calculate_derived_stats(test_character)
        # 10 + (14 * 5) = 80
        assert stats["carry_capacity"] == 80

    async def test_carry_capacity_high_str(self, test_character):
        """Test carry capacity with high strength."""
        test_character.strength = 20
        stats = calculate_derived_stats(test_character)
        # 10 + (20 * 5) = 110
        assert stats["carry_capacity"] == 110

    async def test_all_derived_stats_average(self, test_character):
        """Test all derived stats with average attributes."""
        test_character.level = 1
        test_character.strength = 10
        test_character.dexterity = 10
        test_character.constitution = 10
        test_character.intelligence = 10
        test_character.wisdom = 10

        stats = calculate_derived_stats(test_character)

        # All modifiers are 0 for attribute 10
        assert stats["max_hp"] == 11  # 10 + (0 * 1) + 1
        assert stats["max_mp"] == 5  # 5 + (0 * 1) + (0 * 1 // 2)
        assert stats["attack_bonus"] == 0
        assert stats["ranged_attack_bonus"] == 0
        assert stats["defense"] == 10  # 10 + 0
        assert stats["carry_capacity"] == 60  # 10 + (10 * 5)


class TestEquipmentBonuses:
    """Tests for equipment attribute bonus application."""

    async def test_apply_no_bonuses(self, test_character):
        """Test applying empty equipment bonuses."""
        result = apply_attribute_bonuses(test_character, {})
        assert result["strength"] == 10
        assert result["dexterity"] == 10
        assert result["constitution"] == 10
        assert result["intelligence"] == 10
        assert result["wisdom"] == 10
        assert result["charisma"] == 10

    async def test_apply_strength_bonus(self, test_character):
        """Test applying strength bonus from equipment."""
        bonuses = {"strength": 2}
        result = apply_attribute_bonuses(test_character, bonuses)
        assert result["strength"] == 12
        assert result["dexterity"] == 10

    async def test_apply_multiple_bonuses(self, test_character):
        """Test applying multiple equipment bonuses."""
        bonuses = {
            "strength": 2,
            "dexterity": 1,
            "intelligence": 3,
        }
        result = apply_attribute_bonuses(test_character, bonuses)
        assert result["strength"] == 12
        assert result["dexterity"] == 11
        assert result["constitution"] == 10
        assert result["intelligence"] == 13
        assert result["wisdom"] == 10
        assert result["charisma"] == 10

    async def test_apply_all_bonuses(self, test_character):
        """Test applying bonuses to all attributes."""
        bonuses = {
            "strength": 1,
            "dexterity": 2,
            "constitution": 1,
            "intelligence": 3,
            "wisdom": 1,
            "charisma": 2,
        }
        result = apply_attribute_bonuses(test_character, bonuses)
        assert result["strength"] == 11
        assert result["dexterity"] == 12
        assert result["constitution"] == 11
        assert result["intelligence"] == 13
        assert result["wisdom"] == 11
        assert result["charisma"] == 12

    async def test_negative_bonuses(self, test_character):
        """Test applying negative bonuses (cursed items)."""
        bonuses = {
            "strength": -2,
            "wisdom": -1,
        }
        result = apply_attribute_bonuses(test_character, bonuses)
        assert result["strength"] == 8
        assert result["wisdom"] == 9


class TestTotalAttributesWithEquipment:
    """Tests for convenience function combining base and equipment bonuses."""

    async def test_total_attributes_no_equipment(self, test_character):
        """Test total attributes without equipment bonuses."""
        result = get_total_attributes_with_equipment(test_character)
        assert result["strength"] == 10
        assert result["intelligence"] == 10

    async def test_total_attributes_with_equipment(self, test_character):
        """Test total attributes with equipment bonuses."""
        equipment_bonuses = {
            "strength": 3,
            "intelligence": 2,
        }
        result = get_total_attributes_with_equipment(test_character, equipment_bonuses)
        assert result["strength"] == 13
        assert result["intelligence"] == 12

    async def test_total_attributes_none_bonuses(self, test_character):
        """Test function handles None equipment bonuses."""
        result = get_total_attributes_with_equipment(test_character, None)
        assert result["strength"] == 10


class TestIntegrationScenarios:
    """Integration tests combining multiple systems."""

    async def test_scholar_character_full_stats(self, db_session: AsyncSession, test_user):
        """Test complete stat calculation for a Scholar character."""
        character = Character(
            user_id=test_user.id,
            name="Kvothe",
            background=CharacterBackground.SCHOLAR,
            current_room_id="university_archives",
            strength=10,
            dexterity=14,
            constitution=12,
            intelligence=18,  # High INT for Scholar
            wisdom=14,
            charisma=16,
            level=3,
        )
        db_session.add(character)
        await db_session.commit()
        await db_session.refresh(character)

        stats = calculate_derived_stats(character)

        # Verify all derived stats
        # HP: 10 + (CON mod +1 * 3) + 3 = 16
        assert stats["max_hp"] == 16
        # MP: 5 + (INT mod +4 * 3) + (WIS mod +2 * 3 // 2) = 5 + 12 + 3 = 20
        assert stats["max_mp"] == 20
        # Attack: STR mod 0
        assert stats["attack_bonus"] == 0
        # Ranged: DEX mod +2
        assert stats["ranged_attack_bonus"] == 2
        # Defense: 10 + DEX mod +2 = 12
        assert stats["defense"] == 12
        # Carry: 10 + (10 * 5) = 60
        assert stats["carry_capacity"] == 60

    async def test_warrior_character_full_stats(self, db_session: AsyncSession, test_user):
        """Test complete stat calculation for a warrior-type character."""
        character = Character(
            user_id=test_user.id,
            name="Tempi",
            background=CharacterBackground.WAYFARER,
            current_room_id="stonebridge",
            strength=16,  # High STR for combat
            dexterity=14,
            constitution=16,  # High CON for HP
            intelligence=10,
            wisdom=12,
            charisma=8,
            level=5,
        )
        db_session.add(character)
        await db_session.commit()
        await db_session.refresh(character)

        stats = calculate_derived_stats(character)

        # Verify warrior-focused stats
        # HP: 10 + (CON mod +3 * 5) + 5 = 30
        assert stats["max_hp"] == 30
        # MP: 5 + (INT mod 0 * 5) + (WIS mod +1 * 5 // 2) = 5 + 0 + 2 = 7
        assert stats["max_mp"] == 7
        # Attack: STR mod +3
        assert stats["attack_bonus"] == 3
        # Defense: 10 + DEX mod +2 = 12
        assert stats["defense"] == 12
        # Carry: 10 + (16 * 5) = 90
        assert stats["carry_capacity"] == 90

    async def test_equipment_affects_derived_stats(self, db_session: AsyncSession, test_user):
        """Test that equipment bonuses affect derived stats through modifiers."""
        character = Character(
            user_id=test_user.id,
            name="TestWarrior",
            background=CharacterBackground.COMMONER,
            current_room_id="test_room",
            strength=14,  # +2 mod base
            dexterity=12,  # +1 mod base
            constitution=14,  # +2 mod base
            intelligence=10,
            wisdom=10,
            charisma=10,
            level=3,
        )
        db_session.add(character)
        await db_session.commit()
        await db_session.refresh(character)

        # Calculate base stats
        base_stats = calculate_derived_stats(character)
        assert base_stats["attack_bonus"] == 2  # STR +2
        assert base_stats["defense"] == 11  # 10 + DEX +1

        # Simulate equipment bonuses
        equipment_bonuses = {
            "strength": 2,  # Magic sword
            "dexterity": 2,  # Enchanted boots
        }
        total_attrs = apply_attribute_bonuses(character, equipment_bonuses)

        # Verify bonuses applied
        assert total_attrs["strength"] == 16  # 14 + 2 = 16 (+3 mod)
        assert total_attrs["dexterity"] == 14  # 12 + 2 = 14 (+2 mod)

        # Note: To get updated derived stats with equipment, you would need to
        # apply bonuses to a temporary character or recalculate with modified values
