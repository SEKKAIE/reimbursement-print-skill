"""Copy the native-calibrated print geometry, not cell content, to a filled export."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import argparse
import copy
import xml.etree.ElementTree as ET

ap=argparse.ArgumentParser()
ap.add_argument('--master',required=True)
ap.add_argument('--filled',required=True)
ap.add_argument('--active-sheet',type=int,choices=[0,1,2,3],default=0)
a=ap.parse_args()
master,filled=Path(a.master),Path(a.filled)
N='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
q=lambda tag:f'{{{N}}}{tag}'
ET.register_namespace('',N)
with ZipFile(master) as z: original={n:z.read(n) for n in z.namelist()}
with ZipFile(filled) as z: data={n:z.read(n) for n in z.namelist()}
for idx in range(1,4):
    key=f'xl/worksheets/sheet{idx}.xml'
    src=ET.fromstring(original[key]); dst=ET.fromstring(data[key])
    for tag in ['cols','printOptions','pageMargins','pageSetup']:
        node=src.find(q(tag)); old=dst.find(q(tag))
        if old is not None: dst.remove(old)
        if node is not None:
            # Worksheet child order per SpreadsheetML.
            order=['sheetPr','dimension','sheetViews','sheetFormatPr','cols','sheetData','sheetCalcPr','sheetProtection','protectedRanges','scenarios','autoFilter','sortState','dataConsolidate','customSheetViews','mergeCells','phoneticPr','conditionalFormatting','dataValidations','hyperlinks','printOptions','pageMargins','pageSetup','headerFooter','rowBreaks','colBreaks','customProperties','cellWatches','ignoredErrors','smartTags','drawing','legacyDrawing','legacyDrawingHF','picture','oleObjects','controls','webPublishItems','tableParts','extLst']
            new_rank=order.index(tag)
            insert=len(dst)
            for k,child in enumerate(dst):
                local=child.tag.rsplit('}',1)[-1]
                if local in order and order.index(local)>new_rank: insert=k;break
            dst.insert(insert,copy.deepcopy(node))
    srcrows={row.attrib['r']:row for row in src.find(q('sheetData'))}
    for row in dst.find(q('sheetData')):
        source=srcrows.get(row.attrib['r'])
        if source is not None:
            for attr in ['ht','customHeight','thickTop','thickBot']:
                if attr in source.attrib:row.set(attr,source.attrib[attr])
                elif attr in row.attrib:del row.attrib[attr]
    pr=dst.find(q('sheetPr'))
    if pr is None:pr=ET.Element(q('sheetPr'));dst.insert(0,pr)
    pp=pr.find(q('pageSetUpPr'))
    if pp is None:pp=ET.SubElement(pr,q('pageSetUpPr'))
    pp.set('fitToPage','0');pp.set('autoPageBreaks','0')
    data[key]=ET.tostring(dst,encoding='utf-8',xml_declaration=True)
src=ET.fromstring(original['xl/workbook.xml']);dst=ET.fromstring(data['xl/workbook.xml'])
views=dst.find(q('bookViews'))
if views is None:
    views=ET.Element(q('bookViews'))
    dst.insert(list(dst).index(dst.find(q('sheets'))),views)
view=views.find(q('workbookView'))
if view is None:view=ET.SubElement(views,q('workbookView'))
view.set('activeTab',str(a.active_sheet))
for idx in range(1,5):
    key=f'xl/worksheets/sheet{idx}.xml'
    sheet=ET.fromstring(data[key])
    for v in sheet.findall(q('sheetViews')+'/'+q('sheetView')):
        v.set('tabSelected','1' if idx-1==a.active_sheet else '0')
    data[key]=ET.tostring(sheet,encoding='utf-8',xml_declaration=True)
names=dst.find(q('definedNames'))
if names is None:
    names=ET.Element(q('definedNames'))
    calc=dst.find(q('calcPr'))
    dst.insert(list(dst).index(calc) if calc is not None else len(dst),names)
for node in list(names):
    if node.attrib.get('name')=='_xlnm.Print_Area':names.remove(node)
for node in src.find(q('definedNames')):
    if node.attrib.get('name')=='_xlnm.Print_Area':names.append(copy.deepcopy(node))
data['xl/workbook.xml']=ET.tostring(dst,encoding='utf-8',xml_declaration=True)
temp=filled.with_suffix('.layout-tmp.xlsx')
with ZipFile(temp,'w',ZIP_DEFLATED) as z:
    for n,b in data.items():z.writestr(n,b)
temp.replace(filled)
print('Native-calibrated widths, heights, print settings, print areas and active worksheet preserved.')
