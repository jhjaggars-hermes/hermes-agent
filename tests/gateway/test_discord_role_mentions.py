"""Discord role mentions can be configured as invocation mentions."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from gateway.config import PlatformConfig
from plugins.platforms.discord import adapter as discord_adapter
from plugins.platforms.discord.adapter import DiscordAdapter


def _role(role_id: str) -> SimpleNamespace:
    return SimpleNamespace(id=role_id)


def _user(*, user_id: str = "111", bot: bool = False) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, bot=bot)


def _message(
    *,
    content: str = "<@&999> hello",
    author: SimpleNamespace | None = None,
    mentions: list | None = None,
    role_mentions: list | None = None,
    channel: object | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id="123",
        content=content,
        type=discord_adapter.discord.MessageType.default,
        author=author or _user(),
        mentions=mentions or [],
        role_mentions=role_mentions or [],
        channel=channel or SimpleNamespace(id="555", parent_id=None),
        guild=SimpleNamespace(id="777"),
        message_snapshots=[],
        attachments=[],
        reference=None,
    )


def _adapter(*, extra: dict | None = None) -> DiscordAdapter:
    adapter = object.__new__(DiscordAdapter)
    adapter.config = PlatformConfig(enabled=True, token="test-token", extra=extra or {})
    adapter._client = SimpleNamespace(user=_user(user_id="222", bot=True))
    adapter._dedup = MagicMock()
    adapter._dedup.is_duplicate.return_value = False
    adapter._dedup.contains.return_value = False
    adapter._allowed_role_ids = set()
    adapter._is_allowed_user = MagicMock(return_value=True)
    adapter._warn_if_fail_closed_default = MagicMock()
    adapter._get_parent_channel_id = MagicMock(return_value=None)
    adapter._discord_channel_keys = MagicMock(return_value={"555"})
    adapter._discord_free_response_channels = MagicMock(return_value=set())
    adapter._discord_thread_require_mention = MagicMock(return_value=False)
    adapter._discord_bots_require_inline_mention = MagicMock(return_value=False)
    adapter._handle_message = AsyncMock(return_value=True)
    setattr(adapter, "_threads", set())
    adapter._voice_text_channels = {}
    setattr(adapter, "_session_id_for_channel", MagicMock(return_value="session"))
    return adapter


class TestDiscordAcceptedRoleIds:
    def test_config_mention_role_ids_take_precedence_over_env(self):
        adapter = _adapter(extra={"mention_role_ids": [" 111 ", "", "222"]})
        with patch.dict("os.environ", {"DISCORD_MENTION_ROLE_IDS": "999"}):
            assert adapter._discord_accepted_role_ids() == {"111", "222"}

    def test_config_accepted_mention_role_ids_fallback(self):
        adapter = _adapter(extra={"accepted_mention_role_ids": "333, 444"})
        assert adapter._discord_accepted_role_ids() == {"333", "444"}

    def test_env_fallbacks(self):
        adapter = _adapter()
        with patch.dict("os.environ", {"DISCORD_MENTION_ROLE_IDS": "555,666"}, clear=False):
            assert adapter._discord_accepted_role_ids() == {"555", "666"}
        with patch.dict("os.environ", {"DISCORD_ACCEPTED_MENTION_ROLE_IDS": "777"}, clear=False):
            with patch.dict("os.environ", {"DISCORD_MENTION_ROLE_IDS": ""}, clear=False):
                # Empty primary env is considered configured-empty, matching the
                # existing Discord list-parsing convention.
                assert adapter._discord_accepted_role_ids() == set()
        with patch.dict("os.environ", {"DISCORD_ACCEPTED_MENTION_ROLE_IDS": "777"}, clear=True):
            assert adapter._discord_accepted_role_ids() == {"777"}


class TestDiscordRoleMentionAdmission:
    def test_matching_role_is_accepted_invocation(self):
        adapter = _adapter(extra={"mention_role_ids": ["999"]})
        msg = _message(role_mentions=[_role("999")])
        assert adapter._has_accepted_role_mention(msg) is True

    def test_non_matching_role_is_not_invocation(self):
        adapter = _adapter(extra={"mention_role_ids": ["999"]})
        msg = _message(role_mentions=[_role("888")])
        assert adapter._has_accepted_role_mention(msg) is False

    def test_bot_allow_bots_mentions_accepts_configured_role_mention(self):
        adapter = _adapter(extra={"mention_role_ids": ["999"]})
        msg = _message(author=_user(bot=True), role_mentions=[_role("999")])
        with patch.dict("os.environ", {"DISCORD_ALLOW_BOTS": "mentions"}):
            assert adapter._discord_message_admission(msg, claim=True) == (True, False)

    def test_role_mention_satisfies_require_mention_for_recovered_messages(self):
        adapter = _adapter(extra={"mention_role_ids": ["999"], "require_mention": True})
        msg = _message(role_mentions=[_role("999")])
        admitted, _ = adapter._discord_message_admission(msg, claim=False)
        assert admitted is True
