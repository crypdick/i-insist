# Coordinate checker execution with uv installation

Status: accepted.

uv tool reinstallation removes installed packages before restoring them. A checker
starting during that window can fail while importing a dependency, even though
installation finishes successfully. Retrying arbitrary checker failures risks
repeating side effects and does not prevent removal during a successful import.

For directly invoked uv-installed checker executables on Linux and macOS, the
runner shares uv's existing tools-directory file lock. It resolves entrypoint
symlinks, identifies the environment by its receipt, and holds a shared lock
through checker exit. uv takes an exclusive lock for tool installation. Checker
lock waits and execution share the configured timeout; errors still fail closed.
No rule fields or provider registrations change.

uv locks its entire tools directory, so an unrelated tool installation can delay
a checker. Shared locks preserve concurrent checks. This depends on uv retaining
its `.lock` and receipt during in-place package updates; destructive environment
replacement and the runner's own imports remain outside this protection. Wrapper
commands are opaque. See [checker execution](../reference.md#write-a-checker).
