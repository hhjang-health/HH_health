"""Source-provided nutrients only. Missing is not zero; never estimate a meal."""
import json
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor


def number(value):
    try:
        result = float(str(value).replace(',', ''))
        return result if result >= 0 and result < float('inf') else None
    except (ValueError, TypeError):
        return None


def fresh_detail(data):
    fields = [('calories','kcal','caloriesYn'), ('protein','protein','proteinYn'),
              ('carbs','carb','carboYn'), ('fat','fat','fatYn'), ('sodium','salt','natriumYn')]
    return {key: number(data.get(source)) if data.get(flag) == 'Y' else None
            for key, source, flag in fields}


def welstory_html(document, target_date):
    """Read individual serialized records, not the markdown's summed alternatives.

    The existing public Welplan intermediary embeds its menu detail data as
    Svelte JS objects. Parse only data literals, never execute page JavaScript.
    """
    meals = {'breakfast': [], 'lunch': [], 'dinner': []}
    seen = set()
    for raw in re.findall(r'\bd\[\d+\]=(\{.*?\});', document, re.S):
        def key(match):
            token = match.group(0)
            if token.startswith('"'): return token
            return json.dumps(token[:-1]) + ':'
        encoded = re.sub(r'"(?:\\.|[^"\\])*"|\b[A-Za-z_$][\w$]*:', key, raw)
        try:
            item = json.loads(encoded)
        except ValueError:
            continue
        meal = {'1':'breakfast','2':'lunch','3':'dinner'}.get(str(item.get('mealTimeId')))
        record_key = (meal, item.get('id'))
        if not meal or item.get('date') != target_date or record_key in seen:
            continue
        # Welstory reuses a counter id (for example E537-AA) across breakfast,
        # lunch, and dinner. Deduplicate only inside the same meal period.
        seen.add(record_key)
        # Packaged alternatives are independent records, not a single huge meal.
        source = item.get('nutrition') or {}
        nutrients = {key: number(source.get(field)) for key, field in
                     [('calories','calories'), ('carbs','carbohydrates'),
                      ('sugar','sugar'), ('fiber','fiber'), ('protein','protein'),
                      ('fat','fat'), ('saturated_fat','saturatedFat'),
                      ('trans_fat','transFat'), ('sodium','sodium')]}
        name = item.get('name') or ''
        parts = list(dict.fromkeys([name] + [x.get('name','') for x in item.get('components',[])]))
        title = item.get('courseName') or item.get('cornerName') or ('간편식' if item.get('isTakeOut') else '오늘의 식단')
        meals[meal].append({'title':title, 'menu':' · '.join(p for p in parts if p),
                            'nutrition':nutrients, 'source_id':item.get('id'),
                            'course_type': str(item.get('courseType') or ''),
                            'detail_query': {k:item.get(k) for k in ('restaurantId','date','mealTimeId','hallNo','courseType')},
                            'source_note':'웰스토리 공개 중계 상세정보 · 코너명이 제공되지 않으면 임의로 추정하지 않습니다.'})
    # Welstory exposes the actual counter in courseType even though its text
    # title is frequently just “오늘의 식단”. These stable codes prevent the
    # menus from shifting when the public gallery adds convenience products.
    course_order = {
        'breakfast': (('AA', '한식사계'),),
        'lunch': (('AA', '한식사계'), ('BB', '모던키친'), ('HH', '별미공방')),
        'dinner': (('AA', '한식사계'), ('HH', '별미공방')),
    }
    output = {}
    for meal, rows in meals.items():
        selected = []
        for code, counter in course_order[meal]:
            row = next((item for item in rows if item['course_type'] == code), None)
            if row:
                selected.append({**row, 'title': counter})
        # Bare source fixtures lack courseType; preserve their individual
        # values rather than turning a temporary source schema change into an
        # empty menu.
        if not selected and rows and not any(item['course_type'] for item in rows):
            selected = rows
        output[meal] = json.dumps(selected, ensure_ascii=False)
    return output


def enrich_welstory(fetch, meals):
    decoded = {key:json.loads(value) for key,value in meals.items()}
    queries = {}
    for rows in decoded.values():
        for row in rows:
            query = row.get('detail_query') or {}
            if all(query.values()) and len(query)==5:
                queries[tuple(sorted(query.items()))] = query
    def retrieve(pair):
        key, query = pair
        query = dict(query)
        restaurant = query.pop('restaurantId')
        try:
            # This is the same component nutrition table opened by tapping a
            # menu card in Welplan; the default detail view omits carbs.
            query['nutrient'] = '1'
            payload = json.loads(fetch('https://welplan.pmh.codes/proxy/' + urllib.parse.quote(restaurant, safe='') +
                                '/menus/detail?' + urllib.parse.urlencode(query)))
            return key, payload if isinstance(payload,list) else []
        except Exception:
            return key, []
    with ThreadPoolExecutor(max_workers=3) as pool:
        details = dict(pool.map(retrieve, queries.items()))
    for rows in decoded.values():
        for row in rows:
            detail = details.get(tuple(sorted(row.get('detail_query',{}).items()))) or []
            if detail:
                # The response is one record per dish.  Sum each disclosed
                # value once, rather than showing only the first dish.
                fields = [('calories','calories'), ('carbs','carbohydrates'),
                          ('sugar','sugar'), ('fiber','fiber'), ('protein','protein'),
                          ('fat','fat'), ('saturated_fat','saturatedFat'),
                          ('trans_fat','transFat'), ('sodium','sodium')]
                for target, source in fields:
                    values = [number((entry.get('nutrition') or {}).get(source)) for entry in detail]
                    disclosed = [value for value in values if value is not None]
                    if disclosed:
                        row['nutrition'][target] = sum(disclosed)
                names = list(dict.fromkeys(x.get('name','') for x in detail))
                if names: row['menu'] = ' · '.join(names)
            else:
                row['source_note'] += '\n상세 서버가 응답하지 않아 목록에서 확인된 값만 표시합니다.'
    return {key:json.dumps(rows,ensure_ascii=False) for key,rows in decoded.items()}
