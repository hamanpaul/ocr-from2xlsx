"""Render-agnostic model for form-layout templates.

This module defines a shared data model for form layouts that is independent
of any specific rendering format (e.g., Excel). It provides a hierarchical
structure of sections, fields, and options that can be used to represent
form templates and their metadata.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Iterator, Literal

Kind = Literal["text", "single_choice", "multi_choice"]


@dataclass(frozen=True, slots=True)
class Option:
    label: str
    code: str
    cell: str


@dataclass(frozen=True, slots=True)
class Field:
    key: str
    title: str
    kind: Kind
    record_path: str | None
    anchor_cell: str
    options: tuple[Option, ...] = field(default_factory=tuple)

    def __init__(
        self,
        key: str,
        title: str,
        kind: Kind,
        record_path: str | None,
        anchor_cell: str,
        options: Sequence[Option] = (),
    ) -> None:
        # Validate kind is one of the allowed values
        if kind not in ("text", "single_choice", "multi_choice"):
            raise ValueError(f"Invalid kind: {kind!r}, must be one of 'text', 'single_choice', 'multi_choice'")
        object.__setattr__(self, "key", key)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "record_path", record_path)
        object.__setattr__(self, "anchor_cell", anchor_cell)
        object.__setattr__(self, "options", tuple(options))
        # Validate kind-options invariants
        if kind == "text" and self.options:
            raise ValueError(f"text field must have empty options, got {len(self.options)}")
        if kind in ("single_choice", "multi_choice") and not self.options:
            raise ValueError(f"{kind} field requires at least one option")
        # Reject duplicate option codes
        codes = [opt.code for opt in self.options]
        if len(codes) != len(set(codes)):
            seen = set()
            for code in codes:
                if code in seen:
                    raise ValueError(f"Duplicate option code: {code!r}")
                seen.add(code)

    def selected_codes(self, value: bool | str | list[str] | None) -> tuple[str, ...]:
        """Return option codes selected by the given record value.
        
        This provides a generic contract for mapping record values to option codes:
        - For text fields: always returns ()
        - For single_choice fields:
          - Bool value only accepted if field is bool-backed (codes ⊆ {"true", "false"})
          - String value accepted for non-bool-backed fields
        - For multi_choice fields: list of strings only
        - None always maps to ()
        """
        if self.kind == "text":
            return ()
        
        if value is None:
            return ()
        
        if isinstance(value, bool):
            # Bool values only valid for bool-backed single_choice fields
            if self.kind != "single_choice":
                raise TypeError(
                    f"bool value not supported for {self.kind} field "
                    f"(field is not bool-backed single_choice)"
                )
            # Check if this is a bool-backed field (codes subset of {true, false})
            option_codes = {opt.code for opt in self.options}
            if not option_codes.issubset({"true", "false"}):
                raise TypeError(
                    f"bool value not supported for field {self.key!r}: "
                    f"field is not bool-backed (codes: {option_codes})"
                )
            # For bool-backed fields: True -> first code, False -> ()
            if value:
                if self.options:
                    return (self.options[0].code,)
                return ()
            else:
                return ()
        
        if isinstance(value, str):
            # String value only valid for single_choice fields
            if self.kind != "single_choice":
                raise TypeError(
                    f"str value not supported for {self.kind} field "
                    f"(expected list for multi_choice)"
                )
            return (value,)
        
        if isinstance(value, list):
            # List value only valid for multi_choice fields
            if self.kind != "multi_choice":
                raise TypeError(
                    f"list value not supported for {self.kind} field "
                    f"(field is single_choice, not multi_choice)"
                )
            return tuple(value)
        
        return ()


@dataclass(frozen=True, slots=True)
class Section:
    id: str
    title: str
    fields: tuple[Field, ...]

    def __init__(self, id: str, title: str, fields: Sequence[Field]) -> None:
        object.__setattr__(self, "id", id)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "fields", tuple(fields))


@dataclass(frozen=True, slots=True)
class FormLayout:
    template_id: str
    sections: tuple[Section, ...]

    def __init__(self, template_id: str, sections: Sequence[Section]) -> None:
        object.__setattr__(self, "template_id", template_id)
        object.__setattr__(self, "sections", tuple(sections))
        # Reject duplicate field keys
        keys = [fld.key for sec in self.sections for fld in sec.fields]
        if len(keys) != len(set(keys)):
            seen = set()
            for key in keys:
                if key in seen:
                    raise ValueError(f"Duplicate field key: {key!r}")
                seen.add(key)

    def iter_fields(self) -> Iterator[Field]:
        for section in self.sections:
            for fld in section.fields:
                yield fld

    def field_by_key(self, key: str) -> Field | None:
        for section in self.sections:
            for fld in section.fields:
                if fld.key == key:
                    return fld
        return None

    def iter_options(self) -> Iterator[tuple[Field, Option]]:
        for section in self.sections:
            for fld in section.fields:
                for opt in fld.options:
                    yield (fld, opt)

    def options_by_code(self, field_key: str) -> dict[str, Option]:
        fld = self.field_by_key(field_key)
        if fld is None:
            raise KeyError(field_key)
        return {opt.code: opt for opt in fld.options}


def _opts(*triples: tuple[str, str, str]) -> tuple[Option, ...]:
    """Helper to build option tuples from (label, code, cell) triples."""
    return tuple(Option(label=label, code=code, cell=cell) for label, code, cell in triples)


def service_record_layout() -> FormLayout:
    """Return the curated service_record.v1 form layout.
    
    This layout covers the form sections for service record tracking, including
    demographics, patient information, consultations, supplies, and referrals.
    """
    # Top section: service_date
    top = Section(
        id="top",
        title="頂部",
        fields=[
            Field(
                key="service_date",
                title="服務年/月/日",
                kind="text",
                record_path="service_date",
                anchor_cell="A2",
            ),
        ],
    )
    
    # Section A: 服務評估統計
    section_a = Section(
        id="A",
        title="服務評估統計",
        fields=[
            Field(
                key="consultation.health_medical",
                title="健康醫療",
                kind="multi_choice",
                record_path="services.consultation.health_medical",
                anchor_cell="B4",
                options=_opts(
                    ("1.癌症篩檢與預防", "screening_prevention", "C4"),
                    ("2.疾病及治療知識", "disease_treatment_knowledge", "D4"),
                    ("3.醫病溝通", "doctor_patient_communication", "E4"),
                    ("4.健康生活", "healthy_lifestyle", "F4"),
                    ("5.第二意見諮詢", "second_opinion", "C5"),
                    ("6.轉院、掛診", "transfer_registration", "D5"),
                    ("7.安寧緩和與病主法", "palliative_patient_rights", "E5"),
                    ("8.其他", "other", "F5"),
                ),
            ),
            Field(
                key="consultation.symptom_side_effect",
                title="症狀副作用",
                kind="multi_choice",
                record_path="services.consultation.symptom_side_effect",
                anchor_cell="B6",
                options=_opts(
                    ("1.治療副作用因應", "treatment_side_effect", "C6"),
                    ("2.傷口照護", "wound_care", "D6"),
                    ("3.疼痛處理", "pain_management", "E6"),
                    ("4.疲憊與體力", "fatigue_strength", "F6"),
                    ("5.整合治療照護", "integrated_care", "C7"),
                    ("6. 性與生育", "sexuality_fertility", "D7"),
                    ("7.其他：", "other", "E7"),
                ),
            ),
            Field(
                key="consultation.nutrition_diet",
                title="營養飲食",
                kind="multi_choice",
                record_path="services.consultation.nutrition_diet",
                anchor_cell="B8",
                options=_opts(
                    ("1.飲食與調理", "diet_conditioning", "C8"),
                    ("2. 營養品", "nutrition_products", "D8"),
                    ("3.保健/健康食品", "health_food", "E8"),
                    ("4.其他", "other", "F8"),
                ),
            ),
            Field(
                key="consultation.psychosocial_emotion",
                title="心理社會情緒",
                kind="multi_choice",
                record_path="services.consultation.psychosocial_emotion",
                anchor_cell="B10",
                options=_opts(
                    ("1.心理情緒支持", "emotional_support", "C10"),
                    ("2.疾病認知與適應", "disease_adaptation", "D10"),
                    ("3.家庭互動溝通", "family_communication", "E10"),
                    ("4.失落與悲傷關懷", "loss_grief", "F10"),
                    ("5.靈性關懷", "spiritual_care", "C11"),
                    ("6.其他", "other", "D11"),
                ),
            ),
            Field(
                key="consultation.financial_social",
                title="經濟社福",
                kind="multi_choice",
                record_path="services.consultation.financial_social",
                anchor_cell="B12",
                options=_opts(
                    ("1.經濟與社福", "financial_welfare", "C12"),
                    ("2.營養品補助", "nutrition_subsidy", "D12"),
                    ("3.交通補助", "transportation_subsidy", "E12"),
                    ("4.住宿補助", "housing_subsidy", "F12"),
                    ("5.保險議題", "insurance", "C13"),
                    ("6.就學與就業議題", "school_work", "D13"),
                    ("7.康復用品與輔具", "rehab_supplies_aids", "E13"),
                    ("8.其他", "other", "F13"),
                ),
            ),
            Field(
                key="consultation.care_support",
                title="照護支持",
                kind="multi_choice",
                record_path="services.consultation.care_support",
                anchor_cell="B14",
                options=_opts(
                    ("1.病友經驗", "peer_experience", "C14"),
                    ("2.長期照顧", "long_term_care", "D14"),
                    ("3.照顧者支持", "caregiver_support", "E14"),
                    ("4.人際與社交", "relationship_social", "F14"),
                    ("5.出院準備", "discharge_planning", "C15"),
                    ("6.其他", "other", "D15"),
                ),
            ),
            Field(
                key="supplies",
                title="物資",
                kind="multi_choice",
                record_path="services.supplies",
                anchor_cell="A16",
                options=_opts(
                    ("1.假髮/頭巾/毛帽用品", "wig_hat", "B16"),
                    ("2.其他照護用品", "other_care_supplies", "C16"),
                    ("3.營養品", "nutrition_products", "D16"),
                    ("4.其他用品與設備", "other_equipment", "E16"),
                ),
            ),
            Field(
                key="internal_referrals",
                title="內部轉介",
                kind="multi_choice",
                record_path="services.internal_referrals",
                anchor_cell="A17",
                options=_opts(
                    ("1.假髮/頭巾/毛帽用品", "wig_hat", "B17"),
                    ("2.其他照護用品", "other_care_supplies", "C17"),
                    ("3.社福資源", "social_welfare", "D17"),
                    ("4.病友志工、團體", "peer_volunteer_group", "E17"),
                    ("5.心理相關", "psychology", "F17"),
                    ("6.營養相關", "nutrition", "B18"),
                    ("7. 長照資源", "long_term_care", "C18"),
                    ("8.復健相關", "rehabilitation", "D18"),
                    ("9.照護資訊", "care_information", "E18"),
                    ("10.其他及活動", "other_activity", "F18"),
                ),
            ),
            Field(
                key="external_referrals",
                title="外部轉介",
                kind="multi_choice",
                record_path="services.external_referrals",
                anchor_cell="A19",
                options=_opts(
                    ("1假髮/頭巾/毛帽用品", "wig_hat", "B19"),
                    ("2.其他照護用品", "other_care_supplies", "C19"),
                    ("3.社福資源", "social_welfare", "D19"),
                    ("4.病友志工、團體", "peer_volunteer_group", "E19"),
                    ("5.心理相關", "psychology", "F19"),
                    ("6.營養相關", "nutrition", "B20"),
                    ("7. 長照資源", "long_term_care", "C20"),
                    ("8.復健相關", "rehabilitation", "D20"),
                    ("9.照護資訊", "care_information", "E20"),
                    ("10.其他及活動", "other_activity", "F20"),
                ),
            ),
            Field(
                key="referral_outcomes",
                title="轉介成果",
                kind="multi_choice",
                record_path="services.referral_outcomes",
                anchor_cell="A21",
                options=_opts(
                    ("1.獲得假髮/頭巾/毛帽用品", "received_wig_hat", "B21"),
                    ("2.獲得其他照護用品", "received_other_supplies", "C21"),
                    ("3.獲得經濟補助", "received_financial_aid", "D21"),
                    ("4.獲得服務協助", "received_service_help", "E21"),
                ),
            ),
        ],
    )
    
    # Section B: 綜合身份統計
    section_b = Section(
        id="B",
        title="綜合身份統計",
        fields=[
            Field(
                key="identity",
                title="身分",
                kind="single_choice",
                record_path="identity",
                anchor_cell="A23",
                options=_opts(
                    ("病人", "patient", "B23"),
                    ("親友及照顧者", "family_caregiver", "C23"),
                    ("一般民眾及其他", "public_other", "D23"),
                ),
            ),
            Field(
                key="name",
                title="姓名",
                kind="text",
                record_path="name",
                anchor_cell="B23",
            ),
            Field(
                key="medical_record_no",
                title="病歷號",
                kind="text",
                record_path="medical_record_no",
                anchor_cell="B23",
            ),
            Field(
                key="diagnosis_date",
                title="診斷日",
                kind="text",
                record_path=None,
                anchor_cell="A24",
            ),
            Field(
                key="gender",
                title="性別",
                kind="single_choice",
                record_path="gender",
                anchor_cell="A25",
                options=_opts(
                    ("女性", "female", "B25"),
                    ("男性", "male", "B26"),
                    ("其他", "other", "B27"),
                ),
            ),
            Field(
                key="nationality",
                title="國籍",
                kind="single_choice",
                record_path="patient_fields.nationality",
                anchor_cell="A28",
                options=_opts(
                    ("本國籍", "local", "B28"),
                    ("外國籍", "foreign", "B29"),
                ),
            ),
            Field(
                key="age",
                title="年齡",
                kind="single_choice",
                record_path="patient_fields.age_group",
                anchor_cell="A30",
                options=_opts(
                    ("20歲以下", "20_under", "B30"),
                    ("21-30歲", "21_30", "B31"),
                    ("31-40歲", "31_40", "B32"),
                    ("41-50歲", "41_50", "B33"),
                    ("51-60歲", "51_60", "B34"),
                    ("61-70歲", "61_70", "B35"),
                    ("71歲以上", "71_over", "B36"),
                ),
            ),
        ],
    )
    
    # Section C: 病人基本資料統計
    section_c = Section(
        id="C",
        title="病人基本資料統計",
        fields=[
            Field(
                key="channel",
                title="管道",
                kind="single_choice",
                record_path="patient_fields.channel",
                anchor_cell="A38",
                options=_opts(
                    ("1.自行得知", "self_known", "B38"),
                    ("2.病友或家屬介紹", "introduced", "C38"),
                    ("3.主動關懷或追蹤", "active_followup", "D38"),
                    ("4.院內轉介", "internal_referral", "E38"),
                    ("5.院外轉介", "external_referral", "F38"),
                    ("6.活動課程接觸", "activity", "B39"),
                    ("7.其他", "other", "C39"),
                ),
            ),
            Field(
                key="disease_status",
                title="疾病狀態",
                kind="single_choice",
                record_path="patient_fields.disease_status",
                anchor_cell="A40",
                options=_opts(
                    ("1.尚未確診", "undiagnosed", "B40"),
                    ("2.確診，尚未治療", "diagnosed_not_treated", "C40"),
                    ("3.確診，拒絕治療", "diagnosed_refused", "D40"),
                    ("4.治療中", "treating", "E40"),
                    ("5.復發治療中", "recurrence_treating", "F40"),
                    ("6.追蹤期", "followup", "B41"),
                    ("7.緩和治療", "palliative", "C41"),
                ),
            ),
            Field(
                key="source",
                title="來源",
                kind="single_choice",
                record_path="patient_fields.source",
                anchor_cell="A42",
                options=_opts(
                    ("1.門診", "outpatient", "B42"),
                    ("2.住院", "inpatient", "C42"),
                    ("3.急診", "emergency", "D42"),
                ),
            ),
            Field(
                key="cancer",
                title="癌症",
                kind="multi_choice",
                record_path="patient_fields.cancers",
                anchor_cell="A43",
                options=_opts(
                    ("1.腦癌", "brain_cancer", "B43"),
                    ("2.鼻咽癌", "nasopharyngeal_cancer", "C43"),
                    ("3.口腔癌", "oral_cancer", "D43"),
                    ("4.下咽癌", "hypopharyngeal_cancer", "E43"),
                    ("5.喉癌", "laryngeal_cancer", "F43"),
                    ("6.甲狀腺癌", "thyroid_cancer", "B44"),
                    ("7.食道癌", "esophageal_cancer", "C44"),
                    ("8.乳癌", "breast_cancer", "D44"),
                    ("9.肺癌", "lung_cancer", "E44"),
                    ("10.肝癌", "liver_cancer", "F44"),
                    ("11.結直腸癌", "colorectal_cancer", "B45"),
                    ("12.胃癌", "stomach_cancer", "C45"),
                    ("13.胰臟癌", "pancreatic_cancer", "D45"),
                    ("14.腎臟癌", "kidney_cancer", "E45"),
                    ("15.膀胱癌", "bladder_cancer", "F45"),
                    ("16.卵巢癌", "ovarian_cancer", "B46"),
                    ("17.子宮內膜癌", "endometrial_cancer", "C46"),
                    ("18.子宮頸癌", "cervical_cancer", "D46"),
                    ("19.攝護腺癌", "prostate_cancer", "E46"),
                    ("20.淋巴癌", "lymphoma", "F46"),
                    ("21.白血病", "leukemia", "B47"),
                    ("22.皮膚癌", "skin_cancer", "C47"),
                    ("23.多發性骨髓瘤", "multiple_myeloma", "D47"),
                    ("24.惡性肉瘤", "sarcoma", "E47"),
                    ("25.其他", "other", "F47"),
                ),
            ),
            Field(
                key="newly_diagnosed",
                title="一年內新診斷個案",
                kind="single_choice",
                record_path="patient_fields.newly_diagnosed_within_year",
                anchor_cell="A48",
                options=_opts(
                    ("一年內新診斷個案", "true", "A48"),
                ),
            ),
        ],
    )
    
    return FormLayout(
        template_id="service_record.v1",
        sections=(top, section_a, section_b, section_c),
    )
