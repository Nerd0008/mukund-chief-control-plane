"""Owner-approved typography overrides, separate from immutable source geometry."""
def standardize(layout):
    slots = layout['slots']
    by_id = {s['id']: s for s in slots}
    layout['version'] = 3
    layout['body_leading'] = 11.5
    layout['spacing_policy'] = '11.5 pt body leading; 23 pt two-line bullet cadence; upright bold degree titles'
    for s in slots:
        s['leading'] = 11.5
    for first, last, cadence in [(6,11,11.5),(21,23,23),(25,27,23),(31,33,23),(36,38,23),(41,43,23),(45,48,11.5)]:
        start = by_id[f's{first:02d}']['baseline']
        for n in range(first,last+1):
            by_id[f's{n:02d}']['baseline'] = start + (n-first)*cadence
    for run in by_id['s16']['runs']:
        if run['style'] == 'bold_italic':
            run['style'] = 'bold'
    for s in slots:
        s['region'] = [s['x'], s['baseline']-s['font_size'], 545.25,
                       s['baseline']+(s['max_lines']-1)*s['leading']+3]
    return layout
