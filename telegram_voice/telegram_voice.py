import boto3
import requests
import logging
import os
import subprocess
import time
import json
import asyncio
import aiohttp
from google.cloud import dialogflow_v2 as dialogflow
from google.protobuf.json_format import MessageToDict

def detectIntent(projectId, sessionId, text, languageCode='en'):
    sessionClient = dialogflow.SessionsClient()
    session = sessionClient.session_path(projectId, sessionId)
    textInput = dialogflow.TextInput(text=text, language_code=languageCode)
    queryInput = dialogflow.QueryInput(text=textInput)
    response = sessionClient.detect_intent(request={"session": session, "query_input": queryInput})
    responseDict = MessageToDict(response._pb, preserving_proto_field_name=True)
    queryResult = responseDict.get("query_result", {})
    return {
        "intent": {"displayName": queryResult.get("intent", {}).get("display_name", "")},
        "parameters": queryResult.get("parameters", {}),
        "fulfillmentText": queryResult.get("fulfillment_text", ""),
        "fulfillmentMessages": queryResult.get("fulfillment_messages", [])
    }

class TelegramVoiceChannel:
    def __init__(self, token: str, s3BucketName: str = None):
        self.token = token
        self.baseUrl = f"https://api.telegram.org/bot{token}"
        self.s3BucketName = s3BucketName

    async def getFileDownloadUrl(self, fileId: str) -> str:
        url = f"{self.baseUrl}/getFile"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"file_id": fileId}) as response:
                data = await response.json()
        if data.get("ok"):
            filePath = data["result"]["file_path"]
            logging.info(f"Obtained file path: {filePath}")
            return f"https://api.telegram.org/file/bot{self.token}/{filePath}"
        logging.error("Failed to get file info from Telegram.")
        return ""

    @staticmethod
    def convertOggToWav(inputFile: str, outputFile: str) -> bool:
        # Convert an OGG audio file to WAV format using ffmpeg. Synchronous. (TODO: Consider async version if needed.)
        command = ["ffmpeg", "-y", "-f", "ogg", "-i", inputFile, "-ar", "16000", "-ac", "1", outputFile]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            logging.error(f"ffmpeg error: {result.stderr}")
            return False
        logging.info("ffmpeg conversion succeeded.")
        return True

    def uploadFileToS3(self, localFile: str, s3Key: str, bucketName: str, s3Client) -> bool:
        # Upload a file to S3 bucket. Synchronous. (TODO: Consider async version if needed.)
        try:
            s3Client.upload_file(localFile, bucketName, s3Key)
            logging.info(f"Uploaded {localFile} to bucket {bucketName} with key {s3Key}.")
            return True
        except Exception as e:
            logging.error(f"S3 upload error: {e}")
            return False

    def startTranscriptionJob(self, s3Client, transcribeClient, bucketName: str, s3Key: str) -> (str, dict):
        jobName = f"transcribe_{int(time.time())}"
        logging.info(f"Starting transcription job: {jobName}")
        transcribeClient.start_transcription_job(
            TranscriptionJobName=jobName,
            Media={'MediaFileUri': f"s3://{bucketName}/{s3Key}"},
            MediaFormat='wav',
            LanguageCode='en-US'
        )
        return jobName, transcribeClient.get_transcription_job(TranscriptionJobName=jobName)

    def waitForTranscription(self, transcribeClient, jobName: str) -> dict:
        delay = 1
        max_delay = 5
        while True:
            status = transcribeClient.get_transcription_job(TranscriptionJobName=jobName)
            jobStatus = status['TranscriptionJob']['TranscriptionJobStatus']
            logging.info(f"Job {jobName} status: {jobStatus}")
            if jobStatus in ['COMPLETED', 'FAILED']:
                return status
            time.sleep(delay)
            delay = min(delay * 2, max_delay)

    def getTranscribedText(self, status: dict) -> str:
        if status['TranscriptionJob']['TranscriptionJobStatus'] == 'COMPLETED':
            transcriptUri = status['TranscriptionJob']['Transcript']['TranscriptFileUri']
            transcriptRes = requests.get(transcriptUri)
            text = transcriptRes.json()['results']['transcripts'][0]['transcript']
            logging.info(f"Transcribed text: {text.strip()}")
            return text.strip()
        raise Exception("Transcription failed.")

    def synthesizeSpeech(self, text: str, s3Client, bucketName: str, config: dict) -> (str, str):
        """Synthesize speech from text using AWS Polly and upload to S3. Synchronous. (TODO: Consider async version if needed.)"""
        pollyClient = boto3.client(
            'polly',
            aws_access_key_id=config["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=config["AWS_SECRET_ACCESS_KEY"],
            region_name=config["AWS_REGION"]
        )
        logging.info("Synthesizing speech with Polly.")
        pollyRes = pollyClient.synthesize_speech(
            Text=text, OutputFormat='mp3', VoiceId='Joanna'
        )
        outputAudioFile = "response_audio.mp3"
        with open(outputAudioFile, 'wb') as file:
            file.write(pollyRes['AudioStream'].read())
        # Upload the synthesized audio to S3 and return the presigned URL
        return self.uploadSynthesizedAudio(outputAudioFile, s3Client, bucketName)

    def uploadSynthesizedAudio(self, audioFile: str, s3Client, bucketName: str) -> (str, str):
        """Upload the synthesized audio file to S3 and return the file path and presigned URL. Synchronous. (TODO: Consider async version if needed.)"""
        s3KeyOutput = "audio/response_audio.mp3"
        if self.uploadFileToS3(audioFile, s3KeyOutput, bucketName, s3Client):
            fileUrl = s3Client.generate_presigned_url(
                'get_object', Params={'Bucket': bucketName, 'Key': s3KeyOutput}, ExpiresIn=3600
            )
            logging.info(f"Uploaded response audio. URL: {fileUrl}")
            return audioFile, fileUrl
        raise Exception("Failed to upload synthesized speech.")

    async def downloadAndConvertVoice(self, message: dict) -> (str, str):
        """Download a Telegram voice message and convert it to WAV format. Async."""
        fileId = message.get("voice", {}).get("file_id")
        logging.info(f"Processing voice message. file_id: {fileId}")
        downloadUrl = await self.getFileDownloadUrl(fileId)
        if not downloadUrl:
            raise Exception("Failed to get download URL for voice message.")
        async with aiohttp.ClientSession() as session:
            async with session.get(downloadUrl) as resp:
                content = await resp.read()
        localOggFile = "incoming_audio.ogg"
        with open(localOggFile, "wb") as f:
            f.write(content)
        logging.info("Downloaded voice file.")
        localWavFile = "incoming_audio.wav"
        if not self.convertOggToWav(localOggFile, localWavFile):
            raise Exception("Conversion from OGG to WAV failed.")
        logging.info("Converted to WAV format.")
        return localOggFile, localWavFile

    def createS3Clients(self, config: dict) -> (object, object):
        """Create boto3 S3 and Transcribe clients using the provided config."""
        s3Client = boto3.client(
            's3',
            aws_access_key_id=config["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=config["AWS_SECRET_ACCESS_KEY"],
            region_name=config["AWS_REGION"]
        )
        transcribeClient = boto3.client(
            'transcribe',
            aws_access_key_id=config["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=config["AWS_SECRET_ACCESS_KEY"],
            region_name=config["AWS_REGION"]
        )
        return s3Client, transcribeClient

    def uploadAndTranscribe(self, s3Client, transcribeClient, config: dict, localWavFile: str) -> str:
        # Upload WAV file to S3 and transcribe it using AWS Transcribe.
        bucketName = config["S3_BUCKET_NAME"]
        s3Key = "audio/incoming_audio.wav"
        if not self.uploadFileToS3(localWavFile, s3Key, bucketName, s3Client):
            raise Exception("WAV upload failed.")
        jobName, _ = self.startTranscriptionJob(s3Client, transcribeClient, bucketName, s3Key)
        status = self.waitForTranscription(transcribeClient, jobName)
        return self.getTranscribedText(status)

    def getResponseText(self, message: dict, transcript: str, projectId, dialogflowHandler) -> str:
        # Get response text from Dialogflow or use a fallback if Dialogflow is not available.
        if dialogflowHandler is not None and projectId:
            chatId = str(message.get("chat", {}).get("id"))
            queryResult = detectIntent(projectId, chatId, transcript)
            logging.info(f"Dialogflow queryResult: {json.dumps(queryResult, indent=2)}")
            responseDf = dialogflowHandler.processRequest({"queryResult": queryResult})
            responseText = responseDf.get("fulfillmentText", "")
            if not responseText:
                logging.warning("Empty fulfillmentText from Dialogflow; using fallback.")
                responseText = "I'm sorry, I didn't understand that request."
        else:
            responseText = "You said: " + transcript
        return responseText

    def synthesizeAndSendResponse(self, message: dict, responseText: str, s3Client, config: dict) -> None:
        # Synthesize a response, upload to S3, and send as audio to the Telegram chat.
        bucketName = config["S3_BUCKET_NAME"]
        _, fileUrl = self.synthesizeSpeech(responseText, s3Client, bucketName, config)
        sendUrl = f"{self.baseUrl}/sendAudio"
        data = {"chat_id": message.get("chat", {}).get("id"), "audio": fileUrl}
        requests.post(sendUrl, data=data)
        logging.info("Sent audio response to Telegram.")

    def cleanupVoiceFiles(self, localOggFile: str, localWavFile: str) -> None:
        # Remove temporary audio files from the local filesystem.
        os.remove(localOggFile)
        os.remove(localWavFile)
        os.remove("response_audio.mp3")
        logging.info("Cleaned up temporary files.")

    async def handleVoiceMessage(self, message: dict, config: dict, projectId=None, dialogflowHandler=None) -> dict:
        # Main entry point for handling a Telegram voice message: download, transcribe, process, synthesize, and respond. Async.
        try:
            localOgg, localWav = await self.downloadAndConvertVoice(message)
            s3Client, transcribeClient = self.createS3Clients(config)
            transcript = self.uploadAndTranscribe(s3Client, transcribeClient, config, localWav)
            responseText = self.getResponseText(message, transcript, projectId, dialogflowHandler)
            logging.info(f"Final response text: {responseText}")
            self.synthesizeAndSendResponse(message, responseText, s3Client, config)
            self.cleanupVoiceFiles(localOgg, localWav)
            return {"status": 0}
        except Exception as e:
            logging.error(f"Error processing voice message: {e}")
            return {"status": 1, "error": str(e)}

    async def processWebhook(self, requestData: dict, dialogflowHandler=None, config=None, projectId=None) -> dict:
        # Process an incoming Telegram webhook event. Async.
        logging.info("Received Telegram webhook event.")
        message = requestData.get("message", {})
        if "voice" in message:
            return await self.handleVoiceMessage(message, config, projectId, dialogflowHandler)
        logging.info("Processing non-voice message.")
        return {"status": 0}
