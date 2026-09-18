# One uv-managed runner

Status: accepted.

Install i-insist as a standalone uv tool that every harness shares. Its installer
registers lifecycle hooks. Providers own their rule and checker files.
Providers depend on the file and JSON protocol and an available runner, not another
plugin's import path or versioned cache directory.

Harness plugins can bundle the runner and use each harness's update mechanisms,
but dependency resolution and update policies differ across harnesses. The user
chose uv to keep one installed version and one update path. Updates are explicit
through uv rather than automatic plugin updates. Avoid requiring both a
plugin and a separately upgraded runner.

A harness plugin can package the same engine without changing provider
rules. [Installation instructions](../../README.md#install) are canonical in the
README.
