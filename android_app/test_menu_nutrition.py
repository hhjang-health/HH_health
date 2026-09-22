import json
import unittest
from menu_nutrition import fresh_detail, welstory_html, enrich_welstory
from wonderplus import parse_menu, detail_nutrition


class SourceNutritionTests(unittest.TestCase):
    def test_wonderplus_green_detail_endpoint_fields(self):
        """The public green-ellipsis endpoint supplies kcal/carbs/protein/fat/sodium."""
        def fetch(_url, **_kwargs):
            return '{"data":[["경상도식소고기뭇국","629","1783","105","27","11","67:17:16",null,null]]}'
        nutrients = detail_nutrition(fetch, 'O000002', 'S000685', '20260919', '006', '001')
        self.assertEqual(nutrients, {'calories': 629, 'sodium': 1783, 'carbs': 105, 'protein': 27, 'fat': 11})

    def test_wonderplus_preserves_published_detail_nutrients(self):
        payload = {'data': [[
            '020', 'KITCHEN 1', '20260919', '비빔밥', '730', '국',
            None, None, None, None, None, None, None, None, None, None,
            None, None, None, None, None, None, None, None, None, None,
            None, None, None, None,
            '{"protein": 24, "carbohydrates": 91, "sodium": 610}'
        ]]}
        rows = json.loads(parse_menu(payload, '20260919')['lunch'])
        self.assertEqual(rows[0]['nutrition'], {'calories': 730, 'protein': 24, 'carbs': 91, 'sodium': 610})

    def test_fresh_detail_respects_disclosure(self):
        nutrients = fresh_detail({'kcal':1077,'protein':28,'carb':145,'caloriesYn':'Y','proteinYn':'Y','carboYn':'Y','fat':0,'fatYn':'N'})
        self.assertEqual(nutrients['calories'],1077)
        self.assertEqual(nutrients['protein'],28)
        self.assertEqual(nutrients['carbs'],145)
        self.assertIsNone(nutrients['fat'])

    def test_wonder_exact_date_and_kitchens(self):
        data={'data':[['010','KITCHEN 1','20260919','조식',732,'반찬'],
                      ['010','Ramyun','20260919','라면',500,''],
                      ['010','KITCHEN 2','20260918','어제',600,'']]}
        rows=json.loads(parse_menu(data,'20260919')['breakfast'])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['nutrition']['calories'],732)
        self.assertNotIn('protein',rows[0]['nutrition'])

    def test_wonder_takeout_counters_are_preserved(self):
        data={'data':[
            ['020','TAKE OUT1','20260919','샌드위치',420,'음료'],
            ['020','Take Out 2','20260919','도시락',560,'반찬'],
        ]}
        rows=json.loads(parse_menu(data,'20260919')['lunch'])
        self.assertEqual([row['title'] for row in rows], ['Take Out1', 'Take Out2'])

    def test_wonder_takeout_keeps_individual_children(self):
        data={'data':[
            ['020','TAKE OUT1','20260919','샌드위치, 샐러드',420,'음료, 과일'],
        ]}
        row=json.loads(parse_menu(data,'20260919')['lunch'])[0]
        self.assertEqual([item['menu'] for item in row['items']], ['샌드위치', '샐러드', '음료', '과일'])
        # The official 420 kcal is for the full counter, never copied to each
        # child and therefore cannot be multiplied by multi-selection.
        self.assertEqual(row['items'][0]['nutrition'], {})

    def test_welstory_individual_values_not_sum(self):
        doc='d[0]={id:"a",date:"20260919",name:"밥",mealTimeId:"1",nutrition:{calories:600,protein:22},components:[]};d[1]={id:"b",date:"20260919",name:"면",mealTimeId:"1",nutrition:{calories:700,protein:25},components:[]};'
        rows=json.loads(welstory_html(doc,'20260919')['breakfast'])
        self.assertEqual([r['nutrition']['calories'] for r in rows],[600,700])
        self.assertIsNone(rows[0]['nutrition']['carbs'])
        self.assertEqual(json.loads(welstory_html(doc,'20260920')['breakfast']),[])

    def test_nutrient_detail_sums_component_values_once(self):
        meals={'breakfast':json.dumps([{'menu':'밥','nutrition':{'calories':600},'source_note':'test','detail_query':{'restaurantId':'a','date':'20260919','mealTimeId':'1','hallNo':'x','courseType':'AA'}}])}
        response=json.dumps([{'name':'밥','nutrition':{'calories':500,'protein':20,'carbohydrates':70,'sugar':9,'fiber':3}}, {'name':'국','nutrition':{'calories':100,'protein':5,'carbohydrates':10,'sugar':1,'fiber':2}}])
        seen=[]
        row=json.loads(enrich_welstory(lambda url:(seen.append(url) or response),meals)['breakfast'])[0]
        self.assertIn('nutrient=1', seen[0])
        self.assertEqual(row['nutrition']['protein'],25)
        self.assertEqual(row['nutrition']['calories'],600)
        self.assertEqual(row['nutrition']['carbs'],80)
        self.assertEqual(row['nutrition']['sugar'],10)
        self.assertEqual(row['nutrition']['fiber'],5)
        self.assertEqual(row['menu'],'밥 · 국')

    def test_failed_detail_does_not_invent_macros(self):
        meals={'breakfast':json.dumps([{'menu':'밥','nutrition':{'calories':600},'source_note':'test'}])}
        row=json.loads(enrich_welstory(lambda _: '{}',meals)['breakfast'])[0]
        self.assertNotIn('protein',row['nutrition'])

if __name__=='__main__': unittest.main()
