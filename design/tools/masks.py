# Design Pro Max 8.1 · surface masks. Usage: python3 masks.py <room-id>
# Reads design/rooms.json, writes design/rooms/<room>_<surface>.png (soft mask) and an overlay preview for checking.
import json, sys, numpy as np, cv2, os
from PIL import Image
here=os.path.dirname(os.path.abspath(__file__)); root=os.path.dirname(here)
rooms=json.load(open(os.path.join(root,'rooms.json'),encoding='utf-8'))
rid=sys.argv[1]; room=[r for r in rooms if r['id']==rid][0]
img=cv2.imread(os.path.join(root,room['img']))  # BGR
H,W=img.shape[:2]
lab=cv2.cvtColor(img,cv2.COLOR_BGR2LAB).astype(np.float32)
L=lab[:,:,0]; A=lab[:,:,1]; B=lab[:,:,2]
over=img.copy()
colors=[(0,200,255),(255,120,0),(0,255,120)]
for i,s in enumerate(room['surfaces']):
    quad=np.array(s['quad'],np.int32)
    region=np.zeros((H,W),np.uint8); cv2.fillPoly(region,[quad],255)
    # base colour: median over the region (robust to objects when they cover < half of it)
    sel=region>0
    l0=np.median(L[sel]); a0=np.median(A[sel]); b0=np.median(B[sel])
    lo,hi=s.get('lum',[0.45,1.45]); ctol=s.get('chroma',9)
    ratio=L/max(l0,1)
    chroma=np.sqrt((A-a0)**2+(B-b0)**2)
    m=(ratio>lo)&(ratio<hi)&(chroma<ctol)&sel
    # zones: inside a polygon use other limits (stricter around furniture, looser on sun spots)
    for z in s.get('zones',[]):
        zr=np.zeros((H,W),np.uint8); cv2.fillPoly(zr,[np.array(z['poly'],np.int32)],1); zr=zr.astype(bool)&sel
        zl,zh=z.get('lum',[lo,hi]); zc=z.get('chroma',ctol)
        m[zr]=((ratio>zl)&(ratio<zh)&(chroma<zc))[zr]
    m=m.astype(np.uint8)*255
    for ex in s.get('exclude',[]): cv2.fillPoly(m,[np.array(ex,np.int32)],0)
    # clean: close small holes (thin fixtures stay excluded only if wider than k), remove specks
    k=s.get('close',5 if not s.get('zones') else 3)
    m=cv2.morphologyEx(m,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
    m=cv2.morphologyEx(m,cv2.MORPH_CLOSE,np.ones((k,k),np.uint8))
    # keep only the largest connected component plus any component touching it after closing
    n,lab_,stats,_=cv2.connectedComponentsWithStats(m)
    if n>1:
        big=1+np.argmax(stats[1:,cv2.CC_STAT_AREA]); keep=np.zeros_like(m); keep[lab_==big]=255
        # also keep components larger than 2% of region (floor seen through glass etc.)
        for j in range(1,n):
            if stats[j,cv2.CC_STAT_AREA]>0.02*sel.sum(): keep[lab_==j]=255
        m=keep
    m=cv2.GaussianBlur(m,(0,0),1.2)
    cv2.imwrite(os.path.join(root,'rooms',f"{rid}_{s['id']}.png"),m)
    gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY).astype(np.float32)
    s['base']=round(float(gray[m>127].mean()),1)
    s['mv']=int(__import__('time').time())
    col=np.array(colors[i%3],np.uint8)
    a=(m.astype(np.float32)/255)[...,None]*0.45
    over=(over*(1-a)+col*a).astype(np.uint8)
    cv2.polylines(over,[quad],True,tuple(int(c) for c in col),3)
    print(s['id'],'base L',round(float(l0),1),'coverage',round(float((m>127).sum()/sel.sum()),3))
json.dump(rooms,open(os.path.join(root,'rooms.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=1)
clean=[{k:v for k,v in r.items() if not k.startswith('_')} for r in rooms]
for r in clean: r['surfaces']=[{k:v for k,v in s.items() if not k.startswith('_')} for s in r['surfaces']]
open(os.path.join(root,'rooms.js'),'w',encoding='utf-8').write('window.ROOMS='+json.dumps(clean,ensure_ascii=False)+';')
small=cv2.resize(over,(1600,int(1600*H/W)))
cv2.imwrite(os.path.join(root,'rooms',f'_check_{rid}.jpg'),small,[cv2.IMWRITE_JPEG_QUALITY,80])
