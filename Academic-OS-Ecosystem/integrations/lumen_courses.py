"""
Lumen Courses Module - Fetch and parse student course enrollments.

Retrieves active course offerings, course details, and enrollment information
from Brightspace API with data normalization and error handling.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from .lumen_client import LumenClient
from .lumen_exceptions import LumenAPIError


logger = logging.getLogger(__name__)


class LumenCourses:
    """
    Manage course retrieval from Lumen/Brightspace.
    
    Handles:
    - Fetching enrolled courses
    - Course detail retrieval
    - Course status and term information
    - Data normalization and validation
    """

    def __init__(self, client: LumenClient):
        """
        Initialize courses manager.
        
        Args:
            client: Authenticated LumenClient instance
        """
        self.client = client
        logger.info("Lumen courses manager initialized")

    def get_enrolled_courses(
        self,
        user_id: Optional[str] = None,
        is_active: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Fetch student's enrolled courses.
        
        Args:
            user_id: Optional specific user ID (defaults to current user)
            is_active: Only fetch active enrollments
            
        Returns:
            List of normalized course dictionaries
            
        Raises:
            LumenAPIError: If API call fails
        """
        # The student-context endpoint is used for every student sync. The
        # user-scoped enrollments route is an admin/instructor route and fails
        # for student tokens, so ``user_id`` is accepted for compatibility only.
        endpoint = "/d2l/api/le/1.55/enrollments/myenrollments/"

        try:
            courses_data = self.client.get_paginated(endpoint, page_size=100)

            normalized_courses = [
                self._normalize_course(course)
                for course in courses_data
            ]
            # Enrollments also list departments and semesters; keep course offerings.
            normalized_courses = [
                course for course in normalized_courses
                if course["course_id"] and course["course_type"] in (None, "", "Course Offering")
            ]

            logger.info(f"Fetched {len(normalized_courses)} enrolled courses")
            return normalized_courses
        
        except Exception as e:
            logger.error(f"Failed to fetch enrolled courses: {str(e)}")
            raise LumenAPIError(f"Failed to fetch enrolled courses: {str(e)}")

    def get_course_details(self, course_id: str) -> Dict[str, Any]:
        """
        Fetch detailed information for a specific course.
        
        Args:
            course_id: Course org unit ID
            
        Returns:
            Normalized course details dictionary
            
        Raises:
            LumenAPIError: If API call fails
        """
        endpoint = f"/d2l/api/le/1.55/orgUnits/{course_id}"
        
        try:
            course_data = self.client.request("GET", endpoint)
            
            normalized = self._normalize_course_details(course_data)
            
            logger.info(f"Fetched details for course {course_id}")
            return normalized
        
        except Exception as e:
            logger.error(f"Failed to fetch course details for {course_id}: {str(e)}")
            raise LumenAPIError(f"Failed to fetch course details: {str(e)}")

    def get_course_offering_info(self, course_id: str) -> Dict[str, Any]:
        """
        Fetch course offering metadata (term, section, etc).
        
        Args:
            course_id: Course org unit ID
            
        Returns:
            Course offering information
        """
        endpoint = f"/d2l/api/le/1.55/orgUnits/{course_id}/properties"
        
        try:
            offering_data = self.client.request("GET", endpoint)
            
            return {
                "course_id": course_id,
                "term_id": offering_data.get("OfferedTermId"),
                "section": offering_data.get("Section"),
                "credits": offering_data.get("Credits"),
                "max_students": offering_data.get("MaxStudents"),
                "enrollment_set_id": offering_data.get("EnrollmentSetId"),
            }
        
        except Exception as e:
            logger.error(f"Failed to fetch course offering info: {str(e)}")
            raise LumenAPIError(f"Failed to fetch course offering info: {str(e)}")

    def search_courses(
        self,
        search_term: str,
        search_type: str = "Name",
    ) -> List[Dict[str, Any]]:
        """
        Search for courses by name or code.
        
        Args:
            search_term: Search query
            search_type: Type of search (Name, Code, Instructor)
            
        Returns:
            List of matching courses
        """
        endpoint = "/d2l/api/le/1.55/orgUnits/"
        
        try:
            params = {
                "search": search_term,
                "searchType": search_type,
            }
            
            courses_data = self.client.request("GET", endpoint, params=params)
            
            items = courses_data.get("Items", [])
            normalized = [self._normalize_course(c) for c in items]
            
            logger.info(f"Found {len(normalized)} courses matching '{search_term}'")
            return normalized
        
        except Exception as e:
            logger.error(f"Course search failed: {str(e)}")
            raise LumenAPIError(f"Course search failed: {str(e)}")

    def get_course_instructors(self, course_id: str) -> List[Dict[str, str]]:
        """
        Fetch instructors for a course.
        
        Args:
            course_id: Course org unit ID
            
        Returns:
            List of instructor information
        """
        endpoint = f"/d2l/api/le/1.55/orgUnits/{course_id}/users/"
        
        try:
            params = {
                "roleId": "109",  # Instructor role ID in Brightspace
            }
            
            response = self.client.request("GET", endpoint, params=params)
            instructors = response.get("Items", [])
            
            normalized = [
                {
                    "user_id": inst.get("UserId"),
                    "first_name": inst.get("FirstName"),
                    "last_name": inst.get("LastName"),
                    "email": inst.get("Email"),
                }
                for inst in instructors
            ]
            
            logger.info(f"Fetched {len(normalized)} instructors for course {course_id}")
            return normalized
        
        except Exception as e:
            logger.error(f"Failed to fetch instructors: {str(e)}")
            raise LumenAPIError(f"Failed to fetch instructors: {str(e)}")

    def _normalize_course(self, course_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize raw course data from API.
        
        Args:
            course_data: Raw course data from Brightspace
            
        Returns:
            Normalized course dictionary
        """
        # Brightspace's enrollment list nests the org unit under "OrgUnit"
        # (MyOrgUnitInfo). Flat OrgUnitId/Name/Code shapes are kept as fallbacks.
        org_unit = course_data.get("OrgUnit") or {}
        org_unit_type = org_unit.get("Type") or {}
        raw_id = org_unit.get("Id", course_data.get("OrgUnitId"))
        return {
            "course_id": str(raw_id) if raw_id is not None else None,
            "course_code": org_unit.get("Code") or course_data.get("Code") or "",
            "course_name": org_unit.get("Name") or course_data.get("Name") or "",
            "course_type": org_unit_type.get("Code") or course_data.get("Type"),
            "is_active": course_data.get("IsActive", True),
            "start_date": self._parse_datetime(course_data.get("StartDate")),
            "end_date": self._parse_datetime(course_data.get("EndDate")),
            "synced_at": datetime.utcnow().isoformat(),
        }

    def _normalize_course_details(self, course_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize course details response."""
        base_info = self._normalize_course(course_data)
        
        base_info.update({
            "description": course_data.get("Description", ""),
            "department": course_data.get("DepartmentId"),
            "semester": course_data.get("SemesterId"),
            "instructor": course_data.get("InstructorId"),
        })
        
        return base_info

    def _parse_datetime(self, date_string: Optional[str]) -> Optional[str]:
        """
        Parse ISO datetime string from Brightspace.
        
        Args:
            date_string: ISO format date string
            
        Returns:
            ISO format datetime or None
        """
        if not date_string:
            return None
        
        try:
            # Brightspace returns ISO format: 2024-01-15T00:00:00.000Z
            dt = datetime.fromisoformat(date_string.replace("Z", "+00:00"))
            return dt.isoformat()
        except Exception:
            logger.warning(f"Failed to parse date: {date_string}")
            return date_string
