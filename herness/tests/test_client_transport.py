from __future__ import annotations

import httpx
import pytest

from octocoder.client import NetworkError, OpenAICompatClient
from octocoder.conversation import ConversationManager


class BrokenStream:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise httpx.RemoteProtocolError(
            "peer closed connection without sending complete message body"
        )


class FakeCompletions:
    async def create(self, **_kwargs):
        return BrokenStream()


class FakeChat:
    completions = FakeCompletions()


class FakeOpenAI:
    chat = FakeChat()


@pytest.mark.asyncio
async def test_openai_compat_normalizes_incomplete_chunked_stream() -> None:
    client = OpenAICompatClient.__new__(OpenAICompatClient)
    client.model = "test-model"
    client.max_output_tokens = 128
    client._client = FakeOpenAI()
    conversation = ConversationManager()
    conversation.add_user_message("hello")

    with pytest.raises(NetworkError, match="Network stream interrupted"):
        async for _event in client.stream(conversation):
            pass
