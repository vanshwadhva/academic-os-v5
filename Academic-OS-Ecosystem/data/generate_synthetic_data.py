"""
Synthetic student behavior + placement dataset generator.

IMPORTANT - read before trusting any output of this pipeline:
This data is fabricated. The correlations between features and the
placement label are hand-specified by me below (weights in
`placement_logit`), not observed from real students. A model trained
on this data learns MY assumptions about what drives placement, not
reality. This is a systems-engineering exercise (data gen -> feature
engineering -> training -> serving -> API), not a real predictor.
Treat every output downstream as "does the pipeline work correctly,"
never as "is this true about a student."

Generation strategy:
- Each student has a latent `ability` variable (unobserved in the
  feature set) that drives correlated noise into aptitude, GPA, quiz
  scores, and consistency - mimicking how real students with strong
  underlying ability tend to score well across multiple correlated
  signals, while still allowing individual feature noise.
- Placement label is drawn probabilistically from a logistic function
  of features (not deterministic), so the classification task is
  learnable but not trivial - mirroring the noise inherent to real
  hiring outcomes (interview variance, role fit, market conditions).
"""

import numpy as np
import pandas as pd

RNG_SEED = 42


def generate(n_students: int = 5000, seed: int = RNG_SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    # Latent ability, standard normal. Not exposed as a feature.
    ability = rng.normal(0, 1, n_students)

    # --- Behavioral features ---
    preferred_study_hour = rng.integers(0, 24, n_students)  # 24h clock
    study_period = pd.cut(
        preferred_study_hour,
        bins=[-1, 5, 11, 17, 21, 24],
        labels=["late_night", "morning", "afternoon", "evening", "night"],
    ).astype(str)

    weekly_study_hours = np.clip(
        rng.normal(12 + 3 * ability, 4, n_students), 1, 40
    )

    # consistency: fraction of weeks with meaningful activity, correlated
    # with ability but with its own noise (some high-ability students are
    # inconsistent, some low-ability students grind)
    consistency_score = np.clip(
        rng.normal(0.55 + 0.15 * ability, 0.2, n_students), 0, 1
    )

    attendance_pct = np.clip(
        rng.normal(70 + 8 * ability, 15, n_students), 0, 100
    )

    backlogs_count = np.clip(
        rng.poisson(lam=np.clip(1.2 - 0.5 * ability, 0.05, None), size=n_students),
        0,
        8,
    )

    # --- Academic performance features ---
    aptitude_score = np.clip(rng.normal(60 + 12 * ability, 10, n_students), 0, 100)
    avg_quiz_score = np.clip(rng.normal(58 + 14 * ability, 12, n_students), 0, 100)
    quiz_score_std = np.clip(rng.normal(12 - 2 * ability, 4, n_students), 1, 30)
    assignment_avg = np.clip(rng.normal(62 + 11 * ability, 12, n_students), 0, 100)
    trimester_gpa = np.clip(rng.normal(6.5 + 1.1 * ability, 1.0, n_students), 0, 10)

    modules_completed_pct = np.clip(
        rng.normal(70 + 10 * consistency_score * 30, 12, n_students), 0, 100
    )

    # --- Employability / soft-skill features ---
    communication_score = np.clip(
        rng.normal(55 + 6 * ability, 15, n_students), 0, 100
    )
    projects_count = np.clip(
        rng.poisson(lam=np.clip(1.5 + 0.6 * ability, 0.1, None), size=n_students),
        0,
        10,
    )
    internships_count = np.clip(
        rng.poisson(lam=np.clip(0.6 + 0.3 * ability, 0.05, None), size=n_students),
        0,
        5,
    )
    mock_interviews_attended = np.clip(
        rng.poisson(lam=3, size=n_students), 0, 15
    )  # mostly independent of ability - effort signal

    # --- Placement label: probabilistic logistic function ---
    z = (
        -2.2
        + 0.45 * ability
        + 0.015 * (avg_quiz_score - 50)
        + 0.30 * (trimester_gpa - 6.5)
        + 0.012 * (communication_score - 50)
        + 0.25 * projects_count
        + 0.35 * internships_count
        + 0.10 * mock_interviews_attended
        + 1.2 * (consistency_score - 0.5)
        - 0.18 * backlogs_count
        + rng.normal(0, 0.6, n_students)  # irreducible noise: interview luck, market
    )
    placement_prob = 1 / (1 + np.exp(-z))
    placed = rng.binomial(1, placement_prob)

    df = pd.DataFrame(
        {
            "student_id": [f"S{i:05d}" for i in range(n_students)],
            "preferred_study_hour": preferred_study_hour,
            "study_period": study_period,
            "weekly_study_hours": weekly_study_hours.round(1),
            "consistency_score": consistency_score.round(3),
            "attendance_pct": attendance_pct.round(1),
            "backlogs_count": backlogs_count,
            "aptitude_score": aptitude_score.round(1),
            "avg_quiz_score": avg_quiz_score.round(1),
            "quiz_score_std": quiz_score_std.round(1),
            "assignment_avg": assignment_avg.round(1),
            "trimester_gpa": trimester_gpa.round(2),
            "modules_completed_pct": modules_completed_pct.round(1),
            "communication_score": communication_score.round(1),
            "projects_count": projects_count,
            "internships_count": internships_count,
            "mock_interviews_attended": mock_interviews_attended,
            "placement_probability_true": placement_prob.round(4),  # ground-truth latent prob, for debugging only
            "placed": placed,
        }
    )
    return df


if __name__ == "__main__":
    df = generate(5000)
    df.to_csv("synthetic_students.csv", index=False)
    print(df.head())
    print(f"\nGenerated {len(df)} rows. Placement rate: {df['placed'].mean():.2%}")
