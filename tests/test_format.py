from datetime import date

from insidejob.format import detail_parts, fi_date, plain
from insidejob.models import Employment, Workplace
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
