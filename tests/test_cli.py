from watch4ping.cli import build_parser, normalize_formats


def test_parser_accepts_short_monitoring_flags():
    args = build_parser().parse_args(["-t", "8.8.8.8", "-i", "5", "-w", "2"])

    assert args.target == "8.8.8.8"
    assert args.interval == 5
    assert args.timeout == 2


def test_normalize_formats_defaults_to_all_formats():
    assert normalize_formats(None) == ("json", "csv", "md")


def test_normalize_formats_expands_all():
    assert normalize_formats(["all"]) == ("json", "csv", "md")


def test_normalize_formats_preserves_selected_formats():
    assert normalize_formats(["json", "csv"]) == ("json", "csv")
