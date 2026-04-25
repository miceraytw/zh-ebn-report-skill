"""Tests for the Codex CLI LLM backend."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from zh_ebn_report.clients.codex_cli import (
    CodexCliClient,
    CodexCliError,
    _build_exec_prompt,
    _parse_model_json,
)
from zh_ebn_report.clients.system import CachedSystemBlock
from zh_ebn_report.config import LlmConfig


def _cfg(**overrides: object) -> LlmConfig:
    base = dict(
        backend="codex",
        api_key="",
        base_url=None,
        default_model="gpt-5.4",
        haiku_model="gpt-5.4-mini",
        sonnet_model="gpt-5.4",
        opus_model="gpt-5.2",
    )
    base.update(overrides)
    return LlmConfig(**base)  # type: ignore[arg-type]


class _FakeProcess:
    def __init__(
        self,
        *,
        stdout: bytes = b"",
        stderr: bytes = b"",
        returncode: int = 0,
    ):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self.kill_called = False

    def communicate(self, input: bytes | None = None):  # noqa: A002
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[tuple[bytes, bytes]] = loop.create_future()
        fut.set_result((self._stdout, self._stderr))
        return fut

    def kill(self) -> None:
        self.kill_called = True

    async def wait(self) -> int:
        return self.returncode


class TestBuildExecPrompt:
    def test_contains_system_and_user_blocks(self) -> None:
        prompt = _build_exec_prompt(
            [CachedSystemBlock(text="SYS-ONE"), CachedSystemBlock(text="SYS-TWO")],
            "USER",
            json_mode=False,
        )
        assert "<system>" in prompt
        assert "SYS-ONE" in prompt
        assert "SYS-TWO" in prompt
        assert "<user>" in prompt
        assert "USER" in prompt

    def test_json_mode_adds_strict_instruction(self) -> None:
        prompt = _build_exec_prompt(
            [CachedSystemBlock(text="SYS")],
            "USER",
            json_mode=True,
        )
        assert "Return valid JSON only" in prompt


class TestParseModelJson:
    def test_plain_json(self) -> None:
        assert _parse_model_json('{"a": 1}') == {"a": 1}

    def test_markdown_fenced_json(self) -> None:
        assert _parse_model_json("```json\n{\"a\": 1}\n```") == {"a": 1}


class TestCompleteFlow:
    @pytest.mark.asyncio
    async def test_successful_call_reads_output_file(self, tmp_path: Path) -> None:
        client = CodexCliClient(_cfg())
        fake = _FakeProcess()

        def _spawn_tempfile(*args: object, **kwargs: object):  # noqa: ANN202
            class _Ctx:
                def __enter__(self_inner):
                    self_inner.path = tmp_path / "codex-last.txt"
                    self_inner.file = open(
                        self_inner.path, kwargs.get("mode", "w"), encoding="utf-8"
                    )
                    return self_inner.file

                def __exit__(self_inner, exc_type, exc, tb):
                    self_inner.file.close()
                    return False

            return _Ctx()

        async def _wait_for(awaitable, timeout):  # noqa: ANN001, ANN202
            await awaitable
            (tmp_path / "codex-last.txt").write_text("OK", encoding="utf-8")
            return (b"", b"")

        with (
            patch(
                "asyncio.create_subprocess_exec",
                AsyncMock(return_value=fake),
            ),
            patch(
                "zh_ebn_report.clients.codex_cli.tempfile.NamedTemporaryFile",
                _spawn_tempfile,
            ),
            patch("asyncio.wait_for", _wait_for),
        ):
            out = await client.complete(
                tier="haiku",
                system_blocks=[CachedSystemBlock(text="sys")],
                user_message="hi",
            )
        assert out == "OK"

    @pytest.mark.asyncio
    async def test_complete_json_parses_inner_json(self, tmp_path: Path) -> None:
        client = CodexCliClient(_cfg())
        fake = _FakeProcess()

        def _spawn_tempfile(*args: object, **kwargs: object):  # noqa: ANN202
            class _Ctx:
                def __enter__(self_inner):
                    self_inner.path = tmp_path / "codex-last.json"
                    self_inner.file = open(
                        self_inner.path, kwargs.get("mode", "w"), encoding="utf-8"
                    )
                    return self_inner.file

                def __exit__(self_inner, exc_type, exc, tb):
                    self_inner.file.close()
                    return False

            return _Ctx()

        async def _wait_for(awaitable, timeout):  # noqa: ANN001, ANN202
            await awaitable
            (tmp_path / "codex-last.json").write_text('{"k": 42}', encoding="utf-8")
            return (b"", b"")

        with (
            patch(
                "asyncio.create_subprocess_exec",
                AsyncMock(return_value=fake),
            ),
            patch(
                "zh_ebn_report.clients.codex_cli.tempfile.NamedTemporaryFile",
                _spawn_tempfile,
            ),
            patch("asyncio.wait_for", _wait_for),
        ):
            out = await client.complete_json(
                tier="sonnet",
                system_blocks=[CachedSystemBlock(text="sys")],
                user_message="hi",
            )
        assert out == {"k": 42}

    @pytest.mark.asyncio
    async def test_nonzero_exit_raises(self, tmp_path: Path) -> None:
        client = CodexCliClient(_cfg())
        fake = _FakeProcess(stderr=b"boom", returncode=2)

        def _spawn_tempfile(*args: object, **kwargs: object):  # noqa: ANN202
            class _Ctx:
                def __enter__(self_inner):
                    self_inner.path = tmp_path / "codex-last.txt"
                    self_inner.file = open(
                        self_inner.path, kwargs.get("mode", "w"), encoding="utf-8"
                    )
                    return self_inner.file

                def __exit__(self_inner, exc_type, exc, tb):
                    self_inner.file.close()
                    return False

            return _Ctx()

        with (
            patch(
                "asyncio.create_subprocess_exec",
                AsyncMock(return_value=fake),
            ),
            patch(
                "zh_ebn_report.clients.codex_cli.tempfile.NamedTemporaryFile",
                _spawn_tempfile,
            ),
            patch("zh_ebn_report.clients.codex_cli.AsyncRetrying") as retrying,
        ):
            async def _single(self_):  # noqa: ANN001
                class _Attempt:
                    def __enter__(self):
                        return self

                    def __exit__(self, exc_type, exc, tb):
                        return False

                yield _Attempt()

            retrying.return_value.__aiter__ = _single
            with pytest.raises(CodexCliError, match="exited 2"):
                await client.complete(
                    tier="haiku",
                    system_blocks=[CachedSystemBlock(text="sys")],
                    user_message="hi",
                )
