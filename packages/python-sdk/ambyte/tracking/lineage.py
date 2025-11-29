import uuid
from datetime import datetime, timezone
from types import TracebackType
from typing import Optional, Type

from ambyte.context import AmbyteContext
from ambyte.tracking.manager import get_tracker
from ambyte_schemas.models.common import Actor
from ambyte_schemas.models.lineage import RunType


class LineageTracer:
	"""
	Context Manager to trace the execution of a data process.
	"""

	def __init__(
		self,
		name: str,
		run_type: RunType = RunType.ETL_TRANSFORM,
		inputs: Optional[list[str]] = None,
		outputs: Optional[list[str]] = None,
		actor: Optional[Actor] = None,
	):
		self.run_id = str(uuid.uuid4())
		self.name = name
		self.run_type = run_type
		self.inputs = inputs or []
		self.outputs = outputs or []
		self.actor = actor

		self.tracker = get_tracker()
		self.start_time: Optional[datetime] = None

		# Determine Context
		# We need to set the global run_id so nested checks are attributed to us
		self._ctx_manager = AmbyteContext(actor=self.actor, run_id=self.run_id)

	def __enter__(self):
		# 1. Enter ContextVars Scope
		self._ctx_manager.__enter__()

		# 2. Start Timer
		self.start_time = datetime.now(timezone.utc)

		# 3. Emit "Run Started" Signal
		payload = {
			'id': self.run_id,
			'type': self.run_type,
			'start_time': self.start_time.isoformat(),
			# We don't know success yet
		}
		self.tracker.enqueue('lineage_run', payload)

		return self

	def __exit__(
		self,
		exc_type: Optional[Type[BaseException]],
		exc_value: Optional[BaseException],
		traceback: Optional[TracebackType],
	) -> None:
		end_time = datetime.now(timezone.utc)
		is_success = exc_type is None

		# 4. Emit "Run Finished" Signal
		run_payload = {'id': self.run_id, 'end_time': end_time.isoformat(), 'success': is_success}
		self.tracker.enqueue('lineage_run', run_payload)

		# 5. Emit the actual Lineage Edge (Inputs -> Outputs)
		# Only emit if the job actually did something (or even if it failed, to track intent)
		if self.inputs or self.outputs:
			event_payload = {'run_id': self.run_id, 'input_urns': self.inputs, 'output_urns': self.outputs}
			self.tracker.enqueue('lineage_event', event_payload)

		# 6. Exit ContextVars Scope
		self._ctx_manager.__exit__(exc_type, exc_value, traceback)


# DX Helper
def trace(
	name: str = 'script_execution', inputs: Optional[list[str]] = None, outputs: Optional[list[str]] = None
) -> LineageTracer:
	"""
	Wraps a block of code to track data lineage.

	Usage:
	with ambyte.lineage.trace(
	        inputs=["urn:s3:raw"],
	        outputs=["urn:snowflake:clean"]
	    ):
	        df = read_s3(...)
	        df.write_snowflake(...)
	"""  # noqa: E101
	return LineageTracer(name=name, inputs=inputs, outputs=outputs)
