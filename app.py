import json, os, time
from collections import defaultdict, deque
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from flask import Flask, jsonify, request

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
API_URL = "https://apis.data.go.kr/1471000/FoodNtrCpntDbInfo03/getFoodNtrCpntDbInq03"
cache, visits = {}, defaultdict(deque)


def number(value):
    try:
        return float(str(value).replace(",", "")) if value not in (None, "", "-") else None
    except (TypeError, ValueError):
        return None


def first(item, *keys):
    for key in keys:
        value = item.get(key)
        if value not in (None, "", "-"):
            return value
    return None


def normalize(item):
    return {
        "name": first(item, "FOOD_NM_KR", "FOOD_NM") or "이름 미제공",
        "manufacturer": first(item, "MAKER_NM") or "",
        "category": first(item, "FOOD_CAT1_NM", "DB_CLASS_NM") or "기타",
        "calories": number(first(item, "AMT_NUM1", "ENERGY", "ENERC_KCAL")),
        "protein": number(first(item, "AMT_NUM3", "PROTEIN", "PROCNT")),
        "fat": number(first(item, "AMT_NUM4", "FAT", "FATCE")),
        "carbs": number(first(item, "AMT_NUM6", "CARBOHYDRATE", "CHOCDF")),
        "serving": str(first(item, "SERVING_SIZE", "SERVING_WT", "FOOD_SIZE") or ""),
        "source": "식품의약품안전처 식품영양성분DB",
    }


@app.get("/")
def health():
    return jsonify({"service": "hh-health", "status": "ok"})


@app.get("/api/nutrition-search")
def nutrition_search():
    query = " ".join((request.args.get("q") or "").split())
    if not query or len(query) > 80:
        return jsonify(error="검색어는 1~80자로 입력해 주세요.", items=[]), 400
    key = os.environ.get("FOOD_SAFETY_API_KEY")
    if not key:
        return jsonify(error="영양정보 검색 서비스가 아직 설정되지 않았습니다.", items=[]), 503
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    now = time.monotonic()
    history = visits[ip]
    while history and now - history[0] > 60:
        history.popleft()
    if len(history) >= 30:
        return jsonify(error="잠시 후 다시 검색해 주세요.", items=[]), 429
    history.append(now)
    saved = cache.get(query.casefold())
    if saved and now - saved[0] < 43200:
        return jsonify(items=saved[1], cached=True)
    params = urlencode({"serviceKey": key, "pageNo": 1, "numOfRows": 20, "type": "json", "FOOD_NM_KR": query})
    try:
        req = Request(API_URL + "?" + params, headers={"Accept": "application/json", "User-Agent": "HH-health/1.0"})
        with urlopen(req, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))
        body = data.get("response", data).get("body", {})
        items = body.get("items", [])
        if isinstance(items, dict):
            items = items.get("item", items.get("items", []))
        if isinstance(items, dict):
            items = [items]
        result = [normalize(item) for item in items if isinstance(item, dict)]
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        return jsonify(error="영양정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.", items=[]), 502
    cache[query.casefold()] = (now, result)
    return jsonify(items=result, cached=False)


@app.get("/api/app-update")
def app_update():
    return jsonify(version=os.environ.get("APP_RELEASE_VERSION", "0.0.0"), notes=os.environ.get("APP_RELEASE_NOTES", ""), apk_url=os.environ.get("APP_RELEASE_APK_URL", ""))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))

