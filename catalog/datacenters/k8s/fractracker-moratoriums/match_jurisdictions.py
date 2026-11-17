"""Match FracTracker moratorium jurisdictions to Census 2024 geographies by name.

usage: match_jurisdictions.py MORATORIUMS_CSV GAZETTEER_DIR OUT_CSV

Reads the Census 2024 Gazetteer files (counties, place, cousubs, aiannh) and writes
the moratorium rows with three added columns: geo_level (state, county, place,
county_subdivision, aiannh, or empty), geoid, census_name. Rows that cannot be matched
uniquely keep an empty geo_level; they are reported on stderr.
"""
import csv
import re
import sys
from collections import defaultdict

STATE_FIPS = {
    'AL': '01', 'AK': '02', 'AZ': '04', 'AR': '05', 'CA': '06', 'CO': '08', 'CT': '09', 'DE': '10',
    'DC': '11', 'FL': '12', 'GA': '13', 'HI': '15', 'ID': '16', 'IL': '17', 'IN': '18', 'IA': '19',
    'KS': '20', 'KY': '21', 'LA': '22', 'ME': '23', 'MD': '24', 'MA': '25', 'MI': '26', 'MN': '27',
    'MS': '28', 'MO': '29', 'MT': '30', 'NE': '31', 'NV': '32', 'NH': '33', 'NJ': '34', 'NM': '35',
    'NY': '36', 'NC': '37', 'ND': '38', 'OH': '39', 'OK': '40', 'OR': '41', 'PA': '42', 'RI': '44',
    'SC': '45', 'SD': '46', 'TN': '47', 'TX': '48', 'UT': '49', 'VT': '50', 'VA': '51', 'WA': '53',
    'WV': '54', 'WI': '55', 'WY': '56', 'PR': '72',
}

# Tribal jurisdictions are named in prose, so they are mapped by hand to a TIGER 2024 AIANNH
# code (AIANNHCE). The build unions every AIANNH feature with that code (reservation "R" and
# off-reservation trust land "T").
TRIBAL = {
    ('Fort Peck Reservation', 'MT'): ('1250', 'Fort Peck Indian Reservation and Off-Reservation Trust Land'),
    ('Eastern Band of Cherokee Indians (EBCI) Lands', 'NC'): ('0990', 'Eastern Cherokee Reservation and Off-Reservation Trust Land'),
    ('Cherokee Nation Tribal Lands', 'OK'): ('5550', 'Cherokee OTSA'),
    ('Seminole Nation of Oklahoma Lands', 'OK'): ('5830', 'Seminole OTSA'),
}

# Consolidated city-county governments, listed upstream by their short name.
ALIASES = {
    ('Lexington', 'KY'): 'lexington fayette',
    ('Nashville', 'TN'): 'nashville davidson',
}

# Local sources whose county settles which of several same-named townships a row means, when
# the row does not name the county itself (county FIPS). Each checked by hand.
SOURCE_COUNTY = {
    'timesleader.com': '42079',            # Times Leader, Wilkes-Barre: Luzerne County, PA
    'uniontwp.com': '42125',               # Union Township, Finleyville: Washington County, PA
    'butlereagle.com': '42019',            # Butler Eagle: Butler County, PA
    'lowerbuckstimes.com': '42017',        # Lower Bucks Times: Bucks County, PA
    'lctberrien.org': '26021',             # Lincoln Charter Township: Berrien County, MI
    'wash-twp-stark-oh.us': '39151',       # Washington Township: Stark County, OH
    'oh-pleasant-township-franklin': '39049',  # Pleasant Township: Franklin County, OH
    'tapinto.net/towns/union/': '34039',   # TAPinto Union: Union Township, Union County, NJ
}

SUFFIXES =r'(city|town|village|borough|township|charter township|cdp|municipality|plantation|city and borough|consolidated government.*|metro government.*|unified government.*|metropolitan government.*|urban county)'


def norm(s):
    s = s.lower().replace('’', "'").strip()
    s = re.sub(r'\(.*?\)', '', s)
    s = re.sub(r'\bst\.?\s', 'saint ', s)
    s = re.sub(r'\bmt\.?\s', 'mount ', s)
    s = re.sub(r'\bft\.?\s', 'fort ', s)
    s = re.sub(r'[^a-z0-9 ]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def base(name):
    """Census name without its legal/statistical suffix ('Abington township' -> 'abington')."""
    n = norm(name)
    n = re.sub(r'\s+' + SUFFIXES + r'$', '', n)
    return n


def load(path, key='USPS'):
    with open(path, encoding='latin-1') as f:
        rows = list(csv.DictReader(f, delimiter='\t'))
    for r in rows:
        for k in list(r):
            r[k.strip()] = (r.pop(k) or '').strip()
    return rows


def main(src, gaz, out):
    counties = load(f'{gaz}/2024_Gaz_counties_national.txt')
    places = load(f'{gaz}/2024_Gaz_place_national.txt')
    cousubs = load(f'{gaz}/2024_Gaz_cousubs_national.txt')
    aiannh = load(f'{gaz}/2024_Gaz_aiannh_national.txt')

    county_ix = defaultdict(list)
    for r in counties:
        county_ix[(r['USPS'], norm(r['NAME']))].append(r)
    place_ix = defaultdict(list)
    for r in places:
        place_ix[(r['USPS'], base(r['NAME']))].append(r)
    cousub_ix = defaultdict(list)
    for r in cousubs:
        cousub_ix[(r['USPS'], base(r['NAME']))].append(r)

    def pick(cands):
        """Prefer active governments (FUNCSTAT A) over statistical areas (CDPs)."""
        if not cands:
            return None
        active = [c for c in cands if c.get('FUNCSTAT') in ('A', 'B', 'C', 'F', 'G')] or cands
        return active[0] if len(active) == 1 else None

    county_name = {r['GEOID']: base(r['NAME']).replace(' county', '').replace(' parish', '')
                   for r in counties}

    def by_county(cands, text, name):
        """Several same-named townships in one state: keep the one whose county the row names
        ("<county> County" as whole words, after removing the jurisdiction's own name, so Butler
        Township is not read as Butler County), or whose source site is in SOURCE_COUNTY."""
        for site, fips in SOURCE_COUNTY.items():
            if site in text.lower():
                hits = [c for c in cands if c['GEOID'][:5] == fips]
                return hits[0] if len(hits) == 1 else None
        t = re.sub(r'\b' + re.escape(name) + r'\b', ' ', norm(text))
        hits = [c for c in cands if c['GEOID'][:5] in county_name and
                re.search(r'\b' + re.escape(county_name[c['GEOID'][:5]]) + r' (county|parish)(s)?\b', t)]
        return hits[0] if len(hits) == 1 else None

    def match(j, st, text=''):
        jn = norm(j)
        if re.match(r'(state|commonwealth) of ', jn):
            return 'state', STATE_FIPS[st], j.split(' of ', 1)[1]
        if (j, st) in TRIBAL:
            code, label = TRIBAL[(j, st)]
            return 'aiannh', code, label
        if (j, st) in ALIASES:
            jn = ALIASES[(j, st)]
        if re.search(r'\b(county|parish|borough)$', jn) or re.search(r'\bcounty\b', jn):
            c = county_ix.get((st, jn))
            if c and len(c) == 1:
                return 'county', c[0]['GEOID'], c[0]['NAME']
            # otherwise fall through: consolidated governments ("Athens-Clarke County") are places
        # strip "City of", "Town of", "Village of" prefixes and trailing type words
        m = re.match(r'(city|town|village|township|borough) of (.+)$', jn)
        kind = None
        name = jn
        if m:
            kind, name = m.group(1), m.group(2)
        else:
            m = re.match(r'(.+?) (charter township|township|twp|city|town|village|borough)$', jn)
            if m:
                name, kind = m.group(1), m.group(2)
        name = norm(name)
        order = ['place', 'cousub']
        if kind in ('township', 'charter township', 'twp'):
            order = ['cousub', 'place']
        elif kind == 'town' and st in ('NY', 'WI', 'CT', 'MA', 'ME', 'NH', 'RI', 'VT'):
            order = ['cousub', 'place']
        elif st in ('CT', 'MA', 'ME', 'NH', 'RI', 'VT') and kind is None:
            order = ['cousub', 'place']
        for lvl in order:
            ix = place_ix if lvl == 'place' else cousub_ix
            # "Kansas City", "Old Town": the type word is part of the name
            cands = ix.get((st, name), []) or ix.get((st, jn), [])
            if lvl == 'cousub' and kind in ('township', 'charter township', 'twp'):
                cands = [c for c in cands if 'township' in c['NAME'].lower()]
            elif lvl == 'cousub' and kind in ('town', 'city', 'village'):
                cands = [c for c in cands if re.search(r'\b' + kind + r'\b', c['NAME'].lower())] or cands
            if kind == 'borough' and lvl == 'place':
                cands = [c for c in cands if 'borough' in c['NAME'].lower()] or cands
            if kind in ('city', 'town', 'village') and lvl == 'place':
                cands = [c for c in cands if re.search(r'\b' + kind + r'\b', c['NAME'].lower())] or cands
            h = pick(cands)
            if h is None and len(cands) > 1:
                h = by_county(cands, text, name)
            if h:
                return ('place' if lvl == 'place' else 'county_subdivision'), h['GEOID'], h['NAME']
            if lvl == 'cousub' and order[0] == 'cousub' and kind is not None:
                return None
        return None

    with open(src, encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    fields = list(rows[0].keys()) + ['geo_level', 'geoid', 'census_name']
    unmatched = []
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            text = ' '.join(r.get(k) or '' for k in r if k.startswith(('notes', 'source link')))
            res = match(r['jurisdiction'].strip(), r['state'].strip(), text)
            if res:
                r['geo_level'], r['geoid'], r['census_name'] = res
            else:
                r['geo_level'] = r['geoid'] = r['census_name'] = ''
                unmatched.append(f"{r['jurisdiction']} / {r['state']}")
            w.writerow(r)
    print(f'{len(rows) - len(unmatched)} of {len(rows)} matched', file=sys.stderr)
    for u in unmatched:
        print('  unmatched:', u, file=sys.stderr)


if __name__ == '__main__':
    main(*sys.argv[1:4])
