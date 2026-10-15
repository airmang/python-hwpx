"""Experimental cache-blind single-column body scene. No oracle dependency.

GlyphProvider is the native/WASM portability seam; this module owns HWPX
semantics and Hancom layout policy. Unsupported documents produce no pages.
"""
from __future__ import annotations
import hashlib
import io
import json
import copy
from collections import OrderedDict
from typing import Any, Protocol
from hwpx import HwpxDocument
from .pages import HP, HH, _Measure, _pitch, _line_widths, _t_text
from ..form_fit.measure import hancom_line_starts

VERSION = 'body-scene-0.3'

class GlyphProvider(Protocol):
    def shape(self, text: str, attributes: dict, style: object) -> list[dict]: ...
    def manifest(self) -> dict: ...

def digest(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

class BodySceneSession:
    """Incremental paragraph reflow with full downstream pagination.

    Cached values contain only our own unpositioned paragraph measurements.
    A session owns one immutable glyph provider. Header or paper changes
    invalidate all entries; paragraph edits invalidate their content keys.
    Returned scenes are deep copies and cannot corrupt later renders.
    """
    def __init__(self, provider: GlyphProvider, *, max_paragraphs=256):
        if max_paragraphs < 1:
            raise ValueError('max_paragraphs must be positive')
        self.provider = provider
        self.max_paragraphs = max_paragraphs
        self._entries: OrderedDict[str, Any] = OrderedDict()
        self._environment = None

    def clear(self):
        self._entries.clear()
        self._environment = None

    def render(self, data: bytes, *, cache_mode='ignore', inject_test_cache=False):
        if getattr(self, '_bound_provider', self.provider) is not self.provider:
            self.clear()
        self._bound_provider = self.provider
        return build_body_scene(data, self.provider, cache_mode=cache_mode,
                                inject_test_cache=inject_test_cache, _paragraph_cache=self)

    def _begin(self, environment):
        invalidated = environment != self._environment
        if invalidated:
            self._entries.clear()
            self._environment = environment
        self._stats: dict[str, Any] = dict(mode='incremental_paragraphs_full_pagination',
                           environmentInvalidated=invalidated,
                           paragraphsRecomputed=0, paragraphsReused=0,
                           sourceLayoutCacheUsed=False)

    def _get(self, key):
        if key not in self._entries:
            self._stats['paragraphsRecomputed'] += 1
            return None
        self._stats['paragraphsReused'] += 1
        self._entries.move_to_end(key)
        return copy.deepcopy(self._entries[key])

    def _put(self, key, value):
        self._entries[key] = copy.deepcopy(value)
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_paragraphs:
            self._entries.popitem(last=False)

def build_body_scene(data: bytes, provider: GlyphProvider, *, cache_mode='ignore', inject_test_cache=False, _paragraph_cache=None, _object_layout: bool | None=False) -> dict:
    from lxml import etree  # type: ignore[reportAttributeAccessIssue]  # incomplete lxml typing
    if cache_mode not in {'ignore','remove','poison'}: raise ValueError('unknown cache test mode')
    d = HwpxDocument.open(io.BytesIO(data))  # core OPC/XML guards
    root: Any = d.oxml
    if _object_layout is None:
        # Detect scene controls only after the normal OPC/XML guards, using the
        # already parsed tree rather than holding a second document in memory.
        _object_layout = any(node.tag in {HP+'tbl', HP+'pic', HP+'header', HP+'pageNum'}
                             for section in root.sections for node in section.element.iter())
    removed = 0
    if inject_test_cache:
        for section in root.sections:
            for pi,p in enumerate(section.element.findall(HP+'p')):
                a=etree.SubElement(p,HP+'linesegarray')
                etree.SubElement(a,HP+'lineseg',dict(textpos='0',vertpos=str(pi*1600),vertsize='1000',textheight='1000',
                                  baseline='850',spacing='600',horzpos='0',horzsize='48188',flags='393216'))
    # Boundary: never read cache attributes. Mutation here is only an in-memory
    # metamorphic fixture. Every mode drops these subtrees before measurement.
    for section in root.sections:
        for node in list(section.element.iter(HP+'linesegarray')):
            if cache_mode == 'poison':
                for seg in node:
                    seg.attrib.update(dict(textpos='7', horzsize='48190', horzpos='1500',
                                      vertpos='3200', vertsize='1600', baseline='1250',
                                      textheight='1600', spacing='600'))
            removed += 1
            node.getparent().remove(node)
        if _object_layout:
            for node in section.element.iter(HP+'subList'):
                for key in ['textWidth','textHeight']:
                    node.attrib.pop(key,None)
    scene: dict[str, Any] = dict(schemaVersion=1, algorithmVersion=VERSION, unit='HWPUNIT',
                 inputSha256=hashlib.sha256(data).hexdigest(), sourceCachePolicy='ignore',
                 cacheInputReads=0, cacheArraysExcluded=removed, status='supported',
                 unsupported=[], pages=[], offsetUnit='Python codepoint; hwpTextStart UTF16/control units',
                 substitutions=[], errors=[])
    scene['qualityValidated']=False
    scene['cacheInstrumentation']='source layout subtrees excluded before semantic measurement; no cache field getter exposed'
    def reject(path, reason): scene['unsupported'].append(dict(path=path, reason=reason))
    if len(root.sections) != 1: reject('sections', 'single section only')
    allowed = {'sec','p','run','t','lineBreak','fwSpace','secPr','ctrl','colPr','pagePr','margin',
               'startNum','visibility','grid','footNotePr','endNotePr','autoNumFormat',
               'noteLine','noteSpacing','numbering','placement','pageBorderFill','offset',
               'masterPage','parameters','stringParam','integerParam','lineNumberShape'}
    if _object_layout:
        from .object_scene import OBJECT_ELEMENTS
        allowed |= OBJECT_ELEMENTS | {'header','pageNum'}
    # Section defaults are declarative, not visible footnote/header content.
    for si, section in enumerate(root.sections):
        for el in section.element.iter():
            local = el.tag.rsplit('}',1)[-1]
            if local not in allowed: reject(f'section/{si}/{local}', 'element outside body slice')
            if local == 'lineNumberShape' and el.get('restartType','0') != '0': reject(f'section/{si}/lineNumberShape','active line numbers')
            if local == 'secPr' and el.get('textDirection','HORIZONTAL') != 'HORIZONTAL': reject(f'section/{si}/secPr','vertical text')
            if local == 'grid' and any(el.get(k,'0')!='0' for k in ['lineGrid','charGrid','wonggojiFormat']): reject(f'section/{si}/grid','active grid')
        for col in section.element.iter(HP+'colPr'):
            if col.get('colCount','1') != '1': reject(f'section/{si}/colPr', 'multiple columns')
    semantic = [etree.tostring(h.element).decode() for h in root.headers] + [etree.tostring(s.element).decode() for s in root.sections]
    scene['semanticSha256'] = digest(semantic)
    if scene['unsupported']:
        scene.update(status='unsupported', **provider.manifest()); return scene
    measure = _Measure(root)
    sec = root.sections[0]
    pagepr = next(sec.element.iter(HP+'pagePr'), None)
    if pagepr is None: reject('pagePr', 'missing paper geometry')
    else:
        margin = pagepr.find(HP+'margin')
        if margin is None:
            reject('pagePr/margin', 'missing page margins')
            scene.update(status='unsupported', **provider.manifest())
            return scene
        paper = {k:int(pagepr.get(k,0)) for k in ['width','height']}
        margins = {k:int(margin.get(k,0)) for k in ['left','right','top','bottom','header','footer','gutter']}
        if paper['width'] != 59528 or paper['height'] not in {84186,84188} or margins['gutter'] or pagepr.get('landscape','WIDELY') not in {'WIDELY','PORTRAIT','0'}:
            reject('pagePr', 'slice requires portrait A4 with zero gutter')
    if scene['unsupported']:
        scene.update(status='unsupported', **provider.manifest()); return scene
    body = dict(x=margins['left'],y=margins['top']+margins['header'],width=paper['width']-margins['left']-margins['right'],
                height=paper['height']-sum(margins[k] for k in ['top','bottom','header','footer']))
    if _object_layout:
        from .object_scene import paginate_objects,render_headers,render_page_numbers
        paginate_objects(data, root, measure, body, paper, provider, scene, reject)
        if not scene['unsupported'] and not scene['errors']:
            render_headers(data,root,measure,body,paper,margins,provider,scene,reject)
            if not scene['unsupported']:render_page_numbers(root,body,paper,margins,provider,scene,reject)
        if scene['unsupported']: scene['status']='unsupported'; scene['pages']=[]
        elif scene['errors']: scene['status']='failed'; scene['pages']=[]
        scene.update(provider.manifest())
        scene['layoutSha256']=digest(scene['pages'])
        return scene
    def page():
        scene['pages'].append(dict(index=len(scene['pages']),size=paper.copy(),bodyRect=body.copy(),lines=[]))
    page(); y=0; pending=0
    if _paragraph_cache is not None:
        _paragraph_cache._begin(digest(dict(version=VERSION, body=body, paper=paper,
            headers=[etree.tostring(h.element).decode() for h in root.headers])))
    for pi, paragraph in enumerate(sec.element.findall(HP+'p')):
        key = hashlib.sha256(etree.tostring(paragraph)).hexdigest()
        cached = _paragraph_cache._get(key) if _paragraph_cache is not None else None
        if cached is None:
            prepared, shape = _prepare_paragraph(paragraph, pi, root, measure, body, provider,
                                                  reject, lambda: bool(scene['unsupported']))
            if scene['unsupported']: continue
            if _paragraph_cache is not None: _paragraph_cache._put(key, (prepared, shape))
        else:
            prepared, shape = cached
        for line in prepared: line['paragraphId'] = pi
        if paragraph.get('pageBreak')=='1' and scene['pages'][-1]['lines']: page(); y=0; pending=0
        y+=pending+shape.prev
        block=sum(l['pitch'] for l in prepared[:-1])+prepared[-1]['height']
        if shape.flags.get('keepLines') in {'1','true'} and y+block>=body['height'] and block<body['height']:
            page(); y=shape.prev
        for line in prepared:
            if y+line['height']>=body['height'] and scene['pages'][-1]['lines']: page(); y=0
            line['y']=body['y']+y; line['baseline']+=line['y']
            for g in line['glyphRuns']:
                g['origin'][1]+=line['y']
                b=g['inkBounds']; g['inkBounds']=[b[0]+g['origin'][0],b[1]+g['origin'][1],b[2]+g['origin'][0],b[3]+g['origin'][1]]
                if g['glyphId'] and (g['inkBounds'][0]<0 or g['inkBounds'][1]<0 or g['inkBounds'][2]>paper['width'] or g['inkBounds'][3]>paper['height']): scene['errors'].append(f'p{pi} clipped glyph')
            scene['pages'][-1]['lines'].append(line); y+=line['pitch']
        pending=shape.next
    if scene['unsupported']: scene['status']='unsupported'; scene['pages']=[]
    elif len(scene['pages'])>2: reject('pages','more than two logical pages'); scene['status']='unsupported'; scene['pages']=[]
    elif scene['errors']: scene['status']='failed'
    scene.update(provider.manifest())
    scene['layoutSha256']=digest(scene['pages'])
    if _paragraph_cache is not None: scene['incremental'] = _paragraph_cache._stats.copy()
    return scene

def _prepare_paragraph(paragraph, pi, root, measure, body, provider, reject, rejected, *, line_boxes=None):
    pr = paragraph.get('paraPrIDRef','0'); shape=measure.shape(pr)
    prop=next(h for h in measure._header.iter(HH+'paraPr') if h.get('id') == pr)
    align=prop.find(HH+'align'); alignment=align.get('horizontal','LEFT') if align is not None else 'LEFT'
    if alignment not in {'LEFT','RIGHT','CENTER','JUSTIFY'}: reject(f'p/{pi}', f'alignment {alignment}')
    if measure.numbered(pr) or measure.headed(paragraph): reject(f'p/{pi}', 'numbering/bullet')
    if prop.get('textDir','LTR') != 'LTR': reject(f'p/{pi}', 'non-LTR')
    if any(shape.flags.get(k) in {'1','true'} for k in ['keepWithNext','widowOrphan','pageBreakBefore']):
        reject(f'p/{pi}', 'keepWithNext/widowOrphan/pageBreakBefore not implemented')
    if shape.font_line: reject(f'p/{pi}', 'fontLineHeight requires separate font metrics calibration')
    chars=[]; text=''; empty_end=1000; hwp_offset=0; hwp_positions=[]; control_height=0
    for ri,run in enumerate(paragraph.findall(HP+'run')):
        ref=run.get('charPrIDRef','0'); char=root.char_property(ref)
        attrs: dict[str, Any] = dict(char.attributes) if char is not None else {'height':'1000'}
        el=next(e for e in measure._header.iter(HH+'charPr') if e.get('id')==ref)
        if el.get('useKerning','0') in {'1','true'}: reject(f'p/{pi}/run/{ri}', 'requested kerning outside feature-off slice')
        for name in ['strikeout','outline','shadow','emboss','engrave','supscript','subscript']:
            effect=el.find(HH+name)
            if effect is not None and effect.get('type','NONE') != 'NONE': reject(f'p/{pi}/run/{ri}', 'unsupported character effect '+name)
        attrs.update(bold=el.find(HH+'bold') is not None, italic=el.find(HH+'italic') is not None,
                     underline=el.find(HH+'underline').get('type','NONE') != 'NONE' if el.find(HH+'underline') is not None else False)
        style=measure.style(pr,[ref]); attrs['height']=measure.char_height(ref)
        empty_end=attrs['height']
        if style.scripts and any((r,s)!=(style.ratio,style.spacing) for _,r,s in style.scripts):
            reject(f'p/{pi}/run/{ri}', 'separate script scaling not implemented')
        for child in run:
            if child.tag == HP+'secPr' or child.tag == HP+'ctrl':
                hwp_offset+=8; control_height=max(control_height,attrs['height'])
            elif child.tag == HP+'t':
                part=_t_text(child)
                fixed_spaces=set();cursor=len(child.text or '')
                for inline_child in child:
                    if inline_child.tag==HP+'fwSpace':fixed_spaces.add(cursor)
                    cursor+=1+len(inline_child.tail or '')
                if any(not (32<=ord(c)<127 or 0xAC00<=ord(c)<=0xD7A3 or c in '\n“”‘’·—…\u3000') for c in part):
                    reject(f'p/{pi}/run/{ri}', 'character outside modern Hangul/ASCII/punctuation')
                try: glyphs=provider.shape(part,attrs,style)
                except Exception as exc:
                    reject(f'p/{pi}/run/{ri}', str(exc)); glyphs=[]
                if len(glyphs)!=len(part): reject(f'p/{pi}/run/{ri}', 'non-one-codepoint cluster (not supported)')
                for gi,(c,g) in enumerate(zip(part,glyphs)):
                    if gi in fixed_spaces:
                        # A tagged Hancom fixed-width blank is a quarter em,
                        # independent of font advance, ratio and tracking.
                        g.update(glyphId=0,advance=attrs['height']/4,spacingAdvance=0,
                                 rawAdvance=attrs['height']/4,inkBounds=[0,0,0,0])
                    hwp_positions.append(hwp_offset); hwp_offset+=1
                    chars.append(dict(glyph=g,attributes=attrs,style=style,runId=ri,fixedSpace=gi in fixed_spaces)); text+=c
    if rejected(): return None, shape
    pstyle=measure.style(pr,[r.get('charPrIDRef','0') for r in paragraph.findall(HP+'run')] or ['0'])
    widths=_line_widths(shape,body['width'],pstyle)
    if line_boxes is not None:
        widths=[b['width']-shape.left-shape.right for b in line_boxes]
        if shape.indent or '\n' in text:reject(f'p/{pi}','wrapped object slice excludes indent and explicit line break')
    starts=[]; base=0
    layout_text=''.join('\ufdd0' if c=='\u3000' and not chars[i]['fixedSpace'] else c for i,c in enumerate(text))
    for part in layout_text.split('\n'):
        span=chars[base:base+len(part)]
        advances={i:c['glyph']['advance'] for i,c in enumerate(span)}
        starts += [base+s for s in hancom_line_starts(part,widths,empty_end/100,pstyle,
                     [c['attributes']['height']/100 for c in span], [c['style'] for c in span], advances)]
        base+=len(part)+1
    prepared=[]
    for li,(start,stop) in enumerate(zip(starts,starts[1:]+[len(text)])):
        end=stop-1 if stop>start and text[stop-1]=='\n' else stop
        span=chars[start:end]; height=max([c['attributes']['height'] for c in span]+[empty_end if stop==len(text) else 0,control_height if start==0 else 0]) or empty_end
        if shape.font_line:
            height=max([measure.font_line(c['attributes']['height'],c['style']) for c in span]+[measure.font_line(empty_end,pstyle)])
        pitch=_pitch(shape.kind,shape.value,height)
        baseline=height*0.85  # explicit prototype hypothesis; comparator must judge
        room=widths[min(li,len(widths)-1)] if line_boxes is not None else widths[min(li,1)]
        visible=len(text[start:end].rstrip(' '))
        total=sum(c['glyph']['advance'] for c in span[:visible])
        if visible: total-=span[visible-1]['glyph']['spacingAdvance']
        natural=total; offset=0; extras={}
        if alignment=='RIGHT': offset=room-total
        elif alignment=='CENTER': offset=(room-total)/2
        elif alignment=='JUSTIFY' and stop<len(text) and (end==stop):
            def hangul(c): return 0xAC00<=ord(c)<=0xD7A3
            # Word spaces absorb expansion first. With no word spaces,
            # use inter-character opportunities in the restricted slice.
            slots=[i for i in range(max(0,visible-1)) if text[start+i]==' ']
            if not slots:
                slots=[i for i in range(max(0,visible-1)) if
                       hangul(text[start+i]) or hangul(text[start+i+1])]
            if not slots: slots=list(range(max(0,visible-1)))
            if slots:
                # Expansion is quantized per opportunity in HWPUNIT;
                # spreading the fractional remainder accumulates drift.
                expansion=(room-total)//len(slots)
                extras={i:expansion for i in slots}
                total+=expansion*len(slots)
        x=body['x']+shape.left+(max(shape.indent,0) if li==0 else max(-shape.indent,0))+offset
        if line_boxes is not None:x=line_boxes[min(li,len(line_boxes)-1)]['x']+shape.left+offset
        glyphs=[]; gx=x
        for ci,c in enumerate(span):
            g=copy.deepcopy(c['glyph']); g.update(clusterStart=start+ci,clusterEnd=start+ci+1,runId=c['runId'],
                 origin=[gx,baseline],color=c['attributes'].get('textColor','#000000'),underline=c['attributes']['underline'])
            g['advance']-=g['spacingAdvance'] if ci==len(span)-1 else 0
            g['justifyAdvance']=extras.get(ci,0)
            gx+=g['advance']+g['justifyAdvance']; glyphs.append(g)
        prepared.append(dict(paragraphId=pi,lineIndex=li,textStart=start,textEnd=end,
             hwpTextStart=0 if start==0 else hwp_positions[start],text=text[start:end],
             x=x,y=0,width=total,naturalWidth=natural,availableWidth=room,height=height,baseline=baseline,
             lineBoxX=(line_boxes[min(li,len(line_boxes)-1)]['x'] if line_boxes is not None else body['x'])+shape.left,
             lineBoxWidth=room if line_boxes is not None else body['width']-shape.left-shape.right,
             pitch=pitch,glyphRuns=glyphs))
        if line_boxes is not None:prepared[-1]['relativeY']=line_boxes[min(li,len(line_boxes)-1)]['y']
    return prepared, shape
