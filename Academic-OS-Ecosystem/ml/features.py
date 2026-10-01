"""
Feature engineering pipeline. Shared by training and the FastAPI inference
path so train/serve skew can't creep in - both call `build_features` on the
same raw input shape.
"""

import pandas as pd

RAW_FEATURE_COLUMNS = [
    "preferred_study_hour",
    "weekly_study_hours",
    "consistency_score",
    "attendance_pct",
    "backlogs_count",
    "aptitude_score",
    "avg_quiz_score",
    "quiz_score_std",
    "assignment_avg",
    "trimester_gpa",
    "modules_completed_pct",
    "communication_score",
    "projects_count",
    "internships_count",
    "mock_interviews_attended",
]

STUDY_PERIOD_CATEGORIES = ["late_night", "morning", "afternoon", "evening", "night"]


def derive_study_period(preferred_study_hour: pd.Series) -> pd.Series:
    return pd.cut(
        preferred_study_hour,
        bins=[-1, 5, 11, 17, 21, 24],
        labels=STUDY_PERIOD_CATEGORIES,
    ).astype(str)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Takes a dataframe with RAW_FEATURE_COLUMNS (+ optionally study_period)
    and returns a model-ready feature matrix: numeric features + one-hot
    encoded study period.
    """
    df = df.copy()

    if "study_period" not in df.columns:
        df["study_period"] = derive_study_period(df["preferred_study_hour"])

    # Engineered ratios/interactions - these are the "feature engineering"
    # value-add beyond raw columns
    df["quiz_consistency_ratio"] = df["avg_quiz_score"] / (df["quiz_score_std"] + 1)
    df["effort_score"] = (
        0.4 * df["consistency_score"] * 100
        + 0.3 * df["attendance_pct"]
        + 0.3 * df["modules_completed_pct"]
    ) / 100
    df["academic_strength"] = (
        df["avg_quiz_score"] + df["assignment_avg"] + df["trimester_gpa"] * 10
    ) / 3
    df["employability_signal"] = (
        df["projects_count"] * 8
        + df["internships_count"] * 12
        + df["mock_interviews_attended"] * 2
        + df["communication_score"]
    )

    study_period_dummies = pd.get_dummies(
        df["study_period"], prefix="study_period"
    )
    for cat in STUDY_PERIOD_CATEGORIES:
        col = f"study_period_{cat}"
        if col not in study_period_dummies.columns:
            study_period_dummies[col] = 0

    feature_df = pd.concat(
        [
            df[RAW_FEATURE_COLUMNS + [
                "quiz_consistency_ratio",
                "effort_score",
                "academic_strength",
                "employability_signal",
            ]],
            study_period_dummies[[f"study_period_{c}" for c in STUDY_PERIOD_CATEGORIES]],
        ],
        axis=1,
    )
    return feature_df


def feature_columns():
    """Canonical, ordered list of model input columns. Used to enforce
    consistent column order between training and inference."""
    return (
        RAW_FEATURE_COLUMNS
        + [
            "quiz_consistency_ratio",
            "effort_score",
            "academic_strength",
            "employability_signal",
        ]
        + [f"study_period_{c}" for c in STUDY_PERIOD_CATEGORIES]
    )
