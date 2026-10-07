# magicpen — 神笔马良 True-Clone Writing Flow

> The public repo keeps the name **magicpen**; its content is **神笔马良 (Shenbi Maliang)**.

A true-clone writing flow: drafts that read as if the person wrote them, with zero human rewriting.

## How it works

1. **Persona bundle, three frozen beams.** Style (A: sentence length, catchphrases, pronouns, punctuation),
   thinking (B: five-part structure, openings, analogy rules), and judgment (C: stances, taboos, decision rules).
   Every beam is a numeric baseline sampled from the longform corpus in strata (A: 30 pieces / B: 30 / C: 31).
   Numbers live in `profile/` — no source text ships with this repo.
2. **Internal task self-loop, the only legit path.** A writer persona drafts from a topic; a machine-check
   persona pre-screens; three subjective lanes review; a repair persona revises. At most 3 rounds.
   Writer, verifier, and repairer are always different passes with fresh context.
3. **Subjective three-lane verification.** Style aesthetics, thinking aesthetics, and judgment aesthetics
   each read the draft with naked eyes and quote it. Verifier personas MUST NOT run scripts —
   machine counts can count, but they cannot tell "this line was forced in".

Pass bar: `blocker = 0`, `major ≤ 1`, no major in the C (judgment) beam, and no FAIL from any subjective lane.
A machine PASS overruled by a subjective FAIL counts as FAIL.

## Files

| Path | What it is |
|---|---|
| `SKILL.md` | Sole entry point: constraints (§2–§4), workflow (§5), file map (§7) |
| `VERIFIER-PROMPTS.md` | Prompts for the 4 verifier roles (1 machine pre-screen + 3 subjective lanes) |
| `profile/profile_a.json` | Beam A numeric baseline (length / catchphrases / pronouns / punctuation) |
| `profile/profile_b.json` | Beam B templates (five parts / openings / failure gates) |
| `profile/stance_table.json` | Beam C stances S-01…S-10 (id / domain / stance / evidence / boundary) |
| `profile/taboo_list.json` | Beam C taboos T-01…T-10 (zero tolerance) |
| `profile/decision_rules.json` | Beam C drafting rules D-01…D-10 |

## How to use

Use with an agent that supports skills plus internal subagents:

1. Load the five JSON files in `profile/` and `SKILL.md` §2–§4 into the writer persona.
2. Draft from a topic, following the five-part shape (event anchor → scope → substance → advice → invite).
3. Run the four verifier roles from `VERIFIER-PROMPTS.md` (machine pre-screen + subjective A / B / C),
   then repair and repeat until the pass bar is met.

## Notes

- The machine-check scripts are internal pre-screeners; this public repo ships only the rule spec, not the scripts.
- The training corpus is private and never enters this repo (`corpus/` is ignored); `profile/` carries numeric baselines only.
- The previous edition is archived under the tag `archive/pre-shenbi`.
- Language versions: [简体中文](README.zh-CN.md) · [日本語](README.ja.md).
