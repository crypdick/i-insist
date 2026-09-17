import pytest
from beartype.roar import BeartypeCallHintParamViolation

from i_insist.approval import prompt_approves


def test_package_import_enables_runtime_type_checks():
    with pytest.raises(BeartypeCallHintParamViolation):
        prompt_approves(42)  # type: ignore[arg-type]
