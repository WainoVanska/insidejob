import pytest

from insidejob.links import LinkError, LinkSource, parse_link


@pytest.mark.parametrize(
    ("link", "expected"),
    [
        ("https://job-boards.greenhouse.io/wolt", ("greenhouse", "wolt")),
        ("https://job-boards.greenhouse.io/wolt/jobs/123456", ("greenhouse", "wolt")),
        ("https://boards.greenhouse.io/relex/jobs/8014266003?gh_src=x", ("greenhouse", "relex")),
        ("https://boards.greenhouse.io/embed/job_board?for=oura", ("greenhouse", "oura")),
        ("https://boards-api.greenhouse.io/v1/boards/solita/jobs", ("greenhouse", "solita")),
        ("job-boards.greenhouse.io/smartlyio", ("greenhouse", "smartlyio")),  # no https://
        ("https://jobs.ashbyhq.com/iceye", ("ashby", "iceye")),
        ("https://jobs.ashbyhq.com/iceye/1b8f0c3e-1111/application", ("ashby", "iceye")),
        ("https://api.ashbyhq.com/posting-api/job-board/reaktor", ("ashby", "reaktor")),
        ("https://apply.workable.com/nitor/", ("workable", "nitor")),
        ("https://apply.workable.com/varjo-1/j/ABC123/", ("workable", "varjo-1")),
        ("https://apply.workable.com/api/v3/accounts/nitor/jobs", ("workable", "nitor")),
        (
            "https://hypehype.teamtailor.com/jobs/12-intern",
            ("rss", "hypehype.teamtailor.com/jobs.rss"),
        ),
        ("https://careers.futurice.com/jobs.rss", ("rss", "careers.futurice.com/jobs.rss")),
        ("https://gofore.com/en/careers/feed/", ("rss", "gofore.com/en/careers/feed/")),
    ],
)
def test_links_become_sources(link, expected):
    found = parse_link(link)
    assert (found.type, found.board) == expected


def test_company_name_is_guessed_from_the_board():
    assert parse_link("https://job-boards.greenhouse.io/small-giant").company == "Small Giant"
    assert parse_link("https://jobs.ashbyhq.com/iceye") == LinkSource("ashby", "iceye", "Iceye")
    assert parse_link("https://careers.futurice.com/jobs.rss").company == "Futurice"


@pytest.mark.parametrize(
    ("link", "message"),
    [
        ("", "empty"),
        ("https://www.linkedin.com/jobs/view/123", "isn't a supported job site"),
        ("https://kone.wd3.myworkdayjobs.com/Careers/job/x", "Workday"),
        ("https://www.relex.com/careers/?gh_jid=123", "Greenhouse job shown on the company"),
        ("https://apply.workable.com/j/ABC123", "short Workable link"),
        ("https://boards.greenhouse.io/embed/job_app", "board name"),
    ],
)
def test_unusable_links_explain_why(link, message):
    with pytest.raises(LinkError, match=message):
        parse_link(link)
