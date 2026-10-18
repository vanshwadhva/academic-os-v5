"""
Lumen response parsing against the Brightspace shapes documented at
docs.valence.desire2learn.com (enrollments: OrgUnit nested; TOC: nested Modules/Topics).
"""

import json
import re
from datetime import datetime, timedelta, timezone

import pytest
import responses

from integrations.lumen_client import LumenClient
from integrations.lumen_courses import LumenCourses
from integrations.lumen_modules import LumenModules
from integrations.sync_manager import LumenCredential, SyncManager

BASE = "https://lumen.test.example"

ENROLLMENTS = {
    "Items": [
        {
            "OrgUnit": {
                "Id": 6606,
                "Name": "Data Stores & Pipelines",
                "Code": "DSP-101",
                "Type": {"Id": 3, "Code": "Course Offering", "Name": "Course Offering"},
            },
            "Access": {"IsActive": True},
            "PinDate": None,
        },
        {
            "OrgUnit": {
                "Id": 1,
                "Name": "BITS Pilani Digital",
                "Code": "ROOT",
                "Type": {"Id": 1, "Code": "Organization", "Name": "Organization"},
            },
            "Access": {"IsActive": True},
            "PinDate": None,
        },
    ],
    "PagingInfo": {"HasMoreItems": False, "Bookmark": None},
}

TOC = {
    "Modules": [
        {
            "ModuleId": 101,
            "Title": "Week 1",
            "Modules": [],
            "Topics": [
                {"TopicId": 1001, "Title": "Lecture 1.1", "Url": "/l1", "ActivityType": 1},
                {"TopicId": 1002, "Title": "Lecture 1.2", "Url": "/l2", "ActivityType": 1},
            ],
        },
        {
            "ModuleId": 102,
            "Title": "Week 2",
            "Modules": [
                {
                    "ModuleId": 103,
                    "Title": "Part B",
                    "Modules": [],
                    "Topics": [{"TopicId": 1004, "Title": "Lecture 2.2", "Url": "/l4"}],
                }
            ],
            "Topics": [
                {"TopicId": 1003, "Title": "Lecture 2.1", "Url": "/l3"},
                {"TopicId": 1005, "Title": "Hidden lecture", "IsHidden": True},
            ],
        },
    ]
}


def _client() -> LumenClient:
    client = LumenClient(BASE, "client", "secret")
    client.set_access_token("token", 3600)
    return client


# ---------------------------------------------------------------------------
# Course enrollment parsing
# ---------------------------------------------------------------------------

def test_course_id_is_read_from_nested_org_unit():
    courses = LumenCourses(_client())._normalize_course(ENROLLMENTS["Items"][0])
    assert courses["course_id"] == "6606"
    assert courses["course_name"] == "Data Stores & Pipelines"
    assert courses["course_code"] == "DSP-101"
    assert courses["course_type"] == "Course Offering"


def test_missing_id_is_none_not_the_string_none():
    normalized = LumenCourses(_client())._normalize_course({"OrgUnit": {"Name": "x"}})
    assert normalized["course_id"] is None


@responses.activate
def test_enrolled_courses_keep_only_course_offerings():
    responses.add(
        responses.GET,
        re.compile(re.escape(BASE) + r"/d2l/api/le/1.55/enrollments/myenrollments/.*"),
        json=ENROLLMENTS,
    )
    courses = LumenCourses(_client()).get_enrolled_courses()
    assert [c["course_id"] for c in courses] == ["6606"]


@responses.activate
def test_enrolled_courses_always_use_student_context_endpoint():
    responses.add(
        responses.GET,
        re.compile(re.escape(BASE) + r"/d2l/api/le/1.55/enrollments/myenrollments/.*"),
        json=ENROLLMENTS,
    )
    LumenCourses(_client()).get_enrolled_courses(user_id="555")
    assert responses.calls[0].request.url.startswith(BASE + "/d2l/api/le/1.55/enrollments/myenrollments/")


# ---------------------------------------------------------------------------
# TOC parsing
# ---------------------------------------------------------------------------

@responses.activate
def test_toc_yields_every_visible_lecture_with_its_topic_id():
    responses.add(
        responses.GET,
        re.compile(re.escape(BASE) + r"/d2l/api/le/1.55/content/orgUnits/6606/toc.*"),
        json=TOC,
    )
    lectures = LumenModules(_client()).get_course_modules("6606")
    ids = [lecture["topic_id"] for lecture in lectures]
    # Reading order: a week's own topics, then its nested sub-module's topics; hidden topics excluded.
    assert ids == ["1001", "1002", "1003", "1004"]
    assert all(lecture["module_type"] == "1" for lecture in lectures)
    assert lectures[2]["module_path"] == "Week 2"
    assert lectures[3]["module_path"] == "Week 2 > Part B"


def test_flatten_toc_handles_empty_and_non_dict_input():
    modules = LumenModules(_client())
    assert modules._flatten_toc(None) == []
    assert modules._flatten_toc({}) == []


# ---------------------------------------------------------------------------
# Sync behaviour
# ---------------------------------------------------------------------------

def test_token_is_seeded_with_remaining_lifetime_not_original_lifetime():
    issued = datetime.now(timezone.utc) - timedelta(seconds=3240)
    credential = LumenCredential(
        access_token="token", expires_in=3600, refresh_token=None, issued_at=issued.isoformat()
    )
    client = SyncManager.from_env()._build_client(credential)
    seconds_left = (client._token_expires_at - datetime.utcnow()).total_seconds()
    assert 300 <= seconds_left <= 365  # actual remaining ~360s, not the 3300s the old code claimed


def test_expired_credential_without_refresh_token_is_not_usable():
    issued = datetime.now(timezone.utc) - timedelta(seconds=4000)
    credential = LumenCredential(
        access_token="token", expires_in=3600, refresh_token=None, issued_at=issued.isoformat()
    )
    assert credential.remaining_seconds() == 0
    assert credential.is_expired() is True


def test_export_refreshed_tokens_is_none_when_no_refresh_happened():
    assert _client().export_refreshed_tokens() is None


@responses.activate
def test_full_sync_for_student_builds_courses_and_lectures_without_phantom_course():
    def fake(request):
        path = request.url.split("?")[0].replace(BASE, "")
        if path.endswith("/enrollments/myenrollments/"):
            return 200, {}, json.dumps(ENROLLMENTS)
        if path.endswith("/content/orgUnits/6606/toc"):
            return 200, {}, json.dumps(TOC)
        return 404, {}, "{}"

    responses.add_callback(responses.GET, re.compile(re.escape(BASE) + r".*"), callback=fake)
    credential = LumenCredential(
        access_token="token", expires_in=3600, refresh_token=None,
        issued_at=datetime.now(timezone.utc).isoformat(),
    )
    payload = SyncManager.from_env().run_full_sync("student-x", credential).to_dashboard_payload()

    assert [c["course_id"] for c in payload["courses"]] == ["6606"]
    course = payload["courses"][0]
    assert course["course_name"] == "Data Stores & Pipelines"
    assert course["modules_total"] == 4
    assert all(m["topic_id"] for m in course["modules"])
    assert all(c["course_id"] != "None" for c in payload["courses"])


@responses.activate
def test_lecture_list_survives_a_missing_completion_endpoint():
    def fake(request):
        path = request.url.split("?")[0].replace(BASE, "")
        if path.endswith("/content/orgUnits/6606/toc"):
            return 200, {}, json.dumps(TOC)
        return 404, {}, "{}"

    responses.add_callback(responses.GET, re.compile(re.escape(BASE) + r".*"), callback=fake)
    from integrations.sync_manager import CourseSnapshot, SyncResult, SyncStatus, SyncTrigger, _utcnow

    result = SyncResult(
        sync_job_id="job", student_id="s", correlation_id="c", status=SyncStatus.RUNNING,
        trigger=SyncTrigger.MANUAL, started_at=_utcnow(),
    )
    snapshot = CourseSnapshot(course_id="6606", course_name="DSP", course_code="DSP-101")
    SyncManager.from_env()._sync_course_domains(_client(), snapshot, result)
    assert len(snapshot.modules) == 4
    assert any(key.startswith("module_completion:") for key in result.domain_errors)


def test_sync_result_serialisation_never_contains_tokens():
    from integrations.sync_manager import SyncResult, SyncStatus, SyncTrigger, _utcnow

    result = SyncResult(
        sync_job_id="job", student_id="s", correlation_id="c", status=SyncStatus.SUCCESS,
        trigger=SyncTrigger.MANUAL, started_at=_utcnow(),
        refreshed_credential=LumenCredential(access_token="SECRET-ACCESS", expires_in=60),
    )
    assert "SECRET-ACCESS" not in str(result.to_dashboard_payload())
    assert "SECRET-ACCESS" not in str(result.to_dict())


@pytest.mark.parametrize("bad_id", [None, ""])
def test_courses_without_ids_are_skipped_by_sync(bad_id):
    from integrations.sync_manager import CourseSnapshot  # noqa: F401 - import guards the path

    manager = SyncManager.from_env()
    seen = []
    manager._sync_course_domains = lambda client, snapshot, result: seen.append(snapshot.course_id)

    class Stub:
        def get_enrolled_courses(self, user_id=None):
            return [{"course_id": bad_id, "course_name": "x", "course_code": "y"}]

    import integrations.sync_manager as sm

    original = sm.LumenCourses
    sm.LumenCourses = lambda client: Stub()
    try:
        from integrations.sync_manager import SyncResult, SyncStatus, SyncTrigger, _utcnow

        result = SyncResult(
            sync_job_id="job", student_id="s", correlation_id="c", status=SyncStatus.RUNNING,
            trigger=SyncTrigger.MANUAL, started_at=_utcnow(),
        )
        manager._sync_all_courses(_client(), result)
    finally:
        sm.LumenCourses = original
    assert seen == []
    assert result.courses == []
