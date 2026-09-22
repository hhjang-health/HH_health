"""Code-rendered preview of the current phone layouts (not a device screenshot)."""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math
from pathlib import Path

W, H = 412, 892
ROOT = Path(__file__).parent
FONT = ROOT / 'assets/fonts/Pretendard-Regular.otf'
BOLD = ROOT / 'assets/fonts/Pretendard-SemiBold.otf'

def font(n, bold=False): return ImageFont.truetype(str(BOLD if bold else FONT), n)
def round_rect(d, box, r, fill, outline=None): d.rounded_rectangle(box, r, fill=fill, outline=outline, width=1)
def glass(d, box, r, fill, outline=None):
    """Draw a genuine translucent layer over the already drawn background."""
    im = d._image
    layer = Image.new('RGBA', im.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    softened = (20, 29, 43, int(fill[3] * .68))
    ld.rounded_rectangle(box, r, fill=softened)
    # A neutral white edge and a very faint inner highlight are the visual
    # cue for glass; feature colours belong inside, not on its perimeter.
    ld.rounded_rectangle(box, r, outline=(238,246,255,38), width=1)
    ld.rounded_rectangle((box[0]+1,box[1]+1,box[2]-1,box[3]-1), max(1,r-1), outline=(255,255,255,12), width=1)
    ld.line([(box[0]+r, box[1]+1), (box[2]-r, box[1]+1)], fill=(245,249,255,32), width=1)
    im.alpha_composite(layer)
def cafeteria_glass(d, box, r):
    """Lighter blue glass used by the current cafeteria widget."""
    im = d._image
    layer = Image.new('RGBA', im.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.rounded_rectangle(box, r, fill=(33, 64, 94, 132))
    ld.rounded_rectangle(box, r, outline=(210, 231, 255, 62), width=1)
    ld.rounded_rectangle((box[0]+2,box[1]+2,box[2]-2,box[3]-2), max(1,r-2), outline=(255,255,255,18), width=1)
    im.alpha_composite(layer)
def glass_rect(d, box, fill):
    im = d._image
    layer = Image.new('RGBA', im.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rectangle(box, fill=fill)
    im.alpha_composite(layer)
def glass_poly(d, points, fill):
    im = d._image
    layer = Image.new('RGBA', im.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).polygon(points, fill=fill)
    im.alpha_composite(layer)
def text(d, xy, value, n, fill, bold=False, anchor=None): d.text(xy, value, font=font(n,bold), fill=fill, anchor=anchor)
def pill(d, box, value, fill=(23,42,66), color=(205,222,255)):
    glass(d, box, (box[3]-box[1])//2, (*fill, 178), (145,185,247))
    text(d, ((box[0]+box[2])//2,(box[1]+box[3])//2), value, 10, color, anchor='mm')
def shell():
    # Sampled from the approved early home screenshot: navy header, dark body,
    # and the restrained teal/warm diffuse lights behind the lower cards.
    im=Image.new('RGBA',(W,H),(7,13,27,255)); d=ImageDraw.Draw(im)
    stops=[(0,(9,22,41)),(105,(11,32,56)),(190,(12,36,64)),(320,(14,25,43)),(446,(7,13,27)),(H,(7,13,27))]
    for index in range(len(stops)-1):
        sy, left=stops[index]; ey, right=stops[index+1]
        for y in range(sy,ey+1):
            t=(y-sy)/max(1,ey-sy)
            d.line((0,y,W,y), fill=tuple(int(left[c]+(right[c]-left[c])*t) for c in range(3))+(255,))
    glow = Image.new('RGBA', (W,H), (0,0,0,0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((150,500,520,880), fill=(17,109,104,45))
    gd.ellipse((-130,620,230,980), fill=(130,75,48,35))
    glow = glow.filter(ImageFilter.GaussianBlur(75))
    im.alpha_composite(glow)
    # Status bar is intentionally present in the preview and has its own
    # legible white icons, matching the Android implementation.
    text(d,(20,15),'3:54',10,(246,249,255),True,anchor='lm')
    text(d,(338,15),'◔ 5G  ▮▮▮  85',9,(246,249,255),True,anchor='lm')
    return im,d
def dock(d, selected):
    glass(d,(24,806,388,876),28,(10,20,37,172),(111,139,180))
    labels=['홈','식단','운동','리포트','내 정보']
    xs=[60,132,204,276,348]
    for x,label in zip(xs,labels):
        active=label==selected
        if active: round_rect(d,(x-27,814,x+27,866),17,(37,58,108))
        text(d,(x,832),'●' if active else '○',17,(183,204,255) if active else (103,115,140),anchor='mm')
        text(d,(x,854),label,9,(207,221,255) if active else (126,137,157),bold=active,anchor='mm')
def home():
    im,d=shell(); text(d,(24,37),'9월 18일 · 목요일',10,(169,187,214)); text(d,(24,67),'회원님, 오늘도 가볍게 시작해요',22,(247,249,255),True)
    glass(d,(24,105,388,250),30,(19,30,48,176),(133,170,220)); text(d,(45,131),'오늘의 영양',11,(197,211,239),True)
    nutrients=[('칼로리','1,703','/ 1,800',(250,36,107)),('단백질','96g','/ 100g',(174,245,12)),('탄수화물','214g','/ 220g',(14,224,204))]
    for y,(label,current,target,c) in zip((160,188,216),nutrients):
        d.ellipse((45,y+5,53,y+13),fill=c); text(d,(61,y+1),label,10,(164,181,208)); text(d,(116,y-3),current,16,(246,249,255),True); text(d,(178,y+2),target,10,(78,91,116))
    rings=[((282,134,370,222),145,.95,(250,36,107),8),((292,144,360,212),92,.96,(174,245,12),7),((302,154,350,202),46,.97,(14,224,204),6)]
    for box,start,progress,c,width in rings:
        d.arc(box,0,360,fill=(24,33,49),width=width); d.arc(box,start,start+360*progress,fill=c,width=width)
        cx,cy=(box[0]+box[2])/2,(box[1]+box[3])/2; radius=(box[2]-box[0])/2
    cafeteria_glass(d,(24,267,388,506),24); text(d,(40,290),'오늘의 구내식당  ·  세메스 화성사업장',12,(235,255,247),True); pill(d,(241,279,300,307),'메뉴 열기',(36,69,105),(214,234,255)); pill(d,(309,279,369,307),'새로고침',(15,54,52),(178,255,225))
    for box,label,active in [((40,322,138,350),'화성',True),((145,322,243,350),'천안',False),((250,322,348,350),'동탄',False),((40,358,138,386),'아침',True),((145,358,243,386),'점심',False),((250,358,348,386),'저녁',False)]:
        pill(d,box,label,(31,70,118) if active else (20,30,46),(235,245,255) if active else (157,174,201))
    glass(d,(40,394,370,496),15,(15,30,42,170))
    for y,name,menu in [(398,'더고메','순두부찌개 · 불고기 · 현미밥 · 샐러드'),(432,'소담상','닭가슴살 스테이크 · 잡곡밥 · 나물'),(466,'마이보글','토마토 파스타 · 시저 샐러드 · 과일')]:
        text(d,(53,y+9),name,9,(186,235,221),True); text(d,(105,y+9),menu,9,(218,231,234)); pill(d,(323,y+1,365,y+27),'선택',(14,64,50),(186,255,221))
    text(d,(24,532),'오늘의 식단',20,(248,249,255),True)
    for y,title,sub in [(572,'아침','그릭 요거트 · 오트밀 · 바나나'),(650,'점심','비빔밥 · 두부 샐러드'),(728,'저녁','연어 구이 · 고구마 · 브로콜리')]:
        glass(d,(24,y,388,y+72),20,(13,20,36,166),(70,95,138)); text(d,(42,y+22),title,14,(246,248,255),True); text(d,(42,y+46),sub,10,(153,166,191)); pill(d,(278,y+22,310,y+50),'+'); pill(d,(322,y+22,371,y+50),'기록')
    dock(d,'홈'); return im
def manual_dialog():
    im = home(); d = ImageDraw.Draw(im)
    glass_rect(d,(0,0,W,H),(0,0,0,195))
    glass(d,(18,100,394,790),32,(21,31,47,236))
    text(d,(42,137),'아침 직접 선택',19,(248,250,255),True)
    text(d,(42,161),'오늘만 적용하거나, 같은 구성으로 세트를 만들 수 있어요.',10,(164,181,207))
    pill(d,(342,121,370,151),'×',(28,35,47),(235,241,255))
    text(d,(42,203),'선택한 음식',11,(220,232,250),True)
    glass(d,(42,221,370,270),16,(18,27,40,185))
    text(d,(56,242),'그릭 요거트 · 오트밀 · 바나나  ·  390 kcal',10,(198,218,244))
    glass(d,(42,286,370,330),15,(17,25,38,176))
    text(d,(56,309),'음식명 또는 카테고리 검색',11,(117,134,158))
    text(d,(42,362),'음식 라이브러리',12,(236,244,255),True)
    rows=[('✓  그릭 요거트','유제품 · 130 kcal · 단백질 15g'),('✓  오트밀','곡류 · 155 kcal · 단백질 5g'),('바나나','과일 · 105 kcal · 단백질 1.3g'),('계란','단백질 · 92 kcal · 단백질 6.3g')]
    for y,(title,detail) in zip((382,445,508,571),rows):
        glass(d,(42,y,370,y+54),16,(24,35,54,186))
        text(d,(57,y+19),title,11,(243,247,255),True)
        text(d,(57,y+39),detail,9,(162,183,211))
    pill(d,(42,710,193,755),'오늘만 선택',(26,51,87),(223,235,255))
    pill(d,(205,710,370,755),'세트로 저장',(41,76,137),(255,255,255))
    return im
def meals():
    im,d=shell(); text(d,(24,37),'식단 라이브러리',10,(169,187,214)); text(d,(24,68),'나의 식단 세트',27,(247,249,255),True); pill(d,(284,55,388,88),'+ 세트 만들기',(25,48,82),(219,231,255))
    glass(d,(24,116,388,231),28,(17,30,48,168),(126,164,219)); text(d,(43,143),'균형식 아침',12,(239,248,255),True); text(d,(43,169),'오트밀 · 그릭 요거트 · 블루베리',11,(167,187,216)); text(d,(43,199),'425 kcal  ·  단백질 29g',10,(121,231,190))
    pill(d,(306,140,369,168),'아침',(21,69,63),(185,255,225)); pill(d,(306,183,369,211),'수정',(18,31,53),(199,216,255))
    glass(d,(24,247,388,362),28,(10,47,56,162),(99,189,174)); text(d,(43,274),'든든한 점심',12,(239,255,251),True); text(d,(43,300),'현미 비빔밥 · 닭가슴살 · 샐러드',11,(169,203,199)); text(d,(43,330),'660 kcal  ·  단백질 43g',10,(128,235,200))
    pill(d,(306,271,369,299),'점심',(17,74,61),(185,255,225)); pill(d,(306,314,369,342),'수정',(18,31,53),(199,216,255))
    text(d,(24,407),'오늘 선택한 식단',19,(248,249,255),True); text(d,(24,434),'선택한 세트는 홈 화면에서 바로 기록할 수 있어요.',10,(153,169,194))
    for y,label,title,sub,c in [(466,'아침','균형식 아침','오트밀 · 그릭 요거트 · 블루베리',(52,94,167)),(548,'점심','든든한 점심','현미 비빔밥 · 닭가슴살 · 샐러드',(30,137,113)),(630,'저녁','가벼운 저녁','연어 구이 · 고구마 · 채소',(153,95,48))]:
        glass(d,(24,y,388,y+70),20,(13,20,36,162),(71,96,139)); round_rect(d,(40,y+14,80,y+54),13,c); text(d,(60,y+34),label[0],11,(255,255,255),True,anchor='mm'); text(d,(94,y+27),title,13,(247,249,255),True); text(d,(94,y+49),sub,10,(157,173,198)); pill(d,(324,y+23,370,y+49),'변경')
    dock(d,'식단'); return im
def workout():
    im,d=shell(); text(d,(24,37),'기록',10,(169,187,214)); text(d,(24,68),'운동',27,(247,249,255),True); pill(d,(227,55,280,88),'연결',(27,55,97),(211,225,255)); pill(d,(285,55,348,88),'동기화',(26,67,130),(220,235,255)); pill(d,(353,55,388,88),'+',(19,37,67),(220,235,255))
    glass(d,(24,116,388,258),30,(17,29,49,170),(111,151,212)); text(d,(44,145),'이번 주의 움직임',11,(164,187,225),True); text(d,(44,188),'182분',36,(255,255,255),True); text(d,(45,234),'목표 240분까지 58분 남았어요',10,(144,163,192))
    days=['월','화','수','목','금','토','일']; vals=[27,46,18,58,31,42,37]
    for i,(day,val) in enumerate(zip(days,vals)):
        x=247+i*19; d.rounded_rectangle((x,211-val,x+9,211),5,fill=(50,104,217) if i==3 else (72,94,137)); text(d,(x+4,229),day,8,(136,151,177),anchor='mm')
    text(d,(24,297),'최근 활동',19,(248,249,255),True); text(d,(24,323),'왼쪽으로 밀면 삭제가 표시됩니다.',10,(152,168,193))
    rows=[('실외 걷기','47분  ·  224 kcal','오늘 08:20',(43,157,100)),('근력 운동','35분  ·  182 kcal','어제 19:10',(65,95,181)),('러닝','26분  ·  198 kcal','9월 16일',(175,89,56))]
    for y,(title,detail,tail,c) in zip((356,442,528),rows):
        glass(d,(24,y,388,y+74),22,(13,20,36,164),(70,95,139)); round_rect(d,(42,y+17,82,y+57),13,c); text(d,(62,y+37),'●',13,(255,255,255),anchor='mm'); text(d,(97,y+26),title,14,(247,249,255),True); text(d,(97,y+49),detail,10,(158,174,200)); text(d,(363,y+26),tail,9,(130,147,175),anchor='ra')
    glass(d,(24,630,388,744),28,(8,96,112,164),(72,215,201)); text(d,(44,659),'오늘의 제안',11,(181,255,235),True); text(d,(44,703),'15분 산책, 가볍게 마무리해요',15,(246,255,252),True); pill(d,(294,686,369,718),'시작',(17,89,78),(197,255,235))
    dock(d,'운동'); return im
def body():
    im,d=shell(); text(d,(24,38),'내 몸의 변화',10,(132,143,165)); text(d,(24,67),'내 정보',27,(248,249,255),True); pill(d,(230,54,280,88),'프로필'); pill(d,(285,54,343,88),'동기화',(28,63,120)); pill(d,(349,54,382,88),'+')
    glass(d,(24,122,388,294),30,(14,24,43,170),(86,118,171)); text(d,(45,150),'현재 체중',11,(158,178,224),True); text(d,(45,210),'68.4',38,(255,255,255),True); text(d,(175,224),'kg',15,(151,164,190)); text(d,(45,264),'꾸준한 기록이 나만의 기준을 만들어요',10,(143,155,179))
    cards=[('체지방률','21.8%'),('골격근량','27.6 kg'),('최근 심박수','72 bpm'),('최근 수면','7.4시간')]
    pos=[(24,314),(211,314),(24,416),(211,416)]
    for (title,value),(x,y) in zip(cards,pos): glass(d,(x,y,x+177,y+84),20,(13,20,36,160),(69,94,137)); text(d,(x+14,y+20),title,10,(145,157,179)); text(d,(x+14,y+54),value,19,(248,249,255),True)
    glass(d,(24,520,388,590),20,(7,44,45,160),(87,174,139)); text(d,(39,542),'내 식당',11,(170,246,205),True); text(d,(39,566),'1 / 3개 설정됨 · 대표: 16라인 Cafeteria',10,(168,191,192)); pill(d,(299,540,370,572),'식당 설정',(14,64,50),(186,255,221))
    text(d,(24,627),'건강 기록 히스토리',18,(248,249,255),True); glass(d,(24,660,388,728),20,(13,20,36,160),(69,94,137)); text(d,(40,683),'2026-09-18',13,(245,248,255),True); text(d,(40,708),'68.4 kg  ·  체지방 21.8%  ·  골격근 27.6 kg',10,(153,166,191)); text(d,(334,683),'Health',10,(160,205,193))
    dock(d,'내 정보'); return im
def cafeteria_widget():
    """Launcher-widget preview: only the cafeteria block, with real widget opacity."""
    im,d=shell()
    # Android widget drawable: #A62A496B (65% opaque blue) + a subtle border.
    cafeteria_glass(d,(24,260,388,462),24)
    text(d,(42,290),'오늘의 구내식당 · 세메스 화성사업장',14,(241,247,255),True)
    text(d,(42,324),'점심',12,(157,244,228),True)
    text(d,(42,354),'한식사계  오리불고기',13,(220,234,245))
    text(d,(42,381),'모던키친  남산왕돈가스정식',13,(220,234,245))
    text(d,(42,408),'별미공방  자장면&계란후라이',13,(220,234,245))
    text(d,(350,440),'살빼자 열기  ›',11,(169,201,255),anchor='ra')
    return im
if __name__=='__main__':
    home().save(ROOT/'preview_home_glass_preview.png')
    manual_dialog().save(ROOT/'preview_manual_meal_glass_preview.png')
    meals().save(ROOT/'preview_meals_glass_preview.png')
    workout().save(ROOT/'preview_workout_glass_preview.png')
    body().save(ROOT/'preview_body_glass_preview.png')
    cafeteria_widget().save(ROOT/'preview_cafeteria_launcher_widget.png')
