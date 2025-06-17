import boto3
import os
import logging

class S3Uploader:
    @staticmethod
    def uploadFileToS3(filePath: str, bucketName: str, objectName: str = None) -> str:
        # Uploads the file to S3 and returns a pre-signed URL valid for 1 hour.
        if objectName is None:
            objectName = os.path.basename(filePath)
        try:
            s3Client = boto3.client('s3', region_name="eu-north-1")
            s3Client.upload_file(filePath, bucketName, objectName)
            url = s3Client.generate_presigned_url('get_object',
                                                   Params={'Bucket': bucketName, 'Key': objectName},
                                                   ExpiresIn=3600)
            return url
        except Exception as e:
            logging.error(f"Exception in uploadFileToS3: {e}")
            return ""
