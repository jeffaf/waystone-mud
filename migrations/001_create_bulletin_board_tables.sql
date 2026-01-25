-- Migration: Create Bulletin Board System Tables
-- Version: 001
-- Created: 2025-01-25
-- Description: Creates the bulletin_boards, board_messages, and message_reads tables
--              for the BBS feature.

-- =============================================================================
-- UP MIGRATION
-- =============================================================================

-- Enable foreign key enforcement (required for SQLite)
PRAGMA foreign_keys = ON;

-- -----------------------------------------------------------------------------
-- Table: bulletin_boards
-- Purpose: Stores bulletin board definitions that are placed in specific rooms
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bulletin_boards (
    -- Primary key: human-readable board identifier
    id VARCHAR(100) PRIMARY KEY,

    -- Display name shown to players
    name VARCHAR(100) NOT NULL,

    -- Description shown when examining the board
    description TEXT NOT NULL,

    -- Room where this board is located (references rooms.id logically)
    room_id VARCHAR(100) NOT NULL,

    -- Access control levels (enum stored as string)
    -- Values: 'public', 'student', 'advanced', 'master', 'private'
    read_level VARCHAR(20) NOT NULL DEFAULT 'public',
    post_level VARCHAR(20) NOT NULL DEFAULT 'public',

    -- Maximum messages before auto-pruning oldest (non-pinned)
    max_messages INTEGER NOT NULL DEFAULT 50,

    -- Whether anonymous posting is allowed
    allow_anonymous BOOLEAN NOT NULL DEFAULT 0,

    -- Whether the board is currently active (accepting posts)
    is_active BOOLEAN NOT NULL DEFAULT 1,

    -- Optional attribute requirements as JSON string
    -- Example: '{"charisma": 12}' for Eolian board
    attribute_requirement VARCHAR(500),

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Index for finding boards in a room
CREATE INDEX IF NOT EXISTS idx_bulletin_boards_room_id ON bulletin_boards(room_id);

-- -----------------------------------------------------------------------------
-- Table: board_messages
-- Purpose: Stores messages posted to bulletin boards
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS board_messages (
    -- Primary key: UUID for unique message identification
    id BLOB PRIMARY KEY,

    -- Foreign key to the board this message belongs to
    -- CASCADE: Delete messages when board is deleted
    board_id VARCHAR(100) NOT NULL REFERENCES bulletin_boards(id) ON DELETE CASCADE,

    -- Foreign key to the character who posted
    -- SET NULL: Keep message but remove author link when character is deleted
    author_id BLOB REFERENCES characters(id) ON DELETE SET NULL,

    -- Preserved author name (shown even if character is deleted)
    author_name VARCHAR(100) NOT NULL,

    -- NPC template ID if posted by an NPC (null for player posts)
    npc_author_id VARCHAR(100),

    -- Message content
    subject VARCHAR(80) NOT NULL,
    body TEXT NOT NULL,

    -- Threading support: parent message for replies
    -- SET NULL: Keep reply but unlink from deleted parent
    reply_to BLOB REFERENCES board_messages(id) ON DELETE SET NULL,

    -- Message flags
    is_pinned BOOLEAN NOT NULL DEFAULT 0,
    is_anonymous BOOLEAN NOT NULL DEFAULT 0,

    -- Sequential number within the board (for "read 5" style commands)
    board_sequence INTEGER NOT NULL,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Index for finding messages on a board
CREATE INDEX IF NOT EXISTS idx_board_messages_board_id ON board_messages(board_id);

-- Index for finding messages by author
CREATE INDEX IF NOT EXISTS idx_board_messages_author_id ON board_messages(author_id);

-- Index for finding messages by sequence number (for "read 5" command)
CREATE INDEX IF NOT EXISTS idx_board_messages_sequence ON board_messages(board_id, board_sequence);

-- -----------------------------------------------------------------------------
-- Table: message_reads
-- Purpose: Tracks which messages a character has read (for "new" detection)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS message_reads (
    -- Composite primary key: (character_id, message_id)
    character_id BLOB NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    message_id BLOB NOT NULL REFERENCES board_messages(id) ON DELETE CASCADE,

    -- When the message was read
    read_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (character_id, message_id)
);

-- Index for finding read messages for a character (for unread count queries)
CREATE INDEX IF NOT EXISTS idx_message_reads_character_id ON message_reads(character_id);

-- Index for finding who has read a message
CREATE INDEX IF NOT EXISTS idx_message_reads_message_id ON message_reads(message_id);

-- =============================================================================
-- DOWN MIGRATION (for rollback)
-- =============================================================================
-- To rollback this migration, run these commands in order:
--
-- DROP INDEX IF EXISTS idx_message_reads_message_id;
-- DROP INDEX IF EXISTS idx_message_reads_character_id;
-- DROP TABLE IF EXISTS message_reads;
--
-- DROP INDEX IF EXISTS idx_board_messages_sequence;
-- DROP INDEX IF EXISTS idx_board_messages_author_id;
-- DROP INDEX IF EXISTS idx_board_messages_board_id;
-- DROP TABLE IF EXISTS board_messages;
--
-- DROP INDEX IF EXISTS idx_bulletin_boards_room_id;
-- DROP TABLE IF EXISTS bulletin_boards;
-- =============================================================================
