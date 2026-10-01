"""
Lumen Assignments Module - Fetch and parse assignment details and submissions.

Retrieves assignment objects, submission information, feedback, and status
from Brightspace API with data normalization.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from .lumen_client import LumenClient
from .lumen_exceptions import LumenAPIError


logger = logging.getLogger(__name__)


class LumenAssignments:
    """
    Manage assignment retrieval from Lumen/Brightspace.
    
    Handles:
    - Fetching assignments in course
    - Submission status and details
    - Assignment feedback and marks
    - Due dates and submission tracking
    - Data normalization
    """

    def __init__(self, client: LumenClient):
        """
        Initialize assignments manager.
        
        Args:
            client: Authenticated LumenClient instance
        """
        self.client = client
        logger.info("Lumen assignments manager initialized")

    def get_course_assignments(self, course_id: str) -> List[Dict[str, Any]]:
        """
        Fetch all assignments in a course.
        
        Args:
            course_id: Course org unit ID
            
        Returns:
            List of normalized assignment dictionaries
            
        Raises:
            LumenAPIError: If API call fails
        """
        endpoint = f"/d2l/api/le/1.55/dropbox/orgUnits/{course_id}/assignments"
        
        try:
            assignments_data = self.client.get_paginated(endpoint, page_size=100)
            
            normalized_assignments = [
                self._normalize_assignment(assignment)
                for assignment in assignments_data
            ]
            
            logger.info(f"Fetched {len(normalized_assignments)} assignments for course {course_id}")
            return normalized_assignments
        
        except Exception as e:
            logger.error(f"Failed to fetch assignments: {str(e)}")
            raise LumenAPIError(f"Failed to fetch assignments: {str(e)}")

    def get_assignment_details(
        self,
        course_id: str,
        assignment_id: str,
    ) -> Dict[str, Any]:
        """
        Fetch detailed information for a specific assignment.
        
        Args:
            course_id: Course org unit ID
            assignment_id: Assignment ID
            
        Returns:
            Normalized assignment details
        """
        endpoint = f"/d2l/api/le/1.55/dropbox/orgUnits/{course_id}/assignments/{assignment_id}"
        
        try:
            assignment_data = self.client.request("GET", endpoint)
            
            normalized = self._normalize_assignment(assignment_data)
            
            logger.info(f"Fetched details for assignment {assignment_id}")
            return normalized
        
        except Exception as e:
            logger.error(f"Failed to fetch assignment details: {str(e)}")
            raise LumenAPIError(f"Failed to fetch assignment details: {str(e)}")

    def get_assignment_submissions(
        self,
        course_id: str,
        assignment_id: str,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch submission(s) for an assignment.
        
        Args:
            course_id: Course org unit ID
            assignment_id: Assignment ID
            user_id: Optional specific user ID
            
        Returns:
            List of submission dictionaries
        """
        if user_id:
            endpoint = f"/d2l/api/le/1.55/dropbox/orgUnits/{course_id}/assignments/{assignment_id}/submissions/users/{user_id}"
        else:
            endpoint = f"/d2l/api/le/1.55/dropbox/orgUnits/{course_id}/assignments/{assignment_id}/submissions/mysubmissions"
        
        try:
            submissions_data = self.client.get_paginated(endpoint, page_size=100)
            
            normalized_submissions = [
                self._normalize_submission(submission)
                for submission in submissions_data
            ]
            
            logger.info(f"Fetched {len(normalized_submissions)} submissions for assignment {assignment_id}")
            return normalized_submissions
        
        except Exception as e:
            logger.error(f"Failed to fetch submissions: {str(e)}")
            raise LumenAPIError(f"Failed to fetch submissions: {str(e)}")

    def get_submission_details(
        self,
        course_id: str,
        assignment_id: str,
        submission_id: str,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch detailed submission information including feedback.
        
        Args:
            course_id: Course org unit ID
            assignment_id: Assignment ID
            submission_id: Submission ID
            user_id: Optional specific user ID
            
        Returns:
            Detailed submission information
        """
        if user_id:
            endpoint = f"/d2l/api/le/1.55/dropbox/orgUnits/{course_id}/assignments/{assignment_id}/submissions/users/{user_id}/feedback"
        else:
            endpoint = f"/d2l/api/le/1.55/dropbox/orgUnits/{course_id}/assignments/{assignment_id}/submissions/mysubmissions/{submission_id}/feedback"
        
        try:
            submission_data = self.client.request("GET", endpoint)
            
            return self._normalize_submission_detail(submission_data)
        
        except Exception as e:
            logger.error(f"Failed to fetch submission details: {str(e)}")
            raise LumenAPIError(f"Failed to fetch submission details: {str(e)}")

    def get_assignment_rubric(
        self,
        course_id: str,
        assignment_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch rubric information for an assignment if available.
        
        Args:
            course_id: Course org unit ID
            assignment_id: Assignment ID
            
        Returns:
            Rubric information or None if not available
        """
        endpoint = f"/d2l/api/le/1.55/dropbox/orgUnits/{course_id}/assignments/{assignment_id}/rubric"
        
        try:
            rubric_data = self.client.request("GET", endpoint)
            
            return {
                "assignment_id": assignment_id,
                "rubric": rubric_data,
                "synced_at": datetime.utcnow().isoformat(),
            }
        
        except Exception as e:
            logger.debug(f"No rubric available for assignment: {str(e)}")
            return None

    def get_class_assignments_summary(self, course_id: str) -> Dict[str, Any]:
        """
        Fetch summary statistics for all assignments in course.
        
        Args:
            course_id: Course org unit ID
            
        Returns:
            Summary statistics dictionary
        """
        try:
            assignments = self.get_course_assignments(course_id)
            
            now = datetime.utcnow()
            
            upcoming = [a for a in assignments if a.get("due_date") and self._parse_date(a["due_date"]) > now]
            overdue = [a for a in assignments if a.get("due_date") and self._parse_date(a["due_date"]) < now]
            submitted = [a for a in assignments if a.get("submitted_date")]
            
            return {
                "course_id": course_id,
                "total_assignments": len(assignments),
                "upcoming_count": len(upcoming),
                "overdue_count": len(overdue),
                "submitted_count": len(submitted),
                "pending_count": len(assignments) - len(submitted),
                "average_score": self._calculate_average_score(assignments),
                "synced_at": datetime.utcnow().isoformat(),
            }
        
        except Exception as e:
            logger.error(f"Failed to get assignments summary: {str(e)}")
            raise LumenAPIError(f"Failed to get assignments summary: {str(e)}")

    def _normalize_assignment(self, assignment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize raw assignment data from API.
        
        Args:
            assignment_data: Raw assignment from Brightspace
            
        Returns:
            Normalized assignment dictionary
        """
        return {
            "assignment_id": assignment_data.get("Id"),
            "name": assignment_data.get("Name", ""),
            "description": assignment_data.get("Description", ""),
            "due_date": self._parse_datetime(assignment_data.get("DueDate")),
            "is_hidden": assignment_data.get("IsHidden", False),
            "is_dropbox": assignment_data.get("IsDropbox", True),
            "grade_item_id": assignment_data.get("GradeItemId"),
            "max_points": assignment_data.get("MaxPoints"),
            "allow_submissions": assignment_data.get("AllowSubmissions", True),
            "allow_late_submissions": assignment_data.get("AllowLateSubmissions", False),
            "synced_at": datetime.utcnow().isoformat(),
        }

    def _normalize_submission(self, submission_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize raw submission data.
        
        Args:
            submission_data: Raw submission from Brightspace
            
        Returns:
            Normalized submission dictionary
        """
        return {
            "submission_id": submission_data.get("Id"),
            "user_id": submission_data.get("UserId"),
            "submission_date": self._parse_datetime(submission_data.get("SubmissionDate")),
            "submission_folder_id": submission_data.get("SubmissionFolderId"),
            "feedback_date": self._parse_datetime(submission_data.get("FeedbackDate")),
            "is_submitted": submission_data.get("IsSubmitted", False),
            "is_late": submission_data.get("IsLate", False),
            "attempt_count": submission_data.get("AttemptCount", 0),
            "synced_at": datetime.utcnow().isoformat(),
        }

    def _normalize_submission_detail(self, submission_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize detailed submission data with feedback.
        
        Args:
            submission_data: Detailed submission from Brightspace
            
        Returns:
            Normalized detailed submission
        """
        base_submission = self._normalize_submission(submission_data)
        
        base_submission.update({
            "grade_received": submission_data.get("GradeReceived"),
            "grade_percentage": submission_data.get("GradePercentage"),
            "feedback_text": submission_data.get("FeedbackText", ""),
            "feedback_html": submission_data.get("FeedbackHtml", ""),
            "files": submission_data.get("Files", []),
        })
        
        return base_submission

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

    def _parse_date(self, date_string: Optional[str]) -> Optional[datetime]:
        """Parse date string to datetime object."""
        if not date_string:
            return None
        
        try:
            return datetime.fromisoformat(date_string.replace("Z", "+00:00"))
        except Exception:
            return None

    def _calculate_average_score(self, assignments: List[Dict[str, Any]]) -> Optional[float]:
        """Calculate average score across assignments."""
        try:
            scores = [a for a in assignments if a.get("grade_received")]
            if not scores:
                return None
            
            total = sum(s["grade_received"] for s in scores)
            return round(total / len(scores), 2)
        except Exception:
            return None
