"""Tests for Discord role-mention invocation support."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from plugins.platforms.discord.adapter import DiscordAdapter


def _make_role(role_id: str = "999") -> MagicMock:
    role = MagicMock()
    role.id = role_id
    return role


def _make_message(*, content: str = "hello", role_mentions: list | None = None) -> MagicMock:
    message = MagicMock()
    message.content = content
    message.role_mentions = role_mentions or []
    message.mentions = []
    return message


def _make_adapter() -> MagicMock:
    adapter = MagicMock(spec=DiscordAdapter)
    adapter.config = MagicMock()
    adapter.config.extra = {}
    adapter._discord_accepted_role_ids = DiscordAdapter._discord_accepted_role_ids.__get__(adapter)
    adapter._has_accepted_role_mention = DiscordAdapter._has_accepted_role_mention.__get__(adapter)
    return adapter


class TestDiscordAcceptedRoleIds:
    def test_config_mention_role_ids(self):
        adapter = _make_adapter()
        adapter.config.extra = {"mention_role_ids": ["111", "222"]}

        assert adapter._discord_accepted_role_ids() == {"111", "222"}

    def test_config_accepted_mention_role_ids_fallback(self):
        adapter = _make_adapter()
        adapter.config.extra = {"accepted_mention_role_ids": ["333"]}

        assert adapter._discord_accepted_role_ids() == {"333"}

    def test_env_mention_role_ids(self):
        adapter = _make_adapter()

        with patch.dict(os.environ, {"DISCORD_MENTION_ROLE_IDS": "444,555"}, clear=False):
            assert adapter._discord_accepted_role_ids() == {"444", "555"}

    def test_env_accepted_mention_role_ids_fallback(self):
        adapter = _make_adapter()

        with patch.dict(
            os.environ,
            {"DISCORD_ACCEPTED_MENTION_ROLE_IDS": "666"},
            clear=False,
        ):
            os.environ.pop("DISCORD_MENTION_ROLE_IDS", None)
            assert adapter._discord_accepted_role_ids() == {"666"}

    def test_precedence_config_over_env(self):
        adapter = _make_adapter()
        adapter.config.extra = {"mention_role_ids": ["111"]}

        with patch.dict(os.environ, {"DISCORD_MENTION_ROLE_IDS": "999"}, clear=False):
            assert adapter._discord_accepted_role_ids() == {"111"}

    def test_empty_returns_empty_set(self):
        adapter = _make_adapter()

        with patch.dict(os.environ, {}, clear=True):
            assert adapter._discord_accepted_role_ids() == set()

    def test_whitespace_stripped(self):
        adapter = _make_adapter()
        adapter.config.extra = {"mention_role_ids": [" 111 ", "", " 222 "]}

        assert adapter._discord_accepted_role_ids() == {"111", "222"}


class TestHasAcceptedRoleMention:
    def test_no_accepted_roles_returns_false(self):
        adapter = _make_adapter()
        message = _make_message(role_mentions=[_make_role("999")])

        assert not adapter._has_accepted_role_mention(message)

    def test_matching_role_returns_true(self):
        adapter = _make_adapter()
        adapter.config.extra = {"mention_role_ids": ["999"]}
        message = _make_message(role_mentions=[_make_role("999")])

        assert adapter._has_accepted_role_mention(message)

    def test_non_matching_role_returns_false(self):
        adapter = _make_adapter()
        adapter.config.extra = {"mention_role_ids": ["999"]}
        message = _make_message(role_mentions=[_make_role("888")])

        assert not adapter._has_accepted_role_mention(message)

    def test_no_role_mentions_returns_false(self):
        adapter = _make_adapter()
        adapter.config.extra = {"mention_role_ids": ["999"]}
        message = _make_message(role_mentions=[])

        assert not adapter._has_accepted_role_mention(message)

    def test_none_role_mentions_returns_false(self):
        adapter = _make_adapter()
        adapter.config.extra = {"mention_role_ids": ["999"]}
        message = _make_message()
        message.role_mentions = None

        assert not adapter._has_accepted_role_mention(message)