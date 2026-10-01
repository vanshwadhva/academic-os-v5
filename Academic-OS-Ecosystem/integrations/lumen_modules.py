"""
Lumen Modules Module - Fetch and track module/content completion.

Retrieves course modules, content items, and completion status from
Brightspace API with normalization and progress calculation.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from .lumen_client import LumenClient
from .lumen_exceptions import LumenAPIError


logger = logging.getLogger(__name__)


class LumenModules:
    """
    Manage module and content retrieval from Lumen/Brightspace.
    
    Handles:
    - Fetching course modules/topics
    - Content item retrieval
    - Module completion tracking
    - Content completion status
    - Progress calculation
    """

    def __init__(self, client: LumenClient):
        """
        Initialize modules manager.
        
        Args:
            client: Authenticated LumenClient instance
        """
        self.client = client
        logger.info("Lumen modules manager initialized")

    def get_course_modules(self, course_id: str) -> List[Dict[str, Any]]:
        """
        Fetch all modules/topics in a course.
        
        Args:
            course_id: Course org unit ID
            
        Returns:
            List of normalized module dictionaries
            
        Raises:
            LumenAPIError: If API call fails
        """
        endpoint = f"/d2l/api/le/1.55/content/orgUnits/{course_id}/toc"
        
        try:
            modules_data = self.client.get_paginated(endpoint, page_size=100)
            
            normalized_modules = [
                self._normalize_module(module)
                for module in modules_data
            ]
            # The TOC can contain both folders (Type 0) and learner-facing
            # topics (Type 1). Count the topics as lectures when the tenant
            # supplies type information; retain legacy/untyped responses.
            typed_topics = [
                module for module in normalized_modules
                if str(module.get("module_type")).lower() in {"1", "topic"}
            ]
            if typed_topics:
                normalized_modules = typed_topics
            
            logger.info(f"Fetched {len(normalized_modules)} modules for course {course_id}")
            return normalized_modules
        
        except Exception as e:
            logger.error(f"Failed to fetch modules for course {course_id}: {str(e)}")
            raise LumenAPIError(f"Failed to fetch course modules: {str(e)}")

    def get_course_topic_progress(
        self,
        course_id: str,
        user_id: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Return per-topic learner progress keyed by the Brightspace topic ID."""
        endpoint = f"/d2l/api/le/1.55/{course_id}/content/userprogress/"
        params = {"userId": user_id} if user_id else None

        try:
            items = self.client.get_paginated(
                endpoint,
                page_size=100,
                max_pages=100,
                query_params=params,
            )
        except Exception as exc:
            logger.warning("Could not fetch per-topic progress for course %s: %s", course_id, exc)
            raise LumenAPIError(f"Failed to fetch per-topic progress: {exc}") from exc

        progress_by_topic = {}
        for item in items:
            topic_id = item.get("ObjectId") or item.get("TopicId") or item.get("ContentId")
            if topic_id is not None:
                progress_by_topic[str(topic_id)] = item
        return progress_by_topic

    @staticmethod
    def apply_topic_progress(
        modules: List[Dict[str, Any]],
        progress_by_topic: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Attach visited, read, completed, and time-spent state to each topic."""
        enriched = []
        for module in modules:
            topic_id = module.get("topic_id")
            state = progress_by_topic.get(str(topic_id), {}) if topic_id is not None else {}
            enriched.append({
                **module,
                "visited": bool(state.get("Visited", state.get("visited", False))),
                "is_read": bool(state.get("IsRead", state.get("is_read", False))),
                "completed": bool(state.get("Completed", state.get("IsCompleted", state.get("completed", False)))),
                "last_visited": state.get("LastVisited") or state.get("last_visited"),
                "completion_date": state.get("CompletedDate") or state.get("completion_date"),
                "num_visits": int(state.get("NumVisits") or state.get("num_visits") or 0),
                "total_time_seconds": int(state.get("TotalTime") or state.get("total_time_seconds") or 0),
            })
        return enriched

    def get_module_details(self, course_id: str, topic_id: str) -> Dict[str, Any]:
        """
        Fetch detailed information for a specific module/topic.
        
        Args:
            course_id: Course org unit ID
            topic_id: Topic/module ID
            
        Returns:
            Normalized module details
        """
        endpoint = f"/d2l/api/le/1.55/content/orgUnits/{course_id}/topics/{topic_id}"
        
        try:
            module_data = self.client.request("GET", endpoint)
            
            normalized = self._normalize_module(module_data)
            
            logger.info(f"Fetched details for module {topic_id} in course {course_id}")
            return normalized
        
        except Exception as e:
            logger.error(f"Failed to fetch module details: {str(e)}")
            raise LumenAPIError(f"Failed to fetch module details: {str(e)}")

    def get_module_contents(
        self,
        course_id: str,
        topic_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Fetch all content items within a module/topic.
        
        Args:
            course_id: Course org unit ID
            topic_id: Topic/module ID
            
        Returns:
            List of content items
        """
        endpoint = f"/d2l/api/le/1.55/content/orgUnits/{course_id}/topics/{topic_id}/children"
        
        try:
            contents_data = self.client.get_paginated(endpoint, page_size=100)
            
            normalized_contents = [
                self._normalize_content_item(item)
                for item in contents_data
            ]
            
            logger.info(f"Fetched {len(normalized_contents)} content items for module {topic_id}")
            return normalized_contents
        
        except Exception as e:
            logger.error(f"Failed to fetch module contents: {str(e)}")
            raise LumenAPIError(f"Failed to fetch module contents: {str(e)}")

    def get_content_completion(
        self,
        course_id: str,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch content completion status for course or user.
        
        Args:
            course_id: Course org unit ID
            user_id: Optional specific user ID
            
        Returns:
            Content completion data with progress
        """
        if user_id:
            endpoint = f"/d2l/api/le/1.55/content/orgUnits/{course_id}/users/{user_id}/completion"
        else:
            endpoint = f"/d2l/api/le/1.55/content/orgUnits/{course_id}/mycompletion"
        
        try:
            completion_data = self.client.request("GET", endpoint)
            completion_info = self._normalize_completion_info(completion_data)
            
            return {
                "course_id": course_id,
                "user_id": user_id,
                "completion_info": completion_info,
                "raw_completion_info": completion_data,
                "synced_at": datetime.utcnow().isoformat(),
            }
        
        except Exception as e:
            logger.error(f"Failed to fetch content completion: {str(e)}")
            raise LumenAPIError(f"Failed to fetch content completion: {str(e)}")

    def get_course_completion(
        self,
        course_id: str,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch overall course completion status.
        
        Args:
            course_id: Course org unit ID
            user_id: Optional specific user ID
            
        Returns:
            Course completion percentage and details
        """
        if user_id:
            endpoint = f"/d2l/api/le/1.55/enrollments/orgUnits/{course_id}/users/{user_id}"
        else:
            endpoint = f"/d2l/api/le/1.55/enrollments/myenrollments/{course_id}"
        
        try:
            enrollment_data = self.client.request("GET", endpoint)
            
            # Extract completion percentage if available
            completion_percent = enrollment_data.get("CompletionPercent")
            
            return {
                "course_id": course_id,
                "user_id": user_id,
                "completion_percent": completion_percent,
                "is_completed": enrollment_data.get("IsCompleted", False),
                "enrollment_status": enrollment_data.get("EnrollmentStatus"),
                "synced_at": datetime.utcnow().isoformat(),
            }
        
        except Exception as e:
            logger.error(f"Failed to fetch course completion: {str(e)}")
            raise LumenAPIError(f"Failed to fetch course completion: {str(e)}")

    def calculate_module_progress(
        self,
        modules: List[Dict[str, Any]],
        completion_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Calculate progress metrics from module data.
        
        Args:
            modules: List of modules
            completion_data: Completion status data
            
        Returns:
            Progress metrics dictionary
        """
        total_modules = len(modules)
        
        # Count completed modules (completion_data structure varies by instance)
        info = completion_data.get("completion_info", completion_data)
        completed = int(info.get("CompletedItems") or info.get("completed_items") or 0)
        total_from_completion = int(info.get("TotalItems") or info.get("total_items") or 0)
        if total_from_completion > total_modules:
            total_modules = total_from_completion
        
        if total_modules == 0:
            progress_percent = 0
        else:
            progress_percent = int((completed / total_modules) * 100)
        
        return {
            "total_modules": total_modules,
            "completed_modules": completed,
            "remaining_modules": total_modules - completed,
            "progress_percent": progress_percent,
        }

    def get_progress_snapshot(self, course_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Fetch modules and completion data, then return one normalized progress snapshot."""
        modules = self.get_course_modules(course_id)
        completion = self.get_content_completion(course_id, user_id=user_id)
        progress = self.calculate_module_progress(modules, completion)
        progress.update(
            {
                "course_id": course_id,
                "user_id": user_id,
                "modules": modules,
                "completion_info": completion.get("completion_info", {}),
                "synced_at": datetime.utcnow().isoformat(),
            }
        )
        return progress

    def _normalize_module(self, module_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize raw module data from API.
        
        Args:
            module_data: Raw module data from Brightspace
            
        Returns:
            Normalized module dictionary
        """
        return {
            "topic_id": module_data.get("TopicId") or module_data.get("Id") or module_data.get("ObjectId"),
            "title": module_data.get("Title", ""),
            "description": module_data.get("Description", ""),
            "module_type": module_data.get("Type"),
            "available": module_data.get("IsAvailable", True),
            "published": module_data.get("IsPublished", True),
            "sequence": module_data.get("Sequence"),
            "parent_topic_id": module_data.get("ParentTopicId"),
            "last_modified": self._parse_datetime(module_data.get("LastModifiedDate")),
            "synced_at": datetime.utcnow().isoformat(),
        }

    def _normalize_content_item(self, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize raw content item data.
        
        Args:
            item_data: Raw content item from Brightspace
            
        Returns:
            Normalized content item dictionary
        """
        return {
            "content_id": item_data.get("ContentId"),
            "content_type": item_data.get("ContentType"),
            "title": item_data.get("Title", ""),
            "description": item_data.get("Description", ""),
            "url": item_data.get("Url"),
            "available": item_data.get("IsAvailable", True),
            "published": item_data.get("IsPublished", True),
            "has_completion": item_data.get("HasCompletion", False),
            "is_trackable": item_data.get("IsTrackable", False),
            "last_modified": self._parse_datetime(item_data.get("LastModifiedDate")),
            "synced_at": datetime.utcnow().isoformat(),
        }

    def _normalize_completion_info(self, completion_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize the different Brightspace completion shapes seen across tenants."""
        if not isinstance(completion_data, dict):
            return {"CompletedItems": 0, "TotalItems": 0, "Items": []}

        items = (
            completion_data.get("Items")
            or completion_data.get("CompletionData")
            or completion_data.get("Modules")
            or completion_data.get("Topics")
            or []
        )
        total = (
            completion_data.get("TotalItems")
            or completion_data.get("TotalCount")
            or completion_data.get("Total")
            or len(items)
        )
        completed = (
            completion_data.get("CompletedItems")
            or completion_data.get("CompletedCount")
            or completion_data.get("Completed")
        )

        if completed is None and items:
            completed = sum(
                1
                for item in items
                if item.get("IsCompleted")
                or item.get("Completed")
                or str(item.get("Status", "")).lower() == "completed"
            )

        return {
            "CompletedItems": int(completed or 0),
            "TotalItems": int(total or 0),
            "Items": items,
        }

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
