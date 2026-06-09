"""Tests for Discord role-mention invocation (accepted role mention support)."""

import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.config import PlatformConfig


def _ensure_discord_mock():
    """Install a mock discord module when discord.py isn't available."""
    if "discord" in sys.modules and hasattr(sys.modules["discord"], "__file__"):
        return

    discord_mod = MagicMock()
    discord_mod.Intents.default.return_value = MagicMock()
    discord_mod.Client = MagicMock
    discord_mod.File = MagicMock
    discord_mod.DMChannel = type("DMChannel", (), {})
    discord_mod.Thread = type("Thread", (), {})
    discord_mod.ForumChannel = type("ForumChannel", (), {})
    discord_mod.ui = SimpleNamespace(
        View=object,
        button=lambda *a, **k: (lambda fn: fn),
        Button=object,
    )
    discord_mod.ButtonStyle = SimpleNamespace(
        success=1, primary=2, secondary=2, danger=3, green=1, grey=2, blurple=2, red=3
    )
    discord_mod.Color = SimpleNamespace(
        orange=lambda: 1, green=lambda: 2, blue=lambda: 3, red=lambda: 4, purple=lambda: 5
    )
    discord_mod.Interaction = object
    discord_mod.Embed = MagicMock
    discord_mod.app_commands = SimpleNamespace(
        describe=lambda **kwargs: (lambda fn: fn),
        choices=lambda **kwargs: (lambda fn: fn),
        Choice=lambda **kwargs: SimpleNamespace(**kwargs),
    )

    ext_mod = MagicMock()
    commands_mod = MagicMock()
    commands_mod.Bot = MagicMock
    ext_mod.commands = commands_mod

    sys.modules.setdefault("discord", discord_mod)
    sys.modules.setdefault("discord.ext", ext_mod)
    sys.modules.setdefault("discord.ext.commands", commands_mod)


_ensure_discord_mock()

import plugins.platforms.discord.adapter as discord_platform  # noqa: E402
from plugins.platforms.discord.adapter import DiscordAdapter  # noqa: E402


# ── Fake channel / message helpers ────────────────────────────────────────────


class FakeDMChannel:
    def __init__(self, channel_id: int = 1):
        self.id = channel_id
        self.name = "dm"


class FakeTextChannel:
    def __init__(self, channel_id: int = 222, name: str = "alerts"):
        self.id = channel_id
        self.name = name
        self.guild = SimpleNamespace(name="TestServer")
        self.topic = None
        self.parent_id = None

    def history(self, *, limit, before, after=None, oldest_first=None):
        async def _iter():
            return
            yield  # noqa: unreachable — makes this an async generator

        return _iter()


def make_role(role_id: int):
    """Create a fake Discord role object."""
    return SimpleNamespace(id=role_id, name=f"role-{role_id}")


def make_message(
    *,
    channel=None,
    content: str = "hello",
    mentions=None,
    role_mentions=None,
    author=None,
    msg_type=None,
):
    """Create a fake Discord message."""
    if author is None:
        author = SimpleNamespace(id=42, display_name="User", name="User", bot=False)
    return SimpleNamespace(
        id=123,
        content=content,
        mentions=list(mentions or []),
        role_mentions=list(role_mentions or []),
        attachments=[],
        reference=None,
        created_at=datetime.now(timezone.utc),
        channel=channel or FakeTextChannel(),
        author=author,
        type=(
            msg_type
            if msg_type is not None
            else discord_platform.discord.MessageType.default
        ),
    )


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.setattr(discord_platform.discord, "DMChannel", FakeDMChannel, raising=False)
    monkeypatch.setattr(
        discord_platform.discord, "Thread", type("Thread", (), {}), raising=False
    )

    for _var in (
        "DISCORD_REQUIRE_MENTION",
        "DISCORD_THREAD_REQUIRE_MENTION",
        "DISCORD_FREE_RESPONSE_CHANNELS",
        "DISCORD_AUTO_THREAD",
        "DISCORD_NO_THREAD_CHANNELS",
        "DISCORD_ALLOWED_CHANNELS",
        "DISCORD_IGNORED_CHANNELS",
        "DISCORD_HISTORY_BACKFILL",
        "DISCORD_HISTORY_BACKFILL_LIMIT",
        "DISCORD_ALLOW_BOTS",
        "DISCORD_MENTION_ROLE_IDS",
        "DISCORD_ACCEPTED_MENTION_ROLE_IDS",
    ):
        monkeypatch.delenv(_var, raising=False)

    config = PlatformConfig(enabled=True, token="fake-token")
    a = DiscordAdapter(config)
    a._client = SimpleNamespace(user=SimpleNamespace(id=999))
    a._text_batch_delay_seconds = 0
    a.handle_message = AsyncMock()
    return a


# ── Tests 1-4: Config parsing ─────────────────────────────────────────────────


def test_parse_mention_role_ids_from_config_list(adapter):
    """Parses mention_role_ids as a list from config.extra, strips whitespace, ignores empties."""
    adapter.config.extra["mention_role_ids"] = ["1507142227590385838", " 123 ", ""]
    assert adapter._discord_accepted_role_ids() == {"1507142227590385838", "123"}


def test_parse_accepted_mention_role_ids_alias_from_config(adapter):
    """Falls back to accepted_mention_role_ids alias in config.extra."""
    adapter.config.extra["accepted_mention_role_ids"] = ["1507142227590385838"]
    assert adapter._discord_accepted_role_ids() == {"1507142227590385838"}


def test_parse_mention_role_ids_from_env_var(adapter, monkeypatch):
    """Parses DISCORD_MENTION_ROLE_IDS from a comma-separated env var."""
    monkeypatch.setenv("DISCORD_MENTION_ROLE_IDS", "1507142227590385838,123")
    assert adapter._discord_accepted_role_ids() == {"1507142227590385838", "123"}


def test_accepted_mention_role_ids_env_alias(adapter, monkeypatch):
    """Falls back to DISCORD_ACCEPTED_MENTION_ROLE_IDS when primary env var is absent."""
    monkeypatch.setenv("DISCORD_ACCEPTED_MENTION_ROLE_IDS", "1507142227590385838")
    assert adapter._discord_accepted_role_ids() == {"1507142227590385838"}


# ── Tests 5-7: Role-match helper ──────────────────────────────────────────────


def test_accepted_role_mention_matches(adapter):
    """Returns True when message.role_mentions includes an accepted role."""
    adapter.config.extra["mention_role_ids"] = ["1507142227590385838"]
    msg = make_message(role_mentions=[make_role(1507142227590385838)])
    assert adapter._has_accepted_role_mention(msg) is True


def test_unaccepted_role_mention_does_not_match(adapter):
    """Returns False when message.role_mentions contains only unaccepted roles."""
    adapter.config.extra["mention_role_ids"] = ["1507142227590385838"]
    msg = make_message(role_mentions=[make_role(999)])
    assert adapter._has_accepted_role_mention(msg) is False


def test_missing_role_mentions_is_safe(adapter):
    """Returns False without raising when message has no role_mentions attribute."""
    adapter.config.extra["mention_role_ids"] = ["1507142227590385838"]
    msg = SimpleNamespace(id=1, content="hi")  # deliberately no role_mentions
    assert adapter._has_accepted_role_mention(msg) is False


# ── Tests 8-9: Mention stripping ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_role_mention_stripping_removes_accepted_token(adapter, monkeypatch):
    """Accepted role token <@&ROLE_ID> is stripped from message content before the model."""
    monkeypatch.setenv("DISCORD_REQUIRE_MENTION", "false")
    adapter.config.extra["mention_role_ids"] = ["1507142227590385838"]
    msg = make_message(
        content="<@&1507142227590385838> diagnose this",
        role_mentions=[make_role(1507142227590385838)],
    )
    await adapter._handle_message(msg)
    adapter.handle_message.assert_awaited_once()
    event = adapter.handle_message.await_args.args[0]
    assert event.text == "diagnose this"
    assert "<@&1507142227590385838>" not in event.text


@pytest.mark.asyncio
async def test_role_mention_stripping_preserves_unaccepted_token(adapter, monkeypatch):
    """Unaccepted role token <@&ROLE_ID> is NOT stripped from message content."""
    monkeypatch.setenv("DISCORD_REQUIRE_MENTION", "false")
    adapter.config.extra["mention_role_ids"] = ["1507142227590385838"]
    msg = make_message(
        content="<@&999> diagnose this",
        role_mentions=[make_role(999)],
    )
    await adapter._handle_message(msg)
    adapter.handle_message.assert_awaited_once()
    event = adapter.handle_message.await_args.args[0]
    assert "<@&999>" in event.text


# ── Tests 10-11: require_mention gate ────────────────────────────────────────


@pytest.mark.asyncio
async def test_require_mention_gate_accepts_accepted_role_mention(adapter, monkeypatch):
    """Accepted role mention satisfies the require_mention gate (no direct bot mention needed)."""
    monkeypatch.setenv("DISCORD_REQUIRE_MENTION", "true")
    adapter.config.extra["mention_role_ids"] = ["1507142227590385838"]
    msg = make_message(
        content="<@&1507142227590385838> diagnose this",
        mentions=[],  # no direct bot @mention
        role_mentions=[make_role(1507142227590385838)],
    )
    await adapter._handle_message(msg)
    adapter.handle_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_require_mention_gate_rejects_unaccepted_role_mention(adapter, monkeypatch):
    """Unaccepted role mention does not satisfy the require_mention gate."""
    monkeypatch.setenv("DISCORD_REQUIRE_MENTION", "true")
    adapter.config.extra["mention_role_ids"] = ["1507142227590385838"]
    msg = make_message(
        content="<@&999> hello",
        mentions=[],
        role_mentions=[make_role(999)],
    )
    await adapter._handle_message(msg)
    adapter.handle_message.assert_not_awaited()


# ── Test 12: Bot-message filter ───────────────────────────────────────────────


def test_allow_bots_mentions_accepts_bot_with_accepted_role_mention(adapter):
    """DISCORD_ALLOW_BOTS=mentions: bot-authored message with accepted role mention passes filter."""
    adapter.config.extra["mention_role_ids"] = ["1507142227590385838"]
    client_user = SimpleNamespace(id=999)
    bot_author = SimpleNamespace(id=12345, bot=True, name="AlertBot")

    def _run_updated_bot_filter(message, allow_bots):
        """Replicate the updated on_message bot filter including role-mention check."""
        if message.author == client_user:
            return False
        if getattr(message.author, "bot", False):
            allow = allow_bots.lower().strip()
            if allow == "none":
                return False
            elif allow == "mentions":
                direct_mention = client_user in message.mentions
                role_mention = adapter._has_accepted_role_mention(message)
                if not direct_mention and not role_mention:
                    return False
        return True

    msg_with_role = make_message(
        author=bot_author,
        mentions=[],
        role_mentions=[make_role(1507142227590385838)],
    )
    assert _run_updated_bot_filter(msg_with_role, "mentions") is True

    msg_wrong_role = make_message(
        author=bot_author,
        mentions=[],
        role_mentions=[make_role(999)],
    )
    assert _run_updated_bot_filter(msg_wrong_role, "mentions") is False

    msg_no_role = make_message(author=bot_author, mentions=[], role_mentions=[])
    assert _run_updated_bot_filter(msg_no_role, "mentions") is False


# ── Test 13: Auto-thread ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_auto_thread_treats_accepted_role_mention_like_direct_mention(
    adapter, monkeypatch
):
    """Accepted role mention in a top-level channel triggers auto-thread creation."""
    monkeypatch.setenv("DISCORD_REQUIRE_MENTION", "true")
    monkeypatch.setenv("DISCORD_AUTO_THREAD", "true")
    adapter.config.extra["mention_role_ids"] = ["1507142227590385838"]

    fake_thread = SimpleNamespace(id=555, name="incident-thread", parent_id=None, parent=None)

    adapter._auto_create_thread = AsyncMock(return_value=fake_thread)
    mock_threads = MagicMock()
    mock_threads.__contains__ = lambda self, key: False
    adapter._threads = mock_threads

    msg = make_message(
        content="<@&1507142227590385838> service is down",
        mentions=[],
        role_mentions=[make_role(1507142227590385838)],
    )
    await adapter._handle_message(msg)

    adapter._auto_create_thread.assert_awaited_once()
    adapter.handle_message.assert_awaited_once()
