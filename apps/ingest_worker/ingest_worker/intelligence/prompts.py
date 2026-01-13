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

3. **REGULATORY KNOWLEDGE GRAPH (HIGHEST PRIORITY):**
   - You may be provided with "MATCHED REGULATION" context blocks.
   - **IF** the input text refers to the specific regulation concept described in the context 
      (e.g., GDPR Art 17 "Right to Erasure"), **THEN** you must use the `REQUIRED TECHNICAL CONFIGURATION` 
      provided in that context.
   - Copy the values (e.g., `trigger`, `enforcement_level`, `method`) exactly from the context into your output object.
   - Do not invent your own parameters if a canonical mapping is provided.

4. **ONTOLOGY MAPPING (Fallback):**
   If no specific regulatory match is found, apply these general heuristics:

   **A. RETENTION (Time)**
   - Convert "delete after X" into a duration string (e.g. "30d", "1y", "24h").
   - Triggers: 
     - "After termination" -> EVENT_DATE
     - "After collection" -> CREATION_DATE
   - If the text says "retain as long as necessary" or "duration of services" WITHOUT a specific time limit:
   - Set duration to "3y" (Standard Default).
   - OR set `allow_legal_hold_override = True`.
   - DO NOT set duration to "0s".

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

5. **SCOPING (Subject Standardization):**
   - When filling the `subject` field, map the legal term to a standard technical category if possible.
   - GOOD: "Personal Data", "Usage Logs", "Financial Records"
   - BAD: "Personal Data originating from the European Economic Area (EEA)"
   - BAD: "Data provided by the Customer for the purpose of the Services"
   - Keep `subject` under 5 words.

6. **IGNORE BOILERPLATE:**
   - Ignore general liability, indemnification, or payment terms.
   - ONLY extract data-centric technical constraints.
"""


def format_constraint_user_prompt(text_chunk: str, definitions_context: str, regulatory_context: str = '') -> str:
	"""
	Constructs the prompt for Pass 2, injecting:
	1. Definitions found in Pass 1.
	2. Canonical Regulatory Rules found via Vector Search.
	"""
	def_block = ''
	if definitions_context:
		def_block = f"""
### CONTEXT (DEFINED TERMS):
The following terms have been defined elsewhere in the document. 
Use these meanings to interpret the scope of the rules below.

{definitions_context}
--------------------------------------------------
"""

	reg_block = ''
	if regulatory_context:
		reg_block = f"""
### CONTEXT (REGULATORY KNOWLEDGE GRAPH):
The following canonical regulations match the semantic content of the input text.
If the text is discussing these specific articles, APPLY THE TECHNICAL CONFIGURATION BELOW EXACTLY.

{regulatory_context}
--------------------------------------------------
"""

	return f"""
{def_block}
{reg_block}

### TARGET TEXT:
Analyze the following text for technical data obligations:

"{text_chunk}"
"""
