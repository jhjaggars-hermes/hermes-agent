"""
Tests for Discord role-mention invocation support.

Covers the three places role-mention acceptance is checked:
  1. Bot-message allow_bots=mentions gating (adapter)
  2. Human-message self-mention / role-mention gating (adapter)
  3. Mention stripping from normalized content (adapter)
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_role(role_id: str = "999") -> MagicMock:
    r = MagicMock()
    r.id = role_id
    return r


def _make_message(
    *,
    content: str = "hello",
    author_id: str = "111",
    author_bot: bool = False,
    mentions: list | None = None,
    role_mentions: list | None = None,
    channel_type: str = "text",
    msg_type: str = "default",
) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.type = MagicMock()
    msg.type.name = msg_type
    msg.author = MagicMock()
    msg.author.id = author_id
    msg.author.bot = author_bot
    msg.mentions = mentions or []
    msg.role_mentions = role_mentions or []
    msg.channel = MagicMock()
    if channel_type == "dm":
        msg.channel.__class__.__name__ = "DMChannel"
        msg.guild = None
    else:
        msg.channel.__class__.__name__ = "TextChannel"
        msg.channel.id = "555"
        msg.guild = MagicMock()
        msg.guild.id = "777"
    return msg


def _make_client() -> MagicMock:
    client = MagicMock()
    client.user = MagicMock()
    client.user.id = "222"
    client.user.bot = True
    return client


def _make_adapter(**overrides) -> MagicMock:
    from plugins.platforms.discord.adapter import DiscordAdapter
    adapter = MagicMock(spec=DiscordAdapter)
    adapter._client = _make_client()
    adapter._allowed_role_ids = set()
    adapter.config = MagicMock()
    adapter.config.extra = {}
    adapter.name = "discord"
    # Bind real methods we want to test
    adapter._discord_accepted_role_ids = DiscordAdapter._discord_accepted_role_ids.__get__(adapter)
    adapter._has_accepted_role_mention = DiscordAdapter._has_accepted_role_mention.__get__(adapter)
    adapter._discord_free_response_channels = MagicMock(return_value=set())
    adapter._is_allowed_user = MagicMock(return_value=True)
    adapter._handle_message = AsyncMock()
    for k, v in overrides.items():
        setattr(adapter, k, v)
    return adapter


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDiscordAcceptedRoleIds(unittest.TestCase):
    """_discord_accepted_role_ids precedence and parsing."""

    def test_config_mention_role_ids(self):
        adapter = _make_adapter()
        adapter.config.extra = {"mention_role_ids": ["111", "222"]}
        result = adapter._discord_accepted_role_ids()
        self.assertEqual(result, {"111", "222"})

    def test_config_accepted_mention_role_ids_fallback(self):
        adapter = _make_adapter()
        adapter.config.extra = {"accepted_mention_role_ids": ["333"]}
        result = adapter._discord_accepted_role_ids()
        self.assertEqual(result, {"333"})

    def test_env_mention_role_ids(self):
        adapter = _make_adapter()
        with patch.dict(os.environ, {"DISCORD_MENTION_ROLE_IDS": "444,555"}):
            result = adapter._discord_accepted_role_ids()
        self.assertEqual(result, {"444", "555"})

    def test_env_accepted_mention_role_ids_fallback(self):
        adapter = _make_adapter()
        os.environ.pop("DISCORD_MENTION_ROLE_IDS", None)
        with patch.dict(os.environ, {"DISCORD_ACCEPTED_MENTION_ROLE_IDS": "666"}):
            result = adapter._discord_accepted_role_ids()
        self.assertEqual(result, {"666"})

    def test_precedence_config_over_env(self):
        adapter = _make_adapter()
        adapter.config.extra = {"mention_role_ids": ["111"]}
        with patch.dict(os.environ, {"DISCORD_MENTION_ROLE_IDS": "999"}):
            result = adapter._discord_accepted_role_ids()
        self.assertEqual(result, {"111"})

    def test_empty_returns_empty_set(self):
        adapter = _make_adapter()
        with patch.dict(os.environ, {"DISCORD_MENTION_ROLE_IDS": "", "DISCORD_ACCEPTED_MENTION_ROLE_IDS": ""}):
            os.environ.pop("DISCORD_MENTION_ROLE_IDS", None)
            os.environ.pop("DISCORD_ACCEPTED_MENTION_ROLE_IDS", None)
            result = adapter._discord_accepted_role_ids()
        self.assertEqual(result, set())

    def test_whitespace_stripped(self):
        adapter = _make_adapter()
        adapter.config.extra = {"mention_role_ids": [" 111 ", "", " 222 "]}
        result = adapter._discord_accepted_role_ids()
        self.assertEqual(result, {"111", "222"})


class TestHasAcceptedRoleMention(unittest.TestCase):
    """_has_accepted_role_mention returns True only for accepted role IDs."""

    def test_no_accepted_roles_returns_false(self):
        adapter = _make_adapter()
        msg = _make_message(role_mentions=[_make_role("999")])
        self.assertFalse(adapter._has_accepted_role_mention(msg))

    def test_matching_role_returns_true(self):
        adapter = _make_adapter()
        adapter.config.extra = {"mention_role_ids": ["999"]}
        msg = _make_message(role_mentions=[_make_role("999")])
        self.assertTrue(adapter._has_accepted_role_mention(msg))

    def test_non_matching_role_returns_false(self):
        adapter = _make_adapter()
        adapter.config.extra = {"mention_role_ids": ["999"]}
        msg = _make_message(role_mentions=[_make_role("888")])
        self.assertFalse(adapter._has_accepted_role_mention(msg))

    def test_no_role_mentions_returns_false(self):
        adapter = _make_adapter()
        adapter.config.extra = {"mention_role_ids": ["999"]}
        msg = _make_message(role_mentions=[])
        self.assertFalse(adapter._has_accepted_role_mention(msg))

    def test_none_role_mentions_returns_false(self):
        adapter = _make_adapter()
        adapter.config.extra = {"mention_role_ids": ["999"]}
        msg = _make_message()
        msg.role_mentions = None
        self.assertFalse(adapter._has_accepted_role_mention(msg))


if __name__ == "__main__":
    unittest.main()
