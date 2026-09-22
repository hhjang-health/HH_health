import json, os, ssl, time
from collections import defaultdict, deque
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from flask import Flask, jsonify, request

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
API_URL = "https://apis.data.go.kr/1471000/FoodNtrCpntDbInfo03/getFoodNtrCpntDbInq03"
WELPLAN_BASE = "https://welplan.pmh.codes"
WELPLAN_HOST = "welplan.pmh.codes"
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

def _welplan_fetch(url, accept="application/json, text/plain, */*"):
    """Fetch one allow-listed public Welplan resource.

    The upstream public host currently serves an expired TLS certificate.  A
    narrowly scoped fallback is needed until that operator renews it; callers
    cannot supply an arbitrary host and the fetched data is public menu data.
    """
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != WELPLAN_HOST:
        raise ValueError("허용되지 않은 웰스토리 메뉴 주소입니다.")
    req = Request(url, headers={"Accept": accept, "User-Agent": "HH-health-menu/2.0"})
    try:
        with urlopen(req, timeout=15) as response:
            return response.read()
    except Exception as exc:
        reason = getattr(exc, "reason", exc)
        certificate_error = isinstance(reason, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(reason)
        if not certificate_error:
            raise
        # The fallback is deliberately restricted above to the one public
        # source.  It prevents an upstream certificate lapse from making the
        # in-app menu unavailable while preserving normal TLS verification for
        # every other request made by this service.
        with urlopen(req, timeout=15, context=ssl._create_unverified_context()) as response:
            return response.read()

@app.get("/api/welstory-menu")
def welstory_menu_proxy():
    path = str(request.args.get("path") or "")
    day = str(request.args.get("date") or "")
    if not path.startswith("/restaurants/") or any(token in path for token in ("?", "#", "..")) or len(day) != 8 or not day.isdigit():
        return jsonify(error="잘못된 웰스토리 메뉴 요청입니다."), 400
    try:
        encoded_path = quote(path.rstrip("/") + "/" + day, safe="/%")
        return app.response_class(_welplan_fetch(WELPLAN_BASE + encoded_path, "text/html, */*"), content_type="text/html; charset=utf-8")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        return jsonify(error="웰스토리 메뉴 서버에 연결하지 못했습니다."), 502

@app.get("/api/welstory-search")
def welstory_search_proxy():
    query = " ".join((request.args.get("q") or "").split())
    if not query or len(query) > 80:
        return jsonify(error="검색어는 1~80자로 입력해 주세요."), 400
    try:
        return app.response_class(_welplan_fetch(WELPLAN_BASE + "/proxy/search?" + urlencode({"q": query}), "application/json"), content_type="application/json; charset=utf-8")
    except (HTTPError, URLError, TimeoutError, OSError):
        return jsonify(error="웰스토리 식당 검색 서버에 연결하지 못했습니다."), 502

@app.get("/api/welstory-detail")
def welstory_detail_proxy():
    restaurant = str(request.args.get("restaurant") or "")
    allowed = {key: str(request.args[key]) for key in ("date", "mealTimeId", "hallNo", "courseType", "nutrient") if key in request.args}
    if not restaurant or len(restaurant) > 100 or not restaurant.replace("-", "").replace("_", "").isalnum() or not all(value and len(value) <= 40 for value in allowed.values()):
        return jsonify(error="잘못된 메뉴 상세 요청입니다."), 400
    try:
        url = WELPLAN_BASE + "/proxy/" + restaurant + "/menus/detail?" + urlencode(allowed)
        return app.response_class(_welplan_fetch(url, "application/json"), content_type="application/json; charset=utf-8")
    except (HTTPError, URLError, TimeoutError, OSError):
        return jsonify(error="웰스토리 상세 서버에 연결하지 못했습니다."), 502

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
