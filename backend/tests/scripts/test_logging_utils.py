import click

import app.utils.env_logging as logging_utils


def test_format_env_tag_colors():
    tag = logging_utils.format_env_tag("stg")
    assert tag.startswith("\x1b[")
    assert tag.endswith("\x1b[0m")
    assert click.unstyle(tag) == "[STG]"


def test_format_env_tag_for_unknown_env():
    tag = logging_utils.format_env_tag("custom")
    assert tag == "[CUSTOM]"


def test_log_info_only_colors_tag(capsys):
    logging_utils.log_info("preview", "Hello world")
    captured = capsys.readouterr()
    assert "[PREVIEW]" in captured.out
    assert click.unstyle(captured.out.strip()) == "[PREVIEW] Hello world"


def test_log_warn_streams_to_stderr(capsys):
    logging_utils.log_warn("prod", "Danger zone")
    captured = capsys.readouterr()
    assert "[PROD]" in captured.err
    assert click.unstyle(captured.err.strip()) == "[PROD] Danger zone"
