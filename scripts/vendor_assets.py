"""First-run maintainer tool only; event startup never downloads frontend assets."""
from pathlib import Path
from urllib.request import Request, urlopen
import re, hashlib, json
root=Path(__file__).resolve().parents[1]/'website'/'static'/'vendor'
manifest={}
def fetch(url, relative):
    path=root/relative; path.parent.mkdir(parents=True,exist_ok=True)
    data=urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=30).read()
    path.write_bytes(data)
    manifest[relative]={'url':url,'sha256':hashlib.sha256(data).hexdigest()}
    return data
fetch('https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css','bootstrap/bootstrap.min.css')
fetch('https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js','bootstrap/bootstrap.bundle.min.js')
fetch('https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/LICENSE','bootstrap/LICENSE')
css=fetch('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css','fontawesome/css/all.min.css').decode()
for name in set(re.findall(r'\.\./webfonts/([^\)]+)',css)):
    fetch('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/webfonts/'+name,'fontawesome/webfonts/'+name)
fetch('https://raw.githubusercontent.com/FortAwesome/Font-Awesome/6.4.2/LICENSE.txt','fontawesome/LICENSE.txt')
css=fetch('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap','poppins/poppins.css').decode()
for index,url in enumerate(set(re.findall(r'url\((https://[^)]+)\)',css))):
    name=f'poppins-{index}.'+url.rsplit('.',1)[1]
    fetch(url,'poppins/'+name); css=css.replace(url,name)
(root/'poppins'/'poppins.css').write_text(css)
fetch('https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/OFL.txt','poppins/OFL.txt')
(root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Vendored',len(manifest),'assets')
