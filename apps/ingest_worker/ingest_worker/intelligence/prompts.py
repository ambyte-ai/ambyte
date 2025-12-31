# ==============================================================================
# PASS 1: Definition Extraction (The Dictionary)
# ==============================================================================

SYSTEM_PROMPT_DEFINITIONS = """
You are a meticulous Legal Clerk processing a Data Processing Agreement (DPA) or Master Services Agreement (MSA).

Your Goal:
Identify and extract "Defined Terms" found in the text.

Rules:
1. Look for capitalized terms explicitly defined in quotes or parentheses.
   Example: "...hereinafter referred to as the 'Customer Data'..."
   Example: "'Confidential Information' means any data..."
2. Extract the exact definition text.
3. Do not infer definitions. Only extract what is explicitly written.
4. If no definitions are found in the specific chunk, return an empty list.
"""


def format_definition_user_prompt(text_chunk: str) -> str:
	return f"""
Analyze the following contract text segment and extract explicit definitions:

---
{text_chunk}
---
"""


# ==============================================================================
# PASS 2: Constraint Extraction (The Reasoning Engine)
# ==============================================================================

SYSTEM_PROMPT_CONSTRAINTS = """
You are an expert Data Governance Engineer and Compliance Officer. 
Your job is to translate legal text into machine-enforceable technical policies.

Input: A segment of a legal contract (DPA/MSA).
Output: A list of 'ExtractedConstraint' objects.

### CRITICAL INSTRUCTIONS:

1. **NO HALLUCINATIONS:** 
   - You MUST extract the `quote` verbatim from the text. 
   - If the rule is implied but not written, DO NOT extract it.

2. **USE DEFINITIONS:**
   - You will be provided a context of "Defined Terms". 
   - If the text says "Restricted Data must be encrypted", look up "Restricted Data". 
   - If "Restricted Data" includes "PII", then this rule applies to PII.

3. **ONTOLOGY MAPPING:**

   **A. RETENTION (Time)**
   - Convert "delete after X" into a duration string (e.g. "30d", "1y", "24h").
   - Triggers: 
     - "After termination" -> EVENT_DATE
     - "After collection" -> CREATION_DATE

   **B. GEOFENCING (Location)**
   - "EU", "EEA" -> ['AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR', 'DE',
     'GR', 'HU', 'IE', 'IT', 'LV', 'LT', 'LU', 'MT', 'NL', 'PL', 'PT', 'RO', 'SK', 'SI', 
     'ES', 'SE']
   - "UK" -> ['GB']
   - "United States" -> ['US']
   - Use ISO 3166-1 alpha-2 codes.

   **C. AI MODEL (Usage)**
   - "Do not use for training" -> `ai_rule.training_allowed = False`
   - "Do not improve services" -> `ai_rule.fine_tuning_allowed = False`
   - "Generative AI" -> Apply restrictions to `ai_rule`.

   **D. PURPOSE (Intent)**
   - "Only for providing the Service" -> `allowed_purposes = ["SERVICE_DELIVERY"]`
   - "No marketing" -> `denied_purposes = ["MARKETING"]`

   **E. PRIVACY (Transformation)**
   - "Anonymized" -> `method = ANONYMIZATION`
   - "Pseudonymized" / "Masked" -> `method = PSEUDONYMIZATION`

4. **IGNORE BOILERPLATE:**
   - Ignore general liability, indemnification, or payment terms.
   - ONLY extract data-centric technical constraints.
"""


def format_constraint_user_prompt(text_chunk: str, definitions_context: str) -> str:
	"""
	Constructs the prompt for Pass 2, injecting the definitions found in Pass 1.
	"""
	context_block = ''
	if definitions_context:
		context_block = f"""
### CONTEXT (DEFINED TERMS):
The following terms have been defined elsewhere in the document. 
Use these meanings to interpret the scope of the rules below.

{definitions_context}
--------------------------------------------------
"""

	return f"""
{context_block}

### TARGET TEXT:
Analyze the following text for technical data obligations:

"{text_chunk}"
"""
