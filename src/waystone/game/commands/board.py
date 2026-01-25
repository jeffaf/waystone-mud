"""Bulletin board commands for Waystone MUD.

Commands:
- board/boards/bb: List boards in room or select a board
- list: List messages on current board
- read/r: Read a message
- post/p/write: Post a new message
- reply/re: Reply to a message
- delete/del: Delete a message
- pin: Pin a message (moderators only)
- next/n: Read next message
- prev/previous: Read previous message
"""

from uuid import UUID

import structlog

from waystone.database.engine import get_session
from waystone.database.models import Character
from waystone.database.models.bulletin import BulletinBoard
from waystone.game.commands.base import Command, CommandContext
from waystone.game.systems.bulletin import BoardManager, MessageFormatter, MessageInfo
from waystone.network import colorize

logger = structlog.get_logger(__name__)


async def _get_character(ctx: CommandContext) -> Character | None:
    """Helper to get character from database."""
    from sqlalchemy import select

    if not ctx.session.character_id:
        return None

    async with get_session() as db:
        result = await db.execute(
            select(Character).where(Character.id == UUID(ctx.session.character_id))
        )
        return result.scalar_one_or_none()


async def _get_selected_board(ctx: CommandContext) -> BulletinBoard | None:
    """Get the currently selected board from session state."""
    from sqlalchemy import select

    board_id = ctx.session.data.get("selected_board_id")
    if not board_id:
        return None

    async with get_session() as db:
        result = await db.execute(
            select(BulletinBoard).where(BulletinBoard.id == board_id)
        )
        return result.scalar_one_or_none()


class BoardListCommand(Command):
    """List bulletin boards in the current room."""

    name = "board"
    aliases = ["boards", "bb"]
    help_text = "board [name] - List boards or select a board"
    extended_help = """
List all bulletin boards in your current room, or select a specific
board to read and post messages.

Usage:
  board         - List all boards in this room
  board <name>  - Select a board by name
  boards        - Same as 'board'
  bb            - Same as 'board'

Examples:
  board                   - Show all boards here
  board university        - Select the University board
  board imre              - Select a board starting with "imre"
"""
    min_args = 0
    requires_character = True

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the board list command."""
        character = await _get_character(ctx)
        if not character:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        # If args provided, select a board
        if ctx.args:
            await self._select_board(ctx, character, " ".join(ctx.args))
            return

        # Otherwise list boards in room
        async with get_session() as db:
            manager = BoardManager(db)
            boards = await manager.get_boards_in_room(character.current_room_id)

            if not boards:
                await ctx.connection.send_line("There are no bulletin boards here.")
                return

            # Get unread counts for each board
            for board in boards:
                board.unread_count = await manager.get_unread_count(
                    board.id, character.id
                )

            output = MessageFormatter.format_board_list(boards, character)
            await ctx.connection.send_line(output)

    async def _select_board(
        self, ctx: CommandContext, character: Character, search: str
    ) -> None:
        """Select a board by name."""
        async with get_session() as db:
            manager = BoardManager(db)
            boards = await manager.get_boards_in_room(character.current_room_id)

            if not boards:
                await ctx.connection.send_line("There are no bulletin boards here.")
                return

            # Find matching board
            search_lower = search.lower()
            matching = [b for b in boards if search_lower in b.name.lower()]

            if not matching:
                await ctx.connection.send_line(
                    colorize(f"No board matching '{search}' found here.", "YELLOW")
                )
                return

            if len(matching) > 1:
                await ctx.connection.send_line(
                    colorize("Multiple boards match. Be more specific:", "YELLOW")
                )
                for b in matching:
                    await ctx.connection.send_line(f"  - {b.name}")
                return

            board = matching[0]

            # Check read access
            from sqlalchemy import select

            board_result = await db.execute(
                select(BulletinBoard).where(BulletinBoard.id == board.id)
            )
            board_model = board_result.scalar_one_or_none()

            if board_model and not await manager.can_read_board(character, board_model):
                await ctx.connection.send_line(
                    colorize("You do not have access to read this board.", "RED")
                )
                return

            # Store in session
            ctx.session.data["selected_board_id"] = board.id
            ctx.session.data["current_message_sequence"] = None

            # Get unread count
            unread = await manager.get_unread_count(board.id, character.id)

            # Show board header and message list
            output = MessageFormatter.format_board_header(board, unread)
            await ctx.connection.send_line(output)

            # Show message list
            messages = await manager.get_messages(board.id, character.id)
            if messages:
                msg_output = MessageFormatter.format_message_list(messages, character)
                await ctx.connection.send_line(msg_output)


class BoardSelectCommand(Command):
    """Select a bulletin board (alias for 'board <name>')."""

    name = "select"
    aliases = []
    help_text = "select <board> - Select a bulletin board"
    min_args = 1
    requires_character = True

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the select command."""
        # Delegate to BoardListCommand's _select_board
        cmd = BoardListCommand()
        character = await _get_character(ctx)
        if not character:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return
        await cmd._select_board(ctx, character, " ".join(ctx.args))


class ListCommand(Command):
    """List messages on the current board."""

    name = "list"
    aliases = []
    help_text = "list [new] - List messages on current board"
    extended_help = """
List messages on the currently selected bulletin board.

Usage:
  list      - List all messages
  list new  - List only unread messages

You must first select a board using 'board <name>'.
"""
    min_args = 0
    requires_character = True

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the list command."""
        character = await _get_character(ctx)
        if not character:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        board = await _get_selected_board(ctx)
        if not board:
            await ctx.connection.send_line(
                colorize("No board selected. Use 'board <name>' first.", "YELLOW")
            )
            return

        show_new_only = len(ctx.args) > 0 and ctx.args[0].lower() == "new"

        async with get_session() as db:
            manager = BoardManager(db)
            messages = await manager.get_messages(board.id, character.id)

            if show_new_only:
                messages = [m for m in messages if not m.is_read]

            if not messages:
                if show_new_only:
                    await ctx.connection.send_line("No unread messages.")
                else:
                    await ctx.connection.send_line("No messages on this board.")
                return

            output = MessageFormatter.format_message_list(messages, character)
            await ctx.connection.send_line(output)


class ReadCommand(Command):
    """Read a message from the current board."""

    name = "read"
    aliases = ["r"]
    help_text = "read [number|new|all] - Read message(s)"
    extended_help = """
Read messages from the currently selected bulletin board.

Usage:
  read       - Read next unread message (or first if none)
  read 5     - Read message #5
  read new   - Read all unread messages
  read all   - Read all messages
  r          - Same as 'read'

You must first select a board using 'board <name>'.
"""
    min_args = 0
    requires_character = True

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the read command."""
        character = await _get_character(ctx)
        if not character:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        board = await _get_selected_board(ctx)
        if not board:
            await ctx.connection.send_line(
                colorize("No board selected. Use 'board <name>' first.", "YELLOW")
            )
            return

        async with get_session() as db:
            manager = BoardManager(db)
            messages = await manager.get_messages(board.id, character.id)
            total_messages = len(messages)

            if not messages:
                await ctx.connection.send_line("No messages on this board.")
                return

            if not ctx.args:
                # Read next unread or first message
                unread = [m for m in messages if not m.is_read]
                if unread:
                    message = unread[0]
                else:
                    message = messages[0]

                await self._display_message(ctx, manager, message, character, total_messages)
                return

            arg = ctx.args[0].lower()

            if arg == "new":
                # Read all unread
                unread = [m for m in messages if not m.is_read]
                if not unread:
                    await ctx.connection.send_line("No unread messages.")
                    return

                for msg in unread:
                    await self._display_message(ctx, manager, msg, character, total_messages)
                    await ctx.connection.send_line("")
                return

            if arg == "all":
                # Read all messages
                for msg in messages:
                    await self._display_message(ctx, manager, msg, character, total_messages)
                    await ctx.connection.send_line("")
                return

            # Try to parse as number
            try:
                seq_num = int(arg)
            except ValueError:
                await ctx.connection.send_line(
                    colorize(f"Invalid message number: {arg}", "YELLOW")
                )
                return

            message_result = await manager.get_message_by_sequence(board.id, seq_num)
            if not message_result:
                await ctx.connection.send_line(
                    colorize(f"Message #{seq_num} not found.", "YELLOW")
                )
                return

            await self._display_message(ctx, manager, message_result, character, total_messages)

    async def _display_message(
        self, ctx: CommandContext, manager: BoardManager, message: MessageInfo, character: Character, total: int
    ) -> None:
        """Display a message and mark as read."""
        output = MessageFormatter.format_message(message, character, total)
        await ctx.connection.send_line(output)

        # Mark as read
        await manager.mark_as_read(message.id, character.id)

        # Update current message in session
        ctx.session.data["current_message_sequence"] = message.board_sequence


class PostCommand(Command):
    """Post a new message to the current board."""

    name = "post"
    aliases = ["p", "write"]
    help_text = "post <subject> - Post a new message"
    extended_help = """
Post a new message to the currently selected bulletin board.

Usage:
  post <subject>  - Start composing a message with the given subject
  write <subject> - Same as 'post'

After entering the command, you'll enter the message editor:
  - Type your message line by line
  - Use '.send' to post the message
  - Use '.cancel' to abort
  - Use '.help' for editor commands

You must have permission to post to the board.
"""
    min_args = 1
    requires_character = True

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the post command."""
        character = await _get_character(ctx)
        if not character:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        board = await _get_selected_board(ctx)
        if not board:
            await ctx.connection.send_line(
                colorize("No board selected. Use 'board <name>' first.", "YELLOW")
            )
            return

        async with get_session() as db:
            manager = BoardManager(db)

            # Check post permission
            if not await manager.can_post_to_board(character, board):
                await ctx.connection.send_line(
                    colorize("You do not have permission to post to this board.", "RED")
                )
                return

        subject = " ".join(ctx.args)

        # Start editor mode
        await ctx.connection.send_line(
            colorize(f"Composing message: {subject}", "CYAN")
        )
        await ctx.connection.send_line(
            "Enter your message. Use '.send' to post, '.cancel' to abort, '.help' for help."
        )
        await ctx.connection.send_line("-" * 40)

        # Store editor state in session
        ctx.session.data["editor_mode"] = "post"
        ctx.session.data["editor_subject"] = subject
        ctx.session.data["editor_reply_to"] = None
        ctx.session.data["editor_lines"] = []

        await self._run_editor(ctx, character, board, subject, None)

    async def _run_editor(
        self, ctx: CommandContext, character: Character, board: BulletinBoard,
        subject: str, reply_to: int | None
    ) -> None:
        """Run the multi-line editor."""
        lines: list[str] = []

        while True:
            await ctx.connection.send("> ")
            line = await ctx.connection.readline()

            if not line:
                continue

            line = line.strip()

            # Editor commands
            if line.lower() == ".send":
                if not lines:
                    await ctx.connection.send_line(
                        colorize("Cannot send empty message.", "YELLOW")
                    )
                    continue

                # Post the message
                body = "\n".join(lines)
                async with get_session() as db:
                    manager = BoardManager(db)
                    message = await manager.post_message(
                        board_id=board.id,
                        author_id=character.id,
                        subject=subject,
                        body=body,
                        reply_to=reply_to,
                        is_anonymous=False,
                    )

                await ctx.connection.send_line(
                    colorize(f"Message #{message.board_sequence} posted successfully!", "GREEN")
                )

                # Clear editor state
                ctx.session.data.pop("editor_mode", None)
                ctx.session.data.pop("editor_subject", None)
                ctx.session.data.pop("editor_reply_to", None)
                ctx.session.data.pop("editor_lines", None)
                return

            if line.lower() == ".cancel":
                await ctx.connection.send_line(colorize("Message cancelled.", "YELLOW"))
                ctx.session.data.pop("editor_mode", None)
                ctx.session.data.pop("editor_subject", None)
                ctx.session.data.pop("editor_reply_to", None)
                ctx.session.data.pop("editor_lines", None)
                return

            if line.lower() == ".help":
                await ctx.connection.send_line("Editor commands:")
                await ctx.connection.send_line("  .send   - Post the message")
                await ctx.connection.send_line("  .cancel - Abort without posting")
                await ctx.connection.send_line("  .clear  - Clear all lines")
                await ctx.connection.send_line("  .show   - Show current message")
                await ctx.connection.send_line("  .help   - Show this help")
                continue

            if line.lower() == ".clear":
                lines = []
                await ctx.connection.send_line(colorize("Message cleared.", "YELLOW"))
                continue

            if line.lower() == ".show":
                if not lines:
                    await ctx.connection.send_line("(message is empty)")
                else:
                    await ctx.connection.send_line("-" * 40)
                    for content_line in lines:
                        await ctx.connection.send_line(content_line)
                    await ctx.connection.send_line("-" * 40)
                continue

            # Normal line - add to message
            lines.append(line)


class ReplyCommand(Command):
    """Reply to an existing message."""

    name = "reply"
    aliases = ["re"]
    help_text = "reply <number> - Reply to a message"
    extended_help = """
Reply to an existing message on the current board.

Usage:
  reply 5   - Reply to message #5
  re 5      - Same as 'reply 5'

The reply will be linked to the original message and the subject
will automatically be set to 'Re: <original subject>'.
"""
    min_args = 1
    requires_character = True

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the reply command."""
        character = await _get_character(ctx)
        if not character:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        board = await _get_selected_board(ctx)
        if not board:
            await ctx.connection.send_line(
                colorize("No board selected. Use 'board <name>' first.", "YELLOW")
            )
            return

        try:
            seq_num = int(ctx.args[0])
        except ValueError:
            await ctx.connection.send_line(
                colorize(f"Invalid message number: {ctx.args[0]}", "YELLOW")
            )
            return

        async with get_session() as db:
            manager = BoardManager(db)

            # Check post permission
            if not await manager.can_post_to_board(character, board):
                await ctx.connection.send_line(
                    colorize("You do not have permission to post to this board.", "RED")
                )
                return

            # Get the original message
            original = await manager.get_message_by_sequence(board.id, seq_num)
            if not original:
                await ctx.connection.send_line(
                    colorize(f"Message #{seq_num} not found.", "YELLOW")
                )
                return

        # Create reply subject
        subject = original.subject
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        await ctx.connection.send_line(
            colorize(f"Replying to message #{seq_num}: {original.subject}", "CYAN")
        )
        await ctx.connection.send_line(
            "Enter your reply. Use '.send' to post, '.cancel' to abort."
        )
        await ctx.connection.send_line("-" * 40)

        # Run editor with reply_to set
        post_cmd = PostCommand()
        await post_cmd._run_editor(ctx, character, board, subject, seq_num)


class RemoveCommand(Command):
    """Remove a message from the board."""

    name = "delete"
    aliases = ["del"]
    help_text = "delete <number> - Delete a message"
    extended_help = """
Delete a message from the current board.

Usage:
  delete 5   - Delete message #5
  del 5      - Same as 'delete 5'

You can only delete your own messages, unless you are a moderator
(El'the rank or higher).
"""
    min_args = 1
    requires_character = True

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the remove command."""
        character = await _get_character(ctx)
        if not character:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        board = await _get_selected_board(ctx)
        if not board:
            await ctx.connection.send_line(
                colorize("No board selected. Use 'board <name>' first.", "YELLOW")
            )
            return

        try:
            seq_num = int(ctx.args[0])
        except ValueError:
            await ctx.connection.send_line(
                colorize(f"Invalid message number: {ctx.args[0]}", "YELLOW")
            )
            return

        async with get_session() as db:
            manager = BoardManager(db)

            # Get the message
            message = await manager.get_message_by_sequence(board.id, seq_num)
            if not message:
                await ctx.connection.send_line(
                    colorize(f"Message #{seq_num} not found.", "YELLOW")
                )
                return

            # Try to delete
            deleted = await manager.delete_message(message.id, character.id)

            if deleted:
                await ctx.connection.send_line(
                    colorize(f"Message #{seq_num} deleted.", "GREEN")
                )
            else:
                await ctx.connection.send_line(
                    colorize("You do not have permission to delete this message.", "RED")
                )


class PinCommand(Command):
    """Pin a message to the top of the board."""

    name = "pin"
    aliases = []
    help_text = "pin <number> - Pin a message (moderators only)"
    extended_help = """
Pin a message to the top of the board. Pinned messages always appear
first in the message list and are protected from pruning.

Usage:
  pin 5  - Pin message #5

This command requires moderator status (El'the rank or higher).
"""
    min_args = 1
    requires_character = True

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the pin command."""
        character = await _get_character(ctx)
        if not character:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        board = await _get_selected_board(ctx)
        if not board:
            await ctx.connection.send_line(
                colorize("No board selected. Use 'board <name>' first.", "YELLOW")
            )
            return

        try:
            seq_num = int(ctx.args[0])
        except ValueError:
            await ctx.connection.send_line(
                colorize(f"Invalid message number: {ctx.args[0]}", "YELLOW")
            )
            return

        async with get_session() as db:
            manager = BoardManager(db)

            # Get the message
            message = await manager.get_message_by_sequence(board.id, seq_num)
            if not message:
                await ctx.connection.send_line(
                    colorize(f"Message #{seq_num} not found.", "YELLOW")
                )
                return

            # Try to pin
            pinned = await manager.pin_message(message.id, character.id)

            if pinned:
                await ctx.connection.send_line(
                    colorize(f"Message #{seq_num} pinned.", "GREEN")
                )
            else:
                await ctx.connection.send_line(
                    colorize("Only moderators (El'the or higher) can pin messages.", "RED")
                )


class NextCommand(Command):
    """Read the next message in sequence."""

    name = "next"
    aliases = ["n"]
    help_text = "next - Read next message"
    extended_help = """
Read the next message after the one you just read.

Usage:
  next  - Read next message
  n     - Same as 'next'

If you haven't read a message yet, reads the first message.
"""
    min_args = 0
    requires_character = True

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the next command."""
        character = await _get_character(ctx)
        if not character:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        board = await _get_selected_board(ctx)
        if not board:
            await ctx.connection.send_line(
                colorize("No board selected. Use 'board <name>' first.", "YELLOW")
            )
            return

        current_seq_raw = ctx.session.data.get("current_message_sequence", 0)
        current_seq = int(str(current_seq_raw)) if current_seq_raw is not None else 0
        next_seq = current_seq + 1

        async with get_session() as db:
            manager = BoardManager(db)
            messages = await manager.get_messages(board.id, character.id)

            if not messages:
                await ctx.connection.send_line("No messages on this board.")
                return

            message = await manager.get_message_by_sequence(board.id, next_seq)
            if not message:
                await ctx.connection.send_line(
                    colorize("No more messages.", "YELLOW")
                )
                return

            output = MessageFormatter.format_message(message, character, len(messages))
            await ctx.connection.send_line(output)

            # Mark as read and update current
            await manager.mark_as_read(message.id, character.id)
            ctx.session.data["current_message_sequence"] = message.board_sequence


class PrevCommand(Command):
    """Read the previous message in sequence."""

    name = "prev"
    aliases = ["previous"]
    help_text = "prev - Read previous message"
    extended_help = """
Read the previous message before the one you just read.

Usage:
  prev      - Read previous message
  previous  - Same as 'prev'
"""
    min_args = 0
    requires_character = True

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the prev command."""
        character = await _get_character(ctx)
        if not character:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        board = await _get_selected_board(ctx)
        if not board:
            await ctx.connection.send_line(
                colorize("No board selected. Use 'board <name>' first.", "YELLOW")
            )
            return

        current_seq_raw = ctx.session.data.get("current_message_sequence", 2)
        current_seq = int(str(current_seq_raw)) if current_seq_raw is not None else 2
        prev_seq = current_seq - 1

        if prev_seq < 1:
            await ctx.connection.send_line(
                colorize("No previous messages.", "YELLOW")
            )
            return

        async with get_session() as db:
            manager = BoardManager(db)
            messages = await manager.get_messages(board.id, character.id)

            if not messages:
                await ctx.connection.send_line("No messages on this board.")
                return

            message = await manager.get_message_by_sequence(board.id, prev_seq)
            if not message:
                await ctx.connection.send_line(
                    colorize("No previous messages.", "YELLOW")
                )
                return

            output = MessageFormatter.format_message(message, character, len(messages))
            await ctx.connection.send_line(output)

            # Mark as read and update current
            await manager.mark_as_read(message.id, character.id)
            ctx.session.data["current_message_sequence"] = message.board_sequence
