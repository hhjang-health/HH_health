"""Read WonderPul Plus's public restaurant/menu endpoints (no login data)."""
import html
import json
import re
from datetime import date
from menu_nutrition import number

BASE = 'https://puls2.pulmuone.com'
INTRO = '/src/sql/intro/intro_sql.php'
WEEK = '/src/sql/menu/week_sql.php'
NUTRIENT = '/src/sql/menu/nutrient_sql.php'


def request(fetch, path, action, params):
    return json.loads(fetch(BASE + path, referer=BASE + '/src/php/menu/week.php',
                           form={'requestId': action, 'requestUrl': path,
                                 'requestMode': '1', 'requestParam': json.dumps(params)}))


def search_sites(fetch, keyword):
    rows = request(fetch, INTRO, 'search_storeList', {}).get('storeList') or []
    term = re.sub(r'\s+', '', keyword).casefold()
    return [{'name': row[2], 'operator': row[0], 'assignment': row[1]}
            for row in rows if len(row) >= 3 and
            term in re.sub(r'\s+', '', row[2]).casefold()]


def detail_nutrition(fetch, operator, assignment, menu_date, time_code, shop_code):
    """Read the exact public payload behind WonderPul's green “…” button."""
    payload = request(fetch, NUTRIENT, 'search_menuDetail', {
        'srchOperCd': operator, 'srchAssignCd': assignment,
        'srchMenuDay': menu_date, 'srchTimeCd': time_code, 'srchShopCd': shop_code,
    })
    rows = payload.get('data') or []
    if not rows or len(rows[0]) < 6:
        return {}
    row = rows[0]
    fields = ('calories', 'sodium', 'carbs', 'protein', 'fat')
    return {name: value for name, raw in zip(fields, row[1:6])
            if (value := number(raw)) is not None}


def parse_menu(payload, menu_date, detail_lookup=None):
    """Keep source dates and kitchen names; never turn missing data into food."""
    keys = {'010': 'breakfast', '020': 'lunch', '030': 'dinner'}
    groups = {key: {} for key in keys.values()}
    for row in payload.get('data') or []:
        if len(row) < 6 or str(row[2]) != menu_date:
            continue
        key = keys.get(str(row[0]))
        counter = str(row[1]).strip()
        kitchen = re.fullmatch(r'(?:KITCHEN|키친|K)\s*([1-4])', counter, re.I)
        takeout = re.fullmatch(r'(?:TAKE\s*OUT|TAKEOUT|테이크\s*아웃)\s*([12])?', counter, re.I)
        if not key or not (kitchen or takeout):
            continue
        title = ('K' + kitchen[1]) if kitchen else ('Take Out' + (takeout[1] or ''))
        raw_parts = [html.unescape(re.sub(r'<[^>]+>', ' ', str(value))).strip()
                     for value in (row[3], row[5]) if value]
        parts = raw_parts
        menu = re.sub(r'\s+', ' ', ' · '.join(parts)).strip()
        if menu:
            # The weekly endpoint always exposes kcal at index 4.  Some
            # branches additionally attach a JSON nutrient payload behind the
            # app's “…” affordance.  Accept those extra fields when present;
            # never manufacture protein/carbohydrate values when they are not.
            nutrition = {'calories': number(row[4])}
            aliases = {
                'calorie': 'calories', 'calories': 'calories', 'kcal': 'calories', 'energy': 'calories',
                'protein': 'protein', 'proteins': 'protein', '단백질': 'protein',
                'carb': 'carbs', 'carbohydrate': 'carbs', 'carbohydrates': 'carbs', '탄수화물': 'carbs',
                'fat': 'fat', '지방': 'fat', 'sodium': 'sodium', '나트륨': 'sodium',
            }
            def collect(value):
                if isinstance(value, dict):
                    for source, raw in value.items():
                        target = aliases.get(str(source).strip().casefold())
                        parsed = number(raw)
                        if target and parsed is not None:
                            nutrition[target] = parsed
                        elif isinstance(raw, (dict, list)):
                            collect(raw)
                elif isinstance(value, list):
                    for child in value:
                        collect(child)
                elif isinstance(value, str) and value.lstrip().startswith(('{', '[')):
                    try:
                        collect(json.loads(value))
                    except (TypeError, ValueError):
                        pass
            for extra in row[30:]:
                collect(extra)
            # The weekly list exposes only calories.  The site deliberately
            # exposes the remaining values from its green “…” detail action;
            # use that same public response rather than estimating macros.
            if detail_lookup and len(row) > 13 and row[11] and row[13]:
                try:
                    nutrition.update(detail_lookup(str(row[11]), str(row[13])))
                # A single counter can legitimately have no published detail
                # record.  Keep its official kcal instead of failing the
                # whole cafeteria refresh.
                except Exception:
                    pass
            nutrition = {name: value for name, value in nutrition.items() if value is not None}
            # Keep the public fields as individually selectable foods as well
            # as the compact group summary.  ``row[3]`` is the main item and
            # ``row[5]`` is the published side/item list; flattening them here
            # made a whole Take Out counter behave as one inseparable choice.
            item_names = []
            for part in raw_parts:
                for segment in re.split(r'\s*(?:,|·|/|\\n)\s*', part):
                    # Take Out 1/2 are bundles.  The source sometimes uses
                    # whitespace alone between products, so keep each product
                    # selectable rather than merging the full line.
                    values = re.split(r'\s+', segment) if takeout else [segment]
                    for value in values:
                        value = re.sub(r'\s+', ' ', value).strip()
                        if value and value not in item_names:
                            item_names.append(value)
            # Counter-level nutrients describe the complete published tray,
            # not each child.  Reusing them per child would multiply calories
            # when a user selects two items, so only a one-item counter keeps
            # that exact value; multi-item choices are enriched per food.
            item_nutrition = dict(nutrition) if len(item_names) == 1 else {}
            items = [{'menu': value, 'nutrition': dict(item_nutrition)} for value in item_names]
            groups[key].setdefault(title, []).append({'menu':menu, 'nutrition':nutrition,
                'items': items,
                'source_note':'원더풀 플러스 공식 메뉴 영양정보 · 공개 응답에 없는 영양소는 미제공으로 표시합니다.'})
    return {key: json.dumps([{'title': title, **item}
                            for title, items in sorted(corners.items()) for item in items], ensure_ascii=False)
            for key, corners in groups.items()}


def fetch_menus(fetch, restaurant_name='삼성SDI동탄', menu_date=None):
    target = menu_date or date.today().strftime('%Y%m%d')
    sites = search_sites(fetch, restaurant_name)
    exact = [site for site in sites if re.sub(r'\s+', '', site['name']).casefold()
             == re.sub(r'\s+', '', restaurant_name).casefold()]
    if len(exact) != 1:
        raise ValueError('원더풀 플러스에서 해당 식당을 확인하지 못했어요.')
    site = exact[0]
    # Public selection resolves the opaque catalogue values to the real site codes.
    resolved = request(fetch, INTRO, 'search_pageStore', {
        'operCd': site['operator'], 'assignCd': site['assignment']}).get('storeList') or []
    if not resolved or len(resolved[0]) < 3 or resolved[0][2] != site['name']:
        raise ValueError('식당 선택 정보를 확인하지 못했어요.')
    row = resolved[0]
    payload = request(fetch, WEEK, 'search_week', {
        'topOperCd': row[0], 'topAssignCd': row[1], 'menuDay': target,
        'srchCurShopclsCd': '', 'custCd': ''})
    if 'data' not in payload or 'day' not in payload:
        raise ValueError('메뉴 서버 응답을 확인하지 못했어요.')
    detail_cache = {}
    def lookup(time_code, shop_code):
        key = (time_code, shop_code)
        if key not in detail_cache:
            detail_cache[key] = detail_nutrition(fetch, row[0], row[1], target, time_code, shop_code)
        return detail_cache[key]
    return parse_menu(payload, target, detail_lookup=lookup)
