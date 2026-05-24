from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from ocr_from2xlsx.constants import SCHEMA_VERSION


def _none_if_empty(value: Any) -> Any:
    return None if value == "" else value


@dataclass(slots=True)
class SourceInfo:
    image_path: str | None = None
    capture_time: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SourceInfo":
        data = data or {}
        return cls(image_path=_none_if_empty(data.get("image_path")), capture_time=_none_if_empty(data.get("capture_time")))


@dataclass(slots=True)
class PatientFields:
    nationality: str | None = None
    age_group: str | None = None
    channel: str | None = None
    disease_status: str | None = None
    source: str | None = None
    cancers: list[str] = field(default_factory=list)
    newly_diagnosed_within_year: bool | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PatientFields":
        data = data or {}
        return cls(
            nationality=_none_if_empty(data.get("nationality")),
            age_group=_none_if_empty(data.get("age_group")),
            channel=_none_if_empty(data.get("channel")),
            disease_status=_none_if_empty(data.get("disease_status")),
            source=_none_if_empty(data.get("source")),
            cancers=list(data.get("cancers") or []),
            newly_diagnosed_within_year=data.get("newly_diagnosed_within_year"),
        )


@dataclass(slots=True)
class Services:
    consultation: dict[str, list[str]] = field(default_factory=dict)
    supplies: list[str] = field(default_factory=list)
    internal_referrals: list[str] = field(default_factory=list)
    external_referrals: list[str] = field(default_factory=list)
    referral_outcomes: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Services":
        data = data or {}
        consultation = {
            str(category): list(values or [])
            for category, values in (data.get("consultation") or {}).items()
        }
        return cls(
            consultation=consultation,
            supplies=list(data.get("supplies") or []),
            internal_referrals=list(data.get("internal_referrals") or []),
            external_referrals=list(data.get("external_referrals") or []),
            referral_outcomes=list(data.get("referral_outcomes") or []),
        )

    def summary(self) -> str:
        parts: list[str] = []
        for category in sorted(self.consultation):
            for code in sorted(self.consultation[category]):
                parts.append(f"{category}:{code}")
        for name, values in [
            ("supplies", self.supplies),
            ("internal", self.internal_referrals),
            ("external", self.external_referrals),
            ("outcomes", self.referral_outcomes),
        ]:
            for code in sorted(values):
                parts.append(f"{name}:{code}")
        return "|".join(parts)


@dataclass(slots=True)
class OcrInfo:
    confidence: float | None = None
    raw_text: str = ""
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "OcrInfo":
        data = data or {}
        return cls(
            confidence=data.get("confidence"),
            raw_text=str(data.get("raw_text") or ""),
            warnings=list(data.get("warnings") or []),
        )


@dataclass(slots=True)
class ReviewInfo:
    status: str = "pending"
    edited_by_user: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ReviewInfo":
        data = data or {}
        return cls(status=str(data.get("status") or "pending"), edited_by_user=bool(data.get("edited_by_user", False)))


@dataclass(slots=True)
class Record:
    record_id: str
    service_date: str
    identity: str
    name: str
    medical_record_no: str
    gender: str
    source: SourceInfo = field(default_factory=SourceInfo)
    birthdate: str | None = None
    patient_fields: PatientFields = field(default_factory=PatientFields)
    services: Services = field(default_factory=Services)
    discharge_followup: bool | None = None
    notes: str = ""
    ocr: OcrInfo = field(default_factory=OcrInfo)
    review: ReviewInfo = field(default_factory=ReviewInfo)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Record":
        return cls(
            record_id=str(data["record_id"]),
            source=SourceInfo.from_dict(data.get("source")),
            service_date=str(data.get("service_date") or ""),
            identity=str(data.get("identity") or ""),
            name=str(data.get("name") or ""),
            medical_record_no=str(data.get("medical_record_no") or ""),
            birthdate=_none_if_empty(data.get("birthdate")),
            gender=str(data.get("gender") or ""),
            patient_fields=PatientFields.from_dict(data.get("patient_fields")),
            services=Services.from_dict(data.get("services")),
            discharge_followup=data.get("discharge_followup"),
            notes=str(data.get("notes") or ""),
            ocr=OcrInfo.from_dict(data.get("ocr")),
            review=ReviewInfo.from_dict(data.get("review")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def service_month_label(self) -> str:
        parsed = date.fromisoformat(self.service_date)
        return f"{parsed.month}月"

    def duplicate_key(self) -> tuple[str, str, str, str]:
        return (self.service_date, self.name.strip(), self.medical_record_no.strip(), self.services.summary())


@dataclass(slots=True)
class SourceBatch:
    created_at: str
    source_type: str
    template_name: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceBatch":
        return cls(
            created_at=str(data.get("created_at") or ""),
            source_type=str(data.get("source_type") or ""),
            template_name=str(data.get("template_name") or ""),
        )


@dataclass(slots=True)
class Batch:
    source_batch: SourceBatch
    records: list[Record]
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Batch":
        return cls(
            schema_version=str(data.get("schema_version") or ""),
            source_batch=SourceBatch.from_dict(data.get("source_batch") or {}),
            records=[Record.from_dict(item) for item in data.get("records") or []],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
