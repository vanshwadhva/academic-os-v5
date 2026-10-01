"""
Academic OS - Lumen Integration Package
=======================================

This package provides all integrations required to communicate with the
BITS Pilani Lumen LMS.

Modules
-------
lumen_client
    Primary API client.

lumen_auth
    Authentication and session management.

lumen_courses
    Course retrieval.

lumen_modules
    Module retrieval.

lumen_grades
    Grade retrieval.

lumen_assignments
    Assignment retrieval.

lumen_quizzes
    Quiz retrieval.

lumen_attendance
    Attendance retrieval.

lumen_calendar
    Calendar events and deadlines.

lumen_announcements
    Course announcements.

parser
    LMS response parsing utilities.

sync_manager
    Complete synchronization orchestrator.
"""

from .lumen_client import LumenClient
from .lumen_auth import LumenAuth, LumenAuthCallback
from .lumen_courses import LumenCourses
from .lumen_modules import LumenModules
from .lumen_grades import LumenGrades
from .lumen_assignments import LumenAssignments
from .lumen_quizzes import QuizService
from .sync_manager import LumenCredential, SyncManager

__version__ = "1.0.0"
__author__ = "Academic OS"
__license__ = "MIT"

__all__ = [
    "LumenClient",
    "LumenAuth",
    "LumenAuthCallback",
    "LumenCourses",
    "LumenModules",
    "LumenGrades",
    "LumenAssignments",
    "QuizService",
    "LumenCredential",
    "SyncManager",
]
