"""Welltable: an offline-first Android meal and activity tracker.

This app is deliberately self-contained: all personal records live in SQLite on
the device. Health Connect integration is isolated in `HealthConnectBridge`,
which reads the user-approved records through the Android client API.
"""
from __future__ import annotations

import json
import math
import os
import random
import sqlite3
import re
import urllib.parse
import urllib.request
import webbrowser
from datetime import date, datetime, timedelta
from threading import Thread
from wonderplus import fetch_menus as fetch_wonderplus_menus, search_sites as search_wonderplus_sites
from menu_nutrition import fresh_detail, welstory_html, enrich_welstory

from kivy.app import App
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.text import LabelBase
from kivy.effects.scroll import ScrollEffect
from kivy.lang import Builder
from kivy.logger import Logger
from kivy.metrics import dp
from kivy.graphics import Color, Mesh, Line, Ellipse, RoundedRectangle
from kivy.graphics.texture import Texture
from kivy.properties import ListProperty, NumericProperty, StringProperty
from kivy.properties import BooleanProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.label import Label
from kivy.uix.popup import Popup as KivyPopup
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.stencilview import StencilView
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget


if os.environ.get('WELLTABLE_PREVIEW'):
    Window.size = (412, 892)


APP_DIR = os.path.dirname(os.path.abspath(__file__))
APP_VERSION = '2.0.9'

# Public service only.  The Food Safety Korea credential stays in Render's
# environment and is never included in the APK or requested from end users.
SERVICE_BASE_URL = 'https://hh-health.onrender.com'
NUTRITION_SEARCH_URL = SERVICE_BASE_URL + '/api/nutrition-search'
UPDATE_MANIFEST_URL = SERVICE_BASE_URL + '/api/app-update'


FOODS = [
    ("현미밥", "곡류", 210, 4.5, 45, 1.6, "180g"),
    ("닭가슴살", "단백질", 165, 31, 0, 3.6, "100g"),
    ("연어 구이", "단백질", 208, 20, 0, 13, "100g"),
    ("그릭 요거트", "유제품", 130, 15, 8, 3, "150g"),
    ("오트밀", "곡류", 155, 5, 27, 3, "40g"),
    ("바나나", "과일", 105, 1.3, 27, .4, "1개"),
    ("아보카도 토스트", "곡류", 280, 8, 33, 13, "1조각"),
    ("계란", "단백질", 92, 6.3, .4, 7, "1개"),
    ("닭가슴살 포케", "한식", 480, 35, 60, 11, "1그릇"),
    ("비빔밥", "한식", 560, 18, 86, 16, "1그릇"),
    ("두부 샐러드", "단백질", 190, 16, 12, 9, "1접시"),
    ("고등어 구이", "단백질", 265, 24, 0, 18, "120g"),
    ("고구마", "곡류", 128, 2.4, 30, .2, "150g"),
    ("브로콜리", "채소", 35, 2.4, 7, .4, "100g"),
    ("된장국", "한식", 75, 6, 8, 2, "1그릇"),
]

# Typical per-serving values.  The library is deliberately broad enough for
# Korean home meals, convenience foods, and common diet staples; values are
# practical estimates rather than medical prescriptions.
FOODS += [
    ("가자미 구이", "수산물", 172, 24, 0, 7, "100g"), ("갈비탕", "한식", 410, 29, 25, 23, "1그릇"),
    ("감자", "곡류", 130, 3, 30, .2, "180g"), ("검은콩밥", "곡류", 245, 7, 49, 2, "1공기"),
    ("계란찜", "단백질", 160, 13, 5, 10, "1인분"), ("고구마말랭이", "간식", 160, 2, 38, .3, "60g"),
    ("고등어 조림", "수산물", 310, 25, 12, 18, "1인분"), ("곤약밥", "곡류", 110, 2, 24, .2, "150g"),
    ("곰탕", "한식", 330, 24, 28, 13, "1그릇"), ("귀리밥", "곡류", 220, 5, 46, 2, "1공기"),
    ("그린 샐러드", "채소", 80, 3, 12, 3, "1접시"), ("김", "반찬", 25, 2, 1, 2, "5g"),
    ("김밥", "한식", 485, 15, 76, 14, "1줄"), ("김치", "반찬", 35, 2, 7, .4, "100g"),
    ("깍두기", "반찬", 28, 1, 6, .1, "100g"), ("깻잎", "채소", 16, 2, 2, .3, "30g"),
    ("나물 비빔밥", "한식", 520, 17, 82, 14, "1그릇"), ("날치알 주먹밥", "한식", 310, 9, 53, 7, "1개"),
    ("닭가슴살 샌드위치", "간편식", 390, 29, 42, 12, "1개"), ("닭다리살 구이", "단백질", 250, 26, 2, 15, "150g"),
    ("닭볶음탕", "한식", 380, 31, 20, 19, "1인분"), ("닭죽", "한식", 330, 20, 52, 6, "1그릇"),
    ("단백질 쉐이크", "간식", 170, 25, 10, 3, "1병"), ("단호박", "채소", 66, 1, 16, .2, "150g"),
    ("두부김치", "한식", 270, 19, 13, 16, "1인분"), ("두유", "유제품", 135, 8, 13, 5, "190ml"),
    ("딸기", "과일", 50, 1, 12, .4, "150g"), ("라떼 무가당", "음료", 110, 7, 10, 4, "1잔"),
    ("렌틸콩 샐러드", "채소", 260, 15, 38, 6, "1접시"), ("메밀국수", "한식", 430, 16, 76, 7, "1그릇"),
    ("멸치볶음", "반찬", 100, 12, 6, 4, "50g"), ("목살 구이", "단백질", 360, 28, 0, 27, "150g"),
    ("무가당 아몬드밀크", "음료", 45, 2, 2, 3, "190ml"), ("미역국", "한식", 95, 8, 5, 4, "1그릇"),
    ("바질 닭가슴살 파스타", "양식", 540, 35, 66, 15, "1접시"), ("방울토마토", "채소", 30, 1, 7, .3, "150g"),
    ("배", "과일", 102, 1, 27, .2, "1개"), ("버섯볶음", "채소", 74, 4, 9, 3, "100g"),
    ("보리밥", "곡류", 215, 5, 45, 1, "1공기"), ("보쌈", "단백질", 430, 33, 3, 30, "150g"),
    ("부추전", "한식", 290, 8, 35, 13, "1장"), ("북엇국", "한식", 120, 18, 8, 2, "1그릇"),
    ("불고기", "한식", 350, 27, 18, 19, "150g"), ("브라운 라이스볼", "간편식", 465, 28, 68, 10, "1그릇"),
    ("사과", "과일", 95, .5, 25, .3, "1개"), ("새우", "수산물", 100, 24, .2, .5, "100g"),
    ("샐러드 파스타", "양식", 420, 16, 60, 13, "1접시"), ("소고기 안심", "단백질", 270, 31, 0, 16, "150g"),
    ("소고기무국", "한식", 180, 19, 11, 7, "1그릇"), ("순두부찌개", "한식", 290, 20, 18, 14, "1그릇"),
    ("스키르 요거트", "유제품", 120, 17, 8, .5, "150g"), ("시금치나물", "반찬", 55, 3, 5, 3, "80g"),
    ("아메리카노", "음료", 10, 0, 2, 0, "1잔"), ("애호박볶음", "반찬", 65, 2, 6, 4, "100g"),
    ("양배추 샐러드", "채소", 92, 2, 12, 4, "1접시"), ("연두부", "단백질", 110, 10, 5, 6, "200g"),
    ("오렌지", "과일", 62, 1, 15, .2, "1개"), ("오이", "채소", 18, 1, 4, .1, "150g"),
    ("오징어볶음", "수산물", 245, 25, 18, 9, "150g"), ("우삼겹", "단백질", 480, 24, 1, 42, "150g"),
    ("유부초밥", "한식", 360, 10, 62, 8, "4개"), ("잡곡밥", "곡류", 230, 5, 48, 2, "1공기"),
    ("장어구이", "수산물", 330, 23, 12, 22, "150g"), ("저지방 우유", "유제품", 100, 8, 12, 2, "200ml"),
    ("제육볶음", "한식", 405, 29, 20, 23, "150g"), ("조기 구이", "수산물", 190, 25, 0, 9, "100g"),
    ("참치 샐러드", "단백질", 245, 25, 13, 10, "1접시"), ("참치캔 물", "단백질", 140, 31, 0, 1, "100g"),
    ("체리", "과일", 90, 1, 22, .3, "150g"), ("치아씨드 푸딩", "간식", 220, 8, 25, 10, "1컵"),
    ("콩나물국", "한식", 70, 7, 8, 2, "1그릇"), ("콩국수", "한식", 520, 23, 59, 22, "1그릇"),
    ("퀴노아 샐러드", "채소", 310, 11, 43, 11, "1접시"), ("키위", "과일", 62, 1, 15, .5, "1개"),
    ("통밀빵", "곡류", 130, 5, 24, 2, "2조각"), ("토마토 달걀볶음", "한식", 210, 14, 10, 12, "1인분"),
    ("토마토 파스타", "양식", 470, 17, 77, 10, "1접시"), ("파프리카", "채소", 35, 1, 8, .3, "150g"),
    ("현미 주먹밥", "간편식", 260, 8, 48, 4, "1개"), ("훈제오리", "단백질", 310, 25, 3, 22, "150g"),
]

# Frequently available Korean RTD protein drinks.  Values are per labelled
# package; flavours and renewed packaging can vary, so users can still add
# the exact product from its nutrition label.
FOODS += [
    ('셀렉스 프로핏 스포츠 초콜릿', '간편식 · 단백질 음료', 135, 20, 10, 2, '250ml'),
    ('셀렉스 프로핏 스파클링', '간편식 · 단백질 음료', 95, 20, 3, 0, '245ml'),
    ('빙그레 더단백 드링크 커피', '간편식 · 단백질 음료', 165, 20, 11, 3, '250ml'),
    ('빙그레 더단백 워터프로틴', '간편식 · 단백질 음료', 95, 20, 3, 0, '500ml'),
    ('닥터유PRO 단백질 드링크', '간편식 · 단백질 음료', 160, 24, 12, 3, '250ml'),
    ('테이크핏 맥스 초코', '간편식 · 단백질 음료', 210, 24, 16, 5, '250ml'),
    ('테이크핏 몬스터', '간편식 · 단백질 음료', 260, 43, 15, 5, '350ml'),
    ('마이밀 퓨로틴', '간편식 · 단백질 음료', 150, 20, 12, 4, '250ml'),
    ('뉴케어 스포식스', '간편식 · 단백질 음료', 165, 20, 15, 3, '250ml'),
    ('하이뮨 프로틴 밸런스', '간편식 · 단백질 음료', 150, 20, 12, 3, '250ml'),
    ('황성주 이롬 고단백 두유 Pro 24', '간편식 · 단백질 음료', 165, 24, 11, 4, '190ml'),
    ('얼티브 프로틴 단백질 쌀밥맛', '간편식 · 단백질 음료', 150, 20, 15, 2, '250ml'),
    ('오트몬드 프로틴', '간편식 · 단백질 음료', 120, 21, 8, 2, '250ml'),
    ('하림 오늘단백 라떼', '간편식 · 단백질 음료', 130, 20, 9, 2, '250ml'),
]

FOODS += [
    ('아메리카노', '카페 음료', 10,0,2,0,'Tall 355ml'),('카페라떼', '카페 음료',180,10,18,8,'Tall 355ml'),('바닐라 라떼','카페 음료',280,10,38,10,'Tall 355ml'),('콜드브루','카페 음료',5,0,1,0,'355ml'),('카페 모카','카페 음료',330,11,45,12,'Tall 355ml'),('말차 라떼','카페 음료',290,10,42,9,'Tall 355ml'),('자몽 허니 블랙티','카페 음료',245,1,58,0,'Tall 355ml'),('딸기 요거트 블렌디드','카페 음료',340,8,68,5,'Tall 355ml'),('초콜릿 쉐이크','카페 음료',410,10,65,13,'Tall 355ml'),
    ('치즈케이크','디저트',420,7,35,28,'1조각'),('티라미수','디저트',380,6,42,20,'1조각'),('크루아상','베이커리',270,5,30,15,'1개'),('소금빵','베이커리',250,6,33,11,'1개'),('통밀 식빵','베이커리',135,5,25,2,'2쪽'),('베이글','베이커리',280,10,56,2,'1개'),('머핀','베이커리',420,6,57,19,'1개'),('도넛','베이커리',290,4,37,15,'1개'),('마카롱','디저트',105,2,13,5,'1개'),('쿠키','디저트',160,2,21,8,'1개'),
    ('김치찌개','한식',350,23,24,18,'1그릇'),('불고기 덮밥','한식',620,28,87,18,'1그릇'),('삼겹살','한식',520,28,0,43,'180g'),('설렁탕','한식',420,28,45,14,'1그릇'),('냉면','한식',480,17,91,7,'1그릇'),('떡볶이','한식',380,8,76,6,'1인분'),('잡채','한식',350,10,54,12,'1접시'),('삼계탕','한식',780,55,45,40,'1그릇'),
    ('짜장면','중식',760,20,116,24,'1그릇'),('짬뽕','중식',620,27,85,19,'1그릇'),('탕수육','중식',620,29,66,27,'1인분'),('마파두부','중식',430,21,29,27,'1인분'),('볶음밥','중식',680,17,96,26,'1그릇'),('군만두','중식',420,14,49,19,'8개'),
    ('알리오 올리오','양식',560,16,75,22,'1접시'),('까르보나라','양식',820,27,86,39,'1접시'),('토마토 파스타','양식',600,20,93,18,'1접시'),('리조또','양식',650,19,85,26,'1접시'),('스테이크','양식',540,45,18,31,'200g'),('치킨 샐러드','양식',390,35,24,18,'1접시'),('피자','양식',285,12,34,13,'1조각'),('햄버거','양식',610,31,52,32,'1개'),
]

# Packaged-food entries use each manufacturer's labelled single-serving value;
# users can still add the exact variant they buy below.
FOODS += [
    ('농심 신라면 컵', '간편식 · 컵라면', 300, 6, 47, 10, '1컵 65g'),
    ('농심 육개장 사발면', '간편식 · 컵라면', 375, 7, 52, 16, '1컵 86g'),
    ('오뚜기 진라면 매운맛 컵', '간편식 · 컵라면', 310, 6, 48, 10, '1컵 65g'),
    ('팔도 왕뚜껑', '간편식 · 컵라면', 490, 10, 74, 17, '1컵 110g'),
    ('삼양 큰컵 불닭볶음면', '간편식 · 컵라면', 425, 8, 63, 16, '1컵 105g'),
    ('빙그레 더단백 드링크 초코', '간편식 · 단백질 음료', 160, 20, 10, 3, '250ml'),
    ('매일 셀렉스 프로핏', '간편식 · 단백질 음료', 100, 20, 3, 1, '250ml'),
    ('랩노쉬 프로틴 드링크', '간편식 · 단백질 음료', 150, 20, 12, 3, '250ml'),
    ('마이밀 마시는 뉴프로틴', '간편식 · 단백질 음료', 130, 18, 10, 2, '190ml'),
]

# Popular Korean franchise items.  These are single-menu portions (not a set
# with fries or a drink); recipe and packaging renewals can change nutrition,
# so the serving is kept explicit for easy comparison in the meal picker.
FOODS += [
    ('맥도날드 빅맥', '프랜차이즈 · 맥도날드', 583, 27, 48, 33, '단품 1개'),
    ('맥도날드 맥스파이시 상하이 버거', '프랜차이즈 · 맥도날드', 467, 23, 50, 22, '단품 1개'),
    ('맥도날드 슈슈 버거', '프랜차이즈 · 맥도날드', 432, 15, 51, 19, '단품 1개'),
    ('맥도날드 맥너겟 6조각', '프랜차이즈 · 맥도날드', 261, 16, 14, 16, '6조각'),
    ('맥도날드 후렌치 후라이 M', '프랜차이즈 · 맥도날드', 352, 4, 47, 16, 'M'),
    ('써브웨이 에그마요 15cm', '프랜차이즈 · 써브웨이', 416, 16, 48, 18, '15cm · 기본 빵'),
    ('써브웨이 로티세리 바비큐 치킨 15cm', '프랜차이즈 · 써브웨이', 351, 28, 49, 8, '15cm · 기본 빵'),
    ('써브웨이 터키 15cm', '프랜차이즈 · 써브웨이', 280, 18, 46, 4, '15cm · 기본 빵'),
    ('써브웨이 스테이크 앤 치즈 15cm', '프랜차이즈 · 써브웨이', 356, 25, 47, 9, '15cm · 기본 빵'),
    # 15cm sandwich values are the standard menu baseline.  Bread, cheese,
    # extra topping and sauce selections are separately loggable below.
    ('써브웨이 이탈리안 비엠티 15cm', '프랜차이즈 · 써브웨이', 410, 20, 48, 20, '15cm · 기본 빵'),
    ('써브웨이 비엘티 15cm', '프랜차이즈 · 써브웨이', 300, 15, 47, 10, '15cm · 기본 빵'),
    ('써브웨이 햄 15cm', '프랜차이즈 · 써브웨이', 262, 18, 46, 5, '15cm · 기본 빵'),
    ('써브웨이 치킨 슬라이스 15cm', '프랜차이즈 · 써브웨이', 320, 25, 46, 7, '15cm · 기본 빵'),
    ('써브웨이 치킨 데리야끼 15cm', '프랜차이즈 · 써브웨이', 370, 26, 57, 8, '15cm · 기본 빵'),
    ('써브웨이 로티세리 치킨 15cm', '프랜차이즈 · 써브웨이', 310, 28, 46, 6, '15cm · 기본 빵'),
    ('써브웨이 쉬림프 15cm', '프랜차이즈 · 써브웨이', 282, 20, 46, 5, '15cm · 기본 빵'),
    ('써브웨이 참치 15cm', '프랜차이즈 · 써브웨이', 480, 22, 48, 24, '15cm · 기본 빵'),
    ('써브웨이 터키 베이컨 아보카도 15cm', '프랜차이즈 · 써브웨이', 355, 23, 47, 12, '15cm · 기본 빵'),
    ('써브웨이 베지 딜라이트 15cm', '프랜차이즈 · 써브웨이', 230, 10, 44, 3, '15cm · 기본 빵'),
    ('써브웨이 스파이시 이탈리안 15cm', '프랜차이즈 · 써브웨이', 480, 21, 49, 26, '15cm · 기본 빵'),
    ('써브웨이 K-바비큐 15cm', '프랜차이즈 · 써브웨이', 375, 25, 54, 9, '15cm · 기본 빵'),
    ('써브웨이 치킨 베이컨 미니 랩', '프랜차이즈 · 써브웨이', 376, 18, 31, 17, '1개'),
    ('써브웨이 화이트 빵', '프랜차이즈 · 써브웨이 재료', 195, 7, 39, 2, '15cm 1개'),
    ('써브웨이 위트 빵', '프랜차이즈 · 써브웨이 재료', 195, 8, 39, 2, '15cm 1개'),
    ('써브웨이 허니오트 빵', '프랜차이즈 · 써브웨이 재료', 237, 9, 46, 3, '15cm 1개'),
    ('써브웨이 플랫브레드', '프랜차이즈 · 써브웨이 재료', 232, 8, 42, 4, '15cm 1개'),
    ('써브웨이 아메리칸 치즈', '프랜차이즈 · 써브웨이 재료', 35, 2, 1, 3, '1장'),
    ('써브웨이 슈레드 치즈', '프랜차이즈 · 써브웨이 재료', 54, 3, 1, 4, '1회'),
    ('써브웨이 스위트 어니언 소스', '프랜차이즈 · 써브웨이 재료', 40, 0, 10, 0, '1회'),
    ('써브웨이 사우스웨스트 치폴레 소스', '프랜차이즈 · 써브웨이 재료', 97, 0, 4, 9, '1회'),
    ('써브웨이 랜치 소스', '프랜차이즈 · 써브웨이 재료', 116, 1, 2, 12, '1회'),
    ('써브웨이 저칼로리 오리엔탈 소스', '프랜차이즈 · 써브웨이 재료', 21, 0, 4, 1, '1회'),
    ('BBQ 황금올리브치킨', '프랜차이즈 · BBQ', 249, 19, 6, 17, '100g · 뼈 포함'),
    ('BBQ 황금올리브 핫윙', '프랜차이즈 · BBQ', 184, 12, 7, 12, '3조각'),
    ('BBQ 자메이카 통다리구이', '프랜차이즈 · BBQ', 280, 24, 8, 16, '1조각'),
    ('BHC 뿌링클', '프랜차이즈 · BHC', 286, 18, 12, 19, '100g · 뼈 포함'),
    ('BHC 맛초킹', '프랜차이즈 · BHC', 273, 18, 16, 16, '100g · 뼈 포함'),
    ('교촌 허니콤보', '프랜차이즈 · 교촌치킨', 318, 17, 22, 19, '100g · 뼈 포함'),
    ('교촌 레드콤보', '프랜차이즈 · 교촌치킨', 303, 18, 14, 19, '100g · 뼈 포함'),
    ('굽네 고추바사삭', '프랜차이즈 · 굽네치킨', 221, 22, 10, 11, '100g · 뼈 포함'),
    ('KFC 징거버거', '프랜차이즈 · KFC', 498, 24, 53, 21, '단품 1개'),
    ('KFC 핫크리스피 치킨', '프랜차이즈 · KFC', 274, 20, 10, 18, '1조각'),
    ('롯데리아 리아 불고기', '프랜차이즈 · 롯데리아', 462, 21, 48, 21, '단품 1개'),
    ('롯데리아 한우불고기버거', '프랜차이즈 · 롯데리아', 572, 23, 51, 31, '단품 1개'),
    ('롯데리아 리아 새우', '프랜차이즈 · 롯데리아', 473, 15, 53, 19, '단품 1개'),
    ('맘스터치 싸이버거', '프랜차이즈 · 맘스터치', 594, 28, 54, 29, '단품 1개'),
    ('맘스터치 딥치즈 싸이버거', '프랜차이즈 · 맘스터치', 680, 32, 58, 36, '단품 1개'),
    ('도미노 페퍼로니 피자', '프랜차이즈 · 도미노피자', 304, 13, 34, 15, '1조각'),
    ('피자헛 직화불고기 피자', '프랜차이즈 · 피자헛', 321, 14, 38, 15, '1조각'),
    ('한솥 치킨마요', '프랜차이즈 · 한솥', 734, 28, 91, 27, '1개'),
    ('한솥 돈까스도련님', '프랜차이즈 · 한솥', 820, 29, 109, 29, '1개'),
    ('김가네 참치김밥', '프랜차이즈 · 김가네', 536, 17, 74, 18, '1줄'),
    ('신전떡볶이', '프랜차이즈 · 신전떡볶이', 503, 9, 100, 7, '1인분'),
]

# Standard sets use the listed main item + regular side + zero-calorie drink.
# This lets users log a common order without accidentally treating it as a
# single burger or sandwich.
FOODS += [
    ('맥도날드 빅맥 세트', '프랜차이즈 세트 · 맥도날드', 935, 31, 95, 49, '빅맥 + 후렌치후라이 M + 제로 음료'),
    ('맥도날드 상하이 버거 세트', '프랜차이즈 세트 · 맥도날드', 819, 27, 97, 38, '상하이 버거 + 후렌치후라이 M + 제로 음료'),
    ('맥도날드 슈슈 버거 세트', '프랜차이즈 세트 · 맥도날드', 784, 19, 98, 35, '슈슈 버거 + 후렌치후라이 M + 제로 음료'),
    ('롯데리아 리아 불고기 세트', '프랜차이즈 세트 · 롯데리아', 884, 25, 101, 39, '리아 불고기 + 포테이토 R + 제로 음료'),
    ('롯데리아 리아 새우 세트', '프랜차이즈 세트 · 롯데리아', 895, 19, 106, 37, '리아 새우 + 포테이토 R + 제로 음료'),
    ('맘스터치 싸이버거 세트', '프랜차이즈 세트 · 맘스터치', 1_005, 33, 103, 51, '싸이버거 + 케이준양념감자 + 제로 음료'),
    ('KFC 징거버거 세트', '프랜차이즈 세트 · KFC', 848, 28, 94, 38, '징거버거 + 프라이 + 제로 음료'),
    ('써브웨이 에그마요 세트', '프랜차이즈 세트 · 써브웨이', 646, 21, 79, 27, '에그마요 15cm + 쿠키 + 제로 음료'),
    ('써브웨이 로티세리 바비큐 치킨 세트', '프랜차이즈 세트 · 써브웨이', 581, 33, 80, 17, '15cm + 쿠키 + 제로 음료'),
    ('한솥 치킨마요 곱빼기', '프랜차이즈 세트 · 한솥', 959, 35, 118, 35, '치킨마요 + 밥 곱빼기'),
    ('신전떡볶이 세트', '프랜차이즈 세트 · 신전떡볶이', 938, 18, 165, 24, '떡볶이 + 튀김 3종 + 순대'),
    ('BBQ 황금올리브 반마리 세트', '프랜차이즈 세트 · BBQ', 1_245, 95, 30, 85, '치킨 반마리 + 제로 음료'),
    ('BHC 뿌링클 반마리 세트', '프랜차이즈 세트 · BHC', 1_430, 90, 60, 95, '치킨 반마리 + 제로 음료'),
    ('교촌 허니콤보 반마리 세트', '프랜차이즈 세트 · 교촌치킨', 1_590, 85, 110, 95, '치킨 반마리 + 제로 음료'),
    ('도미노 피자 2조각 세트', '프랜차이즈 세트 · 도미노피자', 808, 30, 92, 40, '피자 2조각 + 제로 음료'),
    ('피자헛 피자 2조각 세트', '프랜차이즈 세트 · 피자헛', 842, 32, 102, 40, '피자 2조각 + 제로 음료'),
]

FOODS += [
    ('스타벅스 카페 라떼 Tall', '프랜차이즈 · 스타벅스', 180, 10, 18, 8, 'Tall 355ml'),
    ('스타벅스 자몽 허니 블랙 티 Tall', '프랜차이즈 · 스타벅스', 245, 1, 58, 0, 'Tall 355ml'),
    ('스타벅스 자바 칩 프라푸치노 Tall', '프랜차이즈 · 스타벅스', 340, 6, 63, 10, 'Tall 355ml'),
    ('스타벅스 치킨 베이컨 랩', '프랜차이즈 · 스타벅스', 366, 20, 35, 16, '1개'),
    ('투썸플레이스 스트로베리 초콜릿 생크림', '프랜차이즈 · 투썸플레이스', 475, 6, 43, 31, '1조각'),
    ('투썸플레이스 아이스 카페라떼', '프랜차이즈 · 투썸플레이스', 170, 9, 19, 7, 'Regular'),
    ('메가MGC커피 아이스 아메리카노', '프랜차이즈 · 메가MGC커피', 13, 0, 3, 0, '20oz'),
    ('메가MGC커피 딸기라떼', '프랜차이즈 · 메가MGC커피', 362, 8, 66, 7, '20oz'),
    ('빽다방 원조커피', '프랜차이즈 · 빽다방', 330, 3, 65, 5, 'Large'),
    ('빽다방 사라다빵', '프랜차이즈 · 빽다방', 465, 13, 58, 20, '1개'),
    ('이디야 카페라떼', '프랜차이즈 · 이디야', 190, 10, 21, 8, 'Regular'),
    ('이디야 흑당 버블티', '프랜차이즈 · 이디야', 437, 6, 82, 8, 'Regular'),
    ('홍콩반점 짜장면', '프랜차이즈 · 홍콩반점', 760, 20, 116, 24, '1그릇'),
    ('홍콩반점 짬뽕', '프랜차이즈 · 홍콩반점', 620, 27, 85, 19, '1그릇'),
    ('역전우동 옛날우동', '프랜차이즈 · 역전우동', 480, 14, 88, 9, '1그릇'),
    ('롤링파스타 매운 크림 파스타', '프랜차이즈 · 롤링파스타', 780, 22, 92, 34, '1접시'),
    ('본죽 쇠고기야채죽', '프랜차이즈 · 본죽', 680, 28, 118, 12, '1그릇'),
    ('본죽 단호박죽', '프랜차이즈 · 본죽', 560, 9, 120, 8, '1그릇'),
    ('명륜진사갈비 돼지갈비', '프랜차이즈 · 명륜진사갈비', 540, 31, 25, 36, '200g'),
    ('샐러디 탄단지 샐러드', '프랜차이즈 · 샐러디', 410, 31, 39, 15, '1개'),
    ('포케올데이 닭가슴살 포케', '프랜차이즈 · 포케', 460, 36, 58, 11, '1그릇'),
    ('GS25 참치마요 삼각김밥', '프랜차이즈 · 편의점', 198, 4, 35, 5, '1개'),
    ('CU 득템 닭가슴살', '프랜차이즈 · 편의점', 135, 25, 2, 2, '100g'),
    ('세븐일레븐 도시락', '프랜차이즈 · 편의점', 720, 28, 94, 28, '1개'),
    # Common single-serving convenience-store sandwiches.  Product recipes
    # can change; the serving label makes it clear what each entry represents.
    ('CU 참치마요 샌드위치', '편의점 샌드위치', 395, 14, 48, 17, '1개'),
    ('CU 에그햄 샌드위치', '편의점 샌드위치', 410, 16, 45, 19, '1개'),
    ('CU 닭가슴살 에그 샌드위치', '편의점 샌드위치', 345, 24, 39, 11, '1개'),
    ('CU 햄치즈 샌드위치', '편의점 샌드위치', 385, 17, 42, 17, '1개'),
    ('GS25 참치마요 샌드위치', '편의점 샌드위치', 405, 15, 49, 18, '1개'),
    ('GS25 에그듬뿍 샌드위치', '편의점 샌드위치', 370, 17, 40, 16, '1개'),
    ('GS25 치킨텐더 샌드위치', '편의점 샌드위치', 420, 21, 46, 18, '1개'),
    ('GS25 BLT 샌드위치', '편의점 샌드위치', 355, 18, 39, 15, '1개'),
    ('세븐일레븐 에그마요 샌드위치', '편의점 샌드위치', 390, 15, 43, 18, '1개'),
    ('세븐일레븐 햄치즈 샌드위치', '편의점 샌드위치', 365, 16, 40, 16, '1개'),
    ('이마트24 닭가슴살 샌드위치', '편의점 샌드위치', 330, 23, 38, 10, '1개'),
    ('이마트24 데리야끼치킨 샌드위치', '편의점 샌드위치', 415, 20, 52, 15, '1개'),
]

FOODS += [
    ('참이슬 후레쉬', '주류', 327, 0, 0, 0, '1병 360ml'),
    ('처음처럼', '주류', 326, 0, 0, 0, '1병 360ml'),
    ('진로', '주류', 320, 0, 0, 0, '1병 360ml'),
    ('새로', '주류', 320, 0, 0, 0, '1병 360ml'),
    ('막걸리', '주류', 230, 2, 28, 0, '1병 750ml'),
    ('장수막걸리', '주류', 460, 4, 56, 0, '1병 750ml'),
    ('카스 프레시', '주류', 185, 1, 14, 0, '500ml'),
    ('테라', '주류', 190, 1, 15, 0, '500ml'),
    ('켈리', '주류', 190, 1, 15, 0, '500ml'),
    ('하이트', '주류', 185, 1, 14, 0, '500ml'),
    ('클라우드', '주류', 210, 1, 17, 0, '500ml'),
    ('칭따오', '주류', 190, 1, 15, 0, '500ml'),
    ('하이네켄', '주류', 210, 1, 16, 0, '500ml'),
    ('기네스 드래프트', '주류', 210, 2, 18, 0, '440ml'),
    ('레드와인', '주류', 125, 0, 4, 0, '1잔 150ml'),
    ('화이트와인', '주류', 121, 0, 4, 0, '1잔 150ml'),
    ('샴페인', '주류', 95, 0, 2, 0, '1잔 120ml'),
    ('위스키', '주류', 105, 0, 0, 0, '1잔 45ml'),
    ('보드카', '주류', 97, 0, 0, 0, '1잔 45ml'),
    ('하이볼', '주류', 150, 0, 10, 0, '1잔 300ml'),
]

# Store names are already part of the food name.  Keep the category short and
# sort the complete built-in library once so the picker is predictable.
FOODS = sorted(
    [(name, category.replace('프랜차이즈 세트 · ', '').replace('프랜차이즈 · ', ''), calories, protein, carbs, fat, serving)
     for name, category, calories, protein, carbs, fat, serving in FOODS],
    key=lambda item: item[0],
)

# CJ FreshMeal exposes the public meal feed separately from the member-only
# features of its app.  Store the verified numeric id, never a user's account
# token, so the app can safely show the cafeteria's published daily menu.
FRESHMEAL_SITES = (
    {
        'key': 'semes-hwaseong',
        'store_id': '6525',
        'name': '세메스 화성사업장',
        'aliases': ('세메스', 'semes', '화성', '반월'),
        'address': '경기 화성시 효행로 1339 · 지하 1층 사내식당',
    },
)

# 풀무원푸드앤컬처는 원더풀(WonderPul)에서 사업장별 급식 메뉴를
# 제공한다. 사업장 목록은 고정하지 않고 공개 식당 색인에서 검색해
# 동기화한다. 그래야 신규/변경 사업장이 앱 업데이트 없이 반영된다.
PULMUONE_PROVIDER = 'pulmuone'
WONDERPLUS_PROVIDER = 'wonderplus'
PROVIDER_LABELS = {
    'welstory': '삼성웰스토리',
    'freshmeal': 'CJ 프레시밀',
    PULMUONE_PROVIDER: '풀무원 푸드앤컬처',
    WONDERPLUS_PROVIDER: '원더풀 플러스',
}
# The compact Welstory view intentionally exposes only the three actual
# restaurant counters the user uses; all other public feed rows are omitted.
# Keep the names in one place so the parser and the display upgrade together.
WELSTORY_HOME_GROUPS = ('한식사계', '별미공방', '모던키친')

# WonderPul's business-site catalogue is account-scoped, so it cannot be
# searched through the unrelated Welstory index. These sites publish their
# Food & Culture menu openly and retain their real source URL.
PULMUONE_PUBLIC_SITES = (
    {
        'key': 'postech-pal',
        'name': '포항가속기연구소 구내식당',
        'aliases': ('포항가속기', '가속기', 'postech', '포항', 'pal'),
        'menu_url': 'https://paleng.postech.ac.kr/ko/info/rstrnt.do',
        'address': '경북 포항시 남구 지곡로127번길 65',
    },
)
WONDERPLUS_SITES = (
    {
        'key': 'samsung-sdi-dongtan',
        'name': '삼성SDI 동탄',
        'aliases': ('삼성sdi', 'sdi', '동탄', '삼성sdi동탄'),
        'address': '원더풀 플러스 사업장',
    },
)


SET_SEEDS = [
    ("아침 01", "breakfast", ["그릭 요거트", "오트밀", "바나나"]),
    ("아침 02", "breakfast", ["계란", "아보카도 토스트", "현미밥"]),
    ("아침 03", "breakfast", ["현미밥", "닭가슴살", "브로콜리"]),
    ("점심 01", "lunch", ["닭가슴살 포케", "된장국"]),
    ("점심 02", "lunch", ["비빔밥", "두부 샐러드"]),
    ("점심 03", "lunch", ["닭가슴살", "현미밥", "브로콜리"]),
    ("저녁 01", "dinner", ["연어 구이", "고구마", "브로콜리"]),
    ("저녁 02", "dinner", ["고등어 구이", "현미밥", "된장국"]),
    ("저녁 03", "dinner", ["두부 샐러드", "고구마", "계란"]),
]


class Store:
    @staticmethod
    def compact_food_names(foods):
        """Keep order while rendering duplicate portions as a count."""
        counts, order = {}, []
        for food in foods:
            name = str(food.get('name') or '').strip()
            if not name:
                continue
            if name not in counts:
                counts[name] = 0
                order.append(name)
            counts[name] += 1
        return ' · '.join(name if counts[name] == 1 else f'{name} × {counts[name]}' for name in order)

    def __init__(self, path):
        # Android's app bundle is read-only after installation. Personal
        # records therefore belong in the app-private data directory.
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS foods(id INTEGER PRIMARY KEY, name TEXT UNIQUE, category TEXT, calories REAL, protein REAL, carbs REAL, fat REAL, serving TEXT);
        CREATE TABLE IF NOT EXISTS meal_sets(id INTEGER PRIMARY KEY, title TEXT, meal_type TEXT, food_ids TEXT);
        CREATE TABLE IF NOT EXISTS plans(id INTEGER PRIMARY KEY, plan_date TEXT, meal_type TEXT, set_id INTEGER, completed INTEGER DEFAULT 0, UNIQUE(plan_date, meal_type));
        CREATE TABLE IF NOT EXISTS workouts(id INTEGER PRIMARY KEY, workout_date TEXT, title TEXT, minutes INTEGER, calories INTEGER, source TEXT, health_key TEXT);
        CREATE TABLE IF NOT EXISTS health_hidden(key TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS body(id INTEGER PRIMARY KEY, log_date TEXT UNIQUE, weight REAL, fat REAL, muscle REAL, source TEXT);
        CREATE TABLE IF NOT EXISTS profile(id INTEGER PRIMARY KEY CHECK(id=1), name TEXT, birthday TEXT, heart_rate INTEGER, sleep_hours REAL, health_connected INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS cafeterias(id INTEGER PRIMARY KEY, provider TEXT NOT NULL, name TEXT NOT NULL, remote_path TEXT, is_primary INTEGER DEFAULT 0, created_at TEXT);
        CREATE TABLE IF NOT EXISTS cafeteria_menus(cafeteria_id INTEGER NOT NULL, menu_date TEXT NOT NULL, breakfast TEXT, lunch TEXT, dinner TEXT, synced_at TEXT, PRIMARY KEY(cafeteria_id, menu_date));
        CREATE TABLE IF NOT EXISTS cafeteria_selections(meal_date TEXT, meal_type TEXT, title TEXT, calories REAL, protein REAL, carbs REAL, source TEXT DEFAULT 'cafeteria', PRIMARY KEY(meal_date, meal_type));
        CREATE TABLE IF NOT EXISTS cafeteria_takeout_selections(meal_date TEXT NOT NULL, meal_type TEXT NOT NULL, title TEXT NOT NULL, calories REAL, protein REAL, carbs REAL, PRIMARY KEY(meal_date, meal_type, title));
        """)
        self._ensure_column('body', 'heart_rate', 'INTEGER')
        self._ensure_column('body', 'sleep_hours', 'REAL')
        self._ensure_column('workouts', 'health_key', 'TEXT')
        self._ensure_column('meal_sets', 'deleted', 'INTEGER DEFAULT 0')
        self._ensure_column('profile', 'target_calories', 'REAL')
        self._ensure_column('profile', 'target_protein', 'REAL')
        self._ensure_column('profile', 'target_carbs', 'REAL')
        self._ensure_column('profile', 'steps', 'INTEGER DEFAULT 0')
        self._ensure_column('profile', 'active_minutes', 'INTEGER DEFAULT 0')
        self._ensure_column('profile', 'active_calories', 'INTEGER DEFAULT 0')
        self._ensure_column('profile', 'total_calories', 'INTEGER DEFAULT 0')
        self._ensure_column('profile', 'distance_meters', 'INTEGER DEFAULT 0')
        self._ensure_column('profile', 'target_steps', 'INTEGER DEFAULT 6300')
        self._ensure_column('profile', 'target_exercise_calories', 'INTEGER DEFAULT 300')
        self._ensure_column('profile', 'height_cm', 'REAL')
        self._ensure_column('profile', 'basal_kcal', 'REAL')
        self._ensure_column('cafeteria_selections', 'source', "TEXT DEFAULT 'cafeteria'")
        self._ensure_column('cafeteria_selections', 'completed', 'INTEGER DEFAULT 0')
        self.conn.execute('CREATE INDEX IF NOT EXISTS foods_name_index ON foods(name)')
        self.conn.execute('CREATE TABLE IF NOT EXISTS app_migrations(name TEXT PRIMARY KEY)')
        self.seed()

    def _ensure_column(self, table, column, definition):
        columns = {row['name'] for row in self.conn.execute(f'PRAGMA table_info({table})')}
        if column not in columns:
            self.conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')

    def seed(self):
        # v1.2.2 repairs snapshots produced while body-fat was multiplied by
        # 100 twice in the Android bridge.  The migration is intentionally
        # narrow: valid percentages remain untouched and only impossible
        # values are normalized once.
        if not self.conn.execute("SELECT 1 FROM app_migrations WHERE name='body_fat_percent_122'").fetchone():
            self.conn.execute('UPDATE body SET fat=ROUND(fat / 100.0, 1) WHERE fat > 100')
            self.conn.execute("INSERT INTO app_migrations(name) VALUES('body_fat_percent_122')")
            self.conn.commit()
        if not self.conn.execute("SELECT 1 FROM app_migrations WHERE name='source_nutrition_36'").fetchone():
            self.conn.execute("UPDATE cafeteria_selections SET calories=NULL,protein=NULL,carbs=NULL WHERE source='cafeteria'")
            self.conn.execute('DELETE FROM cafeteria_menus')
            self.conn.execute("INSERT INTO app_migrations(name) VALUES('source_nutrition_36')")
            self.conn.commit()
        if not self.conn.execute("SELECT 1 FROM app_migrations WHERE name='food_category_clean_138'").fetchone():
            self.conn.execute("UPDATE foods SET category=replace(replace(category, '프랜차이즈 세트 · ', ''), '프랜차이즈 · ', '')")
            self.conn.execute("INSERT INTO app_migrations(name) VALUES('food_category_clean_138')")
            self.conn.commit()
        # A prior Welstory parser could leave a valid restaurant with an empty
        # menu cached for the whole day. Clear only that provider once so the
        # current public source is fetched again after this upgrade.
        if not self.conn.execute("SELECT 1 FROM app_migrations WHERE name='welstory_public_refresh_205'").fetchone():
            self.conn.execute("DELETE FROM cafeteria_menus WHERE cafeteria_id IN (SELECT id FROM cafeterias WHERE provider='welstory')")
            self.conn.execute("INSERT INTO app_migrations(name) VALUES('welstory_public_refresh_205')")
            self.conn.commit()
        # Version 2.0.7 preserves the full published list so non-counter
        # items can be exposed below the primary counters as 테이크아웃.
        if not self.conn.execute("SELECT 1 FROM app_migrations WHERE name='welstory_takeout_refresh_207'").fetchone():
            self.conn.execute("DELETE FROM cafeteria_menus WHERE cafeteria_id IN (SELECT id FROM cafeterias WHERE provider='welstory')")
            self.conn.execute("INSERT INTO app_migrations(name) VALUES('welstory_takeout_refresh_207')")
            self.conn.commit()
        self.conn.executemany("INSERT OR IGNORE INTO foods(name,category,calories,protein,carbs,fat,serving) VALUES(?,?,?,?,?,?,?)", FOODS)
        # Meal sets are personal presets. Foods are seeded as a library, while
        # plans and health records are always created from the user's own data.
        today = date.today()
        if not self.conn.execute("SELECT id FROM body LIMIT 1").fetchone():
            self.conn.execute("INSERT INTO body(log_date,weight,fat,muscle,source) VALUES(?,?,?,?,?)", (today.isoformat(), 0, 0, 0, 'empty'))
        # Earlier builds saved SEMES as a generic restaurant (or accidentally
        # rewrote it as Welstory).  Repair only that known workplace, leaving
        # every other user-created restaurant untouched.
        self.conn.execute("""UPDATE cafeterias
            SET provider='freshmeal', name='세메스 화성사업장',
                remote_path='freshmeal:6525'
            WHERE lower(replace(name, ' ', '')) IN ('세메스', 'semes', '세메스화성사업장')""")
        # First-run defaults map directly to the three Home slots. Existing
        # personal restaurants are intentionally never overwritten.
        if not self.conn.execute('SELECT id FROM cafeterias LIMIT 1').fetchone():
            defaults = (
                ('freshmeal', '세메스 화성사업장', 'freshmeal:6525'),
                ('welstory', '세메스 천안', '/restaurants/welstory/REST000151/%EC%84%B8%EB%A9%94%EC%8A%A4-%EC%B2%9C%EC%95%88'),
                (WONDERPLUS_PROVIDER, '삼성SDI 동탄', 'wonderplus:samsung-sdi-dongtan'),
            )
            for index, (provider, name, path) in enumerate(defaults):
                self.conn.execute('INSERT INTO cafeterias(provider,name,remote_path,is_primary,created_at) VALUES(?,?,?,?,?)',
                                  (provider, name, path, 1 if index == 0 else 0, datetime.now().isoformat()))
        # One-time upgrade: older installations had only the first two defaults.
        # Preserve personal restaurants; only fill available slots once.
        if not self.conn.execute("SELECT 1 FROM app_migrations WHERE name='dongtan_35'").fetchone():
            rows = self.conn.execute('SELECT id, name FROM cafeterias').fetchall()
            dongtan = [row for row in rows if re.sub(r'\s+', '', row['name']).lower() == '삼성sdi동탄']
            for row in dongtan:
                self.conn.execute("UPDATE cafeterias SET provider=?,remote_path=? WHERE id=?",
                                  (WONDERPLUS_PROVIDER, 'wonderplus:samsung-sdi-dongtan', row['id']))
            if not dongtan and len(rows) < 3:
                self.conn.execute('INSERT INTO cafeterias(provider,name,remote_path,is_primary,created_at) VALUES(?,?,?,?,?)',
                                  (WONDERPLUS_PROVIDER, '삼성SDI 동탄', 'wonderplus:samsung-sdi-dongtan', 0, datetime.now().isoformat()))
            self.conn.execute("INSERT INTO app_migrations VALUES('dongtan_35')")
        self.conn.commit()

    def foods(self, query=''):
        query = query.strip()
        if query:
            return [dict(row) for row in self.conn.execute(
                'SELECT * FROM foods WHERE name LIKE ? OR category LIKE ? ORDER BY name COLLATE NOCASE, id LIMIT 80',
                (f'%{query}%', f'%{query}%'))]
        return [dict(row) for row in self.conn.execute('SELECT * FROM foods ORDER BY name COLLATE NOCASE, id LIMIT 80')]

    def add_food(self, name, category, calories, protein, carbs, fat, serving):
        if not name.strip():
            raise ValueError('음식 이름을 입력해 주세요.')
        # A public nutrition source does not always carry every nutrient.
        # Keep such fields blank in the editor; saving treats blank as zero
        # rather than preventing the user from recording the food.
        values = [float(value) if str(value).strip() else 0.0 for value in (calories, protein, carbs, fat)]
        if any(value < 0 for value in values):
            raise ValueError('영양정보는 0 이상으로 입력해 주세요.')
        self.conn.execute('INSERT INTO foods(name,category,calories,protein,carbs,fat,serving) VALUES(?,?,?,?,?,?,?)',
                          (name.strip(), category.strip() or '내 음식', *values, serving.strip() or '1회 제공량'))
        self.conn.commit()

    def save_set(self, title, meal_type, food_ids, set_id=None):
        if not title.strip() or not food_ids:
            raise ValueError('세트 이름과 최소 한 가지 음식이 필요합니다.')
        payload = json.dumps(food_ids)
        if set_id:
            self.conn.execute('UPDATE meal_sets SET title=?, meal_type=?, food_ids=? WHERE id=?', (title.strip(), meal_type, payload, set_id))
        else:
            self.conn.execute('INSERT INTO meal_sets(title,meal_type,food_ids) VALUES(?,?,?)', (title.strip(), meal_type, payload))
        self.conn.commit()

    def delete_set(self, set_id):
        # Preserve completed historical plans while removing the reusable set.
        self.conn.execute('DELETE FROM plans WHERE set_id=? AND plan_date>=?', (set_id, date.today().isoformat()))
        self.conn.execute('UPDATE meal_sets SET deleted=1 WHERE id=?', (set_id,))
        self.conn.commit()

    def meal_set(self, row):
        item = dict(row); ids = json.loads(item['food_ids'])
        rows = self.conn.execute("SELECT * FROM foods WHERE id IN (%s)" % ','.join('?'*len(ids)), ids).fetchall()
        lookup = {r['id']:dict(r) for r in rows}; foods = [lookup[i] for i in ids]
        item['foods'] = foods
        item['calories'] = round(sum(x['calories'] for x in foods))
        item['protein'] = round(sum(x['protein'] for x in foods),1)
        item['carbs'] = round(sum(x['carbs'] for x in foods),1)
        return item

    def today_plan(self, refresh=False):
        today = date.today().isoformat()
        result = []
        for kind in ('breakfast','lunch','dinner'):
            # A cafeteria choice is the meal selected for that time of day.
            # It replaces the displayed plan until the user cancels it or
            # marks that meal as completed; completed records stay locked.
            chosen = self.conn.execute("SELECT * FROM cafeteria_selections WHERE meal_date=? AND meal_type=?", (today, kind)).fetchone()
            if chosen:
                selected = dict(chosen)
                result.append((kind, {'title': selected['title'], 'foods':[{'name':selected['title']}], 'calories':round(selected['calories'] or 0), 'protein':round(selected['protein'] or 0,1), 'carbs':round(selected['carbs'] or 0,1), 'missing_nutrients':[k for k in ('calories','protein','carbs') if selected[k] is None], 'cafeteria':True, 'selection_source': selected.get('source') or 'cafeteria'}, int(selected.get('completed') or 0)))
                continue
            row = self.conn.execute("SELECT * FROM plans WHERE plan_date=? AND meal_type=?",(today,kind)).fetchone()
            if refresh or not row:
                options = self.conn.execute("SELECT id FROM meal_sets WHERE meal_type=? AND deleted=0",(kind,)).fetchall()
                if not options:
                    continue
                chosen = random.choice(options)['id']
                self.conn.execute("INSERT INTO plans(plan_date,meal_type,set_id,completed) VALUES(?,?,?,0) ON CONFLICT(plan_date,meal_type) DO UPDATE SET set_id=excluded.set_id,completed=0",(today,kind,chosen))
                self.conn.commit(); row=self.conn.execute("SELECT * FROM plans WHERE plan_date=? AND meal_type=?",(today,kind)).fetchone()
            s=self.conn.execute("SELECT * FROM meal_sets WHERE id=?",(row['set_id'],)).fetchone()
            result.append((kind,self.meal_set(s),row['completed']))
        return result

    def sets(self):
        return [self.meal_set(x) for x in self.conn.execute("""
            SELECT * FROM meal_sets WHERE deleted=0
            ORDER BY CASE meal_type
                WHEN 'breakfast' THEN 1
                WHEN 'lunch' THEN 2
                WHEN 'dinner' THEN 3
                ELSE 4
            END, id
        """)]
    def toggle_meal_complete(self, kind):
        today = date.today().isoformat()
        # Both library and cafeteria choices become an eaten meal only after
        # the person taps the matching card.  Do not exclude cafeteria rows:
        # doing so left the completion tap visually inert and skipped Health
        # Connect nutrition writes.
        selected = self.conn.execute("SELECT * FROM cafeteria_selections WHERE meal_date=? AND meal_type=?", (today, kind)).fetchone()
        if selected:
            item = dict(selected)
            completed = not bool(item.get('completed'))
            self.conn.execute('UPDATE cafeteria_selections SET completed=? WHERE meal_date=? AND meal_type=?', (int(completed), today, kind))
            self.conn.commit()
            return completed, {'title': item['title'], 'calories': item['calories'] or 0, 'protein': item['protein'] or 0, 'carbs': item['carbs'] or 0}
        row = self.conn.execute('SELECT * FROM plans WHERE plan_date=? AND meal_type=?', (today, kind)).fetchone()
        if not row:
            return False, None
        completed = not bool(row['completed'])
        self.conn.execute('UPDATE plans SET completed=? WHERE plan_date=? AND meal_type=?', (int(completed), today, kind))
        self.conn.commit()
        meal = self.meal_set(self.conn.execute('SELECT * FROM meal_sets WHERE id=?', (row['set_id'],)).fetchone())
        return completed, meal
    def add_set(self,title,kind,ids): self.conn.execute("INSERT INTO meal_sets(title,meal_type,food_ids) VALUES(?,?,?)",(title,kind,json.dumps(ids))); self.conn.commit()
    def workouts(self): return [dict(x) for x in self.conn.execute("SELECT * FROM workouts ORDER BY workout_date DESC,id DESC LIMIT 20")]
    def add_workout(self,title,mins,kcal): self.conn.execute("INSERT INTO workouts(workout_date,title,minutes,calories,source) VALUES(?,?,?,?,?)",(date.today().isoformat(),title,mins,kcal,'manual'));self.conn.commit()
    def delete_workout(self, workout_id):
        row = self.conn.execute('SELECT source,health_key FROM workouts WHERE id=?', (workout_id,)).fetchone()
        if row and row['source'] == 'health_connect' and row['health_key']:
            self.conn.execute('INSERT OR IGNORE INTO health_hidden(key) VALUES(?)', (row['health_key'],))
        self.conn.execute('DELETE FROM workouts WHERE id=?', (workout_id,))
        self.conn.commit()
    def body(self):
        # A first-run placeholder (0 kg) must never hide an actual older
        # Health Connect/manual measurement when the screen is refreshed.
        return [dict(x) for x in self.conn.execute("""SELECT * FROM body
            ORDER BY CASE WHEN COALESCE(weight,0)>0 OR COALESCE(fat,0)>0 OR COALESCE(muscle,0)>0
                          THEN 1 ELSE 0 END DESC, log_date DESC""")]
    def add_body(self,weight,fat,muscle): self.conn.execute("INSERT INTO body(log_date,weight,fat,muscle,source) VALUES(?,?,?,?,?) ON CONFLICT(log_date) DO UPDATE SET weight=excluded.weight,fat=excluded.fat,muscle=excluded.muscle,source=excluded.source",(date.today().isoformat(),weight,fat,muscle,'manual'));self.conn.commit()
    def cafeterias(self):
        return [dict(row) for row in self.conn.execute('SELECT * FROM cafeterias ORDER BY is_primary DESC, id ASC')]
    def add_cafeteria(self, provider, name, remote_path=''):
        if len(self.cafeterias()) >= 3:
            raise ValueError('식당은 최대 3개까지 설정할 수 있어요.')
        primary = 0 if self.cafeterias() else 1
        # Search providers may return a list of category paths.  Only a
        # generated URL path belongs in this field, so never call .strip() on
        # untrusted API values.
        remote_path = remote_path.strip() if isinstance(remote_path, str) else ''
        self.conn.execute('INSERT INTO cafeterias(provider,name,remote_path,is_primary,created_at) VALUES(?,?,?,?,?)',
                          (provider, name.strip(), remote_path, primary, datetime.now().isoformat()))
        self.conn.commit()
        return dict(self.conn.execute('SELECT * FROM cafeterias WHERE id=last_insert_rowid()').fetchone())
    def delete_cafeteria(self, cafeteria_id):
        was_primary = self.conn.execute('SELECT is_primary FROM cafeterias WHERE id=?', (cafeteria_id,)).fetchone()
        self.conn.execute('DELETE FROM cafeteria_menus WHERE cafeteria_id=?', (cafeteria_id,))
        self.conn.execute('DELETE FROM cafeterias WHERE id=?', (cafeteria_id,))
        if was_primary and was_primary['is_primary']:
            first = self.conn.execute('SELECT id FROM cafeterias ORDER BY id LIMIT 1').fetchone()
            if first: self.conn.execute('UPDATE cafeterias SET is_primary=1 WHERE id=?', (first['id'],))
        self.conn.commit()
    def set_primary_cafeteria(self, cafeteria_id):
        self.conn.execute('UPDATE cafeterias SET is_primary=0')
        self.conn.execute('UPDATE cafeterias SET is_primary=1 WHERE id=?', (cafeteria_id,))
        self.conn.commit()
    def save_cafeteria_menu(self, cafeteria_id, meals):
        self.conn.execute('''INSERT INTO cafeteria_menus(cafeteria_id,menu_date,breakfast,lunch,dinner,synced_at)
            VALUES(?,?,?,?,?,?) ON CONFLICT(cafeteria_id,menu_date) DO UPDATE SET
            breakfast=excluded.breakfast,lunch=excluded.lunch,dinner=excluded.dinner,synced_at=excluded.synced_at''',
            (cafeteria_id, date.today().isoformat(), meals.get('breakfast',''), meals.get('lunch',''), meals.get('dinner',''), datetime.now().isoformat()))
        self.conn.commit()
    def update_cafeteria_path(self, cafeteria_id, path):
        # Do not silently convert a CJ FreshMeal site into Welstory while
        # repairing an old saved URL.  That was the reason saved FreshMeal
        # sites such as SEMES later appeared to have no menu source.
        self.conn.execute('UPDATE cafeterias SET remote_path=? WHERE id=?', (path, cafeteria_id)); self.conn.commit()
    def primary_cafeteria_menu(self):
        row = self.conn.execute('''SELECT c.*, m.breakfast, m.lunch, m.dinner, m.synced_at
            FROM cafeterias c LEFT JOIN cafeteria_menus m ON c.id=m.cafeteria_id AND m.menu_date=?
            WHERE c.is_primary=1 ORDER BY c.id LIMIT 1''', (date.today().isoformat(),)).fetchone()
        return dict(row) if row else None
    def cafeteria_menus(self):
        """Return every saved restaurant together with today's public menu."""
        return [dict(row) for row in self.conn.execute('''SELECT c.*, m.breakfast, m.lunch, m.dinner, m.synced_at
            FROM cafeterias c LEFT JOIN cafeteria_menus m ON c.id=m.cafeteria_id AND m.menu_date=?
            ORDER BY c.is_primary DESC, c.id ASC''', (date.today().isoformat(),))]
    def profile(self):
        row = self.conn.execute('SELECT * FROM profile WHERE id=1').fetchone()
        return dict(row) if row else {'name':'', 'birthday':'', 'heart_rate':None, 'sleep_hours':None, 'health_connected':0, 'target_calories':1800, 'target_protein':100, 'target_carbs':220, 'target_steps':6300, 'target_exercise_calories':300}
    def save_profile(self, name, birthday, calories=1800, protein=100, carbs=220, steps=6300, exercise_calories=300):
        self.conn.execute('''INSERT INTO profile(id,name,birthday,target_calories,target_protein,target_carbs,target_steps,target_exercise_calories) VALUES(1,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
            name=excluded.name,birthday=excluded.birthday,target_calories=excluded.target_calories,target_protein=excluded.target_protein,target_carbs=excluded.target_carbs,target_steps=excluded.target_steps,target_exercise_calories=excluded.target_exercise_calories''',
            (name.strip(), birthday.strip(), calories, protein, carbs, int(steps), int(exercise_calories)))
        self.conn.commit()
    def select_cafeteria_meal(self, meal_type, title, nutrition=None):
        today = date.today().isoformat()
        # A completed meal is a consumption record.  Never replace it from
        # the cafeteria browser; the user must first reopen the meal block.
        completed_selection = self.conn.execute(
            'SELECT completed FROM cafeteria_selections WHERE meal_date=? AND meal_type=?',
            (today, meal_type),
        ).fetchone()
        completed_plan = self.conn.execute(
            'SELECT completed FROM plans WHERE plan_date=? AND meal_type=?',
            (today, meal_type),
        ).fetchone()
        if (completed_selection and completed_selection['completed']) or (completed_plan and completed_plan['completed']):
            return None
        # A main counter replaces any takeout combination for that meal.
        self.conn.execute('DELETE FROM cafeteria_takeout_selections WHERE meal_date=? AND meal_type=?', (today, meal_type))
        nutrition = nutrition or {}
        calories, protein, carbs = (nutrition.get(k) for k in ('calories','protein','carbs'))
        self.conn.execute('INSERT OR REPLACE INTO cafeteria_selections(meal_date,meal_type,title,calories,protein,carbs,source) VALUES(?,?,?,?,?,?,?)', (today, meal_type, title, calories, protein, carbs, 'cafeteria'))
        self.conn.commit()
        return {'title': title, 'calories': calories or 0, 'protein': protein or 0, 'carbs': carbs or 0}

    def toggle_cafeteria_choice(self, meal_type, title, nutrition=None):
        """Select a cafeteria item, or clear it when the same item is tapped.

        This deliberately applies only to an unfinished cafeteria choice.  A
        completed meal stays immutable until the person reopens its meal card.
        """
        row = self.conn.execute(
            'SELECT * FROM cafeteria_selections WHERE meal_date=? AND meal_type=?',
            (date.today().isoformat(), meal_type),
        ).fetchone()
        if row and row['source'] == 'cafeteria' and row['title'] == title and not row['completed']:
            self.conn.execute('DELETE FROM cafeteria_selections WHERE meal_date=? AND meal_type=?',
                              (date.today().isoformat(), meal_type))
            self.conn.commit()
            return False
        return self.select_cafeteria_meal(meal_type, title, nutrition) is not None

    def cafeteria_choice(self, meal_type):
        row = self.conn.execute(
            "SELECT * FROM cafeteria_selections WHERE meal_date=? AND meal_type=? AND source='cafeteria'",
            (date.today().isoformat(), meal_type),
        ).fetchone()
        return dict(row) if row else None

    def takeout_choices(self, meal_type):
        return [dict(row) for row in self.conn.execute(
            'SELECT * FROM cafeteria_takeout_selections WHERE meal_date=? AND meal_type=? ORDER BY title',
            (date.today().isoformat(), meal_type),
        )]

    def _sync_takeout_summary(self, meal_type):
        """Mirror the individually selected takeout foods into today's meal.

        The detail rows remain separate for reversible teal selections while
        the existing meal/completion/Health Connect pipeline receives one
        summed cafeteria row.
        """
        today = date.today().isoformat()
        rows = self.takeout_choices(meal_type)
        if not rows:
            self.conn.execute('DELETE FROM cafeteria_selections WHERE meal_date=? AND meal_type=?', (today, meal_type))
            self.conn.commit()
            return False
        title = ' · '.join(row['title'] for row in rows)
        calories = sum(float(row['calories'] or 0) for row in rows)
        protein = sum(float(row['protein'] or 0) for row in rows)
        carbs = sum(float(row['carbs'] or 0) for row in rows)
        self.conn.execute('''INSERT OR REPLACE INTO cafeteria_selections
            (meal_date,meal_type,title,calories,protein,carbs,source,completed)
            VALUES(?,?,?,?,?,?,?,0)''', (today, meal_type, title, round(calories), round(protein, 1), round(carbs, 1), 'takeout'))
        self.conn.commit()
        return True

    def toggle_takeout_choice(self, meal_type, title, nutrition=None):
        today = date.today().isoformat()
        current = self.conn.execute('SELECT completed FROM cafeteria_selections WHERE meal_date=? AND meal_type=?', (today, meal_type)).fetchone()
        # Completed meals are intentionally locked until the meal card is
        # reopened, exactly like a main-counter selection.
        if current and bool(current['completed']):
            return None
        existing = self.conn.execute('SELECT 1 FROM cafeteria_takeout_selections WHERE meal_date=? AND meal_type=? AND title=?', (today, meal_type, title)).fetchone()
        if existing:
            self.conn.execute('DELETE FROM cafeteria_takeout_selections WHERE meal_date=? AND meal_type=? AND title=?', (today, meal_type, title))
            self._sync_takeout_summary(meal_type)
            return False
        # A takeout selection replaces a previous main-counter choice, then
        # remains independently toggleable alongside other takeout items.
        self.conn.execute('DELETE FROM cafeteria_selections WHERE meal_date=? AND meal_type=?', (today, meal_type))
        nutrients = nutrition or {}
        self.conn.execute('INSERT INTO cafeteria_takeout_selections(meal_date,meal_type,title,calories,protein,carbs) VALUES(?,?,?,?,?,?)',
                          (today, meal_type, title, nutrients.get('calories'), nutrients.get('protein'), nutrients.get('carbs')))
        self._sync_takeout_summary(meal_type)
        return True

    def select_manual_meal(self, meal_type, food_ids):
        rows = [dict(row) for row in self.conn.execute(
            'SELECT * FROM foods WHERE id IN (%s)' % ','.join('?' * len(food_ids)), food_ids
        ).fetchall()] if food_ids else []
        lookup = {food['id']: food for food in rows}
        foods = [lookup[food_id] for food_id in food_ids if food_id in lookup]
        if not foods:
            raise ValueError('최소 한 가지 음식을 선택해 주세요.')
        title = self.compact_food_names(foods)
        self.conn.execute('DELETE FROM cafeteria_takeout_selections WHERE meal_date=? AND meal_type=?', (date.today().isoformat(), meal_type))
        self.conn.execute('INSERT OR REPLACE INTO cafeteria_selections(meal_date,meal_type,title,calories,protein,carbs,source) VALUES(?,?,?,?,?,?,?)',
                          (date.today().isoformat(), meal_type, title, round(sum(food['calories'] for food in foods)),
                           round(sum(food['protein'] for food in foods), 1), round(sum(food['carbs'] for food in foods), 1), 'manual'))
        self.conn.commit()
        return {'title': title, 'calories': round(sum(food['calories'] for food in foods)),
                'protein': round(sum(food['protein'] for food in foods), 1),
                'carbs': round(sum(food['carbs'] for food in foods), 1)}

    def clear_cafeteria_meal(self, meal_type):
        """Return this meal to its ordinary saved set without touching others."""
        self.conn.execute('DELETE FROM cafeteria_selections WHERE meal_date=? AND meal_type=?',
                          (date.today().isoformat(), meal_type))
        self.conn.execute('DELETE FROM cafeteria_takeout_selections WHERE meal_date=? AND meal_type=?',
                          (date.today().isoformat(), meal_type))
        self.conn.commit()

    def apply_health_snapshot(self, snapshot):
        """Persist a completed native Health Connect snapshot locally."""
        today = date.today().isoformat()
        weight = snapshot.get('weight')
        body_fat = snapshot.get('body_fat')
        lean_body_mass = snapshot.get('lean_body_mass')
        # Health Connect does not guarantee that Samsung Health exports a
        # skeletal-muscle record. When it only shares weight, body fat and
        # BMR, show a clearly marked estimate instead of a false “미기록”.
        muscle_estimated = False
        if lean_body_mass is None and weight is not None and body_fat is not None:
            fat_free_mass = float(weight) * max(0, 1 - float(body_fat) / 100.0)
            bmr = snapshot.get('basal_kcal')
            if bmr is not None and float(bmr) > 370:
                fat_free_mass = (float(bmr) - 370.0) / 21.6
            lean_body_mass = round(max(0, fat_free_mass * .55), 1)
            muscle_estimated = True
        if weight is not None or body_fat is not None or lean_body_mass is not None:
            # Health Connect writes weight, fat and lean mass as independent
            # records.  Never take all three from a single "latest" row: a
            # newer weight-only sample used to overwrite an older valid muscle
            # measurement with 0 and make the profile say "미기록".
            def latest_positive(column):
                return self.conn.execute(
                    'SELECT %s FROM body WHERE COALESCE(%s,0)>0 ORDER BY log_date DESC LIMIT 1' % (column, column)
                ).fetchone()

            previous_weight = latest_positive('weight')
            previous_fat = latest_positive('fat')
            previous_muscle = latest_positive('muscle')
            fat = float(body_fat) if body_fat is not None else (previous_fat['fat'] if previous_fat else 0)
            # Be defensive with a provider that still sends a fraction or an
            # old locally cached percentage.  The UI always stores 0–100.
            if fat is not None and float(fat) > 100:
                fat = float(fat) / 100.0
            muscle = float(lean_body_mass) if lean_body_mass is not None else (previous_muscle['muscle'] if previous_muscle else 0)
            synced_weight = float(weight) if weight is not None else (previous_weight['weight'] if previous_weight else 0)
            self.conn.execute("""INSERT INTO body(log_date,weight,fat,muscle,source)
                VALUES(?,?,?,?,?) ON CONFLICT(log_date) DO UPDATE SET
                weight=excluded.weight, fat=excluded.fat, muscle=excluded.muscle, source=excluded.source""", (today, round(float(synced_weight), 1), fat, muscle, 'health_connect'))

        profile = self.profile()
        heart_rate = snapshot.get('heart_rate', profile.get('heart_rate'))
        sleep_hours = snapshot.get('sleep_hours', profile.get('sleep_hours'))
        steps = int(snapshot.get('steps', profile.get('steps') or 0) or 0)
        active_minutes = int(snapshot.get('active_minutes', profile.get('active_minutes') or 0) or 0)
        active_calories = int(snapshot.get('active_calories', profile.get('active_calories') or 0) or 0)
        total_calories = int(snapshot.get('total_calories', profile.get('total_calories') or 0) or 0)
        distance_meters = int(snapshot.get('distance_meters', profile.get('distance_meters') or 0) or 0)
        self.conn.execute("""INSERT INTO profile(id,name,birthday,heart_rate,sleep_hours,steps,active_minutes,active_calories,total_calories,distance_meters,height_cm,basal_kcal,health_connected)
            VALUES(1,?,?,?,?,?,?,?,?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET
            heart_rate=excluded.heart_rate, sleep_hours=excluded.sleep_hours,
            steps=excluded.steps, active_minutes=excluded.active_minutes,
            active_calories=excluded.active_calories, total_calories=excluded.total_calories, distance_meters=excluded.distance_meters,
            height_cm=COALESCE(excluded.height_cm, profile.height_cm),
            basal_kcal=COALESCE(excluded.basal_kcal, profile.basal_kcal),
            health_connected=1""",
            (profile.get('name') or '', profile.get('birthday') or '', heart_rate, sleep_hours,
             steps, active_minutes, active_calories, total_calories, distance_meters,
             snapshot.get('height_cm'), snapshot.get('basal_kcal')))

        # These rows originate from Health Connect and may be safely refreshed.
        # Manual entries are intentionally never touched.
        self.conn.execute("DELETE FROM workouts WHERE source='health_connect'")
        for item in snapshot.get('workouts', []):
            try:
                when = datetime.fromisoformat(item['start'].replace('Z', '+00:00')).date().isoformat()
                title = str(item.get('title') or '운동 기록')[:60]
                minutes = max(1, int(item.get('minutes', 1)))
            except (KeyError, TypeError, ValueError):
                continue
            health_key = f"{item.get('start', '')}|{title}|{minutes}"
            hidden = self.conn.execute('SELECT 1 FROM health_hidden WHERE key=?', (health_key,)).fetchone()
            if not hidden:
                self.conn.execute('INSERT INTO workouts(workout_date,title,minutes,calories,source,health_key) VALUES(?,?,?,?,?,?)',
                                  (when, title, minutes, 0, 'health_connect', health_key))
        self.conn.commit()


class RoundedCard(BoxLayout):
    surface_opacity = NumericProperty(.50)
    surface_color = ListProperty([.065, .09, .145, 1])
    rim_strength = NumericProperty(1)
    background_color = ListProperty([1, 1, 1, 1])
    border_color = ListProperty([1, 1, 1, .12])
    radius = NumericProperty(dp(20))


class LinearBackdrop(Widget):
    """Preblurred linear planes: a shared static texture, no per-frame blur."""
    _texture = None

    @classmethod
    def backdrop_texture(cls):
        if cls._texture is None:
            width, height = 128, 256
            pixels = bytearray()
            for y in range(height):
                v = y / (height - 1)
                for x in range(width):
                    u = x / (width - 1)
                    # Directly sampled from the approved early home screen:
                    # the navy header settles into the near-black body, with
                    # the same very low-key teal and warm light around the
                    # lower meal cards.  These are part of the background,
                    # not decorative card colours.
                    # `v` starts at Kivy's bottom edge.  Work in top-down
                    # screen space so the status-bar colour joins the header
                    # without a visible painted band.
                    s = 1.0 - v
                    stops = [
                        # Reference screen: a clear blue top behind the
                        # status icons, easing into an ink-blue content body.
                        (0.00, (8, 43, 75)),
                        (0.15, (9, 42, 72)),
                        (0.31, (7, 31, 54)),
                        (0.49, (5, 18, 34)),
                        (0.68, (4, 12, 24)),
                        (1.00, (4, 10, 20)),
                    ]
                    for index in range(len(stops) - 1):
                        start, left = stops[index]
                        end, right = stops[index + 1]
                        if s <= end:
                            t = (s - start) / (end - start)
                            rgb = [left[channel] + (right[channel] - left[channel]) * t
                                   for channel in range(3)]
                            break
                    # Subtle diffuse lights from the approved home screen.
                    # Keep them below card-strength so content stays legible.
                    teal = 20 * pow(2.71828, -(((u - .57) / .43) ** 2 + ((v - .32) / .16) ** 2) * 2.1)
                    warm = 15 * pow(2.71828, -(((u - .18) / .34) ** 2 + ((v - .14) / .13) ** 2) * 2.1)
                    rgb[0] += warm
                    rgb[1] += teal * .72 + warm * .28
                    rgb[2] += teal * .82 + warm * .06
                    pixels.extend(int(max(0, min(255, c))) for c in rgb)
            texture = Texture.create(size=(width, height), colorfmt='rgb')
            texture.blit_buffer(bytes(pixels), colorfmt='rgb', bufferfmt='ubyte')
            texture.mag_filter = 'linear'
            texture.min_filter = 'linear'
            cls._texture = texture
        return cls._texture


class ProgressRing(Widget):
    """A compact, high-contrast nutrition progress indicator."""
    progress = NumericProperty(.76)
    value = StringProperty('76%')


class NutritionRings(Widget):
    """Three compact goal rings for calories, protein, and carbohydrates."""
    calorie_progress = NumericProperty(.0)
    protein_progress = NumericProperty(.0)
    carbs_progress = NumericProperty(.0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self._redraw, size=self._redraw, calorie_progress=self._redraw,
                  protein_progress=self._redraw, carbs_progress=self._redraw)

    def _redraw(self, *_):
        # Mesh bands have an explicit full thickness. Kivy Line.width is a
        # half-width, which made the old neighbouring rings overlap.
        self.canvas.clear()
        scale = min(self.size)
        with self.canvas:
            for ratio, progress, bright, dark in (
                (.43, self.calorie_progress, (.98,.13,.40,1), (.25,.035,.105,1)),
                (.32, self.protein_progress, (.68,.96,.06,1), (.17,.235,.035,1)),
                (.21, self.carbs_progress, (.03,.90,.81,1), (.025,.22,.205,1))):
                radius, half = scale * ratio, scale * .037
                for value, color in ((1, dark), (max(0, min(1, progress)), bright)):
                    if value <= 0:
                        continue
                    Color(*color)
                    segments = max(2, int(180 * value))
                    vertices = []
                    for i in range(segments + 1):
                        angle = math.radians(90 - 360 * value * i / segments)
                        for r in (radius - half, radius + half):
                            vertices.extend((self.center_x + r * math.cos(angle),
                                             self.center_y + r * math.sin(angle), 0, 0))
                    Mesh(vertices=vertices, indices=list(range(2 * (segments + 1))), mode='triangle_strip')

    def ring_point(self, radius_ratio, progress, start_angle):
        radius = min(self.width, self.height) * radius_ratio
        angle = math.radians(start_angle + 360 * progress)
        return self.center_x + radius * math.cos(angle), self.center_y + radius * math.sin(angle)

    def ring_start(self, radius_ratio, start_angle):
        radius = min(self.width, self.height) * radius_ratio
        angle = math.radians(start_angle)
        return self.center_x + radius * math.cos(angle), self.center_y + radius * math.sin(angle)


class ActivityRings(Widget):
    """Samsung Health-inspired activity rings: muted plan bands under bright progress."""
    steps_progress = NumericProperty(0)
    minutes_progress = NumericProperty(0)
    calories_progress = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self._redraw, size=self._redraw, steps_progress=self._redraw,
                  minutes_progress=self._redraw, calories_progress=self._redraw)

    def _redraw(self, *_):
        self.canvas.clear()
        scale = min(self.size)
        with self.canvas:
            # The full, dark bands represent the plan; only completion is vivid.
            for ratio, progress, bright, dim in (
                (.43, self.steps_progress, (.72, 1.0, .20, 1), (.20, .30, .10, 1)),
                (.32, self.minutes_progress, (.10, .70, 1.0, 1), (.05, .20, .30, 1)),
                (.21, self.calories_progress, (.72, .32, 1.0, 1), (.20, .08, .28, 1))):
                radius, half = scale * ratio, scale * .040
                for value, color in ((1, dim), (max(0, min(1, progress)), bright)):
                    Color(*color)
                    segments = max(24, int(210 * value))
                    vertices = []
                    for i in range(segments + 1):
                        angle = math.radians(92 - 360 * value * i / segments)
                        for r in (radius - half, radius + half):
                            vertices.extend((self.center_x + r * math.cos(angle),
                                             self.center_y + r * math.sin(angle), 0, 0))
                    Mesh(vertices=vertices, indices=list(range(2 * (segments + 1))), mode='triangle_strip')


class TopScrollMask(Widget):
    """Fixed frosted safe-area mask above scrolling app content.

    Android 15 draws edge-to-edge by default.  This mask keeps scrollable
    cards out of the status area and gives their top edge a soft, glass-like
    fade rather than allowing text to collide with system icons.
    """
    _texture = None

    @classmethod
    def scroll_mask_texture(cls):
        """A single vertically interpolated status-safe glass veil.

        Four discrete rectangles made the overlay visibly banded on OLED
        displays.  A tiny RGBA texture provides a continuous curve from a
        dense navy at the system status bar to fully transparent at the lower
        edge, so scrolling content is gently absorbed without a seam.
        """
        if cls._texture is None:
            height = 256
            pixels = bytearray()
            for y in range(height):
                # Kivy's texture data starts at the bottom: t=0 is the lower,
                # transparent edge; t=1 is the protected status-bar edge.
                t = y / (height - 1)
                alpha = int(255 * (.02 + .96 * (t ** 2.15)))
                pixels.extend((9, 22, 41, alpha))
            texture = Texture.create(size=(1, height), colorfmt='rgba')
            texture.blit_buffer(bytes(pixels), colorfmt='rgba', bufferfmt='ubyte')
            texture.mag_filter = 'linear'
            texture.min_filter = 'linear'
            cls._texture = texture
        return cls._texture


class GlassButton(Button):
    glass_color = ListProperty([.16, .23, .41, .86])


class CafeteriaTab(GlassButton):
    """Independent selected state for restaurant and meal-time controls."""
    selected = BooleanProperty(False)

class GlassInput(TextInput):
    """A high-contrast text field used for every editable value in the app."""
    _value_white = (1, 1, 1, 1)

    def on_kv_post(self, _base_widget):
        # Android's IME/theme may apply its muted default after the KV rule and
        # once more when the popup is attached.  Paint again on both frames.
        Clock.schedule_once(self._apply_value_color, 0)
        Clock.schedule_once(self._apply_value_color, .12)

    def _apply_value_color(self, _dt=0):
        self.foreground_color = self._value_white
        self.disabled_foreground_color = self._value_white
        self.cursor_color = (.78, .88, 1, 1)

    def on_text(self, *_args):
        # Typed, pasted, and programmatically filled values all use white.
        self._apply_value_color()

    def on_focus(self, *_args):
        # Reassert after the Android soft keyboard changes the input state.
        self._apply_value_color()
        Clock.schedule_once(self._apply_value_color, .08)


class StepProgress(Widget):
    """A deliberately thick, readable step-goal bar.

    Kivy's platform ProgressBar texture stays hairline-thin on several
    Samsung devices even when its widget height is increased. Drawing the
    track ourselves keeps the visible fill at the requested size.
    """
    max = NumericProperty(6300)
    value = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas:
            self._track_color = Color(.42, .52, .66, .72)
            self._track = RoundedRectangle(radius=[dp(8)])
            self._fill_color = Color(.08, .75, .97, 1)
            self._fill = RoundedRectangle(radius=[dp(8)])
        self.bind(pos=self._redraw, size=self._redraw, value=self._redraw, max=self._redraw)
        self._redraw()

    def _redraw(self, *_args):
        self._track.pos = self.pos
        self._track.size = self.size
        ratio = 0 if self.max <= 0 else max(0, min(1, self.value / self.max))
        self._fill.pos = self.pos
        self._fill.size = (self.width * ratio, self.height)


class DockItem(ButtonBehavior, BoxLayout):
    icon = StringProperty('')
    label = StringProperty('')
    active = BooleanProperty(False)
class AppDock(RoundedCard):
    selected = StringProperty('home')
class TrendBar(BoxLayout):
    day = StringProperty('')
    level = NumericProperty(.5)
    active = BooleanProperty(False)


class BodyTrendChart(Widget):
    """Compact, source-driven body metric trend for the Report screen."""
    values = ListProperty([])
    accent = ListProperty([.39, .78, 1, 1])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self._redraw, size=self._redraw, values=self._redraw, accent=self._redraw)

    def _redraw(self, *_):
        self.canvas.clear()
        left, right = self.x + dp(4), self.right - dp(4)
        bottom, top = self.y + dp(7), self.top - dp(7)
        with self.canvas:
            # Quiet gridlines keep the graph legible without imitating a
            # spreadsheet.  They intentionally match the app's glass rims.
            Color(.70, .79, .94, .14)
            for fraction in (.15, .50, .85):
                y = bottom + (top - bottom) * fraction
                Line(points=[left, y, right, y], width=dp(.7))
            vals = [float(v) for v in self.values if v is not None]
            if not vals:
                return
            low, high = min(vals), max(vals)
            pad = max(.5, (high - low) * .22)
            low, high = low - pad, high + pad
            span = max(.01, high - low)
            count = max(1, len(vals) - 1)
            points = []
            for index, value in enumerate(vals):
                x = left + (right - left) * index / count
                y = bottom + (top - bottom) * (value - low) / span
                points.extend((x, y))
            Color(*self.accent)
            if len(points) > 2:
                Line(points=points, width=dp(2.1), joint='round')
            for index in range(0, len(points), 2):
                Ellipse(pos=(points[index] - dp(3.3), points[index + 1] - dp(3.3)), size=(dp(6.6), dp(6.6)))

class MealCard(ButtonBehavior, BoxLayout):
    title = StringProperty(''); foods = StringProperty(''); calories = StringProperty(''); protein = StringProperty(''); color = ListProperty([.8,.95,.85,1]); meal_type=StringProperty(''); badge=StringProperty(''); divider = BooleanProperty(False); cafeteria = BooleanProperty(False); completed = BooleanProperty(False); glow = NumericProperty(0)


class MenuMarquee(StencilView):
    """A lightweight clipped menu label.

    The former ticker started a 30fps callback for every row and retained it
    after Home was rebuilt. Native ellipsis keeps scrolling responsive while
    the full menu is still available through the selection action.
    """
    text = StringProperty('')
    font_name = StringProperty('')
    font_size = NumericProperty(dp(10))
    text_color = ListProperty([.79, .87, .87, 1])
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._label = Label(halign='left', valign='middle', shorten=True,
                            shorten_from='right', max_lines=1, size_hint=(1, 1))
        self.add_widget(self._label)
        self.bind(text=self._reset, font_name=self._reset,
                  font_size=self._reset, text_color=self._reset,
                  size=self._reset, pos=self._reset)
        Clock.schedule_once(self._reset, 0)

    def _reset(self, *_args):
        label = self._label
        label.text = self.text or ''
        label.font_name = self.font_name
        label.font_size = self.font_size
        label.color = self.text_color
        label.text_size = (self.width, self.height)
        label.size = self.size
        label.pos = self.pos

class StatTile(BoxLayout): pass
class ListLine(BoxLayout):
    icon = StringProperty('')
    title = StringProperty('')
    tag = StringProperty('')
    detail = StringProperty('')
    tail = StringProperty('')
class SwipeWorkout(ListLine):
    workout_id = NumericProperty(0)
    _start_x = NumericProperty(0)
    _original_tail = StringProperty('')
    swipe_offset = NumericProperty(0)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self._start_x = touch.x
            self._original_tail = self.tail
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if self._start_x:
            self.swipe_offset = min(0, max(-dp(132), touch.x - self._start_x))
            self.tail = '삭제' if self.swipe_offset < -dp(60) else '왼쪽으로 밀어 삭제'
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if self._start_x and self.swipe_offset < -dp(112):
            App.get_running_app().delete_workout(self.workout_id)
        elif self._start_x:
            self.tail = self._original_tail
            self.swipe_offset = 0
        self._start_x = 0
        return super().on_touch_up(touch)
class MealSetLine(ListLine):
    meal_set_id = NumericProperty(0)

    def on_touch_up(self, touch):
        if self.collide_point(*touch.pos):
            item = next((row for row in App.get_running_app().store.sets() if row['id'] == self.meal_set_id), None)
            if item:
                App.get_running_app().popup_meal_set(item)
                return True
        return super().on_touch_up(touch)
class HomeScreen(Screen): pass
class Popup(KivyPopup):
    def __init__(self, **kwargs):
        # Kivy's default separator is bright cyan on a few Android themes.
        # Dialogs in this app intentionally have no title rail or separator.
        kwargs.setdefault('separator_color', (0, 0, 0, 0))
        kwargs.setdefault('overlay_color', (.008, .015, .032, .74))
        content = kwargs.get('content')
        if isinstance(content, RoundedCard):
            content.surface_opacity = 1
            content.background_color = [.045,.060,.092,.992]
            content.rim_strength = .42
        super().__init__(**kwargs)

class MealsScreen(Screen): pass
class WorkoutScreen(Screen): pass
class ReportScreen(Screen): pass
class BodyScreen(Screen): pass


class WelltableApp(App):
    store: Store
    # Bundled family provides crisp Korean text and a real semibold face on Android.
    font_name = StringProperty('WelltablePretendard')
    selected_cafeteria_id = NumericProperty(0)
    selected_cafeteria_meal = StringProperty('breakfast')
    selected_cafeteria_group = StringProperty('')
    update_available = BooleanProperty(False)
    update_version = StringProperty('')
    update_notes = StringProperty('')
    meal_names = {'breakfast':'아침','lunch':'점심','dinner':'저녁'}
    motivation_lines = (
        '오늘의 작은 선택이 내일의 컨디션을 만듭니다.',
        '완벽보다 꾸준함. 한 끼부터 가볍게 시작해요.',
        '몸은 오늘의 나를 기억합니다. 기분 좋게 움직여요.',
        '나를 위한 루틴, 오늘도 한 칸 채워볼까요?',
        '에너지는 채우고, 부담은 덜어내는 하루예요.',
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Avoid launching duplicate network requests when Home redraws.
        self._welstory_sync_requested = set()
        self._menu_sync_requested = set()
        self._menu_syncing = set()
        self._menu_errors = {}
        self._update_apk_url = ''

    def load_kv(self, *args, **kwargs):
        """Load the root only after bundled fonts are registered below."""
        return None

    def build(self):
        self.title = '살빼자'
        LabelBase.register(
            name='WelltablePretendard',
            fn_regular=os.path.join(APP_DIR, 'assets', 'fonts', 'Pretendard-Regular.otf'),
            fn_bold=os.path.join(APP_DIR, 'assets', 'fonts', 'Pretendard-SemiBold.otf'),
        )
        LabelBase.register(
            name='WelltableSymbols',
            fn_regular=os.path.join(APP_DIR, 'assets', 'fonts', 'MaterialSymbolsRounded.ttf'),
        )
        try:
            data_dir = os.environ.get('WELLTABLE_DATA_DIR', self.user_data_dir) if os.environ.get('WELLTABLE_PREVIEW') else self.user_data_dir
            self.store = Store(os.path.join(data_dir, 'welltable_mobile.db'))
        except Exception:
            # A broken device storage mount must not prevent the app from
            # opening. Records stay available for this session in that case.
            Logger.exception('Welltable storage unavailable; using memory store')
            self.store = Store(':memory:')
        return Builder.load_file(os.path.join(APP_DIR, 'welltable.kv'))

    def on_start(self):
        Clock.schedule_once(self._start_content, 0)

    def _start_content(self, _dt):
        try:
            self.configure_system_bars()
            # SDL/Kivy can apply its initial window flags a fraction after
            # on_start. Re-apply the normal (non-fullscreen) bars once that
            # setup has completed.
            Clock.schedule_once(lambda _dt: self.configure_system_bars(), .35)
            self.refresh_all()
            self.check_for_update()
            self.sync_health(silent=True)
            # The foreground dashboard refreshes at a short, bounded interval
            # so walking, distance, and active-energy values feel live without
            # keeping a background service or draining the battery.
            self._health_poll_event = Clock.schedule_interval(self._poll_health, 45)
            requested_screen = os.environ.get('WELLTABLE_SCREEN')
            if requested_screen in ('home', 'meals', 'workouts', 'report', 'body'):
                self.show(requested_screen)
            capture = os.environ.get('WELLTABLE_CAPTURE')
            if capture:
                Clock.schedule_once(lambda _dt: self.capture_and_stop(capture), 2.0)
        except Exception as exc:
            # Keep the app open with a readable diagnostic rather than
            # returning to Android's launcher after the splash screen.
            Logger.exception('Welltable startup failed')
            error = Screen(name='startup_error')
            error.add_widget(Label(
                text='살빼자를 시작하지 못했습니다.\\n\\n'
                     + type(exc).__name__ + ': ' + str(exc),
                color=(1, .82, .82, 1),
                font_size=dp(16),
                halign='center', valign='middle',
                text_size=(Window.width - dp(48), Window.height - dp(48)),
                padding=(dp(24), dp(24)),
            ))
            self.root.add_widget(error)
            self.root.current = 'startup_error'

    @staticmethod
    def _version_key(value):
        """Compare dotted semantic versions without accepting arbitrary text."""
        try:
            parts = str(value).strip().lstrip('vV').split('.')
            if not parts or len(parts) > 4 or any(not part.isdigit() for part in parts):
                return ()
            return tuple(int(part) for part in parts)
        except Exception:
            return ()

    def check_for_update(self):
        """Check the public GitHub-backed release manifest without blocking UI."""
        def worker():
            try:
                manifest = self._fetch_public_json(UPDATE_MANIFEST_URL, SERVICE_BASE_URL + '/')
                remote_version = str(manifest.get('version') or '')
                apk_url = str(manifest.get('apk_url') or '')
                notes = str(manifest.get('notes') or '').strip()
                available = bool(apk_url.startswith('https://') and self._version_key(remote_version)
                                 and self._version_key(remote_version) > self._version_key(APP_VERSION))
                Clock.schedule_once(lambda _dt: self._apply_update_manifest(
                    remote_version, notes, apk_url, available), 0)
            except Exception:
                # A release check is optional. No network error may interfere
                # with opening the offline-first tracker.
                Clock.schedule_once(lambda _dt: self._apply_update_manifest('', '', '', False), 0)
        Thread(target=worker, daemon=True).start()

    def _apply_update_manifest(self, version, notes, apk_url, available):
        self.update_version = version if available else ''
        self.update_notes = notes if available else ''
        self._update_apk_url = apk_url if available else ''
        self.update_available = bool(available)

    def popup_update(self):
        if not self.update_available or not self._update_apk_url:
            return
        box = RoundedCard(orientation='vertical', padding=dp(20), spacing=dp(12), radius=dp(26),
                          background_color=[.055,.07,.11,.99], border_color=[1,.55,.22,.30])
        header, dialog = self._dialog_header(f'v{self.update_version} 업데이트', '새 버전을 내려받아 설치할 수 있어요.')
        box.add_widget(header)
        notes = Label(text=self.update_notes or '새로운 기능과 안정성 개선이 포함되어 있어요.',
                      font_name=self.font_name, color=(.80,.86,.96,1), font_size=dp(12),
                      halign='left', valign='top', text_size=(dp(290), None), size_hint_y=None)
        notes.texture_update()
        notes.height = max(dp(54), notes.texture_size[1] + dp(10))
        # Keep short release notes compact, while a longer user-facing note
        # remains completely readable inside its own vertical scroll area.
        notes_scroll = ScrollView(do_scroll_x=False, bar_width=dp(3), size_hint_y=None,
                                  height=min(notes.height, Window.height * .46))
        notes_scroll.add_widget(notes)
        box.add_widget(notes_scroll)
        buttons = BoxLayout(size_hint_y=None, height=dp(43), spacing=dp(9))
        later = GlassButton(text='다음에', font_name=self.font_name, glass_color=(.11,.15,.23,.84), color=(.75,.83,.96,1))
        install = GlassButton(text='업데이트', font_name=self.font_name, glass_color=(.86,.33,.10,.78), color=(1,.94,.88,1))
        buttons.add_widget(later); buttons.add_widget(install); box.add_widget(buttons)
        popup_height = min(Window.height * .82, dp(64 + 43 + 64) + notes_scroll.height)
        popup = Popup(title='', content=box, size_hint=(.90,None), height=max(dp(205), popup_height), background='', background_color=(0,0,0,0))
        dialog['popup'] = popup
        later.bind(on_release=lambda _button: popup.dismiss())
        def begin(_button):
            popup.dismiss()
            if not self._enqueue_apk_download():
                self._health_notice('업데이트를 시작하지 못했어요', '저장공간과 네트워크 연결을 확인한 뒤 다시 시도해 주세요.')
        install.bind(on_release=begin)
        popup.open()

    def _enqueue_apk_download(self):
        """Download an approved release straight into Android Downloads.

        This intentionally uses Android's DownloadManager rather than a
        browser intent, so tapping 업데이트 never opens GitHub first. Android
        still owns the later package-installer confirmation, as it must.
        """
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Context = autoclass('android.content.Context')
            Uri = autoclass('android.net.Uri')
            DownloadManager = autoclass('android.app.DownloadManager')
            Request = autoclass('android.app.DownloadManager$Request')
            Environment = autoclass('android.os.Environment')
            activity = PythonActivity.mActivity
            request = Request(Uri.parse(self._update_apk_url))
            request.setTitle(f'살빼자 v{self.update_version}')
            request.setDescription('최신 APK를 다운로드하고 있어요.')
            request.setMimeType('application/vnd.android.package-archive')
            request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS,
                                                       f'살빼자_{self.update_version}.apk')
            activity.getSystemService(Context.DOWNLOAD_SERVICE).enqueue(request)
            self._health_notice('다운로드를 시작했어요', '완료 알림을 누르면 최신 버전을 설치할 수 있어요.')
            return True
        except Exception:
            Logger.exception('APK DownloadManager request failed')
            return False

    def configure_system_bars(self):
        """Native activity owns the system bars after its SDL surface exists."""
        # Calling Java through PyJNIus during Kivy's first frame races the SDL
        # surface attach on some Android devices. WelltableActivity restores
        # the bars natively after attach instead.
        return None

    def capture_and_stop(self, path):
        Window.screenshot(name=path)
        Clock.schedule_once(lambda _dt: self.stop(), .2)

    def refresh_all(self):
        self.refresh_home(); self.refresh_meals(); self.refresh_workouts(); self.refresh_report(); self.refresh_body()

    def show(self, screen):
        if screen == 'home':
            previous = getattr(self, '_greeting', '')
            self._greeting = random.choice([s for s in self.motivation_lines if s != previous])
        self.root.current = screen
        {
            'home': self.refresh_home,
            'meals': self.refresh_meals,
            'workouts': self.refresh_workouts,
            'report': self.refresh_report,
            'body': self.refresh_body,
        }.get(screen, self.refresh_home)()
        # Tapping a dock item is also a deliberate "back to top" action.
        # Wait one frame so the freshly refreshed content is measurable.
        Clock.schedule_once(lambda _dt: self._scroll_screen_to_top(screen), 0)

    def _scroll_screen_to_top(self, screen):
        try:
            self.root.get_screen(screen).ids[f'{screen}_scroll'].scroll_y = 1
        except (KeyError, AttributeError):
            pass

    def refresh_home(self):
        root=self.root.get_screen('home'); box=root.ids.plan_box; box.clear_widgets()
        plan=self.store.today_plan(); total=sum(s['calories'] for _,s,_ in plan); protein=sum(s['protein'] for _,s,_ in plan); carbs=sum(s.get('carbs', 0) for _,s,_ in plan); done=sum(done for _,_,done in plan)
        group=RoundedCard(
            orientation='vertical',
            size_hint_y=None,
            height=dp(226),
            radius=dp(26),
            background_color=[.052,.063,.090,.78],
            border_color=[.94,.97,1,.085],
            padding=[dp(4), dp(2)],
        )
        plan_by_kind = {kind: (item, completed) for kind, item, completed in plan}
        for idx, kind in enumerate(('breakfast', 'lunch', 'dinner')):
            entry = plan_by_kind.get(kind)
            if entry:
                s, completed = entry
            else:
                s = {'title': '선택한 식단 없음', 'foods': [],
                     'calories': 0, 'protein': 0, 'carbs': 0, 'cafeteria': False}
                completed = False
            # Meal time is a muted label, while the actual set name receives the
            # emphasis.  This avoids the old repeated "아침 · 아침 02" wording.
            colors=[[.26,.46,.79,.85],[.12,.53,.56,.85],[.47,.36,.72,.85]]
            # Cafeteria selection fills the appropriate meal card, but it is
            # not a completed meal. The teal confirmation belongs solely to
            # the selected cafeteria row above; completion remains explicit.
            selected_cafeteria = bool(s.get('cafeteria'))
            card=MealCard(title=s['title'],foods=self.store.compact_food_names(s['foods']),calories=f"{s['calories']:,} kcal",protein=f"단백질 {s['protein']}g",color=colors[idx],meal_type=kind,badge=self.meal_names[kind],divider=idx > 0,cafeteria=selected_cafeteria,completed=bool(completed))
            card.ids.done.text='완료' if completed else '기록'
            card.ids.done.glass_color=(.30,.56,1,.82) if completed else (.12,.16,.25,.62)
            card.ids.done.color=(1,1,1,1) if completed else (.76,.85,1,1)
            if not entry:
                card.ids.done.disabled = True
                card.ids.done.opacity = 0
                card.ids.done.width = 0
                card.calories = ''
                card.protein = ''
            if s.get('cafeteria'):
                if 'calories' in s.get('missing_nutrients', []):
                    card.calories = '열량 미제공'
                if 'protein' in s.get('missing_nutrients', []):
                    card.protein = '단백질 미제공'
                card.ids.done.text = '취소'
                card.ids.done.glass_color = (.35,.14,.19,.88)
                card.ids.done.color = (1,.77,.80,1)
            if completed:
                card.ids.done.disabled = True
                card.ids.done.opacity = 0
                card.ids.done.width = 0
            if completed and getattr(self, '_meal_flash_kind', '') == kind:
                Clock.schedule_once(lambda _dt, target=card: (Animation(glow=1, duration=.15) + Animation(glow=0, duration=.65)).start(target), 0)
            group.add_widget(card)
        box.add_widget(group)
        targets = self.store.profile()
        target_kcal = float(targets.get('target_calories') or 1800)
        target_protein = float(targets.get('target_protein') or 100)
        target_carbs = float(targets.get('target_carbs') or 220)
        root.ids.kcal_current.text = f"{total:,}"
        root.ids.kcal_target.text = f"/ {target_kcal:,.0f}"
        root.ids.protein_current.text = f"{protein:.0f}g"
        root.ids.protein_target.text = f"/ {target_protein:.0f}g"
        root.ids.carbs_current.text = f"{carbs:.0f}g"
        root.ids.carbs_target.text = f"/ {target_carbs:.0f}g"
        incomplete = {key for _,item,_ in plan for key in item.get('missing_nutrients', [])}
        root.ids.nutrition_heading.text = '확인된 영양 · 미제공 제외' if incomplete else '오늘의 영양'
        for key, label in [('calories',root.ids.kcal_current),('protein',root.ids.protein_current),('carbs',root.ids.carbs_current)]:
            if plan and all(key in item.get('missing_nutrients',[]) for _,item,_ in plan):
                label.text = '—'
        root.ids.nutrition_rings.calorie_progress = min(1, total / target_kcal)
        root.ids.nutrition_rings.protein_progress = min(1, protein / target_protein)
        root.ids.nutrition_rings.carbs_progress = min(1, carbs / target_carbs)
        root.ids.done_count.text=f"{done} / 3"
        today=date.today(); label=['월','화','수','목','금','토','일'][today.weekday()]
        root.ids.date_label.text=f"{today.month}월 {today.day}일 · {label}요일"
        profile = self.store.profile()
        name = profile.get('name') or '회원'
        if not getattr(self, '_greeting', ''):
            self._greeting = random.choice(self.motivation_lines)
        root.ids.greeting_name.text = f'{name}님,'
        root.ids.greeting_label.text = self._greeting
        self._render_cafeteria_menu(root)

    def _render_cafeteria_menu(self, root):
        """Render a focused restaurant → meal → counter menu hierarchy."""
        restaurant_box = root.ids.restaurant_box
        restaurant_box.clear_widgets()
        restaurants = self.store.cafeteria_menus()
        if not restaurants:
            return
        ids = {item['id'] for item in restaurants}
        if self.selected_cafeteria_id not in ids:
            self.selected_cafeteria_id = restaurants[0]['id']
        restaurant = next(item for item in restaurants if item['id'] == self.selected_cafeteria_id)
        sync_key = (restaurant['id'], date.today().isoformat())
        if not restaurant.get('synced_at') and sync_key not in self._menu_sync_requested:
            self._menu_sync_requested.add(sync_key)
            Clock.schedule_once(lambda _dt, item=dict(restaurant): self.sync_cafeteria(item), .1)
        is_freshmeal = restaurant.get('provider') == 'freshmeal'
        raw_menu = restaurant.get(self.selected_cafeteria_meal) or ''
        groups = self._menu_groups(raw_menu)
        # Welstory's three named counters remain the main list. Every other
        # published item is deliberately retained for the expandable
        # 테이크아웃 section below instead of being silently discarded.
        if restaurant.get('provider') == 'welstory':
            if not groups and restaurant['id'] not in self._welstory_sync_requested:
                self._welstory_sync_requested.add(restaurant['id'])
                Clock.schedule_once(lambda _dt, item=dict(restaurant): self.sync_cafeteria(item), .25)
        if restaurant.get('provider') == WONDERPLUS_PROVIDER:
            kitchens = []
            non_kitchens = []
            for group in groups:
                match = re.search(r'(?:키친|kitchen|k)\s*([1-4])', group['title'], re.IGNORECASE)
                if match:
                    kitchens.append({**group, 'title': f"K{match.group(1)}"})
                else:
                    # Keep every published non-counter entry. It belongs in
                    # the common takeout picker instead of being discarded.
                    non_kitchens.append(group)
            # The Dongtan counter selector intentionally shows only K1–K4.
            groups = sorted(kitchens, key=lambda item: item['title']) + non_kitchens

        # Existing named counters stay in the primary vertical list. All
        # remaining provider items are available as takeout without changing
        # that established list layout.
        # Only counters deliberately chosen for the home view may remain in
        # the primary list.  Generic labels such as “오늘의 메뉴” are not a
        # named main counter; keeping them here previously hid their dishes
        # from the takeout picker.
        known_main = set(WELSTORY_HOME_GROUPS) | {'더고메', '소담상', '마이보글', 'K1', 'K2', 'K3', 'K4'}
        primary_groups = [group for group in groups if str(group.get('title') or '') in known_main]
        takeout_groups = [group for group in groups if group not in primary_groups]
        has_menu = bool(primary_groups or takeout_groups)
        if not primary_groups and not takeout_groups:
            message = self._menu_errors.get(restaurant['id']) or (
                '오늘 제공되는 식단이 없어요' if restaurant.get('synced_at') else '메뉴를 불러오는 중이에요')
            primary_groups = [{'title': '', 'menu': message}]

        displayed_groups = primary_groups
        # Restaurant and meal are controls.  Counters are deliberately a
        # readable vertical menu list, so a user can compare every counter at
        # once instead of drilling into a third row of tiny buttons.
        def compact_menu(group):
            """Render each remaining counter as a readable vertical list."""
            text = str(group.get('menu') or '')
            return re.sub(r'\s*(?: · |,)\s*', '\n', text)
        menu_lines = [compact_menu(g) for g in displayed_groups]
        capacity = max(12, (Window.width - dp(180)) / dp(12))
        row_heights = [dp(max(84, 19 * sum(max(1, math.ceil(len(line) / capacity)) for line in text.splitlines()) + 16)) for text in menu_lines]
        # Takeout is intentionally a separate scrollable dialog. Keeping it
        # out of this home card prevents a long menu from pushing the actual
        # meal controls off screen on small phones.
        takeout_height = dp(38) if takeout_groups else 0
        card_height = dp(128) + sum(row_heights) + takeout_height
        # Use the same dark-glass surface as the other home cards.  A more
        # opaque blue cafeteria panel made this one section look detached
        # from the main page even though it is part of the same card system.
        card = RoundedCard(orientation='vertical', size_hint_y=None, height=card_height, radius=dp(24),
                           padding=(dp(14), dp(12)), spacing=dp(6),
                           surface_color=[.055,.087,.145,1], surface_opacity=.50,
                           background_color=[.055,.087,.145,.50], border_color=[.72,.84,1,.26])
        title_row = BoxLayout(size_hint_y=None, height=dp(22))
        title_row.add_widget(Label(text=f"오늘의 구내식당  ·  {restaurant['name']}", font_name=self.font_name, font_size=dp(13), bold=True,
                                   color=(.90,1,.96,1), halign='left', valign='middle', text_size=(dp(250), dp(22)), shorten=True))
        title_row.children[0].bind(size=lambda w,v: setattr(w,'text_size',v))
        title_row.add_widget(GlassButton(text='새로고침', font_name=self.font_name, size_hint_x=None, width=dp(64), font_size=dp(9),
                                         glass_color=(.10,.25,.25,.82), color=(.67,1,.87,1),
                                         on_release=lambda _button: self.sync_cafeteria(restaurant)))
        card.add_widget(title_row)

        restaurant_tabs = BoxLayout(size_hint_y=None, height=dp(30), spacing=dp(5))
        slot_names = ('화성', '천안', '동탄')
        for idx, item in enumerate(restaurants, start=1):
            active = item['id'] == restaurant['id']
            location = next((name for name in slot_names if name in item['name']), item['name'])
            tab = CafeteriaTab(text=location, selected=active, font_name=self.font_name, font_size=dp(9),
                              glass_color=(.14,.42,.34,.92) if active else (.10,.14,.23,.76),
                              color=(.78,1,.88,1) if active else (.62,.70,.84,1))
            tab.bind(on_release=lambda _button, cafe_id=item['id']: self.select_home_cafeteria(cafe_id))
            restaurant_tabs.add_widget(tab)
        card.add_widget(restaurant_tabs)

        meal_tabs = BoxLayout(size_hint_y=None, height=dp(30), spacing=dp(5))
        for label, key in (('아침', 'breakfast'), ('점심', 'lunch'), ('저녁', 'dinner')):
            active = key == self.selected_cafeteria_meal
            tab = CafeteriaTab(text=label, selected=active, font_name=self.font_name, font_size=dp(9),
                              glass_color=(.20,.33,.62,.90) if active else (.075,.105,.17,.78),
                              color=(.90,.94,1,1) if active else (.60,.69,.84,1))
            tab.bind(on_release=lambda _button, meal_key=key: self.select_home_cafeteria_meal(meal_key))
            meal_tabs.add_widget(tab)
        card.add_widget(meal_tabs)

        menu_list = RoundedCard(orientation='vertical', size_hint_y=None,
                                height=sum(row_heights) + takeout_height + dp(4), radius=dp(15),
                                padding=(dp(9), dp(2)), spacing=0,
                                background_color=[.035,.052,.078,.76], border_color=[0,0,0,0], rim_strength=0)
        for group, row_height, menu_text in zip(displayed_groups, row_heights, menu_lines):
            chosen_title = f"{group['title']} · {group['menu']}"
            current_choice = self.store.cafeteria_choice(self.selected_cafeteria_meal)
            selected_menu = bool(current_choice and current_choice.get('title') == chosen_title)
            # The complete cafeteria-menu row is the selection block: its
            # vendor label, menu body and detail action all receive one teal
            # treatment. The selected menu also fills its matching meal
            # card below without marking it eaten.
            row = RoundedCard(orientation='horizontal', size_hint_y=None, height=row_height,
                              radius=dp(11), padding=(dp(3), 0), spacing=dp(4),
                              # RoundedCard uses ``surface_color`` for RGB
                              # and background alpha for opacity. Passing only
                              # background_color previously changed no colour
                              # at all, leaving just mint text visible.
                              surface_color=[.05,.58,.50,1] if selected_menu else [.065,.09,.145,1],
                              surface_opacity=.96 if selected_menu else .50,
                              background_color=[1,1,1,.90] if selected_menu else [0,0,0,0],
                              # A selected counter is a filled teal block,
                              # not an outlined card within another card.
                              border_color=[0,0,0,0], rim_strength=0)
            # The restaurant label (e.g. "소담상") is part of the selection
            # target as well.  Users naturally tap that left-hand label, so a
            # passive Label here made the visual selection appear broken.
            vendor = Button(text=group['title'], font_name=self.font_name, size_hint_x=None, width=dp(52), font_size=dp(11), bold=True,
                            background_normal='', background_color=(0,0,0,0),
                            color=(.88,1,.95,1) if selected_menu else (.62,.95,.84,1), halign='center', valign='middle', shorten=True)
            vendor.bind(size=lambda widget, size: setattr(widget, 'text_size', (size[0], size[1])))
            vendor.bind(on_release=lambda _b, meal_key=self.selected_cafeteria_meal, title=chosen_title, nutrients=group.get('nutrition', {}): self.choose_cafeteria_meal(meal_key, title, nutrients))
            row.add_widget(vendor)
            menu = Button(text=menu_text, font_name=self.font_name, font_size=dp(12), halign='left', valign='middle',
                          background_normal='', background_color=(0,0,0,0),
                          color=(.84,1,.93,1) if selected_menu else (.86,.91,.96,1), shorten=False)
            menu.bind(size=lambda widget, size: setattr(widget, 'text_size', (size[0], size[1])))
            # The visible representative menu itself is the quick selection
            # target.  This avoids a second tiny action button for every row.
            menu.bind(on_release=lambda _b, meal_key=self.selected_cafeteria_meal, title=chosen_title, nutrients=group.get('nutrition', {}): self.choose_cafeteria_meal(meal_key, title, nutrients))
            row.add_widget(menu)
            choose = GlassButton(text='···', font_name=self.font_name, size_hint_x=None, width=dp(38), font_size=dp(13),
                                 glass_color=(.05,.58,.50,.88) if selected_menu else (.11,.16,.25,.86),
                                 color=(.88,1,.95,1) if selected_menu else (.78,.87,1,1))
            choose.size_hint_y = None
            choose.height = dp(32)
            choose.pos_hint = {'center_y': .5}
            choose.disabled = not has_menu
            choose.opacity = 1 if has_menu else 0
            choose.bind(on_release=lambda _button, item=dict(group): self.popup_cafeteria_detail(item))
            row.add_widget(choose)
            menu_list.add_widget(row)
            if selected_menu and getattr(self, '_cafeteria_flash', None) == (self.selected_cafeteria_meal, chosen_title):
                Clock.schedule_once(
                    lambda _dt, target=row: (Animation(surface_color=[.36,1,.89,1], duration=.12)
                                             + Animation(surface_color=[.05,.58,.50,1], duration=.58)).start(target),
                    0,
                )
        if takeout_groups:
            takeout_button = GlassButton(
                text='테이크아웃  ·  메뉴 보기', font_name=self.font_name,
                size_hint_y=None, height=dp(34), font_size=dp(11),
                glass_color=(.08,.13,.21,.82), color=(.80,1,.92,1),
            )
            takeout_button.bind(on_release=lambda _button, item=dict(restaurant), groups=[dict(group) for group in takeout_groups]: self.popup_takeout_choices(item, groups))
            menu_list.add_widget(takeout_button)
        card.add_widget(menu_list)
        restaurant_box.add_widget(card)
        self._update_cafeteria_widget(restaurant, displayed_groups)

    @staticmethod
    def _update_cafeteria_widget(restaurant, groups):
        """Publish only the cafeteria block to Android's home-screen widget."""
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Context = autoclass('android.content.Context')
            Provider = autoclass('com.welltable.welltable.CafeteriaWidgetProvider')
            activity = PythonActivity.mActivity
            prefs = activity.getSharedPreferences('cafeteria_widget', Context.MODE_PRIVATE)
            meal_name = {'breakfast': '아침', 'lunch': '점심', 'dinner': '저녁'}.get(
                str(getattr(App.get_running_app(), 'selected_cafeteria_meal', '')), '오늘')
            lines = []
            for group in groups[:3]:
                title = str(group.get('title') or '')
                menu = str(group.get('menu') or '').replace(' · ', ' · ')
                lines.append((title + '  ' + menu).strip())
            editor = prefs.edit()
            editor.putString('title', f"오늘의 구내식당 · {restaurant.get('name', '')}")
            editor.putString('meal', meal_name)
            editor.putString('menu', '\n'.join(lines) if lines else '오늘 제공되는 식단이 없어요')
            editor.apply()
            Provider.updateAll(activity)
        except Exception:
            # Widgets are Android-only and must never interfere with the app.
            pass

    def open_cafeteria_source(self, restaurant):
        """Open the public menu page for the selected cafeteria."""
        provider = str(restaurant.get('provider') or '')
        path = str(restaurant.get('remote_path') or '')
        if provider == 'welstory' and path.startswith('/'):
            url = 'https://welplan.pmh.codes' + path.rstrip('/') + '/' + date.today().strftime('%Y%m%d')
        elif provider == 'freshmeal':
            url = 'https://www.welstory.com/'
        elif provider == WONDERPLUS_PROVIDER:
            url = 'https://wonderplus.co.kr/'
        else:
            url = 'https://welplan.pmh.codes/'
        try:
            webbrowser.open(url)
        except Exception:
            self._health_notice('메뉴 앱을 열 수 없어요', '기기의 브라우저 또는 연결 상태를 확인해 주세요.')

    @staticmethod
    def _menu_groups(raw_menu):
        """Read both new structured menu records and older text-only rows."""
        if not raw_menu:
            return []
        try:
            decoded = json.loads(raw_menu)
            if isinstance(decoded, list):
                result = []
                for item in decoded:
                    if isinstance(item, dict) and item.get('menu'):
                        result.append({**item, 'title': str(item.get('title') or '오늘의 메뉴'), 'menu': str(item['menu'])})
                return result
        except (TypeError, ValueError):
            pass
        result = []
        for section in str(raw_menu).split(' / '):
            title, separator, menu = section.partition(' · ')
            result.append({'title': title if separator else '오늘의 메뉴', 'menu': menu if separator else section})
        return result

    def select_home_cafeteria(self, cafeteria_id):
        self.selected_cafeteria_id = cafeteria_id
        self.selected_cafeteria_group = ''
        self.refresh_home()

    def select_home_cafeteria_meal(self, meal_key):
        self.selected_cafeteria_meal = meal_key
        self.selected_cafeteria_group = ''
        self.refresh_home()

    def select_home_cafeteria_group(self, group_title):
        self.selected_cafeteria_group = group_title
        self.refresh_home()

    def toggle_meal(self, kind):
        completed, item = self.store.toggle_meal_complete(kind)
        self._meal_flash_kind = kind if completed else ''
        if completed and item:
            self.write_health_nutrition(item)
        self.refresh_home()
    def choose_cafeteria_meal(self, meal_type, title, nutrition=None):
        selected = self.store.toggle_cafeteria_choice(meal_type, title, nutrition)
        self._cafeteria_flash = (meal_type, title) if selected else None
        self.refresh_home()
    def choose_takeout_meal(self, meal_type, title, nutrition=None):
        selected = self.store.toggle_takeout_choice(meal_type, title, nutrition)
        if selected is None:
            self._health_notice('완료된 식단이에요', '오늘의 식단 블록을 다시 눌러 완료를 해제한 뒤 변경할 수 있어요.')
            return
        self._takeout_flash = (meal_type, title) if selected else None
        self.selected_cafeteria_group = 'takeout'
        self.refresh_home()
    def clear_cafeteria_meal(self, meal_type):
        self.store.clear_cafeteria_meal(meal_type)
        self.refresh_home()
    def new_plan(self): self.store.today_plan(refresh=True);self.refresh_home()

    def refresh_meals(self):
        root=self.root.get_screen('meals'); box=root.ids.set_box;box.clear_widgets()
        for kind in ('breakfast','lunch','dinner'):
            sets = [s for s in self.store.sets() if s['meal_type'] == kind]
            box.add_widget(Label(text=self.meal_names[kind], font_name=self.font_name, size_hint_y=None, height=dp(28), color=(.62,.74,1,1), bold=True, halign='left', text_size=(dp(300),None)))
            for s in sets:
                row = BoxLayout(size_hint_y=None, height=dp(78), spacing=dp(8))
                row.add_widget(MealSetLine(meal_set_id=s['id'], title=s['title'], tag=self.meal_names[s['meal_type']],
                                           detail=self.store.compact_food_names(s['foods']),
                                           tail=f"{s['calories']} kcal  ·  편집 ›"))
                delete = GlassButton(text='삭제', size_hint=(None,None), size=(dp(48),dp(34)), pos_hint={'center_y':.5}, color=(1,.65,.7,1))
                delete.bind(on_release=lambda _b, item=dict(s): self.confirm_delete_set(item))
                row.add_widget(delete); box.add_widget(row)
        if not self.store.sets():
            box.add_widget(Label(text='아직 만든 식단 세트가 없어요.\n상단의 ‘세트 만들기’에서 첫 식단을 구성해 보세요.', font_name=self.font_name, size_hint_y=None, height=dp(90), color=(.66,.74,.88,1), halign='center', valign='middle', text_size=(dp(300),dp(90))))

    def refresh_workouts(self):
        root=self.root.get_screen('workouts'); records=self.store.workouts(); box=root.ids.workout_box;box.clear_widgets()
        today = date.today()
        week_start = today - timedelta(days=6)
        week_records = [x for x in records if week_start <= date.fromisoformat(x['workout_date']) <= today]
        total = sum(x['minutes'] for x in week_records)
        profile = self.store.profile()
        steps = int(profile.get('steps') or 0)
        # These four fields come from one native Health Connect snapshot.  Do
        # not substitute session totals here: Samsung Health's activity time
        # and activity calories are different metrics from exercise sessions.
        today_minutes = int(profile.get('active_minutes') or 0)
        # Only Health Connect's ActiveCaloriesBurned record belongs here;
        # total energy is deliberately excluded.
        today_kcal = max(0, int(profile.get('active_calories') or 0))
        # Some Samsung Health providers expose no usable activity record.
        # In that case the UI falls back to their total, rather than claiming
        # that an otherwise active day burned 0 kcal.
        if today_kcal <= 0:
            today_kcal = max(0, int(profile.get('total_calories') or 0))
        distance_meters = int(profile.get('distance_meters') or 0)
        step_goal = max(1, int(profile.get('target_steps') or 6300))
        exercise_calorie_goal = max(1, int(profile.get('target_exercise_calories') or 300))
        # Same hierarchy as the reference cards: bright dot = metric, then value.
        root.ids.activity_steps.text = f'[color=baff35]●[/color]  {steps:,} 걸음'
        root.ids.activity_minutes.text = f'[color=1bbcff]●[/color]  {today_minutes:,} 분'
        root.ids.activity_kcal.text = f'[color=b85cff]●[/color]  {today_kcal:,} kcal'
        root.ids.activity_distance.text = ('—' if distance_meters <= 0 else f'{distance_meters / 1000:.2f} km')
        root.ids.step_card_value.text = f'{steps:,}'
        root.ids.step_card_target.text = (f'목표 {step_goal:,} 걸음' if distance_meters <= 0
                                          else f'목표 {step_goal:,} 걸음  ·  {distance_meters / 1000:.2f} km')
        root.ids.steps_progress_bar.max = step_goal
        root.ids.steps_progress_bar.value = min(step_goal, steps)
        rings = root.ids.activity_rings
        rings.steps_progress = min(1, steps / step_goal)
        rings.minutes_progress = min(1, today_minutes / 60)
        rings.calories_progress = min(1, today_kcal / exercise_calorie_goal)
        hours, minutes = divmod(total, 60)
        root.ids.week_duration.text = f'{hours}:{minutes:02d}:00'
        root.ids.week_sessions.text = f'{len(week_records)}개 세션'
        root.ids.week_kcal.text = f'{sum(x["calories"] for x in week_records):,} kcal'
        # Sunday-first bars make the dates and the selected day immediately legible.
        by_day = {day_: 0 for day_ in range(7)}
        for row in week_records:
            by_day[date.fromisoformat(row['workout_date']).weekday()] += row['minutes']
        ids = ('week_mon', 'week_tue', 'week_wed', 'week_thu', 'week_fri', 'week_sat', 'week_sun')
        ceiling = max(30, max(by_day.values(), default=0))
        for weekday, widget_id in enumerate(ids):
            bar = root.ids[widget_id]
            bar.level = max(.06, by_day[weekday] / ceiling)
            bar.active = weekday == today.weekday()
        for x in records:
            detail = f"{x['minutes']}분 · Health Connect" if x['source'] == 'health_connect' else f"{x['minutes']}분 · {x['calories']} kcal"
            box.add_widget(SwipeWorkout(workout_id=x['id'], title=x['title'], icon=self.workout_icon(x['title']), tag=x['workout_date'], detail=detail, tail='← 밀어서 삭제'))

    @staticmethod
    def workout_icon(title):
        for words, glyph in [(('걷','walk'), '\ue536'), (('달리','러닝','run'), '\ue566'),
                             (('자전거','cycle','cycling'), '\ue52f'), (('수영','swim'), '\ueb48'),
                             (('요가','스트레칭','yoga'), '\uea88'), (('등산','하이킹','hiking'), '\ue50a')]:
            if any(word in title.lower() for word in words): return glyph
        return '\ueb43'

    def refresh_report(self):
        root=self.root.get_screen('report'); ws=self.store.workouts(); total=sum(x['minutes'] for x in ws if date.fromisoformat(x['workout_date'])>=date.today()-timedelta(days=6)); kcal=sum(x['calories'] for x in ws if date.fromisoformat(x['workout_date'])>=date.today()-timedelta(days=6)); plan=self.store.today_plan(); score=min(99,58+int(total*.14)+sum(x[2] for x in plan)*4)
        root.ids.score.text=str(score);root.ids.report_minutes.text=f'{total}분';root.ids.report_kcal.text=f'{kcal:,} kcal'
        # Each graph comes from the same persisted source that powers the
        # profile card.  Sorting by date avoids the “latest first” query order
        # drawing a reversed trend.
        body_rows = sorted(self.store.body(), key=lambda item: item['log_date'])[-7:]
        metrics = (
            ('weight', 'report_weight_value', 'report_weight_trend', 'kg'),
            ('muscle', 'report_muscle_value', 'report_muscle_trend', 'kg'),
            ('fat', 'report_fat_value', 'report_fat_trend', '%'),
        )
        for key, value_id, trend_id, unit in metrics:
            values = [float(row[key]) for row in body_rows if row.get(key) is not None and float(row.get(key) or 0) > 0]
            root.ids[trend_id].values = values
            root.ids[value_id].text = '미기록' if not values else f'{values[-1]:.1f} {unit}'

    def refresh_body(self):
        root=self.root.get_screen('body'); rows=self.store.body(); now=rows[0] if rows else {}
        # A Health Connect source can publish weight and body-fat at different
        # times.  Treat 0 as a legitimate numeric value and keep every latest
        # field visible instead of collapsing the entire profile to “미기록”.
        has_weight = now.get('weight') is not None and float(now.get('weight') or 0) > 0
        root.ids.weight.text='미기록' if not has_weight else f"{now['weight']:.1f}"
        root.ids.weight.font_size = dp(20) if not has_weight else dp(42)
        root.ids.weight_unit.text='' if not has_weight else 'kg'
        root.ids.fat.text='미기록' if now.get('fat') is None else f"{float(now['fat']):.1f}%"
        root.ids.muscle.text='미기록' if now.get('muscle') is None or float(now.get('muscle') or 0) <= 0 else f"{float(now['muscle']):.1f} kg"
        profile = self.store.profile()
        root.ids.heart_rate.text = '—' if not profile.get('heart_rate') else f"{profile['heart_rate']} bpm"
        root.ids.sleep_hours.text = '—' if profile.get('sleep_hours') is None else f"{profile['sleep_hours']:.1f}시간"
        restaurants = self.store.cafeterias()
        root.ids.cafeteria_summary.text = '설정한 식당이 없어요' if not restaurants else f"{len(restaurants)} / 3개 설정됨 · 대표: {restaurants[0]['name']}"
        box=root.ids.body_box;box.clear_widgets()
        for x in rows:
            if x.get('weight') is None and x.get('fat') is None and x.get('muscle') is None:
                continue
            source = 'Health Connect' if x['source'] == 'health_connect' else '직접 기록'
            weight_text = '체중 미기록' if not x.get('weight') else f"{float(x['weight']):.1f} kg"
            fat_text = '체지방 미기록' if x.get('fat') is None else f"체지방 {float(x['fat']):.1f}%"
            muscle_text = '골격근 미기록' if not x.get('muscle') else f"골격근 {float(x['muscle']):.1f} kg"
            box.add_widget(self.line_item(x['log_date'], weight_text, f"{fat_text} · {muscle_text}", source))
        root.ids.version_label.text = f'살빼자  ·  v{APP_VERSION}'

    def confirm_delete_set(self, item):
        box = RoundedCard(orientation='vertical', padding=dp(20), spacing=dp(12))
        header, holder = self._dialog_header('식단 세트 삭제', '과거 기록은 유지하고, 오늘 이후 배정에서 제외해요.')
        box.add_widget(header)
        box.add_widget(Label(text=item['title'], font_name=self.font_name, color=(1,1,1,1)))
        button = GlassButton(text='삭제', size_hint_y=None, height=dp(42), color=(1,.66,.71,1))
        box.add_widget(button)
        popup = Popup(content=box, title='', size_hint=(.9,None), height=dp(235), background='', background_color=(0,0,0,0))
        holder['popup'] = popup
        def remove(_):
            self.store.delete_set(item['id']); popup.dismiss(); self.refresh_all()
        button.bind(on_release=remove); popup.open()

    def popup_cafeteria_detail(self, item):
        box = RoundedCard(orientation='vertical', padding=dp(20), spacing=dp(12))
        header, holder = self._dialog_header(item['title'], '식당 제공 영양정보 · 미제공 항목은 합계에서 제외')
        box.add_widget(header)
        scroll = ScrollView(do_scroll_x=False)
        text = item['menu'] + '\n\n'
        for key, title, unit in [('calories','열량','kcal'),('carbs','탄수화물','g'),
                                 ('sugar','당류','g'),('fiber','식이섬유','g'),
                                 ('protein','단백질','g'),('fat','지방','g'),
                                 ('saturated_fat','포화지방','g'),('trans_fat','트랜스지방','g'),
                                 ('sodium','나트륨','mg')]:
            value = item.get('nutrition', {}).get(key)
            text += f'{title}   ' + ('미제공' if value is None else f'{value:g} {unit}') + '\n'
        text += '\n' + item.get('source_note', '식당에서 공개한 값이며 실제 제공량에 따라 달라질 수 있어요.')
        label = Label(text=text, font_name=self.font_name, font_size=dp(14), size_hint_y=None, halign='left', valign='top', color=(.87,.92,.98,1))
        label.bind(width=lambda w,v: setattr(w,'text_size',(v,None)), texture_size=lambda w,v: setattr(w,'height',v[1]))
        scroll.add_widget(label); box.add_widget(scroll)
        popup = Popup(content=box, title='', size_hint=(.92,.72), background='', background_color=(0,0,0,0))
        holder['popup'] = popup; popup.open()

    def popup_takeout_choices(self, restaurant, groups):
        """Show every non-main cafeteria menu in a bounded, scrollable picker."""
        box = RoundedCard(orientation='vertical', padding=dp(18), spacing=dp(10), radius=dp(26))
        meal_label = self.meal_names.get(self.selected_cafeteria_meal, '식사')
        header, holder = self._dialog_header('테이크아웃 메뉴', f"{restaurant.get('name', '')} · {meal_label} · 여러 메뉴를 선택할 수 있어요.")
        box.add_widget(header)
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        list_box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(7), padding=(0, dp(2)))
        list_box.bind(minimum_height=list_box.setter('height'))
        selected_takeouts = {row['title'] for row in self.store.takeout_choices(self.selected_cafeteria_meal)}

        for group in groups:
            menu_raw = str(group.get('menu') or '')
            menu_text = re.sub(r'\s*(?: · |,)\s*', '\n', menu_raw)
            group_title = str(group.get('title') or '')
            takeout_title = menu_raw if group_title in ('', '오늘의 메뉴') else f'{group_title} · {menu_raw}'
            selected = takeout_title in selected_takeouts
            line_count = max(1, len(menu_text.splitlines()))
            row = RoundedCard(orientation='horizontal', size_hint_y=None,
                              height=dp(max(58, 19 * line_count + 18)), radius=dp(12),
                              padding=(dp(10), dp(4)), spacing=dp(6),
                              surface_color=[.05,.58,.50,1] if selected else [.065,.09,.145,1],
                              surface_opacity=.96 if selected else .58,
                              background_color=[1,1,1,.90] if selected else [0,0,0,0],
                              border_color=[0,0,0,0], rim_strength=0)
            item_button = Button(text=(menu_text if group_title in ('', '오늘의 메뉴') else f'{group_title}\n{menu_text}'), font_name=self.font_name, font_size=dp(11),
                                 halign='left', valign='middle', background_normal='', background_color=(0,0,0,0),
                                 color=(.84,1,.93,1) if selected else (.86,.91,.96,1), shorten=False)
            item_button.bind(size=lambda widget, size: setattr(widget, 'text_size', (size[0], size[1])))
            def toggle(_button, meal_key=self.selected_cafeteria_meal, title=takeout_title,
                       nutrients=group.get('nutrition', {}), source_group=dict(group)):
                result = self.store.toggle_takeout_choice(meal_key, title, nutrients)
                if result is None:
                    self._health_notice('완료된 식단이에요', '오늘의 식단 블록을 다시 눌러 완료를 해제한 뒤 변경할 수 있어요.')
                    return
                self._takeout_flash = (meal_key, title) if result else None
                holder['popup'].dismiss()
                self.refresh_home()
                Clock.schedule_once(lambda _dt: self.popup_takeout_choices(restaurant, groups), .05)
            item_button.bind(on_release=toggle)
            row.add_widget(item_button)
            detail = GlassButton(text='···', font_name=self.font_name, size_hint=(None, None),
                                 size=(dp(38), dp(32)), pos_hint={'center_y': .5}, font_size=dp(13),
                                 glass_color=(.05,.58,.50,.88) if selected else (.11,.16,.25,.86),
                                 color=(.88,1,.95,1) if selected else (.78,.87,1,1))
            detail.bind(on_release=lambda _button, item=dict(group): self.popup_cafeteria_detail(item))
            row.add_widget(detail)
            list_box.add_widget(row)
        scroll.add_widget(list_box)
        box.add_widget(scroll)
        popup = Popup(content=box, title='', size_hint=(.94, .80), background='', background_color=(0,0,0,0))
        holder['popup'] = popup
        popup.open()

    def line_item(self,title,tag,detail,tail):
        return ListLine(title=title, tag=tag, detail=detail, tail=tail)

    def delete_workout(self, workout_id):
        self.store.delete_workout(workout_id)
        self.refresh_all()

    @staticmethod
    def _menu_text(markdown):
        """Preserve Welstory corner names instead of flattening them to one line.

        Public Welplan pages can represent a counter as a heading, a bold
        bullet, or ``한식사계: 메뉴``.  The parser accepts all three variants
        and stores the result as the same JSON group format used by FreshMeal.
        """
        meal_keys = {'아침': 'breakfast', '점심': 'lunch', '저녁': 'dinner'}
        collected = {key: [] for key in meal_keys.values()}
        current = None
        active_group = '오늘의 메뉴'

        def clean_text(value):
            value = re.sub(r'^[#>*\-+\s]+', '', value.strip())
            value = re.sub(r'[`*_]', '', value).strip()
            return re.sub(r'\s+', ' ', value)

        def append_menu(value):
            if not current:
                return
            value = clean_text(value)
            if not value or value in WELSTORY_HOME_GROUPS:
                return
            # Nutrient/source sub-lines are not menu items and make marquees noisy.
            if any(token in value.lower() for token in ('칼로리', '알레르기', '원산지', '영양성분', 'nutrition:', 'components:')):
                return
            bucket = collected[current]
            record = {'title': active_group, 'menu': value}
            if record not in bucket:
                bucket.append(record)

        for raw in markdown.splitlines():
            stripped = raw.strip()
            plain = clean_text(stripped)
            heading = re.sub(r'^#+\s*', '', stripped)
            heading = re.sub(r'[`*_]', '', heading).strip()
            if heading in meal_keys:
                current = meal_keys[heading]
                active_group = '오늘의 메뉴'
                continue
            if not current:
                continue

            matched_group = next((name for name in WELSTORY_HOME_GROUPS if name in plain), None)
            if matched_group:
                active_group = matched_group
                # When a line contains both the counter and its first item,
                # retain the item.  Pure headings deliberately add nothing.
                remainder = plain.replace(matched_group, '', 1)
                remainder = re.sub(r'^[\[\]【】\s:：|\-–—·]+', '', remainder).strip()
                if remainder and remainder not in ('메뉴', '식단'):
                    append_menu(remainder)
                continue

            # Only list rows and table cells are menu candidates. This avoids
            # accidentally treating the next date/page heading as food.
            if stripped.startswith(('- ', '* ', '+ ', '|')):
                append_menu(plain.strip('|').strip())

        output = {}
        for key, rows in collected.items():
            # Certain public Welstory pages publish dishes without a corner
            # label. Split those unlabelled rows into the requested Korean /
            # global tiles; a source-provided counter label always wins.
            if rows:
                global_terms = ('파스타', '피자', '마라', '쌀국수', '카레', '돈까스', '가츠', '우동', '라멘', '탄탄면', '볶음면', '버거', '스테이크', '타코', '샌드위치', '포케')
                for item in rows:
                    if item['title'] != '오늘의 메뉴':
                        continue
                    item['title'] = '별미공방' if any(term in item['menu'] for term in global_terms) else '한식사계'
            grouped = []
            for title in WELSTORY_HOME_GROUPS:
                menus = [item['menu'] for item in rows if item['title'] == title]
                if menus:
                    grouped.append({'title': title, 'menu': ' · '.join(menus[:5])})
            output[key] = json.dumps(grouped, ensure_ascii=False) if grouped else ''
        return output

    def sync_cafeteria(self, restaurant):
        if restaurant.get('provider') == 'freshmeal':
            self._sync_freshmeal_cafeteria(restaurant)
            return
        if restaurant.get('provider') == PULMUONE_PROVIDER:
            self._sync_pulmuone_cafeteria(restaurant)
            return
        if restaurant.get('provider') == WONDERPLUS_PROVIDER:
            self._sync_wonderplus_cafeteria(restaurant)
            return
        provider_code = restaurant.get('provider') or 'welstory'
        provider_name = PROVIDER_LABELS.get(provider_code, '식당')
        def worker():
            try:
                path = restaurant.get('remote_path') or ''
                # Repair restaurants saved by earlier builds: resolve their
                # name to a real public restaurant id before requesting menus.
                if not path:
                    search_url = SERVICE_BASE_URL + '/api/welstory-search?' + urllib.parse.urlencode({'q': restaurant['name']})
                    found = self._fetch_public_json(search_url, SERVICE_BASE_URL + '/')
                    if not found: raise RuntimeError('식당을 찾지 못했습니다')
                    item = found[0]; slug = urllib.parse.quote(item['name'].strip().lower().replace(' ', '-'), safe='-')
                    default_vendor = 'welstory'
                    path = f"/restaurants/{item.get('vendor', default_vendor)}/{item['id']}/{slug}"
                day = date.today().strftime('%Y%m%d')
                url = SERVICE_BASE_URL + '/api/welstory-menu?' + urllib.parse.urlencode({'path': path, 'date': day})
                document = self._fetch_public_text(url, 'text/html', SERVICE_BASE_URL + '/')
                meals = enrich_welstory(self._fetch_welstory_detail, welstory_html(document, day))
                # Empty published menus are a normal response.  Persist them
                # so the card shows an inline empty state rather than a popup.
                Clock.schedule_once(lambda _dt, cafe_id=restaurant['id'], fetched=meals, saved_path=path:
                                    self._commit_cafeteria_sync(cafe_id, fetched, saved_path, provider_name), 0)
            except Exception as exc:
                Logger.exception('%s public menu sync failed', provider_name)
                detail = str(exc).strip() or '네트워크 상태를 확인해 주세요.'
                Clock.schedule_once(lambda _dt: self._health_notice(f'{provider_name} 메뉴를 불러오지 못했어요', detail[:110]), 0)
        Thread(target=worker, daemon=True).start()

    def _fetch_welstory_detail(self, original_url, *_args, **_kwargs):
        """Use the trusted app service for Welplan's public detail request."""
        parsed = urllib.parse.urlsplit(original_url)
        marker = '/proxy/'
        if marker not in parsed.path or not parsed.path.endswith('/menus/detail'):
            raise ValueError('지원하지 않는 웰스토리 상세 경로입니다.')
        restaurant = urllib.parse.unquote(parsed.path.split(marker, 1)[1].rsplit('/menus/detail', 1)[0])
        parameters = urllib.parse.parse_qs(parsed.query)
        payload = {'restaurant': restaurant}
        for key in ('date', 'mealTimeId', 'hallNo', 'courseType', 'nutrient'):
            if parameters.get(key):
                payload[key] = parameters[key][0]
        url = SERVICE_BASE_URL + '/api/welstory-detail?' + urllib.parse.urlencode(payload)
        return self._fetch_public_text(url, 'application/json', SERVICE_BASE_URL + '/')

    @staticmethod
    def pulmuone_sites(keyword):
        normalized = re.sub(r'\s+', '', keyword).lower()
        if not normalized:
            return list(PULMUONE_PUBLIC_SITES)
        return [site for site in PULMUONE_PUBLIC_SITES
                if any(normalized in re.sub(r'\s+', '', term).lower() or
                       re.sub(r'\s+', '', term).lower() in normalized
                       for term in (site['name'], *site['aliases']))]

    @staticmethod
    def wonderplus_sites(keyword):
        normalized = re.sub(r'\s+', '', keyword).lower()
        if not normalized:
            return list(WONDERPLUS_SITES)
        return [site for site in WONDERPLUS_SITES
                if any(normalized in re.sub(r'\s+', '', term).lower() or
                       re.sub(r'\s+', '', term).lower() in normalized
                       for term in (site['name'], *site['aliases']))]

    @staticmethod
    def _pulmuone_menu_text(html):
        """Parse the published daily Food & Culture table without app login."""
        today_id = date.today().isoformat()
        block_match = re.search(r'<div class="item" id="%s">(.*?)(?=<div class="item" id=|</div>\s*</div>\s*</div>)' % re.escape(today_id), html, re.S)
        block = block_match.group(1) if block_match else html
        meals = {'breakfast': '', 'lunch': '', 'dinner': ''}
        labels = (('breakfast', '조식|아침'), ('lunch', '중식|점심'), ('dinner', '석식|저녁'))
        for key, label in labels:
            match = re.search(r'<div class="menu[^\"]*">.*?<h5>.*?(?:%s).*?</h5>.*?<p class="menu_item">\s*(.*?)\s*</p>' % label, block, re.S)
            if match:
                text = re.sub(r'<[^>]+>', '', match.group(1)).strip()
                if text:
                    meals[key] = json.dumps([{'title': '오늘의 메뉴', 'menu': text}], ensure_ascii=False)
        return meals

    def _sync_pulmuone_cafeteria(self, restaurant):
        """Read a business site's public menu; never use WonderPul credentials."""
        raw_path = str(restaurant.get('remote_path') or '')
        menu_url = raw_path.split('pulmuone-public:', 1)[1] if raw_path.startswith('pulmuone-public:') else ''
        if not menu_url:
            self._health_notice('풀무원 메뉴 정보를 확인할 수 없어요', '식당 설정에서 공개 메뉴가 있는 사업장을 다시 선택해 주세요.')
            return
        def worker():
            try:
                html = self._fetch_public_text(menu_url, 'text/html, */*', menu_url)
                meals = self._pulmuone_menu_text(html)
                # No menu today is displayed directly inside the restaurant
                # card, not as an error dialog.
                Clock.schedule_once(lambda _dt, cafe_id=restaurant['id'], fetched=meals:
                                    self._commit_cafeteria_sync(cafe_id, fetched, provider_name='풀무원'), 0)
            except Exception as exc:
                Logger.exception('Pulmuone public menu sync failed')
                Clock.schedule_once(lambda _dt: self._health_notice('풀무원 메뉴를 불러오지 못했어요', str(exc).strip()[:110] or '잠시 뒤 다시 시도해 주세요.'), 0)
        Thread(target=worker, daemon=True).start()

    def _sync_wonderplus_cafeteria(self, restaurant):
        cafe_id = restaurant['id']
        if cafe_id in self._menu_syncing:
            return
        self._menu_syncing.add(cafe_id)
        self._menu_errors.pop(cafe_id, None)
        def finish(meals=None, error=None):
            self._menu_syncing.discard(cafe_id)
            if error:
                self._menu_errors[cafe_id] = '연결을 확인한 뒤 새로고침해 주세요'
                self.refresh_home()
            else:
                self._commit_cafeteria_sync(cafe_id, meals, provider_name='원더풀 플러스')
        def worker():
            try:
                meals = fetch_wonderplus_menus(self._fetch_public_text, restaurant['name'])
                Clock.schedule_once(lambda _dt: finish(meals=meals), 0)
            except Exception as exc:
                Logger.exception('WonderPlus public menu sync failed')
                Clock.schedule_once(lambda _dt, error=str(exc): finish(error=error), 0)
        Thread(target=worker, daemon=True).start()

    def _commit_cafeteria_sync(self, cafeteria_id, meals, remote_path='', provider_name='식당'):
        """Persist a completed network result on Kivy's UI/database thread.

        SQLite was opened when the app started on the main thread.  Network
        fetching happens on a worker thread, but touching that SQLite handle
        there makes Python reject the successful result.  Keep the expensive
        request off the UI while committing its plain-data result here.
        """
        try:
            if remote_path:
                self.store.update_cafeteria_path(cafeteria_id, remote_path)
            self.store.save_cafeteria_menu(cafeteria_id, meals)
            # A public-menu sync only changes Home; rebuilding hidden screens
            # here was visible as a pause on lower-end phones.
            self.refresh_home()
        except Exception as exc:
            Logger.exception('Cafeteria menu database commit failed')
            self._health_notice(f'{provider_name} 메뉴를 저장하지 못했어요', str(exc).strip()[:110] or '잠시 뒤 다시 시도해 주세요.')

    @staticmethod
    def _freshmeal_menu_text(payload):
        """Preserve every FreshMeal corner as a selectable, readable group."""
        data = payload.get('data') or {}
        meals = {}
        for feed_key, meal_key in (('1', 'breakfast'), ('2', 'lunch'), ('3', 'dinner')):
            options = data.get(feed_key) or []
            if not options:
                meals[meal_key] = ''
                continue
            # The service can publish several counters (더고메, 소담상,
            # 마이보글 등) for one meal.  Keep all of them rather than
            # flattening the response into one truncated line.
            groups = []
            for item in options:
                corner = str(item.get('corner') or '').strip()
                name = str(item.get('name') or '').strip()
                side = str(item.get('side') or '').strip()
                menu = ' · '.join(part for part in (name, side) if part)
                if menu:
                    groups.append({'title': corner or '오늘의 메뉴', 'menu': menu,
                                   'nutrition': item.get('_nutrition', {}), 'source_id': item.get('mealIdx'),
                                   'source_note': item.get('_nutrition_note', '프레시밀 공식 상세정보')})
            meals[meal_key] = json.dumps(groups, ensure_ascii=False) if groups else ''
        return meals

    @staticmethod
    def _fetch_public_text(url, accept='application/json, text/plain, */*', referer='', form=None):
        """Read a public feed using Android's TLS stack when running on a phone.

        Python's bundled SSL certificate list is not always present in a
        python-for-android build.  That can make a perfectly valid HTTPS
        endpoint fail only on the handset.  HttpURLConnection uses Android's
        maintained trust store, which is the appropriate transport for this
        public, read-only request.
        """
        try:
            from jnius import autoclass, cast
            JavaURL = autoclass('java.net.URL')
            BufferedReader = autoclass('java.io.BufferedReader')
            InputStreamReader = autoclass('java.io.InputStreamReader')
            connection = cast('java.net.HttpURLConnection', JavaURL(url).openConnection())
            connection.setConnectTimeout(15000)
            connection.setReadTimeout(15000)
            connection.setInstanceFollowRedirects(True)
            connection.setRequestProperty('Accept', accept)
            # InputStreamReader cannot decode a compressed response itself.
            # Ask the public source for plain UTF-8 so this behaves the same
            # on Samsung's Android transport and desktop previews.
            connection.setRequestProperty('Accept-Encoding', 'identity')
            connection.setRequestProperty('User-Agent', 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36')
            if referer:
                connection.setRequestProperty('Referer', referer)
            if form is not None:
                connection.setRequestMethod('POST')
                connection.setDoOutput(True)
                connection.setRequestProperty('Content-Type', 'application/x-www-form-urlencoded; charset=UTF-8')
                writer = autoclass('java.io.OutputStreamWriter')(connection.getOutputStream(), 'UTF-8')
                writer.write(urllib.parse.urlencode(form))
                writer.close()
            code = connection.getResponseCode()
            if code < 200 or code >= 300:
                raise RuntimeError(f'공개 메뉴 서버 응답 오류 ({code})')
            reader = BufferedReader(InputStreamReader(connection.getInputStream(), 'UTF-8'))
            chunks = []
            try:
                while True:
                    line = reader.readLine()
                    if line is None:
                        break
                    chunks.append(str(line))
            finally:
                reader.close()
                # URL.openConnection() is exposed to PyJNIus as the base
                # URLConnection type, which does not declare disconnect().
                # Closing the reader releases the socket; calling disconnect
                # here turned a successful response into a false failure.
            return '\n'.join(chunks)
        except ImportError:
            # Desktop preview uses the standard library; the phone follows the
            # Android branch above and does not depend on Python CA bundles.
            request = urllib.request.Request(url, data=urllib.parse.urlencode(form).encode('utf-8') if form is not None else None, headers={
                'Accept': accept,
                'User-Agent': 'Mozilla/5.0',
                **({'Referer': referer} if referer else {}),
            })
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.read().decode('utf-8')

    @classmethod
    def _fetch_public_json(cls, url, referer=''):
        return json.loads(cls._fetch_public_text(url, 'application/json, text/plain, */*', referer))

    def _sync_freshmeal_cafeteria(self, restaurant):
        """Fetch the official public menu feed; no sign-in data is accessed."""
        raw_path = str(restaurant.get('remote_path') or '')
        store_id = raw_path.split(':', 1)[1] if raw_path.startswith('freshmeal:') else ''
        if not store_id.isdigit():
            self._health_notice('프레시밀 식당 정보를 확인할 수 없어요', '식당 설정에서 세메스 식당을 다시 선택해 주세요.')
            return
        def worker():
            try:
                url = f'https://front.cjfreshmeal.co.kr/meal/v1/today-all-meal?storeIdx={urllib.parse.quote(store_id)}&mealDt={date.today():%Y%m%d}'
                payload = self._fetch_public_json(url)
                if payload.get('retCode') != '00':
                    raise RuntimeError(str(payload.get('retMsg') or '메뉴가 제공되지 않아요.'))
                for options in (payload.get('data') or {}).values():
                    for item in options:
                        try:
                            detail = self._fetch_public_json('https://front.cjfreshmeal.co.kr/meal/v1/meal-detail?mealIdx=' + str(int(item['mealIdx'])))
                            if detail.get('retCode') != '00': raise ValueError('상세 조회 실패')
                            data = detail['data']
                            if str(data.get('mealIdx')) != str(item['mealIdx']): raise ValueError('메뉴 불일치')
                            if data.get('mealDt','').replace('-','') != item.get('mealDt'):
                                raise ValueError('메뉴 날짜 불일치')
                            item['_nutrition'] = fresh_detail(data)
                        except Exception:
                            item['_nutrition'] = {}
                            item['_nutrition_note'] = '상세 영양정보를 불러오지 못했어요. 새로고침해 주세요.'
                meals = self._freshmeal_menu_text(payload)
                # CJ FreshMeal can have no feed on a given date.  Save that
                # empty state and render it inline instead of interrupting.
                Clock.schedule_once(lambda _dt, cafe_id=restaurant['id'], fetched=meals:
                                    self._commit_cafeteria_sync(cafe_id, fetched, provider_name='프레시밀'), 0)
            except Exception as exc:
                Logger.exception('FreshMeal public menu sync failed')
                message = str(exc).strip() or '네트워크 연결을 확인해 주세요.'
                Clock.schedule_once(lambda _dt: self._health_notice('프레시밀 메뉴를 불러오지 못했어요', message[:110]), 0)
        Thread(target=worker, daemon=True).start()

    def open_freshmeal_app(self):
        """Open the official FreshMeal client without accessing private data."""
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Intent = autoclass('android.content.Intent')
            Uri = autoclass('android.net.Uri')
            activity = PythonActivity.mActivity
            launch_intent = activity.getPackageManager().getLaunchIntentForPackage('com.cjfreshway.fs.freshmeal')
            if launch_intent:
                activity.startActivity(launch_intent)
                return
            # The official app is not installed yet.  Send the person to its
            # Play Store page rather than showing an unusable error dialog.
            intent = Intent(Intent.ACTION_VIEW, Uri.parse('market://details?id=com.cjfreshway.fs.freshmeal'))
            activity.startActivity(intent)
        except Exception:
            self._health_notice('프레시밀 앱을 열 수 없어요', 'Play 스토어에서 프레시밀을 설치한 뒤 세메스 사업장을 선택해 주세요.')

    @staticmethod
    def freshmeal_sites(keyword):
        normalized = re.sub(r'\s+', '', keyword).lower()
        if not normalized:
            return list(FRESHMEAL_SITES)
        matches = []
        for site in FRESHMEAL_SITES:
            terms = (site['name'], *site['aliases'])
            if any(normalized in re.sub(r'\s+', '', term).lower() or
                   re.sub(r'\s+', '', term).lower() in normalized for term in terms):
                matches.append(site)
        return matches

    def add_cafeteria_and_refresh(self, provider, name, remote_path, render_saved):
        try:
            restaurant = self.store.add_cafeteria(provider, name, remote_path)
            render_saved()
            self.refresh_all()
            if provider in ('welstory', 'freshmeal', PULMUONE_PROVIDER, WONDERPLUS_PROVIDER):
                self.sync_cafeteria(restaurant)
        except ValueError as exc:
            self._health_notice('식당을 추가하지 못했어요', str(exc))

    def popup_cafeterias(self):
        """Manage three cafeterias with public and account-scoped providers."""
        box = RoundedCard(orientation='vertical', spacing=dp(10), padding=dp(18), radius=dp(28),
                          background_color=[.035,.050,.085,.99], border_color=[.55,.90,.78,.20])
        header, dialog = self._dialog_header('내 식당 설정', '최대 3개까지 저장할 수 있어요. 대표 식당 메뉴는 홈에 표시됩니다.')
        box.add_widget(header)
        saved = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(6))
        saved.bind(minimum_height=saved.setter('height'))
        def render_saved():
            saved.clear_widgets()
            for item in self.store.cafeterias():
                row = RoundedCard(size_hint_y=None, height=dp(48), radius=dp(16), padding=(dp(11),dp(5)), background_color=[.07,.10,.13,.9], border_color=[.8,1,.92,.10])
                provider_label = PROVIDER_LABELS.get(item['provider'], '식당')
                row.add_widget(Label(text=f"{'대표 · ' if item['is_primary'] else ''}{item['name']}\n{provider_label}", font_name=self.font_name, font_size=dp(10), color=(.91,.97,.94,1), halign='left', valign='middle', text_size=(dp(165),dp(38)), shorten=True))
                primary = GlassButton(text='대표' if not item['is_primary'] else '표시 중', size_hint_x=None, width=dp(48), font_size=dp(8), glass_color=(.10,.29,.24,.9))
                primary.bind(on_release=lambda _button, cafe_id=item['id']: (self.store.set_primary_cafeteria(cafe_id), render_saved(), self.refresh_all()))
                remove = GlassButton(text='×', size_hint_x=None, width=dp(28), font_size=dp(16), glass_color=(.31,.13,.18,.9), color=(1,.75,.78,1))
                remove.bind(on_release=lambda _button, cafe_id=item['id']: (self.store.delete_cafeteria(cafe_id), render_saved(), self.refresh_all()))
                row.add_widget(primary); row.add_widget(remove); saved.add_widget(row)
        render_saved(); box.add_widget(saved)
        provider = {'value':'welstory'}
        providers = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(7))
        for code, text in (('welstory','삼성웰스토리'), ('freshmeal','CJ 프레시밀'), (WONDERPLUS_PROVIDER,'원더풀+')):
            chip = ToggleButton(text=text, group='cafeteria_provider', state='down' if code == provider['value'] else 'normal', font_name=self.font_name, font_size=dp(10), background_normal='', background_down='', background_color=(.15,.43,.35,.9) if code == provider['value'] else (.075,.095,.145,1), color=(1,1,1,1))
            def pick_provider(button, state, value=code):
                if state == 'down':
                    provider['value'] = value
                    for child in providers.children:
                        child.background_color = (.15,.43,.35,.9) if child is button else (.075,.095,.145,1)
                    query.hint_text = (
                        '세메스 등 프레시밀 사업장을 검색하세요' if value == 'freshmeal' else
                        '원더풀 플러스 사업장을 검색하세요' if value == WONDERPLUS_PROVIDER else
                        '웰스토리 식당명을 검색하세요')
            chip.bind(state=pick_provider)
            providers.add_widget(chip)
        box.add_widget(providers)
        query = GlassInput(hint_text='웰스토리 식당명을 검색하세요', multiline=False, font_name=self.font_name, size_hint_y=None, height=dp(42), padding=[dp(12),dp(11)])
        box.add_widget(query)
        results = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(5))
        results.bind(minimum_height=results.setter('height'))
        from kivy.uix.scrollview import ScrollView
        result_scroll = ScrollView(do_scroll_x=False, bar_width=dp(2)); result_scroll.add_widget(results); box.add_widget(result_scroll)
        popup = Popup(title='', content=box, size_hint=(.92,.88), background='', background_color=(0,0,0,0), overlay_color=(0,0,0,.66))
        dialog['popup'] = popup
        def search(_button=None):
            keyword = query.text.strip()
            if provider['value'] == 'freshmeal':
                results.clear_widgets()
                results.add_widget(Label(
                    text='프레시밀의 공개 오늘 메뉴를 홈에 바로 불러와요.\n개인 계정 정보는 저장하지 않습니다.',
                    font_name=self.font_name, font_size=dp(10), color=(.67,.76,.84,1),
                    halign='center', valign='middle', text_size=(dp(280), dp(52)),
                    size_hint_y=None, height=dp(52)))
                sites = self.freshmeal_sites(keyword)
                if not sites:
                    results.add_widget(Label(text='등록된 프레시밀 사업장을 찾지 못했어요.\n“세메스”로 다시 검색해 보세요.', font_name=self.font_name,
                                             font_size=dp(10), color=(1,.70,.70,1), halign='center',
                                             valign='middle', text_size=(dp(280), dp(52)), size_hint_y=None, height=dp(52)))
                for site in sites:
                    add = GlassButton(text=f"{site['name']}\n{site['address']}", size_hint_y=None, height=dp(56),
                                      font_name=self.font_name, font_size=dp(10), glass_color=(.09,.18,.17,.96))
                    add.bind(on_release=lambda _b, s=site: self.add_cafeteria_and_refresh(
                        'freshmeal', s['name'], f"freshmeal:{s['store_id']}", render_saved))
                    results.add_widget(add)
                return
            if provider['value'] == WONDERPLUS_PROVIDER:
                results.clear_widgets()
                results.add_widget(Label(
                    text='원더풀 플러스의 공개 식단을 홈에 불러와요.\n동탄은 키친 K1~K4의 메뉴를 표시합니다.',
                    font_name=self.font_name, font_size=dp(10), color=(.67,.76,.84,1),
                    halign='center', valign='middle', text_size=(dp(280), dp(52)),
                    size_hint_y=None, height=dp(52)))
                sites = self.wonderplus_sites(keyword)
                if not sites:
                    results.add_widget(Label(text='등록된 사업장을 찾지 못했어요.\n“삼성SDI 동탄”으로 검색해 보세요.', font_name=self.font_name,
                                             font_size=dp(10), color=(1,.70,.70,1), halign='center',
                                             valign='middle', text_size=(dp(280), dp(52)), size_hint_y=None, height=dp(52)))
                for site in sites:
                    add = GlassButton(text=f"{site['name']}\n{site['address']}", size_hint_y=None, height=dp(56),
                                      font_name=self.font_name, font_size=dp(10), glass_color=(.09,.18,.17,.96))
                    add.bind(on_release=lambda _b, s=site: self.add_cafeteria_and_refresh(
                        WONDERPLUS_PROVIDER, s['name'], f"wonderplus:{s['key']}", render_saved))
                    results.add_widget(add)
                return
            if not keyword: return
            selected_provider = provider['value']
            results.clear_widgets(); results.add_widget(Label(text='식당을 찾는 중…', font_name=self.font_name, size_hint_y=None, height=dp(44), color=(.65,.78,.78,1)))
            def worker():
                try:
                    url = 'https://welplan.pmh.codes/proxy/search?q=' + urllib.parse.quote(keyword)
                    found = self._fetch_public_json(url, 'https://welplan.pmh.codes/')
                    def draw(_dt):
                        results.clear_widgets()
                        if not found:
                            message = '일치하는 식당을 찾지 못했어요. 검색어를 확인해 주세요.'
                            results.add_widget(Label(text=message, font_name=self.font_name,
                                                     font_size=dp(10), color=(1,.72,.72,1),
                                                     halign='center', valign='middle',
                                                     text_size=(dp(280), dp(54)),
                                                     size_hint_y=None, height=dp(54)))
                            return
                        for item in found[:12]:
                            name = item.get('name','이름 없는 식당')
                            vendor = item.get('vendor','welstory')
                            restaurant_id = item.get('id','')
                            # The public search response's "path" is an array
                            # of category names, not a URL.  Build the documented
                            # date-menu endpoint from vendor, id, and name.
                            slug = urllib.parse.quote(name.strip().lower().replace(' ', '-'), safe='-')
                            path = f'/restaurants/{vendor}/{restaurant_id}/{slug}'
                            add = GlassButton(text=name, size_hint_y=None, height=dp(44), font_name=self.font_name, font_size=dp(11), glass_color=(.09,.16,.19,.9))
                            add.bind(on_release=lambda _b, n=name, p=path, provider_code=selected_provider: self.add_cafeteria_and_refresh(provider_code, n, p, render_saved))
                            results.add_widget(add)
                    Clock.schedule_once(draw, 0)
                except Exception:
                    Clock.schedule_once(lambda _dt: (results.clear_widgets(), results.add_widget(Label(text='지점을 찾지 못했어요. 잠시 뒤 다시 시도해 주세요.', font_name=self.font_name, color=(1,.65,.65,1), size_hint_y=None, height=dp(50)))), 0)
            Thread(target=worker, daemon=True).start()
        search_button = GlassButton(text='지점 검색', size_hint_y=None, height=dp(44), glass_color=(.15,.43,.35,.92), font_size=dp(11))
        search_button.bind(on_release=search)
        box.add_widget(search_button)
        popup.open()

    def popup_workout(self):
        fields=self.form_popup('운동 직접 기록',[('운동 이름','근력 운동'),('운동 시간 (분)','40'),('소모 칼로리','260')])
        popup=fields['popup']
        def save(_):
            try:
                title = fields['inputs'][0].text or '운동'
                minutes, calories = int(fields['inputs'][1].text), int(fields['inputs'][2].text)
                self.store.add_workout(title, minutes, calories)
                self.write_health_workout(title, minutes)
                popup.dismiss(); self.refresh_all()
            except ValueError: fields['error'].text='시간과 칼로리는 숫자로 입력해 주세요.'
        fields['save'].bind(on_release=save);popup.open()

    def _dialog_header(self, title, subtitle=''):
        """Common, closeable glass-dialog heading used by every popup."""
        holder = {'popup': None}
        header = BoxLayout(size_hint_y=None, height=dp(64), spacing=dp(10))
        words = BoxLayout(orientation='vertical', spacing=dp(1))
        words.add_widget(Label(text=title, font_name=self.font_name, font_size=dp(18), bold=True,
                               color=(.97,.98,1,1), halign='left', valign='bottom', text_size=(dp(235), dp(30))))
        words.add_widget(Label(text=subtitle, font_name=self.font_name, font_size=dp(10),
                               color=(.62,.70,.83,1), halign='left', valign='top', text_size=(dp(235), dp(17))))
        for label in words.children:
            label.bind(size=lambda w,v: setattr(w, 'text_size', v))
            label.shorten = False
            label.valign = 'middle'
        close = GlassButton(text='×', size_hint_x=None, width=dp(34), font_size=dp(19),
                            glass_color=(.16,.19,.25,.62), color=(.90,.94,1,1))
        close.size_hint_y = None
        close.height = dp(34)
        close.pos_hint = {'center_y': .5}
        close.bind(on_release=lambda _button: holder['popup'].dismiss() if holder.get('popup') else None)
        header.add_widget(words); header.add_widget(close)
        return header, holder

    def popup_manual_meal(self, meal_type):
        """Pick foods for just today, or carry the same choice into a saved set."""
        box = RoundedCard(orientation='vertical', spacing=dp(9), padding=dp(18), radius=dp(28),
                          background_color=[.035,.050,.085,.94], border_color=[.72,.82,1,.18])
        header, dialog = self._dialog_header(f'{self.meal_names[meal_type]} 직접 선택',
                                             '오늘만 적용하거나, 같은 구성으로 세트를 만들 수 있어요.')
        box.add_widget(header)
        # A meal can contain two identical portions.  Keep tap order and
        # duplicates rather than collapsing selections into a set.
        selected = []
        food_lookup = {food['id']: food for food in self.store.foods()}
        selected_label = Label(font_name=self.font_name, size_hint_y=None, height=dp(44),
                               font_size=dp(10), color=(.78,.88,1,1), halign='left', valign='middle',
                               text_size=(dp(274), dp(44)), shorten=True)
        box.add_widget(selected_label)
        search_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(7))
        search = GlassInput(hint_text='음식명 또는 카테고리 검색', multiline=False, font_name=self.font_name,
                            size_hint_y=None, height=dp(44), padding=[dp(13),dp(12)])
        add_food = GlassButton(text='+ 추가', font_name=self.font_name, size_hint_x=None, width=dp(58),
                               font_size=dp(10), glass_color=(.12,.29,.29,.88), color=(.76,1,.89,1))
        search_row.add_widget(search); search_row.add_widget(add_food); box.add_widget(search_row)
        results = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(6))
        results.bind(minimum_height=results.setter('height'))
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(2), effect_cls=ScrollEffect,
                            scroll_distance=dp(6), scroll_timeout=60)
        scroll.add_widget(results); box.add_widget(scroll)
        error = Label(text='', font_name=self.font_name, size_hint_y=None, height=dp(18),
                      font_size=dp(10), color=(1,.62,.66,1), halign='center', text_size=(dp(274),dp(18)))
        box.add_widget(error)
        actions = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        choose_today = GlassButton(text='선택', font_size=dp(11), glass_color=(.15,.26,.44,.82), color=(.90,.95,1,1))
        save_set = GlassButton(text='세트로 저장', font_size=dp(11), glass_color=(.22,.40,.78,.84), color=(1,1,1,1))
        actions.add_widget(choose_today); actions.add_widget(save_set); box.add_widget(actions)
        popup = Popup(title='', content=box, size_hint=(.90,.82), background='', background_color=(0,0,0,0), separator_color=(0,0,0,0), overlay_color=(0,0,0,.66))
        dialog['popup'] = popup
        def render_selected():
            foods = [food_lookup[i] for i in selected if i in food_lookup]
            selected_label.text = ('선택한 음식이 없어요. 아래에서 추가해 주세요.' if not foods else
                                   self.store.compact_food_names(foods) + f'  ·  {round(sum(food["calories"] for food in foods))} kcal')
        def render_foods(query=''):
            results.clear_widgets()
            foods = self.store.foods(query)
            # The initial list is intentionally capped for speed.  Keep every
            # searched item in the lookup as well, otherwise a selected result
            # outside the first page cannot be rendered in the selection line.
            food_lookup.update({food['id']: food for food in foods})
            if not foods:
                results.add_widget(Label(text='찾는 음식이 없어요', font_name=self.font_name, size_hint_y=None, height=dp(54), color=(.62,.70,.83,1)))
                return
            for food in foods:
                amount = selected.count(food['id'])
                item = GlassButton(text=f"{'✓ ' + str(amount) + '개  ' if amount else '+  '}{food['name']}  ·  {food['calories']} kcal\n{food['category']} · 단백질 {food['protein']}g · {food['serving']}",
                                   size_hint_y=None, height=dp(54), font_size=dp(10), halign='left',
                                   glass_color=(.20,.38,.70,.82) if amount else (.10,.14,.21,.64),
                                   color=(.94,.97,1,1))
                def add_portion(_button, food_id=food['id']):
                    selected.append(food_id)
                    render_selected(); render_foods(search.text)
                item.bind(on_release=add_portion); results.add_widget(item)
        def apply_today(_button):
            try:
                saved = self.store.select_manual_meal(meal_type, selected)
                popup.dismiss(); self.refresh_all()
            except ValueError as exc:
                error.text = str(exc)
        def create_set(_button):
            if not selected:
                error.text = '세트에 넣을 음식을 한 가지 이상 골라 주세요.'
                return
            saved = self.store.select_manual_meal(meal_type, selected)
            popup.dismiss(); self.refresh_all()
            self.popup_meal_set(preset_food_ids=selected, preferred_kind=meal_type)
        choose_today.bind(on_release=apply_today); save_set.bind(on_release=create_set)
        search_event = {'value': None}
        def queue_search(_input, value):
            if search_event['value']:
                search_event['value'].cancel()
            search_event['value'] = Clock.schedule_once(lambda _dt: render_foods(value), .12)
        search.bind(text=queue_search)
        add_food.bind(on_release=lambda _button: self.popup_add_food(lambda: (food_lookup.update({f['id']: f for f in self.store.foods()}), render_foods(search.text))))
        render_selected(); render_foods(); popup.open()

    def popup_meal_set(self, existing=None, preset_food_ids=None, preferred_kind=None):
        """Polished searchable meal-set composer backed by the food library."""
        box = RoundedCard(orientation='vertical', spacing=dp(10), padding=dp(18), radius=dp(28),
                          background_color=[.035,.050,.085,.985], border_color=[.72,.82,1,.17])
        header, dialog = self._dialog_header('식단 세트 만들기' if not existing else '식단 세트 편집',
                                             '식사 시간과 음식을 골라 나만의 루틴으로 저장하세요.')
        box.add_widget(header)
        title = GlassInput(text=existing['title'] if existing else '', hint_text='세트 이름  예: 아침 1', multiline=False,
                           font_name=self.font_name, font_size=dp(14), size_hint_y=None, height=dp(48), padding=[dp(14), dp(13)])
        box.add_widget(title)
        selected_kind = {'value': existing['meal_type'] if existing else (preferred_kind or 'breakfast')}
        kinds = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(7))
        for key in ('breakfast','lunch','dinner'):
            chip = ToggleButton(text=self.meal_names[key], group='meal_kind', state='down' if key == selected_kind['value'] else 'normal',
                                font_name=self.font_name, font_size=dp(11), background_normal='', background_down='',
                                background_color=(.27,.45,.86,.92) if key == selected_kind['value'] else (.08,.11,.17,1),
                                color=(1,1,1,1))
            def update_kind(button, state, value=key):
                if state == 'down':
                    selected_kind['value'] = value
                    for child in kinds.children:
                        child.background_color = (.27,.45,.86,.92) if child is button else (.08,.11,.17,1)
            chip.bind(state=update_kind)
            kinds.add_widget(chip)
        box.add_widget(kinds)
        library_head = BoxLayout(size_hint_y=None, height=dp(26))
        library_head.add_widget(Label(text='선택한 음식', font_name=self.font_name, font_size=dp(13), bold=True, color=(.93,.96,1,1), halign='left', text_size=(dp(210), None)))
        library_head.add_widget(Label(text='타일의 ×를 눌러 취소', font_name=self.font_name, font_size=dp(10), color=(.56,.70,1,1), halign='right', text_size=(dp(120), None)))
        for label in library_head.children:
            label.bind(size=lambda w,v: setattr(w,'text_size',v))
        box.add_widget(library_head)
        selected_summary = Label(text='', font_name=self.font_name, size_hint_y=None, height=dp(22),
                                 font_size=dp(10), color=(.60,.90,.80,1), halign='left', valign='middle',
                                 text_size=(dp(296), dp(22)), shorten=True)
        box.add_widget(selected_summary)
        from kivy.uix.scrollview import ScrollView
        selected_tiles = BoxLayout(orientation='horizontal', size_hint_x=None, size_hint_y=None, height=dp(50), spacing=dp(7))
        selected_tiles.bind(minimum_width=selected_tiles.setter('width'))
        selected_scroll = ScrollView(size_hint_y=None, height=dp(54), do_scroll_y=False, do_scroll_x=True, bar_width=0)
        selected_scroll.add_widget(selected_tiles)
        box.add_widget(selected_scroll)
        search_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(7))
        search = GlassInput(hint_text='음식명 또는 카테고리 검색', multiline=False, font_name=self.font_name,
                            font_size=dp(13), size_hint_y=None, height=dp(44), padding=[dp(14), dp(12)])
        add_food = GlassButton(text='+ 음식 추가', font_name=self.font_name, size_hint_x=None, width=dp(82),
                               font_size=dp(10), glass_color=(.12,.29,.29,.88), color=(.76,1,.89,1))
        search_row.add_widget(search); search_row.add_widget(add_food); box.add_widget(search_row)
        # A set may deliberately include two portions of the same food.  A
        # list preserves that count while the old set silently lost it.
        selected = [food['id'] for food in existing['foods']] if existing else list(preset_food_ids or [])
        food_lookup = {food['id']: food for food in self.store.foods()}
        list_box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(6))
        list_box.bind(minimum_height=list_box.setter('height'))
        def render_selected():
            selected_tiles.clear_widgets()
            if not selected:
                selected_summary.text = '선택한 음식이 없어요.'
                selected_tiles.add_widget(Label(text='아직 선택한 음식이 없어요', font_name=self.font_name, font_size=dp(10),
                                                color=(.50,.59,.74,1), size_hint_x=None, width=dp(160),
                                                halign='left', valign='middle', text_size=(dp(160), dp(50))))
                return
            picked = [food_lookup[item] for item in selected if item in food_lookup]
            selected_summary.text = self.store.compact_food_names(picked)
            ordered_ids = []
            for food_id in selected:
                if food_id not in ordered_ids:
                    ordered_ids.append(food_id)
            for food_id in ordered_ids:
                food = food_lookup.get(food_id)
                if not food:
                    continue
                count = selected.count(food_id)
                tile = RoundedCard(orientation='horizontal', size_hint_x=None, width=dp(142), size_hint_y=None,
                                   height=dp(48), radius=dp(16), padding=(dp(11), dp(5)),
                                   background_color=[.105,.17,.30,.92], border_color=[.55,.71,1,.22])
                tile.add_widget(Label(text=f"{food['name']}{' × ' + str(count) if count > 1 else ''}\n{food['calories']} kcal · {food['serving']}", font_name=self.font_name,
                                      font_size=dp(9), color=(.94,.97,1,1), halign='left', valign='middle',
                                      text_size=(dp(98), dp(38)), shorten=True))
                remove = GlassButton(text='×', font_name=self.font_name, size_hint=(None, None), size=(dp(23), dp(23)),
                                     font_size=dp(15), glass_color=(.36,.16,.23,.92), color=(1,.78,.82,1))
                def unselect(_button, value=food_id):
                    # Remove one portion at a time so duplicate counts remain
                    # explicit and reversible.
                    selected.remove(value)
                    render_selected()
                    render_foods(search.text)
                remove.bind(on_release=unselect)
                tile.add_widget(remove)
                selected_tiles.add_widget(tile)
        def render_foods(query=''):
            list_box.clear_widgets()
            foods = self.store.foods(query)
            if not foods:
                list_box.add_widget(Label(text='찾는 음식이 없어요', font_name=self.font_name, color=(.57,.66,.81,1), size_hint_y=None, height=dp(60)))
                return
            for food in foods:
                amount = selected.count(food['id'])
                button = GlassButton(text=f"{'✓ ' + str(amount) + '개  ' if amount else '+  '}{food['name']}\n{food['category']}  ·  {food['calories']} kcal  ·  단백질 {food['protein']}g  ·  {food['serving']}",
                                     font_name=self.font_name, font_size=dp(12), halign='left', valign='middle', text_size=(dp(250), dp(48)),
                                     glass_color=(.15,.50,.42,.84) if amount else (.060,.075,.115,.96),
                                     color=(.96,.98,1,1), size_hint_y=None, height=dp(70), padding=[dp(12), dp(5)])
                button.bind(size=lambda w,v: setattr(w,'text_size',(max(dp(40),v[0]-dp(24)),v[1]-dp(10))))
                def add_food_portion(_button, food_id=food['id']):
                    selected.append(food_id)
                    render_selected()
                    render_foods(search.text)
                button.bind(on_release=add_food_portion)
                list_box.add_widget(button)
        render_selected()
        render_foods()
        search_event = {'value': None}
        def queue_search(_input, value):
            if search_event['value']:
                search_event['value'].cancel()
            search_event['value'] = Clock.schedule_once(lambda _dt: render_foods(value), .12)
        search.bind(text=queue_search)
        add_food.bind(on_release=lambda _button: self.popup_add_food(lambda: (food_lookup.update({f['id']: f for f in self.store.foods()}), render_foods(search.text))))
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3)); scroll.add_widget(list_box); box.add_widget(scroll)
        save = GlassButton(text='선택한 음식으로 세트 저장', size_hint_y=None, height=dp(50), font_size=dp(12), glass_color=(.25,.43,.88,.94))
        box.add_widget(save)
        popup = Popup(title='', content=box, size_hint=(.92,.90),
                      background='', background_color=(0,0,0,0), separator_color=(0,0,0,0), overlay_color=(0,0,0,.66))
        dialog['popup'] = popup
        def commit(_):
            try:
                self.store.save_set(title.text, selected_kind['value'], selected, existing['id'] if existing else None)
                popup.dismiss(); self.refresh_all()
            except ValueError:
                title.hint_text = '이름과 최소 한 가지 음식을 선택하세요'
        save.bind(on_release=commit)
        popup.open()

    def popup_add_food(self, on_saved=None):
        """Let people add their own packaged food or recipe to the library."""
        fields = self.form_popup('라이브러리에 음식 추가', [
            ('음식 이름', '예: 내가 먹는 단백질 음료'), ('카테고리', '간편식 · 직접 추가'),
            ('열량 (kcal)', ''), ('단백질 (g)', ''), ('탄수화물 (g)', ''), ('지방 (g)', ''), ('1회 제공량', '예: 250ml'),
        ])
        popup = fields['popup']
        # The lookup lives beside the first field's title, not at the bottom
        # of the form. It uses the Render proxy, so the Food Safety Korea key
        # is never present on a person's device.
        lookup = GlassButton(text='검색', font_name=self.font_name, size_hint=(None, None),
                             size=(dp(52), dp(22)), font_size=dp(10),
                             glass_color=(.10,.40,.36,.92), color=(.78,1,.90,1))
        name_label = fields['labels'][0]
        label_index = fields['box'].children.index(name_label)
        fields['box'].remove_widget(name_label)
        name_header = BoxLayout(size_hint_y=None, height=dp(22))
        name_header.add_widget(name_label)
        name_header.add_widget(lookup)
        fields['box'].add_widget(name_header, index=label_index)
        # Keep the lookup guidance next to the field it describes, instead
        # of leaving it at the very bottom of a long manual-entry form.
        fields['box'].remove_widget(fields['error'])
        first_input_index = fields['box'].children.index(fields['inputs'][0])
        fields['error'].text = '음식 이름을 입력한 뒤 검색을 누르면 영양정보를 채울 수 있어요.'
        fields['error'].color = (.62,.78,1,1)
        fields['error'].height = dp(22)
        fields['box'].add_widget(fields['error'], index=first_input_index + 1)

        def fill_from_search(_button):
            try:
                query = fields['inputs'][0].text.strip()
                if not query:
                    raise ValueError('먼저 음식 이름을 입력해 주세요.')
                lookup.disabled = True
                fields['error'].color = (.62,.78,1,1)
                fields['error'].text = '식약처 영양정보를 검색 중이에요…'
            except Exception as exc:
                fields['error'].color = (1,.55,.58,1)
                fields['error'].text = str(exc)[:80]
                return

            def worker():
                try:
                    url = NUTRITION_SEARCH_URL + '?' + urllib.parse.urlencode({'q': query})
                    payload = self._fetch_public_json(url, SERVICE_BASE_URL + '/')
                    items = payload.get('items') if isinstance(payload, dict) else []
                    if not isinstance(items, list) or not items:
                        raise ValueError((payload.get('error') if isinstance(payload, dict) else '') or '일치하는 식품을 찾지 못했어요.')
                    normalized = re.sub(r'\s+', '', query).casefold()
                    exact = next((item for item in items if re.sub(r'\s+', '', str(item.get('name') or '')).casefold() == normalized), None)
                    if exact:
                        Clock.schedule_once(lambda _dt, found=dict(exact): fill_fields(found), 0)
                    elif len(items) == 1:
                        Clock.schedule_once(lambda _dt, found=dict(items[0]): fill_fields(found), 0)
                    else:
                        Clock.schedule_once(lambda _dt, choices=[dict(item) for item in items]: self.popup_nutrition_choices(choices, fill_fields, lookup), 0)
                except Exception as exc:
                    Clock.schedule_once(lambda _dt, message=str(exc): show_lookup_error(message), 0)

            def fill_fields(food):
                lookup.disabled = False
                fields['inputs'][0].text = str(food.get('name') or query)
                fields['inputs'][1].text = str(food.get('category') or '')
                for index, key in ((2, 'calories'), (3, 'protein'), (4, 'carbs'), (5, 'fat')):
                    value = food.get(key)
                    fields['inputs'][index].text = f'{float(value):g}' if value not in (None, '') else ''
                fields['inputs'][6].text = str(food.get('serving') or '')
                fields['error'].color = (.62,1,.82,1)
                fields['error'].text = '식약처 영양정보를 입력했어요. 제품 라벨과 한 번 더 확인해 주세요.'

            def show_lookup_error(message):
                lookup.disabled = False
                # Network/API failures are surfaced inside the open dialog;
                # they must never propagate from a worker to Android.
                fields['error'].color = (1,.55,.58,1)
                fields['error'].text = (message or '영양정보를 불러오지 못했어요.')[:100]

            Thread(target=worker, daemon=True).start()

        lookup.bind(on_release=fill_from_search)
        def save(_button):
            try:
                self.store.add_food(fields['inputs'][0].text, fields['inputs'][1].text,
                                    fields['inputs'][2].text, fields['inputs'][3].text,
                                    fields['inputs'][4].text, fields['inputs'][5].text,
                                    fields['inputs'][6].text)
                popup.dismiss()
                if on_saved: on_saved()
            except (ValueError, sqlite3.IntegrityError) as exc:
                fields['error'].text = '이미 있는 이름이거나 영양정보가 올바르지 않아요.' if isinstance(exc, sqlite3.IntegrityError) else str(exc)
        fields['save'].bind(on_release=save)
        popup.open()

    def popup_nutrition_choices(self, items, on_choose, lookup_button=None):
        """Let a person select among multiple 식약처 matches vertically."""
        box = RoundedCard(orientation='vertical', padding=dp(18), spacing=dp(9), radius=dp(24),
                          background_color=[.045,.06,.092,.99], border_color=[.72,.84,1,.22])
        header, dialog = self._dialog_header('검색 결과', '일치하는 식품을 선택하면 영양정보를 입력합니다.')
        box.add_widget(header)
        list_box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(7))
        list_box.bind(minimum_height=list_box.setter('height'))
        popup = Popup(title='', content=box, size_hint=(.90,.76), background='', background_color=(0,0,0,0), overlay_color=(0,0,0,.66))
        dialog['popup'] = popup
        for item in items[:20]:
            name = str(item.get('name') or '이름 미제공')
            maker = str(item.get('manufacturer') or item.get('category') or '')
            calories = item.get('calories')
            detail = f"{maker}  ·  {'열량 미제공' if calories in (None, '') else f'{float(calories):g} kcal'}"
            choice = GlassButton(text=f'{name}\n{detail}', font_name=self.font_name, font_size=dp(11),
                                 halign='left', valign='middle', text_size=(dp(280), dp(46)),
                                 glass_color=(.075,.11,.18,.94), color=(.93,.97,1,1), size_hint_y=None, height=dp(62), padding=[dp(12),dp(6)])
            choice.bind(size=lambda widget, size: setattr(widget, 'text_size', (max(dp(40), size[0]-dp(24)), size[1]-dp(10))))
            def choose(_button, found=dict(item)):
                popup.dismiss()
                on_choose(found)
            choice.bind(on_release=choose)
            list_box.add_widget(choice)
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3)); scroll.add_widget(list_box)
        box.add_widget(scroll)
        popup.bind(on_dismiss=lambda *_args: setattr(lookup_button, 'disabled', False) if lookup_button is not None else None)
        popup.open()

    def popup_body(self):
        """Create an explicitly editable body-information form.

        The previous dialog rendered example numbers only as hint text.  On
        Android that made the values look saved while there was nothing useful
        to edit or update.  Load the current values into real TextInput text
        fields instead, then upsert them when the user presses save.
        """
        current = self.store.body()[0] if self.store.body() else {}
        profile = self.store.profile()
        fields = self.form_popup('신체 정보 추가', [
            ('체중 (kg)', ''), ('체지방률 (%)', ''), ('골격근량 (kg)', ''),
            ('키 (cm)', ''), ('기초대사량 (kcal)', ''),
        ])
        defaults = (
            current.get('weight'), current.get('fat'), current.get('muscle'),
            profile.get('height_cm'), profile.get('basal_kcal'),
        )
        for item, value in zip(fields['inputs'], defaults):
            # Leave empty fields truly empty.  Example numerals were rendered
            # like saved values on Android and were misleading.
            item.text = f'{float(value):g}' if value is not None else ''
            item.hint_text = ''
            item.input_filter = 'float'
            item.foreground_color = (1, 1, 1, 1)
            item.disabled = False
        popup=fields['popup']
        def save(_):
            try:
                self.store.add_body(*[float(x.text) for x in fields['inputs'][:3]])
                self.store.conn.execute('UPDATE profile SET height_cm=?, basal_kcal=? WHERE id=1',
                                        (float(fields['inputs'][3].text), float(fields['inputs'][4].text)))
                self.store.conn.commit(); popup.dismiss(); self.refresh_all()
            except ValueError: fields['error'].text='모든 항목을 숫자로 입력해 주세요.'
        fields['save'].bind(on_release=save);popup.open()

    def popup_profile(self):
        profile = self.store.profile()
        age = None
        try:
            born = datetime.strptime(profile.get('birthday') or '', '%Y-%m-%d').date()
            age = date.today().year - born.year - ((date.today().month, date.today().day) < (born.month, born.day))
        except ValueError: pass
        weight = float(self.store.body()[0].get('weight') or 0)
        protein_hint = max(45, round(weight * .8)) if weight else 50
        age_text = f'{age}세 권장' if age is not None and age >= 0 else '성인 권장'
        guidance = Label(text='', font_name=self.font_name, size_hint_y=None, height=dp(38),
                         font_size=dp(10), color=(.72,.86,1,1), halign='left', valign='middle')
        guidance.bind(size=lambda widget, size: setattr(widget, 'text_size', size))
        fields = self.form_popup('내 정보 · 하루 목표', [
            # Profile fields intentionally have no hint text. A hint is muted
            # by design and had been confused with a saved value on Android.
            ('이름', ''),
            ('생년월일', ''),
            ('__widget__', guidance),
            (f'목표 칼로리 (kcal)  ·  {age_text}: 1,800 kcal', ''),
            (f'목표 단백질 (g)  ·  {age_text}: {protein_hint}g 이상', ''),
            (f'목표 탄수화물 (g)  ·  {age_text}: 130g 이상', ''),
            ('목표 걸음수 (걸음)', ''),
            ('운동 목표 소모 칼로리 (kcal)', ''),
        ])
        fields['inputs'][0].text = profile.get('name') or ''
        fields['inputs'][1].text = profile.get('birthday') or ''
        fields['inputs'][0].hint_text = ''
        fields['inputs'][1].hint_text = ''
        # Values must be real TextInput values, not grey hint text.  This makes
        # the current target visible and guarantees each field is editable on
        # Android's soft keyboard.
        for index, value, hint in (
            (2, profile.get('target_calories') or 1800, '예: 1800'),
            (3, profile.get('target_protein') or 100, '예: 100'),
            (4, profile.get('target_carbs') or 220, '예: 220'),
            (5, profile.get('target_steps') or 6300, '예: 6300'),
            (6, profile.get('target_exercise_calories') or 300, '예: 300'),
        ):
            item = fields['inputs'][index]
            item.text = f'{float(value):g}'
            # Never mirror the current value as a hint: hint text is muted by
            # design, while a stored goal must be clearly readable in white.
            item.hint_text = ''
            item.input_filter = 'float'
            item.foreground_color = (1, 1, 1, 1)
            item.disabled_foreground_color = (1, 1, 1, 1)
            item.cursor_color = (.78, .88, 1, 1)
            item.disabled = False
        popup = fields['popup']
        synced_body = Label(text='', font_name=self.font_name, size_hint_y=None, height=dp(52),
                            font_size=dp(11), color=(.88,.94,1,1), halign='left', valign='middle')
        synced_body.bind(size=lambda widget, size: setattr(widget, 'text_size', size))
        def show_synced_body():
            current = self.store.body()[0] if self.store.body() else {}
            weight_text = '미기록' if not current.get('weight') else f"{current['weight']:.1f} kg"
            fat_text = '미기록' if current.get('fat') is None or not current.get('fat') else f"{current['fat']:.1f}%"
            muscle_text = '미기록' if current.get('muscle') is None or not current.get('muscle') else f"{current['muscle']:.1f} kg"
            source = 'Health Connect 동기화 값' if current.get('source') == 'health_connect' else '최근 저장 값'
            synced_body.text = f'[b]신체 정보[/b]  ·  {source}\n체중 {weight_text}   체지방률 {fat_text}   골격근량 {muscle_text}'
            synced_body.markup = True
        show_synced_body()
        birthday_input = fields['inputs'][1]
        birthday_input.input_filter = 'int'
        def birthday_digits(value):
            return re.sub(r'\D', '', value)[:8]

        def canonical_birthday(value):
            digits = birthday_digits(value)
            return f'{digits[:4]}-{digits[4:6]}-{digits[6:8]}' if len(digits) == 8 else value.strip()

        def recommended(_widget=None, value=None):
            try:
                # Work from raw digits as they are typed. This updates at the
                # eighth digit without rewriting the focused input or moving
                # Android's caret.
                born = datetime.strptime(birthday_digits(fields['inputs'][1].text), '%Y%m%d').date()
                today = date.today(); age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
                # Adult baseline ranges: protein 0.8 g/kg and carbohydrate
                # 130 g/day; present these as guidance, not a prescription.
                body = self.store.body()[0]
                weight = float(body.get('weight') or 0)
                protein_goal = max(45, round(weight * .8)) if weight else 50
                carbs_goal = 130
                if age >= 0:
                    guidance.text = (f'{age}세 권장 기준  ·  단백질 {protein_goal}g 이상  ·  탄수화물 {carbs_goal}g 이상\n'
                                     '개인 질환·운동량에 따라 목표는 달라질 수 있어요.')
                    fields['labels'][2].text = f'목표 칼로리 (kcal)  ·  {age}세 권장: 1,800 kcal'
                    fields['labels'][3].text = f'목표 단백질 (g)  ·  {age}세 권장: {protein_goal}g 이상'
                    fields['labels'][4].text = f'목표 탄수화물 (g)  ·  {age}세 권장: {carbs_goal}g 이상'
                else:
                    guidance.text = '올바른 생년월일을 입력해 주세요.'
            except ValueError:
                guidance.text = '생년월일 8자리를 입력하면 연령 기준 권장량을 바로 보여드려요.'
        def finish_birthday(_widget, focused):
            # Formatting only after editing is complete prevents the cursor
            # jump that previously reordered dates such as 19930430.
            if not focused:
                birthday_input.text = canonical_birthday(birthday_input.text)
        birthday_input.bind(text=recommended, focus=finish_birthday)
        recommended()
        fields['box'].remove_widget(fields['save'])
        connect = GlassButton(text='Health Connect 권한 설정', font_name=self.font_name, size_hint_y=None,
                              height=dp(42), glass_color=(.10,.17,.30,.84), color=(.76,.85,1,1))
        connect.bind(on_release=lambda _button: self.open_health_connect())
        sync_now = GlassButton(text='Health Connect에서 신체 정보 가져오기', font_name=self.font_name,
                               size_hint_y=None, height=dp(44), glass_color=(.12,.39,.40,.96), color=(.82,1,.93,1))
        def sync_profile(_button):
            fields['error'].color = (.66,.86,1,1)
            fields['error'].text = 'Health Connect 데이터를 불러오는 중이에요…'
            self.sync_health(after=lambda success: self._refresh_profile_sync_result(fields, show_synced_body, success))
        sync_now.bind(on_release=sync_profile)
        fields['box'].add_widget(connect)
        fields['box'].add_widget(sync_now)
        fields['box'].add_widget(synced_body)
        fields['box'].add_widget(fields['save'])
        def save(_):
            try:
                self.store.save_profile(fields['inputs'][0].text, canonical_birthday(fields['inputs'][1].text), float(fields['inputs'][2].text), float(fields['inputs'][3].text), float(fields['inputs'][4].text), int(float(fields['inputs'][5].text)), int(float(fields['inputs'][6].text)))
                popup.dismiss(); self.refresh_all()
            except ValueError:
                fields['error'].text = '목표 수치는 숫자로 입력해 주세요.'
        fields['save'].bind(on_release=save)
        popup.open()

    def open_health_connect(self):
        """Open this app's exact Health Connect permission sheet."""
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Bridge = autoclass('com.welltable.welltable.HealthConnectBridge')
            activity = PythonActivity.mActivity
            if not Bridge.requestPermissions(activity):
                raise RuntimeError('Health Connect permission activity unavailable')
        except Exception:
            self._health_notice('Health Connect 권한 화면을 열 수 없어요', '기기의 Health Connect 앱 또는 시스템 서비스를 확인한 뒤 다시 시도해 주세요.')

    def write_health_nutrition(self, item):
        """Mirror an explicitly selected meal after local storage succeeds."""
        try:
            from jnius import autoclass
            Activity = autoclass('org.kivy.android.PythonActivity')
            Bridge = autoclass('com.welltable.welltable.HealthConnectBridge')
            Bridge.writeNutrition(Activity.mActivity, str(item.get('title') or '식단 기록'),
                                  float(item.get('calories') or 0),
                                  float(item.get('protein') or 0), float(item.get('carbs') or 0))
        except Exception:
            # Local recording is never blocked by a declined write permission.
            pass

    def write_health_workout(self, title, minutes):
        """Mirror only a workout the user intentionally records here."""
        try:
            from jnius import autoclass
            Activity = autoclass('org.kivy.android.PythonActivity')
            Bridge = autoclass('com.welltable.welltable.HealthConnectBridge')
            Bridge.writeWorkout(Activity.mActivity, str(title), int(minutes))
        except Exception:
            pass

    def _poll_health(self, _dt):
        # A single outstanding read avoids race conditions while values are
        # refreshed frequently on the visible dashboard.
        if not getattr(self, '_health_sync_running', False):
            self.sync_health(silent=True)

    def _refresh_profile_sync_result(self, fields, show_synced_body, success):
        if success:
            show_synced_body()
            fields['error'].color = (.62,1,.82,1)
            fields['error'].text = '최신 신체 정보를 입력했어요.'
        else:
            fields['error'].color = (1,.55,.58,1)
            fields['error'].text = '가져오지 못했어요. Health Connect 권한을 확인해 주세요.'

    def sync_health(self, silent=False, after=None):
        """Pull the completed native snapshot without freezing the Kivy UI."""
        try:
            if getattr(self, '_health_sync_running', False):
                return
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Bridge = autoclass('com.welltable.welltable.HealthConnectBridge')
            Bridge.sync(PythonActivity.mActivity)
            self._health_sync_running = True
            self._health_sync_silent = silent
            self._health_after_sync = after
            Clock.schedule_interval(self._finish_health_sync, .45)
        except Exception as exc:
            if after:
                after(False)
            if not silent:
                self._health_notice('동기화를 시작할 수 없어요', str(exc))

    def _finish_health_sync(self, _dt):
        try:
            from jnius import autoclass
            Bridge = autoclass('com.welltable.welltable.HealthConnectBridge')
            payload = json.loads(str(Bridge.getLastSyncJson()))
            state = payload.get('state')
            if state == 'syncing':
                return True
            if state == 'ready':
                self.store.apply_health_snapshot(payload)
                self.refresh_all()
                callback = getattr(self, '_health_after_sync', None)
                self._health_after_sync = None
                if callback:
                    callback(True)
                if not self._health_sync_silent:
                    self._health_notice('동기화 완료', '운동, 체중, 심박수, 수면 기록을 최신 정보로 반영했어요.')
            elif state == 'permission_required':
                callback = getattr(self, '_health_after_sync', None)
                self._health_after_sync = None
                if callback:
                    callback(False)
                # Silent app-start/background refreshes never interrupt the
                # user. A person-initiated sync receives an explicit choice.
                if not self._health_sync_silent:
                    self._health_permission_notice(payload.get('message'))
            else:
                callback = getattr(self, '_health_after_sync', None)
                self._health_after_sync = None
                if callback:
                    callback(False)
                if not self._health_sync_silent:
                    self._health_notice(
                        '동기화가 필요해요',
                        payload.get('message', 'Health Connect 읽기 권한을 하나 이상 허용해 주세요.'),
                        on_confirm=self.open_health_connect,
                    )
        except Exception as exc:
            callback = getattr(self, '_health_after_sync', None)
            self._health_after_sync = None
            if callback:
                callback(False)
            if not getattr(self, '_health_sync_silent', False):
                self._health_notice('동기화를 완료하지 못했어요', str(exc))
        self._health_sync_running = False
        return False

    def _health_notice(self, title, message, on_confirm=None):
        notice = RoundedCard(orientation='vertical', padding=dp(22), spacing=dp(12), radius=dp(26), background_color=[.035,.050,.085,.99], border_color=[.72,.82,1,.16])
        header, dialog = self._dialog_header(title, '')
        notice.add_widget(header)
        notice.add_widget(Label(text=message, font_name=self.font_name, font_size=dp(12), color=(.68,.75,.89,1), halign='center', valign='middle'))
        close = GlassButton(text='확인', size_hint_y=None, height=dp(40), font_size=dp(11), glass_color=(.15,.24,.40,.72))
        notice.add_widget(close)
        popup = Popup(title='', content=notice, size_hint=(.86,None), height=dp(230), background='', background_color=(0,0,0,0), overlay_color=(0,0,0,.66))
        dialog['popup'] = popup
        def confirm(_button):
            popup.dismiss()
            # The permission activity must be started after the Kivy popup has
            # fully released focus; otherwise some Android versions only close
            # the dialog and never show Health Connect's App access page.
            if on_confirm:
                Clock.schedule_once(lambda _dt: on_confirm(), .12)
        close.bind(on_release=confirm)
        popup.open()

    def _health_permission_notice(self, message):
        """Ask before leaving the app for Android's permission settings."""
        notice = RoundedCard(orientation='vertical', padding=dp(22), spacing=dp(12), radius=dp(26), background_color=[.035,.050,.085,.99], border_color=[.72,.82,1,.16])
        header, dialog = self._dialog_header('Health Connect 권한이 필요해요', '')
        notice.add_widget(header)
        notice.add_widget(Label(text=message or '동기화에 필요한 읽기 권한을 허용해 주세요.', font_name=self.font_name, font_size=dp(12), color=(.68,.75,.89,1), halign='center', valign='middle'))
        actions = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        later = GlassButton(text='다음에', font_name=self.font_name, glass_color=(.12,.18,.30,.9))
        confirm = GlassButton(text='확인', font_name=self.font_name, glass_color=(.16,.42,.58,.96), color=(.88,1,1,1))
        actions.add_widget(later); actions.add_widget(confirm); notice.add_widget(actions)
        popup = Popup(title='', content=notice, size_hint=(.86,None), height=dp(238), background='', background_color=(0,0,0,0), overlay_color=(0,0,0,.66))
        dialog['popup'] = popup
        later.bind(on_release=lambda _button: popup.dismiss())
        def open_settings(_button):
            popup.dismiss(); Clock.schedule_once(lambda _dt: self.open_health_connect(), .12)
        confirm.bind(on_release=open_settings); popup.open()

    def form_popup(self,title,fields):
        box=RoundedCard(
            orientation='vertical',
            spacing=dp(10),
            padding=dp(20),
            radius=dp(26),
            background_color=[.012,.020,.038,1],
            border_color=[.95,.97,1,.16],
            # Dialogs deliberately use near-opaque glass. The page behind is
            # dimmed by the popup overlay, rather than bleeding through text.
            surface_opacity=.98,
            rim_strength=.55,
            size_hint_y=None,
        ); inputs=[]; labels=[]
        # Let long forms grow inside a scroll view instead of forcing the popup
        # above the visible area on smaller Android screens.
        box.bind(minimum_height=box.setter('height'))
        header, dialog = self._dialog_header(title, '입력한 내용은 이 기기에만 저장됩니다.')
        box.add_widget(header)
        for label,hint in fields:
            if label == '__widget__':
                box.add_widget(hint)
                continue
            field_label = Label(text=label,font_name=self.font_name,size_hint_y=None,height=dp(22),color=(.78,.84,.94,1),halign='left',valign='middle')
            labels.append(field_label)
            box.add_widget(field_label)
            item=GlassInput(text='',hint_text=hint,multiline=False,font_name=self.font_name,
                            size_hint_y=None,height=dp(47),padding=[dp(12),dp(12)])
            inputs.append(item);box.add_widget(item)
        error=Label(text='',font_name=self.font_name,size_hint_y=None,height=dp(18),color=(1,.48,.48,1));box.add_widget(error)
        save=GlassButton(text='저장하기',font_name=self.font_name,size_hint_y=None,height=dp(50),glass_color=(.24,.42,.82,.86),color=(1,1,1,1));box.add_widget(save)
        content=ScrollView(
            do_scroll_x=False,
            bar_width=0,
            effect_cls=ScrollEffect,
            scroll_distance=dp(6),
            scroll_timeout=60,
        )
        content.add_widget(box)
        popup_height=min(dp(620), max(dp(360), Window.height-dp(84)))
        p=Popup(title='', content=content, size_hint=(.90,None), height=popup_height,
                pos_hint={'center_x': .5, 'center_y': .5},
                background='', background_color=(0,0,0,0), separator_color=(0,0,0,0), overlay_color=(0,0,0,.84))
        dialog['popup'] = p
        return {'popup':p,'box':box,'inputs':inputs,'labels':labels,'save':save,'error':error}


if __name__ == '__main__':
    WelltableApp().run()
