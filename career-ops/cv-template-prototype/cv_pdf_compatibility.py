"""Serialize completed flow layout with Unicode CID fonts for ATS uploads.
No content generation or reflow: preserve every rendered character origin.
"""
import pathlib,re
import pymupdf as fitz

def normalize(pdf,fonts):
    pdf=pathlib.Path(pdf);source=fitz.open(pdf);out=fitz.open()
    if len(source)!=1:raise ValueError('single-page CV required')
    page=out.new_page(width=source[0].rect.width,height=source[0].rect.height)
    source_chars=set(source[0].get_text())-set('\n\r')
    font_objects={}
    for style,filename in fonts.items():
        path=pathlib.Path('C:/Windows/Fonts')/filename
        page.insert_font(fontname='cv'+style,fontfile=str(path))
        font_objects[style]=fitz.Font(fontfile=str(path))
    shape=page.new_shape()
    for drawing in source[0].get_drawings():
        for item in drawing['items']:
            if item[0]=='l':shape.draw_line(item[1],item[2])
        shape.finish(color=drawing['color'],width=drawing['width'])
    for block in source[0].get_text('rawdict')['blocks']:
        for line in block.get('lines',[]):
            for span in line['spans']:
                style='bold_italic' if 'BoldItal' in span['font'] else 'bold' if 'Bold' in span['font'] else 'italic' if 'Ital' in span['font'] else 'normal'
                for char in span['chars']:
                    shape.insert_text(char['origin'],char['c'],fontname='cv'+style,fontsize=span['size'])
    shape.commit()
    for entry in page.get_fonts():
        style=entry[4].removeprefix('cv');font=font_objects[style]
        pairs={font.has_glyph(ord(c)):ord(c) for c in source_chars};pairs.pop(0,None)
        cmap='/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n/CMapName /CVUnicode def\n/CMapType 2 def\n1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n'+str(len(pairs))+' beginbfchar\n'+''.join('<%04x> <%04x>\n'%(g,u) for g,u in pairs.items())+'endbfchar\nendcmap\nCMapName currentdict /CMap defineresource pop\nend\nend'
        ref=int(out.xref_get_key(entry[0],'ToUnicode')[1].split()[0]);out.update_stream(ref,cmap.encode())
    out.set_metadata({'title':'Mukund Didwania CV','author':'Mukund Didwania'})
    temporary=pdf.with_suffix('.unicode.pdf');out.save(temporary,garbage=4,deflate=True,no_new_id=True)
    out.close();source.close();temporary.replace(pdf)
