#!/usr/bin/env node
// review.md -> GitLab Code Quality JSON.

import { createHash } from 'node:crypto'
import { readFileSync, writeFileSync } from 'node:fs'

// Critical/Medium/Low is the agent's vocabulary; GitLab's `blocker` is unused, nothing blocks.
const SEVERITY = { C: 'critical', M: 'major', L: 'minor' }

export function parseReview(md) {
  // `| Critical | 2 |` — the agent's own tally of what is still open.
  const counted = [...md.matchAll(/^\|\s*(Critical|Medium|Low)\s*\|\s*(\d+)\s*\|/gim)].reduce(
    (n, m) => n + Number(m[2]),
    0
  )

  const findings = []
  // Split on the headings rather than matching heading-to-heading: a lookahead would need to
  // say "or end of input", and JS has no \Z — which silently dropped every last finding.
  for (const block of md.split(/^###\s+/m).slice(1)) {
    const m = block.match(/^([CML])(\d+)\s*·\s*(.+?)\s*$([\s\S]*)/m)
    if (!m) continue
    const [, letter, id, claim, rest] = m
    // The whole block, not just the line under the heading, so a wrapped heading still parses.
    const at = rest.match(/`([^`\s]+?):(\d+)`/)
    if (!at) continue
    const body = rest
      .replace(/`[^`\s]+?:\d+`/, '')
      .replace(/\s+/g, ' ')
      .trim()
    findings.push({
      description: body ? `${claim} — ${body}` : claim,
      check_name: `code-review/${letter}${id}`,
      // Not the line number and not the commit: GitLab matches findings across pushes by
      // fingerprint, and a finding whose code moved down a file is the same finding.
      fingerprint: createHash('sha256').update(`${letter}${id}\n${at[1]}\n${claim}`).digest('hex'),
      severity: SEVERITY[letter],
      location: { path: at[1].replace(/^\.\//, ''), lines: { begin: Number(at[2]) } },
    })
  }
  return { findings, counted }
}

function main([input, output]) {
  const { findings, counted } = parseReview(readFileSync(input, 'utf8'))
  if (findings.length !== counted) {
    console.error(
      `review.md counts ${counted} finding(s) but ${findings.length} parsed — ` +
        'the review format and this parser disagree, so the report would be wrong'
    )
    process.exit(1)
  }
  writeFileSync(output, JSON.stringify(findings, null, 2))
  console.log(`${findings.length} finding(s) -> ${output}`)
}

if (process.argv[1] === new URL(import.meta.url).pathname) {
  main(process.argv.slice(2))
}
