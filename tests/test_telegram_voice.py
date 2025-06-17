import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
import types
from unittest.mock import MagicMock, patch, AsyncMock
from telegram_voice.telegram_voice import TelegramVoiceChannel

class MockS3Client:
    def upload_file(self, localFile, bucketName, s3Key):
        pass
    def generate_presigned_url(self, *args, **kwargs):
        return "https://dummy-s3-url"

class MockTranscribeClient:
    def start_transcription_job(self, **kwargs):
        pass
    def get_transcription_job(self, TranscriptionJobName):
        return {"TranscriptionJob": {"TranscriptionJobStatus": "COMPLETED", "Transcript": {"TranscriptFileUri": "http://dummy-transcript"}}}

@pytest.mark.asyncio
async def testGetFileDownloadUrl(monkeypatch):
    channel = TelegramVoiceChannel(token="dummy")
    mockResponse = AsyncMock()
    mockResponse.json = AsyncMock(return_value={"ok": True, "result": {"file_path": "voice.ogg"}})
    sessionCtx = AsyncMock()
    sessionCtx.__aenter__.return_value = mockResponse
    with patch("aiohttp.ClientSession.post", return_value=sessionCtx):
        url = await channel.getFileDownloadUrl("fileid")
        assert url.endswith("voice.ogg")

@pytest.mark.asyncio
async def testDownloadAndConvertVoice(monkeypatch):
    channel = TelegramVoiceChannel(token="dummy")
    async def dummyGetFileDownloadUrl(fileId):
        return "http://dummy-url"
    monkeypatch.setattr(channel, "getFileDownloadUrl", dummyGetFileDownloadUrl)
    sessionCtx = AsyncMock()
    sessionCtx.__aenter__.return_value.read = AsyncMock(return_value=b"dummy")
    with patch("aiohttp.ClientSession.get", return_value=sessionCtx):
        with patch("builtins.open", MagicMock()):
            monkeypatch.setattr(channel, "convertOggToWav", lambda *a, **k: True)
            ogg, wav = await channel.downloadAndConvertVoice({"voice": {"file_id": "dummy"}})
            assert ogg == "incoming_audio.ogg"
            assert wav == "incoming_audio.wav"

def testConvertOggToWav(monkeypatch):
    channel = TelegramVoiceChannel(token="dummy")
    monkeypatch.setattr("subprocess.run", lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=""))
    assert channel.convertOggToWav("in.ogg", "out.wav") is True
    monkeypatch.setattr("subprocess.run", lambda *a, **k: types.SimpleNamespace(returncode=1, stderr="fail"))
    assert channel.convertOggToWav("in.ogg", "out.wav") is False

def testUploadFileToS3():
    channel = TelegramVoiceChannel(token="dummy")
    client = MockS3Client()
    assert channel.uploadFileToS3("file", "key", "bucket", client) is True

def testUploadFileToS3Error(monkeypatch):
    channel = TelegramVoiceChannel(token="dummy")
    class BadS3:
        def upload_file(self, *a, **k): raise Exception("fail")
    assert channel.uploadFileToS3("file", "key", "bucket", BadS3()) is False

def testCreateS3Clients(monkeypatch):
    channel = TelegramVoiceChannel(token="dummy")
    monkeypatch.setattr("boto3.client", lambda *a, **k: MockS3Client())
    s3, transcribe = channel.createS3Clients({"AWS_ACCESS_KEY_ID": "a", "AWS_SECRET_ACCESS_KEY": "b", "AWS_REGION": "us"})
    assert isinstance(s3, MockS3Client)
    assert isinstance(transcribe, MockS3Client)

def testSynthesizeSpeech(monkeypatch):
    channel = TelegramVoiceChannel(token="dummy")
    monkeypatch.setattr("boto3.client", lambda *a, **k: types.SimpleNamespace(synthesize_speech=lambda **kw: {"AudioStream": types.SimpleNamespace(read=lambda: b"audio")}))
    with patch("builtins.open", MagicMock()):
        channel.uploadFileToS3 = lambda *a, **k: True
        DummyS3 = MockS3Client()
        DummyS3.generate_presigned_url = lambda *a, **k: "https://dummy-s3-url"
        audio, url = channel.synthesizeSpeech("hi", DummyS3, "bucket", {"AWS_ACCESS_KEY_ID": "a", "AWS_SECRET_ACCESS_KEY": "b", "AWS_REGION": "us", "S3_BUCKET_NAME": "bucket"})
        assert audio == "response_audio.mp3"
        assert url == "https://dummy-s3-url"

def testUploadSynthesizedAudio():
    channel = TelegramVoiceChannel(token="dummy")
    channel.uploadFileToS3 = lambda *a, **k: True
    DummyS3 = MockS3Client()
    DummyS3.generate_presigned_url = lambda *a, **k: "https://dummy-s3-url"
    audio, url = channel.uploadSynthesizedAudio("audio.mp3", DummyS3, "bucket")
    assert audio == "audio.mp3"
    assert url == "https://dummy-s3-url"

def testUploadSynthesizedAudioFail():
    channel = TelegramVoiceChannel(token="dummy")
    channel.uploadFileToS3 = lambda *a, **k: False
    DummyS3 = MockS3Client()
    with pytest.raises(Exception):
        channel._uploadSynthesizedAudio("audio.mp3", DummyS3, "bucket")

def testUploadAndTranscribe(monkeypatch):
    channel = TelegramVoiceChannel(token="dummy")
    monkeypatch.setattr(channel, "uploadFileToS3", lambda *a, **k: True)
    monkeypatch.setattr(channel, "startTranscriptionJob", lambda *a, **k: ("job", None))
    monkeypatch.setattr(channel, "waitForTranscription", lambda *a, **k: {"TranscriptionJob": {"TranscriptionJobStatus": "COMPLETED", "Transcript": {"TranscriptFileUri": "http://dummy"}}})
    monkeypatch.setattr(channel, "getTranscribedText", lambda *a, **k: "text")
    result = channel.uploadAndTranscribe(None, None, {"S3_BUCKET_NAME": "bucket"}, "file.wav")
    assert result == "text"

def testGetResponseText(monkeypatch):
    channel = TelegramVoiceChannel(token="dummy")
    # Dialogflow present
    class DummyHandler:
        def processRequest(self, req):
            return {"fulfillmentText": "ok"}
    monkeypatch.setattr("telegram_voice.telegram_voice.detectIntent", lambda *a, **k: {"intent": {}, "parameters": {}, "fulfillmentText": "hi", "fulfillmentMessages": []})
    message = {"chat": {"id": 1}}
    resp = channel.getResponseText(message, "text", "pid", DummyHandler())
    assert resp == "ok"
    # Dialogflow fallback
    class DummyHandler2:
        def processRequest(self, req):
            return {"fulfillmentText": ""}
    resp = channel.getResponseText(message, "text", "pid", DummyHandler2())
    assert resp.startswith("I'm sorry")
    # No dialogflow
    resp = channel.getResponseText(message, "text", None, None)
    assert resp.startswith("You said:")

def testCleanupVoiceFiles(monkeypatch):
    channel = TelegramVoiceChannel(token="dummy")
    monkeypatch.setattr("os.remove", lambda *a, **k: None)
    channel.cleanupVoiceFiles("ogg", "wav")

@pytest.mark.asyncio
async def testHandleVoiceMessage(monkeypatch):
    channel = TelegramVoiceChannel(token="dummy")
    monkeypatch.setattr(channel, "downloadAndConvertVoice", AsyncMock(return_value=("ogg", "wav")))
    monkeypatch.setattr(channel, "createS3Clients", lambda c: (MockS3Client(), MockTranscribeClient()))
    monkeypatch.setattr(channel, "uploadAndTranscribe", lambda *a, **k: "transcript")
    monkeypatch.setattr(channel, "getResponseText", lambda *a, **k: "hello")
    monkeypatch.setattr(channel, "synthesizeAndSendResponse", lambda *a, **k: None)
    monkeypatch.setattr(channel, "cleanupVoiceFiles", lambda *a, **k: None)
    result = await channel.handleVoiceMessage({}, {"S3_BUCKET_NAME": "bucket"})
    assert result["status"] == 0
    # Test error case
    async def failDownload(*a, **k): raise Exception("fail")
    monkeypatch.setattr(channel, "downloadAndConvertVoice", failDownload)
    result = await channel.handleVoiceMessage({}, {"S3_BUCKET_NAME": "bucket"})
    assert result["status"] == 1

@pytest.mark.asyncio
async def testProcessWebhook(monkeypatch):
    channel = TelegramVoiceChannel(token="dummy")
    monkeypatch.setattr(channel, "handleVoiceMessage", AsyncMock(return_value={"status": 0}))
    # Voice message
    resp = await channel.processWebhook({"message": {"voice": {}}}, None, {"S3_BUCKET_NAME": "bucket"}, None)
    assert resp["status"] == 0
    # Non-voice message
    resp = await channel.processWebhook({"message": {"text": "hi"}}, None, {"S3_BUCKET_NAME": "bucket"}, None)
    assert resp["status"] == 0
