"""Owner-approved typography overrides, separate from immutable source geometry."""
def standardize(layout):
    slots = layout['slots']
    by_id = {s['id']: s for s in slots}
    layout['version'] = 4
    layout['body_leading'] = 11.0
    layout['spacing_policy'] = '11 pt body leading; no extra bullet paragraph gap; 2.5 pt block gap; upright bold degree titles'
    for s in slots:
        s['leading'] = 11.0
    for first, last, cadence in [(6,11,11),(45,48,11)]:
        start = by_id[f's{first:02d}']['baseline']
        for n in range(first,last+1):
            by_id[f's{n:02d}']['baseline'] = start + (n-first)*cadence
    # Lay out the whole work/project sequence from one anchor. Continuation
    # lines and the following bullet use exactly the same baseline interval.
    for n in range(21,49):
        previous=by_id[f's{n-1:02d}']; current=by_id[f's{n:02d}']
        gap=0.0
        if current['heading']: gap=5.0
        elif previous['heading']: gap=5.5
        elif n in (24,34,39): gap=2.5
        current['baseline']=previous['baseline']+previous['max_lines']*11.0+gap
    for run in by_id['s16']['runs']:
        if run['style'] == 'bold_italic':
            run['style'] = 'bold'
    for s in slots:
        s['region'] = [s['x'], s['baseline']-s['font_size'], 545.25,
                       s['baseline']+(s['max_lines']-1)*s['leading']+3]
    for rule, heading in zip(layout['rules'],(s for s in slots if s['heading'])):
        rule['y']=heading['baseline']+5
    return layout
