---
name: taste-enforcer
enabled: true
event: prompt
pattern: don.?t use|always prefer|avoid|never do|instead of|I hate when|stop using|should always|should never|prefer .+ over|ban |forbid
action: warn
---

If this prompt expresses a durable coding preference, codify it with an existing tool setting,
static check, or Hookify rule. Check earlier messages for missed preferences too.
