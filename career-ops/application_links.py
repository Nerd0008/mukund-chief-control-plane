"""Extract a target vacancy's application route. Never submits or invents URLs.

Discovery pages are leads, not availability evidence. An outbound route must
still be read and verified by jd_fetcher before it can authorize delivery.
"""
from __future__ import annotations

import html as entities
import ipaddress
import json
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

AGGREGATORS = frozenset(('jointheintake.com', 'brightnetwork.co.uk', 'gradcracker.com'))
APPLY = re.compile(r'^(?:apply(?:\s+(?:now|online(?:\s+now)?|for\s+(?:(?:this|the)\s+)?(?:job|role|position)))?|apply\s+on\s+.+?[’\']s\s+(?:site|website))$', re.I)


def public_url(value, base=''):
    """Reject local/private destinations and non-GET schemes, retaining query identity."""
    value = entities.unescape(value or '').strip()
    if not value or value.startswith('#'):
        return None
    try:
        parsed = urlsplit(urljoin(base, value))
        host = parsed.hostname or ''
        if parsed.scheme not in ('http', 'https') or not host or parsed.username or parsed.password:
            return None
        if host.lower() == 'localhost' or host.lower().endswith(('.localhost', '.local')):
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            if '.' not in host:
                return None
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ''))
    except ValueError:
        return None


def aggregator(url):
    host = (urlsplit(url).hostname or '').lower().removeprefix('www.')
    return host in AGGREGATORS


def listing(url):
    p = urlsplit(url)
    parts = [s for s in p.path.split('/') if s]
    host = (p.hostname or '').lower().removeprefix('www.')
    return ((host == 'brightnetwork.co.uk' and (not parts or len(parts) < 3))
            or (host == 'jointheintake.com' and len(parts) < 2)
            or bool(re.search(r'/(?:jobs/search|job-search|search-jobs)(?:/|$)', p.path)))


def tokens(text):
    return set(re.findall(r'[a-z0-9]+', entities.unescape(text or '').lower()))


def title_matches(expected, actual):
    wanted = tokens(expected)
    found = tokens(actual)
    # Years must agree; broad token overlap must not accept a different intake.
    years = {t for t in wanted if re.fullmatch(r'20\d\d', t)}
    return bool(wanted and len(wanted & found) / len(wanted) >= .75
                and (not years or years <= found))


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.links = []
        self.anchor = None
        self.h1 = None
        self.titles = []
        self.script = None
        self.postings = []
        self.frames = []
        self.forms = []
        self.meta_title = ''

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        # html.parser yields None for a present-but-valueless attribute (e.g. <div class>),
        # so a dict .get(key, '') default does NOT protect us. Coerce explicitly.
        blocked = tag in ('nav', 'header', 'footer', 'aside') or bool(re.search(
            r'(?:similar|related|recommended)[-_ ](?:jobs|roles)',
            (a.get('class') or '') + ' ' + (a.get('id') or ''), re.I))
        inherited = any(x[2] for x in self.stack)
        if tag not in ('input', 'meta', 'link', 'br', 'hr', 'img', 'source', 'area', 'wbr'):
            self.stack.append((tag, a, blocked or inherited))
        if not (blocked or inherited):
            if tag == 'meta' and a.get('property') == 'og:title': self.meta_title = a.get('content', '')
            if tag == 'h1': self.h1 = []
            if tag == 'a': self.anchor = {'url': a.get('href'), 'parts': []}
            if tag == 'script' and (a.get('type') or '').lower() == 'application/ld+json': self.script = []
            if tag == 'turbo-frame' and any(x[1].get('data-call-to-action--form-kind-value') == 'apply_url' for x in self.stack):
                self.frames.append(a.get('src'))
            if tag == 'form': self.forms.append(a)

    def handle_data(self, data):
        if self.h1 is not None: self.h1.append(data)
        if self.anchor is not None: self.anchor['parts'].append(data)
        if self.script is not None: self.script.append(data)

    def handle_endtag(self, tag):
        if tag == 'h1' and self.h1 is not None:
            self.titles.append(' '.join(' '.join(self.h1).split())); self.h1 = None
        if tag == 'a' and self.anchor is not None:
            self.anchor['text'] = ' '.join(' '.join(self.anchor.pop('parts')).split())
            self.links.append(self.anchor); self.anchor = None
        if tag == 'script' and self.script is not None:
            try:
                data = json.loads(''.join(self.script))
                items = data if isinstance(data, list) else data.get('@graph', [data])
                self.postings.extend(x for x in items if isinstance(x, dict) and x.get('@type') == 'JobPosting')
            except (ValueError, TypeError, AttributeError): pass
            self.script = None
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]; break


def extract(html, url):
    page = _Page(); page.feed(html or '')
    posting = page.postings[0] if len(page.postings) == 1 else {}
    title = next((t for t in page.titles if not APPLY.fullmatch(t)), '') or posting.get('title', '') or page.meta_title
    specific = bool(title and title.lower() not in ('careers', 'jobs', 'current vacancies', 'opportunities') and not listing(url))
    candidates = {}
    if specific:
        for link in page.links:
            target = public_url(link['url'], url)
            if target and APPLY.fullmatch(link['text']) and not listing(target):
                candidates[target] = {'url': target, 'label': link['text']}
    return {'title': title, 'posting': posting, 'specific': specific,
            'links': list(candidates.values()), 'frames': page.frames, 'forms': page.forms}


def employer_matches(source_url, label, destination_url, destination_html):
    """Require brand evidence as well as the matching role on outbound destinations."""
    match = re.fullmatch(r'apply\s+on\s+(.+?)[’\']s\s+(?:site|website)', label or '', re.I)
    if match:
        brand = ''.join(sorted(tokens(match[1])))
        required = tokens(match[1])
    else:
        host = (urlsplit(source_url).hostname or '').lower().removeprefix('www.')
        if aggregator(source_url): return False
        # Employer site -> its ATS: require the employer's domain label at the ATS.
        required = {host.split('.')[-3] if host.endswith('.co.uk') else host.split('.')[-2]}
        brand = ''.join(sorted(required))
    target_host = (urlsplit(destination_url).hostname or '').lower().replace('-', '')
    readable = entities.unescape(re.sub('<[^>]+>', ' ', destination_html or ''))
    return bool(brand and (all(t in target_host for t in required) or required <= tokens(readable)))


def employer_name(label):
    match=re.fullmatch(r'apply\s+on\s+(.+?)[’\']s\s+(?:site|website)',label or '',re.I)
    return match[1].strip() if match else None


def fragment_route(page, fragment_html, posting_url, frame_url):
    """Recognise only a job-bound, declared application form; never call its action."""
    identifier = page['posting'].get('identifier') or {}
    job_id = identifier.get('value') if isinstance(identifier, dict) else None
    if not job_id or parse_qs(urlsplit(frame_url).query).get('job_uid') != [str(job_id)]:
        return False
    fragment = extract(fragment_html, posting_url)
    for form in fragment['forms']:
        action = public_url(form.get('action'), posting_url)
        if (action and urlsplit(action).hostname == urlsplit(posting_url).hostname
                and parse_qs(urlsplit(action).query).get('job_id') == [str(job_id)]
                and form.get('method', '').lower() == 'post'):
            return True
    return False
