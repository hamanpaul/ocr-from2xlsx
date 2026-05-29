"""Fake OCR plugin for tests: echoes a deterministic record from the request."""
from __future__ import annotations

import json
import sys


def main() -> int:
    request = json.loads(sys.stdin.read())
    page = request.get("page", {})
    response = {
        "contract_version": request.get("contract_version"),
        "record": {
            "record_id": f"plugin-{page.get('page_number', 0):04d}",
            "service_date": "2026-05-26",
            "identity": "patient",
            "name": "Plugin Echo",
            "medical_record_no": "PLUGIN-OK",
            "gender": "female",
            "patient_fields": {
                "nationality": "local",
                "age_group": "51_60",
                "channel": "internal_referral",
                "disease_status": "treating",
                "source": "outpatient",
                "cancers": ["breast_cancer"],
                "newly_diagnosed_within_year": False,
            },
            "services": {"consultation": {"health_medical": ["screening_prevention"]}},
            "ocr": {"confidence": 0.91, "raw_text": page.get("image_path", "")},
        },
    }
    sys.stdout.write(json.dumps(response, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
