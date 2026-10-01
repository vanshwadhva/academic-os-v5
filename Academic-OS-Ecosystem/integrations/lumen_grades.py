"""
Lumen Grades Module - Fetch and parse student grades and marks.

Retrieves course grades, grade values, grade scheme information,
and grade calculations from Brightspace API.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from .lumen_client import LumenClient
from .lumen_exceptions import LumenAPIError


logger = logging.getLogger(__name__)


class LumenGrades:
    """
    Manage grade retrieval from Lumen/Brightspace.
    
    Handles:
    - Fetching course grades
    - Grade item retrieval
    - Grade calculations
    - Grade scheme information
    - Data normalization and validation
    """

    def __init__(self, client: LumenClient):
        """
        Initialize grades manager.
        
        Args:
            client: Authenticated LumenClient instance
        """
        self.client = client
        logger.info("Lumen grades manager initialized")

    def get_course_grade(
        self,
        course_id: str,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch final course grade for student.
        
        Args:
            course_id: Course org unit ID
            user_id: Optional specific user ID
            
        Returns:
            Normalized course grade dictionary
            
        Raises:
            LumenAPIError: If API call fails
        """
        if user_id:
            endpoint = f"/d2l/api/le/1.55/grades/orgUnits/{course_id}/users/{user_id}"
        else:
            endpoint = f"/d2l/api/le/1.55/grades/orgUnits/{course_id}/myGradeValues"
        
        try:
            grade_data = self.client.request("GET", endpoint)
            
            normalized = self._normalize_course_grade(grade_data)
            
            logger.info(f"Fetched course grade for course {course_id}")
            return normalized
        
        except Exception as e:
            logger.error(f"Failed to fetch course grade: {str(e)}")
            raise LumenAPIError(f"Failed to fetch course grade: {str(e)}")

    def get_grade_items(self, course_id: str) -> List[Dict[str, Any]]:
        """
        Fetch all gradeable items (assignments, quizzes, etc) in a course.
        
        Args:
            course_id: Course org unit ID
            
        Returns:
            List of normalized grade item dictionaries
            
        Raises:
            LumenAPIError: If API call fails
        """
        endpoint = f"/d2l/api/le/1.55/grades/orgUnits/{course_id}/gradeitems"
        
        try:
            items_data = self.client.get_paginated(endpoint, page_size=100)
            
            normalized_items = [
                self._normalize_grade_item(item)
                for item in items_data
            ]
            
            logger.info(f"Fetched {len(normalized_items)} grade items for course {course_id}")
            return normalized_items
        
        except Exception as e:
            logger.error(f"Failed to fetch grade items: {str(e)}")
            raise LumenAPIError(f"Failed to fetch grade items: {str(e)}")

    def get_grade_values(
        self,
        course_id: str,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch all grade values (actual scores) for student.
        
        Args:
            course_id: Course org unit ID
            user_id: Optional specific user ID
            
        Returns:
            List of normalized grade value dictionaries
        """
        if user_id:
            endpoint = f"/d2l/api/le/1.55/grades/orgUnits/{course_id}/users/{user_id}/grades"
        else:
            endpoint = f"/d2l/api/le/1.55/grades/orgUnits/{course_id}/myGradeValues"
        
        try:
            grades_data = self.client.get_paginated(endpoint, page_size=100)
            
            normalized_grades = [
                self._normalize_grade_value(grade)
                for grade in grades_data
            ]
            
            logger.info(f"Fetched {len(normalized_grades)} grade values for course {course_id}")
            return normalized_grades
        
        except Exception as e:
            logger.error(f"Failed to fetch grade values: {str(e)}")
            raise LumenAPIError(f"Failed to fetch grade values: {str(e)}")

    def get_grade_scheme(self, course_id: str) -> Dict[str, Any]:
        """
        Fetch grading scheme for course (letter grades, scales, etc).
        
        Args:
            course_id: Course org unit ID
            
        Returns:
            Grade scheme information
        """
        endpoint = f"/d2l/api/le/1.55/grades/orgUnits/{course_id}/schemes"
        
        try:
            scheme_data = self.client.request("GET", endpoint)
            
            return {
                "course_id": course_id,
                "scheme": scheme_data,
                "synced_at": datetime.utcnow().isoformat(),
            }
        
        except Exception as e:
            logger.error(f"Failed to fetch grade scheme: {str(e)}")
            raise LumenAPIError(f"Failed to fetch grade scheme: {str(e)}")

    def get_grade_statistics(
        self,
        course_id: str,
        grade_item_id: str,
    ) -> Dict[str, Any]:
        """
        Fetch statistics for a grade item (mean, median, etc).
        
        Args:
            course_id: Course org unit ID
            grade_item_id: Grade item ID
            
        Returns:
            Grade statistics dictionary
        """
        endpoint = f"/d2l/api/le/1.55/grades/orgUnits/{course_id}/gradeitems/{grade_item_id}/statistics"
        
        try:
            stats_data = self.client.request("GET", endpoint)
            
            return {
                "grade_item_id": grade_item_id,
                "mean": stats_data.get("Mean"),
                "median": stats_data.get("Median"),
                "std_dev": stats_data.get("StandardDeviation"),
                "min": stats_data.get("Minimum"),
                "max": stats_data.get("Maximum"),
                "completion_rate": stats_data.get("CompletionRate"),
                "synced_at": datetime.utcnow().isoformat(),
            }
        
        except Exception as e:
            logger.error(f"Failed to fetch grade statistics: {str(e)}")
            raise LumenAPIError(f"Failed to fetch grade statistics: {str(e)}")

    def calculate_weighted_grade(
        self,
        grade_items: List[Dict[str, Any]],
        grade_values: List[Dict[str, Any]],
    ) -> Optional[float]:
        """
        Calculate weighted final grade from items and values.
        
        Args:
            grade_items: List of grade items with weights
            grade_values: List of grade values with scores
            
        Returns:
            Calculated weighted grade or None if insufficient data
        """
        try:
            # Create item lookup
            items_by_id = {item["grade_item_id"]: item for item in grade_items}
            
            total_weighted = 0.0
            total_weight = 0.0
            
            for grade in grade_values:
                item_id = grade.get("grade_item_id")
                item = items_by_id.get(item_id)
                
                if not item or grade.get("numeric_grade") is None:
                    continue
                
                score = grade["numeric_grade"]
                weight = item.get("weight", 1.0)
                max_score = item.get("max_points", 100)
                
                # Calculate percentage
                percentage = (score / max_score * 100) if max_score > 0 else 0
                
                total_weighted += percentage * weight
                total_weight += weight
            
            if total_weight == 0:
                return None
            
            calculated_grade = total_weighted / total_weight
            logger.info(f"Calculated weighted grade: {calculated_grade:.2f}")
            return round(calculated_grade, 2)
        
        except Exception as e:
            logger.error(f"Grade calculation failed: {str(e)}")
            return None

    def _normalize_course_grade(self, grade_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize raw course grade data.
        
        Args:
            grade_data: Raw grade data from Brightspace
            
        Returns:
            Normalized course grade dictionary
        """
        return {
            "user_id": grade_data.get("UserId"),
            "numeric_grade": grade_data.get("FinalGrade"),
            "letter_grade": grade_data.get("FinalLetterGrade"),
            "points_earned": grade_data.get("PointsEarned"),
            "points_possible": grade_data.get("PointsPossible"),
            "percentage": self._calculate_percentage(
                grade_data.get("PointsEarned"),
                grade_data.get("PointsPossible"),
            ),
            "grade_status": grade_data.get("GradeStatus"),
            "last_modified": self._parse_datetime(grade_data.get("LastModifiedDate")),
            "synced_at": datetime.utcnow().isoformat(),
        }

    def _normalize_grade_item(self, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize raw grade item data.
        
        Args:
            item_data: Raw grade item from Brightspace
            
        Returns:
            Normalized grade item dictionary
        """
        return {
            "grade_item_id": item_data.get("GradeItemId"),
            "name": item_data.get("Name", ""),
            "type": item_data.get("Type"),
            "max_points": item_data.get("MaxPoints"),
            "is_bonus": item_data.get("IsBonus", False),
            "is_hidden": item_data.get("IsHidden", False),
            "weight": item_data.get("Weight", 1.0),
            "due_date": self._parse_datetime(item_data.get("DueDate")),
            "category": item_data.get("CategoryId"),
            "synced_at": datetime.utcnow().isoformat(),
        }

    def _normalize_grade_value(self, grade_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize raw grade value data.
        
        Args:
            grade_data: Raw grade value from Brightspace
            
        Returns:
            Normalized grade value dictionary
        """
        numeric_grade = grade_data.get("NumericGrade")
        max_points = grade_data.get("MaxPoints")
        
        percentage = self._calculate_percentage(numeric_grade, max_points)
        
        return {
            "grade_item_id": grade_data.get("GradeItemId"),
            "numeric_grade": numeric_grade,
            "text_grade": grade_data.get("TextGrade", ""),
            "max_points": max_points,
            "percentage": percentage,
            "points_earned": numeric_grade,
            "submitted_date": self._parse_datetime(grade_data.get("SubmittedDate")),
            "graded_date": self._parse_datetime(grade_data.get("GradedDate")),
            "feedback": grade_data.get("Feedback", ""),
            "is_late": grade_data.get("IsLate", False),
            "synced_at": datetime.utcnow().isoformat(),
        }

    def _calculate_percentage(
        self,
        points: Optional[float],
        max_points: Optional[float],
    ) -> Optional[float]:
        """Calculate percentage from points."""
        if points is None or max_points is None or max_points == 0:
            return None
        
        percentage = (points / max_points) * 100
        return round(percentage, 2)

    def _parse_datetime(self, date_string: Optional[str]) -> Optional[str]:
        """Parse ISO datetime string from Brightspace."""
        if not date_string:
            return None
        
        try:
            dt = datetime.fromisoformat(date_string.replace("Z", "+00:00"))
            return dt.isoformat()
        except Exception:
            logger.warning(f"Failed to parse date: {date_string}")
            return date_string
