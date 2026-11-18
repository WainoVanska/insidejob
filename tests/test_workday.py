"""Workday adapter tests.

Fixtures are real `fetch()` results (2026-11-18): KONE's 13 jobs under the "Finland"
facet as returned, and NVIDIA's 3 Finland postings. The facet tree in `FACETS` mirrors the
shapes seen on both tenants (NVIDIA nests locations under locationMainGroup; KONE has a
top-level Country facet).
"""

import json

import httpx
import pytest

from insidejob.adapters import workday

NVIDIA = "nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
KONE = "kone.wd3.myworkdayjobs.com/Careers"

FACETS = [
    {
        "facetParameter": "Country",
        "descriptor": "Location Country",
        "values": [
            {"descriptor": "Sweden", "id": "se-id", "count": 9},
            {"descriptor": "Finland", "id": "kone-fi-id", "count": 13},
        ],
    },
    {
        "facetParameter": "locationMainGroup",
        "values": [
            {
                "facetParameter": "locationHierarchy1",
                "descriptor": "Locations",
                "values": [{"descriptor": "Germany", "id": "de-id", "count": 40}],
            }
        ],
    },
]

NVIDIA_FACETS = [
    {
        "facetParameter": "locationMainGroup",
        "values": [
            {
                "facetParameter": "locationHierarchy2",
                "descriptor": "Location Type",
                "values": [{"descriptor": "Remote", "id": "remote-id"}],
            },
            {
                "facetParameter": "locationHierarchy1",
                "descriptor": "Locations",
                "values": [{"descriptor": "Finland", "id": "nv-fi-id", "count": 3}],
            },
        ],
    }
]


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(workday, "PAGE_PAUSE", 0)


@pytest.mark.parametrize(
    ("board", "expected"),
    [
        (NVIDIA, ("nvidia.wd5.myworkdayjobs.com", "nvidia", "NVIDIAExternalCareerSite")),
        (f"https://{KONE}/", ("kone.wd3.myworkdayjobs.com", "kone", "Careers")),
        (
            "kone.wd3.myworkdayjobs.com/en-US/Careers",
            ("kone.wd3.myworkdayjobs.com", "kone", "Careers"),
        ),
    ],
)
def test_split_board(board, expected):
    assert workday.split_board(board) == expected


@pytest.mark.parametrize("board", ["kone", "example.com/Careers", "kone.wd3.myworkdayjobs.com"])
def test_bad_board(board):
    with pytest.raises(ValueError, match="workday board must look like"):
        workday.split_board(board)


def test_find_top_level_facet():
    assert workday.find_facet(FACETS, "Finland") == ("Country", "kone-fi-id")


def test_find_nested_facet_case_insensitive():
    assert workday.find_facet(NVIDIA_FACETS, "finland") == ("locationHierarchy1", "nv-fi-id")


def test_missing_facet_value():
    with pytest.raises(ValueError, match="no Workday facet value named 'Atlantis'"):
        workday.find_facet(FACETS, "Atlantis")


def test_parse_kone(load_fixture):
    jobs = workday.parse(load_fixture("workday_kone.json"), KONE, "KONE")
    assert len(jobs) == 13
    job = jobs[0]
    assert job.id == f"workday:{KONE}:R0666378-1"
    assert job.title == "Financial Controller"
    assert job.location == "Espoo, Finland"  # facet appended: KONE lists only the city
    assert (
        job.url
        == "https://kone.wd3.myworkdayjobs.com/Careers/job/Espoo/Financial-Controller_R0666378-1"
    )
    assert any(j.location == "Hyvinkää, Finland" for j in jobs)
    assert job.posted_at is None and job.description == ""


def test_parse_nvidia_locations(load_fixture):
    jobs = workday.parse(load_fixture("workday_nvidia.json"), NVIDIA, "NVIDIA")
    assert [j.location for j in jobs] == [
        "Finland, Helsinki",  # already names the facet: unchanged
        "Finland (2 locations)",
        "Finland (3 locations)",
    ]
    assert jobs[0].id == f"workday:{NVIDIA}:JR2029780"
    assert jobs[0].title == "System Software Engineering Intern - 2027"


def test_job_id_without_underscore_falls_back_to_path():
    raw = {"facet": "", "jobPostings": [{"title": "x", "externalPath": "/job/Espoo/Plain"}]}
    (job,) = workday.parse(raw, KONE, "KONE")
    assert job.id == f"workday:{KONE}:/job/Espoo/Plain"
    assert job.location == ""


def posting(n: int) -> dict:
    return {
        "title": f"Job {n}",
        "externalPath": f"/job/Espoo/Job-{n}_R{n}",
        "locationsText": "Espoo",
    }


def fake_workday(total: int, facets=FACETS):
    """Serve facets on the unfiltered call, then pages of the filtered result.

    Like the real API, an offset past the end repeats the first page instead of
    returning nothing.
    """
    calls = []
    all_postings = [posting(n) for n in range(total)]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read())
        calls.append(body)
        assert request.url.path == "/wday/cxs/kone/Careers/jobs"
        if not body["appliedFacets"]:
            assert body["limit"] == 1
            return httpx.Response(200, json={"total": 930, "facets": facets, "jobPostings": []})
        assert body["limit"] == 20
        start = body["offset"] if body["offset"] < total else 0
        page = all_postings[start : start + 20]
        return httpx.Response(200, json={"total": total, "jobPostings": page})

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_fetch_applies_facet_and_pages_until_total():
    client, calls = fake_workday(total=45)
    with client:
        raw = workday.fetch(client, KONE, {"facet": "Finland"})
    assert raw["facet"] == "Finland"
    assert len(raw["jobPostings"]) == 45
    assert calls[0]["appliedFacets"] == {}
    assert [c["offset"] for c in calls[1:]] == [0, 20, 40]
    assert all(c["appliedFacets"] == {"Country": ["kone-fi-id"]} for c in calls[1:])


def test_fetch_single_page():
    client, calls = fake_workday(total=13)
    with client:
        raw = workday.fetch(client, KONE, {"facet": "Finland"})
    assert len(raw["jobPostings"]) == 13
    assert len(calls) == 2  # facets + one page


def test_fetch_stops_at_max_pages(monkeypatch):
    monkeypatch.setattr(workday, "MAX_PAGES", 2)
    client, calls = fake_workday(total=500)
    with client:
        raw = workday.fetch(client, KONE, {"facet": "Finland"})
    assert len(raw["jobPostings"]) == 40
    assert len(calls) == 3


def test_fetch_requires_facet_option():
    with pytest.raises(ValueError, match="options.facet"):
        workday.fetch(httpx.Client(), KONE, {})


def test_fetch_unknown_facet_value():
    client, _ = fake_workday(total=1)
    with client, pytest.raises(ValueError, match="no Workday facet value"):
        workday.fetch(client, KONE, {"facet": "Atlantis"})


def test_fetch_rate_limit_raises():
    transport = httpx.MockTransport(lambda request: httpx.Response(429))
    with httpx.Client(transport=transport) as client, pytest.raises(httpx.HTTPStatusError):
        workday.fetch(client, KONE, {"facet": "Finland"})
