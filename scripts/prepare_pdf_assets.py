"""Build print-size assets without changing the originals or PDF geometry."""
from pathlib import Path
from PIL import Image
root=Path(__file__).resolve().parents[1]/'website'/'static'
out=root/'pdf'; out.mkdir(exist_ok=True)
for name, size in [('header.png',(1754,225)),('JPCS.png',(296,296))]:
    with Image.open(root/name) as im:
        im.thumbnail(size, Image.Resampling.LANCZOS)
        if name == 'header.png':
            # The page underneath the background is white; flatten once at build time.
            background = Image.new('RGB', im.size, 'white')
            background.paste(im, mask=im.getchannel('A') if im.mode == 'RGBA' else None)
            im = background
        im.save(out/name, optimize=True)
        print(name,im.size)
