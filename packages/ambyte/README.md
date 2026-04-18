# Ambyte

**Policy as Code for Data & AI.**

Turn legal obligations into machine-enforceable data policies. Ambyte reads your contracts, extracts constraints using AI, resolves conflicts, and compiles them into executable policies for Snowflake, Databricks, AWS IAM, and Python applications.

## Installation

```bash
pip install ambyte
```

## Quick Start

```python
import ambyte
from ambyte import guard, trace

ambyte.init()

@guard(resource="urn:snowflake:prod:sales_data", action="read", context={"purpose": "marketing"})
def fetch_sales_data():
    return db.query("SELECT * FROM sales_data")
```

## Optional Extras

```bash
# Databricks Unity Catalog connector
pip install ambyte[databricks]
```

For full documentation and architecture details, visit the [GitHub repository](https://github.com/ambyte-ai/ambyte).
