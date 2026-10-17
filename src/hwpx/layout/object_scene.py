"""Cache-blind bounded table and picture scene; SDK is an external observer.

Authored cellSz dimensions are minimum box constraints. subList textWidth /
textHeight and lineseg arrays are derived layout and never measurement inputs.
Unsupported policies fail the whole document before returning any page.
"""
from __future__ import annotations
import copy, hashlib, io, zipfile, base64
from .body_scene import build_body_scene, _prepare_paragraph
from .pages import HP, HH, _pitch, _MIN_SIDE, _spare_cut, _SPARE_DROPPED
from typing import Any

HC='{http://www.hancom.co.kr/hwpml/2011/core}'
OBJECT_ELEMENTS={'tbl','sz','pos','outMargin','inMargin','tr','tc','subList','cellAddr','cellSpan','cellSz','cellMargin',
                 'pic','orgSz','curSz','flip','rotationInfo','renderingInfo','transMatrix','scaMatrix','rotMatrix',
                 'imgRect','pt0','pt1','pt2','pt3','imgClip','imgDim','img','effects','shapeComment'}

def build_document_scene(data, provider, *, cache_mode='ignore'):
    # Body-only callers retain the accepted stage03 algorithm and page schema.
    # None requests control detection on the guarded, already parsed core tree.
    return build_body_scene(data,provider,cache_mode=cache_mode,_object_layout=None)


def render_headers(data,root,measure,body,paper,margins,provider,scene,reject):
    """Lay out header stories locally, then copy onto each applicable page.

    A header uses authored page margins, never cached subList measurements.
    Body flow cannot read or consume its independent cursor.
    """
    from types import SimpleNamespace
    from lxml import etree as ET  # type: ignore[reportAttributeAccessIssue]  # incomplete lxml typing
    headers=list(root.sections[0].element.iter(HP+'header'))
    if not headers:return
    if len(headers)!=1:reject('header','multiple/changeable header stories not yet implemented');return
    header=headers[0];sl=header.find(HP+'subList')
    if sl is None or margins['header']<=0:reject('header','missing/nonpositive header region');return
    if header.get('applyPageType','BOTH') not in {'BOTH','EVEN','ODD'}:reject('header','unknown page parity');return
    if sl.get('textDirection','HORIZONTAL')!='HORIZONTAL' or sl.get('vertAlign','TOP')!='TOP' or sl.get('lineWrap','BREAK')!='BREAK':
        reject('header','unsupported header text policy');return
    if any(sl.get(k,'0') not in {'','0'} for k in ['linkListIDRef','linkListNextIDRef','hasTextRef','hasNumRef']):
        reject('header','linked/referenced header content');return
    section=ET.Element(root.sections[0].element.tag)
    for p in sl.findall(HP+'p'):section.append(copy.deepcopy(p))
    proxy=SimpleNamespace(headers=root.headers,sections=[SimpleNamespace(element=section)],char_property=root.char_property)
    region=dict(x=body['x'],y=margins['top'],width=body['width'],height=margins['header'])
    local=dict(pages=[],unsupported=[],errors=[])
    paginate_objects(data,proxy,measure,region,paper,provider,local,lambda path,reason:local['unsupported'].append(dict(path=path,reason=reason)))
    for issue in local['unsupported']:reject('header/'+issue['path'],issue['reason'])
    if local['unsupported']:return
    if len(local['pages'])!=1 or local['errors']:reject('header','header exceeds its region');return
    visibility=next(root.sections[0].element.iter(HP+'visibility'),None)
    hidden_first=visibility is not None and visibility.get('hideFirstHeader','0')=='1'
    for page in scene['pages']:
        number=page['index']+1;parity=header.get('applyPageType','BOTH')
        if (hidden_first and number==1) or (parity=='EVEN' and number%2) or (parity=='ODD' and number%2==0):continue
        lines=copy.deepcopy(local['pages'][0]['lines']);objects=copy.deepcopy(local['pages'][0]['objects'])
        for line in lines:
            line['story']=dict(line.get('story',{}),region='header',headerId=header.get('id','0'))
        for obj in objects:obj['storyRegion']='header';obj['headerId']=header.get('id','0')
        page['lines']=lines+page['lines'];page.setdefault('objects',[])[:0]=objects

def integer(n,k,default=0):return int(n.get(k,str(default))) if n is not None else default

def render_page_numbers(root,body,paper,margins,provider,scene,reject):
    """Automatic page labels use an independent Hancom default text style.

    Bottom labels align the font's Windows descent to the bottom margin;
    numbering does not consume the body's pagination cursor.
    """
    from ..form_fit.measure import TextStyle
    fields=[]
    for pi,p in enumerate(root.sections[0].element.findall(HP+'p')):
        for r in p.findall(HP+'run'):
            for ctrl in r.findall(HP+'ctrl'):
                for n in ctrl.findall(HP+'pageNum'):fields.append((pi,n))
    all_fields=list(root.sections[0].element.iter(HP+'pageNum'))
    if not all_fields:return
    if len(fields)!=len(all_fields) or len(fields)!=1:reject('pageNum','multiple/nested page number fields');return
    pi,field=fields[0];position=field.get('pos','BOTTOM_CENTER')
    if field.get('formatType','DIGIT')!='DIGIT' or position not in {'BOTTOM_LEFT','BOTTOM_CENTER','BOTTOM_RIGHT'}:
        reject('pageNum','page label format/position not yet implemented');return
    side=field.get('sideChar','')
    if len(side)>1 or margins['footer']<=0:reject('pageNum','invalid side character/footer region');return
    visibility=next(root.sections[0].element.iter(HP+'visibility'),None)
    hidden_first=visibility is not None and visibility.get('hideFirstPageNum','0')=='1'
    start=next(root.sections[0].element.iter(HP+'startNum'),None)
    first=max(1,integer(start,'page',1))
    affected=[pg['index'] for pg in scene['pages'] if any(l['paragraphId']==pi and l.get('story',{}).get('region')!='header' for l in pg['lines'])]
    if not affected:reject('pageNum','page number anchor absent');return
    family='함초롬돋움';height=1000;style=TextStyle(hangul_face=family,glyph_face=family)
    try:metrics=provider.font_metrics(family,height)
    except (AttributeError,ValueError) as exc:reject('pageNum','font metrics unavailable: '+str(exc));return
    baseline=paper['height']-margins['bottom']-metrics['windowsDescent']
    for pg in scene['pages']:
        if pg['index']<min(affected) or (pg['index']==0 and hidden_first):continue
        number=first+pg['index'];text=f'{side} {number} {side}' if side else str(number)
        try:glyphs=provider.shape(text,dict(height=height,bold=False,italic=False),style)
        except Exception as exc:reject('pageNum','page label shaping: '+str(exc));return
        width=sum(g['advance'] for g in glyphs)
        x=body['x'] if position=='BOTTOM_LEFT' else body['x']+body['width']-width if position=='BOTTOM_RIGHT' else body['x']+(body['width']-width)/2
        line=dict(paragraphId=pi,lineIndex=0,textStart=0,textEnd=len(text),hwpTextStart=0,text=text,x=x,y=baseline-height*.85,
            width=width,naturalWidth=width,availableWidth=body['width'],height=height,baseline=baseline,
            lineBoxX=body['x'],lineBoxWidth=body['width'],pitch=height,glyphRuns=glyphs,
            story=dict(kind='pageNumber',region='footer',section=0,value=number),generated=True)
        for g in glyphs:
            g.update(origin=[x,baseline],color='#000000',underline=False,justifyAdvance=0);x+=g['advance']
            b=g['inkBounds'];g['inkBounds']=[b[0]+g['origin'][0],b[1]+baseline,b[2]+g['origin'][0],b[3]+baseline]
        if line['y']<body['y']+body['height'] or width>body['width']:
            reject('pageNum','page label exceeds reserved footer');return
        pg['lines'].append(line)
    scene['pageNumberPolicy']=dict(family=family,height=height,baseline='paper bottom minus bottom margin minus Windows font descent',position=position,format='DIGIT')

def signed32(n,k):
    value=integer(n,k)
    return value-(1<<32) if (1<<31)<=value<(1<<32) else value
def margins(n):return {k:integer(n,k) for k in ['left','right','top','bottom']}

def position_line(line, y, paper, scene):
    line=copy.deepcopy(line);line['y']+=y;line['baseline']+=y
    for g in line['glyphRuns']:
        g['origin'][1]+=y
        b=g['inkBounds'];g['inkBounds']=[b[0]+g['origin'][0],b[1]+g['origin'][1],b[2]+g['origin'][0],b[3]+g['origin'][1]]
        if g['glyphId'] and (min(g['inkBounds'][:2])<0 or g['inkBounds'][2]>paper['width'] or g['inkBounds'][3]>paper['height']):
            scene['errors'].append('glyph exceeds logical paper')
    return line

def border_style(root,ref,reject):
    el=next((n for h in root.headers for n in h.element.iter(HH+'borderFill') if n.get('id')==ref),None)
    if el is None:reject('borderFill','missing cell border style');return {}
    for name in ['slash','backSlash']:
        n=el.find(HH+name)
        if n is not None and n.get('type','NONE')!='NONE':reject('borderFill','diagonal borders')
    if any(el.get(k,'0')!='0' for k in ['threeD','shadow']):reject('borderFill','3D/shadow')
    if el.get('centerLine','NONE')!='NONE':reject('borderFill','center line')
    cell_fill(root,ref,reject)
    edges={}
    for name in ['left','right','top','bottom']:
        n=el.find(HH+name+'Border')
        if n is None:reject('borderFill','incomplete cell borders');continue
        if n.get('type') not in {'NONE','SOLID','DASH'}:reject('borderFill','border pattern not implemented');continue
        try:w=float(n.get('width','0 mm').split()[0])*7200/25.4
        except ValueError:reject('borderFill','invalid border width');continue
        edges[name]=dict(type=n.get('type'),width=w,color=n.get('color','#000000'))
    return edges

def cell_fill(root,ref,reject):
    """An opaque solid cell brush. Pattern/image/gradient policies remain explicit."""
    import re
    el=next((n for h in root.headers for n in h.element.iter(HH+'borderFill') if n.get('id')==ref),None)
    if el is None:return None
    fill=el.find(HC+'fillBrush')
    if fill is None:return None
    brush=fill.find(HC+'winBrush')
    if brush is None or len(fill)!=1:
        reject('borderFill','gradient/image fill not implemented');return None
    if brush.get('hatchStyle','NONE') not in {'NONE','none',''} or brush.get('hatchColor','none') not in {'NONE','none'}:
        reject('borderFill','pattern fill not implemented');return None
    if brush.get('alpha','0')!='0':reject('borderFill','transparent fill not implemented');return None
    color=brush.get('faceColor','none')
    if color in {'NONE','none'}:return None
    if not re.fullmatch(r'#[0-9A-Fa-f]{6}',color):reject('borderFill','invalid fill color');return None
    return color

def nested_cell_scene(sl,pi,r,c,root,measure,box,provider,data,paper,reject):
    from types import SimpleNamespace
    from lxml import etree as ET  # type: ignore[reportAttributeAccessIssue]  # incomplete lxml typing
    depth=getattr(root,'objectDepth',0)
    if data is None or paper is None or depth>=8:
        reject('tbl/tc','nested object context/depth limit');return [],[]
    section=ET.Element(root.sections[0].element.tag)
    for p in sl.findall(HP+'p'):section.append(copy.deepcopy(p))
    proxy=SimpleNamespace(headers=root.headers,sections=[SimpleNamespace(element=section)],char_property=root.char_property,objectDepth=depth+1)
    local=dict(pages=[],unsupported=[],errors=[])
    local_paper=dict(width=box['x']+box['width'],height=box['height'])
    paginate_objects(data,proxy,measure,box,local_paper,provider,local,lambda path,reason:local['unsupported'].append(dict(path=path,reason=reason)))
    for issue in local['unsupported']:reject('tbl/tc/'+issue['path'],issue['reason'])
    if local['unsupported']:return [],[]
    if len(local['pages'])!=1 or local['errors']:
        reject('tbl/tc','nested story requires recursive continuation');return [],[]
    lines=local['pages'][0]['lines'];objects=local['pages'][0]['objects']
    ancestor=dict(tableParagraph=pi,row=r,col=c)
    for line in lines:
        story=line['story']
        if story['kind']=='body':line['story']=dict(kind='cell',tableParagraph=pi,row=r,col=c,paragraph=story['paragraph'])
        else:line['story']=dict(story,ancestors=[ancestor]+story.get('ancestors',[]))
        for g in line['glyphRuns']:
            b=g['inkBounds'];x,y=g['origin'];g['inkBounds']=[b[0]-x,b[1]-y,b[2]-x,b[3]-y]
    for obj in objects:obj['ancestors']=[ancestor]+obj.get('ancestors',[])
    return lines,objects

def translated_object(obj,x,y):
    obj=copy.deepcopy(obj)
    obj['rect'][0]+=x;obj['rect'][1]+=y
    for c in obj.get('cells',[]):
        c['rect'][0]+=x;c['rect'][1]+=y
        c['textOrigin'][0]+=x;c['textOrigin'][1]+=y
    return obj

def table_model(table, pi, root, measure, body, provider, scene, reject,*,data=None,paper=None):
    pos=table.find(HP+'pos');sz=table.find(HP+'sz');outer=margins(table.find(HP+'outMargin'))
    if pos is None or sz is None:reject(f'p/{pi}/tbl','missing object size/anchor');return None
    if any(sz.get(k,'ABSOLUTE')!='ABSOLUTE' for k in ['widthRelTo','heightRelTo']):reject('tbl','relative size')
    if any(integer(pos,k) for k in ['horzOffset','vertOffset','allowOverlap']):reject('tbl','offset/overlapping table')
    if pos.get('treatAsChar') not in {'0','1'}:reject('tbl','invalid table placement')
    inline=pos.get('treatAsChar')=='1'
    if table.get('textWrap')!='TOP_AND_BOTTOM' or integer(table,'cellSpacing'):reject('tbl','wrap or cell spacing')
    if table.get('pageBreak','CELL') not in {'CELL','TABLE'}:reject('tbl','cell-content split not implemented')
    if pos.get('horzAlign','LEFT') not in {'LEFT','RIGHT'} or pos.get('vertAlign','TOP')!='TOP':reject('tbl','object alignment')
    if not inline and (pos.get('vertRelTo','PARA')!='PARA' or pos.get('horzRelTo','COLUMN') not in {'COLUMN','PARA'}):reject('tbl','anchor reference')
    nr=integer(table,'rowCnt');nc=integer(table,'colCnt');width=integer(sz,'width')
    extent=width if inline else width+outer['left']
    if nr<1 or nc<1 or nr*nc>10000 or width<=0 or extent>body['width']:reject('tbl','invalid/outside table geometry');return None
    columns: list[Any] = [None]*nc;cells=[];occupied=set();row_heights=[0]*nr
    for tr in table.findall(HP+'tr'):
        for tc in tr.findall(HP+'tc'):
            addr=tc.find(HP+'cellAddr');span=tc.find(HP+'cellSpan');csz=tc.find(HP+'cellSz');sl=tc.find(HP+'subList')
            if any(n is None for n in [addr,span,csz,sl]):reject('tbl/tc','incomplete cell');continue
            r=integer(addr,'rowAddr');c=integer(addr,'colAddr');rs=integer(span,'rowSpan',1);cols=integer(span,'colSpan',1)
            if not (0<=r<nr and 0<=c<nc and rs>=1 and cols>=1 and r+rs<=nr and c+cols<=nc):reject('tbl/tc','invalid span');continue
            coverage={(rr,cc) for rr in range(r,r+rs) for cc in range(c,c+cols)}
            if coverage & occupied:reject('tbl/tc','overlapping cell spans');continue
            occupied|=coverage
            w=integer(csz,'width');minimum=integer(csz,'height')
            if cols==1:
                if columns[c] is not None and columns[c]!=w:reject('tbl','inconsistent column widths')
                columns[c]=w
            cm=margins(tc.find(HP+'cellMargin') if tc.get('hasMargin')=='1' else table.find(HP+'inMargin'))
            if w<=sum(cm[k] for k in ['left','right']) or minimum<0:reject('tbl/tc','non-positive cell body');continue
            if sl.get('textDirection','HORIZONTAL')!='HORIZONTAL' or sl.get('lineWrap','BREAK')!='BREAK':reject('tbl/tc','cell text policy')
            if any(sl.get(k,'0') not in {'','0'} for k in ['linkListIDRef','linkListNextIDRef']):reject('tbl/tc','linked text')
            if any(sl.get(k,'0')!='0' for k in ['hasTextRef','hasNumRef']):reject('tbl/tc','referenced text/number')
            align=sl.get('vertAlign','TOP')
            if align not in {'TOP','CENTER','BOTTOM'}:reject('tbl/tc','vertical alignment')
            box=dict(x=cm['left'],y=0,width=w-cm['left']-cm['right'],height=body['height'])
            lines=[];y=0;pending=0;nested=[]
            has_nested=any(n.tag in {HP+'tbl',HP+'pic'} for n in sl.iter())
            if has_nested:
                box['height']-=cm['top']+cm['bottom']
                lines,nested=nested_cell_scene(sl,pi,r,c,root,measure,box,provider,data,paper,reject)
            for cp,p in enumerate([] if has_nested else sl.findall(HP+'p')):
                if p.get('pageBreak','0')!='0':reject('tbl/tc','explicit cell page break')
                prepared,shape=_prepare_paragraph(p,pi,root,measure,box,provider,reject,lambda:bool(scene['unsupported']))
                if prepared is None:continue
                y+=pending+shape.prev
                for li,l in enumerate(prepared):
                    l['y']=y;l['baseline']+=y
                    for g in l['glyphRuns']:g['origin'][1]+=y
                    l['paragraphBefore']=shape.prev if li==0 else 0
                    l['story']=dict(kind='cell',tableParagraph=pi,row=r,col=c,paragraph=cp)
                    lines.append(l);y+=l['pitch']
                pending=shape.next
            # Last paragraph ends at the em foot, excluding trailing line spacing.
            content=max([l['y']+l['height'] for l in lines]+[o['rect'][1]+o['rect'][3] for o in nested]+[0])
            needed=content+cm['top']+cm['bottom']
            if rs==1:row_heights[r]=max(row_heights[r],minimum,needed)
            cells.append(dict(row=r,col=c,rowSpan=rs,colSpan=cols,width=w,minimumHeight=minimum,requiredHeight=max(minimum,needed),margin=cm,
                              verticalAlignment=align,contentHeight=content,lines=lines,
                              borders=border_style(root,tc.get('borderFillIDRef',table.get('borderFillIDRef')),reject),
                              header=tc.get('header','0')=='1'))
            fill=cell_fill(root,tc.get('borderFillIDRef',table.get('borderFillIDRef')),reject)
            if fill is not None:cells[-1]['fill']=fill
            if nested:cells[-1]['objects']=nested
    if occupied!={(r,c) for r in range(nr) for c in range(nc)}:reject('tbl','incomplete table grid')
    if any(w is None for w in columns):reject('tbl','cannot determine column widths without guessing');return None
    if sum(columns)!=width:reject('tbl','table width disagrees with grid')
    for c in cells:
        if c['width']!=sum(columns[c['col']:c['col']+c['colSpan']]):reject('tbl','merged cell width disagrees with grid')
    for c in sorted(cells,key=lambda c:(c['row']+c['rowSpan'],c['row'])):
        r=c['row'];rs=c['rowSpan']
        if rs>1:row_heights[r+rs-1]+=max(0,c['requiredHeight']-sum(row_heights[r:r+rs]))
    repeat=table.get('repeatHeader','0')=='1'
    if repeat and not all(c['header'] for c in cells if c['row']==0):reject('tbl','only a complete first header row supported')
    if repeat and any(c['header'] for c in cells if c['row']>0):reject('tbl','multiple header rows')
    if repeat and any(c['row']==0 and c['rowSpan']>1 for c in cells):reject('tbl','header spanning body rows')
    model=dict(kind='table',paragraphId=pi,width=width,rows=row_heights,columns=columns,cells=cells,outer=outer,
                repeatHeader=repeat,pageBreak=table.get('pageBreak','CELL'),inline=pos.get('treatAsChar')=='1',
                rowBreakCut=_spare_cut(table))
    if not inline and pos.get('horzAlign')=='RIGHT':model['horizontalAlignment']='RIGHT'
    return model

def picture_model(pic,pi,data,body,provider,reject,*,paper=None):
    pos=pic.find(HP+'pos');sz=pic.find(HP+'sz');org=pic.find(HP+'orgSz');image=pic.find(HC+'img')
    if any(n is None for n in [pos,sz,org,image]):reject('pic','incomplete picture');return None
    width=integer(sz,'width');height=integer(sz,'height');outer=margins(pic.find(HP+'outMargin'))
    inline=pos.get('treatAsChar')=='1'
    if pic.get('textFlow','BOTH_SIDES') not in {'BOTH_SIDES','LEFT_ONLY','RIGHT_ONLY','LARGEST_ONLY'}:
        reject('pic','invalid picture text flow')
    if pos.get('treatAsChar') not in {'0','1'}:reject('pic','invalid placement')
    if not inline and (pic.get('textWrap') not in {'TOP_AND_BOTTOM','SQUARE'} or pos.get('flowWithText','1')!='1'):
        reject('pic','only flowing top-bottom or square pictures')
    if pos.get('vertRelTo','PARA')!='PARA' or pos.get('horzRelTo','COLUMN')!='COLUMN':reject('pic','anchor reference')
    if any(sz.get(k,'ABSOLUTE')!='ABSOLUTE' for k in ['widthRelTo','heightRelTo']):reject('pic','relative image size')
    if pic.get('href','') or pic.get('reverse','0')!='0':reject('pic','linked or reversed image')
    if integer(pos,'allowOverlap') or integer(pos,'horzOffset')<0 or integer(pos,'vertOffset')<0:reject('pic','overlap/negative offset')
    if inline and any(integer(pos,k) for k in ['horzOffset','vertOffset']):reject('pic','inline offset')
    if pos.get('horzAlign','LEFT')!='LEFT' or pos.get('vertAlign','TOP')!='TOP':reject('pic','object alignment')
    extent=width if inline else width+outer['left']+outer['right']+integer(pos,'horzOffset')
    bound=paper['width']-body['x']-outer['left'] if inline and paper else body['width']
    if width<=0 or height<=0 or extent>bound or height+outer['top']+outer['bottom']>=body['height']:reject('pic','outside picture geometry')
    for n in ['flip','rotationInfo']:
        el=pic.find(HP+n)
        keys={'flip':['horizontal','vertical'],'offset':['x','y'],'rotationInfo':['angle']}[n]
        if el is not None and any(integer(el,k) for k in keys):reject('pic','transform '+n)
    if any(image.get(k,'0')!='0' for k in ['bright','contrast','alpha']) or image.get('effect','REAL_PIC')!='REAL_PIC':reject('pic','image effects')
    effects=pic.find(HP+'effects')
    if effects is not None and len(effects):reject('pic','drawing effects')
    # Axis-aligned authored resize. Translation before/after scaling may
    # cancel (a Hancom saved picture's offset); reject a real displacement.
    matrices={name:pic.findall('.//'+HC+name) for name in ['transMatrix','scaMatrix','rotMatrix']}
    offset=pic.find(HP+'offset')
    if any(len(v)>1 for v in matrices.values()):reject('pic','multiple rendering transforms')
    values={name:[float(v[0].get('e'+str(k),'0')) for k in range(1,7)] if v else [1,0,0,0,1,0] for name,v in matrices.items()}
    trans,scale,rotation=[values[n] for n in ['transMatrix','scaMatrix','rotMatrix']]
    if rotation!=[1,0,0,0,1,0] or trans[0:2]!=[1,0] or trans[3:5]!=[0,1] or scale[1]!=0 or scale[3]!=0:
        reject('pic','rotation/shear rendering transform')
    ow,oh=integer(org,'width'),integer(org,'height')
    if ow<=0 or oh<=0:reject('pic','invalid original size')
    else:
        identity=scale==[1,0,0,0,1,0]
        resized=scale[0]>0 and scale[4]>0 and abs(scale[0]*ow-width)<=1 and abs(scale[4]*oh-height)<=1
        if not identity and not resized:reject('pic','rendering scale disagrees with authored size')
    if abs(trans[2]+scale[2])>1 or abs(trans[5]+scale[5])>1:
        reject('pic','displaced rendering transform')
    if offset is not None and (signed32(offset,'x')!=round(trans[2]) or signed32(offset,'y')!=round(trans[5])):
        reject('pic','offset disagrees with rendering translation')
    rect=pic.find(HP+'imgRect')
    points=None if rect is None else [[integer(rect.find(HC+'pt'+str(i)),k) for k in ['x','y']] for i in range(4)]
    if points!=[[0,0],[ow,0],[ow,oh],[0,oh]]:reject('pic','nonrectangular image mapping')
    clip=pic.find(HP+'imgClip')
    dimensions=pic.find(HP+'imgDim')
    dw,dh=(integer(dimensions,'dimwidth'),integer(dimensions,'dimheight')) if dimensions is not None else (ow,oh)
    crop=[integer(clip,k) for k in ['left','top','right','bottom']]
    if clip is None or not (dw>0 and dh>0 and 0<=crop[0]<crop[2]<=dw and 0<=crop[1]<crop[3]<=dh):reject('pic','invalid picture clip')
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        from lxml import etree as ET  # type: ignore[reportAttributeAccessIssue]  # incomplete lxml typing
        manifest=ET.fromstring(z.read('Contents/content.hpf'))
        items=[n for n in manifest.iter() if n.get('id')==image.get('binaryItemIDRef')]
        if len(items)!=1:reject('pic','ambiguous/missing binary reference');return None
        href=items[0].get('href','');href=href.removeprefix('../')
        if href not in z.namelist() or not href.startswith('BinData/'):reject('pic','external/missing image data');return None
        raw=z.read(href)
    # Raster decoding and limits belong to the draw backend; this prototype
    # accepts PNG bytes only and carries them by value, never a filesystem path.
    if not (raw.startswith(b'\x89PNG\r\n\x1a\n') or raw.startswith(b'\xff\xd8') or raw.startswith(b'BM')):reject('pic','only embedded PNG/JPEG/BMP implemented')
    try:
        dimensions=provider.inspect_picture(raw)
    except Exception as exc:
        reject('pic','picture decoder: '+str(exc));return None
    model: dict[str, Any] = dict(kind='picture',paragraphId=pi,width=width,height=height,outer=outer,
                inline=inline,textWrap=pic.get('textWrap'),textFlow=pic.get('textFlow','BOTH_SIDES'),
                rasterSize=dimensions,binarySha256=hashlib.sha256(raw).hexdigest(),pngBase64=base64.b64encode(raw).decode(),anchor=dict(pos.attrib))
    if clip is not None and [crop[0],crop[1],crop[2],crop[3]]!=[0,0,dw,dh]:
        model['cropNormalized']=[crop[0]/dw,crop[1]/dh,crop[2]/dw,crop[3]/dh]
        # Preserve the authored source canvas independently of page layout.
        # The draw adapter owns conversion from this canvas to source pixels.
        model['cropSourceCanvasHwpunit']=[dw,dh]
    return model

def paginate_objects(data,root,measure,body,paper,provider,scene,reject):
    scene['algorithmVersion']='object-scene-0.2';scene['sourceDerivedCellCachePolicy']='ignore subList textWidth/textHeight'
    blocks=[]
    paragraphs=[]
    from dataclasses import replace
    from lxml import etree as ET  # type: ignore[reportAttributeAccessIssue]  # incomplete lxml typing
    for pi,original in enumerate(root.sections[0].element.findall(HP+'p')):
        objects=[n for r in original.findall(HP+'run') for n in r if n.tag in {HP+'tbl',HP+'pic'}]
        text=any((n.text or '') or len(n) for r in original.findall(HP+'run') for n in r.findall(HP+'t'))
        if len(objects)<=1 and not (objects and text):
            paragraphs.append((pi,original,True,True,0));continue
        if any(n.find(HP+'pos') is None or n.find(HP+'pos').get('treatAsChar')!='1' for n in objects):
            reject(f'p/{pi}','mixed paragraphs require inline objects');continue
        # Bounded source-order path: every object is forced onto its own line
        # by authored width. Small objects sharing a text line require the
        # richer inline line-box path and must not be silently stacked.
        units=[];current=ET.Element(HP+'p',dict(original.attrib));offset=0
        for run in original.findall(HP+'run'):
            for child in run:
                if child.tag in {HP+'tbl',HP+'pic'}:
                    if any((n.text or '') or len(n) for n in current.iter(HP+'t')):
                        units.append((current,offset));offset+=sum(len(''.join(n.itertext())) for n in current.iter(HP+'t'))
                    current=ET.Element(HP+'p',dict(original.attrib))
                    p=ET.Element(HP+'p',dict(original.attrib));r=ET.SubElement(p,HP+'run',dict(run.attrib));r.append(copy.deepcopy(child))
                    units.append((p,offset));offset+=8
                elif child.tag==HP+'t':
                    r=ET.SubElement(current,HP+'run',dict(run.attrib));r.append(copy.deepcopy(child))
                else:reject(f'p/{pi}','additional controls in mixed paragraph')
        if any((n.text or '') or len(n) for n in current.iter(HP+'t')):units.append((current,offset))
        widths=[]
        for p,_ in units:
            obj=next((n for n in p.iter() if n.tag in {HP+'tbl',HP+'pic'}),None)
            if obj is not None:
                m=margins(obj.find(HP+'outMargin'));widths.append(integer(obj.find(HP+'sz'),'width')+m['left']+m['right'])
            else:
                lines,_=_prepare_paragraph(p,pi,root,measure,body,provider,reject,lambda:bool(scene['unsupported']))
                widths.append(lines[-1]['naturalWidth'] if lines else 0)
        if any(a+b<=body['width'] for a,b in zip(widths,widths[1:])):
            reject(f'p/{pi}','inline objects sharing a line not yet implemented');continue
        paragraphs.extend((pi,p,i==0,i==len(units)-1,start) for i,(p,start) in enumerate(units))
    for pi,p,first,last,start in paragraphs:
        objects=[n for r in p.findall(HP+'run') for n in r if n.tag in {HP+'tbl',HP+'pic'}]
        if objects:
            if len(objects)!=1 or any((n.text or '') or len(n) for r in p.findall(HP+'run') for n in r.findall(HP+'t')):
                reject(f'p/{pi}','only one object in an otherwise empty anchor paragraph');continue
            obj=objects[0]
            if obj.tag==HP+'tbl':model=table_model(obj,pi,root,measure,body,provider,scene,reject,data=data,paper=paper)
            else:model=picture_model(obj,pi,data,body,provider,reject,paper=paper)
            # Validate the anchor paragraph policy, rather than bypassing it.
            lines,shape=_prepare_paragraph(p,pi,root,measure,body,provider,reject,lambda:bool(scene['unsupported']))
            if shape.kind!='PERCENT':reject(f'p/{pi}','object anchor needs percent line spacing')
            prop=next(n for h in root.headers for n in h.element.iter(HH+'paraPr') if n.get('id')==p.get('paraPrIDRef','0'))
            align=prop.find(HH+'align')
            alignment=align.get('horizontal','LEFT') if align is not None else 'LEFT'
            if alignment not in {'LEFT','JUSTIFY','CENTER','RIGHT'}:reject(f'p/{pi}','unsupported object anchor alignment')
            if model is not None:
                if model['inline'] and alignment in {'CENTER','RIGHT'}:model['inlineHorizontalAlignment']=alignment
                if model['inline'] and (shape.left or shape.right or shape.indent):
                    model['inlineBoxX']=body['x']+shape.left+(max(shape.indent,0) if first else max(-shape.indent,0))
                    model['inlineBoxWidth']=lines[0]['availableWidth']
                elif not model['inline'] and objects[0].find(HP+'pos').get('horzRelTo')=='PARA' and (shape.left or shape.right):
                    model['paragraphAnchor']=dict(left=shape.left,right=shape.right)
                shape=replace(shape,prev=shape.prev if first else 0,next=shape.next if last else 0)
                model.update(shape=shape,lineGap=lines[0]['pitch']-lines[0]['height'] if lines else 0,
                             anchorLines=lines,paragraphElement=p,paragraphId=pi,pageBreakBefore=first and p.get('pageBreak')=='1')
                blocks.append(model)
        else:
            lines,shape=_prepare_paragraph(p,pi,root,measure,body,provider,reject,lambda:bool(scene['unsupported']))
            if lines is not None:
                if not first and shape.indent:reject(f'p/{pi}','mixed continuation paragraph indent not yet implemented')
                shape=replace(shape,prev=shape.prev if first else 0,next=shape.next if last else 0)
                for line in lines:line['hwpTextStart']+=start
                blocks.append(dict(kind='body',lines=lines,shape=shape,paragraphElement=p,paragraphId=pi,pageBreakBefore=first and p.get('pageBreak')=='1'))
    if scene['unsupported']:return
    def page():
        if len(scene['pages'])>=100:reject('pages','prototype limit 100 logical pages');return
        scene['pages'].append(dict(index=len(scene['pages']),size=paper.copy(),bodyRect=body.copy(),lines=[],objects=[]))
    page();y=0;pending=0;squares=[]
    def prepare_beside(block,y):
        current=[b for b in squares if b['page']==scene['pages'][-1]['index'] and b['bottom']>y]
        if not current:return block.get('lines',block.get('anchorLines'))
        if len(current)>1:reject('wrap','overlapping square bands not implemented');return []
        # Restricted monometric paragraph policy: line tops are known before
        # shaping. Multiple segments at one top preserve left-to-right order.
        p=block['paragraphElement'];h=measure.char_height(p.findall(HP+'run')[-1].get('charPrIDRef','0'))
        heights={measure.char_height(r.get('charPrIDRef','0')) for r in p.findall(HP+'run')}
        if len(heights)!=1 or block['shape'].kind!='PERCENT':reject('wrap','mixed height/fixed spacing beside picture');return []
        pitch=_pitch(block['shape'].kind,block['shape'].value,h);boxes=[];band=current[0]
        count=max(2,len(''.join(p.itertext()))+2)
        for row in range(count):
            top=y+row*pitch
            if top>=band['bottom'] or top+h<=band['top']:
                spans=[(body['x'],body['width'])]
            else:
                left=(body['x'],band['left']-body['x']);right=(band['right'],body['x']+body['width']-band['right'])
                flow=band['flow'];spans=[s for s in ([left,right] if flow=='BOTH_SIDES' else [left] if flow=='LEFT_ONLY' else [right] if flow=='RIGHT_ONLY' else [max([left,right],key=lambda s:s[1])]) if s[1]>=_MIN_SIDE]
                if not spans:reject('wrap','no side wide enough');return []
            boxes.extend(dict(x=x,width=w,y=row*pitch) for x,w in spans)
        lines,_=_prepare_paragraph(p,block['paragraphId'],root,measure,body,provider,reject,lambda:bool(scene['unsupported']),line_boxes=boxes)
        return lines or []
    def place_row(block,r,y,repeated=False,fragment=None):
        pg=scene['pages'][-1];h=block['rows'][r] if fragment is None else fragment['height'];x=body['x']+block['outer']['left']
        if block.get('horizontalAlignment')=='RIGHT':x=body['x']+body['width']-block['width']-block['outer']['right']
        anchor=block.get('paragraphAnchor',{})
        x+=anchor.get('left',0) if block.get('horizontalAlignment')!='RIGHT' else -anchor.get('right',0)
        if block['inline']:
            box_x=block.get('inlineBoxX',body['x']);box_w=block.get('inlineBoxWidth',body['width']);x=box_x+block['outer']['left']
            if block.get('inlineHorizontalAlignment')=='CENTER':x+=max(0,(box_w-block['width']-block['outer']['left']-block['outer']['right'])/2)
            elif block.get('inlineHorizontalAlignment')=='RIGHT':x+=max(0,box_w-block['width']-block['outer']['left']-block['outer']['right'])
        cells=[];nested=[]
        source_cells=[c for c in block['cells'] if c['row']==r] if fragment is None else fragment['cells']
        for c in source_cells:
            ch=sum(block['rows'][r:r+c['rowSpan']]) if fragment is None else c.get('fragmentHeight',h)
            cx=x+sum(block['columns'][:c['col']]);cm=c['margin'];free=ch-cm['top']-cm['bottom']-c['contentHeight']
            dy=cm['top']+(free/2 if c['verticalAlignment']=='CENTER' else free if c['verticalAlignment']=='BOTTOM' else 0)
            for line in c['lines']:
                line=copy.deepcopy(line);line['x']+=cx;line['lineBoxX']+=cx
                for g in line['glyphRuns']:g['origin'][0]+=cx
                line['repeatedHeader']=repeated
                positioned=position_line(line,body['y']+y+dy,paper,scene)
                # A visible cell glyph must fit inside its cell rectangle.
                for g in positioned['glyphRuns']:
                    if g['glyphId'] and (g['inkBounds'][0]<cx or g['inkBounds'][1]<body['y']+y or
                       g['inkBounds'][2]>cx+c['width'] or g['inkBounds'][3]>body['y']+y+ch):
                        scene['errors'].append('cell glyph clipping')
                pg['lines'].append(positioned)
            cells.append(dict(row=r,col=c['col'],rowSpan=c['rowSpan'],colSpan=c['colSpan'],rect=[cx,body['y']+y,c['width'],ch],
                              textOrigin=[cx+cm['left'],body['y']+y+dy],borders=c['borders']))
            if 'sourceRow' in c:cells[-1]['sourceRow']=c['sourceRow']
            if 'fill' in c:cells[-1]['fill']=c['fill']
            nested.extend(translated_object(o,cx,body['y']+y+dy) for o in c.get('objects',[]))
        pg['objects'].append(dict(kind='tableRow',paragraphId=block['paragraphId'],row=r,repeatedHeader=repeated,cells=cells,
                                  rect=[x,body['y']+y,block['width'],h]))
        if fragment is not None:
            pg['objects'][-1].update(fragmentIndex=fragment['index'],continues=fragment['continues'])
        pg['objects'].extend(nested)

    def cell_row(block,r,y):
        """Consume one CELL row using glyph-derived line continuations.

        Spare-height cut/drop rules are shared with pages._flow_row. Every
        cell retains its own unread lines; completed cells continue as empty
        rectangles, never replaying their text. Split borders are explicit.
        """
        cells=copy.deepcopy([c for c in block['cells'] if c['row']==r])
        height=block['rows'][r];index=0
        while True:
            foot=body['height']-block['outer']['bottom']-block['rowBreakCut']
            available=foot-y
            nested_height=max((c['contentHeight']+c['margin']['top']+c['margin']['bottom'] for c in cells if c.get('objects')),default=0)
            if nested_height>available:
                max_room=foot-block['outer']['top']-(block['rows'][0] if block['repeatHeader'] and r>0 else 0)
                if nested_height>max_room:reject('tbl/tc','nested story requires recursive continuation');return y
                page();y=block['outer']['top']
                if block['repeatHeader'] and r>0:place_row(block,0,y,repeated=True);y+=block['rows'][0]
                continue
            if available<=0:
                page();y=block['outer']['top']
                if block['repeatHeader'] and r>0:
                    place_row(block,0,y,repeated=True);y+=block['rows'][0]
                if scene['unsupported']:return y
                continue
            if height<=available:
                place_row(block,r,y,fragment=dict(height=height,cells=cells,index=index,continues=False))
                return y+height
            if any(c['rowSpan']!=1 for c in cells):
                reject('tbl','CELL vertical-merge fragmentation not yet validated');return y
            parts=[];rests=[];counts=[]
            for c in cells:
                cm=c['margin'];vertical=cm['top']+cm['bottom']
                fitting=[]
                for l in c['lines']:
                    if l['y']+l['height']+vertical>available:break
                    fitting.append(l)
                counts.append(len(fitting))
                part=copy.deepcopy(c);part['lines']=fitting
                part['contentHeight']=max((l['y']+l['height'] for l in fitting),default=0)
                parts.append(part)
                rest=copy.deepcopy(c);rest['lines']=rest['lines'][len(fitting):]
                if c.get('objects'):
                    part['contentHeight']=c['contentHeight']
                    rest.pop('objects',None)
                if rest['lines']:
                    shift=rest['lines'][0]['y']-rest['lines'][0].get('paragraphBefore',0)
                    for l in rest['lines']:
                        l['y']-=shift;l['baseline']-=shift
                        for g in l['glyphRuns']:g['origin'][1]-=shift
                rest['contentHeight']=max((l['y']+l['height'] for l in rest['lines']),default=0)
                rests.append(rest)
            if any(c['lines'] and count==0 for c,count in zip(cells,counts)):
                # All populated cells must fit their first line, including a
                # short neighbouring cell; otherwise move the row intact.
                if y==0 or (block['repeatHeader'] and y==block['rows'][0]+block['outer']['top']):
                    reject('tbl','CELL first line cannot fit below repeated header');return y
                page();y=block['outer']['top']
                if block['repeatHeader'] and r>0:
                    place_row(block,0,y,repeated=True);y+=block['rows'][0]
                if scene['unsupported']:return y
                continue
            content_height=max((c['contentHeight']+c['margin']['top']+c['margin']['bottom'] for c in cells),default=0)
            spare=height-content_height
            remaining_lines=any(c['lines'] for c in rests)
            if spare>0 or not remaining_lines:
                drawn_height=available
                rest_height=max(height-available,
                    max((c['contentHeight']+c['margin']['top']+c['margin']['bottom'] for c in rests if c['lines']),default=0))
                if not remaining_lines and rest_height<=_SPARE_DROPPED:rest_height=0
            else:
                # A new row's authored minimum still constrains its first
                # fragment. At the page foot it is clipped to available room;
                # the unread glyph lines retain their own continuation height.
                minimum=max(c['minimumHeight'] for c in cells) if index==0 else 0
                drawn_height=min(available,max(minimum,
                    max(c['contentHeight']+c['margin']['top']+c['margin']['bottom'] for c in parts)))
                rest_height=max(c['contentHeight']+c['margin']['top']+c['margin']['bottom'] for c in rests if c['lines'])
            for c,rest in zip(cells,rests):
                rest['minimumHeight']=max(0,c['minimumHeight']-drawn_height)
            if remaining_lines:
                rest_height=max(rest_height,max(c['minimumHeight'] for c in rests))
            place_row(block,r,y,fragment=dict(height=drawn_height,cells=parts,index=index,continues=rest_height>0))
            if not rest_height:return body['height']-block['outer']['bottom']
            page();y=block['outer']['top']
            if block['repeatHeader'] and r>0:
                place_row(block,0,y,repeated=True);y+=block['rows'][0]
            if scene['unsupported']:return y
            cells=rests;height=rest_height;index+=1

    def merged_cell_group(block,first,end,y):
        """Fragment a connected group of rows using independent cell states.

        Remaining single-row cells constrain their row first. Merged cell
        deficits then grow the last row they cover, in end-row order, as the
        authored grid model does. Source stories never change with visible row
        addresses, and completed cells retain their grid borders without text.
        """
        rows={r:block['rows'][r] for r in range(first,end)}
        cells=copy.deepcopy([c for c in block['cells'] if first<=c['row']<end])
        if any(c.get('objects') for c in cells):
            height=sum(block['rows'][first:end]);foot=body['height']-block['outer']['bottom']-block['rowBreakCut']
            repeat_height=block['rows'][0] if block['repeatHeader'] and first>0 else 0
            if height>foot-block['outer']['top']-repeat_height:
                reject('tbl/tc','merged nested story requires recursive continuation');return y
            if y+height>foot:
                page();y=block['outer']['top']
                if repeat_height:place_row(block,0,y,repeated=True);y+=repeat_height
            for rr in range(first,end):place_row(block,rr,y);y+=block['rows'][rr]
            return y
        for c in cells:c['sourceRow']=c['row']
        index=0
        while rows:
            foot=body['height']-block['outer']['bottom']-block['rowBreakCut']
            tops={};top=y
            for r,h in sorted(rows.items()):tops[r]=top;top+=h
            total=top-y
            if total<=foot-y:
                draw_rows=rows;draw_cells=cells;more=False;rest_rows={};rest_cells=[]
            else:
                if foot<=y:
                    page();y=block['outer']['top']
                    if block['repeatHeader'] and first>0:
                        place_row(block,0,y,repeated=True);y+=block['rows'][0]
                    if scene['unsupported']:return y
                    continue
                cut=next(r for r in sorted(rows) if tops[r]+rows[r]>foot)
                draw_rows={r:h for r,h in rows.items() if r<cut};draw_rows[cut]=0
                rest_rows={r:(0 if r==cut else h) for r,h in rows.items() if r>=cut}
                draw_cells=[];rest_cells=[];constraints=[];draw_constraints=[]
                for c in cells:
                    start=c['row'];last=start+c['rowSpan']-1
                    if start>cut:
                        rest_cells.append(copy.deepcopy(c));constraints.append((start,last,c['requiredHeight']));continue
                    available=foot-tops[start];cm=c['margin'];vertical=cm['top']+cm['bottom']
                    part=copy.deepcopy(c);rest=copy.deepcopy(c)
                    if last<cut:
                        draw_cells.append(part);continue
                    fitting=[]
                    for l in c['lines']:
                        if l['y']+l['height']+vertical>available:break
                        fitting.append(l)
                    part['lines']=fitting;part['contentHeight']=max((l['y']+l['height'] for l in fitting),default=0)
                    rest['lines']=rest['lines'][len(fitting):]
                    if rest['lines']:
                        shift=rest['lines'][0]['y']-rest['lines'][0].get('paragraphBefore',0)
                        for l in rest['lines']:
                            l['y']-=shift;l['baseline']-=shift
                            for g in l['glyphRuns']:g['origin'][1]-=shift
                    rest['contentHeight']=max((l['y']+l['height'] for l in rest['lines']),default=0)
                    if c['requiredHeight']<=available:
                        drawn=c['requiredHeight'];required=0
                    elif not fitting and c['lines']:
                        drawn=0;required=c['requiredHeight']
                    elif c['requiredHeight']>c['contentHeight']+vertical or not rest['lines']:
                        drawn=available;required=max(c['requiredHeight']-available,
                            rest['contentHeight']+vertical if rest['lines'] else 0)
                        if not rest['lines'] and required<=_SPARE_DROPPED:required=0
                    else:
                        drawn=min(available,max(c['minimumHeight'],part['contentHeight']+vertical))
                        required=max(rest['contentHeight']+vertical,c['minimumHeight']-drawn)
                    part['rowSpan']=min(last,cut)-start+1
                    draw_cells.append(part);draw_constraints.append((start,cut,drawn))
                    rest['minimumHeight']=max(0,c['minimumHeight']-drawn)
                    rest['requiredHeight']=required;rest['row']=max(start,cut);rest['rowSpan']=last-rest['row']+1
                    # Grid continuations remain even after all glyphs and
                    # authored height are consumed; they add no row constraint.
                    rest_cells.append(rest);constraints.append((rest['row'],last,required))
                for start,last,h in draw_constraints:
                    draw_rows[last]+=max(0,h-sum(draw_rows.get(r,0) for r in range(start,last+1)))
                cut_cells=[c for c in draw_cells if c['row']==cut]
                if cut_cells and not any(c['lines'] for c in cut_cells) and any(r<cut and h>0 for r,h in draw_rows.items()):
                    # A row whose first cell line cannot fit has not begun.
                    # Continue the preceding row's border to the merged band's
                    # foot instead of inserting an empty sliver of a new row.
                    previous=max(r for r,h in draw_rows.items() if r<cut and h>0)
                    draw_rows[previous]+=draw_rows.pop(cut)
                    draw_cells=[c for c in draw_cells if c['row']!=cut]
                for start,last,h in sorted(constraints,key=lambda a:(a[1]-a[0],a[1],a[0])):
                    if start==last:rest_rows[start]=max(rest_rows[start],h)
                for start,last,h in sorted(constraints,key=lambda a:(a[1],a[0])):
                    if start<last:rest_rows[last]+=max(0,h-sum(rest_rows.get(r,0) for r in range(start,last+1)))
                more=any(rest_rows.values())
                if not any(draw_rows.values()):
                    if y==block['outer']['top']+(block['rows'][0] if block['repeatHeader'] and first>0 else 0):
                        reject('tbl','merged CELL group cannot make progress');return y
                    page();y=block['outer']['top']
                    if block['repeatHeader'] and first>0:place_row(block,0,y,repeated=True);y+=block['rows'][0]
                    if scene['unsupported']:return y
                    continue
            # Collapse zero-height grid rows while keeping each source address.
            visible={r:h for r,h in draw_rows.items() if h>0}
            for c in draw_cells:
                last=min(c['row']+c['rowSpan']-1,max(visible))
                starts=[r for r in visible if c['row']<=r<=last]
                if not starts:continue
                c['row']=min(starts);c['rowSpan']=last-c['row']+1
                c['fragmentHeight']=sum(draw_rows.get(r,0) for r in range(c['row'],last+1))
            for r,h in sorted(visible.items()):
                own=[c for c in draw_cells if c['row']==r and c.get('fragmentHeight',0)>0]
                place_row(block,r,y,fragment=dict(height=h,cells=own,index=index,continues=more));y+=h
            if not more:return y if total<=foot-tops[min(tops)] else body['height']-block['outer']['bottom']
            cells=rest_cells;rows={r:h for r,h in rest_rows.items() if h>0}
            normalized=[]
            for c in cells:
                last=c['row']+c['rowSpan']-1;starts=[r for r in rows if c['row']<=r<=last]
                if not starts:continue
                c['row']=min(starts);c['rowSpan']=last-c['row']+1;normalized.append(c)
            cells=normalized
            page();y=block['outer']['top']
            if block['repeatHeader'] and first>0:place_row(block,0,y,repeated=True);y+=block['rows'][0]
            if scene['unsupported']:return y
            index+=1
    for block in blocks:
        shape=block['shape']
        if block['pageBreakBefore'] and (scene['pages'][-1]['lines'] or scene['pages'][-1]['objects']):page();y=0;pending=0
        y+=pending+shape.prev
        if block['kind']!='body' and any(b['page']==scene['pages'][-1]['index'] and b['bottom']>y for b in squares):
            reject('wrap','another object beside an active picture is not implemented');continue
        if block['kind']=='body':
            lines=prepare_beside(block,y)
            if not lines:continue
            height=lines[-1].get('relativeY',sum(l['pitch'] for l in lines[:-1]))+lines[-1]['height']
            if shape.flags.get('keepLines') in {'1','true'} and y+height>=body['height'] and height<body['height']:page();y=shape.prev
            base=y
            for line in lines:
                if 'relativeY' in line:y=base+line['relativeY']
                if y+line['height']>=body['height'] and scene['pages'][-1]['lines']:page();y=0;base=-line.get('relativeY',0)
                line=copy.deepcopy(line);line['story']=dict(kind='body',paragraph=line['paragraphId'])
                scene['pages'][-1]['lines'].append(position_line(line,body['y']+y,paper,scene));y+=line['pitch']
        elif block['kind']=='table':
            outer=block['outer'];y+=outer['top']
            total=sum(block['rows'])
            if block['inline']:
                if total>=body['height']:reject('tbl','inline table taller than body; requires floating table fragmentation');continue
                if y+total>=body['height']:page();y=outer['top']
                for r,h in enumerate(block['rows']):place_row(block,r,y);y+=h
                y+=outer['bottom']+block['lineGap']
            else:
                if block['pageBreak']=='CELL':
                    if block['repeatHeader'] and block['rows'][0]>=body['height']-block['rowBreakCut']:
                        reject('tbl','CELL repeated header leaves no room');continue
                    r=0
                    while r<len(block['rows']):
                        end=r+1
                        while True:
                            extended=max([end]+[c['row']+c['rowSpan'] for c in block['cells'] if r<=c['row']<end])
                            if extended==end:break
                            end=extended
                        y=merged_cell_group(block,r,end,y) if end>r+1 else cell_row(block,r,y)
                        if scene['unsupported']:break
                        r=end
                    y+=outer['bottom'];continue
                if any(h>body['height']-block['rowBreakCut'] for h in block['rows']):reject('tbl','row taller than page requires cell-content splitting');continue
                r=0
                while r<len(block['rows']):
                    end=r+1
                    while True:
                        extended=max([end]+[c['row']+c['rowSpan'] for c in block['cells'] if r<=c['row']<end])
                        if extended==end:break
                        end=extended
                    groupHeight=sum(block['rows'][r:end])
                    if groupHeight>body['height']-block['rowBreakCut']:reject('tbl','merged group taller than page');break
                    if y+groupHeight>body['height']-block['rowBreakCut']:
                        page();y=0
                        if block['repeatHeader'] and r>0:
                            place_row(block,0,y,repeated=True);y+=block['rows'][0]
                            if y+groupHeight>body['height']-block['rowBreakCut']:reject('tbl','header leaves insufficient room');break
                    for rr in range(r,end):place_row(block,rr,y);y+=block['rows'][rr]
                    r=end
                y+=outer['bottom']
        else:
            outer=block['outer'];h=block['height']+outer['top']+outer['bottom']
            if y+h>=body['height']:page();y=0
            obj={k:copy.deepcopy(v) for k,v in block.items() if k not in {'shape','pageBreakBefore','lineGap','paragraphElement','anchorLines'}}
            x=body['x']+outer['left'];top=y+outer['top']
            if block['inline']:
                box_x=block.get('inlineBoxX',body['x']);box_w=block.get('inlineBoxWidth',body['width']);x=box_x+outer['left']
                if block.get('inlineHorizontalAlignment')=='CENTER':x+=max(0,(box_w-block['width']-outer['left']-outer['right'])/2)
                elif block.get('inlineHorizontalAlignment')=='RIGHT':x+=max(0,box_w-block['width']-outer['left']-outer['right'])
            if not block['inline']:
                x+=integer(block['anchor'],'horzOffset');top+=integer(block['anchor'],'vertOffset')
                if top+block['height']+outer['bottom']>=body['height']:page();y=0;top=outer['top']
            obj['rect']=[x,body['y']+top,block['width'],block['height']]
            scene['pages'][-1]['objects'].append(obj)
            if block['inline']:y+=h+block['lineGap']
            elif block['textWrap']=='TOP_AND_BOTTOM':
                # A flowing picture excludes its band from subsequent text;
                # its empty anchor remains at the paragraph start and does not
                # consume a second line after the excluded band.
                for line in block['anchorLines']:
                    line=copy.deepcopy(line);line['story']=dict(kind='body',paragraph=block['paragraphId'])
                    scene['pages'][-1]['lines'].append(position_line(line,body['y']+y,paper,scene))
                y=max(y+sum(l['pitch'] for l in block['anchorLines']),top+block['height']+outer['bottom'])
            else:
                squares.append(dict(page=scene['pages'][-1]['index'],left=x-outer['left'],right=x+block['width']+outer['right'],
                                    top=top-outer['top'],bottom=top+block['height']+outer['bottom'],flow=block['textFlow']))
                lines=prepare_beside(block,y);base=y
                for line in lines:
                    line=copy.deepcopy(line);line['story']=dict(kind='body',paragraph=block['paragraphId'])
                    ly=base+line.get('relativeY',0);scene['pages'][-1]['lines'].append(position_line(line,body['y']+ly,paper,scene));y=ly+line['pitch']
        pending=shape.next
