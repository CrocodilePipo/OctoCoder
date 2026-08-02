from __future__ import annotations

import httpx
import pytest

from octocoder.config import VoiceConfig, VoiceProviderProfile
from octocoder.voice import (
    AliyunVoiceProvider,
    OpenAICompatibleVoiceProvider,
    SiliconFlowVoiceProvider,
    VoiceErrorKind,
    VoiceProviderError,
    VolcengineVoiceProvider,
    create_batch_asr_provider,
    create_tts_provider,
    create_voice_provider,
)


def _config(**overrides) -> VoiceConfig:
    values = {
        "enabled": True,
        "base_url": "https://voice.example/v1/",
        "api_key": "voice-secret",
        "stt_model": "stt-model",
        "tts_model": "tts-model",
        "voice": "speaker",
        "language": "zh",
    }
    values.update(overrides)
    return VoiceConfig(**values)


@pytest.mark.asyncio
async def test_transcribe_sends_compatible_multipart_request() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://voice.example/v1/audio/transcriptions"
        assert request.headers["authorization"] == "Bearer voice-secret"
        body = await request.aread()
        assert b'name="model"' in body and b"stt-model" in body
        assert b'name="language"' in body and b"zh" in body
        assert b'filename="recording.webm"' in body
        assert b"audio/webm" in body
        assert b"encoded-audio" in body
        return httpx.Response(200, json={"text": "  hello voice  "})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleVoiceProvider(_config(), client=client)
        text = await provider.transcribe(
            b"encoded-audio",
            filename="recording.webm",
            content_type="audio/webm",
        )
    assert text == "hello voice"


@pytest.mark.asyncio
async def test_synthesize_sends_compatible_json_request() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://voice.example/v1/audio/speech"
        assert request.headers["authorization"] == "Bearer voice-secret"
        payload = __import__("json").loads((await request.aread()).decode())
        assert payload == {
            "model": "tts-model",
            "voice": "speaker",
            "input": "final answer",
            "response_format": "mp3",
        }
        return httpx.Response(
            200,
            content=b"mp3-bytes",
            headers={"content-type": "audio/mpeg"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleVoiceProvider(_config(), client=client)
        audio = await provider.synthesize("final answer")
    assert audio.data == b"mp3-bytes"
    assert audio.content_type == "audio/mpeg"


@pytest.mark.asyncio
async def test_provider_error_is_sanitized() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad credentials"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleVoiceProvider(_config(), client=client)
        with pytest.raises(VoiceProviderError, match="HTTP 401") as caught:
            await provider.transcribe(
                b"audio",
                filename="recording.webm",
                content_type="audio/webm",
            )
    assert "voice-secret" not in str(caught.value)
    assert caught.value.kind is VoiceErrorKind.AUTHENTICATION
    assert caught.value.retryable is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status, kind, retryable",
    [
        (400, VoiceErrorKind.INVALID_REQUEST, False),
        (401, VoiceErrorKind.AUTHENTICATION, False),
        (403, VoiceErrorKind.AUTHORIZATION, False),
        (415, VoiceErrorKind.UNSUPPORTED_FORMAT, False),
        (429, VoiceErrorKind.RATE_LIMIT, True),
        (500, VoiceErrorKind.SERVER, True),
        (503, VoiceErrorKind.SERVER, True),
    ],
)
async def test_http_errors_are_classified(status, kind, retryable) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"message": "provider failure"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleVoiceProvider(_config(), client=client)
        with pytest.raises(VoiceProviderError) as caught:
            await provider.transcribe(b"audio", filename="a.wav", content_type="audio/wav")
    assert caught.value.kind is kind
    assert caught.value.retryable is retryable
    assert caught.value.status_code == status


@pytest.mark.asyncio
async def test_transport_and_timeout_errors_are_retryable() -> None:
    errors = [
        httpx.ReadTimeout("slow response"),
        httpx.RemoteProtocolError("peer closed connection without sending complete message body"),
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        raise errors.pop(0)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleVoiceProvider(_config(), client=client)
        with pytest.raises(VoiceProviderError) as timeout_error:
            await provider.transcribe(b"audio", filename="a.wav", content_type="audio/wav")
        with pytest.raises(VoiceProviderError) as transport_error:
            await provider.transcribe(b"audio", filename="a.wav", content_type="audio/wav")
    assert timeout_error.value.kind is VoiceErrorKind.TIMEOUT
    assert timeout_error.value.retryable is True
    assert transport_error.value.kind is VoiceErrorKind.TRANSPORT
    assert transport_error.value.retryable is True


@pytest.mark.asyncio
async def test_transcribe_rejects_invalid_or_empty_json() -> None:
    responses = [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"text": "  "}),
    ]

    async def handler(_request: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleVoiceProvider(_config(), client=client)
        with pytest.raises(VoiceProviderError, match="invalid JSON"):
            await provider.transcribe(b"a", filename="a.webm", content_type="audio/webm")
        with pytest.raises(VoiceProviderError, match="no text"):
            await provider.transcribe(b"a", filename="a.webm", content_type="audio/webm")


@pytest.mark.asyncio
async def test_synthesize_rejects_non_audio_response() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleVoiceProvider(_config(), client=client)
        with pytest.raises(VoiceProviderError, match="did not contain audio"):
            await provider.synthesize("hello")


def test_provider_factory_selects_vendor_adapter() -> None:
    assert isinstance(
        create_voice_provider(_config(provider="siliconflow")),
        SiliconFlowVoiceProvider,
    )
    assert isinstance(
        create_voice_provider(_config(provider="aliyun")),
        AliyunVoiceProvider,
    )
    assert isinstance(
        create_voice_provider(_config(provider="openai")),
        OpenAICompatibleVoiceProvider,
    )
    assert isinstance(
        create_voice_provider(
            _config(provider="volcengine", app_id="test-app-id")
        ),
        VolcengineVoiceProvider,
    )


def test_capability_factories_use_requested_profile() -> None:
    profile = VoiceProviderProfile(
        id="aliyun-main",
        provider="aliyun",
        base_url="https://dashscope.aliyuncs.com",
        api_key="secret",
        batch_stt_model="qwen3-asr-flash",
        tts_model="qwen-audio-3.0-tts-flash",
        voice="longanhuan_v3.6",
    )
    assert isinstance(create_batch_asr_provider(profile), AliyunVoiceProvider)
    assert isinstance(create_tts_provider(profile), AliyunVoiceProvider)


@pytest.mark.asyncio
async def test_siliconflow_transcription_uses_documented_fields() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.siliconflow.cn/v1/audio/transcriptions"
        body = await request.aread()
        assert b"FunAudioLLM/SenseVoiceSmall" in body
        assert b"response_format" not in body
        assert b'name="language"' not in body
        return httpx.Response(200, json={"text": "silicon transcript"})

    config = _config(
        provider="siliconflow",
        base_url="https://api.siliconflow.cn/v1",
        stt_model="FunAudioLLM/SenseVoiceSmall",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = create_voice_provider(config, client=client)
        text = await provider.transcribe(
            b"audio", filename="recording.webm", content_type="audio/webm"
        )
    assert text == "silicon transcript"


@pytest.mark.asyncio
async def test_aliyun_transcription_sends_base64_audio() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        payload = __import__("json").loads((await request.aread()).decode())
        assert payload["model"] == "qwen3-asr-flash"
        assert payload["stream"] is False
        assert payload["asr_options"] == {"language": "zh"}
        audio = payload["messages"][0]["content"][0]["input_audio"]["data"]
        assert audio == "data:audio/webm;base64,YXVkaW8="
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": " aliyun transcript "}}]},
        )

    config = _config(
        provider="aliyun",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        stt_model="qwen3-asr-flash",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = create_voice_provider(config, client=client)
        text = await provider.transcribe(
            b"audio", filename="recording.webm", content_type="audio/webm;codecs=opus"
        )
    assert text == "aliyun transcript"


@pytest.mark.asyncio
async def test_aliyun_speech_downloads_generated_audio() -> None:
    requests: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.method == "POST":
            assert request.url == "https://workspace.cn-beijing.maas.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer"
            payload = __import__("json").loads((await request.aread()).decode())
            assert payload == {
                "model": "qwen-audio-3.0-tts-flash",
                "input": {
                    "text": "final answer",
                    "voice": "longanhuan_v3.6",
                    "format": "mp3",
                    "language_hints": ["zh"],
                },
            }
            return httpx.Response(
                200,
                json={"output": {"audio": {"data": "", "url": "https://audio.example/result.mp3"}}},
            )
        assert request.url == "https://audio.example/result.mp3"
        return httpx.Response(200, content=b"aliyun-mp3", headers={"content-type": "audio/mpeg"})

    config = _config(
        provider="aliyun",
        base_url="https://workspace.cn-beijing.maas.aliyuncs.com",
        tts_model="qwen-audio-3.0-tts-flash",
        voice="longanhuan_v3.6",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = create_voice_provider(config, client=client)
        audio = await provider.synthesize("final answer")
    assert audio.data == b"aliyun-mp3"
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_volcengine_transcription_uses_flash_api_contract() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash"
        assert request.headers["x-api-app-key"] == "test-app-id"
        assert request.headers["x-api-access-key"] == "test-access-token"
        assert request.headers["x-api-resource-id"] == "volc.bigasr.auc_turbo"
        assert request.headers["x-api-sequence"] == "-1"
        payload = __import__("json").loads((await request.aread()).decode())
        assert payload == {
            "user": {"uid": "test-app-id"},
            "audio": {"data": "YXVkaW8="},
            "request": {"model_name": "bigmodel"},
        }
        return httpx.Response(
            200,
            headers={"X-Api-Status-Code": "20000000", "X-Api-Message": "OK"},
            json={"result": {"text": " 火山转写结果 "}},
        )

    config = _config(
        provider="volcengine",
        base_url="https://openspeech.bytedance.com",
        api_key="test-access-token",
        app_id="test-app-id",
        stt_model="volc.bigasr.auc_turbo",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = create_voice_provider(config, client=client)
        text = await provider.transcribe(
            b"audio", filename="recording.webm", content_type="audio/webm"
        )
    assert text == "火山转写结果"


@pytest.mark.asyncio
async def test_volcengine_speech_uses_bearer_contract() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://openspeech.bytedance.com/api/v1/tts"
        assert request.headers["authorization"] == "Bearer;test-access-token"
        payload = __import__("json").loads((await request.aread()).decode())
        assert payload["app"] == {
            "appid": "test-app-id",
            "token": "test-access-token",
            "cluster": "volcano_tts",
        }
        assert payload["audio"] == {
            "voice_type": "zh_female_cancan_mars_bigtts",
            "encoding": "mp3",
            "speed_ratio": 1.0,
        }
        assert payload["request"]["text"] == "最终回复"
        assert payload["request"]["operation"] == "query"
        assert payload["request"]["model"] == "seed-tts-1.1"
        return httpx.Response(
            200,
            json={
                "code": 3000,
                "message": "Success",
                "sequence": -1,
                "data": "bXAzLWF1ZGlv",
            },
        )

    config = _config(
        provider="volcengine",
        base_url="https://openspeech.bytedance.com",
        api_key="test-access-token",
        app_id="test-app-id",
        tts_model="seed-tts-1.1",
        voice="zh_female_cancan_mars_bigtts",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = create_voice_provider(config, client=client)
        audio = await provider.synthesize("最终回复")
    assert audio.data == b"mp3-audio"
    assert audio.content_type == "audio/mpeg"


def test_volcengine_normalizes_bearer_prefix() -> None:
    config = _config(
        provider="volcengine",
        api_key="Bearer; test-access-token",
        app_id="test-app-id",
    )
    provider = VolcengineVoiceProvider(config)
    assert provider._credentials() == ("test-app-id", "test-access-token")
