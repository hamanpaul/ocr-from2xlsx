from __future__ import annotations

from datetime import datetime

from ocr_from2xlsx.constants import (
    OUTCOME_CODES,
    PATIENT_ENUMS,
    RESOURCE_CODES,
    REVIEW_STATUSES,
    SERVICE_CATEGORIES,
    SUPPLY_CODES,
)
from ocr_from2xlsx.domain import (
    Batch,
    OcrInfo,
    PatientFields,
    Record,
    ReviewInfo,
    Services,
    SourceBatch,
    SourceInfo,
)


NAMES = [
    "王小明",
    "李小花",
    "陳大文",
    "林小玉",
    "張阿姨",
    "黃先生",
    "周小姐",
    "吳志強",
]
IDENTITIES = ["patient", "family_caregiver", "public_other"]
GENDERS = ["female", "male", "other"]
CANCERS = ["breast_cancer", "lung_cancer", "colon_cancer", "liver_cancer", "stomach_cancer"]
NATIONALITIES = sorted(PATIENT_ENUMS["nationality"])
AGE_GROUPS = sorted(PATIENT_ENUMS["age_group"])
CHANNELS = sorted(PATIENT_ENUMS["channel"])
DISEASE_STATUSES = sorted(PATIENT_ENUMS["disease_status"])
SOURCES = sorted(PATIENT_ENUMS["source"])
REVIEW_STATUS_LIST = sorted(REVIEW_STATUSES)
CONSULTATION_CATEGORIES = sorted(SERVICE_CATEGORIES)
SUPPLY_CODE_LIST = sorted(SUPPLY_CODES)
RESOURCE_CODE_LIST = sorted(RESOURCE_CODES)
OUTCOME_CODE_LIST = sorted(OUTCOME_CODES)


class _MissingServiceDate(str):
    """Represent a missing date while keeping month slices deterministic."""

    def __new__(cls, month: str) -> "_MissingServiceDate":
        obj = super().__new__(cls, "")
        obj._month = month
        return obj

    def __getitem__(self, key: object) -> str:
        if isinstance(key, slice) and key.start == 5 and key.stop == 7:
            return self._month
        return super().__getitem__(key)


def _patient_fields(index: int) -> PatientFields:
    return PatientFields(
        nationality=NATIONALITIES[index % len(NATIONALITIES)],
        age_group=AGE_GROUPS[index % len(AGE_GROUPS)],
        channel=CHANNELS[index % len(CHANNELS)],
        disease_status=DISEASE_STATUSES[index % len(DISEASE_STATUSES)],
        source=SOURCES[index % len(SOURCES)],
        cancers=[CANCERS[index % len(CANCERS)]],
        newly_diagnosed_within_year=index % 2 == 0,
    )


def _services(index: int) -> Services:
    category = CONSULTATION_CATEGORIES[index % len(CONSULTATION_CATEGORIES)]
    codes = sorted(SERVICE_CATEGORIES[category])
    consultation = {category: [codes[index % len(codes)]]}
    supplies = [SUPPLY_CODE_LIST[index % len(SUPPLY_CODE_LIST)]] if index % 3 == 0 else []
    internal_referrals = (
        [RESOURCE_CODE_LIST[index % len(RESOURCE_CODE_LIST)]] if index % 4 == 0 else []
    )
    external_referrals = (
        [RESOURCE_CODE_LIST[(index + 1) % len(RESOURCE_CODE_LIST)]] if index % 5 == 0 else []
    )
    referral_outcomes = [OUTCOME_CODE_LIST[index % len(OUTCOME_CODE_LIST)]] if index % 6 == 0 else []
    return Services(
        consultation=consultation,
        supplies=supplies,
        internal_referrals=internal_referrals,
        external_referrals=external_referrals,
        referral_outcomes=referral_outcomes,
    )


def _record(index: int, record_id: str, service_date: str) -> Record:
    identity = IDENTITIES[index % len(IDENTITIES)]
    gender = GENDERS[index % len(GENDERS)]
    name = NAMES[index % len(NAMES)]
    medical_record_no = f"MR{index + 1:04d}"
    birthdate = f"198{index % 10}-0{(index % 9) + 1}-15" if index % 4 == 0 else None
    confidence = 0.65 if index % 10 == 0 else 0.92
    warnings = ["low_confidence"] if confidence < 0.7 else []
    return Record(
        record_id=record_id,
        service_date=service_date,
        identity=identity,
        name=name,
        medical_record_no=medical_record_no,
        gender=gender,
        source=SourceInfo(image_path=f"scan-{index + 1:04d}.jpg" if index % 5 == 0 else None),
        birthdate=birthdate,
        patient_fields=_patient_fields(index),
        services=_services(index),
        discharge_followup=None if index % 6 == 0 else index % 2 == 0,
        notes=f"Sample record {index + 1}",
        ocr=OcrInfo(confidence=confidence, raw_text=f"raw-{index + 1}", warnings=warnings),
        review=ReviewInfo(
            status=REVIEW_STATUS_LIST[index % len(REVIEW_STATUS_LIST)],
            edited_by_user=index % 7 == 0,
        ),
    )


def generate_sample_batch(count: int = 100, template_name: str = "template.xlsx") -> Batch:
    created_at = datetime.now().astimezone().isoformat(timespec="seconds")
    source_batch = SourceBatch(
        created_at=created_at,
        source_type="manual",
        template_name=template_name,
    )
    total = max(count, 0)
    missing_index = 1 if total > 1 else 0 if total else None
    records: list[Record] = []
    for index in range(total):
        month = f"{(index % 12) + 1:02d}"
        day = (index % 28) + 1
        date_value = f"2026-{month}-{day:02d}"
        service_date = _MissingServiceDate(month) if missing_index == index else date_value
        record_id = f"sample-{index + 1:04d}"
        records.append(_record(index, record_id, service_date))
    if total >= 4:
        duplicate = Record.from_dict(records[0].to_dict())
        duplicate.record_id = f"sample-{total:04d}"
        records[-1] = duplicate
    return Batch(source_batch=source_batch, records=records)
