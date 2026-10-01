"""
Prediction Service
Loads trained ML models and generates predictions for expected grade, completion probability, and risk level.

Production considerations:
- Model versioning and hot-reloading
- Confidence scoring and uncertainty quantification
- Feature validation before inference
- Prediction logging for audit trail
- Graceful degradation if model unavailable
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
from enum import Enum

import numpy as np
import xgboost as xgb
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    """Risk classification levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class LetterGrade(str, Enum):
    """Letter grade mapping."""
    A_PLUS = "A+"
    A = "A"
    A_MINUS = "A-"
    B_PLUS = "B+"
    B = "B"
    B_MINUS = "B-"
    C_PLUS = "C+"
    C = "C"
    C_MINUS = "C-"
    D = "D"
    F = "F"


class GradeDistribution(BaseModel):
    """Grade distribution for calibration."""
    grade: LetterGrade
    min_score: float = Field(..., description="Minimum numeric score for this grade")
    max_score: float = Field(..., description="Maximum numeric score for this grade")


class PredictionOutput(BaseModel):
    """Standardized prediction output."""
    student_id: str
    course_id: str
    prediction_type: str  # expected_grade, completion, risk
    prediction_value: str | float
    confidence_score: Optional[float] = Field(None, description="0.0-1.0")
    model_name: str
    model_version: str
    generated_at: datetime
    feature_set_hash: str = Field(..., description="SHA256 hash of features used")
    raw_score: Optional[float] = Field(None, description="Numeric score if applicable")


class StudentFeatures(BaseModel):
    """Feature vector for a single student in a course."""
    student_id: str
    course_id: str
    
    # Base features
    module_completion_pct: float = Field(..., ge=0, le=100)
    completed_modules: int = Field(..., ge=0)
    pending_modules: int = Field(..., ge=0)
    quiz_average: Optional[float] = Field(None, ge=0, le=100)
    assignment_average: Optional[float] = Field(None, ge=0, le=100)
    attendance_pct: Optional[float] = Field(None, ge=0, le=100)
    missing_submissions: int = Field(default=0, ge=0)
    late_submissions: int = Field(default=0, ge=0)
    days_since_activity: int = Field(default=0, ge=0)
    current_grade: Optional[float] = Field(None, ge=0, le=100)
    course_age_days: int = Field(..., ge=0)
    weeks_remaining: int = Field(..., ge=0)
    submission_consistency: Optional[float] = Field(None, ge=0, le=1)
    
    # Derived features (computed)
    rolling_7day_activity_change: Optional[float] = None
    rolling_14day_activity_change: Optional[float] = None
    grade_trend: Optional[float] = None  # Slope of grade progression
    assessment_volatility: Optional[float] = None
    attendance_performance_correlation: Optional[float] = None
    engagement_score: Optional[float] = None
    deadline_pressure_index: Optional[float] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "student_id": "student_123",
                "course_id": "course_456",
                "module_completion_pct": 42.0,
                "completed_modules": 3,
                "pending_modules": 4,
                "quiz_average": 78.5,
                "assignment_average": 82.0,
                "attendance_pct": 94.0,
                "current_grade": 80.5,
                "course_age_days": 45,
                "weeks_remaining": 8,
            }
        }


class PredictionService:
    """
    XGBoost-based ML prediction service.
    
    Manages:
    - Model loading and versioning
    - Feature validation
    - Inference for expected grade, completion, and risk
    - Confidence calibration
    - Prediction logging
    
    Models expected in:
    - ml/models/expected_grade_v1.0.pkl
    - ml/models/completion_v1.0.pkl
    - ml/models/risk_v1.0.pkl
    
    Metadata in:
    - ml/models/expected_grade_v1.0_metadata.json
    - ml/models/completion_v1.0_metadata.json
    - ml/models/risk_v1.0_metadata.json
    """
    
    # Feature names and order (must match training)
    FEATURE_NAMES = [
        "module_completion_pct",
        "completed_modules",
        "pending_modules",
        "quiz_average",
        "assignment_average",
        "attendance_pct",
        "missing_submissions",
        "late_submissions",
        "days_since_activity",
        "current_grade",
        "course_age_days",
        "weeks_remaining",
        "submission_consistency",
        "rolling_7day_activity_change",
        "rolling_14day_activity_change",
        "grade_trend",
        "assessment_volatility",
        "attendance_performance_correlation",
        "engagement_score",
        "deadline_pressure_index",
    ]
    
    # Grade thresholds (numeric to letter grade mapping)
    GRADE_DISTRIBUTION = [
        GradeDistribution(grade=LetterGrade.A_PLUS, min_score=95, max_score=100),
        GradeDistribution(grade=LetterGrade.A, min_score=90, max_score=94.99),
        GradeDistribution(grade=LetterGrade.A_MINUS, min_score=85, max_score=89.99),
        GradeDistribution(grade=LetterGrade.B_PLUS, min_score=80, max_score=84.99),
        GradeDistribution(grade=LetterGrade.B, min_score=75, max_score=79.99),
        GradeDistribution(grade=LetterGrade.B_MINUS, min_score=70, max_score=74.99),
        GradeDistribution(grade=LetterGrade.C_PLUS, min_score=65, max_score=69.99),
        GradeDistribution(grade=LetterGrade.C, min_score=60, max_score=64.99),
        GradeDistribution(grade=LetterGrade.C_MINUS, min_score=55, max_score=59.99),
        GradeDistribution(grade=LetterGrade.D, min_score=50, max_score=54.99),
        GradeDistribution(grade=LetterGrade.F, min_score=0, max_score=49.99),
    ]
    
    def __init__(self, models_dir: Optional[str] = None):
        """
        Initialize prediction service.
        
        Args:
            models_dir: Path to directory containing trained models.
                       Defaults to ./ml/models
        """
        self.models_dir = Path(models_dir or os.getenv("ML_MODELS_DIR", "./ml/models"))
        
        self.models = {}
        self.metadata = {}
        
        self._load_models()
    
    def _load_models(self):
        """Load all trained models and metadata from disk."""
        model_types = ["expected_grade", "completion", "risk"]
        
        for model_type in model_types:
            try:
                # Try loading latest version first
                versions = list(self.models_dir.glob(f"{model_type}_v*.pkl"))
                if not versions:
                    logger.warning(f"No {model_type} model found")
                    continue
                
                # Sort by version and take latest
                latest = sorted(versions, key=lambda p: p.stem.split("_v")[1])[-1]
                version = latest.stem.split("_v")[1]
                
                self.models[model_type] = xgb.Booster()
                self.models[model_type].load_model(str(latest))
                
                # Load metadata
                metadata_path = latest.with_stem(f"{model_type}_v{version}_metadata")
                if metadata_path.with_suffix(".json").exists():
                    with open(metadata_path.with_suffix(".json")) as f:
                        self.metadata[model_type] = json.load(f)
                else:
                    self.metadata[model_type] = {"version": version}
                
                logger.info(f"Loaded {model_type} model v{version}")
            
            except Exception as e:
                logger.error(f"Failed to load {model_type} model: {e}")
    
    def _numeric_to_letter_grade(self, numeric_score: float) -> LetterGrade:
        """Convert numeric score to letter grade."""
        for grade_dist in self.GRADE_DISTRIBUTION:
            if grade_dist.min_score <= numeric_score <= grade_dist.max_score:
                return grade_dist.grade
        return LetterGrade.F
    
    def _calibrate_probability(self, raw_score: float, model_type: str) -> float:
        """
        Calibrate model output to probability between 0 and 1.
        
        For regression models, uses sigmoid. For classifiers, uses softmax.
        """
        if model_type == "completion":
            # Completion is binary; apply sigmoid for probability
            return 1.0 / (1.0 + np.exp(-raw_score))
        elif model_type == "risk":
            # Risk classifier; return as-is if already probability
            return np.clip(raw_score, 0.0, 1.0)
        else:  # expected_grade (regression)
            # Return as-is; will be converted to letter grade separately
            return np.clip(raw_score, 0.0, 100.0)
    
    def _extract_features(self, features: StudentFeatures) -> np.ndarray:
        """
        Extract and order features for model input.
        
        Args:
            features: StudentFeatures object
            
        Returns:
            Numpy array in feature order expected by model
        """
        feature_dict = features.dict()
        
        feature_vector = []
        for feature_name in self.FEATURE_NAMES:
            value = feature_dict.get(feature_name)
            if value is None:
                # Fill missing features with 0 or mean from training
                value = 0.0
            feature_vector.append(float(value))
        
        return np.array([feature_vector])
    
    def predict_expected_grade(self, features: StudentFeatures) -> PredictionOutput:
        """
        Predict expected final grade for a student in a course.
        
        Args:
            features: StudentFeatures vector
            
        Returns:
            PredictionOutput with expected grade and confidence
            
        Raises:
            ValueError: If model not loaded or inference fails
        """
        if "expected_grade" not in self.models:
            raise ValueError("Expected grade model not loaded")
        
        try:
            feature_vector = self._extract_features(features)
            
            # Run inference
            dmatrix = xgb.DMatrix(feature_vector)
            raw_prediction = self.models["expected_grade"].predict(dmatrix)[0]
            
            # Calibrate to 0-100 scale
            calibrated_score = self._calibrate_probability(raw_prediction, "expected_grade")
            
            # Convert to letter grade
            letter_grade = self._numeric_to_letter_grade(calibrated_score)
            
            # Confidence: based on feature completeness
            missing_features = sum(1 for v in feature_vector[0] if v == 0)
            confidence = max(0.5, 1.0 - (missing_features / len(self.FEATURE_NAMES)))
            
            logger.info(
                f"Predicted grade {letter_grade} (score {calibrated_score:.1f}) "
                f"for {features.student_id} in {features.course_id}"
            )
            
            return PredictionOutput(
                student_id=features.student_id,
                course_id=features.course_id,
                prediction_type="expected_grade",
                prediction_value=letter_grade.value,
                confidence_score=confidence,
                model_name="expected_grade",
                model_version=self.metadata["expected_grade"].get("version", "unknown"),
                generated_at=datetime.utcnow(),
                feature_set_hash=self._hash_features(feature_vector),
                raw_score=calibrated_score,
            )
        
        except Exception as e:
            logger.error(f"Expected grade prediction failed: {e}")
            raise
    
    def predict_completion(self, features: StudentFeatures) -> PredictionOutput:
        """
        Predict probability of course completion.
        
        Args:
            features: StudentFeatures vector
            
        Returns:
            PredictionOutput with completion probability
        """
        if "completion" not in self.models:
            raise ValueError("Completion model not loaded")
        
        try:
            feature_vector = self._extract_features(features)
            dmatrix = xgb.DMatrix(feature_vector)
            raw_prediction = self.models["completion"].predict(dmatrix)[0]
            
            completion_prob = self._calibrate_probability(raw_prediction, "completion")
            confidence = max(0.5, 1.0 - (sum(1 for v in feature_vector[0] if v == 0) / len(self.FEATURE_NAMES)))
            
            logger.info(
                f"Predicted completion {completion_prob:.2%} for {features.student_id}"
            )
            
            return PredictionOutput(
                student_id=features.student_id,
                course_id=features.course_id,
                prediction_type="completion",
                prediction_value=round(completion_prob, 3),
                confidence_score=confidence,
                model_name="completion",
                model_version=self.metadata["completion"].get("version", "unknown"),
                generated_at=datetime.utcnow(),
                feature_set_hash=self._hash_features(feature_vector),
                raw_score=completion_prob,
            )
        
        except Exception as e:
            logger.error(f"Completion prediction failed: {e}")
            raise
    
    def predict_risk(self, features: StudentFeatures) -> PredictionOutput:
        """
        Predict risk level (low, medium, high, critical).
        
        Args:
            features: StudentFeatures vector
            
        Returns:
            PredictionOutput with risk classification
        """
        if "risk" not in self.models:
            raise ValueError("Risk model not loaded")
        
        try:
            feature_vector = self._extract_features(features)
            dmatrix = xgb.DMatrix(feature_vector)
            raw_prediction = self.models["risk"].predict(dmatrix)[0]
            
            risk_score = self._calibrate_probability(raw_prediction, "risk")
            
            # Classify into risk buckets
            if risk_score >= 0.75:
                risk_level = RiskLevel.CRITICAL
            elif risk_score >= 0.50:
                risk_level = RiskLevel.HIGH
            elif risk_score >= 0.25:
                risk_level = RiskLevel.MEDIUM
            else:
                risk_level = RiskLevel.LOW
            
            confidence = max(0.5, 1.0 - (sum(1 for v in feature_vector[0] if v == 0) / len(self.FEATURE_NAMES)))
            
            logger.info(f"Predicted risk {risk_level.value} for {features.student_id}")
            
            return PredictionOutput(
                student_id=features.student_id,
                course_id=features.course_id,
                prediction_type="risk",
                prediction_value=risk_level.value,
                confidence_score=confidence,
                model_name="risk",
                model_version=self.metadata["risk"].get("version", "unknown"),
                generated_at=datetime.utcnow(),
                feature_set_hash=self._hash_features(feature_vector),
                raw_score=risk_score,
            )
        
        except Exception as e:
            logger.error(f"Risk prediction failed: {e}")
            raise
    
    def predict_all(self, features: StudentFeatures) -> Dict[str, PredictionOutput]:
        """
        Run all three predictions for a student in a course.
        
        Returns:
            Dict with keys: expected_grade, completion, risk
        """
        predictions = {}
        
        try:
            predictions["expected_grade"] = self.predict_expected_grade(features)
        except Exception as e:
            logger.error(f"Grade prediction failed: {e}")
        
        try:
            predictions["completion"] = self.predict_completion(features)
        except Exception as e:
            logger.error(f"Completion prediction failed: {e}")
        
        try:
            predictions["risk"] = self.predict_risk(features)
        except Exception as e:
            logger.error(f"Risk prediction failed: {e}")
        
        return predictions
    
    @staticmethod
    def _hash_features(feature_vector: np.ndarray) -> str:
        """Create hash of feature vector for audit trail."""
        import hashlib
        feature_bytes = feature_vector.tobytes()
        return hashlib.sha256(feature_bytes).hexdigest()