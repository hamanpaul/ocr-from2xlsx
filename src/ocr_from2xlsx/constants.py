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
