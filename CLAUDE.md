# CLAUDE.md

load Skill(developing*)

dont use `/plan`. Use Skill(agent-claude-bot)

## Rules
- When editing any `.claude/skills/*/SKILL.md`, MUST bump `version:` in frontmatter (patch for fixes, minor for features). No exceptions.
- `.claude/skills/` is a **git submodule**. After editing files inside it, MUST commit inside the submodule first (`cd .claude/skills && git add && git commit`), then commit the submodule reference in the parent repo (`git add .claude/skills && git commit`).

## Frontend Debug

login with "lattice" user to use .browser snapshot

see llm.snapshot.md

## About LatticeCast

lattice-cast is airtable-like table system at layer-1. and layer-2 is project management system or CRM.

pm sys and crm use shared airtable-like base.