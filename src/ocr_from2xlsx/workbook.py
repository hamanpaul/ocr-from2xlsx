from __future__ import annotations

import shutil
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from ocr_from2xlsx.constants import (
    AGE_GROUP_LABELS,
    BASIC_COLUMN_BY_FIELD,
    CANCER_LABELS,
    CHANNEL_LABELS,
    DISEASE_STATUS_LABELS,
    GENDER_LABELS,
    IDENTITY_LABELS,
    NATIONALITY_LABELS,
    SOURCE_LABELS,
    WORKBOOK_SHEET,
)
from ocr_from2xlsx.domain import Record

LABEL_BY_CODE = {
    "screening_prevention": "1.癌症篩檢與預防",
    "disease_treatment_knowledge": "2.疾病及治療知識",
    "wig_hat": "1.假髮/頭巾/毛帽用品",
    "social_welfare": "3.社福資源",
    "care_information": "9.照護資訊",
    "received_service_help": "4.獲得服務協助",
}

SUMMARY_BY_HEADER_PREFIX_AND_LABEL = {
    ("諮詢-健康與醫療系統", "1.癌症篩檢與預防"): "health_medical:screening_prevention",
    ("諮詢-健康與醫療系統", "2.疾病及治療知識"): "health_medical:disease_treatment_knowledge",
    ("提供實體用品及設備", "1.假髮/頭巾/毛帽用品"): "supplies:wig_hat",
    ("轉介或連結院內資源", "3.社福資源"): "internal:social_welfare",
    ("轉介或連結院外資源", "9.照護資訊"): "external:care_information",
    ("轉介或連結資源成果", "4.獲得服務協助"): "outcomes:received_service_help",
}

SUMMARY_PREFIX_BY_HEADER_PREFIX = {
    "諮詢-健康與醫療系統": "health_medical",
    "提供實體用品及設備": "supplies",
    "轉介或連結院內資源": "internal",
    "轉介或連結院外資源": "external",
    "轉介或連結資源成果": "outcomes",
}


def _normalize_duplicate_value(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_service_date(value: object) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return _normalize_duplicate_value(value)


class WorkbookWriter:
    def __init__(self, working_path: Path | str) -> None:
        self.working_path = Path(working_path)
        suffix = self.working_path.suffix.lower()
        if suffix in {".xlsm", ".xltm"}:
            self.workbook = load_workbook(self.working_path, keep_vba=True)
        else:
            self.workbook = load_workbook(self.working_path)
        if WORKBOOK_SHEET not in self.workbook.sheetnames:
            raise ValueError(f"Missing sheet: {WORKBOOK_SHEET}")
        self.sheet = self.workbook[WORKBOOK_SHEET]
        self.header_map = self._build_header_map(self.sheet)

    @classmethod
    def create_from_template(cls, template_path: Path | str, working_path: Path | str) -> "WorkbookWriter":
        template_path = Path(template_path)
        working_path = Path(working_path)
        working_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template_path, working_path)
        return cls(working_path)

    def write_record(self, record: Record) -> int:
        row = self._next_empty_row()
        self._set(row, BASIC_COLUMN_BY_FIELD["service_month"], record.service_month_label())
        self._set(row, BASIC_COLUMN_BY_FIELD["service_date"], record.service_date)
        self._set(row, BASIC_COLUMN_BY_FIELD["identity"], IDENTITY_LABELS[record.identity])
        self._set(row, BASIC_COLUMN_BY_FIELD["name"], record.name)
        self._set(row, BASIC_COLUMN_BY_FIELD["medical_record_no"], record.medical_record_no)
        self._set(row, BASIC_COLUMN_BY_FIELD["gender"], GENDER_LABELS[record.gender])

        if record.identity == "patient":
            fields = record.patient_fields
            self._set(row, BASIC_COLUMN_BY_FIELD["nationality"], NATIONALITY_LABELS.get(fields.nationality or ""))
            self._set(row, BASIC_COLUMN_BY_FIELD["age_group"], AGE_GROUP_LABELS.get(fields.age_group or ""))
            self._set(row, BASIC_COLUMN_BY_FIELD["channel"], CHANNEL_LABELS.get(fields.channel or ""))
            self._set(row, BASIC_COLUMN_BY_FIELD["disease_status"], DISEASE_STATUS_LABELS.get(fields.disease_status or ""))
            self._set(row, BASIC_COLUMN_BY_FIELD["source"], SOURCE_LABELS.get(fields.source or ""))
            newly_diagnosed = None
            if fields.newly_diagnosed_within_year is True:
                newly_diagnosed = "是"
            elif fields.newly_diagnosed_within_year is False:
                newly_diagnosed = "否"
            self._set(row, BASIC_COLUMN_BY_FIELD["newly_diagnosed_within_year"], newly_diagnosed)
            for index, cancer in enumerate(fields.cancers[:3], start=1):
                self._set(row, f"癌別{index}\n(病人才填)", CANCER_LABELS.get(cancer, cancer))

        discharge_followup = None
        if record.discharge_followup is True:
            discharge_followup = "是"
        elif record.discharge_followup is False:
            discharge_followup = "否"
        self._set(row, BASIC_COLUMN_BY_FIELD["discharge_followup"], discharge_followup)

        self._write_services(row, record)
        return row

    def save(self) -> None:
        self.workbook.calculation.fullCalcOnLoad = True
        self.workbook.calculation.forceFullCalc = True
        self.workbook.save(self.working_path)

    def existing_duplicate_keys(self) -> set[tuple[str, str, str, str]]:
        keys: set[tuple[str, str, str, str]] = set()
        service_date_col = self.header_map.get(BASIC_COLUMN_BY_FIELD["service_date"])
        name_col = self.header_map.get(BASIC_COLUMN_BY_FIELD["name"])
        id_col = self.header_map.get(BASIC_COLUMN_BY_FIELD["medical_record_no"])
        if not service_date_col or not name_col or not id_col:
            return keys
        for row in range(2, self.sheet.max_row + 1):
            service_date = _normalize_service_date(self.sheet.cell(row=row, column=service_date_col).value)
            name = _normalize_duplicate_value(self.sheet.cell(row=row, column=name_col).value)
            medical_id = _normalize_duplicate_value(self.sheet.cell(row=row, column=id_col).value)
            if not service_date or not name or not medical_id:
                continue
            keys.add((service_date, name, medical_id, self._service_summary_from_row(row)))
        return keys

    def _write_services(self, row: int, record: Record) -> None:
        for category, codes in record.services.consultation.items():
            prefix = _consultation_prefix(category)
            for index, code in enumerate(codes, start=1):
                self._set_if_present(row, f"{prefix}{index}", LABEL_BY_CODE.get(code, code))
        for index, code in enumerate(record.services.supplies, start=1):
            self._set_if_present(row, f"提供實體用品及設備{index}", LABEL_BY_CODE.get(code, code))
        for index, code in enumerate(record.services.internal_referrals, start=1):
            self._set_if_present(row, f"轉介或連結院內資源{index}", LABEL_BY_CODE.get(code, code))
        for index, code in enumerate(record.services.external_referrals, start=1):
            self._set_if_present(row, f"轉介或連結院外資源{index}", LABEL_BY_CODE.get(code, code))
        for index, code in enumerate(record.services.referral_outcomes, start=1):
            self._set_if_present(row, f"轉介或連結資源成果{index}", LABEL_BY_CODE.get(code, code))

    def _service_summary_from_row(self, row: int) -> str:
        parts: list[str] = []
        for header, column in self.header_map.items():
            value = self.sheet.cell(row=row, column=column).value
            if value in (None, ""):
                continue
            value_str = str(value)
            summary_part = None
            for (prefix, label), candidate in SUMMARY_BY_HEADER_PREFIX_AND_LABEL.items():
                if header.startswith(prefix) and value_str == label:
                    summary_part = candidate
                    break
            if summary_part:
                parts.append(summary_part)
                continue
            for prefix, summary_prefix in SUMMARY_PREFIX_BY_HEADER_PREFIX.items():
                if header.startswith(prefix):
                    parts.append(f"{summary_prefix}:{value_str}")
                    break
        return "|".join(sorted(parts))

    def _build_header_map(self, sheet: Worksheet) -> dict[str, int]:
        header_map: dict[str, int] = {}
        for cell in sheet[1]:
            if cell.value:
                header_map[str(cell.value)] = cell.column
        required_headers = list(BASIC_COLUMN_BY_FIELD.values()) + [
            "癌別1\n(病人才填)",
            "癌別2\n(病人才填)",
            "癌別3\n(病人才填)",
        ]
        missing = [header for header in required_headers if header not in header_map]
        if missing:
            raise ValueError(f"Missing required headers: {', '.join(missing)}")
        return header_map

    def _next_empty_row(self) -> int:
        name_col = self.header_map[BASIC_COLUMN_BY_FIELD["name"]]
        for row in range(2, self.sheet.max_row + 2):
            if self.sheet.cell(row=row, column=name_col).value in (None, ""):
                return row
        return self.sheet.max_row + 1

    def _set(self, row: int, header: str, value: object) -> None:
        column = self.header_map[header]
        self.sheet.cell(row=row, column=column, value=value)

    def _set_if_present(self, row: int, header: str, value: object) -> None:
        column = self.header_map.get(header)
        if column:
            self.sheet.cell(row=row, column=column, value=value)


def _consultation_prefix(category: str) -> str:
    return {
        "health_medical": "諮詢-健康與醫療系統",
        "symptom_side_effect": "諮詢-症狀與副作用照護",
        "nutrition_diet": "諮詢-營養與飲食",
        "psychosocial_emotion": "諮詢-社會心理情緒",
        "financial_social": "諮詢-經濟與社會資源",
        "care_support": "諮詢-照顧與支持",
    }[category]
