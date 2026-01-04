import logging
from typing import Any, BinaryIO

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from fastapi.concurrency import run_in_threadpool
from ingest_worker.config import settings

logger = logging.getLogger(__name__)


class BlobStorageService:
	"""
	Adapter for Object Storage (S3 / MinIO).
	Abstracts boto3 interactions and handles async offloading.
	"""

	def __init__(self):
		self._client = None
		self.bucket_name = settings.S3_BUCKET_NAME
		self.region = settings.S3_REGION

	def initialize(self):
		"""
		Initializes the Boto3 client.
		Detects if we are running locally (MinIO) or in Cloud (AWS) based on S3_ENDPOINT_URL.
		"""
		try:
			# Common config
			config: dict[str, Any] = {
				'service_name': 's3',
				'region_name': self.region,
			}

			# If an endpoint URL is provided (e.g. http://minio:9000), use it.
			# This is the switch between Real AWS and Local MinIO.
			if settings.S3_ENDPOINT_URL:
				logger.info(f'Initializing Object Storage with Custom Endpoint: {settings.S3_ENDPOINT_URL}')
				config['endpoint_url'] = settings.S3_ENDPOINT_URL

				# For MinIO, we usually need signature version v4 explicitly
				from botocore.client import Config

				config['config'] = Config(signature_version='s3v4')

			self._client = boto3.client(**config)

			# Lightweight check to ensure connectivity
			# We don't create the bucket here (handled by Infra/Terraform/Docker), just check it.
			try:
				self._client.head_bucket(Bucket=self.bucket_name)
				logger.info(f"Connected to object storage. Bucket '{self.bucket_name}' exists.")
			except ClientError as e:
				error_code = int(e.response['Error']['Code'])
				if error_code == 404:
					logger.warning(
						f"Bucket '{self.bucket_name}' does not exist. Ensure infrastructure provisioning ran."
					)
				elif error_code == 403:
					logger.error(f"Access denied to bucket '{self.bucket_name}'. Check credentials.")
				else:
					raise

		except NoCredentialsError:
			logger.critical('No AWS credentials found. Ensure AWS_ACCESS_KEY_ID/SECRET are set.')
			raise
		except Exception as e:
			logger.critical(f'Failed to initialize BlobStorageService: {e}')
			raise

	async def upload_stream(self, file_obj: BinaryIO, key: str, content_type: str = 'application/pdf') -> str:
		"""
		Uploads a file stream to S3.
		Returns the constructed S3 URI.
		"""
		if not self._client:
			raise RuntimeError('BlobStorageService not initialized.')

		logger.info(f'Uploading stream to s3://{self.bucket_name}/{key}')

		try:
			# Run blocking I/O in a threadpool to avoid freezing the async event loop
			await run_in_threadpool(
				self._client.upload_fileobj,
				Fileobj=file_obj,
				Bucket=self.bucket_name,
				Key=key,
				ExtraArgs={'ContentType': content_type},
			)
			return self.generate_uri(key)
		except ClientError as e:
			logger.error(f'S3 Upload Failed for {key}: {e}')
			raise

	async def download_file(self, key: str, destination_path: str):
		"""
		Downloads an object from S3 to a local file path.
		"""
		if not self._client:
			raise RuntimeError('BlobStorageService not initialized.')

		logger.info(f'Downloading s3://{self.bucket_name}/{key} to {destination_path}')

		try:
			await run_in_threadpool(
				self._client.download_file, Bucket=self.bucket_name, Key=key, Filename=destination_path
			)
		except ClientError as e:
			logger.error(f'S3 Download Failed for {key}: {e}')
			raise

	def generate_uri(self, key: str) -> str:
		"""
		Returns the S3 URI string.
		"""
		return f's3://{self.bucket_name}/{key}'

	def close(self):
		"""
		Boto3 clients are thread-safe and generally don't need explicit closing,
		but we keep the interface consistent with other services.
		"""
		pass


# Singleton instance
blob_storage = BlobStorageService()
