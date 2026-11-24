from pathlib import Path
import json
import pymupdf
from PIL import Image, ImageChops, ImageStat
root=Path('output/verification'); baseline=pymupdf.open(root/'baseline-isolated/report-final.pdf'); final=pymupdf.open(root/'final-isolated/report-final.pdf')
assert len(baseline)==len(final)
report={'pages':len(final),'text_and_positions_match':True,'pages_rendered':[]}
for i,(before,after) in enumerate(zip(baseline,final),1):
    assert before.get_text()==after.get_text(),f'Text changed on page {i}'
    assert before.get_text('words')==after.get_text('words'),f'Layout changed on page {i}'
    bp=before.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5)); ap=after.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5))
    filename=root/f'report-page-{i}.png';ap.save(filename)
    bi=Image.frombytes('RGB',(bp.width,bp.height),bp.samples); ai=Image.frombytes('RGB',(ap.width,ap.height),ap.samples)
    diff=ImageStat.Stat(ImageChops.difference(bi,ai))
    report['pages_rendered'].append({'file':str(filename),'mean_pixel_difference':round(sum(diff.mean)/3,4)})
(root/'pdf-comparison.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
