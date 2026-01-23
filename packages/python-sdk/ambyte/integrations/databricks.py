"""
Databricks Integration for Ambyte SDK.

This module provides auto-configuration capabilities for running the SDK
inside Databricks Notebooks and Jobs. It automatically detects the
current user, cluster context, and job ID to populate Ambyte ContextVars.
"""

import logging
import os
from typing import Any

from ambyte.context import AmbyteContext
from ambyte_schemas.models.common import Actor, ActorType

logger = logging.getLogger('ambyte.integrations.databricks')

# Global reference to hold the context manager to prevent garbage collection
# and allow manual cleanup if necessary.
_ACTIVE_DATABRICKS_CONTEXT: AmbyteContext | None = None


def _get_spark_session() -> Any:
	"""
	Attempts to retrieve the active SparkSession.
	Returns None if pyspark is not installed or no session is active.
	"""
	try:
		from pyspark.sql import SparkSession

		return SparkSession.getActiveSession()
	except ImportError:
		return None


def _get_dbutils(spark: Any) -> Any:
	"""
	Attempts to retrieve the DBUtils object.
	Supports both standard Databricks runtime and Connect.
	"""
	try:
		from pyspark.dbutils import DBUtils  # type: ignore

		return DBUtils(spark)
	except ImportError:
		return None


def _extract_notebook_tags(dbutils: Any) -> dict[str, str]:
	"""
	Uses reflection to extract context tags from the notebook entry point.
	This provides rich metadata like Notebook ID, Job ID, and Cluster ID.
	"""
	tags = {}
	try:
		# Standard reflection pattern for Databricks notebooks
		ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
		raw_tags = ctx.tags()

		# Java map to Python dict
		iterator = raw_tags.entrySet().iterator()
		while iterator.hasNext():
			entry = iterator.next()
			tags[str(entry.getKey())] = str(entry.getValue())

	except Exception as e:
		logger.debug(f'Could not extract notebook tags via dbutils: {e}')

	return tags


def databricks_init(project_id: str | None = None):
	"""
	Auto-initializes the Ambyte SDK for the current Databricks environment.

	This function:
	1. Detects the Spark Session.
	2. Identifies the current user (email).
	3. Extracts Job/Run IDs for lineage.
	4. Sets the global Ambyte Context (Actor & Run ID).

	Usage:
	    import ambyte
	    ambyte.databricks_init()

	    # Now checks are attributed to the notebook user
	    @ambyte.guard(...)
	    def my_func(): ...
	"""  # noqa: E101
	global _ACTIVE_DATABRICKS_CONTEXT

	# 1. Environment Check
	if 'DATABRICKS_RUNTIME_VERSION' not in os.environ:
		logger.warning('databricks_init called, but DATABRICKS_RUNTIME_VERSION not detected.')

	spark = _get_spark_session()
	if not spark:
		logger.error('Active SparkSession not found. Cannot initialize Databricks integration.')
		return

	# 2. Extract Identity (Actor)
	# Spark SQL is the most reliable way to get the effective user in UC clusters
	try:
		current_user_email = spark.sql('SELECT current_user()').collect()[0][0]
	except Exception as e:
		logger.error(f'Failed to determine current user via Spark: {e}')
		current_user_email = 'unknown-databricks-user'

	# 3. Extract Metadata (Tags)
	attributes = {
		'platform': 'databricks',
		'runtime_version': os.environ.get('DATABRICKS_RUNTIME_VERSION', 'unknown'),
	}

	run_id: str | None = None

	dbutils = _get_dbutils(spark)
	if dbutils:
		tags = _extract_notebook_tags(dbutils)

		# Map useful tags to attributes
		if 'clusterId' in tags:
			attributes['cluster_id'] = tags['clusterId']
		if 'notebookId' in tags:
			attributes['notebook_id'] = tags['notebookId']
		if 'browserHostName' in tags:
			attributes['host'] = tags['browserHostName']

		# Determine Run ID
		# Priority: Job Run ID > Notebook ID > None (Auto-generate)
		if 'jobId' in tags and 'runId' in tags:
			attributes['job_id'] = tags['jobId']
			run_id = f'job_{tags["jobId"]}_run_{tags["runId"]}'
		elif 'notebookId' in tags:
			# Persistent context for a notebook session
			run_id = f'notebook_session_{tags["notebookId"]}'

	# 4. Determine Actor Type
	# Service Principals usually look like UUIDs, Humans look like emails
	actor_type = ActorType.HUMAN
	if '@' not in current_user_email and '-' in current_user_email:
		# Heuristic for Service Principal App ID
		actor_type = ActorType.SERVICE_ACCOUNT

	actor = Actor(
		id=current_user_email,
		type=actor_type,
		roles=[],  # Roles are handled by the PDP via the Control Plane, not locally
		attributes=attributes,
	)

	# 5. Initialize Context
	# We purposefully enter the context without exiting to maintain state
	# for the duration of the notebook session.

	# Clean up previous context if re-initialized
	if _ACTIVE_DATABRICKS_CONTEXT:
		# This resets ContextVars to previous state (likely empty)
		# Note: We pass None, None, None as we don't have exc info
		_ACTIVE_DATABRICKS_CONTEXT.__exit__(None, None, None)

	logger.info(f'Initializing Ambyte Context for: {actor.id}')
	if run_id:
		logger.info(f'Context Run ID: {run_id}')

	# Create and enter new context
	_ACTIVE_DATABRICKS_CONTEXT = AmbyteContext(
		actor=actor, run_id=run_id, extras={'project_id': project_id} if project_id else None
	)
	_ACTIVE_DATABRICKS_CONTEXT.__enter__()

	logger.info('✅ Ambyte Databricks integration active.')
