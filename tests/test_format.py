from datetime import date

from insidejob.format import detail_parts, fi_date, plain, score_text
from insidejob.models import Employment, Workplace
from insidejob.rank import DEFAULT_RANK, Rank, max_score, score
from tests.helpers import make_job


def test_fi_date_has_no_zero_padding():
    assert fi_date(date(2027, 1, 5)) == "5.1.2027"


def test_known_details_in_order():
    job = make_job(
        workplace=Workplace.HYBRID,
        employment=Employment.INTERNSHIP,
        start="Jun 2027",
        deadline=date(2027, 1, 15),
    )
    assert detail_parts(job) == [
        "Helsinki, Finland",
        "hybrid",
        "internship",
        "start Jun 2027",
        "apply by 15.1.2027",
    ]


def test_inferred_values_are_marked():
    job = make_job(workplace=Workplace.HYBRID, start="Jun 2027", inferred={"start"})
    assert detail_parts(job) == ["Helsinki, Finland", "hybrid", "~start Jun 2027"]


def test_unknown_values_are_left_out():
    assert detail_parts(make_job(location="")) == []


def test_plain_two_lines():
    text = plain(make_job())
    assert text == "Acme – Summer Trainee\n    Helsinki, Finland · https://example.com/1"


def test_icons_prefix_each_detail():
    job = make_job(workplace=Workplace.REMOTE, start="Jun 2027", inferred={"start"})
    assert detail_parts(job, icons=True) == [
        "📍 Helsinki, Finland",
        "🏢 remote",
        "🗓️ ~starts Jun 2027",
    ]


def test_score_text_shows_the_maximum_when_known():
    assert score_text(Rank(9.5, 2, (), 13)) == "9.5 / 13"
    assert score_text(Rank(6, 2)) == "6"


def test_plain_with_rank():
    lines = plain(make_job(), Rank(6, 2, ("intern +3", "Helsinki +3"), 13)).splitlines()
    assert lines[0] == "🟡 Acme – Summer Trainee · 6 / 13"
    assert lines[2] == "    ↳ intern +3 · Helsinki +3"


def test_default_maximum_is_13():
    assert max_score(DEFAULT_RANK) == 3 + 3 + 3 + 2 + 2


def test_reason_points_add_up_to_the_score():
    job = make_job(title="Summer Trainee 2027, OpenGL", location="Espoo", start="Jun 2027")
    rank = score(job, DEFAULT_RANK, date(2026, 11, 18))
    assert sum(float(reason.rsplit(" ", 1)[1]) for reason in rank.reasons) == rank.score
    assert rank.out_of == 13


def test_unknown_location_is_listed_as_a_reason():
    rank = score(make_job(location=""), DEFAULT_RANK, date(2026, 11, 18))
    assert "no location +1" in rank.reasons
