#!/usr/bin/env python3
"""Build cv_edits.json for the Tesco IMS Technology Cyber Security Graduate Scheme.

Targets the JD's own vocabulary: incident response, security platforms, cyber assurance,
spotting risks, problem solving, working with others, protecting colleagues/customers/data,
and the Customer Service rotation (owner has strong customer-facing evidence).

Every replacement is validated against the +/-15% character rule before writing, so the
tailoring gate never fails for a reason we could have caught here.
"""
import json
from pathlib import Path

OUT = Path(__file__).with_name("cv_edits.json")

PAIRS = [
    # --- Professional summary: reframe onto the graduate scheme's own language ------- #
    ("MSc Information Security graduate from Royal Holloway with CompTIA Security+ and ISC2 CC. IT support and systems",
     "Information Security MSc graduate (Merit) with CompTIA Security+ and ISC2 CC, applying for a graduate cyber"),

    ("experience, complemented by practical projects in phishing analysis, endpoint risk assessment and security automation. ",
     "security role spanning incident response, security platforms and cyber assurance. IT support, risk assessment"),

    ("Seeking a cybersecurity internship to contribute technical and analytical skills while developing hands-on industry experience.",
     "and customer-facing experience, plus real curiosity about how systems work and how to keep our customers' data safe."),

    # --- Technical skills: JD nouns, and normalise ISO27001 -> ISO 27001 ------------- #
    ("Phishing analysis, Windows Event Logs, network analysis, MITRE ATT&CK",
     "Phishing analysis, incident triage, Windows Event Logs, MITRE ATT&CK"),

    ("Windows, Microsoft 365, Azure, account administration, endpoint configuration",
     "Windows, Microsoft 365, Azure, Active Directory, endpoint configuration"),

    ("ISO27001, Cyber Essentials, GDPR, NIST CSF ",
     "ISO 27001, Cyber Essentials, GDPR, NIST CSF"),

    ("User support, technical documentation, stakeholder coordination",
     "Customer support, documentation, stakeholder coordination and teamwork"),

    # --- Work experience: risk spotting, incident handling, working with others ------- #
    ("• Manage typically 4–5 access requests daily through on-premises Active Directory, verifying business approval, granting time-",
     "• Manage 4–5 access requests daily through on-premises Active Directory, verifying approval before granting time-"),

    ("limited permissions and documenting access periods and extensions.",
     "limited permissions, documenting each access period for assurance."),

    ("• Investigate 4–5 suspicious emails daily, checking sender and link domains for impersonation, documenting findings and alerting ",
     "• Investigate 4–5 suspicious emails daily, checking sender and link domains for impersonation, documenting findings and "),

    ("colleagues to recurring phishing tactics.",
     "escalating phishing patterns to colleagues."),

    ("• Conduct weekly store-wide risk assessments and daily compliance checks, reviewing operational controls, maintaining    ",
     "• Conduct weekly store-wide risk assessments and daily compliance checks, reviewing operational controls, spotting "),

    ("assessment records and identifying issues requiring corrective action.",
     "weak points in process and recording every issue that needs corrective action."),

    ("• Handle 15+ operational issues weekly, including product-date exceptions and safety concerns; document incidents through  ",
     "• Handle 15+ operational issues weekly, including product-date exceptions and safety concerns; document incidents and "),

    ("internal reporting systems, apply temporary controls and escalate unresolved risks.",
     "escalate unresolved risks through internal reporting, applying fixes under time pressure."),

    ("• Coordinate 7–8 colleagues per shift, communicating control requirements, assigning corrective actions and following up ",
     "• Coordinate 7–8 colleagues per shift, explaining control requirements, assigning corrective actions and following up "),

    ("to ensure identified risks are addressed.",
     "until identified risks are closed out."),

    # --- Projects: investigations, triage, problem diagnosis ------------------------- #
    ("• Designed and developed a phishing-analysis prototype to highlight suspicious email indicators and support manual triage,",
     "• Designed and developed a phishing-analysis prototype that highlights suspicious email indicators and supports triage,"),

    ("with design reviews from an experienced SOC analyst.",
     "reviewed by an experienced SOC analyst for realism."),

    ("• Developed a local tool that maps Windows error codes to common causes, supporting investigation of system ",
     "• Developed a local tool that maps Windows error codes to known causes, supporting investigation of system "),
]


def main() -> int:
    edits = []
    bad = 0
    print(f"{'orig':>5} {'new':>5} {'delta':>8}   find")
    for find, repl in PAIRS:
        lo, ln = len(find), len(repl)
        delta = (ln - lo) / lo * 100
        flag = "" if abs(delta) <= 15 else "   <-- OUTSIDE +/-15%"
        if flag:
            bad += 1
        print(f"{lo:>5} {ln:>5} {delta:>+7.1f}% {flag}  {find[:58]!r}")
        edits.append({"find": find, "replace": repl})

    doc = {
        "purpose": "Tesco IMS Technology - Cyber Security Graduate Scheme tailoring",
        "master": "Mukund_CV_BASE_2026-09-25.pdf supplied by owner 2026-09-25",
        "constraint": "layout preserved: each edit keeps its span origin, font, size; +/-15% chars and rendered-width gate",
        "edits": edits,
    }
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {OUT} ({len(edits)} edits), {bad} outside the character budget")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
