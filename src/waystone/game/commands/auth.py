"""Authentication commands for Waystone MUD."""

import re

import structlog
from sqlalchemy import select

from waystone.database.engine import get_session
from waystone.database.models import User
from waystone.network import SessionState, colorize

from .base import Command, CommandContext

logger = structlog.get_logger(__name__)

# Username validation
USERNAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{2,19}$")
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


class RegisterCommand(Command):
    """Register a new user account."""

    name = "register"
    aliases = []
    help_text = "register <username> <password> <email> - Create a new account"
    min_args = 3
    requires_character = False

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the register command."""
        if len(ctx.args) < 3:
            await ctx.connection.send_line(
                colorize("Usage: register <username> <password> <email>", "YELLOW")
            )
            return

        username = ctx.args[0]
        password = ctx.args[1]
        email = ctx.args[2]

        # Validate username
        if not USERNAME_PATTERN.match(username):
            await ctx.connection.send_line(
                colorize(
                    "Invalid username. Must be 3-20 characters, start with a letter, "
                    "and contain only letters, numbers, and underscores.",
                    "RED"
                )
            )
            return

        # Validate password length
        if len(password) < 6:
            await ctx.connection.send_line(
                colorize("Password must be at least 6 characters long.", "RED")
            )
            return

        # Validate email
        if not EMAIL_PATTERN.match(email):
            await ctx.connection.send_line(
                colorize("Invalid email address.", "RED")
            )
            return

        # Create user in database
        try:
            async with get_session() as session:
                # Check if username exists
                result = await session.execute(
                    select(User).where(User.username == username)
                )
                if result.scalar_one_or_none():
                    await ctx.connection.send_line(
                        colorize(f"Username '{username}' is already taken.", "RED")
                    )
                    return

                # Check if email exists
                result = await session.execute(
                    select(User).where(User.email == email)
                )
                if result.scalar_one_or_none():
                    await ctx.connection.send_line(
                        colorize("Email address is already registered.", "RED")
                    )
                    return

                # Create new user
                new_user = User(
                    username=username,
                    email=email,
                    password_hash=User.hash_password(password),
                )
                session.add(new_user)
                await session.commit()

                await ctx.connection.send_line(
                    colorize(
                        f"\nAccount created successfully! Welcome, {username}!",
                        "GREEN"
                    )
                )
                await ctx.connection.send_line(
                    colorize("You can now log in with: ", "CYAN") +
                    colorize(f"login {username} <password>", "YELLOW")
                )

                logger.info(
                    "user_registered",
                    username=username,
                    email=email,
                    user_id=str(new_user.id),
                )

        except Exception as e:
            logger.error("registration_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Registration failed. Please try again.", "RED")
            )


class LoginCommand(Command):
    """Log into an existing account."""

    name = "login"
    aliases = []
    help_text = "login <username> <password> - Log into your account"
    min_args = 2
    requires_character = False

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the login command."""
        if len(ctx.args) < 2:
            await ctx.connection.send_line(
                colorize("Usage: login <username> <password>", "YELLOW")
            )
            return

        username = ctx.args[0]
        password = ctx.args[1]

        try:
            async with get_session() as session:
                # Find user by username
                result = await session.execute(
                    select(User).where(User.username == username)
                )
                user = result.scalar_one_or_none()

                if not user:
                    await ctx.connection.send_line(
                        colorize("Invalid username or password.", "RED")
                    )
                    return

                # Verify password
                if not user.verify_password(password):
                    await ctx.connection.send_line(
                        colorize("Invalid username or password.", "RED")
                    )
                    return

                # Set user in session
                ctx.session.set_user(str(user.id))
                ctx.session.set_state(SessionState.AUTHENTICATING)

                await ctx.connection.send_line(
                    colorize(f"\nWelcome back, {username}!", "GREEN")
                )
                await ctx.connection.send_line("")
                await ctx.connection.send_line(
                    "Type " + colorize("characters", "YELLOW") +
                    " to list your characters, or " +
                    colorize("create <name>", "YELLOW") +
                    " to create a new one."
                )

                logger.info(
                    "user_logged_in",
                    username=username,
                    user_id=str(user.id),
                    session_id=str(ctx.session.id),
                )

        except Exception as e:
            logger.error("login_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Login failed. Please try again.", "RED")
            )


class LogoutCommand(Command):
    """Log out and return to login prompt."""

    name = "logout"
    aliases = []
    help_text = "logout - Log out of your account"
    min_args = 0
    requires_character = False

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the logout command."""
        if ctx.session.character_id:
            # Remove character from room
            if ctx.session.character_id in ctx.engine.character_to_session:
                del ctx.engine.character_to_session[ctx.session.character_id]

        username = "player"
        if ctx.session.user_id:
            try:
                async with get_session() as session:
                    result = await session.execute(
                        select(User).where(User.id == ctx.session.user_id)
                    )
                    user = result.scalar_one_or_none()
                    if user:
                        username = user.username
            except Exception as e:
                logger.error("logout_user_lookup_failed", error=str(e))

        ctx.session.user_id = None
        ctx.session.character_id = None
        ctx.session.set_state(SessionState.CONNECTED)

        await ctx.connection.send_line(
            colorize(f"\nGoodbye, {username}!", "CYAN")
        )
        await ctx.connection.send_line(
            "Type " + colorize("login <username> <password>", "YELLOW") +
            " to log back in."
        )

        logger.info(
            "user_logged_out",
            username=username,
            session_id=str(ctx.session.id),
        )


class QuitCommand(Command):
    """Disconnect from the server."""

    name = "quit"
    aliases = ["exit"]
    help_text = "quit - Disconnect from the server"
    min_args = 0
    requires_character = False

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the quit command."""
        if ctx.session.character_id:
            # Remove character from room
            if ctx.session.character_id in ctx.engine.character_to_session:
                char_id = ctx.session.character_id
                # Get room and remove player
                try:
                    async with get_session() as session:
                        from waystone.database.models import Character
                        result = await session.execute(
                            select(Character).where(Character.id == char_id)
                        )
                        character = result.scalar_one_or_none()
                        if character and character.current_room_id in ctx.engine.world:
                            room = ctx.engine.world[character.current_room_id]
                            room.remove_player(char_id)
                except Exception as e:
                    logger.error("quit_character_cleanup_failed", error=str(e))

                del ctx.engine.character_to_session[ctx.session.character_id]

        await ctx.connection.send_line(
            colorize("\nFarewell, traveler. May the roads rise to meet you.", "CYAN")
        )

        logger.info(
            "user_quit",
            session_id=str(ctx.session.id),
        )

        ctx.connection.close()
