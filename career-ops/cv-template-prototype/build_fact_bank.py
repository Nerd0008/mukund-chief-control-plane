"""Engineering-only curated, source-traceable wording. Never application code."""
import json,pathlib
HERE=pathlib.Path(__file__).parent
l=json.loads((HERE/'layout.json').read_text(encoding='utf-8'))
slots={s['id']:s for s in l['slots']}
texts=[
('s04','MSc Information Security graduate holding CompTIA Security+ and ISC2 Certified in Cybersecurity (CC). Practical experience building Python tools and a JavaScript browser extension, with testing, API integration and Windows troubleshooting, alongside user support and technical documentation.',['s13','s45','s46','s31','s35','s36','s40','s41','s21','s11']),
('s06','Programming & Scripting: Python, Java, JavaScript, PowerShell, SQL',['s08','s18','s30']),
('s07','Web & APIs: JavaScript, HTML, CSS, API integration, Manifest V3',['s08','s30']),
('s08','Systems & Cloud: Windows, Microsoft 365, Azure, endpoint configuration',['s07']),
('s09','Testing & Analysis: Manual testing, false-positive checks, log analysis',['s32','s33','s40','s04']),
('s10','Data & Tools: Python, SQL, MySQL, JSON, Windows Event Logs',['s08','s18','s35','s40']),
('s11','Communication & Support: User support, technical documentation, stakeholder coordination',['s11']),
('s21','Administer 4–5 daily access requests in on-premises Active Directory, verifying approval, recording access periods and managing time-limited permissions.',['s21']),
('s22','Analyse 4–5 suspicious emails daily, checking sender and link domains, recording findings and communicating recurring phishing patterns to colleagues.',['s22']),
('s23','Support 15 employees using 15–20 devices, troubleshooting access and system issues, monitoring server health and maintaining password and website-access controls.',['s23']),
('s25','Review operational controls through weekly risk assessments and daily compliance checks, recording findings and identifying corrective actions.',['s25']),
('s26','Handle 15+ operational issues weekly, including product-date exceptions and safety concerns; document incidents, apply temporary controls and escalate unresolved risks.',['s26']),
('s27','Coordinate 7–8 colleagues per shift, communicating requirements, assigning corrective actions and following up to confirm issues are addressed.',['s27']),
('s31','Built a Chrome extension with 25+ detection patterns to warn users about email addresses, credentials and API keys in pasted content before submission.',['s31']),
('s32','Achieved 93.7% accuracy over 150+ manual tests, including false-positive checks; kept detection local to protect sensitive content.',['s32']),
('s33','Iterated detection rules through manual testing to reduce false positives, while allowing users to review flagged content and decide whether to proceed.',['s33']),
('s36','Built a Python/Gmail API phishing-analysis prototype to highlight suspicious email indicators and support manual triage, with design reviews from an experienced SOC analyst.',['s35','s36']),
('s37','Tested the prototype against suspicious and legitimate business emails, using hardcoded MITRE ATT&CK mappings while keeping sensitive email data local.',['s37']),
('s38','Developing sandbox-based URL analysis to inspect linked content and enrich investigation reports while keeping sensitive email data local.',['s38']),
('s41','Built a Python tool mapping Windows error codes to common causes to support investigation of system faults across business devices.',['s40','s41']),
('s42','Used the tool to investigate server freezes and crashes, finding errors linked to missing or corrupted DLLs and informing corrective action.',['s42']),
('s43','Keep log analysis local for internal troubleshooting; developing background monitoring and automated alerts for unexpected errors.',['s43'])]
bank={'version':1,'master_sha256':l['master_sha256'],'review':'Engineering-curated paraphrases checked against cited master facts; no model-authored facts.','slots':{}}
for s in l['slots']:
    if s['variable']:
        bank['slots'][s['id']]={'original':{'text':s['text'].removeprefix('• '),'sources':[s['id']]}}
for key,text,sources in texts:
    assert key in bank['slots'] and all(x in slots for x in sources),(key,sources)
    bank['slots'][key]['engineering']={'text':text,'sources':sources}
(HERE/'fact_bank.json').write_text(json.dumps(bank,indent=2,ensure_ascii=False),encoding='utf-8')
