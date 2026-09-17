---
name: no-junk-drawers
enabled: true
event: file
conditions:
  - field: file_path
    operator: regex_match
    pattern: (^|[/\\])(utils|helpers|misc|common|shared|general)\.py$
action: warn
---

Name modules for purpose. Put shared behavior and invariants in owning package.
