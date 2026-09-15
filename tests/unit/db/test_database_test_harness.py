from tests.support.database import _create_role_statement


def test_create_role_statement_safely_inlines_password() -> None:
    statement = _create_role_statement(
        "bff_test_control_fixture",
        "fixture'password",
    )

    rendered = statement.as_string()

    assert "$1" not in rendered
    assert "%s" not in rendered
    assert '"bff_test_control_fixture"' in rendered
    assert "PASSWORD 'fixture''password'" in rendered
