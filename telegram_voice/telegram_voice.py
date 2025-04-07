import boto3
import requests
import logging
import os
import subprocess
import time
import json
from google.cloud import dialogflow_v2 as dialogflow
from google.protobuf.json_format import MessageToDict

def detectIntent(projectId, sessionId, text, languageCode='en'):
    sessionClient = dialogflow.SessionsClient()
    session = sessionClient.session_path(projectId, sessionId)
    textInput = dialogflow.TextInput(text=text, language_code=languageCode)
    queryInput = dialogflow.QueryInput(text=textInput)
    response = sessionClient.detect_intent(request={"session": session, "query_input": queryInput})
    response_dict = MessageToDict(response._pb, preserving_proto_field_name=True)
    query_result = response_dict.get("query_result", {})
    return {
        "intent": {"displayName": query_result.get("intent", {}).get("display_name", "")},
        "parameters": query_result.get("parameters", {}),
        "fulfillmentText": query_result.get("fulfillment_text", ""),
        "fulfillmentMessages": query_result.get("fulfillment_messages", [])
    }

class TelegramVoiceChannel:
    def __init__(self, token: str, s3BucketName: str = None):
        self.token = token
        self.baseUrl = f"https://api.telegram.org/bot{token}"
        self.s3BucketName = s3BucketName

    def getFileDownloadUrl(self, file_id: str) -> str:
        url = f"{self.baseUrl}/getFile"
        response = requests.post(url, json={"file_id": file_id})
        data = response.json()
        if data.get("ok"):
            file_path = data["result"]["file_path"]
            logging.info(f"Obtained file path from Telegram: {file_path}")
            return f"https://api.telegram.org/file/bot{self.token}/{file_path}"
        logging.error("Failed to get file info from Telegram.")
        return ""

    @staticmethod
    def convertOggToWav(inputFile: str, outputFile: str) -> bool:
        command = ["ffmpeg", "-y", "-f", "ogg", "-i", inputFile, "-ar", "16000", "-ac", "1", outputFile]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            logging.error(f"ffmpeg conversion error: {result.stderr}")
            return False
        logging.info("ffmpeg conversion succeeded.")
        return True

    def uploadFileToS3(self, localFile: str, s3_key: str, bucket_name: str, s3_client) -> bool:
        try:
            s3_client.upload_file(localFile, bucket_name, s3_key)
            logging.info(f"Uploaded {localFile} to S3 bucket {bucket_name} with key {s3_key}.")
            return True
        except Exception as e:
            logging.error(f"Error uploading file to S3: {e}")
            return False

    def startTranscriptionJob(self, s3_client, transcribe_client, bucket_name: str, s3_key: str) -> (str, dict):
        job_name = f"transcribe_{int(time.time())}"
        logging.info(f"Starting transcription job: {job_name}")
        transcribe_client.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={'MediaFileUri': f"s3://{bucket_name}/{s3_key}"},
            MediaFormat='wav',
            LanguageCode='en-US'
        )
        return job_name, transcribe_client.get_transcription_job(TranscriptionJobName=job_name)

    def waitForTranscription(self, transcribe_client, job_name: str) -> dict:
        while True:
            status = transcribe_client.get_transcription_job(TranscriptionJobName=job_name)
            job_status = status['TranscriptionJob']['TranscriptionJobStatus']
            logging.info(f"Transcription job {job_name} status: {job_status}")
            if job_status in ['COMPLETED', 'FAILED']:
                return status
            time.sleep(5)

    def getTranscribedText(self, status: dict) -> str:
        if status['TranscriptionJob']['TranscriptionJobStatus'] == 'COMPLETED':
            transcript_uri = status['TranscriptionJob']['Transcript']['TranscriptFileUri']
            transcript_response = requests.get(transcript_uri)
            transcribedText = transcript_response.json()['results']['transcripts'][0]['transcript']
            logging.info(f"Transcribed text: {transcribedText.strip()}")
            return transcribedText.strip()
        else:
            raise Exception("Transcription failed.")

    def synthesizeSpeech(self, text: str, s3_client, bucket_name: str) -> (str, str):
        polly_client = boto3.client(
            'polly',
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=os.getenv("AWS_REGION")
        )
        logging.info("Synthesizing speech with Amazon Polly.")
        polly_response = polly_client.synthesize_speech(
            Text=text,
            OutputFormat='mp3',
            VoiceId='Joanna'
        )
        outputAudioFile = "response_audio.mp3"
        with open(outputAudioFile, 'wb') as file:
            file.write(polly_response['AudioStream'].read())
        s3_key_output = "audio/response_audio.mp3"
        if self.uploadFileToS3(outputAudioFile, s3_key_output, bucket_name, s3_client):
            fileUrl = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': s3_key_output},
                ExpiresIn=3600
            )
            logging.info(f"Uploaded response audio to S3. Presigned URL: {fileUrl}")
            return outputAudioFile, fileUrl
        else:
            raise Exception("Failed to upload synthesized speech.")

    def processWebhook(self, requestData: dict, dialogflowHandler=None, config=None, projectId=None) -> dict:
        logging.info("Received Telegram webhook event.")
        message = requestData.get("message", {})
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        if "voice" in message:
            try:
                file_id = message.get("voice", {}).get("file_id")
                logging.info(f"Processing voice message. file_id: {file_id}")
                downloadUrl = self.getFileDownloadUrl(file_id)
                if not downloadUrl:
                    raise Exception("Failed to get download URL for voice message.")
                response = requests.get(downloadUrl)
                localOggFile = "incoming_audio.ogg"
                with open(localOggFile, "wb") as f:
                    f.write(response.content)
                logging.info("Downloaded voice message file to local storage.")
                localWavFile = "incoming_audio.wav"
                if not self.convertOggToWav(localOggFile, localWavFile):
                    raise Exception("Conversion from OGG to WAV failed.")
                logging.info("Converted OGG file to WAV format.")
                s3_client = boto3.client(
                    's3',
                    aws_access_key_id=config["aws_access_key_id"],
                    aws_secret_access_key=config["aws_secret_access_key"],
                    region_name=config["aws_region"]
                )
                transcribe_client = boto3.client(
                    'transcribe',
                    aws_access_key_id=config["aws_access_key_id"],
                    aws_secret_access_key=config["aws_secret_access_key"],
                    region_name=config["aws_region"]
                )
                bucket_name = config["s3BucketName"]
                s3_key = "audio/incoming_audio.wav"
                if not self.uploadFileToS3(localWavFile, s3_key, bucket_name, s3_client):
                    raise Exception("Failed to upload WAV file to S3.")
                job_name, _ = self.startTranscriptionJob(s3_client, transcribe_client, bucket_name, s3_key)
                status = self.waitForTranscription(transcribe_client, job_name)
                transcribedText = self.getTranscribedText(status)
                if dialogflowHandler is not None and projectId:
                    logging.info("Sending transcribed text to Dialogflow for intent detection.")
                    queryResult = detectIntent(projectId, str(chat_id), transcribedText)
                    logging.info(f"Dialogflow queryResult: {json.dumps(queryResult, indent=2)}")
                    responseFromDialogflow = dialogflowHandler.processRequest({"queryResult": queryResult})
                    responseText = responseFromDialogflow.get("fulfillmentText", "")
                    if not responseText:
                        logging.warning("Dialogflow returned empty fulfillmentText. Using fallback response.")
                        responseText = "I'm sorry, I didn't understand that request."
                else:
                    responseText = "You said: " + transcribedText
                logging.info(f"Final response text to be synthesized: {responseText}")
                _, fileUrl = self.synthesizeSpeech(responseText, s3_client, bucket_name)
                send_url = f"{self.baseUrl}/sendAudio"
                data = {"chat_id": chat_id, "audio": fileUrl}
                requests.post(send_url, data=data)
                logging.info("Sent audio response to Telegram.")
                os.remove(localOggFile)
                os.remove(localWavFile)
                os.remove("response_audio.mp3")
                logging.info("Cleaned up temporary audio files.")
                return {"status": 0}
            except Exception as e:
                logging.error(f"Error processing voice message: {e}")
                return {"status": 1, "error": str(e)}
        else:
            logging.info("Processing regular text message (not a voice message).")
            return {"status": 0}
