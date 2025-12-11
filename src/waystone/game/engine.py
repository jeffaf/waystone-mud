"""Main game engine for Waystone MUD."""

import asyncio
from uuid import UUID

import structlog

from waystone.config import get_settings
from waystone.database.engine import close_db, init_db
from waystone.game.commands.base import CommandContext, get_registry
from waystone.game.world import NPCTemplate, Room, load_all_npcs, load_all_rooms
from waystone.network import (
    WELCOME_BANNER,
    Connection,
    Session,
    SessionManager,
    SessionState,
    TelnetServer,
    colorize,
)

logger = structlog.get_logger(__name__)


class GameEngine:
    """
    Main game engine coordinating all MUD systems.

    Manages the game world, connections, sessions, and command execution.
    """

    def __init__(self) -> None:
        """Initialize the game engine."""
        self.world: dict[str, Room] = {}
        self.npc_templates: dict[str, NPCTemplate] = {}
        self.room_npcs: dict[str, list[str]] = {}  # room_id -> list of NPC template IDs
        self.connections: dict[UUID, Connection] = {}
        self.session_manager: SessionManager = SessionManager()
        self.character_to_session: dict[str, Session] = {}
        self.telnet_server: TelnetServer | None = None
        self._running = False
        self._cleanup_task: asyncio.Task[None] | None = None
        self._settings = get_settings()

        logger.info("game_engine_initialized")

    async def start(self) -> None:
        """
        Initialize database, load world, and start server.

        This should be called once at application startup.
        """
        logger.info("game_engine_starting")

        # Initialize database
        logger.info("initializing_database")
        await init_db()

        # Load world
        logger.info("loading_world")
        try:
            world_path = self._settings.world_dir / "rooms"
            self.world = load_all_rooms(world_path)
            logger.info(
                "world_loaded",
                total_rooms=len(self.world),
            )
        except Exception as e:
            logger.error("world_load_failed", error=str(e), exc_info=True)
            raise

        # Load NPC templates
        logger.info("loading_npcs")
        try:
            npc_path = self._settings.world_dir / "npcs"
            self.npc_templates = load_all_npcs(npc_path)
            logger.info(
                "npcs_loaded",
                total_npc_templates=len(self.npc_templates),
            )
        except Exception as e:
            logger.error("npc_load_failed", error=str(e), exc_info=True)
            raise

        # Spawn NPCs in their designated rooms
        self._spawn_initial_npcs()

        # Initialize NPC combat instances
        from waystone.game.systems.npc_combat import initialize_room_npcs

        npc_count = initialize_room_npcs(self)
        logger.info("npc_instances_created", total=npc_count)

        # Register all commands
        self._register_commands()

        # Start telnet server
        logger.info("starting_telnet_server")
        self.telnet_server = TelnetServer(
            connection_callback=self.handle_connection,
        )

        # Start cleanup task
        self._running = True
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

        await self.telnet_server.start(
            host=self._settings.host,
            port=self._settings.telnet_port,
        )
        logger.info(
            "game_engine_started",
            host=self._settings.host,
            port=self._settings.telnet_port,
        )

    async def stop(self) -> None:
        """
        Gracefully shutdown the game engine.

        Stops the server, disconnects all clients, and closes the database.
        """
        logger.info("game_engine_stopping")
        self._running = False

        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Stop telnet server
        if self.telnet_server:
            await self.telnet_server.stop()

        # Disconnect all connections
        for connection in list(self.connections.values()):
            try:
                await connection.send_line(
                    colorize("\nServer is shutting down. Goodbye!", "YELLOW")
                )
                connection.close()
            except Exception as e:
                logger.error(
                    "connection_shutdown_error",
                    connection_id=str(connection.id),
                    error=str(e),
                )

        # Close database
        await close_db()

        logger.info("game_engine_stopped")

    def _register_commands(self) -> None:
        """Register all game commands with the command registry."""
        from waystone.game.commands.auth import (
            LoginCommand,
            LogoutCommand,
            QuitCommand,
            RegisterCommand,
        )
        from waystone.game.commands.character import (
            CharactersCommand,
            CreateCommand,
            DeleteCommand,
            PlayCommand,
        )
        from waystone.game.commands.combat import (
            AttackCommand,
            BashCommand,
            CombatStatusCommand,
            DefendCommand,
            DisarmCommand,
            FleeCommand,
            KickCommand,
            TripCommand,
        )
        from waystone.game.commands.communication import (
            ChatCommand,
            EmoteCommand,
            SayCommand,
            TellCommand,
        )
        from waystone.game.commands.fae import (
            AcceptCurseCommand,
            CurseCommand,
            EnterFaeCommand,
            LeaveFaeCommand,
            SpeakCthaehCommand,
        )
        from waystone.game.commands.info import (
            GuideCommand,
            HelpCommand,
            IncreaseCommand,
            SaveCommand,
            ScoreCommand,
            TimeCommand,
            WealthCommand,
            WhoCommand,
        )
        from waystone.game.commands.inventory import (
            DropCommand,
            EquipCommand,
            EquipmentCommand,
            ExamineCommand,
            GetCommand,
            GiveCommand,
            InventoryCommand,
            UnequipCommand,
        )
        from waystone.game.commands.movement import (
            DownCommand,
            EastCommand,
            ExitsCommand,
            GoCommand,
            LookCommand,
            NorthCommand,
            NortheastCommand,
            NorthwestCommand,
            SouthCommand,
            SoutheastCommand,
            SouthwestCommand,
            UpCommand,
            WestCommand,
        )
        from waystone.game.commands.npc import ConsiderCommand
        from waystone.game.commands.social import (
            EmoteCommands,
            EmotesCommand,
        )
        from waystone.game.commands.sympathy import (
            BindCommand,
            BindingsCommand,
            CastCommand,
            HeatCommand,
            HoldCommand,
            PushCommand,
            ReleaseCommand,
            SympathyCommand,
        )
        from waystone.game.commands.trading import (
            CancelTradeCommand,
            OfferCommand,
            RemoveOfferCommand,
            TradeAcceptCommand,
            TradeCommand,
        )
        from waystone.game.commands.university import (
            AdmitCommand,
            RankCommand,
            TuitionCommand,
            WorkCommand,
        )

        registry = get_registry()

        # Auth commands
        registry.register(RegisterCommand())
        registry.register(LoginCommand())
        registry.register(LogoutCommand())
        registry.register(QuitCommand())

        # Character commands
        registry.register(CharactersCommand())
        registry.register(CreateCommand())
        registry.register(PlayCommand())
        registry.register(DeleteCommand())

        # Movement commands
        registry.register(NorthCommand())
        registry.register(SouthCommand())
        registry.register(EastCommand())
        registry.register(WestCommand())
        registry.register(UpCommand())
        registry.register(DownCommand())
        registry.register(NortheastCommand())
        registry.register(NorthwestCommand())
        registry.register(SoutheastCommand())
        registry.register(SouthwestCommand())
        registry.register(GoCommand())
        registry.register(LookCommand())
        registry.register(ExitsCommand())

        # Communication commands
        registry.register(SayCommand())
        registry.register(EmoteCommand())
        registry.register(ChatCommand())
        registry.register(TellCommand())

        # Combat commands
        registry.register(AttackCommand())
        registry.register(DefendCommand())
        registry.register(FleeCommand())
        registry.register(CombatStatusCommand())
        # Combat skill commands
        registry.register(BashCommand())
        registry.register(KickCommand())
        registry.register(DisarmCommand())
        registry.register(TripCommand())

        # Info commands
        registry.register(HelpCommand())
        registry.register(WhoCommand())
        registry.register(ScoreCommand())
        registry.register(TimeCommand())
        registry.register(IncreaseCommand())
        registry.register(SaveCommand())
        registry.register(GuideCommand())
        registry.register(WealthCommand())

        # Inventory and equipment commands
        registry.register(InventoryCommand())
        registry.register(GetCommand())
        registry.register(DropCommand())
        registry.register(ExamineCommand())
        registry.register(GiveCommand())
        registry.register(EquipCommand())
        registry.register(UnequipCommand())
        registry.register(EquipmentCommand())

        # NPC commands
        registry.register(ConsiderCommand())

        # Sympathy magic commands
        registry.register(BindCommand())
        registry.register(ReleaseCommand())
        registry.register(BindingsCommand())
        registry.register(SympathyCommand())
        registry.register(HoldCommand())
        registry.register(PushCommand())
        registry.register(HeatCommand())
        registry.register(CastCommand())

        # University commands
        registry.register(AdmitCommand())
        registry.register(TuitionCommand())
        registry.register(RankCommand())
        registry.register(WorkCommand())

        # Trading commands
        registry.register(TradeCommand())
        registry.register(TradeAcceptCommand())
        registry.register(OfferCommand())
        registry.register(RemoveOfferCommand())
        registry.register(CancelTradeCommand())

        # Social emote commands
        registry.register(EmotesCommand())
        for emote_cmd_class in EmoteCommands:
            registry.register(emote_cmd_class())

        # Fae realm commands
        registry.register(EnterFaeCommand())
        registry.register(SpeakCthaehCommand())
        registry.register(AcceptCurseCommand())
        registry.register(CurseCommand())
        registry.register(LeaveFaeCommand())

        logger.info(
            "commands_registered",
            total_commands=len(registry.get_all_commands()),
        )

    async def handle_connection(self, connection: Connection) -> None:
        """
        Main loop for handling a single client connection.

        Args:
            connection: The client connection to handle
        """
        self.connections[connection.id] = connection
        session = self.session_manager.create_session(connection)

        logger.info(
            "connection_handler_started",
            connection_id=str(connection.id),
            session_id=str(session.id),
            ip_address=connection.ip_address,
        )

        try:
            # Show welcome banner
            await connection.send_line(WELCOME_BANNER)
            await connection.send_line(colorize("Type 'help' for a list of commands.\n", "DIM"))
            await connection.send_line(
                "To get started:\n"
                "  "
                + colorize("register <username> <password> <email>", "YELLOW")
                + " - Create a new account\n"
                "  "
                + colorize("login <username> <password>", "YELLOW")
                + " - Log into existing account\n"
            )

            # Main command loop
            while not connection.is_closed:
                try:
                    # Show prompt
                    prompt = self._get_prompt(session)
                    await connection.send(prompt)

                    # Read input
                    raw_input = await connection.readline()

                    if not raw_input:
                        continue

                    # Update session activity
                    session.update_activity()

                    # Process command
                    await self.process_command(session, raw_input)

                except ConnectionError:
                    logger.info(
                        "connection_lost",
                        connection_id=str(connection.id),
                    )
                    break
                except Exception as e:
                    logger.error(
                        "command_loop_error",
                        connection_id=str(connection.id),
                        error=str(e),
                        exc_info=True,
                    )
                    await connection.send_line(
                        colorize("An error occurred. Please try again.", "RED")
                    )

        except Exception as e:
            logger.error(
                "connection_handler_error",
                connection_id=str(connection.id),
                error=str(e),
                exc_info=True,
            )
        finally:
            # Cleanup
            if session.character_id:
                if session.character_id in self.character_to_session:
                    del self.character_to_session[session.character_id]

            self.session_manager.destroy_session(session.id)

            if connection.id in self.connections:
                del self.connections[connection.id]

            connection.close()

            logger.info(
                "connection_handler_ended",
                connection_id=str(connection.id),
                session_id=str(session.id),
            )

    def _get_prompt(self, session: Session) -> str:
        """
        Get the appropriate prompt for a session.

        Args:
            session: The session to get a prompt for

        Returns:
            Formatted prompt string
        """
        if session.state == SessionState.PLAYING:
            return colorize("> ", "GREEN")
        elif session.state == SessionState.AUTHENTICATING:
            return colorize("(Character Select) > ", "CYAN")
        else:
            return colorize("(Login) > ", "YELLOW")

    async def process_command(self, session: Session, raw_input: str) -> None:
        """
        Parse and execute a command.

        Args:
            session: The session executing the command
            raw_input: Raw input string from the player
        """
        raw_input = raw_input.strip()

        if not raw_input:
            return

        # Parse command and arguments
        parts = raw_input.split()
        command_name = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []

        # Handle special shortcuts
        if command_name.startswith("'"):
            # Say shortcut
            command_name = "say"
            args = [raw_input[1:].strip()]
        elif command_name.startswith(":"):
            # Emote shortcut
            command_name = "emote"
            args = [raw_input[1:].strip()]

        # Get command from registry
        registry = get_registry()
        command = registry.get(command_name)

        if not command:
            await session.connection.send_line(colorize(f"Unknown command: {command_name}", "RED"))
            await session.connection.send_line(
                "Type " + colorize("help", "YELLOW") + " for a list of commands."
            )
            return

        # Check if command requires a character
        if command.requires_character and not session.character_id:
            await session.connection.send_line(
                colorize("You must be playing a character to use this command.", "RED")
            )
            return

        # Validate arguments
        is_valid, error_msg = command.validate_args(args)
        if not is_valid:
            await session.connection.send_line(
                colorize(error_msg or "Invalid arguments.", "YELLOW")
            )
            return

        # Execute command
        ctx = CommandContext(
            session=session,
            connection=session.connection,
            engine=self,
            args=args,
            raw_input=raw_input,
        )

        try:
            await command.execute(ctx)
            logger.debug(
                "command_executed",
                command=command_name,
                session_id=str(session.id),
                character_id=session.character_id,
            )
        except Exception as e:
            logger.error(
                "command_execution_error",
                command=command_name,
                session_id=str(session.id),
                error=str(e),
                exc_info=True,
            )
            await session.connection.send_line(
                colorize("An error occurred while executing the command.", "RED")
            )

    def broadcast_to_room(self, room_id: str, message: str, exclude: UUID | None = None) -> None:
        """
        Send a message to all players in a room.

        Args:
            room_id: The room ID to broadcast to
            message: The message to send
            exclude: Optional session ID to exclude from broadcast
        """
        room = self.world.get(room_id)
        if not room:
            return

        # Get all sessions in the room
        for character_id in room.players:
            session = self.character_to_session.get(character_id)

            if session and session.id != exclude:
                try:
                    asyncio.create_task(session.connection.send_line(message))
                except Exception as e:
                    logger.error(
                        "broadcast_failed",
                        room_id=room_id,
                        character_id=character_id,
                        error=str(e),
                    )

    def _spawn_initial_npcs(self) -> None:
        """
        Spawn NPCs in their designated rooms based on templates.

        This is called once at startup to populate the world with NPCs.
        For now, this spawns NPCs in specific rooms based on their type.
        Future enhancement: Load spawn data from YAML files.
        """
        # Define NPC spawn locations
        # Format: {room_id: [npc_template_ids]}
        spawn_locations = {
            # University NPCs - The Nine Masters
            "university_archives": ["scriv", "master_lorren"],
            "university_courtyard": ["student"],
            "university_artificery": ["master_kilvin"],
            "university_medica": ["master_arwyl"],
            "university_rookery": ["elodin"],
            "university_lecture_hall": ["master_hemme", "master_elxa_dal"],
            "university_alchemy_lab": ["master_mandrag"],
            "university_rhetoric_hall": ["master_brandeur"],
            "university_mains": ["master_herma"],
            # Imre combat areas
            "imre_training_yard": ["training_dummy"],
            "imre_sewers_entrance": ["sewer_rat"],
            "imre_sewers_main": ["sewer_rat", "sewer_rat", "sewer_rat"],
            "imre_north_road": ["bandit"],
            "imre_back_alley": ["sewer_rat"],
            # Fae realm
            "fae_cthaeh_clearing": ["cthaeh"],
            "fae_twilight_forest": ["sithe_watcher"],
        }

        total_spawned = 0
        for room_id, npc_ids in spawn_locations.items():
            if room_id not in self.world:
                logger.warning(
                    "npc_spawn_room_not_found",
                    room_id=room_id,
                    npc_ids=npc_ids,
                )
                continue

            for npc_id in npc_ids:
                if npc_id not in self.npc_templates:
                    logger.warning(
                        "npc_template_not_found",
                        npc_id=npc_id,
                        room_id=room_id,
                    )
                    continue

                # Add NPC to room's NPC list
                if room_id not in self.room_npcs:
                    self.room_npcs[room_id] = []
                self.room_npcs[room_id].append(npc_id)
                total_spawned += 1

        logger.info(
            "npcs_spawned",
            total_spawned=total_spawned,
            total_rooms_with_npcs=len(self.room_npcs),
        )

    async def _periodic_cleanup(self) -> None:
        """Periodically clean up expired sessions and check for NPC respawns."""
        tick_count = 0

        while self._running:
            try:
                # Wait 30 seconds between ticks
                await asyncio.sleep(30)
                tick_count += 1

                # Clean up expired sessions (every 10 ticks = 5 minutes)
                if tick_count % 10 == 0:
                    expired_count = self.session_manager.cleanup_expired()

                    if expired_count > 0:
                        logger.info(
                            "periodic_cleanup_completed",
                            expired_sessions=expired_count,
                        )

                # Check for NPC respawns every tick
                from waystone.game.systems.death import check_respawns
                from waystone.game.systems.npc_combat import check_npc_respawns

                try:
                    # Check death system respawns
                    respawned_count = await check_respawns(self)

                    # Check combat system respawns (from _pending_respawns)
                    combat_respawned = await check_npc_respawns(self)
                    respawned_count += combat_respawned

                    if respawned_count > 0:
                        logger.debug(
                            "respawn_check_completed",
                            respawned_count=respawned_count,
                        )

                except Exception as e:
                    logger.error(
                        "respawn_check_error",
                        error=str(e),
                        exc_info=True,
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "periodic_cleanup_error",
                    error=str(e),
                    exc_info=True,
                )
