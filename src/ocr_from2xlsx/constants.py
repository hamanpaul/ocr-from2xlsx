SCHEMA_VERSION = "service_record.v1"

IDENTITIES = {"patient", "family_caregiver", "public_other"}
GENDERS = {"female", "male", "other"}
REVIEW_STATUSES = {"pending", "confirmed", "skipped", "forced", "written"}
SOURCE_TYPES = {"camera", "image_folder", "json_import", "manual"}

PATIENT_ENUMS = {
    "nationality": {"local", "foreign"},
    "age_group": {"20_under", "21_30", "31_40", "41_50", "51_60", "61_70", "71_over"},
    "channel": {
        "self_known",
        "introduced",
        "active_followup",
        "internal_referral",
        "external_referral",
        "activity",
        "other",
    },
    "disease_status": {
        "undiagnosed",
        "diagnosed_not_treated",
        "diagnosed_refused",
        "treating",
        "recurrence_treating",
        "followup",
        "palliative",
    },
    "source": {"outpatient", "inpatient", "emergency"},
}

SERVICE_CATEGORIES = {
    "health_medical": {
        "screening_prevention",
        "disease_treatment_knowledge",
        "doctor_patient_communication",
        "healthy_lifestyle",
        "second_opinion",
        "transfer_registration",
        "palliative_patient_rights",
        "other",
    },
    "symptom_side_effect": {
        "treatment_side_effect",
        "wound_care",
        "pain_management",
        "fatigue_strength",
        "integrated_care",
        "sexuality_fertility",
        "other",
    },
    "nutrition_diet": {"diet_conditioning", "nutrition_products", "health_food", "other"},
    "psychosocial_emotion": {
        "emotional_support",
        "disease_adaptation",
        "family_communication",
        "loss_grief",
        "spiritual_care",
        "other",
    },
    "financial_social": {
        "financial_welfare",
        "nutrition_subsidy",
        "transportation_subsidy",
        "housing_subsidy",
        "insurance",
        "school_work",
        "rehab_supplies_aids",
        "other",
    },
    "care_support": {
        "peer_experience",
        "long_term_care",
        "caregiver_support",
        "relationship_social",
        "discharge_planning",
        "other",
    },
}

SUPPLY_CODES = {"wig_hat", "other_care_supplies", "nutrition_products", "other_equipment"}
RESOURCE_CODES = {
    "wig_hat",
    "other_care_supplies",
    "social_welfare",
    "peer_volunteer_group",
    "psychology",
    "nutrition",
    "long_term_care",
    "rehabilitation",
    "care_information",
    "other_activity",
}
OUTCOME_CODES = {
    "received_wig_hat",
    "received_other_supplies",
    "received_financial_aid",
    "received_service_help",
}

WORKBOOK_SHEET = "個案總表"

BASIC_COLUMN_BY_FIELD = {
    "service_month": "服務月份",
    "service_date": "服務日期",
    "identity": "身分",
    "name": "姓名",
    "medical_record_no": "ID",
    "birthdate": "生日",
    "gender": "性別",
    "nationality": "國籍\n(病人才填)",
    "age_group": "年齡\n(病人才填)",
    "channel": "管道\n(病人才填)",
    "disease_status": "疾病狀態\n(病人才填)",
    "source": "來源\n(病人才填)",
    "newly_diagnosed_within_year": "一年內新診斷(病人才填)",
    "discharge_followup": "出院後關懷",
}

IDENTITY_LABELS = {
    "patient": "病人",
    "family_caregiver": "親友及照顧者",
    "public_other": "一般民眾及其他",
}

GENDER_LABELS = {"female": "女性", "male": "男性", "other": "其他"}
NATIONALITY_LABELS = {"local": "本國籍", "foreign": "外國籍"}
AGE_GROUP_LABELS = {
    "20_under": "20歲以下",
    "21_30": "21-30歲",
    "31_40": "31-40歲",
    "41_50": "41-50歲",
    "51_60": "51-60歲",
    "61_70": "61-70歲",
    "71_over": "71歲以上",
}
CHANNEL_LABELS = {
    "self_known": "1.自行得知",
    "introduced": "2.病友或家屬介紹",
    "active_followup": "3.主動關懷或追蹤",
    "internal_referral": "4.院內轉介",
    "external_referral": "5.院外轉介",
    "activity": "6.活動課程接觸",
    "other": "7.其他",
}
DISEASE_STATUS_LABELS = {
    "undiagnosed": "1.尚未確診",
    "diagnosed_not_treated": "2.確診，尚未治療",
    "diagnosed_refused": "3.確診，拒絕治療",
    "treating": "4.治療中",
    "recurrence_treating": "5.復發治療中",
    "followup": "6.追蹤期",
    "palliative": "7.緩和治療",
}
SOURCE_LABELS = {"outpatient": "1.門診", "inpatient": "2.住院", "emergency": "3.急診"}
CANCER_LABELS = {
    "brain_cancer": "1.腦癌",
    "nasopharyngeal_cancer": "2.鼻咽癌",
    "oral_cancer": "3.口腔癌",
    "hypopharyngeal_cancer": "4.下咽癌",
    "laryngeal_cancer": "5.喉癌",
    "thyroid_cancer": "6.甲狀腺癌",
    "esophageal_cancer": "7.食道癌",
    "breast_cancer": "8.乳癌",
    "lung_cancer": "9.肺癌",
    "liver_cancer": "10.肝癌",
    "colorectal_cancer": "11.結直腸癌",
    "stomach_cancer": "12.胃癌",
    "pancreatic_cancer": "13.胰臟癌",
    "kidney_cancer": "14.腎臟癌",
    "bladder_cancer": "15.膀胱癌",
    "ovarian_cancer": "16.卵巢癌",
    "endometrial_cancer": "17.子宮內膜癌",
    "cervical_cancer": "18.子宮頸癌",
    "prostate_cancer": "19.攝護腺癌",
    "lymphoma": "20.淋巴癌",
    "leukemia": "21.白血病",
    "skin_cancer": "22.皮膚癌",
    "multiple_myeloma": "23.多發性骨髓瘤",
    "sarcoma": "24.惡性肉瘤",
    "other": "25.其他",
}
