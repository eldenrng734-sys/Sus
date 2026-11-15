# AI evaluation dataset

`ai_evaluation.jsonl` contains 50 human-labeled examples. Each line is a JSON object with `id`, `language` (`en` or `bn`), `message`, and `expected`. The expected labels are `category`, `intent`, `buying_stage`, `sentiment`, and `recommended_action`, using the allowed values in `app/modules/ai/service.py`. `category` stays `unknown` unless the message establishes the customer type.

Load the dataset in Python without extra dependencies:

```python
import json
from pathlib import Path

path = Path("backend/tests/fixtures/ai_evaluation.jsonl")
records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
```

Dev 3's runner can use `record["message"]` as the input and compare its output fields with `record["expected"]`. The fixture field names intentionally match `AssessmentOutput`; no production runner is included here.
