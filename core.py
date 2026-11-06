"""Deterministic worksheet extraction. All mappings are read from printed labels."""
import base64, io, json, math, hashlib, re
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageOps
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

ROOT = Path(__file__).parent
DEFAULT_MAPS = [list('ץצאחהמםךרפףכדבת'), list('ןוגזינעסטקלש')]
SIZE = 420

def png(a):
    ok, data = cv2.imencode('.png', a)
    return 'data:image/png;base64,' + base64.b64encode(data).decode()

def decode(data):
    raw = base64.b64decode(data.split(',')[-1])
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert('RGB')
    im.thumbnail((2200, 2800))
    return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)

def order(p):
    p = np.array(p, np.float32).reshape(4,2)
    s = p.sum(axis=1); d = np.diff(p,axis=1).ravel()
    return np.array([p[s.argmin()],p[d.argmin()],p[s.argmax()],p[d.argmax()]],np.float32)

def warp(im, p, w=SIZE, h=SIZE):
    target = np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]])
    return cv2.warpPerspective(im,cv2.getPerspectiveTransform(order(p),target),(w,h),borderValue=(255,255,255))

def detect(im, rows):
    gray=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY)
    bw=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,41,12)
    contours,_=cv2.findContours(bw,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    area=im.shape[0]*im.shape[1]; found=[]
    for c in contours:
        a=cv2.contourArea(c)
        if not area*.018<a<area*.15: continue
        p=cv2.approxPolyDP(c,.025*cv2.arcLength(c,True),True)
        if len(p)!=4 or not cv2.isContourConvex(p): continue
        q=order(p); x,y,w,h=cv2.boundingRect(q)
        if not .5<w/h<1.5: continue
        center=q.mean(axis=0)
        if any(np.linalg.norm(center-v.mean(axis=0))<min(w,h)*.2 for v in found): continue
        found.append(q)
    if len(found)!=rows*3:
        raise ValueError(f'זוהו {len(found)} תאים מתוך {rows*3}. סמנו את ארבע פינות רשת התאים בתמונה.')
    found.sort(key=lambda q:q[:,1].mean())
    out=[]
    for r in range(rows): out.extend(sorted(found[r*3:r*3+3],key=lambda q:q[:,0].mean()))
    return out

def extract_cell(cell, threshold=105):
    gray=cv2.cvtColor(cell,cv2.COLOR_BGR2GRAY)
    # Work only inside the frame, below printed labels, above lower frame.
    background=cv2.morphologyEx(gray,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(101,101)))
    background=cv2.GaussianBlur(background,(31,31),0)
    normalized=cv2.divide(gray,np.maximum(background,1),scale=240)
    binary=np.uint8(normalized<threshold)*255
    binary[:int(SIZE*.15)]=0; binary[int(SIZE*.91):]=0
    binary[:,:int(SIZE*.055)]=0; binary[:,int(SIZE*.945):]=0
    # Opening rejects thin printed rules and pencil while preserving marker overlaps.
    clean=cv2.morphologyEx(binary,cv2.MORPH_OPEN,np.ones((7,1),np.uint8))
    clean=cv2.morphologyEx(clean,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
    n,labels,stats,_=cv2.connectedComponentsWithStats(clean)
    kept=np.zeros_like(clean); areas=[]
    for i in range(1,n):
        x,y,w,h,a=stats[i]
        if a>=55 and h>=5 and w>=4 and not (w>h*10 and h<22) and not (y>SIZE*.65 and h<45 and a<500):
            kept[labels==i]=255; areas.append(int(a))
    warnings=[]
    if not areas: warnings.append('לא נמצאה אות — יש לצייר או להעלות צילום אחר')
    if areas and max(areas)<300: warnings.append('ציור קטן מאוד — כדאי לבדוק')
    return kept,warnings

def contours(mask):
    cs,hierarchy=cv2.findContours(mask,cv2.RETR_TREE,cv2.CHAIN_APPROX_SIMPLE)
    result=[]
    if hierarchy is None:return result
    for i,c in enumerate(cs):
        if cv2.contourArea(c)<4: continue
        pts=cv2.approxPolyDP(c,.55,True).reshape(-1,2)
        if len(pts)<3:continue
        depth=0; parent=hierarchy[0][i][3]
        while parent>=0:depth+=1;parent=hierarchy[0][parent][3]
        result.append({'points':pts.tolist(),'hole':bool(depth%2)})
    return result

def process(data):
    mappings=data.get('maps',DEFAULT_MAPS)
    if len(mappings)!=2 or [len(m) for m in mappings]!=[15,12] or set(''.join(''.join(m) for m in mappings))!=set(chr(c) for c in range(0x5d0,0x5eb)):
        raise ValueError('המיפוי חייב להכיל את כל 27 האותיות, פעם אחת בלבד.')
    glyphs=[]; pages=[]
    for pi,src in enumerate(data['images']):
        im=decode(src); rows=5 if pi==0 else 4
        custom=(data.get('corners') or [None,None])[pi]
        if custom:
            h,w=im.shape[:2]; p=np.array(custom,np.float32)*[w,h]
            im=warp(im,p,1260,rows*420)
            quads=[np.float32([[c*420,r*420],[(c+1)*420-1,r*420],[(c+1)*420-1,(r+1)*420-1],[c*420,(r+1)*420-1]]) for r in range(rows) for c in range(3)]
        else: quads=detect(im,rows)
        preview=im.copy()
        for i,q in enumerate(quads):
            cv2.polylines(preview,[q.astype(np.int32)],True,(50,170,40),3)
            cell=warp(im,q)
            ch=mappings[pi][i]
            glyphs.append({'char':ch,'page':pi,'cell':i,'original':png(cell),'approved':False})
        pages.append(png(preview))
    return {'glyphs':sorted(glyphs,key=lambda g:ord(g['char'])),'pages':pages}

def validate_approvals(glyphs):
    expected=set(chr(c) for c in range(0x5d0,0x5eb))
    if len(glyphs)!=27 or {g.get('char') for g in glyphs}!=expected:
        raise ValueError('נדרשות כל 27 האותיות במיפוי הנכון')
    if any(g.get('approved') is not True for g in glyphs):
        raise ValueError('יש לאשר כל אחת מ־27 האותיות לפני יצירת הפונט')

def validate_source_cell(image):
    """Check fixed worksheet guide geometry, not the semantic identity of handwriting."""
    cell=cv2.resize(image,(SIZE,SIZE))
    gray=cv2.cvtColor(cell,cv2.COLOR_BGR2GRAY).astype(np.int16)
    # Thin dark rules differ from nearby rows; broad photographic shadows do not.
    support=np.zeros(SIZE)
    for y in range(9,SIZE-9):
        surroundings=np.median(np.stack([gray[y-8],gray[y-6],gray[y+6],gray[y+8]]),axis=0)
        support[y]=np.mean((surroundings-gray[y]>22)[int(SIZE*.08):int(SIZE*.92)])
    bands=[(.17,.32),(.34,.52),(.70,.87)]
    scores=[float(support[int(a*SIZE):int(b*SIZE)].max()) for a,b in bands]
    if sum(v>=.34 for v in scores)<2:
        return {'valid':False,'error':'לא זוהו קווי העזר של תא מהתבנית. יש להעלות צילום של התא עם האות וקווי העזר, ולא תמונה רגילה.','guideScores':scores}
    return {'valid':True,'guideScores':scores}

def source_issues(glyphs):
    issues=[]
    for g in glyphs:
        original=g.get('sourceOriginal') or g.get('original')
        if not original:
            issues.append({'char':g.get('char',''),'error':'חסר צילום התא המקורי. העלו צילום חדש מהתבנית.'})
            continue
        check=validate_source_cell(decode(original))
        if not check['valid']:issues.append({'char':g['char'],'error':check['error']})
    return issues


def digitize_approved(data):
    glyphs=data['glyphs'];validate_approvals(glyphs)
    issues=source_issues(glyphs)
    if issues:raise ValueError('האות '+issues[0]['char']+': '+issues[0]['error'])
    result=[]
    for g in glyphs:
        if g.get('mask'):
            mask=mask_from_url(g['mask']);warnings=[w for w in g.get('warnings',[]) if w!='בדקו שהחילוץ שומר על הציור המקורי']
        else:
            mask,warnings=extract_cell(decode(g['original']),int(data.get('threshold',105)))
        if not mask.any():
            raise ValueError('לא נמצאה צורה באות '+g['char']+' — חזרו לבדיקה או העלו צילום אחר')
        result.append({**g,'mask':png(255-mask),'initial':png(255-mask),'contours':contours(mask),'warnings':warnings})
    return {'glyphs':result}

def mask_from_url(url):
    a=cv2.imdecode(np.frombuffer(base64.b64decode(url.split(',')[-1]),np.uint8),cv2.IMREAD_GRAYSCALE)
    return np.uint8(a<128)*255

def make_font(data):
    glyphs=data['glyphs']; validate_approvals(glyphs); expected=set(chr(c) for c in range(0x5d0,0x5eb))
    if len(glyphs)!=27 or {g['char'] for g in glyphs}!=expected:raise ValueError('נדרשות כל 27 האותיות')
    name=data.get('name','My Hebrew Font').strip()[:60] or 'My Hebrew Font'
    fb=FontBuilder(1000,isTTF=True)
    names=['.notdef','space']+['uni%04X'%ord(g['char']) for g in glyphs]
    fb.setupGlyphOrder(names); outlines={}; metrics={}; cmap={32:'space'}
    pen=TTGlyphPen(None);pen.moveTo((50,0));pen.lineTo((50,500));pen.lineTo((350,500));pen.lineTo((350,0));pen.closePath()
    outlines['.notdef']=pen.glyph(); metrics['.notdef']=(400,50)
    outlines['space']=TTGlyphPen(None).glyph();metrics['space']=(260,0)
    baseline=float(data.get('baseline',.43))*SIZE
    scale=500/(SIZE*.19)
    ymin=0;ymax=750
    for g,gn in zip(glyphs,names[2:]):
        mask=mask_from_url(g['mask']); cs=contours(mask); xx=np.where(mask>0)[1];left=int(xx.min()) if len(xx) else 0
        pen=TTGlyphPen(None)
        for c in cs:
            pts=[(round((x-left)*scale+55),round((baseline-y)*scale)) for x,y in c['points']]
            area=sum(pts[i][0]*pts[(i+1)%len(pts)][1]-pts[(i+1)%len(pts)][0]*pts[i][1] for i in range(len(pts)))
            if (area>0) != c['hole']:pts.reverse()
            pen.moveTo(pts[0])
            for p in pts[1:]:pen.lineTo(p)
            pen.closePath()
            ymin=min(ymin,min(p[1] for p in pts));ymax=max(ymax,max(p[1] for p in pts))
        outlines[gn]=pen.glyph();metrics[gn]=(max(140,round((int(xx.max())-left)*scale+110)) if len(xx) else 400,55 if len(xx) else 0)
        cmap[ord(g['char'])]=gn
    fb.setupCharacterMap(cmap);fb.setupGlyf(outlines);fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ymax+80,descent=ymin-80)
    identity=json.dumps({'name':name,'baseline':baseline,'glyphs':[(g['char'],g['mask']) for g in sorted(glyphs,key=lambda g:g['char'])]},ensure_ascii=False,sort_keys=True).encode()
    fingerprint=hashlib.sha256(identity).hexdigest()[:12]
    slug=re.sub(r'[^A-Za-z0-9-]', '', name.replace(' ','-'))[:30] or 'HebrewFont'
    ps_name=f'{slug}-v2-{fingerprint}-Regular'
    display_family=name+' '+fingerprint[:6].upper()
    fb.setupNameTable({'familyName':display_family,'styleName':'Regular','typographicFamily':display_family,'typographicSubfamily':'Regular','uniqueFontIdentifier':ps_name+';2.0','fullName':display_family+' Regular','psName':ps_name,'version':'Version 2.0'})
    fb.setupOS2(sTypoAscender=ymax+80,sTypoDescender=ymin-80,usWinAscent=ymax+80,usWinDescent=abs(ymin-80),sTypoLineGap=0)
    fb.setupPost();fb.setupMaxp()
    out=io.BytesIO();fb.save(out);return out.getvalue()
