"""Integration tests for complete gameplay flows.

These tests verify that the full gameplay experience works correctly,
from user registration through character creation, gameplay, and logout.
"""

import asyncio
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select

from waystone.database.engine import get_session, init_db
from waystone.database.models import Character, CharacterBackground, User
from waystone.game.commands.auth import LoginCommand, LogoutCommand, RegisterCommand
from waystone.game.commands.base import CommandContext, get_registry
from waystone.game.commands.character import CharactersCommand, PlayCommand
from waystone.game.commands.communication import ChatCommand, EmoteCommand, SayCommand
from waystone.game.commands.info import HelpCommand, ScoreCommand, WhoCommand
from waystone.game.commands.movement import (
    ExitsCommand,
    LookCommand,
    NorthCommand,
    SouthCommand,
)
from waystone.game.engine import GameEngine
from waystone.game.world import Room
from waystone.network import Connection, Session, SessionState


@pytest.fixture
async def integration_engine() -> AsyncGenerator[GameEngine, None]:
    """Create a game engine with a realistic test world."""
    await init_db()

    # Reset global registry before each test
    import waystone.game.commands.base as base_module

    base_module._registry = None

    engine = GameEngine()

    # Create a more realistic test world
    engine.world = {
        "waystone_inn": Room(
            id="waystone_inn",
            name="The Waystone Inn",
            area="newarre",
            description=(
                "You stand in the common room of the Waystone Inn. "
                "A crackling fire provides warmth against the autumn chill. "
                "The innkeeper, a red-haired man, polishes glasses behind the bar."
            ),
            exits={"north": "inn_kitchen", "east": "village_square", "up": "inn_rooms"},
        ),
        "inn_kitchen": Room(
            id="inn_kitchen",
            name="Inn Kitchen",
            area="newarre",
            description=(
                "The kitchen is warm and filled with the smell of baking bread. "
                "Copper pots hang from hooks above a well-used stove."
            ),
            exits={"south": "waystone_inn"},
        ),
        "village_square": Room(
            id="village_square",
            name="Newarre Village Square",
            area="newarre",
            description=(
                "The village square of Newarre is quiet and peaceful. "
                "A few villagers go about their daily business."
            ),
            exits={"west": "waystone_inn", "north": "village_road"},
        ),
        "village_road": Room(
            id="village_road",
            name="Village Road",
            area="newarre",
            description="A dusty road leads north out of the village.",
            exits={"south": "village_square"},
        ),
        "inn_rooms": Room(
            id="inn_rooms",
            name="Inn Guest Rooms",
            area="newarre",
            description="A hallway with several doors leading to guest rooms.",
            exits={"down": "waystone_inn"},
        ),
    }

    # Register commands
    engine._register_commands()

    yield engine

    # Cleanup
    await engine.stop()
    base_module._registry = None


def create_mock_connection() -> Connection:
    """Create a mock connection for testing."""
    connection = Mock(spec=Connection)
    connection.id = uuid.uuid4()
    connection.ip_address = "127.0.0.1"
    connection.send_line = AsyncMock()
    connection.send = AsyncMock()
    connection.readline = AsyncMock()
    connection.is_closed = False
    return connection


def create_mock_session(connection: Connection, engine: GameEngine | None = None) -> Session:
    """Create a mock session for testing.

    If engine is provided, registers the session with the session_manager
    so it appears in who lists and broadcasts.
    """
    if engine:
        # Use the real session manager to create the session
        session = engine.session_manager.create_session(connection)
    else:
        session = Session(connection)
    connection.session = session
    return session


def create_command_context(
    session: Session,
    connection: Connection,
    engine: GameEngine,
    args: list[str],
    raw_input: str,
) -> CommandContext:
    """Helper to create command contexts."""
    return CommandContext(
        session=session,
        connection=connection,
        engine=engine,
        args=args,
        raw_input=raw_input,
    )


def get_sent_messages(connection: Mock) -> list[str]:
    """Extract all messages sent to a mock connection."""
    return [str(call) for call in connection.send_line.call_args_list]


def assert_message_contains(connection: Mock, text: str) -> None:
    """Assert that any sent message contains the given text."""
    messages = get_sent_messages(connection)
    assert any(text.lower() in msg.lower() for msg in messages), (
        f"Expected message containing '{text}' but got: {messages}"
    )


class TestFullGameplayFlow:
    """Test complete gameplay flows from start to finish."""

    @pytest.mark.asyncio
    async def test_new_player_full_journey(self, integration_engine: GameEngine):
        """
        Test the complete journey of a new player:
        1. Register account
        2. Login
        3. Create character (pre-created for test)
        4. Play character
        5. Explore world
        6. Chat with others
        7. Logout
        """
        connection = create_mock_connection()
        # Use engine's session manager so "who" command can find our session
        session = create_mock_session(connection, integration_engine)
        unique_suffix = uuid.uuid4().hex[:8]

        # Step 1: Register a new account
        register_cmd = RegisterCommand()
        ctx = create_command_context(
            session,
            connection,
            integration_engine,
            [f"testplayer{unique_suffix}", "SecurePass123!", f"test{unique_suffix}@example.com"],
            f"register testplayer{unique_suffix} SecurePass123! test{unique_suffix}@example.com",
        )
        await register_cmd.execute(ctx)

        # Verify registration succeeded
        async with get_session() as db_session:
            result = await db_session.execute(
                select(User).where(User.username == f"testplayer{unique_suffix}")
            )
            user = result.scalar_one_or_none()
            assert user is not None
            assert user.verify_password("SecurePass123!")

        connection.send_line.reset_mock()

        # Step 2: Login with new account
        login_cmd = LoginCommand()
        ctx = create_command_context(
            session,
            connection,
            integration_engine,
            [f"testplayer{unique_suffix}", "SecurePass123!"],
            f"login testplayer{unique_suffix} SecurePass123!",
        )
        await login_cmd.execute(ctx)

        assert session.user_id is not None
        assert session.state == SessionState.AUTHENTICATING
        connection.send_line.reset_mock()

        # Step 3: Create character directly in database (bypassing interactive flow)
        char_name = f"Kvothe{unique_suffix}"
        async with get_session() as db_session:
            character = Character(
                user_id=uuid.UUID(session.user_id),
                name=char_name,
                background=CharacterBackground.SCHOLAR,
                current_room_id="waystone_inn",
                strength=10,
                dexterity=12,
                constitution=10,
                intelligence=14,
                wisdom=11,
                charisma=13,
            )
            db_session.add(character)
            await db_session.commit()
            char_id = str(character.id)

        # Step 4: List characters
        chars_cmd = CharactersCommand()
        ctx = create_command_context(
            session, connection, integration_engine, [], "characters"
        )
        await chars_cmd.execute(ctx)
        assert_message_contains(connection, char_name)
        connection.send_line.reset_mock()

        # Step 5: Play as character
        play_cmd = PlayCommand()
        ctx = create_command_context(
            session, connection, integration_engine, [char_name], f"play {char_name}"
        )
        await play_cmd.execute(ctx)

        assert session.character_id == char_id
        assert session.state == SessionState.PLAYING
        assert char_id in integration_engine.character_to_session
        assert_message_contains(connection, "Waystone Inn")
        connection.send_line.reset_mock()

        # Step 6: Look at current room
        look_cmd = LookCommand()
        ctx = create_command_context(
            session, connection, integration_engine, [], "look"
        )
        await look_cmd.execute(ctx)
        assert_message_contains(connection, "Waystone Inn")
        assert_message_contains(connection, "fire")
        connection.send_line.reset_mock()

        # Step 7: Check exits
        exits_cmd = ExitsCommand()
        ctx = create_command_context(
            session, connection, integration_engine, [], "exits"
        )
        await exits_cmd.execute(ctx)
        assert_message_contains(connection, "north")
        assert_message_contains(connection, "east")
        connection.send_line.reset_mock()

        # Step 8: Move north to kitchen
        north_cmd = NorthCommand()
        ctx = create_command_context(
            session, connection, integration_engine, [], "north"
        )
        await north_cmd.execute(ctx)
        assert_message_contains(connection, "Kitchen")
        assert char_id not in integration_engine.world["waystone_inn"].players
        assert char_id in integration_engine.world["inn_kitchen"].players
        connection.send_line.reset_mock()

        # Step 9: Move back south
        south_cmd = SouthCommand()
        ctx = create_command_context(
            session, connection, integration_engine, [], "south"
        )
        await south_cmd.execute(ctx)
        assert_message_contains(connection, "Waystone Inn")
        connection.send_line.reset_mock()

        # Step 10: Say something
        say_cmd = SayCommand()
        ctx = create_command_context(
            session,
            connection,
            integration_engine,
            ["Hello, is anyone there?"],
            "say Hello, is anyone there?",
        )
        await say_cmd.execute(ctx)
        assert_message_contains(connection, "Hello")
        connection.send_line.reset_mock()

        # Step 11: Emote an action
        emote_cmd = EmoteCommand()
        ctx = create_command_context(
            session,
            connection,
            integration_engine,
            ["looks around curiously"],
            "emote looks around curiously",
        )
        await emote_cmd.execute(ctx)
        assert_message_contains(connection, "curiously")
        connection.send_line.reset_mock()

        # Step 12: Check score
        score_cmd = ScoreCommand()
        ctx = create_command_context(
            session, connection, integration_engine, [], "score"
        )
        await score_cmd.execute(ctx)
        assert_message_contains(connection, char_name)
        assert_message_contains(connection, "Scholar")
        connection.send_line.reset_mock()

        # Step 13: Check who's online
        who_cmd = WhoCommand()
        ctx = create_command_context(
            session, connection, integration_engine, [], "who"
        )
        await who_cmd.execute(ctx)
        assert_message_contains(connection, char_name)
        connection.send_line.reset_mock()

        # Step 14: Logout
        logout_cmd = LogoutCommand()
        ctx = create_command_context(
            session, connection, integration_engine, [], "logout"
        )
        await logout_cmd.execute(ctx)

        assert session.user_id is None
        assert session.character_id is None
        assert session.state == SessionState.CONNECTED

    @pytest.mark.asyncio
    async def test_multiple_players_interaction(self, integration_engine: GameEngine):
        """Test multiple players interacting in the same room."""
        unique_suffix = uuid.uuid4().hex[:8]

        # Create two players
        conn1 = create_mock_connection()
        session1 = create_mock_session(conn1)

        conn2 = create_mock_connection()
        session2 = create_mock_session(conn2)

        # Create users and characters
        async with get_session() as db_session:
            user1 = User(
                username=f"player1_{unique_suffix}",
                email=f"p1_{unique_suffix}@example.com",
                password_hash=User.hash_password("pass123"),
            )
            user2 = User(
                username=f"player2_{unique_suffix}",
                email=f"p2_{unique_suffix}@example.com",
                password_hash=User.hash_password("pass456"),
            )
            db_session.add_all([user1, user2])
            await db_session.flush()

            char1 = Character(
                user_id=user1.id,
                name=f"Denna{unique_suffix}",
                background=CharacterBackground.PERFORMER,
                current_room_id="waystone_inn",
            )
            char2 = Character(
                user_id=user2.id,
                name=f"Bast{unique_suffix}",
                background=CharacterBackground.NOBLE,
                current_room_id="waystone_inn",
            )
            db_session.add_all([char1, char2])
            await db_session.commit()

            session1.set_user(str(user1.id))
            session2.set_user(str(user2.id))
            char1_id = str(char1.id)
            char2_id = str(char2.id)

        # Both players enter the game
        play_cmd = PlayCommand()

        ctx1 = create_command_context(
            session1,
            conn1,
            integration_engine,
            [f"Denna{unique_suffix}"],
            f"play Denna{unique_suffix}",
        )
        await play_cmd.execute(ctx1)

        ctx2 = create_command_context(
            session2,
            conn2,
            integration_engine,
            [f"Bast{unique_suffix}"],
            f"play Bast{unique_suffix}",
        )
        await play_cmd.execute(ctx2)

        # Both should be in the same room
        assert char1_id in integration_engine.world["waystone_inn"].players
        assert char2_id in integration_engine.world["waystone_inn"].players

        conn1.send_line.reset_mock()
        conn2.send_line.reset_mock()

        # Player 1 says something - should broadcast to player 2
        say_cmd = SayCommand()
        ctx = create_command_context(
            session1,
            conn1,
            integration_engine,
            ["Greetings, friend!"],
            "say Greetings, friend!",
        )
        await say_cmd.execute(ctx)

        # Wait for broadcast task
        await asyncio.sleep(0.1)

        # Player 2 should have received the message
        assert conn2.send_line.called

        conn1.send_line.reset_mock()
        conn2.send_line.reset_mock()

        # Player 2 moves away
        north_cmd = NorthCommand()
        ctx = create_command_context(
            session2, conn2, integration_engine, [], "north"
        )
        await north_cmd.execute(ctx)

        # Wait for broadcast
        await asyncio.sleep(0.1)

        # Player 1 should see departure message
        assert conn1.send_line.called

        # Players are now in different rooms
        assert char1_id in integration_engine.world["waystone_inn"].players
        assert char2_id in integration_engine.world["inn_kitchen"].players

    @pytest.mark.asyncio
    async def test_room_navigation_full_circuit(self, integration_engine: GameEngine):
        """Test navigating through all rooms and returning to start."""
        connection = create_mock_connection()
        session = create_mock_session(connection)
        unique_suffix = uuid.uuid4().hex[:8]

        # Create user and character
        async with get_session() as db_session:
            user = User(
                username=f"navigator_{unique_suffix}",
                email=f"nav_{unique_suffix}@example.com",
                password_hash=User.hash_password("navigate123"),
            )
            db_session.add(user)
            await db_session.flush()

            char = Character(
                user_id=user.id,
                name=f"Simmon{unique_suffix}",
                background=CharacterBackground.WAYFARER,
                current_room_id="waystone_inn",
            )
            db_session.add(char)
            await db_session.commit()

            session.set_user(str(user.id))
            char_id = str(char.id)

        # Play as character
        play_cmd = PlayCommand()
        ctx = create_command_context(
            session,
            connection,
            integration_engine,
            [f"Simmon{unique_suffix}"],
            f"play Simmon{unique_suffix}",
        )
        await play_cmd.execute(ctx)

        # Navigate: inn -> kitchen -> inn -> square -> road -> square -> inn
        movements = [
            ("north", "inn_kitchen", "Kitchen"),
            ("south", "waystone_inn", "Waystone"),
            ("east", "village_square", "Square"),
            ("north", "village_road", "Road"),
            ("south", "village_square", "Square"),
            ("west", "waystone_inn", "Waystone"),
        ]

        from waystone.game.commands.movement import (
            EastCommand,
            NorthCommand,
            SouthCommand,
            WestCommand,
        )

        direction_cmds = {
            "north": NorthCommand(),
            "south": SouthCommand(),
            "east": EastCommand(),
            "west": WestCommand(),
        }

        for direction, expected_room, expected_text in movements:
            connection.send_line.reset_mock()
            cmd = direction_cmds[direction]
            ctx = create_command_context(
                session, connection, integration_engine, [], direction
            )
            await cmd.execute(ctx)

            # Verify we're in the right room
            assert char_id in integration_engine.world[expected_room].players
            assert_message_contains(connection, expected_text)

    @pytest.mark.asyncio
    async def test_help_command(self, integration_engine: GameEngine):
        """Test that help command shows available commands."""
        connection = create_mock_connection()
        session = create_mock_session(connection)

        help_cmd = HelpCommand()
        ctx = create_command_context(
            session, connection, integration_engine, [], "help"
        )
        await help_cmd.execute(ctx)

        # Verify help shows key commands
        assert_message_contains(connection, "register")
        assert_message_contains(connection, "login")
        assert_message_contains(connection, "help")

    @pytest.mark.asyncio
    async def test_global_chat(self, integration_engine: GameEngine):
        """Test global chat between players in different rooms."""
        unique_suffix = uuid.uuid4().hex[:8]

        conn1 = create_mock_connection()
        session1 = create_mock_session(conn1, integration_engine)

        conn2 = create_mock_connection()
        session2 = create_mock_session(conn2, integration_engine)

        # Create users and characters in different rooms
        async with get_session() as db_session:
            user1 = User(
                username=f"chatter1_{unique_suffix}",
                email=f"chat1_{unique_suffix}@example.com",
                password_hash=User.hash_password("chat123"),
            )
            user2 = User(
                username=f"chatter2_{unique_suffix}",
                email=f"chat2_{unique_suffix}@example.com",
                password_hash=User.hash_password("chat456"),
            )
            db_session.add_all([user1, user2])
            await db_session.flush()

            # Put characters in different rooms
            char1 = Character(
                user_id=user1.id,
                name=f"Wilem{unique_suffix}",
                background=CharacterBackground.SCHOLAR,
                current_room_id="waystone_inn",
            )
            char2 = Character(
                user_id=user2.id,
                name=f"Fela{unique_suffix}",
                background=CharacterBackground.MERCHANT,
                current_room_id="village_square",
            )
            db_session.add_all([char1, char2])
            await db_session.commit()

            session1.set_user(str(user1.id))
            session2.set_user(str(user2.id))

        # Both players enter
        play_cmd = PlayCommand()

        ctx1 = create_command_context(
            session1,
            conn1,
            integration_engine,
            [f"Wilem{unique_suffix}"],
            f"play Wilem{unique_suffix}",
        )
        await play_cmd.execute(ctx1)

        ctx2 = create_command_context(
            session2,
            conn2,
            integration_engine,
            [f"Fela{unique_suffix}"],
            f"play Fela{unique_suffix}",
        )
        await play_cmd.execute(ctx2)

        conn1.send_line.reset_mock()
        conn2.send_line.reset_mock()

        # Player 1 uses global chat
        chat_cmd = ChatCommand()
        ctx = create_command_context(
            session1,
            conn1,
            integration_engine,
            ["Anyone found any interesting books lately?"],
            "chat Anyone found any interesting books lately?",
        )
        await chat_cmd.execute(ctx)

        # Wait for broadcast
        await asyncio.sleep(0.1)

        # Both should see the chat (global chat broadcasts to all online)
        assert_message_contains(conn1, "books")


class TestErrorHandling:
    """Test error handling in various scenarios."""

    @pytest.mark.asyncio
    async def test_login_before_register(self, integration_engine: GameEngine):
        """Test that login fails for non-existent user."""
        connection = create_mock_connection()
        session = create_mock_session(connection)

        login_cmd = LoginCommand()
        ctx = create_command_context(
            session,
            connection,
            integration_engine,
            ["nonexistent", "password"],
            "login nonexistent password",
        )
        await login_cmd.execute(ctx)

        # Session should not be authenticated
        assert session.user_id is None
        assert session.state == SessionState.CONNECTED

    @pytest.mark.asyncio
    async def test_play_nonexistent_character(self, integration_engine: GameEngine):
        """Test that playing a non-existent character fails gracefully."""
        connection = create_mock_connection()
        session = create_mock_session(connection)
        unique_suffix = uuid.uuid4().hex[:8]

        # Create and login user
        async with get_session() as db_session:
            user = User(
                username=f"nochar_{unique_suffix}",
                email=f"nochar_{unique_suffix}@example.com",
                password_hash=User.hash_password("pass123"),
            )
            db_session.add(user)
            await db_session.commit()
            session.set_user(str(user.id))
            session.set_state(SessionState.AUTHENTICATING)

        play_cmd = PlayCommand()
        ctx = create_command_context(
            session,
            connection,
            integration_engine,
            ["NonExistent"],
            "play NonExistent",
        )
        await play_cmd.execute(ctx)

        # Should still be in character select, not playing
        assert session.state == SessionState.AUTHENTICATING
        assert session.character_id is None

    @pytest.mark.asyncio
    async def test_movement_invalid_direction(self, integration_engine: GameEngine):
        """Test that moving in an invalid direction fails gracefully."""
        connection = create_mock_connection()
        session = create_mock_session(connection)
        unique_suffix = uuid.uuid4().hex[:8]

        # Create user and character
        async with get_session() as db_session:
            user = User(
                username=f"stuck_{unique_suffix}",
                email=f"stuck_{unique_suffix}@example.com",
                password_hash=User.hash_password("stuck123"),
            )
            db_session.add(user)
            await db_session.flush()

            char = Character(
                user_id=user.id,
                name=f"Stuck{unique_suffix}",
                background=CharacterBackground.WAYFARER,
                current_room_id="inn_kitchen",  # Only exit is south
            )
            db_session.add(char)
            await db_session.commit()

            session.set_user(str(user.id))
            char_id = str(char.id)

        # Play character
        play_cmd = PlayCommand()
        ctx = create_command_context(
            session,
            connection,
            integration_engine,
            [f"Stuck{unique_suffix}"],
            f"play Stuck{unique_suffix}",
        )
        await play_cmd.execute(ctx)

        connection.send_line.reset_mock()

        # Try to go north (no exit)
        north_cmd = NorthCommand()
        ctx = create_command_context(
            session, connection, integration_engine, [], "north"
        )
        await north_cmd.execute(ctx)

        # Character should still be in kitchen
        assert char_id in integration_engine.world["inn_kitchen"].players

    @pytest.mark.asyncio
    async def test_commands_require_login(self, integration_engine: GameEngine):
        """Test that character commands require login."""
        connection = create_mock_connection()
        session = create_mock_session(connection)

        # Not logged in - try to list characters
        chars_cmd = CharactersCommand()
        ctx = create_command_context(
            session, connection, integration_engine, [], "characters"
        )
        await chars_cmd.execute(ctx)

        # Should get error message
        assert_message_contains(connection, "logged in")

    @pytest.mark.asyncio
    async def test_duplicate_registration(self, integration_engine: GameEngine):
        """Test that duplicate username registration fails."""
        connection = create_mock_connection()
        session = create_mock_session(connection)
        unique_suffix = uuid.uuid4().hex[:8]

        # Register first user
        register_cmd = RegisterCommand()
        ctx = create_command_context(
            session,
            connection,
            integration_engine,
            [f"duplicate_{unique_suffix}", "pass123", f"dup1_{unique_suffix}@example.com"],
            f"register duplicate_{unique_suffix} pass123 dup1_{unique_suffix}@example.com",
        )
        await register_cmd.execute(ctx)

        # Reset for second attempt
        connection.send_line.reset_mock()
        session2 = create_mock_session(create_mock_connection())

        # Try to register same username
        ctx2 = create_command_context(
            session2,
            session2.connection,
            integration_engine,
            [f"duplicate_{unique_suffix}", "pass456", f"dup2_{unique_suffix}@example.com"],
            f"register duplicate_{unique_suffix} pass456 dup2_{unique_suffix}@example.com",
        )
        await register_cmd.execute(ctx2)

        # Should fail with error message
        assert_message_contains(session2.connection, "already")
