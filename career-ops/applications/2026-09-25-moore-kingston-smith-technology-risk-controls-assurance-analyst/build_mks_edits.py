#!/usr/bin/env python3
"""Build cv_edits.json for Moore Kingston Smith TRCA Analyst.

Angle: this is an IT audit / controls-assurance role, not a SOC role. Lead with the
evidence the JD actually asks for - access management (ITGC), control review, evidence
collection, documentation quality, escalation, methodical testing - and with the
framework knowledge (ISO 27001 / Cyber Essentials / GDPR / NIST CSF) that underpins
control work. Do NOT claim audit, ITGC/ITAC testing or client-liaison experience the
owner does not have; describe his real work in the JD's vocabulary instead.

Every replacement is validated against the +/-15% character rule before writing.
"""
import json
from pathlib import Path

OUT = Path(__file__).with_name("cv_edits.json")

PAIRS = [
    # ---- summary: entry-level technology assurance, control and documentation led --- #
    ("MSc Information Security graduate from Royal Holloway with CompTIA Security+ and ISC2 CC. IT support and systems",
     "Information Security MSc graduate (Merit) with CompTIA Security+ and ISC2 CC, seeking an entry-level"),

    ("experience, complemented by practical projects in phishing analysis, endpoint risk assessment and security automation. ",
     "technology assurance role. Control-focused work in access management, evidence collection, risk assessment"),

    ("Seeking a cybersecurity internship to contribute technical and analytical skills while developing hands-on industry experience.",
     "and ISO 27001-aligned documentation, taking a methodical approach to testing and keeping a clear audit trail."),

    # ---- skills: audit vocabulary, no fabricated audit experience ------------------- #
    ("Security Analysis: ",
     "Controls Testing: "),

    ("Phishing analysis, Windows Event Logs, network analysis, MITRE ATT&CK",
     "Access control administration, evidence collection, control reviews"),

    ("Windows, Microsoft 365, Azure, account administration, endpoint configuration",
     "Windows, Microsoft 365, Azure, Active Directory, access administration"),

    ("ISO27001, Cyber Essentials, GDPR, NIST CSF ",
     "ISO 27001, Cyber Essentials, GDPR, NIST CSF"),

    ("User support, technical documentation, stakeholder coordination",
     "Documentation, stakeholder coordination, clear written communication"),

    # ---- experience: access management, evidence and escalation --------------------- #
    ("• Manage typically 4–5 access requests daily through on-premises Active Directory, verifying business approval, granting time-",
     "• Administer 4–5 access requests daily in on-premises Active Directory, verifying approval before granting time-"),

    ("limited permissions and documenting access periods and extensions.",
     "limited permissions, and recording every access period for later audit."),

    ("• Investigate 4–5 suspicious emails daily, checking sender and link domains for impersonation, documenting findings and alerting ",
     "• Investigate 4–5 suspicious emails daily, checking sender and link domains for impersonation, recording findings and "),

    ("• Conduct weekly store-wide risk assessments and daily compliance checks, reviewing operational controls, maintaining    ",
     "• Test weekly store-wide controls through risk assessments and daily compliance checks, reviewing evidence and spotting "),

    ("assessment records and identifying issues requiring corrective action.",
     "weak points in process and recording every issue that needs corrective action."),

    ("• Handle 15+ operational issues weekly, including product-date exceptions and safety concerns; document incidents through  ",
     "• Record and escalate 15+ operational issues weekly, including product-date exceptions and safety concerns, and apply "),

    ("internal reporting systems, apply temporary controls and escalate unresolved risks.",
     "temporary controls and escalate unresolved risks through internal reporting systems."),

    ("• Developed a local tool that maps Windows error codes to common causes, supporting investigation of system ",
     "• Developed a local tool that maps Windows error codes to known causes, supporting consistent investigation of system "),
]


def main() -> int:
    edits, bad = [], 0
    print(f"{'orig':>5} {'new':>5} {'delta':>8}   find")
    for find, repl in PAIRS:
        lo, ln = len(find), len(repl)
        delta = (ln - lo) / lo * 100
        flag = "" if abs(delta) <= 15 else "   <-- OUTSIDE +/-15%"
        bad += bool(flag)
        print(f"{lo:>5} {ln:>5} {delta:>+7.1f}% {flag}  {find[:56]!r}")
        edits.append({"find": find, "replace": repl})

    OUT.write_text(json.dumps({
        "purpose": "Moore Kingston Smith - Technology Risk & Controls Assurance Analyst",
        "master": "Mukund_CV_BASE_2026-09-25.pdf supplied by owner 2026-09-25",
        "constraint": "layout preserved: each edit keeps its span origin, font, size; +/-15% chars and rendered-width gate",
        "edits": edits,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {OUT} ({len(edits)} edits), {bad} outside budget")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
