"""Harness-independent checks for agent tool invocations."""

from beartype import BeartypeConf
from beartype.claw import beartype_this_package

beartype_this_package(conf=BeartypeConf(claw_is_pep526=False))
