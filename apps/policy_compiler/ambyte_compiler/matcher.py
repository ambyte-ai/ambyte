import fnmatch

from ambyte_schemas.models.obligation import Obligation


class ResourceMatcher:
	"""
	Logic engine to determine if a specific Resource falls within the scope
	of an Obligation based on its ResourceSelector (URN patterns and Tags).
	"""

	def matches(self, resource_urn: str, resource_tags: dict[str, str], obligation: Obligation) -> bool:
		"""
		Evaluates whether the obligation applies to the given resource.

		Logic Flow:
		1. Empty Selector -> Returns False (Safety: No implicit global scope).
		2. Exclude Patterns -> If match, return False immediately.
		3. Tag Matching -> Resource must contain ALL tags defined in the selector.
		4. Include Patterns -> If defined, resource URN must match at least one.
		                    -> If NOT defined, but Tags matched, return True.

		Args:
		    resource_urn: The Unique Resource Name (e.g., 'urn:snowflake:sales:cust').
		    resource_tags: Key-value metadata attached to the resource.
		    obligation: The policy rule containing the target selector.

		Returns:
		    True if the obligation applies, False otherwise.
		"""  # noqa: E101
		selector = obligation.target

		# 1. Safety Check: Empty selector implies "Target Nothing" (or misconfiguration).
		# We do not assume global scope to prevent accidental policy leakage.
		if not selector.include_patterns and not selector.match_tags:
			return False

		# 2. Check Exclusions (Fast Fail)
		# If the URN matches any exclude pattern, we drop it immediately.
		for pattern in selector.exclude_patterns:
			if fnmatch.fnmatch(resource_urn, pattern):
				return False

		# 3. Check Tag Matching (AND Logic)
		# The resource must possess ALL tags defined in the selector.
		# Extra tags on the resource are fine.
		if selector.match_tags:
			for key, required_val in selector.match_tags.items():
				# Normalize values to string for comparison
				actual_val = str(resource_tags.get(key, ''))
				if actual_val != str(required_val):
					return False

		# 4. Check Inclusions (OR Logic for patterns)
		# Case A: No patterns defined, but we passed the Tag check above.
		if not selector.include_patterns:
			# If we had tags and they matched, it's a match.
			# If we had no tags (and no patterns), we hit step 1 already.
			return True

		# Case B: Patterns defined. We must match at least one.
		for pattern in selector.include_patterns:
			if fnmatch.fnmatch(resource_urn, pattern):
				return True

		# Case C: Patterns defined, but none matched.
		return False
